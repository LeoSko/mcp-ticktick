from __future__ import annotations

import argparse
import asyncio
import contextlib
import getpass
import os
import secrets
import sys
from pathlib import Path

import httpx

from ticktick_mcp.auth import (
    DEFAULT_REDIRECT_URI,
    build_authorization_url,
    default_credentials_path,
    exchange_authorization_code,
    extract_session_token,
    load_credentials,
    save_credentials,
    save_session_token,
    wait_for_authorization_code,
)


def _required_value(value: str | None, prompt: str, secret: bool = False) -> str:
    if value:
        return value
    entered = getpass.getpass(prompt) if secret else input(prompt)
    if not entered.strip():
        raise SystemExit(f"{prompt.rstrip(': ')} is required")
    return entered.strip()


def session_cookie_instructions() -> str:
    return (
        "Private v2/v3 API setup:\n"
        "1. Sign in at https://ticktick.com and open browser developer tools.\n"
        "2. Open Network, select an api.ticktick.com request, and copy its Cookie "
        "request header.\n"
        "3. Run `mcp-ticktick session` and paste that header. The helper extracts "
        "the `t` cookie and stores it securely.\n"
        "You can also paste only the value of the `t` cookie from Application/Storage "
        "-> Cookies."
    )


async def _exchange_and_save(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    credentials_path: Path,
) -> Path:
    async with httpx.AsyncClient(timeout=30.0) as http:
        tokens = await exchange_authorization_code(
            http, code, client_id, client_secret, redirect_uri
        )
    credentials = load_credentials(credentials_path)
    credentials.update(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "access_token": str(tokens["access_token"]),
        }
    )
    if refresh_token := tokens.get("refresh_token"):
        credentials["refresh_token"] = str(refresh_token)
    else:
        credentials.pop("refresh_token", None)
    return save_credentials(credentials, credentials_path)


def login(args: argparse.Namespace) -> None:
    print(
        "TickTick OAuth setup:\n"
        "1. Open https://developer.ticktick.com/manage\n"
        "2. Create or select an app.\n"
        f"3. Set its OAuth redirect URL to: {args.redirect_uri}\n"
        "4. Copy the Client ID and Client Secret shown there.\n"
    )
    client_id = _required_value(
        args.client_id or os.environ.get("TICKTICK_CLIENT_ID"),
        "TickTick client ID: ",
    )
    client_secret = _required_value(
        os.environ.get("TICKTICK_CLIENT_SECRET"),
        "TickTick client secret: ",
        secret=True,
    )
    state = secrets.token_urlsafe(32)
    authorization_url = build_authorization_url(client_id, args.redirect_uri, state)
    code = wait_for_authorization_code(
        authorization_url,
        args.redirect_uri,
        state,
        timeout=args.timeout,
        open_browser=not args.no_browser,
    )
    credentials_path = asyncio.run(
        _exchange_and_save(
            code,
            client_id,
            client_secret,
            args.redirect_uri,
            args.credentials_file,
        )
    )
    print(
        f"OAuth authentication complete. Credentials saved to {credentials_path}\n\n"
        f"{session_cookie_instructions()}"
    )


def store_session(args: argparse.Namespace) -> None:
    print(session_cookie_instructions())
    raw_value = (
        sys.stdin.read()
        if args.stdin
        else getpass.getpass("Paste the `t` cookie value or full Cookie header: ")
    )
    try:
        token = extract_session_token(raw_value)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    credentials_path = save_session_token(token, args.credentials_file)
    print(f"Session cookie saved to {credentials_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mcp-ticktick")
    subparsers = parser.add_subparsers(dest="command")
    login_parser = subparsers.add_parser("login", help="Authenticate through a web browser")
    login_parser.add_argument("--client-id")
    login_parser.add_argument(
        "--redirect-uri",
        default=os.environ.get("TICKTICK_REDIRECT_URI", DEFAULT_REDIRECT_URI),
        help="Must exactly match the loopback URL registered in TickTick",
    )
    login_parser.add_argument(
        "--credentials-file",
        type=Path,
        default=default_credentials_path(),
    )
    login_parser.add_argument("--timeout", type=float, default=300)
    login_parser.add_argument("--no-browser", action="store_true")
    session_parser = subparsers.add_parser(
        "session", help="Store the browser session cookie for private v2/v3 APIs"
    )
    session_parser.add_argument(
        "--credentials-file",
        type=Path,
        default=default_credentials_path(),
    )
    session_parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read the cookie value or Cookie header from standard input",
    )
    serve_parser = subparsers.add_parser("serve", help="Run with Streamable HTTP or SSE transport")
    serve_parser.add_argument(
        "--transport",
        choices=("http", "streamable-http", "sse"),
        default=os.environ.get("TICKTICK_MCP_TRANSPORT", "http"),
    )
    serve_parser.add_argument(
        "--host",
        default=os.environ.get("TICKTICK_MCP_HOST", "127.0.0.1"),
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("TICKTICK_MCP_PORT", "8000")),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "login":
        login(args)
        return
    if args.command == "session":
        store_session(args)
        return

    from ticktick_mcp.server import main as server_main

    if args.command == "serve":
        if args.host not in {"127.0.0.1", "localhost", "::1"}:
            print(
                "Warning: HTTP transport has no built-in authentication. "
                "Use a TLS/authenticating reverse proxy before exposing it.",
                file=sys.stderr,
            )
        with contextlib.suppress(KeyboardInterrupt):
            server_main(transport=args.transport, host=args.host, port=args.port)
        return

    with contextlib.suppress(KeyboardInterrupt):
        server_main()
