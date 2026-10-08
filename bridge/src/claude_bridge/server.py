"""HTTP-Server der Bridge (nur Standardbibliothek).

Endpunkte (alle signiert, siehe ``signing.py``):
- ``POST /v1/ask``    ``{"prompt": str, "new_conversation": bool}`` -> ``{"spoken_text": ...}``
- ``POST /v1/reset``  neue Claude-Sitzung beginnen
- ``GET  /v1/health`` Erreichbarkeit + Signatur pruefen

Pruefreihenfolge je Anfrage: IP-Allowlist -> Groesse -> Signatur/Replay ->
Rate-Limit -> Eingabe -> "nur ein Auftrag gleichzeitig".
"""

from __future__ import annotations

import collections
import json
import logging
import ssl
import threading
import time
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .config import BridgeConfig
from .runner import AskService, ClaudeError, write_transcript
from .signing import HEADER_RESPONSE_SIGNATURE, ReplayGuard, sign_response, verify_request
from .speech import make_spoken_text

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 64 * 1024
REQUEST_READ_TIMEOUT_S = 15


class RateLimiter:
    """Gleitendes Fenster: hoechstens ``limit`` Anfragen pro 60 s."""

    def __init__(self, limit: int, clock: Callable[[], float] = time.monotonic) -> None:
        self._limit = limit
        self._clock = clock
        self._hits: collections.deque[float] = collections.deque()
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            now = self._clock()
            while self._hits and now - self._hits[0] > 60:
                self._hits.popleft()
            if len(self._hits) >= self._limit:
                return False
            self._hits.append(now)
            return True


class BridgeServer(ThreadingHTTPServer):
    """HTTP-Server mit gemeinsamem Zustand fuer alle Handler."""

    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, config: BridgeConfig, service: AskService) -> None:
        self.config = config
        self.service = service
        self.replay_guard = ReplayGuard()
        self.rate_limiter = RateLimiter(config.rate_limit_per_min)
        self.job_lock = threading.Lock()
        super().__init__((config.host, config.port), BridgeHandler)
        if config.tls_cert and config.tls_key:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(config.tls_cert, config.tls_key)
            self.socket = context.wrap_socket(self.socket, server_side=True)


class BridgeHandler(BaseHTTPRequestHandler):
    """Ein Handler pro Verbindung."""

    server: BridgeServer
    server_version = "claude-bridge"
    sys_version = ""
    timeout = REQUEST_READ_TIMEOUT_S

    # ------------------------------------------------------------ Hilfsfunktionen
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - Signatur der Basisklasse
        logger.info("%s %s", self.client_address[0], format % args)

    def _send(self, status: HTTPStatus, payload: dict[str, Any], nonce: str | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if nonce is not None:
            self.send_header(
                HEADER_RESPONSE_SIGNATURE, sign_response(self.server.config.token, nonce, int(status), body)
            )
        self.end_headers()
        self.wfile.write(body)

    def _authorize(self) -> tuple[str, bytes] | None:
        """Gemeinsame Pruefungen. Gibt (nonce, body) zurueck oder hat schon geantwortet."""
        cfg = self.server.config
        if not cfg.client_allowed(self.client_address[0]):
            logger.warning("Abgelehnt (IP nicht erlaubt): %s", self.client_address[0])
            self._send(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
            return None
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY_BYTES:
            self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "too large"})
            return None
        body = self.rfile.read(length) if length else b""
        headers = dict(self.headers.items())
        nonce = verify_request(cfg.token, self.command, self.path, headers, body, self.server.replay_guard)
        if nonce is None:
            logger.warning("Abgelehnt (Signatur/Zeit/Replay): %s %s", self.client_address[0], self.path)
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return None
        if not self.server.rate_limiter.allow():
            self._send(
                HTTPStatus.TOO_MANY_REQUESTS, {"error": "Zu viele Anfragen, bitte kurz warten."}, nonce
            )
            return None
        return nonce, body

    # ------------------------------------------------------------------ Routen
    def do_GET(self) -> None:  # noqa: N802 - Name von BaseHTTPRequestHandler vorgegeben
        if self.path != "/v1/health":
            self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        auth = self._authorize()
        if auth is None:
            return
        nonce, _ = auth
        self._send(HTTPStatus.OK, {"status": "ok", "busy": self.server.job_lock.locked()}, nonce)

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in {"/v1/ask", "/v1/reset"}:
            self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        auth = self._authorize()
        if auth is None:
            return
        nonce, body = auth
        if self.path == "/v1/reset":
            self.server.service.reset()
            self._send(HTTPStatus.OK, {"status": "ok"}, nonce)
            return
        self._handle_ask(nonce, body)

    def _handle_ask(self, nonce: str, body: bytes) -> None:
        cfg = self.server.config
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send(HTTPStatus.BAD_REQUEST, {"error": "Ungueltiges JSON."}, nonce)
            return
        prompt = payload.get("prompt") if isinstance(payload, dict) else None
        new_conversation = (
            bool(payload.get("new_conversation", False)) if isinstance(payload, dict) else False
        )
        if not isinstance(prompt, str) or not prompt.strip():
            self._send(HTTPStatus.BAD_REQUEST, {"error": "Der Auftrag ist leer."}, nonce)
            return
        prompt = prompt.strip()
        if len(prompt) > cfg.max_prompt_chars:
            self._send(HTTPStatus.BAD_REQUEST, {"error": "Der Auftrag ist zu lang."}, nonce)
            return
        if not self.server.job_lock.acquire(blocking=False):
            self._send(HTTPStatus.CONFLICT, {"error": "Claude arbeitet noch am vorigen Auftrag."}, nonce)
            return
        try:
            logger.info("Auftrag (%d Zeichen)%s", len(prompt), f": {prompt}" if cfg.log_prompts else "")
            try:
                result = self.server.service.ask(prompt, new_conversation)
            except ClaudeError as exc:
                self._send(HTTPStatus.BAD_GATEWAY, {"error": str(exc)}, nonce)
                return
            if cfg.transcript_dir is not None:
                try:
                    path = write_transcript(cfg.transcript_dir, prompt, result)
                except OSError as exc:
                    logger.error("Mitschrift konnte nicht geschrieben werden: %s", exc)
                else:
                    logger.info("Vollstaendige Antwort: %s", path)
            spoken = make_spoken_text(result.text, cfg.spoken_max_chars)
            self._send(
                HTTPStatus.OK,
                {
                    "status": "error" if result.is_error else "ok",
                    "spoken_text": spoken,
                    "duration_s": round(result.duration_s, 1),
                },
                nonce,
            )
        finally:
            self.server.job_lock.release()
