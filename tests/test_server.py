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
