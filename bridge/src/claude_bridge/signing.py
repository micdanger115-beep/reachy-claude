"""HMAC-Signaturen fuer Anfragen und Antworten (Protokoll "v1").

Das Token selbst wird nie uebertragen. Jede Anfrage traegt Zeitstempel und
Nonce; der Server lehnt alte oder doppelte Anfragen ab (Replay-Schutz). Die
Antwort ist an die Nonce der Anfrage gebunden, damit der Roboter keine
untergeschobenen Antworten vorliest.

Die gleiche Logik steckt (bewusst als Kopie, weil externe Tools Einzeldateien
sind) in ``robot/external_tools/ask_claude.py``; ``robot/tests`` prueft, dass
beide Seiten zusammenpassen.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass, field

PROTOCOL = "v1"
HEADER_TIMESTAMP = "X-Reachy-Timestamp"
HEADER_NONCE = "X-Reachy-Nonce"
HEADER_SIGNATURE = "X-Reachy-Signature"
HEADER_RESPONSE_SIGNATURE = "X-Bridge-Signature"
MAX_CLOCK_SKEW_S = 60
NONCE_HEX_LEN = 32


def _body_digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def sign_request(token: str, method: str, path: str, timestamp: int, nonce: str, body: bytes) -> str:
    """Signatur einer Anfrage berechnen."""
    canonical = f"{PROTOCOL}\n{method.upper()}\n{path}\n{timestamp}\n{nonce}\n{_body_digest(body)}"
    return hmac.new(token.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def sign_response(token: str, request_nonce: str, status: int, body: bytes) -> str:
    """Signatur einer Antwort berechnen (gebunden an die Nonce der Anfrage)."""
    canonical = f"{PROTOCOL}-resp\n{request_nonce}\n{status}\n{_body_digest(body)}"
    return hmac.new(token.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def new_nonce() -> str:
    """Zufaellige Nonce (128 Bit)."""
    return secrets.token_hex(NONCE_HEX_LEN // 2)


@dataclass
class ReplayGuard:
    """Merkt sich gesehene Nonces fuer die Dauer des Zeitfensters."""

    window_s: int = MAX_CLOCK_SKEW_S
    _seen: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def check_and_remember(self, nonce: str, now: float) -> bool:
        """True, wenn die Nonce neu ist (und merkt sie sich); False bei Wiederholung."""
        with self._lock:
            cutoff = now - 2 * self.window_s
            for old in [n for n, seen_at in self._seen.items() if seen_at < cutoff]:
                del self._seen[old]
            if nonce in self._seen:
                return False
            self._seen[nonce] = now
            return True


def verify_request(
    token: str,
    method: str,
    path: str,
    headers: dict[str, str],
    body: bytes,
    replay_guard: ReplayGuard,
    now: float | None = None,
) -> str | None:
    """Anfrage pruefen. Gibt die Nonce zurueck oder ``None``, wenn sie abgelehnt wird."""
    now = time.time() if now is None else now
    raw_ts = headers.get(HEADER_TIMESTAMP, "")
    nonce = headers.get(HEADER_NONCE, "")
    signature = headers.get(HEADER_SIGNATURE, "")
    if not raw_ts.isdigit() or len(nonce) != NONCE_HEX_LEN or not signature:
        return None
    try:
        int(nonce, 16)
    except ValueError:
        return None
    timestamp = int(raw_ts)
    if abs(now - timestamp) > MAX_CLOCK_SKEW_S:
        return None
    expected = sign_request(token, method, path, timestamp, nonce, body)
    # Signatur zuerst pruefen, damit Unbefugte den Nonce-Speicher nicht fuellen koennen.
    if not hmac.compare_digest(expected, signature):
        return None
    if not replay_guard.check_and_remember(nonce, now):
        return None
    return nonce
