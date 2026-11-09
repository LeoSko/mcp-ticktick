from __future__ import annotations

import contextlib
import logging
from typing import Any

from fastmcp import Context
from fastmcp.exceptions import ToolError

from ticktick_mcp.client import TickTickClient
from ticktick_mcp.models import Project
from ticktick_mcp.resolve import resolve_name

logger = logging.getLogger(__name__)

_TOOLS: list[tuple[Any, dict[str, Any]]] = []


def tool(**kwargs: Any) -> Any:
    def collect(fn: Any) -> Any:
        _TOOLS.append((fn, kwargs))
        return fn

    return collect


PRIORITY_MAP = {"none": 0, "low": 1, "medium": 3, "high": 5}
RRULE_FREQS = {"DAILY", "WEEKLY", "MONTHLY", "YEARLY"}
RRULE_KEYS = {
    "FREQ",
    "INTERVAL",
    "COUNT",
    "UNTIL",
    "BYDAY",
    "BYMONTHDAY",
    "BYMONTH",
    "WKST",
}
WEEKDAYS = {"MO", "TU", "WE", "TH", "FR", "SA", "SU"}


def _get_client(ctx: Context) -> TickTickClient:
    return ctx.request_context.lifespan_context["client"]  # type: ignore[union-attr]


async def _resolve_project_id(client: TickTickClient, project: str) -> str:
    """Resolve a project name/ID, with special 'inbox' handling."""
    if project.lower() == "inbox":
        return await _get_inbox_id(client)

    if project.startswith("inbox") and project[5:].isdigit():
        return project

    if len(project) >= 20 and all(c in "0123456789abcdefABCDEF" for c in project):
        return project

    projects = await client.sync_projects()
    parsed = [Project(**p) for p in projects]
    return resolve_name(project, parsed, lambda p: p.name, lambda p: p.id, "project")


async def _get_inbox_id(client: TickTickClient) -> str:
    """Discover the inbox project ID by creating and deleting a temp task."""
    if client._inbox_project_id:
        return client._inbox_project_id

    task = await client.v1_post("/task", {"title": "__inbox_probe__"})
    inbox_id = task.get("projectId")
    if not inbox_id:
        raise ToolError("Could not discover inbox project ID")

    with contextlib.suppress(Exception):
        await client.v1_delete(f"/project/{inbox_id}/task/{task['id']}")

    client._inbox_project_id = inbox_id
    return inbox_id


def _priority_value(priority: str) -> int:
    pri_val = PRIORITY_MAP.get(priority.lower())
    if pri_val is None:
        raise ToolError(f"Invalid priority '{priority}'. Use: none, low, medium, high")
    return pri_val
