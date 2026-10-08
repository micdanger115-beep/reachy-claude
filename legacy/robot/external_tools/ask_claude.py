"""Externes Tool fuer die Reachy-Mini-Conversation-App: Sprachauftraege an Claude Code auf dem PC.

Das Tool schickt den (transkribierten) Auftrag signiert an die ``claude-bridge``
auf dem PC und gibt den vorlesbaren Text zurueck. Die Conversation-App fuehrt
Tools im Hintergrund aus und sagt das Ergebnis an, sobald es da ist; das
Gespraech blockiert also nicht, waehrend Claude arbeitet.

Konfiguration (``.env`` der Conversation-App):
    CLAUDE_BRIDGE_URL       z. B. http://192.168.1.20:8787  (Pflicht)
    CLAUDE_BRIDGE_TOKEN     gleiches Token wie auf dem PC   (Pflicht)
    CLAUDE_BRIDGE_TIMEOUT_S Wartezeit in Sekunden (Standard 960)
    CLAUDE_BRIDGE_CA_FILE   nur bei HTTPS mit eigenem Zertifikat

Die Signaturlogik entspricht ``bridge/src/claude_bridge/signing.py``
(Einzeldatei, weil die App externe Tools dateiweise laedt).
"""

import os
import ssl
import hmac
import json
import time
import asyncio
import hashlib
import logging
import secrets
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
from dataclasses import dataclass

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies


logger = logging.getLogger(__name__)

ASK_PATH = "/v1/ask"
DEFAULT_TIMEOUT_S = 960.0  # etwas laenger als das Bridge-Timeout (900 s)
MAX_PROMPT_CHARS = 4000
MIN_TOKEN_LEN = 32
SPEAK_VERBATIM = "Lies spoken_text woertlich und vollstaendig vor, ohne ihn umzuformulieren."


class BridgeError(Exception):
    """Fehler, dessen Text der Roboter vorlesen kann."""


@dataclass(frozen=True)
class BridgeSettings:
    """Verbindungsdaten zur Bridge."""

    url: str
    token: str
    timeout_s: float
    ca_file: str | None

    @classmethod
    def from_env(cls, env: dict[str, str]) -> "BridgeSettings":
        """Einstellungen aus der Umgebung lesen und pruefen."""
        url = env.get("CLAUDE_BRIDGE_URL", "").strip().rstrip("/")
        token = env.get("CLAUDE_BRIDGE_TOKEN", "").strip()
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise BridgeError("Die Claude-Bruecke ist nicht eingerichtet: CLAUDE_BRIDGE_URL fehlt oder ist ungueltig.")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise BridgeError("CLAUDE_BRIDGE_URL darf nur Schema, Adresse und Port enthalten.")
        if len(token) < MIN_TOKEN_LEN:
            raise BridgeError("Die Claude-Bruecke ist nicht eingerichtet: CLAUDE_BRIDGE_TOKEN fehlt oder ist zu kurz.")
        try:
            timeout_s = float(env.get("CLAUDE_BRIDGE_TIMEOUT_S", DEFAULT_TIMEOUT_S))
        except ValueError as exc:
            raise BridgeError("CLAUDE_BRIDGE_TIMEOUT_S muss eine Zahl sein.") from exc
        return cls(url=url, token=token, timeout_s=timeout_s, ca_file=env.get("CLAUDE_BRIDGE_CA_FILE") or None)


def _sha256_hex(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def sign_request(token: str, method: str, path: str, timestamp: int, nonce: str, body: bytes) -> str:
    """Signatur einer Anfrage (Protokoll v1)."""
    canonical = f"v1\n{method.upper()}\n{path}\n{timestamp}\n{nonce}\n{_sha256_hex(body)}"
    return hmac.new(token.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def sign_response(token: str, request_nonce: str, status: int, body: bytes) -> str:
    """Erwartete Signatur einer Antwort (Protokoll v1)."""
    canonical = f"v1-resp\n{request_nonce}\n{status}\n{_sha256_hex(body)}"
    return hmac.new(token.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def post_to_bridge(settings: BridgeSettings, payload: dict[str, Any]) -> dict[str, Any]:
    """Signierte Anfrage senden, Antwortsignatur pruefen und JSON zurueckgeben (blockierend)."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    timestamp = int(time.time())
    nonce = secrets.token_hex(16)
    request = urllib.request.Request(
        settings.url + ASK_PATH,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-Reachy-Timestamp": str(timestamp),
            "X-Reachy-Nonce": nonce,
            "X-Reachy-Signature": sign_request(settings.token, "POST", ASK_PATH, timestamp, nonce, body),
        },
    )
    context = ssl.create_default_context(cafile=settings.ca_file) if settings.url.startswith("https") else None
    try:
        with urllib.request.urlopen(request, timeout=settings.timeout_s, context=context) as response:  # noqa: S310
            status, raw, signature = response.status, response.read(), response.headers.get("X-Bridge-Signature")
    except urllib.error.HTTPError as exc:
        status, raw, signature = exc.code, exc.read(), exc.headers.get("X-Bridge-Signature")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("Claude-Bruecke nicht erreichbar: %s", exc)
        raise BridgeError("Ich erreiche Claude auf dem PC gerade nicht. Laeuft die Bruecke?") from exc

    if status in {401, 403}:
        raise BridgeError(
            "Die Claude-Bruecke hat die Anfrage abgelehnt. Bitte Token, Uhrzeit und erlaubte IP pruefen."
        )
    expected = sign_response(settings.token, nonce, status, raw)
    if not signature or not hmac.compare_digest(signature, expected):
        logger.error("Antwort der Bruecke hat keine gueltige Signatur (HTTP %s) - verworfen.", status)
        raise BridgeError("Die Antwort vom PC war nicht vertrauenswuerdig und wurde verworfen.")
    try:
        answer = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BridgeError("Die Antwort vom PC war unlesbar.") from exc
    if not isinstance(answer, dict):
        raise BridgeError("Die Antwort vom PC war unlesbar.")
    if status != 200:
        raise BridgeError(str(answer.get("error") or f"Die Bruecke meldet Fehler {status}."))
    return answer


class AskClaude(Tool):
    """Auftrag an Claude Code auf dem PC weitergeben und die Erklaerung vorlesen."""

    name = "ask_claude"
    description = (
        "Send the user's request to Claude Code running on the user's PC, e.g. programming tasks, code "
        "questions or explanations about their project. Use it whenever the user addresses Claude "
        "('frag Claude', 'Claude soll', 'sag Claude') or asks for programming work. Pass the request "
        "in the user's own words, completely, without summarising. Claude may take several minutes; "
        "tell the user briefly that you passed it on. When the result arrives, read 'spoken_text' "
        "aloud verbatim."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The user's request for Claude, in the user's words and language.",
            },
            "new_conversation": {
                "type": "boolean",
                "description": "True only if the user explicitly wants to start a new Claude conversation.",
            },
        },
        "required": ["prompt"],
    }

    def __init__(self, env: dict[str, str] | None = None) -> None:
        """Feste Umgebung fuer Tests uebernehmen; ohne Angabe wird os.environ bei jedem Aufruf gelesen."""
        self._env = env

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Auftrag an die Bridge senden und das Ergebnis zurueckgeben."""
        prompt = str(kwargs.get("prompt") or "").strip()
        new_conversation = kwargs.get("new_conversation") is True
        if not prompt:
            return {"error": "Ich habe keinen Auftrag fuer Claude verstanden."}
        if len(prompt) > MAX_PROMPT_CHARS:
            return {"error": "Der Auftrag ist zu lang. Bitte kuerzer formulieren."}
        logger.info("Tool call: ask_claude (%d Zeichen, neu=%s)", len(prompt), new_conversation)
        try:
            # os.environ erst zur Laufzeit lesen: die App laedt ihre .env beim Start.
            settings = BridgeSettings.from_env(self._env if self._env is not None else dict(os.environ))
            answer = await asyncio.to_thread(
                post_to_bridge, settings, {"prompt": prompt, "new_conversation": new_conversation}
            )
        except BridgeError as exc:
            return {"error": str(exc)}
        spoken = str(answer.get("spoken_text") or "").strip()
        if not spoken:
            return {"error": "Claude ist fertig, hat aber nichts Vorlesbares geliefert."}
        return {"status": str(answer.get("status", "ok")), "spoken_text": spoken, "instruction": SPEAK_VERBATIM}
