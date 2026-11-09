from __future__ import annotations

from typing import Any

import httpx
from fastmcp import Context
from fastmcp.exceptions import ToolError

from ticktick_mcp.tools.tasks._common import (
    _get_client,
    _get_inbox_id,
    _resolve_project_id,
    logger,
    tool,
)


@tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def list_tasks(
    ctx: Context,
    project: str | None = None,
    status: str = "active",
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List tasks from TickTick.

    Retrieves tasks from a specific project or all projects. Use 'status' to
    filter by active/completed tasks. For completed tasks across all projects,
    omit the project parameter.

    Args:
        project: Project name or ID to list tasks from. Supports fuzzy matching.
            Use "inbox" for the default inbox. Omit to list from all projects.
        status: Filter by task status: "active" (default) or "completed".
        limit: Maximum number of completed tasks to return (only used with status="completed").
    """
    client = _get_client(ctx)

    if status == "completed":
        if project:
            pid = await _resolve_project_id(client, project)
            return await client.v2_get(f"/project/{pid}/completed")
        return await client.v2_get(f"/project/all/completedInAll/?limit={limit}")

    if project:
        pid = await _resolve_project_id(client, project)
        data = await client.v1_get(f"/project/{pid}/data")
        return data.get("tasks") or []

    # All projects
    projects = await client.sync_projects()
    all_tasks: list[dict[str, Any]] = []
    for p in projects:
        try:
            data = await client.v1_get(f"/project/{p['id']}/data")
            all_tasks.extend(data.get("tasks") or [])
        except httpx.HTTPError as exc:
            logger.warning("Skipping project %s: %s", p["id"], exc)
            continue

    # Also try inbox
    try:
        inbox_id = await _get_inbox_id(client)
        data = await client.v1_get(f"/project/{inbox_id}/data")
        all_tasks.extend(data.get("tasks") or [])
    except (httpx.HTTPError, ToolError) as exc:
        logger.warning("Skipping inbox: %s", exc)

    return all_tasks


@tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def get_task(
    ctx: Context,
    task_id: str,
    project: str,
) -> dict[str, Any]:
    """Get a single task by its ID.

    Args:
        task_id: The task ID.
        project: The project name or ID containing the task.
    """
    client = _get_client(ctx)
    pid = await _resolve_project_id(client, project)
    return await client.v1_get(f"/project/{pid}/task/{task_id}")


@tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def list_trash(ctx: Context) -> list[dict[str, Any]]:
    """List tasks in the trash.

    Returns tasks that have been deleted but not yet permanently removed.
    Requires v2 session token.
    """
    client = _get_client(ctx)
    data = await client.v2_get("/project/all/trash/page")
    return data.get("tasks") or []
