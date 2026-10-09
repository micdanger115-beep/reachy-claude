"""Schritt 5: Reachy wirkt lebendig – Kopf und Antennen passend zur Situation.

Ein Hintergrund-Thread schickt ~25 Mal pro Sekunde eine Zielpose an Reachy
(``ReachyMini.set_target``). Die Pose haengt von der Stimmung ab und wird weich
angesteuert, damit nichts ruckelt:

- ``IDLE``       ruhig "atmen": Kopf leicht auf/ab, Antennen sanft gegenlaeufig
- ``LISTENING``  du sprichst: Kopf leicht schraeg, Antennen aufmerksam aufgestellt
- ``THINKING``   Claude arbeitet: Blick leicht nach oben/zur Seite, Antennen wandern langsam
- ``SPEAKING``   Reachy spricht (Ebene ueber der Stimmung): der Roboter wackelt selbst passend zur Sprache
                 (``enable_wobbling``), wir halten Kopf ruhig und bewegen nur die Antennen
Zusaetzlich ``acknowledge()``: kurzes "Antennen hoch" beim Wort "Claude".

Werte orientieren sich an Pollens eigenem "Atmen" (Kopf +-5 mm, Antennen +-15 Grad).
Richtungen laut SDK: Pitch > 0 = nach unten; Antennen [rechts, links] in Radiant,
(-0.17, +0.17) = aufrecht, (-3.05, +3.05) = flach (Schlafhaltung).
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Protocol

logger = logging.getLogger(__name__)

RATE_HZ = 25.0
SMOOTHING_S = 0.35  # Zeitkonstante der Glaettung: so schnell folgt Reachy einer neuen Stimmung
ACK_DURATION_S = 0.7
NEUTRAL_ANTENNA_DEG = 10.0  # Pollens Grundstellung (leicht schraeg, weniger Zittern)

# Sicherheitsgrenzen (Grad / mm): weit innerhalb dessen, was das SDK selbst begrenzt.
MAX_ROLL_DEG = 15.0
MAX_PITCH_DEG = 15.0
MAX_YAW_DEG = 20.0
MAX_Z_MM = 10.0
MIN_ANTENNA_DEG = 0.0
MAX_ANTENNA_DEG = 60.0


class Mood(Enum):
    """Was Reachy gerade "tut"."""

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


@dataclass(frozen=True)
class Pose:
    """Kopf (Grad, mm) und Antennen-Auslenkung (Grad, 0 = senkrecht, symmetrisch je Seite)."""

    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    z_mm: float = 0.0
    antenna_right: float = NEUTRAL_ANTENNA_DEG
    antenna_left: float = NEUTRAL_ANTENNA_DEG

    def clamped(self) -> Pose:
        """Pose auf sichere Grenzen beschraenken."""

        def lim(value: float, limit: float) -> float:
            return max(-limit, min(limit, value))

        def ant(value: float) -> float:
            return max(MIN_ANTENNA_DEG, min(MAX_ANTENNA_DEG, value))

        return Pose(
            roll=lim(self.roll, MAX_ROLL_DEG),
            pitch=lim(self.pitch, MAX_PITCH_DEG),
            yaw=lim(self.yaw, MAX_YAW_DEG),
            z_mm=lim(self.z_mm, MAX_Z_MM),
            antenna_right=ant(self.antenna_right),
            antenna_left=ant(self.antenna_left),
        )

    def blend(self, target: Pose, alpha: float) -> Pose:
        """Ein Stueck (``alpha`` 0..1) in Richtung ``target`` gehen."""
        a = min(1.0, max(0.0, alpha))
        return Pose(
            *(
                current + (goal - current) * a
                for current, goal in zip(
                    (self.roll, self.pitch, self.yaw, self.z_mm, self.antenna_right, self.antenna_left),
                    (
                        target.roll,
                        target.pitch,
                        target.yaw,
                        target.z_mm,
                        target.antenna_right,
                        target.antenna_left,
                    ),
                    strict=True,
                )
            )
        )


def _wave(t: float, hz: float, phase: float = 0.0) -> float:
    return math.sin(2.0 * math.pi * hz * t + phase)


def mood_pose(mood: Mood, t: float) -> Pose:
    """Zielpose fuer eine Stimmung zum Zeitpunkt ``t`` (Sekunden) – reine Funktion, gut testbar."""
    if mood is Mood.LISTENING:
        # aufmerksam: Kopf leicht schraeg, Antennen aufgestellt und leicht "lauschend"
        return Pose(
            roll=8.0,
            pitch=-3.0,
            z_mm=2.0 * _wave(t, 0.2),
            antenna_right=4.0 + 4.0 * _wave(t, 0.8),
            antenna_left=4.0 + 4.0 * _wave(t, 0.8, math.pi / 2),
        )
    if mood is Mood.THINKING:
        # nachdenklich: Blick nach oben zur Seite, Kopf pendelt langsam, Antennen wandern abwechselnd
        return Pose(
            roll=-5.0 + 2.0 * _wave(t, 0.15),
            pitch=-8.0,
            yaw=12.0 * _wave(t, 0.08),
            antenna_right=25.0 + 15.0 * _wave(t, 0.4),
            antenna_left=25.0 + 15.0 * _wave(t, 0.4, math.pi),
        )
    if mood is Mood.SPEAKING:
        # Kopf ruhig (der Roboter wackelt selbst zur Sprache), Antennen lebhaft
        return Pose(
            antenna_right=15.0 + 10.0 * _wave(t, 1.2),
            antenna_left=15.0 + 10.0 * _wave(t, 1.2, math.pi / 3),
        )
    # IDLE: ruhig atmen
    sway = 12.0 * _wave(t, 0.3)
    return Pose(
        z_mm=4.0 * _wave(t, 0.1),
        antenna_right=NEUTRAL_ANTENNA_DEG + 8.0 + sway,
        antenna_left=NEUTRAL_ANTENNA_DEG + 8.0 - sway,
    )


def acknowledge_overlay(pose: Pose, since_s: float) -> Pose:
    """Kurzes "Antennen hoch + Nicken" nach dem Aktivierungswort (klingt in ``ACK_DURATION_S`` ab)."""
    if not 0.0 <= since_s < ACK_DURATION_S:
        return pose
    strength = math.sin(math.pi * since_s / ACK_DURATION_S)  # 0 -> 1 -> 0
    return replace(
        pose,
        pitch=pose.pitch + 6.0 * strength,
        antenna_right=pose.antenna_right * (1.0 - strength),
        antenna_left=pose.antenna_left * (1.0 - strength),
    )


class RobotBody(Protocol):
    """Der Teil von ``ReachyMini``, den die Bewegung braucht."""

    def set_target(self, head: Any = None, antennas: Any = None, body_yaw: Any = None) -> None: ...


HeadPoseBuilder = Callable[..., Any]


class Animator:
    """Bewegt Reachy im Hintergrund passend zur aktuellen Stimmung."""

    def __init__(
        self,
        robot: RobotBody,
        head_pose: HeadPoseBuilder,
        *,
        rate_hz: float = RATE_HZ,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._robot = robot
        self._head_pose = head_pose
        self._period = 1.0 / rate_hz
        self._clock = clock or time.monotonic
        self._mood = Mood.IDLE
        self._speaking = 0  # wie viele Saetze gerade gesprochen werden (Ebene ueber der Stimmung)
        self._ack_at: float | None = None
        self._current = Pose()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_at = self._clock()
        self._last_tick: float | None = None
        self._errors = 0

    @property
    def mood(self) -> Mood:
        with self._lock:
            return self._mood

    @property
    def shown_mood(self) -> Mood:
        """Was Reachy gerade zeigt: "spricht" liegt ueber der Grundstimmung."""
        with self._lock:
            return Mood.SPEAKING if self._speaking else self._mood

    def speaking(self, active: bool) -> None:
        """Sprechen beginnt/endet – die Grundstimmung bleibt davon unberuehrt."""
        with self._lock:
            self._speaking = max(0, self._speaking + (1 if active else -1))

    def set_mood(self, mood: Mood) -> None:
        """Stimmung wechseln (wird weich uebergeblendet)."""
        with self._lock:
            if mood is not self._mood:
                logger.debug("Stimmung: %s -> %s", self._mood.value, mood.value)
            self._mood = mood

    def acknowledge(self) -> None:
        """Kurze Bestaetigung (Antennen hoch, leichtes Nicken)."""
        with self._lock:
            self._ack_at = self._clock()

    def tick(self) -> Pose:
        """Eine Pose berechnen und senden (vom Thread aufgerufen; im Test direkt)."""
        now = self._clock()
        dt = self._period if self._last_tick is None else max(0.0, now - self._last_tick)
        self._last_tick = now
        mood = self.shown_mood
        with self._lock:
            ack_at = self._ack_at
        target = mood_pose(mood, now - self._started_at)
        if ack_at is not None:
            target = acknowledge_overlay(target, now - ack_at)
        self._current = self._current.blend(target, dt / SMOOTHING_S).clamped()
        self._send(self._current)
        return self._current

    def _send(self, pose: Pose) -> None:
        head = self._head_pose(0, 0, pose.z_mm, pose.roll, pose.pitch, pose.yaw, mm=True, degrees=True)
        antennas = [-math.radians(pose.antenna_right), math.radians(pose.antenna_left)]
        try:
            self._robot.set_target(head=head, antennas=antennas)
            self._errors = 0
        except Exception as exc:  # Netzwerk-/Verbindungsfehler: nicht abstuerzen, nur melden
            self._errors += 1
            if self._errors in (1, 50):
                logger.warning("Bewegung konnte nicht gesendet werden: %s", exc)

    def start(self) -> None:
        """Hintergrund-Thread starten."""
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="bewegung", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            self.tick()
            self._stop.wait(max(0.0, self._period - (time.monotonic() - started)))

    def stop(self, settle_s: float = 1.0) -> None:
        """Weich in die Grundstellung zurueck und Thread beenden."""
        if self._thread is None:
            return
        self.set_mood(Mood.IDLE)
        with self._lock:
            self._ack_at = None
        self._stop.set()
        self._thread.join(timeout=2.0)
        self._thread = None
        steps = max(1, int(settle_s / self._period))
        for _ in range(steps):
            self._current = self._current.blend(Pose(), 0.2)
            self._send(self._current)
            time.sleep(self._period)


class MovingVoice:
    """Laesst Reachy sprechen und zeigt dabei "spricht" – als Ebene ueber der Stimmung.

    (Frueher wurde die Stimmung von *vor* dem Sprechen wiederhergestellt; aenderte sie sich
    waehrenddessen – z. B. Claude wurde fertig –, blieb Reachy in der alten Stimmung haengen.)
    """

    def __init__(self, voice: Any, animator: Animator) -> None:
        self._voice = voice
        self._animator = animator

    def say(self, text: str) -> None:
        self._animator.speaking(True)
        try:
            self._voice.say(text)
        finally:
            self._animator.speaking(False)
