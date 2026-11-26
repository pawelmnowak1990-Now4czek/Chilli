"""Reading the token from `Authorization: Bearer <token>`, as forgiving as HTTP allows."""

import pytest

from app.bearer import bearer_token


@pytest.mark.parametrize(
    "header",
    ["Bearer abc123", "bearer abc123", "BEARER abc123", "Bearer  abc123", "Bearer abc123 ", "Bearer abc123\n", " Bearer abc123"],
)
def test_accepted_spellings(header: str) -> None:
    # The scheme is case-insensitive (RFC 9110); spaces and a pasted line break around the token are ignored.
    assert bearer_token(header) == "abc123"


@pytest.mark.parametrize("header", [None, "", "Bearer", "Bearer ", "Basic abc123", "abc123", "Bearerabc123", "Bearer abc 123"])
def test_rejected(header: str | None) -> None:
    assert bearer_token(header) is None


def test_capture_accepts_lowercase_scheme_and_trailing_space(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.config import settings

    # No real processing in the background (no network, no model): only the acceptance matters here.
    monkeypatch.setattr("app.processing.process_save", lambda save_id: None)

    response = client.post(
        "/capture", json={"url": "https://example.com/a"},
        headers={"Authorization": f"bearer {settings.capture_token} "},
    )
    assert response.status_code == 202, response.text


@pytest.mark.parametrize(
    ("header", "ok"),
    [("Bearer s3cret", True), ("bearer s3cret", True), ("Bearer s3cret\n", True), ("Bearer wrong", False), ("Basic s3cret", False)],
)
def test_mcp_secret_check(header: str, ok: bool) -> None:
    from app.mcp_auth import _has_valid_secret

    scope = {"headers": [(b"authorization", header.encode("latin-1"))]}
    assert _has_valid_secret(scope, "s3cret") is ok
