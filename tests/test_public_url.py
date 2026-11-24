"""The public server address (PUBLIC_URL) and what is derived from it."""

from app import fetch
from app.public_url import LOCAL_HOSTS, mcp_allowed_hosts, mcp_allowed_origins


def test_hosts_and_origins_from_public_url() -> None:
    url = "https://chilli.example.com"
    assert mcp_allowed_hosts(url) == ["chilli.example.com", *LOCAL_HOSTS]
    assert mcp_allowed_origins(url) == ["https://chilli.example.com", "https://claude.ai"]


def test_trailing_slash_path_and_port_are_handled() -> None:
    url = "https://chilli.example.com:8443/some/path/"
    assert mcp_allowed_hosts(url)[0] == "chilli.example.com:8443"
    assert mcp_allowed_origins(url)[0] == "https://chilli.example.com:8443"


def test_empty_public_url_keeps_local_entries_only() -> None:
    assert mcp_allowed_hosts("") == LOCAL_HOSTS
    assert mcp_allowed_hosts("   ") == LOCAL_HOSTS
    assert mcp_allowed_origins("") == ["https://claude.ai"]


def test_local_hosts_cover_tests_and_localhost() -> None:
    assert "testserver" in LOCAL_HOSTS
    assert "localhost:*" in LOCAL_HOSTS
    assert "127.0.0.1:*" in LOCAL_HOSTS


def test_user_agent_without_public_url_has_no_link() -> None:
    assert fetch.user_agent("") == f"Mozilla/5.0 (compatible; Chilli/{fetch.VERSION})"


def test_user_agent_with_public_url_points_to_it() -> None:
    assert fetch.user_agent("https://chilli.example.com/") == (
        f"Mozilla/5.0 (compatible; Chilli/{fetch.VERSION}; +https://chilli.example.com)"
    )


def test_module_user_agent_comes_from_settings() -> None:
    from app.config import settings

    assert fetch.USER_AGENT == fetch.user_agent(settings.public_url)


def test_build_app_warns_without_public_url(monkeypatch, caplog) -> None:
    import logging

    from app import mcp_server
    from app.config import settings

    monkeypatch.setattr(settings, "public_url", "")
    with caplog.at_level(logging.WARNING, logger="app.mcp_server"):
        mcp_server.build_app()
    assert "PUBLIC_URL is not set" in caplog.text


def test_build_app_silent_with_public_url(monkeypatch, caplog) -> None:
    import logging

    from app import mcp_server
    from app.config import settings

    monkeypatch.setattr(settings, "public_url", "https://chilli.example.com")
    with caplog.at_level(logging.WARNING, logger="app.mcp_server"):
        mcp_server.build_app()
    assert "PUBLIC_URL" not in caplog.text


def test_public_url_without_scheme_has_no_host() -> None:
    assert mcp_allowed_hosts("chilli.example.com") == LOCAL_HOSTS


def test_build_app_warns_on_public_url_without_scheme(monkeypatch, caplog) -> None:
    import logging

    from app import mcp_server
    from app.config import settings

    monkeypatch.setattr(settings, "public_url", "chilli.example.com")
    with caplog.at_level(logging.WARNING, logger="app.mcp_server"):
        mcp_server.build_app()
    assert "must start with https://" in caplog.text
