import json
from pathlib import Path

import pytest
from conftest import FAKE_CLAUDE

from reachy_claude import doctor
from reachy_claude.doctor import (
    Check,
    Level,
    check_claude,
    check_gpu,
    check_packages,
    check_project,
    check_robot,
    check_robot_software,
    check_voice,
    has_errors,
    parse_version,
    report,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("1.11.0", (1, 11, 0)), ("1.12.0rc1", (1, 12, 0)), ("v2.0", (2, 0, 0)), ("", None), ("abc", None)],
)
def test_parse_version(text: str, expected: tuple[int, ...] | None) -> None:
    assert parse_version(text) == expected


def test_packages() -> None:
    assert check_packages(lambda _m: object()).level is Level.OK
    missing = check_packages(lambda m: None if m == "piper" else object())
    assert (
        missing.level is Level.FEHLER and "Sprachausgabe" in missing.message and "app\\.venv" in missing.fix
    )


def test_gpu() -> None:
    assert check_gpu("auto", lambda: 1).level is Level.OK
    assert check_gpu("auto", lambda: 0).level is Level.WARNUNG
    assert check_gpu("cuda", lambda: 0).level is Level.FEHLER  # ausdruecklich GPU verlangt
    assert check_gpu("cpu", lambda: 0).level is Level.OK

    def broken() -> int:
        raise OSError("cudnn fehlt")

    result = check_gpu("auto", broken)
    assert result.level is Level.WARNUNG and "OSError" in result.message


def test_voice(tmp_path: Path) -> None:
    assert check_voice("de_DE-thorsten-medium", tmp_path).level is Level.INFO
    (tmp_path / "de_DE-thorsten-medium.onnx").write_bytes(b"x")
    assert check_voice("de_DE-thorsten-medium", tmp_path).level is Level.OK


def test_claude_states() -> None:
    def status(data: object) -> object:
        return lambda _bin: json.dumps(data)

    assert check_claude(which=lambda _p: None).level is Level.FEHLER
    ok = check_claude(which=lambda p: p, auth_status=status({"loggedIn": True}))  # type: ignore[arg-type]
    assert ok.level is Level.OK
    out = check_claude(which=lambda p: p, auth_status=status({"loggedIn": False}))  # type: ignore[arg-type]
    assert out.level is Level.FEHLER and "auth login" in out.fix
    garbage = check_claude(which=lambda p: p, auth_status=lambda _b: "kein json")
    assert garbage.level is Level.WARNUNG


def test_claude_with_fake_cli_end_to_end() -> None:
    # Die Fake-CLI liefert kein "loggedIn" -> nicht angemeldet; wichtig ist: der echte Aufruf klappt.
    assert check_claude(str(FAKE_CLAUDE)).level is Level.FEHLER


def test_project(tmp_path: Path) -> None:
    file = tmp_path / "e.toml"
    assert check_project(file).level is Level.WARNUNG  # wird beim Start abgefragt
    file.write_text(
        f'[claude]\nprojektordner = "{tmp_path.as_posix()}"\nclaude_programm = "{FAKE_CLAUDE.as_posix()}"\n',
        encoding="utf-8",
    )
    assert check_project(file).level is Level.OK
    file.write_text('[claude]\nprojektordner = "/gibt/es/nicht"\n', encoding="utf-8")
    assert check_project(file).level is Level.FEHLER


def test_robot_ports() -> None:
    assert levels(check_robot("r", lambda _h, _p: True)) == [
        ("Reachy erreichbar", Level.OK),
        ("Reachy Ton/Video", Level.OK),
    ]
    nothing = check_robot("r", lambda _h, _p: False)
    assert levels(nothing) == [("Reachy erreichbar", Level.FEHLER)] and "-Robot" in nothing[0].fix
    no_media = check_robot("r", lambda _h, port: port == 8000)
    assert no_media[1].level is Level.FEHLER and "8443" in no_media[1].message


def levels(checks: list[Check]) -> list[tuple[str, Level]]:
    return [(c.name, c.level) for c in checks]


def test_robot_software_known_issues() -> None:
    old = check_robot_software("r", lambda _h: {"version": "1.8.1"}, lambda: "1.8.1")
    assert ("Reachy-Sicherheit", Level.WARNUNG) in levels(old)  # Upload-Luecke offen
    assert any("CVE-2026-55419" in c.message for c in old)

    current = check_robot_software("r", lambda _h: {"version": "1.11.0"}, lambda: "1.11.0")
    assert all(c.level in (Level.OK, Level.INFO) for c in current)  # nur Bluetooth-Hinweise
    assert not any("CVE-2026-55419" in c.message for c in current)
    assert any("GHSA-993g" in c.message for c in current)

    fixed = check_robot_software("r", lambda _h: {"version": "1.12.0"}, lambda: "1.12.0")
    assert not any("GHSA-993g" in c.message for c in fixed)
    assert any("CVE-2026-62661" in c.message for c in fixed)  # noch ohne Fix


def test_robot_software_version_mismatch_and_errors() -> None:
    mismatch = check_robot_software("r", lambda _h: {"version": "1.12.1"}, lambda: "1.11.0")
    assert ("Reachy-Version", Level.WARNUNG) in levels(mismatch)

    def offline(_h: str) -> dict[str, object]:
        raise TimeoutError

    assert levels(check_robot_software("r", offline)) == [("Reachy-Version", Level.WARNUNG)]
    assert levels(check_robot_software("r", lambda _h: {})) == [("Reachy-Version", Level.WARNUNG)]


def test_robot_software_against_local_http_server() -> None:
    """Echter HTTP-Abruf wie bei Reachy (lokaler Server statt Roboter)."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = json.dumps({"type": "daemon_status", "version": "1.11.0"}).encode()
            ok = self.path == "/api/daemon/status"
            self.send_response(200 if ok else 404)
            self.end_headers()
            self.wfile.write(body if ok else b"")

        def log_message(self, *_args: object) -> None: ...

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        original = doctor.DAEMON_PORT
        doctor.DAEMON_PORT = server.server_address[1]
        checks = check_robot_software("127.0.0.1", sdk_version=lambda: "1.11.0")
    finally:
        doctor.DAEMON_PORT = original
        server.shutdown()
    assert checks[0] == Check("Reachy-Version", Level.OK, "1.11.0")


def test_report_and_errors() -> None:
    checks = [
        Check("A", Level.OK, "gut", "nie zeigen"),
        Check("B", Level.INFO, "nur info"),
        Check("C", Level.WARNUNG, "hmm", "so beheben"),
    ]
    lines: list[str] = []
    report(checks, lines.append, problems_only=True)
    assert lines == ["[WARN] C: hmm", "       -> so beheben"]
    lines.clear()
    report(checks, lines.append)
    assert lines[0] == "[ OK ] A: gut" and "nie zeigen" not in "".join(lines)
    assert not has_errors(checks) and has_errors([*checks, Check("D", Level.FEHLER, "x")])


def test_run_checks_asks_version_when_only_media_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(doctor, "check_robot", lambda h: check_robot(h, lambda _h, port: port == 8000))
    monkeypatch.setattr(
        doctor, "check_robot_software", lambda _h: [Check("Reachy-Version", Level.OK, "1.11.0")]
    )
    checks = doctor.run_checks(
        host="r",
        voice="de_DE-thorsten-medium",
        settings_file=tmp_path / "e.toml",
        with_claude=False,
        with_gpu=False,
    )
    assert [c.name for c in checks][-3:] == ["Reachy erreichbar", "Reachy Ton/Video", "Reachy-Version"]


def test_run_checks_skips_software_when_robot_unreachable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(doctor, "check_robot", lambda h: check_robot(h, lambda _h, _p: False))
    monkeypatch.setattr(doctor, "check_claude", lambda _program: Check("Claude Code", Level.OK, "ok"))
    monkeypatch.setattr(doctor, "check_robot_software", lambda _h: pytest.fail("nicht aufrufen"))
    checks = doctor.run_checks(host="r", voice="de_DE-thorsten-medium", settings_file=tmp_path / "e.toml")
    names = [c.name for c in checks]
    assert names == [
        "Python-Pakete",
        "Grafikkarte",
        "Stimme",
        "Speicherort",
        "Claude Code",
        "Projektordner",
        "Reachy erreichbar",
    ]
    assert has_errors(checks)


def test_claude_check_uses_the_configured_program(tmp_path: Path) -> None:
    file = tmp_path / "e.toml"
    file.write_text(f'[claude]\nclaude_programm = "{FAKE_CLAUDE.as_posix()}"\n', encoding="utf-8")
    seen: list[str] = []
    check_claude(
        doctor.claude_program(file), which=lambda p: seen.append(p) or p, auth_status=lambda _b: "{}"
    )
    assert seen == [FAKE_CLAUDE.as_posix()]
    bad = check_claude("C:/boese/start.cmd")
    assert bad.level is Level.FEHLER and "nicht erlaubt" in bad.message


def test_onedrive_location_is_warned(tmp_path: Path) -> None:
    from reachy_claude.doctor import check_location

    assert check_location(tmp_path / "reachy-claude", tmp_path / "code").level is Level.OK
    assert check_location(Path("/home/anna/onedrive-notizen-alt") / "x", None).level is Level.WARNUNG
    assert check_location(Path("/home/anna/code-onedrive") / "x", None).level is Level.OK
    warn = check_location(Path("/Users/anna/OneDrive - Firma/reachy-claude"), None)
    assert warn.level is Level.WARNUNG and "Cloud" in warn.fix


def test_patch_level_difference_is_fine() -> None:
    checks = check_robot_software("r", lambda _h: {"version": "1.11.3"}, lambda: "1.11.0")
    assert not any(c.name == "Reachy-Version" and c.level is Level.WARNUNG for c in checks)


@pytest.mark.parametrize(
    "failure",
    [
        __import__("subprocess").TimeoutExpired("claude", 30),
        OSError("geht nicht"),
    ],
)
def test_claude_auth_check_failures_are_warnings(failure: Exception) -> None:
    def status(_bin: str) -> str:
        raise failure

    assert check_claude(which=lambda p: p, auth_status=status).level is Level.WARNUNG
    assert check_claude(which=lambda p: p, auth_status=lambda _b: "[]").level is Level.WARNUNG
