import math
from typing import Any

import numpy as np
import pytest

from reachy_claude.motion import (
    ACK_DURATION_S,
    MAX_ANTENNA_DEG,
    MAX_PITCH_DEG,
    MAX_ROLL_DEG,
    MAX_YAW_DEG,
    MAX_Z_MM,
    Animator,
    Mood,
    MovingVoice,
    Pose,
    acknowledge_overlay,
    mood_pose,
)


def fields(p: Pose) -> np.ndarray:
    return np.array([p.roll, p.pitch, p.yaw, p.z_mm, p.antenna_right, p.antenna_left])


@pytest.mark.parametrize("mood", list(Mood))
def test_every_mood_stays_within_safe_limits(mood: Mood) -> None:
    for step in range(0, 6000):
        p = mood_pose(mood, step * 0.01)
        assert p == p.clamped()  # Zielposen liegen schon innerhalb der Grenzen
        assert abs(p.roll) <= MAX_ROLL_DEG and abs(p.pitch) <= MAX_PITCH_DEG and abs(p.yaw) <= MAX_YAW_DEG
        assert abs(p.z_mm) <= MAX_Z_MM and 0 <= p.antenna_left <= MAX_ANTENNA_DEG


def test_moods_look_different() -> None:
    poses = {mood: fields(mood_pose(mood, 1.0)) for mood in Mood}
    for a in Mood:
        for b in Mood:
            if a is not b:
                assert not np.allclose(poses[a], poses[b])
    assert mood_pose(Mood.LISTENING, 0).roll > 0  # Kopf schraeg = aufmerksam
    assert mood_pose(Mood.THINKING, 0).pitch < 0  # Blick nach oben (Pitch < 0)


def test_clamped_limits_extreme_values() -> None:
    wild = Pose(roll=90, pitch=-90, yaw=180, z_mm=50, antenna_right=-20, antenna_left=500)
    c = wild.clamped()
    assert (c.roll, c.pitch, c.yaw, c.z_mm, c.antenna_right, c.antenna_left) == (
        MAX_ROLL_DEG,
        -MAX_PITCH_DEG,
        MAX_YAW_DEG,
        MAX_Z_MM,
        0.0,
        MAX_ANTENNA_DEG,
    )


def test_acknowledge_overlay_rises_and_fades() -> None:
    base = Pose(pitch=0, antenna_right=30, antenna_left=30)
    peak = acknowledge_overlay(base, ACK_DURATION_S / 2)
    assert peak.antenna_right < 1 and peak.pitch > 5  # Antennen hoch, kleines Nicken
    assert acknowledge_overlay(base, ACK_DURATION_S + 0.1) == base
    assert acknowledge_overlay(base, -1) == base


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FakeRobot:
    def __init__(self, fail: bool = False) -> None:
        self.targets: list[dict[str, Any]] = []
        self.fail = fail

    def set_target(self, head: Any = None, antennas: Any = None, body_yaw: Any = None) -> None:
        if self.fail:
            raise ConnectionError("weg")
        self.targets.append({"head": head, "antennas": antennas})


def builder(
    x: float, y: float, z: float, roll: float, pitch: float, yaw: float, mm: bool, degrees: bool
) -> tuple:
    assert mm and degrees
    return (z, roll, pitch, yaw)


def run_ticks(animator: Animator, clock: Clock, seconds: float) -> list[Pose]:
    poses = []
    for _ in range(int(seconds * 25)):
        clock.now += 0.04
        poses.append(animator.tick())
    return poses


def test_animator_sends_targets_with_sdk_conventions() -> None:
    clock, robot = Clock(), FakeRobot()
    animator = Animator(robot, builder, clock=clock)
    run_ticks(animator, clock, 2.0)
    last = robot.targets[-1]
    right, left = last["antennas"]
    assert right <= 0 <= left  # SDK: [rechts negativ, links positiv]
    assert math.isclose(-right, math.radians(animator.tick().antenna_right), abs_tol=0.05)
    assert len(last["head"]) == 4


def test_mood_changes_are_smooth_no_jumps() -> None:
    clock, robot = Clock(), FakeRobot()
    animator = Animator(robot, builder, clock=clock)
    poses = run_ticks(animator, clock, 2.0)
    for mood in (Mood.LISTENING, Mood.THINKING, Mood.SPEAKING, Mood.IDLE):
        animator.set_mood(mood)
        animator.acknowledge()
        poses += run_ticks(animator, clock, 2.0)
    steps = np.abs(np.diff(np.array([fields(p) for p in poses]), axis=0))
    assert steps.max() < 3.0  # hoechstens 3 Grad/mm pro 40 ms


def test_mood_is_reached() -> None:
    clock, robot = Clock(), FakeRobot()
    animator = Animator(robot, builder, clock=clock)
    animator.set_mood(Mood.LISTENING)
    pose = run_ticks(animator, clock, 3.0)[-1]
    assert pose.roll == pytest.approx(8.0, abs=0.5)


def test_network_errors_do_not_crash() -> None:
    clock = Clock()
    animator = Animator(FakeRobot(fail=True), builder, clock=clock)
    run_ticks(animator, clock, 1.0)  # darf keine Ausnahme werfen


def test_thread_start_stop_returns_to_neutral() -> None:
    robot = FakeRobot()
    animator = Animator(robot, builder, rate_hz=200)
    animator.set_mood(Mood.THINKING)
    animator.start()
    import time

    time.sleep(0.3)
    animator.stop(settle_s=0.5)
    assert len(robot.targets) > 20
    z, roll, pitch, yaw = robot.targets[-1]["head"]
    assert abs(pitch) < 3 and abs(yaw) < 3  # weich zurueck Richtung Grundstellung


def test_moving_voice_sets_speaking_and_restores() -> None:
    clock = Clock()
    animator = Animator(FakeRobot(), builder, clock=clock)
    animator.set_mood(Mood.THINKING)
    seen: list[Mood] = []

    class Voice:
        def say(self, text: str) -> None:
            seen.append(animator.mood)

    MovingVoice(Voice(), animator).say("Hallo")
    assert seen == [Mood.THINKING]  # die Grundstimmung bleibt ...
    assert animator.mood is Mood.THINKING


def test_speaking_is_shown_on_top_of_the_mood() -> None:
    clock = Clock()
    animator = Animator(FakeRobot(), builder, clock=clock)
    shown: list[Mood] = []

    class Voice:
        def say(self, text: str) -> None:
            shown.append(animator.shown_mood)

    MovingVoice(Voice(), animator).say("Hallo")
    assert shown == [Mood.SPEAKING]  # ... gezeigt wird "spricht"
    assert animator.shown_mood is Mood.IDLE


def test_mood_change_while_speaking_is_not_undone_afterwards() -> None:
    """Fund der Pruefrunde: MovingVoice stellte die Stimmung von *vor* dem Sprechen wieder her –
    wurde Claude waehrenddessen fertig (THINKING -> IDLE), blieb Reachy im Denk-Modus haengen."""
    clock = Clock()
    animator = Animator(FakeRobot(), builder, clock=clock)
    animator.set_mood(Mood.THINKING)

    class Voice:
        def say(self, text: str) -> None:
            animator.set_mood(Mood.IDLE)  # Claude wird fertig, waehrend Reachy spricht

    MovingVoice(Voice(), animator).say("Claude arbeitet noch am letzten Auftrag.")
    assert animator.shown_mood is Mood.IDLE
