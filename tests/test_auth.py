from __future__ import annotations

import base64
import json
import socket
import stat
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

import httpx
import pytest
import respx

from ticktick_mcp.auth import (
    AUTHORIZE_URL,
    TOKEN_URL,
    build_authorization_url,
    exchange_authorization_code,
    load_credentials,
    parse_authorization_callback,
    refresh_access_token,
    save_credentials,
    wait_for_authorization_code,
)


class TestBrowserLogin:
    def test_build_authorization_url(self):
        url = build_authorization_url(
            "client-id",
            "http://127.0.0.1:8080/callback",
            "random-state",
        )

        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == AUTHORIZE_URL
        assert params == {
            "client_id": ["client-id"],
            "scope": ["tasks:read tasks:write"],
            "state": ["random-state"],
            "redirect_uri": ["http://127.0.0.1:8080/callback"],
            "response_type": ["code"],
        }

    def test_parse_callback(self):
        code = parse_authorization_callback(
            "/callback?code=auth-code&state=random-state",
            "/callback",
            "random-state",
        )
        assert code == "auth-code"

    def test_rejects_callback_state_mismatch(self):
        with pytest.raises(ValueError, match="state mismatch"):
            parse_authorization_callback(
                "/callback?code=auth-code&state=wrong-state",
                "/callback",
                "random-state",
            )

    def test_loopback_callback_server(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        redirect_uri = f"http://127.0.0.1:{port}/callback"

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                wait_for_authorization_code,
                "https://ticktick.com/oauth/authorize",
                redirect_uri,
                "random-state",
                3,
                False,
            )
            callback_url = f"{redirect_uri}?code=auth-code&state=random-state"
            for _ in range(20):
                try:
                    with urlopen(callback_url, timeout=0.2) as response:
                        assert response.status == 200
                    break
                except URLError:
                    time.sleep(0.05)
            else:
                pytest.fail("OAuth callback server did not start")

            assert future.result(timeout=1) == "auth-code"

    @pytest.mark.anyio
    async def test_exchange_authorization_code(self, mock_api: respx.MockRouter):
        route = mock_api.post(TOKEN_URL).mock(
            return_value=httpx.Response(
                200,
                json={"access_token": "access-token", "refresh_token": "refresh-token"},
            )
        )

        async with httpx.AsyncClient() as http:
            result = await exchange_authorization_code(
                http,
                "auth-code",
                "client-id",
                "client-secret",
                "http://127.0.0.1:8080/callback",
            )

        assert result["access_token"] == "access-token"
        request = route.calls.last.request
        assert request.headers["Authorization"] == (
            "Basic " + base64.b64encode(b"client-id:client-secret").decode()
        )
        assert parse_qs(request.content.decode()) == {
            "code": ["auth-code"],
            "grant_type": ["authorization_code"],
            "scope": ["tasks:read tasks:write"],
            "redirect_uri": ["http://127.0.0.1:8080/callback"],
        }

    def test_save_and_load_credentials(self, tmp_path: Path):
        path = tmp_path / "config" / "credentials.json"
        saved_path = save_credentials(
            {
                "client_id": "client-id",
                "client_secret": "client-secret",
                "access_token": "access-token",
                "refresh_token": None,
            },
            path,
        )

        assert saved_path == path
        assert load_credentials(path) == {
            "client_id": "client-id",
            "client_secret": "client-secret",
            "access_token": "access-token",
        }
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert json.loads(path.read_text())["refresh_token"] is None


class TestRefreshToken:
    @pytest.mark.anyio
    async def test_refresh_success(self, mock_api: respx.MockRouter):
        mock_api.post(TOKEN_URL).mock(
            return_value=httpx.Response(
                200,
                json={"access_token": "new-access", "refresh_token": "new-refresh"},
            )
        )
        async with httpx.AsyncClient() as http:
            access, refresh = await refresh_access_token(
                http, "old-refresh", "client-id", "client-secret"
            )
        assert access == "new-access"
        assert refresh == "new-refresh"

    @pytest.mark.anyio
    async def test_refresh_no_new_refresh(self, mock_api: respx.MockRouter):
        mock_api.post(TOKEN_URL).mock(
            return_value=httpx.Response(
                200,
                json={"access_token": "new-access"},
            )
        )
        async with httpx.AsyncClient() as http:
            access, refresh = await refresh_access_token(
                http, "old-refresh", "client-id", "client-secret"
            )
        assert access == "new-access"
        assert refresh is None

    @pytest.mark.anyio
    async def test_refresh_failure(self, mock_api: respx.MockRouter):
        mock_api.post(TOKEN_URL).mock(
            return_value=httpx.Response(401, json={"error": "invalid_grant"})
        )
        async with httpx.AsyncClient() as http:
            with pytest.raises(httpx.HTTPStatusError):
                await refresh_access_token(http, "bad-refresh", "client-id", "client-secret")
