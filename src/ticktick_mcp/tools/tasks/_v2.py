from __future__ import annotations

import uuid
from typing import Any

from fastmcp.exceptions import ToolError

from ticktick_mcp.client import TickTickClient
from ticktick_mcp.tools.tasks._repeat import _normalize_repeat_from, _normalize_repeat_rule


def _comment_body(
    *,
    task_id: str,
    project_id: str,
    text: str,
    comment_id: str | None = None,
    reply_comment_id: str | None = None,
    mentions: list[dict[str, Any]] | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not text:
        raise ToolError("Comment text is required")

    body: dict[str, Any] = {
        "id": comment_id or uuid.uuid4().hex,
        "title": text,
        "taskId": task_id,
        "projectId": project_id,
    }
    if reply_comment_id is not None:
        body["replyCommentId"] = reply_comment_id
    if mentions is not None:
        body["mentions"] = mentions
    if attachments is not None:
        body["attachments"] = attachments
    return body


def _comments_from_response(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        comments = data.get("comments")
        if isinstance(comments, list):
            return comments
    raise ToolError("Unexpected TickTick comments response")


async def _list_task_comments_v2(
    client: TickTickClient,
    *,
    task_id: str,
    project_id: str,
) -> list[dict[str, Any]]:
    data = await client.v2_get(f"/project/{project_id}/task/{task_id}/comments")
    return _comments_from_response(data)


async def _get_task_comment_v2(
    client: TickTickClient,
    *,
    task_id: str,
    project_id: str,
    comment_id: str,
) -> dict[str, Any]:
    comments = await _list_task_comments_v2(client, task_id=task_id, project_id=project_id)
    for comment in comments:
        if comment.get("id") == comment_id:
            return comment
    raise ToolError(f"Comment {comment_id} was not found on task {task_id}")


async def _add_task_comment_v2(
    client: TickTickClient,
    *,
    task_id: str,
    project_id: str,
    text: str,
    reply_comment_id: str | None = None,
    mentions: list[dict[str, Any]] | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    body = _comment_body(
        task_id=task_id,
        project_id=project_id,
        text=text,
        reply_comment_id=reply_comment_id,
        mentions=mentions,
        attachments=attachments,
    )
    await client.v2_post(f"/project/{project_id}/task/{task_id}/comment", body)
    return await _get_task_comment_v2(
        client,
        task_id=task_id,
        project_id=project_id,
        comment_id=body["id"],
    )


async def _edit_task_comment_v2(
    client: TickTickClient,
    *,
    task_id: str,
    project_id: str,
    comment_id: str,
    text: str,
) -> dict[str, Any]:
    comment = await _get_task_comment_v2(
        client,
        task_id=task_id,
        project_id=project_id,
        comment_id=comment_id,
    )
    comment["title"] = text
    await client.v2_put(f"/project/{project_id}/task/{task_id}/comment/{comment_id}", comment)
    return await _get_task_comment_v2(
        client,
        task_id=task_id,
        project_id=project_id,
        comment_id=comment_id,
    )


async def _delete_task_comment_v2(
    client: TickTickClient,
    *,
    task_id: str,
    project_id: str,
    comment_id: str,
) -> str:
    await client.v2_delete(f"/project/{project_id}/task/{task_id}/comment/{comment_id}")
    return f"Comment {comment_id} deleted from task {task_id}"


async def _edit_task_v2(
    client: TickTickClient,
    task_id: str,
    project_id: str,
    updates: dict[str, Any],
    repeat: str | None,
    clear_repeat: bool,
    repeat_from: str | None = None,
) -> dict[str, Any]:
    """Update a task through the v2 batch endpoint used by the web UI."""
    task = await _prepare_edit_task_v2(
        client, task_id, project_id, updates, repeat, clear_repeat, repeat_from
    )

    payload = {
        "add": [],
        "update": [task],
        "delete": [],
        "addAttachments": [],
        "updateAttachments": [],
        "deleteAttachments": [],
    }
    await client.v2_post("/batch/task", payload)
    return task


async def _prepare_edit_task_v2(
    client: TickTickClient,
    task_id: str,
    project_id: str,
    updates: dict[str, Any],
    repeat: str | None,
    clear_repeat: bool,
    repeat_from: str | None = None,
) -> dict[str, Any]:
    """Fetch and merge a task update without posting it."""
    task = await client.v1_get(f"/project/{project_id}/task/{task_id}")
    task.update({key: value for key, value in updates.items() if key != "taskId"})
    task["id"] = task_id
    task["projectId"] = project_id

    if clear_repeat:
        task["repeatFlag"] = None
        task["repeatFirstDate"] = task.get("startDate") or task.get("dueDate")
        task["repeatFrom"] = None
    elif repeat is not None:
        first_date = task.get("startDate") or task.get("dueDate")
        if not first_date:
            raise ToolError("A repeating task requires a start or due date")
        task["repeatFlag"] = _normalize_repeat_rule(repeat)
        task["repeatFirstDate"] = first_date
        task["repeatFrom"] = _normalize_repeat_from(repeat_from)
    elif repeat_from is not None:
        if not task.get("repeatFlag"):
            raise ToolError("repeat_from requires an existing repeat rule or repeat")
        task["repeatFrom"] = _normalize_repeat_from(repeat_from)

    if "startDate" in updates or "dueDate" in updates:
        task["repeatFirstDate"] = task.get("startDate") or task.get("dueDate")

    return task


async def _edit_tasks_v2(
    client: TickTickClient,
    project_id: str,
    edits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Update multiple tasks through one v2 batch request."""
    tasks = [
        await _prepare_edit_task_v2(
            client,
            edit["task_id"],
            project_id,
            edit["updates"],
            edit.get("repeat"),
            edit.get("clear_repeat", False),
            edit.get("repeat_from"),
        )
        for edit in edits
    ]

    payload = {
        "add": [],
        "update": tasks,
        "delete": [],
        "addAttachments": [],
        "updateAttachments": [],
        "deleteAttachments": [],
    }
    await client.v2_post("/batch/task", payload)
    return tasks
