import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from websockets.asyncio.server import ServerConnection, serve

from claude_bridge.__main__ import main
from claude_bridge.listen import (
    Status,
    Transcript,
    TurnState,
    build_url,
    clean_text,
    format_event,
    listen,
    parse_message,
)


def note(method: str, **params: Any) -> str:
    return json.dumps({"jsonrpc": "2.0", "method": method, "params": params})


STATUS_OK = json.dumps(
    {"jsonrpc": "2.0", "id": 1, "result": {"backend_connected": True, "hf_connection_mode": "deployed"}}
)


# ---------------------------------------------------------------- reine Funktionen
def test_parse_transcripts_turns_and_status() -> None:
    assert parse_message(
        note("conversation.transcript", role="user", text="Hallo", final=True)
    ) == Transcript("user", "Hallo")
    assert parse_message(note("conversation.transcript", role="assistant", text="Hi!")) == Transcript(
        "assistant", "Hi!"
    )
    assert parse_message(note("conversation.turn", state="listening")) == TurnState("listening")
    assert parse_message(STATUS_OK) == Status(True, "deployed", None)


@pytest.mark.parametrize(
    "raw",
    [
        "kein json",
        "[1, 2]",
        note("conversation.transcript", role="hacker", text="x"),
        note("conversation.transcript", role="user", text="   "),
        note("conversation.transcript", role="user", text="halb", final=False),
        note("conversation.transcript", role="user", text=42),
        note("conversation.turn", state="tanzen"),
        note("conversation.level", role="user", rms=0.3),
        json.dumps({"jsonrpc": "2.0", "id": 7, "result": {"backend_connected": True}}),
        json.dumps({"method": "conversation.transcript", "params": "kaputt"}),
    ],
)
def test_unknown_or_malformed_messages_are_ignored(raw: str) -> None:
    assert parse_message(raw) is None


def test_control_characters_cannot_reach_the_terminal() -> None:
    evil = "Hallo\x1b[2J\x1b]0;gehackt\x07 Welt\r\nneu\x9b"
    assert clean_text(evil) == "Hallo [2J ]0;gehackt Welt neu"
    event = parse_message(note("conversation.transcript", role="assistant", text=evil))
    assert isinstance(event, Transcript)
    assert "\x1b" not in format_event(event)


def test_format_lines() -> None:
    assert format_event(Transcript("user", "Hallo"), now=0).endswith("Du:     Hallo")
    assert format_event(Transcript("assistant", "Hi"), now=0).endswith("Reachy: Hi")
    assert "hoert zu" in format_event(TurnState("listening"), now=0)
    assert "Hugging-Face-Cloud" in format_event(Status(True, "deployed", None), now=0)
    assert "nicht verbunden: kein Netz" in format_event(Status(False, None, "kein Netz"), now=0)


def test_build_url() -> None:
    assert build_url("reachy-mini.local") == "ws://reachy-mini.local:7860/rpc"
    assert build_url("192.168.1.30", 9000) == "ws://192.168.1.30:9000/rpc"
    assert build_url("fe80::1") == "ws://[fe80::1]:7860/rpc"
    assert build_url("ws://127.0.0.1:7860/rpc") == "ws://127.0.0.1:7860/rpc"
    for bad in ("http://x/rpc", "", "a/b", "user@host"):
        with pytest.raises(ValueError):
            build_url(bad)


# ------------------------------------------------------- mit nachgebautem Reachy
Handler = Callable[[ServerConnection], Awaitable[None]]


async def run_against(handler: Handler, stop_after: Callable[[list[str]], bool], **kwargs: Any) -> list[str]:
    lines: list[str] = []
    stop = asyncio.Event()

    def output(line: str) -> None:
        lines.append(line)
        if stop_after(lines):
            stop.set()

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        await asyncio.wait_for(
            listen(f"ws://127.0.0.1:{port}/rpc", output, stop=stop, retry_start_s=0.05, **kwargs), timeout=10
        )
    return lines


def fake_reachy(*messages: str) -> Handler:
    async def handler(ws: ServerConnection) -> None:
        request = json.loads(await ws.recv())
        assert request["method"] == "conversation.status"
        await ws.send(STATUS_OK)
        for message in messages:
            await ws.send(message)
        await ws.wait_closed()

    return handler


def test_shows_conversation_and_saves_transcript(tmp_path: Path) -> None:
    save = tmp_path / "log" / "gespraech.md"
    handler = fake_reachy(
        note("conversation.turn", state="listening"),
        note("conversation.transcript", role="user", text="Wie geht es dir?", final=True),
        note("conversation.transcript", role="assistant", text="Mir geht es gut!", final=True),
    )
    lines = asyncio.run(run_against(handler, lambda ls: "Mir geht es gut!" in ls[-1], transcript_file=save))
    assert lines[0].startswith("Verbunden mit ws://127.0.0.1:")
    assert "Sprachdienst verbunden (Hugging-Face-Cloud)" in lines[1]
    assert lines[2].endswith("Du:     Wie geht es dir?")
    assert lines[3].endswith("Reachy: Mir geht es gut!")
    assert not any("hoert zu" in line for line in lines)  # Zustaende nur mit show_turns
    saved = save.read_text(encoding="utf-8")
    assert "**Du:** Wie geht es dir?" in saved and "**Reachy:** Mir geht es gut!" in saved


def test_show_turns() -> None:
    handler = fake_reachy(note("conversation.turn", state="speaking"))
    lines = asyncio.run(run_against(handler, lambda ls: "spricht" in ls[-1], show_turns=True))
    assert "spricht" in lines[-1]


def test_reconnects_after_reachy_restarts() -> None:
    connections = 0

    async def handler(ws: ServerConnection) -> None:
        nonlocal connections
        connections += 1
        await ws.recv()
        await ws.send(STATUS_OK)
        await ws.send(note("conversation.transcript", role="user", text=f"Verbindung {connections}"))
        if connections == 1:
            await ws.close()  # App startet neu
        else:
            await ws.wait_closed()

    lines = asyncio.run(run_against(handler, lambda ls: "Verbindung 2" in ls[-1]))
    assert any("Verbindung zu Reachy beendet" in line for line in lines)
    assert connections == 2


def test_unreachable_robot_retries_and_reports() -> None:
    lines: list[str] = []
    stop = asyncio.Event()

    def output(line: str) -> None:
        lines.append(line)
        if len(lines) >= 2:
            stop.set()

    asyncio.run(
        asyncio.wait_for(listen("ws://127.0.0.1:1/rpc", output, stop=stop, retry_start_s=0.05), timeout=10)
    )
    assert all("nicht erreichbar" in line for line in lines)


def test_cli_rejects_bad_robot_name(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["listen", "--robot", "http://falsch"]) == 2
