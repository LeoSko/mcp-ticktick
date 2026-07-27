from __future__ import annotations

import base64
import json
import os
import re
import time
import webbrowser
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

AUTHORIZE_URL = "https://ticktick.com/oauth/authorize"
TOKEN_URL = "https://ticktick.com/oauth/token"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8080/callback"
DEFAULT_SCOPES = ("tasks:read", "tasks:write")


def default_credentials_path() -> Path:
    """Return the per-user credentials file path."""
    configured = os.environ.get("TICKTICK_CREDENTIALS_FILE")
    if configured:
        return Path(configured).expanduser()
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return base / "mcp-ticktick" / "credentials.json"


def load_credentials(path: Path | None = None) -> dict[str, str]:
    """Load stored credentials, returning an empty mapping when absent."""
    credentials_path = path or default_credentials_path()
    if not credentials_path.exists():
        return {}
    data = json.loads(credentials_path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Invalid credentials file: {credentials_path}")
    return {str(key): str(value) for key, value in data.items() if value is not None}


def save_credentials(credentials: Mapping[str, Any], path: Path | None = None) -> Path:
    """Atomically save credentials with owner-only permissions."""
    credentials_path = path or default_credentials_path()
    credentials_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary_path = credentials_path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(dict(credentials), indent=2) + "\n")
    temporary_path.chmod(0o600)
    temporary_path.replace(credentials_path)
    credentials_path.chmod(0o600)
    return credentials_path


def extract_session_token(value: str) -> str:
    """Extract the TickTick `t` cookie from a value or copied Cookie header."""
    candidate = value.strip()
    if not candidate:
        raise ValueError("TickTick session cookie is empty")

    match = re.search(r"(?:^|[;\s])t=([^;\s]+)", candidate, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip("\"'")
    if "=" in candidate or ";" in candidate or candidate.lower().startswith("cookie:"):
        raise ValueError("Copied Cookie header does not contain a `t` cookie")
    return candidate


def save_session_token(value: str, path: Path | None = None) -> Path:
    """Add a browser session token to the owner-only credential file."""
    credentials_path = path or default_credentials_path()
    credentials = load_credentials(credentials_path)
    credentials["session_token"] = extract_session_token(value)
    return save_credentials(credentials, credentials_path)


def build_authorization_url(
    client_id: str,
    redirect_uri: str,
    state: str,
    scopes: tuple[str, ...] = DEFAULT_SCOPES,
) -> str:
    """Build TickTick's OAuth authorization URL."""
    params = {
        "client_id": client_id,
        "scope": " ".join(scopes),
        "state": state,
        "redirect_uri": redirect_uri,
        "response_type": "code",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_authorization_code(
    http: httpx.AsyncClient,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    scopes: tuple[str, ...] = DEFAULT_SCOPES,
) -> dict[str, Any]:
    """Exchange an OAuth authorization code for tokens."""
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = await http.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "code": code,
            "grant_type": "authorization_code",
            "scope": " ".join(scopes),
            "redirect_uri": redirect_uri,
        },
    )
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()
    if not data.get("access_token"):
        raise RuntimeError("TickTick token response did not include an access token")
    return data


def _validate_redirect_uri(redirect_uri: str) -> tuple[str, int, str]:
    parsed = urlparse(redirect_uri)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Redirect URI must use http://127.0.0.1 or http://localhost")
    if parsed.query or parsed.fragment:
        raise ValueError("Redirect URI must not contain a query or fragment")
    return parsed.hostname, parsed.port or 80, parsed.path or "/"


def parse_authorization_callback(path: str, callback_path: str, expected_state: str) -> str:
    """Validate an OAuth callback path and return its authorization code."""
    parsed = urlparse(path)
    if parsed.path != callback_path:
        raise ValueError("OAuth callback path mismatch")
    params = parse_qs(parsed.query)
    if params.get("state", [""])[0] != expected_state:
        raise ValueError("OAuth state mismatch")
    if "error" in params:
        raise RuntimeError(params["error"][0])
    code = params.get("code", [""])[0]
    if not code:
        raise ValueError("OAuth callback did not include a code")
    return code


def wait_for_authorization_code(
    authorization_url: str,
    redirect_uri: str,
    expected_state: str,
    timeout: float = 300,
    open_browser: bool = True,
) -> str:
    """Open the authorization page and wait for a validated loopback callback."""
    host, port, callback_path = _validate_redirect_uri(redirect_uri)
    result: dict[str, str] = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != callback_path:
                self.send_error(404)
                return

            try:
                result["code"] = parse_authorization_callback(
                    self.path, callback_path, expected_state
                )
            except (RuntimeError, ValueError) as exc:
                result["error"] = str(exc)
                self._respond(400, "TickTick authentication failed.")
                return

            self._respond(200, "Authentication complete. You can close this window.")

        def _respond(self, status: int, message: str) -> None:
            body = (
                '<!doctype html><html><head><meta charset="utf-8">'
                "<title>TickTick authentication</title></head>"
                f"<body><p>{message}</p></body></html>"
            ).encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    bind_host = "127.0.0.1" if host == "localhost" else host
    with HTTPServer((bind_host, port), CallbackHandler) as server:
        server.timeout = 0.5
        print(f"Open this URL to authorize TickTick:\n{authorization_url}")
        if open_browser:
            webbrowser.open(authorization_url)

        deadline = time.monotonic() + timeout
        while not result and time.monotonic() < deadline:
            server.handle_request()

    if "error" in result:
        raise RuntimeError(result["error"])
    if "code" not in result:
        raise TimeoutError("Timed out waiting for TickTick authorization")
    return result["code"]


async def refresh_access_token(
    http: httpx.AsyncClient,
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> tuple[str, str | None]:
    """Exchange a refresh token for a new access token.

    Returns (new_access_token, optional_new_refresh_token).
    """
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    resp = await http.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        content=f"grant_type=refresh_token&refresh_token={refresh_token}",
    )
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()
    return data["access_token"], data.get("refresh_token")
