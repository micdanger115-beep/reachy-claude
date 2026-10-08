import http.client
import ipaddress
import json
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from conftest import TOKEN

from claude_bridge.config import BridgeConfig
from claude_bridge.runner import ClaudeError, ClaudeResult
from claude_bridge.server import MAX_BODY_BYTES, BridgeServer, RateLimiter
from claude_bridge.signing import (
    HEADER_NONCE,
    HEADER_RESPONSE_SIGNATURE,
    HEADER_SIGNATURE,
    HEADER_TIMESTAMP,
    new_nonce,
    sign_request,
    sign_response,
)

ConfigFactory = Callable[..., BridgeConfig]


class FakeService:
    def __init__(self) -> None:
        self.prompts: list[tuple[str, bool]] = []
        self.resets = 0
        self.gate: threading.Event | None = None
        self.started = threading.Event()
        self.error: str | None = None

    def ask(self, prompt: str, new_conversation: bool) -> ClaudeResult:
        self.prompts.append((prompt, new_conversation))
        self.started.set()
        if self.gate is not None:
            self.gate.wait(5)
        if self.error:
            raise ClaudeError(self.error)
        return ClaudeResult(f"Code ```x```\nSPRECHTEXT: Fertig mit {prompt}.", "s1", False, 1.23, None)

    def reset(self) -> None:
        self.resets += 1


@contextmanager
def running(config: BridgeConfig, service: FakeService) -> Iterator[int]:
    server = BridgeServer(config, service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


def call(
    port: int,
    method: str,
    path: str,
    payload: object | None = None,
    *,
    token: str = TOKEN,
    nonce: str | None = None,
    raw_body: bytes | None = None,
    sign: bool = True,
) -> tuple[int, dict[str, object], str | None, bytes, str]:
    body = (
        raw_body if raw_body is not None else (json.dumps(payload).encode() if payload is not None else b"")
    )
    nonce = nonce or new_nonce()
    ts = int(time.time())
    headers = {"Content-Type": "application/json"}
    if sign:
        headers.update(
            {
                HEADER_TIMESTAMP: str(ts),
                HEADER_NONCE: nonce,
                HEADER_SIGNATURE: sign_request(token, method, path, ts, nonce, body),
            }
        )
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(method, path, body=body, headers=headers)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, json.loads(data), resp.getheader(HEADER_RESPONSE_SIGNATURE), data, nonce


def test_ask_returns_signed_spoken_text(make_config: ConfigFactory) -> None:
    service = FakeService()
    with running(make_config(), service) as port:
        status, payload, sig, raw, nonce = call(
            port, "POST", "/v1/ask", {"prompt": " Tests schreiben ", "new_conversation": True}
        )
    assert status == 200
    assert payload["spoken_text"] == "Fertig mit Tests schreiben."
    assert "Code" not in str(payload)  # Rohausgabe bleibt auf dem PC
    assert sig == sign_response(TOKEN, nonce, 200, raw)
    assert service.prompts == [("Tests schreiben", True)]


def test_health_and_reset(make_config: ConfigFactory) -> None:
    service = FakeService()
    with running(make_config(), service) as port:
        assert call(port, "GET", "/v1/health")[:2] == (200, {"status": "ok", "busy": False})
        assert call(port, "POST", "/v1/reset", {})[0] == 200
    assert service.resets == 1


def test_unsigned_wrong_token_and_replay_are_rejected(make_config: ConfigFactory) -> None:
    service = FakeService()
    with running(make_config(), service) as port:
        assert call(port, "POST", "/v1/ask", {"prompt": "x"}, sign=False)[0] == 401
        assert call(port, "POST", "/v1/ask", {"prompt": "x"}, token="falsch" * 8)[0] == 401
        nonce = new_nonce()
        assert call(port, "POST", "/v1/ask", {"prompt": "x"}, nonce=nonce)[0] == 200
        status, _, sig, _, _ = call(port, "POST", "/v1/ask", {"prompt": "x"}, nonce=nonce)
    assert status == 401
    assert sig is None
    assert len(service.prompts) == 1


def test_disallowed_ip_is_rejected_before_anything_else(make_config: ConfigFactory) -> None:
    service = FakeService()
    cfg = make_config(allowed_clients=(ipaddress.ip_network("10.9.9.9/32"),))
    with running(cfg, service) as port:
        assert call(port, "POST", "/v1/ask", {"prompt": "x"})[0] == 403
    assert service.prompts == []


def test_input_validation(make_config: ConfigFactory) -> None:
    with running(make_config(max_prompt_chars=20), FakeService()) as port:
        assert call(port, "POST", "/v1/ask", {"prompt": "   "})[0] == 400
        assert call(port, "POST", "/v1/ask", {"prompt": "x" * 21})[0] == 400
        assert call(port, "POST", "/v1/ask", raw_body=b"{kaputt")[0] == 400
        assert call(port, "POST", "/v1/ask", ["liste"])[0] == 400
        assert call(port, "POST", "/v1/ask", raw_body=b"x" * (MAX_BODY_BYTES + 1))[0] == 413
        assert call(port, "POST", "/v1/unbekannt", {})[0] == 404


def test_only_one_job_at_a_time(make_config: ConfigFactory) -> None:
    service = FakeService()
    service.gate = threading.Event()
    with running(make_config(), service) as port:
        first: list[int] = []
        worker = threading.Thread(
            target=lambda: first.append(call(port, "POST", "/v1/ask", {"prompt": "a"})[0])
        )
        worker.start()
        assert service.started.wait(5)
        status, payload, *_ = call(port, "POST", "/v1/ask", {"prompt": "b"})
        service.gate.set()
        worker.join(5)
    assert status == 409
    assert "vorigen" in str(payload["error"])
    assert first == [200]


def test_claude_error_is_reported_as_speakable_text(make_config: ConfigFactory) -> None:
    service = FakeService()
    service.error = "Claude hat nicht geantwortet."
    with running(make_config(), service) as port:
        status, payload, *_ = call(port, "POST", "/v1/ask", {"prompt": "x"})
    assert status == 502
    assert payload == {"error": "Claude hat nicht geantwortet."}


def test_rate_limit(make_config: ConfigFactory) -> None:
    with running(make_config(rate_limit_per_min=2), FakeService()) as port:
        codes = [call(port, "GET", "/v1/health")[0] for _ in range(3)]
    assert codes == [200, 200, 429]


def test_rate_limiter_window_slides() -> None:
    now = [0.0]
    limiter = RateLimiter(1, clock=lambda: now[0])
    assert limiter.allow()
    assert not limiter.allow()
    now[0] = 61
    assert limiter.allow()


def test_transcript_written_when_enabled(make_config: ConfigFactory, tmp_path: Path) -> None:
    with running(make_config(transcript_dir=tmp_path / "t"), FakeService()) as port:
        call(port, "POST", "/v1/ask", {"prompt": "Hallo"})
    files = list((tmp_path / "t").glob("*.md"))
    assert len(files) == 1
    assert "Hallo" in files[0].read_text(encoding="utf-8")


def test_transcript_failure_does_not_block_answer(make_config: ConfigFactory, tmp_path: Path) -> None:
    blocker = tmp_path / "datei"
    blocker.write_text("x", encoding="utf-8")
    with running(make_config(transcript_dir=blocker / "sub"), FakeService()) as port:
        status, payload, *_ = call(port, "POST", "/v1/ask", {"prompt": "Hallo"})
    assert status == 200
    assert payload["spoken_text"] == "Fertig mit Hallo."
