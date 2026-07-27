from __future__ import annotations

from unittest.mock import Mock

from ticktick_mcp import server


def test_stdio_transport(monkeypatch):
    run = Mock()
    monkeypatch.setattr(server.mcp, "run", run)

    server.main()

    run.assert_called_once_with(transport="stdio")


def test_http_transport(monkeypatch):
    run = Mock()
    monkeypatch.setattr(server.mcp, "run", run)

    server.main(transport="http", host="0.0.0.0", port=9000)

    run.assert_called_once_with(transport="http", host="0.0.0.0", port=9000)


async def test_lifespan_loads_stored_session_token(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr(
        server,
        "load_credentials",
        lambda: {"access_token": "access-token", "session_token": "session-token"},
    )
    monkeypatch.setattr(server, "TickTickClient", FakeClient)

    async with server.lifespan(server.mcp):
        pass

    assert captured["session_token"] == "session-token"
