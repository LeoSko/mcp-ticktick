from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import secrets
from pathlib import Path

import httpx

from ticktick_mcp.auth import (
    DEFAULT_REDIRECT_URI,
    build_authorization_url,
    default_credentials_path,
    exchange_authorization_code,
    save_credentials,
    wait_for_authorization_code,
)


def _required_value(value: str | None, prompt: str, secret: bool = False) -> str:
    if value:
        return value
    entered = getpass.getpass(prompt) if secret else input(prompt)
    if not entered.strip():
        raise SystemExit(f"{prompt.rstrip(': ')} is required")
    return entered.strip()


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
    return save_credentials(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token"),
        },
        credentials_path,
    )


def login(args: argparse.Namespace) -> None:
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
    print(f"Authentication complete. Credentials saved to {credentials_path}")


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
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "login":
        login(args)
        return

    from ticktick_mcp.server import main as server_main

    server_main()
