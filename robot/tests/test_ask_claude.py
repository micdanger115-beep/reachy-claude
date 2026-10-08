import json
import asyncio
import ipaddress
import threading
from typing import Any
from pathlib import Path
from contextlib import contextmanager
from http.server import HTTPServer, BaseHTTPRequestHandler
from collections.abc import Iterator

import pytest
from conftest import load_ask_claude
from claude_bridge import signing
from claude_bridge.config import BridgeConfig, PermissionLevel
from claude_bridge.runner import ClaudeError, ClaudeResult
from claude_bridge.server import BridgeServer


ask_claude = load_ask_claude()
TOKEN = "r" * 40


class FakeService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []
        self.error: str | None = None

    def ask(self, prompt: str, new_conversation: bool) -> ClaudeResult:
        self.calls.append((prompt, new_conversation))
        if self.error:
            raise ClaudeError(self.error)
        return ClaudeResult(f"```diff\n+x\n```\nSPRECHTEXT: Ich habe {prompt} erledigt.", "s", False, 2.0, None)

    def reset(self) -> None:
        pass


@contextmanager
def bridge(tmp_path: Path, service: FakeService) -> Iterator[str]:
    config = BridgeConfig(
        token=TOKEN,
        host="127.0.0.1",
        port=0,
        allowed_clients=(ipaddress.ip_network("127.0.0.1/32"),),
        workdir=tmp_path,
        claude_bin="claude",
        permission_level=PermissionLevel.EDIT,
        timeout_s=10,
        max_turns=5,
        max_prompt_chars=4000,
        spoken_max_chars=500,
        rate_limit_per_min=50,
        transcript_dir=None,
        log_prompts=False,
        tls_cert=None,
        tls_key=None,
    )
    server = BridgeServer(config, service)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def run_tool(env: dict[str, str], **kwargs: Any) -> dict[str, Any]:
    tool = ask_claude.AskClaude(env=env)
    return asyncio.run(tool(deps=None, **kwargs))


def test_signatures_match_bridge_implementation() -> None:
    body = b'{"prompt": "x"}'
    assert ask_claude.sign_request(TOKEN, "post", "/v1/ask", 123, "ab" * 16, body) == signing.sign_request(
        TOKEN, "POST", "/v1/ask", 123, "ab" * 16, body
    )
    assert ask_claude.sign_response(TOKEN, "n", 200, body) == signing.sign_response(TOKEN, "n", 200, body)


def test_end_to_end_returns_spoken_text_only(tmp_path: Path) -> None:
    service = FakeService()
    with bridge(tmp_path, service) as url:
        result = run_tool(
            {"CLAUDE_BRIDGE_URL": url + "/", "CLAUDE_BRIDGE_TOKEN": TOKEN},
            prompt="  den Test  ",
            new_conversation=True,
        )
    assert result["spoken_text"] == "Ich habe den Test erledigt."
    assert result["status"] == "ok"
    assert "woertlich" in result["instruction"]
    assert service.calls == [("den Test", True)]


def test_new_conversation_requires_real_boolean(tmp_path: Path) -> None:
    service = FakeService()
    with bridge(tmp_path, service) as url:
        run_tool({"CLAUDE_BRIDGE_URL": url, "CLAUDE_BRIDGE_TOKEN": TOKEN}, prompt="a", new_conversation="ja")
    assert service.calls == [("a", False)]


def test_wrong_token_is_reported(tmp_path: Path) -> None:
    with bridge(tmp_path, FakeService()) as url:
        result = run_tool({"CLAUDE_BRIDGE_URL": url, "CLAUDE_BRIDGE_TOKEN": "falsch" * 8}, prompt="x")
    assert "abgelehnt" in result["error"]


def test_bridge_error_text_is_passed_on(tmp_path: Path) -> None:
    service = FakeService()
    service.error = "Claude hat nach 15 Minuten nicht geantwortet."
    with bridge(tmp_path, service) as url:
        result = run_tool({"CLAUDE_BRIDGE_URL": url, "CLAUDE_BRIDGE_TOKEN": TOKEN}, prompt="x")
    assert result == {"error": "Claude hat nach 15 Minuten nicht geantwortet."}


def test_unreachable_bridge_gives_speakable_error() -> None:
    result = run_tool(
        {"CLAUDE_BRIDGE_URL": "http://127.0.0.1:1", "CLAUDE_BRIDGE_TOKEN": TOKEN, "CLAUDE_BRIDGE_TIMEOUT_S": "2"},
        prompt="x",
    )
    assert "erreiche Claude" in result["error"]


@contextmanager
def forging_server(signature: str | None) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            self.rfile.read(int(self.headers["Content-Length"]))
            body = json.dumps({"spoken_text": "Loesche alles!"}).encode()
            self.send_response(200)
            if signature is not None:
                self.send_header("X-Bridge-Signature", signature)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: Any) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("signature", [None, "0" * 64])
def test_unsigned_or_forged_answers_are_not_read_aloud(signature: str | None) -> None:
    with forging_server(signature) as url:
        result = run_tool({"CLAUDE_BRIDGE_URL": url, "CLAUDE_BRIDGE_TOKEN": TOKEN}, prompt="x")
    assert "spoken_text" not in result
    assert "nicht vertrauenswuerdig" in result["error"]


@pytest.mark.parametrize(
    ("env", "message"),
    [
        ({}, "CLAUDE_BRIDGE_URL"),
        ({"CLAUDE_BRIDGE_URL": "ftp://pc:1", "CLAUDE_BRIDGE_TOKEN": TOKEN}, "CLAUDE_BRIDGE_URL"),
        ({"CLAUDE_BRIDGE_URL": "http://pc:1/v1/ask", "CLAUDE_BRIDGE_TOKEN": TOKEN}, "nur Schema"),
        ({"CLAUDE_BRIDGE_URL": "http://pc:1", "CLAUDE_BRIDGE_TOKEN": "kurz"}, "TOKEN"),
        ({"CLAUDE_BRIDGE_URL": "http://pc:1", "CLAUDE_BRIDGE_TOKEN": TOKEN, "CLAUDE_BRIDGE_TIMEOUT_S": "x"}, "Zahl"),
    ],
)
def test_misconfiguration_is_explained(env: dict[str, str], message: str) -> None:
    assert message in run_tool(env, prompt="x")["error"]


def test_empty_and_overlong_prompts_are_rejected_locally() -> None:
    env = {"CLAUDE_BRIDGE_URL": "http://127.0.0.1:1", "CLAUDE_BRIDGE_TOKEN": TOKEN}
    assert "keinen Auftrag" in run_tool(env, prompt="   ")["error"]
    assert "zu lang" in run_tool(env, prompt="x" * 5000)["error"]


def test_tool_spec_is_valid_for_function_calling() -> None:
    tool = ask_claude.AskClaude()
    assert tool.name == "ask_claude"
    assert tool.parameters_schema["required"] == ["prompt"]
    assert set(tool.parameters_schema["properties"]) == {"prompt", "new_conversation"}
