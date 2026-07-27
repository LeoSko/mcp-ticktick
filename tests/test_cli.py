from __future__ import annotations

import io
from pathlib import Path

import httpx
import pytest
import respx

from ticktick_mcp import cli
from ticktick_mcp.auth import TOKEN_URL, load_credentials, save_credentials
from ticktick_mcp.cli import build_parser


def test_serve_defaults_to_streamable_http():
    args = build_parser().parse_args(["serve"])

    assert args.command == "serve"
    assert args.transport == "http"
    assert args.host == "127.0.0.1"
    assert args.port == 8000


def test_serve_accepts_sse_network_options():
    args = build_parser().parse_args(
        ["serve", "--transport", "sse", "--host", "0.0.0.0", "--port", "9000"]
    )

    assert args.transport == "sse"
    assert args.host == "0.0.0.0"
    assert args.port == 9000


def test_session_command_stores_cookie_from_stdin(monkeypatch, tmp_path: Path, capsys):
    credentials_path = tmp_path / "credentials.json"
    args = build_parser().parse_args(
        ["session", "--stdin", "--credentials-file", str(credentials_path)]
    )
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("x=1; t=token"))

    cli.store_session(args)

    assert load_credentials(credentials_path)["session_token"] == "token"
    output = capsys.readouterr().out
    assert "mcp-ticktick session" in output
    assert "Session cookie saved" in output


@pytest.mark.anyio
async def test_oauth_login_preserves_stored_session(tmp_path: Path, mock_api: respx.MockRouter):
    credentials_path = tmp_path / "credentials.json"
    save_credentials({"session_token": "session-token"}, credentials_path)
    mock_api.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "access-token"})
    )

    await cli._exchange_and_save(
        "auth-code",
        "client-id",
        "client-secret",
        "http://127.0.0.1:8080/callback",
        credentials_path,
    )

    assert load_credentials(credentials_path) == {
        "session_token": "session-token",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "access_token": "access-token",
    }


def test_login_stores_oauth_and_session_in_one_run(monkeypatch, tmp_path: Path, capsys):
    credentials_path = tmp_path / "credentials.json"
    args = build_parser().parse_args(
        [
            "login",
            "--client-id",
            "client-id",
            "--credentials-file",
            str(credentials_path),
        ]
    )

    async def fake_exchange_and_save(*exchange_args):
        save_credentials({"access_token": "access-token"}, credentials_path)
        return credentials_path

    monkeypatch.setenv("TICKTICK_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(cli, "wait_for_authorization_code", lambda *args, **kwargs: "code")
    monkeypatch.setattr(cli, "_exchange_and_save", fake_exchange_and_save)
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "foo=bar; t=session-token")

    cli.login(args)

    assert load_credentials(credentials_path) == {
        "access_token": "access-token",
        "session_token": "session-token",
    }
    assert "OAuth and browser session credentials saved" in capsys.readouterr().out
