"""Stufe 1: Gespraech mit Reachy live als Text anzeigen.

Die Conversation-App auf Reachy verschickt ueber ihren JSON-RPC-WebSocket
(``ws://<roboter>:7860/rpc``) bei jedem fertigen Satz eine Benachrichtigung
``conversation.transcript`` mit ``role`` ("user" = du, "assistant" = Reachy)
und ``text``. Dieser Modul verbindet sich dorthin, liest nur mit und gibt das
Gespraech im Terminal aus. Am Roboter muss dafuer nichts geaendert werden.

Alles, was vom Roboter kommt, gilt als nicht vertrauenswuerdig: Steuerzeichen
werden entfernt, damit niemand ueber den Text das Terminal manipulieren kann.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import WebSocketException
from websockets.typing import Data

logger = logging.getLogger(__name__)

DEFAULT_PORT = 7860
RPC_PATH = "/rpc"
MAX_MESSAGE_BYTES = 256 * 1024
STATUS_REQUEST_ID = 1
RETRY_START_S = 2.0
RETRY_MAX_S = 30.0

SPEAKER_LABELS = {"user": "Du:    ", "assistant": "Reachy:"}
TURN_LABELS = {
    "listening": "… hoert zu",
    "thinking": "… denkt nach",
    "speaking": "… spricht",
    "ready": "… bereit",
}
# C0/C1-Steuerzeichen inkl. ESC (ANSI-Sequenzen); Tab/Zeilenumbruch werden zu Leerzeichen.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")


@dataclass(frozen=True)
class Transcript:
    """Ein fertig erkannter Satz."""

    role: str  # "user" oder "assistant"
    text: str


@dataclass(frozen=True)
class TurnState:
    """Gespraechszustand (zuhoeren, nachdenken, sprechen, bereit)."""

    state: str


@dataclass(frozen=True)
class Status:
    """Antwort auf ``conversation.status``."""

    backend_connected: bool
    connection_mode: str | None
    backend_error: str | None


Event = Transcript | TurnState | Status


def clean_text(text: str) -> str:
    """Steuerzeichen entfernen und Whitespace normalisieren."""
    return " ".join(_CONTROL_CHARS_RE.sub(" ", text).split())


def build_url(robot: str, port: int = DEFAULT_PORT) -> str:
    """WebSocket-Adresse aus Hostname oder vollstaendiger URL bilden."""
    if "://" in robot:
        parts = urlsplit(robot)
        if parts.scheme not in {"ws", "wss"} or not parts.hostname:
            raise ValueError("Die Adresse muss mit ws:// oder wss:// beginnen.")
        return robot
    host = robot.strip()
    if not host or any(c in host for c in "/?#@ "):
        raise ValueError(f"Ungueltiger Roboter-Name: {robot!r}")
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"  # IPv6-Adresse
    return f"ws://{host}:{port}{RPC_PATH}"


def parse_message(raw: str | bytes) -> Event | None:
    """Eine Nachricht vom Roboter auswerten; Unbekanntes wird ignoriert (``None``)."""
    try:
        message = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(message, dict):
        return None

    if message.get("id") == STATUS_REQUEST_ID and isinstance(message.get("result"), dict):
        result = message["result"]
        mode = result.get("hf_connection_mode")
        error = result.get("backend_error")
        return Status(
            backend_connected=result.get("backend_connected") is True,
            connection_mode=clean_text(mode) if isinstance(mode, str) else None,
            backend_error=clean_text(error) if isinstance(error, str) and error else None,
        )

    params = message.get("params")
    if not isinstance(params, dict):
        return None
    method = message.get("method")
    if method == "conversation.transcript":
        role, text = params.get("role"), params.get("text")
        if role in SPEAKER_LABELS and isinstance(text, str) and params.get("final", True) is not False:
            cleaned = clean_text(text)
            return Transcript(role=role, text=cleaned) if cleaned else None
    elif method == "conversation.turn":
        state = params.get("state")
        if state in TURN_LABELS:
            return TurnState(state=state)
    return None


def format_event(event: Event, now: float | None = None) -> str:
    """Eine Bildschirmzeile fuer ein Ereignis erzeugen."""
    stamp = time.strftime("%H:%M:%S", time.localtime(now))
    if isinstance(event, Transcript):
        return f"{stamp}  {SPEAKER_LABELS[event.role]} {event.text}"
    if isinstance(event, TurnState):
        return f"{stamp}          {TURN_LABELS[event.state]}"
    if event.backend_connected:
        mode = {"deployed": "Hugging-Face-Cloud", "local": "lokal"}.get(
            event.connection_mode or "", "unbekannt"
        )
        return f"{stamp}  Sprachdienst verbunden ({mode}). Sprich mit Reachy!"
    reason = f": {event.backend_error}" if event.backend_error else ""
    return f"{stamp}  Achtung: Reachys Sprachdienst ist nicht verbunden{reason}"


def append_transcript(path: Path, event: Transcript, now: float | None = None) -> None:
    """Satz an eine Markdown-Mitschrift anhaengen."""
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
    speaker = "Du" if event.role == "user" else "Reachy"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"- {stamp} **{speaker}:** {event.text}\n")


async def listen(
    url: str,
    output: Callable[[str], None],
    *,
    show_turns: bool = False,
    transcript_file: Path | None = None,
    stop: asyncio.Event | None = None,
    retry_start_s: float = RETRY_START_S,
) -> None:
    """Mit Reachy verbinden und Ereignisse ausgeben; verbindet sich bei Abbruch neu."""
    stop = stop or asyncio.Event()
    delay = retry_start_s
    while not stop.is_set():
        try:
            async with connect(url, max_size=MAX_MESSAGE_BYTES, open_timeout=10) as ws:
                output(f"Verbunden mit {url}")
                delay = retry_start_s
                request = {
                    "jsonrpc": "2.0",
                    "id": STATUS_REQUEST_ID,
                    "method": "conversation.status",
                    "params": {},
                }
                await ws.send(json.dumps(request))
                async for raw in _until_stopped(ws, stop):
                    event = parse_message(raw)
                    if event is None or (isinstance(event, TurnState) and not show_turns):
                        continue
                    output(format_event(event))
                    if transcript_file is not None and isinstance(event, Transcript):
                        try:
                            append_transcript(transcript_file, event)
                        except OSError as exc:
                            logger.error("Mitschrift konnte nicht geschrieben werden: %s", exc)
                if stop.is_set():
                    return
                output("Verbindung zu Reachy beendet.")
        except (OSError, TimeoutError, WebSocketException) as exc:
            output(f"Reachy nicht erreichbar ({type(exc).__name__}: {exc}). Neuer Versuch in {delay:.0f} s …")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=delay)
        delay = min(delay * 2, RETRY_MAX_S)


async def _until_stopped(ws: ClientConnection, stop: asyncio.Event) -> AsyncIterator[Data]:
    """Nachrichten liefern, bis die Verbindung endet oder ``stop`` gesetzt wird."""
    stop_task = asyncio.ensure_future(stop.wait())
    try:
        while True:
            recv_task = asyncio.ensure_future(ws.recv())
            done, _ = await asyncio.wait({recv_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
            if stop_task in done:
                recv_task.cancel()
                return
            try:
                yield recv_task.result()
            except WebSocketException:
                return
    finally:
        stop_task.cancel()
