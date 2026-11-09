from __future__ import annotations

from typing import Any

from fastmcp import Context

from ticktick_mcp.tools.tasks._common import _get_client, _resolve_project_id, tool
from ticktick_mcp.tools.tasks._v2 import (
    _add_task_comment_v2,
    _delete_task_comment_v2,
    _edit_task_comment_v2,
    _list_task_comments_v2,
)


@tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def list_task_comments(
    ctx: Context,
    task_id: str,
    project: str,
) -> list[dict[str, Any]]:
    """List comments for a task.

    Requires a v2 session token. Responses include TickTick's comment ID,
    title text, createdTime, modifiedTime, userProfile, reply metadata,
    mentions, and attachments when present.

    Args:
        task_id: The task ID.
        project: The project name or ID containing the task.
    """
    client = _get_client(ctx)
    pid = await _resolve_project_id(client, project)
    return await _list_task_comments_v2(client, task_id=task_id, project_id=pid)


@tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def add_task_comment(
    ctx: Context,
    task_id: str,
    project: str,
    text: str,
    reply_comment_id: str | None = None,
    mentions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Add a comment to a task.

    Requires a v2 session token. The returned comment includes the stable
    comment ID and author/timestamp metadata returned by TickTick.

    Args:
        task_id: The task ID.
        project: The project name or ID containing the task.
        text: Comment text.
        reply_comment_id: Optional comment ID to reply to.
        mentions: Optional raw TickTick mention objects.
    """
    client = _get_client(ctx)
    pid = await _resolve_project_id(client, project)
    return await _add_task_comment_v2(
        client,
        task_id=task_id,
        project_id=pid,
        text=text,
        reply_comment_id=reply_comment_id,
        mentions=mentions,
    )


@tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def edit_task_comment(
    ctx: Context,
    task_id: str,
    project: str,
    comment_id: str,
    text: str,
) -> dict[str, Any]:
    """Edit a task comment.

    Requires a v2 session token. TickTick supports editing comments through
    the private web API; this tool preserves the existing comment metadata
    and replaces only the title text.

    Args:
        task_id: The task ID.
        project: The project name or ID containing the task.
        comment_id: The stable comment ID to edit.
        text: New comment text.
    """
    client = _get_client(ctx)
    pid = await _resolve_project_id(client, project)
    return await _edit_task_comment_v2(
        client,
        task_id=task_id,
        project_id=pid,
        comment_id=comment_id,
        text=text,
    )


@tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def delete_task_comment(
    ctx: Context,
    task_id: str,
    project: str,
    comment_id: str,
) -> str:
    """Delete a task comment.

    Requires a v2 session token.

    Args:
        task_id: The task ID.
        project: The project name or ID containing the task.
        comment_id: The stable comment ID to delete.
    """
    client = _get_client(ctx)
    pid = await _resolve_project_id(client, project)
    return await _delete_task_comment_v2(
        client,
        task_id=task_id,
        project_id=pid,
        comment_id=comment_id,
    )
