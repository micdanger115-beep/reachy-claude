"""Verbindung zu Reachy ueber das offizielle SDK (``reachy_mini``).

Der PC verbindet sich als Netzwerk-Client mit dem Daemon des Roboters (Port 8000).
Mikrofon und Lautsprecher laufen ueber WebRTC; die Signalisierung uebernimmt der
Roboter selbst (Port 8443) – es ist kein Cloud-Dienst beteiligt.

``reachy_mini`` wird erst beim Verbinden importiert, damit die uebrigen Module
(und ihre Tests) ohne das grosse SDK auskommen.
"""

from __future__ import annotations

import logging
import socket
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

from .audio import SAMPLE_RATE

logger = logging.getLogger(__name__)

DEFAULT_ROBOT = "reachy-mini.local"
DAEMON_PORT = 8000
WEBRTC_SIGNALING_PORT = 8443


class RobotMedia(Protocol):
    """Der Teil von ``ReachyMini.media``, den wir benutzen (im Test ersetzbar)."""

    def start_recording(self) -> None: ...
    def stop_recording(self) -> None: ...
    def get_audio_sample(self) -> npt.NDArray[np.float32] | None: ...
    def get_input_audio_samplerate(self) -> int: ...
    def start_playing(self) -> None: ...
    def stop_playing(self) -> None: ...
    def push_audio_sample(self, data: npt.NDArray[np.float32]) -> None: ...
    def get_output_audio_samplerate(self) -> int: ...


class _DropMissingUsbAudio(logging.Filter):
    """Das SDK sucht auf dem PC eine USB-Soundkarte von Reachy; bei der WLAN-Variante gibt es keine."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "No Reachy Mini Audio USB device" not in record.getMessage()


logging.getLogger("reachy_mini.media.audio_control_utils").addFilter(_DropMissingUsbAudio())


class RobotConnectionError(RuntimeError):
    """Reachy ist nicht erreichbar (Text ist fuer den Nutzer gedacht)."""


def port_open(host: str, port: int, timeout_s: float = 3.0) -> bool:
    """Ist ``host:port`` per TCP erreichbar?"""
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def explain_connection_failure(host: str, exc: Exception) -> str:
    """Verstaendliche Fehlermeldung: Roboter gar nicht erreichbar oder nur Audio/Video nicht?"""
    detail = f"({type(exc).__name__}: {exc})"
    if not port_open(host, DAEMON_PORT):
        return (
            f"Reachy unter '{host}' nicht erreichbar {detail}. Ist Reachy eingeschaltet und im selben WLAN? "
            "Notfalls die IP-Adresse angeben (--robot 192.168.x.y)."
        )
    if not port_open(host, WEBRTC_SIGNALING_PORT):
        return (
            f"Reachy ist erreichbar, aber sein Audio/Video-Dienst (WebRTC, Port {WEBRTC_SIGNALING_PORT}) "
            f"antwortet nicht {detail}. Reachy im Dashboard neu starten und es erneut versuchen."
        )
    return f"Verbindung zu Reachy fehlgeschlagen {detail}. Mit --debug starten fuer Details."


@contextmanager
def connect(host: str = DEFAULT_ROBOT, timeout_s: float = 10.0, debug: bool = False) -> Iterator[Any]:
    """Mit Reachy verbinden (Kontextmanager, gibt ``ReachyMini`` zurueck)."""
    try:
        from reachy_mini import ReachyMini
    except ImportError as exc:  # pragma: no cover - haengt von der Installation ab
        raise RobotConnectionError(
            "Das Reachy-SDK ist nicht installiert. Starte das Programm ueber das Startskript."
        ) from exc
    try:
        mini = ReachyMini(
            host=host,
            connection_mode="network",
            media_backend="webrtc",
            timeout=timeout_s,
            log_level="DEBUG" if debug else "WARNING",
        )
    except Exception as exc:  # SDK wirft verschiedene Typen (Timeout, Verbindungsfehler, ...)
        logger.debug("Verbindungsfehler", exc_info=True)
        raise RobotConnectionError(explain_connection_failure(host, exc)) from exc
    with mini:
        yield mini


PLAYBACK_TAIL_S = 0.3  # Puffer, bis Reachys Lautsprecher wirklich fertig ist


def play(
    media: RobotMedia, samples: npt.NDArray[np.float32], sleep: Callable[[float], None] | None = None
) -> None:
    """Audio (16 kHz mono) auf Reachys Lautsprecher abspielen und warten, bis es fertig ist."""
    sleep = sleep or time.sleep
    media.start_playing()
    try:
        media.push_audio_sample(samples)  # nicht blockierend
        sleep(samples.size / SAMPLE_RATE + PLAYBACK_TAIL_S)
    finally:
        media.stop_playing()
