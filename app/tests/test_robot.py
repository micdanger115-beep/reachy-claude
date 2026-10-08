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
