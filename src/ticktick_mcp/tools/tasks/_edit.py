from __future__ import annotations

from typing import Any

from fastmcp import Context
from fastmcp.exceptions import ToolError

from ticktick_mcp.tools.tasks._builders import _build_edit_task_updates
from ticktick_mcp.tools.tasks._common import _get_client, _resolve_project_id, tool
from ticktick_mcp.tools.tasks._v2 import _edit_task_v2, _edit_tasks_v2


@tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def edit_task(
    ctx: Context,
    task_id: str,
    project: str,
    title: str | None = None,
    due: str | None = None,
    start: str | None = None,
    priority: str | None = None,
    tags: list[str] | None = None,
    content: str | None = None,
    desc: str | None = None,
    clear_due: bool = False,
    clear_start: bool = False,
    reminders: list[str] | None = None,
    clear_reminders: bool = False,
    timezone: str | None = None,
    repeat: str | None = None,
    repeat_from: str | None = None,
    clear_repeat: bool = False,
    sort_order: int | None = None,
) -> dict[str, Any]:
    """Update an existing task.

    Only provided fields are changed. Use clear_due/clear_start to remove dates.
    Requires a v2 session token because TickTick's v1 edit endpoint does not
    reliably persist changes.

    Args:
        task_id: The task ID to edit.
        project: The project name or ID containing the task.
        title: New task title.
        due: New due date ("today", "tomorrow", "YYYY-MM-DD", "YYYY-MM-DDTHH:MM").
        start: New start date.
        priority: New priority: "none", "low", "medium", "high".
        tags: Replace all tags with this list.
        content: New markdown content.
        desc: New plain text description.
        clear_due: Set to true to remove the due date.
        clear_start: Set to true to remove the start date.
        reminders: Replace task reminders. Accepts official TickTick triggers
            such as "TRIGGER:PT0S" or "TRIGGER:-PT30M", bare ISO-8601 durations
            such as "PT30M", and compact before-due offsets such as "30m",
            "1h", or "1d".
        clear_reminders: Set to true to remove all reminders.
        timezone: IANA timezone for date interpretation.
        repeat: New RFC 5545 RRULE, including the "RRULE:" prefix.
        repeat_from: Repeat origin. Currently supports "due_date" (default) or "1".
        clear_repeat: Set to true to make the task non-repeating.
        sort_order: Manual position. Lower values appear first. TickTick spaces
            positions by 1099511627776 (2**40); use multiples of it. The order
            shows only in views with Custom sort, not Date sort.
    """
    client = _get_client(ctx)
    pid = await _resolve_project_id(client, project)

    if repeat is not None and clear_repeat:
        raise ToolError("Use either repeat or clear_repeat, not both")

    body = _build_edit_task_updates(
        task_id=task_id,
        project_id=pid,
        title=title,
        due=due,
        start=start,
        priority=priority,
        tags=tags,
        content=content,
        desc=desc,
        clear_due=clear_due,
        clear_start=clear_start,
        reminders=reminders,
        clear_reminders=clear_reminders,
        timezone=timezone,
        sort_order=sort_order,
    )

    return await _edit_task_v2(client, task_id, pid, body, repeat, clear_repeat, repeat_from)


@tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def edit_tasks(
    ctx: Context,
    project: str,
    tasks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Update multiple tasks in one v2 batch request.

    Each item accepts the same editable fields as edit_task and requires
    task_id. All tasks must be in the same project.

    Args:
        project: Project name or ID containing the tasks.
        tasks: Task update objects. Each object requires task_id and may include
            title, due, start, priority, tags, content, desc, clear_due,
            clear_start, reminders, clear_reminders, timezone, repeat,
            repeat_from, clear_repeat, and sort_order.
    """
    client = _get_client(ctx)
    pid = await _resolve_project_id(client, project)
    edits: list[dict[str, Any]] = []

    for i, task in enumerate(tasks):
        task_id = task.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise ToolError(f"tasks[{i}].task_id is required")
        repeat = task.get("repeat")
        clear_repeat = task.get("clear_repeat", False)
        if repeat is not None and clear_repeat:
            raise ToolError(f"tasks[{i}] uses both repeat and clear_repeat")

        updates = _build_edit_task_updates(
            task_id=task_id,
            project_id=pid,
            title=task.get("title"),
            due=task.get("due"),
            start=task.get("start"),
            priority=task.get("priority"),
            tags=task.get("tags"),
            content=task.get("content"),
            desc=task.get("desc"),
            clear_due=task.get("clear_due", False),
            clear_start=task.get("clear_start", False),
            reminders=task.get("reminders"),
            clear_reminders=task.get("clear_reminders", False),
            timezone=task.get("timezone"),
            sort_order=task.get("sort_order"),
        )
        edits.append(
            {
                "task_id": task_id,
                "updates": updates,
                "repeat": repeat,
                "repeat_from": task.get("repeat_from"),
                "clear_repeat": clear_repeat,
            }
        )

    return await _edit_tasks_v2(client, pid, edits)
