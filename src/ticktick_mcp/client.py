from __future__ import annotations

import asyncio
import copy
import json
import logging
import time
from typing import Any
from urllib.parse import quote

import httpx

from ticktick_mcp.auth import refresh_access_token

logger = logging.getLogger(__name__)

V1_BASE = "https://api.ticktick.com/open/v1"
V2_BASE = "https://api.ticktick.com/api/v2"
V3_BASE = "https://api.ticktick.com/api/v3"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


def generate_device_id() -> str:
    """Generate a device ID matching the TickTick web client format.

    Format: "6490" prefix + 20 random hex characters, generated via LCG.
    """
    state = time.time_ns()
    chars: list[str] = []
    for _ in range(20):
        state = (state * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        nibble = (state >> 33) & 0xF
        chars.append(f"{nibble:x}")
    return "6490" + "".join(chars)


def x_device_header(device_id: str) -> str:
    """Build the x-device header JSON string."""
    return json.dumps(
        {
            "platform": "web",
            "os": "macOS 10.15.7",
            "device": "Chrome 130.0.0.0",
            "name": "",
            "version": 6490,
            "id": device_id,
            "channel": "website",
            "campaign": "",
            "websocket": "",
        },
        separators=(",", ":"),
    )


def url_encode(s: str) -> str:
    """Percent-encode a string for URL query parameters."""
    return quote(s, safe="")


class TickTickClient:
    """Async HTTP client for the TickTick API (v1, v2, v3, ms)."""

    def __init__(
        self,
        access_token: str,
        client_id: str | None = None,
        client_secret: str | None = None,
        session_token: str | None = None,
        refresh_token: str | None = None,
    ) -> None:
        self._access_token = access_token
        self._client_id = client_id
        self._client_secret = client_secret
        self._session_token = session_token
        self._refresh_token = refresh_token
        self._device_id = generate_device_id()
        self._http: httpx.AsyncClient | None = None
        self._inbox_project_id: str | None = None
        self._sync_checkpoint: int | None = None
        self._sync_snapshot: dict[str, Any] = {}
        self._sync_lock = asyncio.Lock()

    async def __aenter__(self) -> TickTickClient:
        self._http = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            raise RuntimeError("Client not initialized. Use 'async with client:' context manager.")
        return self._http

    # ------------------------------------------------------------------
    # v1 API — Bearer auth with auto-refresh on 401
    # ------------------------------------------------------------------

    def _v1_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token}"}

    async def _try_refresh(self) -> bool:
        """Attempt to refresh the access token. Returns True on success."""
        if not (self._refresh_token and self._client_id and self._client_secret):
            return False
        try:
            new_access, new_refresh = await refresh_access_token(
                self.http, self._refresh_token, self._client_id, self._client_secret
            )
            self._access_token = new_access
            if new_refresh:
                self._refresh_token = new_refresh
            logger.info("Token refreshed automatically")
            return True
        except Exception:
            logger.warning("Token refresh failed")
            return False

    async def v1_get(self, endpoint: str) -> Any:
        resp = await self.http.get(f"{V1_BASE}{endpoint}", headers=self._v1_headers())
        if resp.status_code == 401 and await self._try_refresh():
            resp = await self.http.get(f"{V1_BASE}{endpoint}", headers=self._v1_headers())
        resp.raise_for_status()
        return resp.json()

    async def v1_post(self, endpoint: str, json_data: Any = None) -> Any:
        resp = await self.http.post(
            f"{V1_BASE}{endpoint}", headers=self._v1_headers(), json=json_data
        )
        if resp.status_code == 401 and await self._try_refresh():
            resp = await self.http.post(
                f"{V1_BASE}{endpoint}", headers=self._v1_headers(), json=json_data
            )
        resp.raise_for_status()
        return resp.json() if resp.content else None

    async def v1_post_empty(self, endpoint: str) -> httpx.Response:
        resp = await self.http.post(f"{V1_BASE}{endpoint}", headers=self._v1_headers())
        if resp.status_code == 401 and await self._try_refresh():
            resp = await self.http.post(f"{V1_BASE}{endpoint}", headers=self._v1_headers())
        resp.raise_for_status()
        return resp

    async def v1_delete(self, endpoint: str) -> httpx.Response:
        resp = await self.http.delete(f"{V1_BASE}{endpoint}", headers=self._v1_headers())
        if resp.status_code == 401 and await self._try_refresh():
            resp = await self.http.delete(f"{V1_BASE}{endpoint}", headers=self._v1_headers())
        resp.raise_for_status()
        return resp

    # ------------------------------------------------------------------
    # v2 API — Cookie auth with x-device header
    # ------------------------------------------------------------------

    def _require_session(self) -> str:
        if not self._session_token:
            raise RuntimeError(
                "v2 session token not set. "
                "Set TICKTICK_V2_SESSION_TOKEN from the 't' cookie in your browser."
            )
        return self._session_token

    @staticmethod
    def _check_v2_response(resp: httpx.Response) -> None:
        """Raise clear errors for common v2 API failures."""
        if resp.status_code == 401:
            raise RuntimeError(
                "V2 session token is invalid or expired. "
                "Update TICKTICK_V2_SESSION_TOKEN with a fresh 't' cookie from your browser."
            )
        if resp.status_code == 403:
            raise RuntimeError("This feature requires a TickTick Premium subscription.")
        resp.raise_for_status()

    def _v2_headers(self) -> dict[str, str]:
        token = self._require_session()
        return {
            "User-Agent": USER_AGENT,
            "x-device": x_device_header(self._device_id),
            "Cookie": f"t={token}",
        }

    async def v2_get(self, endpoint: str) -> Any:
        resp = await self.http.get(f"{V2_BASE}{endpoint}", headers=self._v2_headers())
        self._check_v2_response(resp)
        return resp.json()

    async def v2_post(self, endpoint: str, json_data: Any) -> Any:
        resp = await self.http.post(
            f"{V2_BASE}{endpoint}", headers=self._v2_headers(), json=json_data
        )
        self._check_v2_response(resp)
        return resp.json() if resp.content else None

    async def v2_put(self, endpoint: str, json_data: Any) -> Any:
        resp = await self.http.put(
            f"{V2_BASE}{endpoint}", headers=self._v2_headers(), json=json_data
        )
        self._check_v2_response(resp)
        return resp.json() if resp.content else None

    async def v2_delete(self, endpoint: str) -> httpx.Response:
        resp = await self.http.delete(f"{V2_BASE}{endpoint}", headers=self._v2_headers())
        self._check_v2_response(resp)
        return resp

    # ------------------------------------------------------------------
    # v3 / batch check
    # ------------------------------------------------------------------

    async def v3_get(self, endpoint: str) -> Any:
        resp = await self.http.get(f"{V3_BASE}{endpoint}", headers=self._v2_headers())
        self._check_v2_response(resp)
        return resp.json()

    @staticmethod
    def _item_key(item: Any, keys: tuple[str, ...]) -> str | None:
        if isinstance(item, str):
            return item
        if not isinstance(item, dict):
            return None
        for key in keys:
            value = item.get(key)
            if value is not None:
                return str(value)
        return None

    @classmethod
    def _merge_items(
        cls,
        current: list[Any],
        changes: list[Any],
        keys: tuple[str, ...],
    ) -> list[Any]:
        merged = {key: item for item in current if (key := cls._item_key(item, keys)) is not None}
        for item in changes:
            key = cls._item_key(item, keys)
            if key is None:
                continue
            if isinstance(item, dict) and item.get("deleted"):
                merged.pop(key, None)
            else:
                merged[key] = item
        return list(merged.values())

    def _merge_sync_delta(self, delta: dict[str, Any]) -> None:
        collection_keys = {
            "projectProfiles": ("id",),
            "projectGroups": ("id",),
            "filters": ("id",),
            "tags": ("name", "label"),
        }
        for name, keys in collection_keys.items():
            changes = delta.get(name)
            if isinstance(changes, list):
                current = self._sync_snapshot.get(name)
                self._sync_snapshot[name] = self._merge_items(
                    current if isinstance(current, list) else [],
                    changes,
                    keys,
                )

        task_delta = delta.get("syncTaskBean")
        if isinstance(task_delta, dict):
            current_bean = self._sync_snapshot.get("syncTaskBean")
            current_tasks = current_bean.get("update", []) if isinstance(current_bean, dict) else []
            tasks = self._merge_items(
                current_tasks,
                [
                    *(task_delta.get("add") or []),
                    *(task_delta.get("update") or []),
                ],
                ("id", "taskId"),
            )
            deleted = task_delta.get("delete") or []
            deleted_ids = {
                key
                for item in deleted
                if (key := self._item_key(item, ("id", "taskId"))) is not None
            }
            tasks = [
                task for task in tasks if self._item_key(task, ("id", "taskId")) not in deleted_ids
            ]
            self._sync_snapshot["syncTaskBean"] = {
                **task_delta,
                "add": [],
                "update": tasks,
                "delete": [],
            }

        handled = {*collection_keys, "syncTaskBean"}
        for key, value in delta.items():
            if key not in handled and value is not None:
                self._sync_snapshot[key] = value

    async def batch_check(self) -> dict[str, Any]:
        """Return cached account state refreshed with a v3 checkpoint delta."""
        async with self._sync_lock:
            checkpoint = self._sync_checkpoint or 0
            delta = await self.v3_get(f"/batch/check/{checkpoint}")
            if self._sync_checkpoint is None:
                self._sync_snapshot = copy.deepcopy(delta)
            else:
                self._merge_sync_delta(delta)
            self._sync_checkpoint = int(delta.get("checkPoint") or checkpoint)
            return copy.deepcopy(self._sync_snapshot)

    async def sync_projects(self) -> list[dict[str, Any]]:
        """Return projects from the incrementally refreshed account snapshot."""
        data = await self.batch_check()
        return data.get("projectProfiles") or []

    async def sync_tags(self) -> list[dict[str, Any]]:
        """Return tags from the incrementally refreshed account snapshot."""
        data = await self.batch_check()
        return data.get("tags") or []
