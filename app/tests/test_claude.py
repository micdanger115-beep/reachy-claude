import json
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from reachy_claude.claude import (
    SYSTEM_PROMPT,
    ClaudeError,
    ClaudeResult,
    ClaudeRunner,
    build_argv,
    parse_cli_output,
    write_transcript,
)
from reachy_claude.settings import ClaudeSettings, Permission

ConfigFactory = Callable[..., ClaudeSettings]


def read_log(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_edit_level_allows_edits_but_never_shell_or_web(make_config: ConfigFactory) -> None:
    argv = build_argv(make_config(permission=Permission.EDIT), None)
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert "Edit" in argv[argv.index("--allowedTools") + 1].split(",")
    disallowed = argv[argv.index("--disallowedTools") + 1].split(",")
    assert {"Bash", "WebFetch", "WebSearch"} <= set(disallowed)
    assert "--strict-mcp-config" in argv
    assert "--dangerously-skip-permissions" not in argv
    assert {"Edit(.claude/**)", "Edit(.git/**)", "Edit(.vscode/**)"} <= set(disallowed)


@pytest.mark.parametrize(
    ("permission", "tools"),
    [
        (Permission.READ, ["Read", "Grep", "Glob"]),
        (Permission.EDIT, ["Read", "Grep", "Glob", "Edit", "Write"]),
    ],
)
def test_only_file_tools_inside_the_project(
    make_config: ConfigFactory, permission: Permission, tools: list[str]
) -> None:
    # --restricted + --tools: nur diese Werkzeuge, nur im Projektordner, keine Einstellungsdateien/Hooks
    # (mit der echten CLI geprueft: ohne das konnte Claude per ../ ueberall lesen und schreiben).
    argv = build_argv(make_config(permission=permission), None)
    assert "--restricted" in argv
    assert argv[argv.index("--tools") + 1].split(",") == tools
    assert argv[argv.index("--allowedTools") + 1].split(",") == tools
    disallowed = set(argv[argv.index("--disallowedTools") + 1].split(","))
    assert {"Bash", "PowerShell", "WebFetch", "WebSearch", "Agent", "Skill"} <= disallowed
    assert "--setting-sources" not in argv  # --restricted ignoriert ohnehin alle Einstellungsdateien


def test_files_run_or_read_by_other_programs_are_protected(make_config: ConfigFactory) -> None:
    argv = build_argv(make_config(permission=Permission.EDIT), None)
    disallowed = set(argv[argv.index("--disallowedTools") + 1].split(","))
    for rule in (
        "Edit(.git/**)",
        "Edit(.github/**)",
        "Edit(.husky/**)",
        "Edit(**/CLAUDE.md)",
        "Edit(.vscode/**)",
    ):
        assert rule in disallowed


def test_read_level_disallows_edits(make_config: ConfigFactory) -> None:
    argv = build_argv(make_config(permission=Permission.READ), None)
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert "Edit" not in argv[argv.index("--allowedTools") + 1].split(",")
    assert {"Edit", "Write", "Bash"} <= set(argv[argv.index("--disallowedTools") + 1].split(","))


def test_session_id_is_validated(make_config: ConfigFactory) -> None:
    cfg = make_config()
    assert build_argv(cfg, "abcdef12-3456")[-2:] == ["--resume", "abcdef12-3456"]
    with pytest.raises(ValueError):
        build_argv(cfg, '" & del *')


def test_system_prompt_is_safe_for_windows_cmd() -> None:
    # Wenn claude eine .cmd-Datei ist, wertet cmd.exe diese Zeichen aus.
    assert not set('"%^&|<>!\n') & set(SYSTEM_PROMPT)


def test_prompt_goes_via_stdin_not_argv(
    make_config: ConfigFactory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    prompt = '"; rm -rf / & echo %PATH% – Größe ändern, Übung'  # Umlaute: muss als UTF-8 ankommen
    result = ClaudeRunner(make_config(workdir=tmp_path)).ask(prompt)
    call = read_log(log)[0]
    assert call["stdin"] == prompt
    assert all(prompt not in arg for arg in call["argv"])  # type: ignore[union-attr]
    # Die Schutzregeln kommen unveraendert an (unter Windows ueber die .cmd-Datei).
    assert call["argv"] == build_argv(make_config(workdir=tmp_path), None)[1:]
    # ohne Telemetrie der CLI (Datensparsamkeit)
    assert call["env"]["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"  # type: ignore[index]
    assert result.session_id == "11111111-2222-3333-4444-555555555555"
    assert "SPRECHTEXT:" in result.text


def test_follow_up_resumes_session_and_new_conversation_resets(
    make_config: ConfigFactory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    runner = ClaudeRunner(make_config())
    runner.ask("eins")
    runner.ask("zwei")
    runner.ask("drei", new_conversation=True)
    argvs = [c["argv"] for c in read_log(log)]
    assert "--resume" not in argvs[0]
    assert "--resume" in argvs[1]
    assert "--resume" not in argvs[2]


def test_failed_resume_retries_with_fresh_session(
    make_config: ConfigFactory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = ClaudeRunner(make_config())
    runner.ask("eins")
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "fail_resume")
    result = runner.ask("zwei")
    assert result.session_id == "99999999-2222-3333-4444-555555555555"
    assert runner.session_id == result.session_id


def test_crash_raises_speakable_error(
    make_config: ConfigFactory, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "crash")
    with pytest.raises(ClaudeError, match="Fehler"):
        ClaudeRunner(make_config()).ask("x")
    assert len(read_log(log)) == 1  # ohne fortgesetzte Sitzung kein zweiter Versuch


def test_timeout_kills_process(make_config: ConfigFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "sleep")
    with pytest.raises(ClaudeError, match="nicht geantwortet"):
        ClaudeRunner(make_config(timeout_s=0.5)).ask("x")


def test_parse_cli_output_handles_noise() -> None:
    assert parse_cli_output('warnung\n{"result": "ok", "session_id": "s"}')["result"] == "ok"
    with pytest.raises(ClaudeError):
        parse_cli_output("kein json")
    with pytest.raises(ClaudeError):
        parse_cli_output('{"anders": 1}')


def test_transcript_is_written_locally(tmp_path: Path) -> None:
    path = write_transcript(tmp_path / "t", "Auftrag", ClaudeResult("Antwort", "s1", False, 1.0, None))
    content = path.read_text(encoding="utf-8")
    assert "Auftrag" in content and "Antwort" in content and "s1" in content


def test_timeout_while_resuming_is_not_retried(
    make_config: ConfigFactory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    runner = ClaudeRunner(make_config(timeout_s=1.0))
    runner.ask("eins")
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "sleep")
    with pytest.raises(ClaudeError, match="nicht geantwortet"):
        runner.ask("zwei")
    assert len(read_log(log)) == 2  # kein zweiter Lauf nach dem Timeout


def test_max_turns_abort_is_reported_not_retried(
    make_config: ConfigFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "max_turns")
    result = ClaudeRunner(make_config()).ask("x")
    assert result.is_error
    assert "maximale Anzahl" in result.text
    assert result.session_id == "abc-123-def"


def test_cancel_kills_running_claude(make_config: ConfigFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    import threading
    import time

    from reachy_claude.claude import CANCELLED_MESSAGE, ClaudeCancelled

    monkeypatch.setenv("FAKE_CLAUDE_MODE", "sleep")
    runner = ClaudeRunner(make_config(timeout_s=60))
    assert runner.cancel() is False  # nichts laeuft
    outcome: list[BaseException] = []

    def work() -> None:
        try:
            runner.ask("lange Aufgabe")
        except BaseException as exc:
            outcome.append(exc)

    worker = threading.Thread(target=work)
    started = time.monotonic()
    worker.start()
    deadline = time.monotonic() + 10
    while not runner.cancel():
        assert time.monotonic() < deadline, "Claude-Prozess startete nicht"
        time.sleep(0.05)
    worker.join(timeout=10)
    assert not worker.is_alive()
    assert time.monotonic() - started < 15  # nicht die 30 s des Fakes abgewartet
    assert len(outcome) == 1 and isinstance(outcome[0], ClaudeCancelled)
    assert str(outcome[0]) == CANCELLED_MESSAGE
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "ok")
    assert "SPRECHTEXT" in runner.ask("danach geht es normal weiter").text


def test_cancel_before_start_never_runs_claude(
    make_config: ConfigFactory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    from reachy_claude.claude import ClaudeCancelled

    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    cancel = threading.Event()
    cancel.set()  # "stopp"/Strg+C kam, bevor Claude gestartet wurde
    with pytest.raises(ClaudeCancelled):
        ClaudeRunner(make_config()).ask("x", cancel_event=cancel)
    assert not log.exists()  # kein Claude-Prozess (der sonst nach Programmende weiterliefe)


@pytest.mark.skipif(
    sys.platform == "win32", reason="unter Windows prueft die CI taskkill /T ueber die .cmd-Kette"
)
def test_cancel_kills_the_whole_process_tree(
    make_config: ConfigFactory, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import os
    import threading
    import time

    child_file = tmp_path / "child.pid"
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "sleep_child")
    monkeypatch.setenv("FAKE_CLAUDE_CHILD", str(child_file))
    runner = ClaudeRunner(make_config(timeout_s=60))
    worker = threading.Thread(target=lambda: pytest.raises(ClaudeError, runner.ask, "x"))
    worker.start()
    deadline = time.monotonic() + 10
    while not child_file.exists():
        assert time.monotonic() < deadline
        time.sleep(0.05)
    child = int(child_file.read_text(encoding="utf-8"))
    assert runner.cancel()
    worker.join(timeout=10)

    def alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        state = Path(f"/proc/{pid}/stat")
        return not (state.exists() and state.read_text().split()[2] == "Z")  # Zombie zaehlt als tot

    deadline = time.monotonic() + 5
    while alive(child) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not alive(child), "Unterprozess von Claude lief nach dem Abbruch weiter"
