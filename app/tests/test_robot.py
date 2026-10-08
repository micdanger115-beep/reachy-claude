import socket

import pytest

from reachy_claude import robot


def test_port_open_detects_listening_socket() -> None:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    port = server.getsockname()[1]
    try:
        assert robot.port_open("127.0.0.1", port)
    finally:
        server.close()
    assert not robot.port_open("127.0.0.1", port, timeout_s=0.5)


@pytest.mark.parametrize(
    ("open_ports", "expected"),
    [
        (set(), "nicht erreichbar"),
        ({robot.DAEMON_PORT}, "Audio/Video-Dienst"),
        ({robot.DAEMON_PORT, robot.WEBRTC_SIGNALING_PORT}, "--debug"),
    ],
)
def test_failure_explanation_distinguishes_causes(
    monkeypatch: pytest.MonkeyPatch, open_ports: set[int], expected: str
) -> None:
    monkeypatch.setattr(robot, "port_open", lambda host, port, timeout_s=3.0: port in open_ports)
    message = robot.explain_connection_failure("reachy", ConnectionError("x"))
    assert expected in message


class LateMicMedia:
    """Mikrofon liefert erst nach einigen Abfragen Daten (WebRTC-Aufbau)."""

    def __init__(self, none_calls: int) -> None:
        self.none_calls = none_calls
        self.calls = 0
        self.started = False

    def start_recording(self) -> None:
        self.started = True

    def get_audio_sample(self) -> object:
        self.calls += 1
        return None if self.calls <= self.none_calls else [[0.0, 0.0]]


class StepClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_wait_for_audio_returns_once_microphone_delivers() -> None:
    media = LateMicMedia(none_calls=25)
    clock = StepClock()
    robot.wait_for_audio(media, timeout_s=5, clock=clock, sleep=clock.sleep)  # type: ignore[arg-type]
    assert media.started and media.calls == 26


def test_wait_for_audio_times_out_with_explanation() -> None:
    media = LateMicMedia(none_calls=10**9)
    clock = StepClock()
    with pytest.raises(robot.RobotConnectionError, match="Audio-Verbindung"):
        robot.wait_for_audio(media, timeout_s=1, clock=clock, sleep=clock.sleep)  # type: ignore[arg-type]
