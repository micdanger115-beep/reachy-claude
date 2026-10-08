import time

from claude_bridge.signing import (
    HEADER_NONCE,
    HEADER_SIGNATURE,
    HEADER_TIMESTAMP,
    ReplayGuard,
    new_nonce,
    sign_request,
    sign_response,
    verify_request,
)

TOKEN = "k" * 40


def signed_headers(
    body: bytes, ts: int | None = None, nonce: str | None = None, token: str = TOKEN
) -> dict[str, str]:
    ts = int(time.time()) if ts is None else ts
    nonce = nonce or new_nonce()
    return {
        HEADER_TIMESTAMP: str(ts),
        HEADER_NONCE: nonce,
        HEADER_SIGNATURE: sign_request(token, "POST", "/v1/ask", ts, nonce, body),
    }


def test_valid_request_is_accepted() -> None:
    body = b'{"prompt":"hi"}'
    headers = signed_headers(body)
    assert verify_request(TOKEN, "POST", "/v1/ask", headers, body, ReplayGuard()) == headers[HEADER_NONCE]


def test_tampered_body_wrong_token_and_path_are_rejected() -> None:
    body = b'{"prompt":"hi"}'
    assert verify_request(TOKEN, "POST", "/v1/ask", signed_headers(body), b"{}", ReplayGuard()) is None
    assert (
        verify_request(TOKEN, "POST", "/v1/ask", signed_headers(body, token="x" * 40), body, ReplayGuard())
        is None
    )
    assert verify_request(TOKEN, "POST", "/v1/reset", signed_headers(body), body, ReplayGuard()) is None


def test_old_timestamp_is_rejected() -> None:
    body = b"{}"
    headers = signed_headers(body, ts=int(time.time()) - 600)
    assert verify_request(TOKEN, "POST", "/v1/ask", headers, body, ReplayGuard()) is None


def test_replay_is_rejected() -> None:
    body = b"{}"
    headers = signed_headers(body)
    guard = ReplayGuard()
    assert verify_request(TOKEN, "POST", "/v1/ask", headers, body, guard) is not None
    assert verify_request(TOKEN, "POST", "/v1/ask", headers, body, guard) is None


def test_malformed_headers_are_rejected() -> None:
    body = b"{}"
    for broken in (
        {},
        signed_headers(body, nonce="zz" * 16),
        {**signed_headers(body), HEADER_TIMESTAMP: "abc"},
    ):
        assert verify_request(TOKEN, "POST", "/v1/ask", broken, body, ReplayGuard()) is None


def test_invalid_signature_does_not_consume_nonce() -> None:
    body = b"{}"
    guard = ReplayGuard()
    good = signed_headers(body)
    forged = {**good, HEADER_SIGNATURE: "0" * 64}
    assert verify_request(TOKEN, "POST", "/v1/ask", forged, body, guard) is None
    assert verify_request(TOKEN, "POST", "/v1/ask", good, body, guard) is not None


def test_replay_guard_forgets_old_nonces() -> None:
    guard = ReplayGuard(window_s=1)
    assert guard.check_and_remember("a", now=0)
    assert not guard.check_and_remember("a", now=1)
    assert guard.check_and_remember("a", now=10)


def test_response_signature_binds_nonce_status_and_body() -> None:
    sig = sign_response(TOKEN, "n1", 200, b"x")
    assert sig == sign_response(TOKEN, "n1", 200, b"x")
    assert sig != sign_response(TOKEN, "n2", 200, b"x")
    assert sig != sign_response(TOKEN, "n1", 500, b"x")
    assert sig != sign_response(TOKEN, "n1", 200, b"y")
