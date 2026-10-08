import json
from collections.abc import Callable
from pathlib import Path

import pytest

from claude_bridge.config import BridgeConfig, PermissionLevel
from claude_bridge.runner import (
    SYSTEM_PROMPT,
    ClaudeError,
    ClaudeResult,
    ClaudeRunner,
    build_argv,
    child_environment,
    parse_cli_output,
    write_transcript,
)

ConfigFactory = Callable[..., BridgeConfig]


def read_log(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_edit_level_allows_edits_but_never_shell_or_web(make_config: ConfigFactory) -> None:
    argv = build_argv(make_config(permission_level=PermissionLevel.EDIT), None)
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert "Edit" in argv[argv.index("--allowedTools") + 1].split(",")
    disallowed = argv[argv.index("--disallowedTools") + 1].split(",")
    assert {"Bash", "WebFetch", "WebSearch"} <= set(disallowed)
    assert "--strict-mcp-config" in argv
    assert "--dangerously-skip-permissions" not in argv


def test_read_level_disallows_edits(make_config: ConfigFactory) -> None:
    argv = build_argv(make_config(permission_level=PermissionLevel.READ), None)
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


def test_child_environment_drops_bridge_secrets() -> None:
    env = child_environment({"PATH": "/bin", "CLAUDE_BRIDGE_TOKEN": "geheim", "HOME": "/h"})
    assert env == {"PATH": "/bin", "HOME": "/h"}


def test_prompt_goes_via_stdin_not_argv(
    make_config: ConfigFactory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.setenv("CLAUDE_BRIDGE_TOKEN", "geheim-geheim")
    prompt = '"; rm -rf / & echo %PATH%'
    result = ClaudeRunner(make_config(workdir=tmp_path)).ask(prompt)
    call = read_log(log)[0]
    assert call["stdin"] == prompt
    assert all(prompt not in arg for arg in call["argv"])  # type: ignore[union-attr]
    assert "CLAUDE_BRIDGE_TOKEN" not in call["env"]  # type: ignore[operator]
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


def test_crash_raises_speakable_error(make_config: ConfigFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "crash")
    with pytest.raises(ClaudeError, match="Fehler"):
        ClaudeRunner(make_config()).ask("x")


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
