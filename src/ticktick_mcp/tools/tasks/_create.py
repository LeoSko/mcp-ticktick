from __future__ import annotations

from typing import Any

from fastmcp import Context
from fastmcp.exceptions import ToolError

from ticktick_mcp.tools.tasks._builders import _build_add_task_body
from ticktick_mcp.tools.tasks._common import _get_client, tool


@tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def add_task(
    ctx: Context,
    title: str,
    project: str | None = None,
    due: str | None = None,
    start: str | None = None,
    duration: str | None = None,
    priority: str = "none",
    tags: list[str] | None = None,
    content: str | None = None,
    desc: str | None = None,
    items: list[str] | None = None,
    reminders: list[str] | None = None,
    all_day: bool | None = None,
    timezone: str | None = None,
    repeat: str | None = None,
    repeat_from: str | None = None,
    sort_order: int | None = None,
) -> dict[str, Any]:
    """Create a new task in TickTick.

    Args:
        title: Task title (required).
        project: Project name or ID. Supports fuzzy matching. Omit for inbox.
        due: Due date. Accepts "today", "tomorrow", "YYYY-MM-DD", "YYYY-MM-DDTHH:MM".
        start: Start date. Same format as due. If duration is set, defaults to due.
        duration: Duration like "1h", "30m", "1h30m". Requires a start or due date with a time.
        priority: Priority level: "none" (default), "low", "medium", "high".
        tags: List of tag names to apply.
        content: Markdown content/notes for the task.
        desc: Plain text description.
        items: List of checklist item titles.
        reminders: List of reminder triggers. Accepts official TickTick triggers
            such as "TRIGGER:PT0S" or "TRIGGER:-PT30M", bare ISO-8601 durations
            such as "PT30M", and compact before-due offsets such as "30m",
            "1h", or "1d".
        all_day: Whether this is an all-day task. Auto-detected from date format.
        timezone: IANA timezone name (e.g. "America/Chicago"). Defaults to system timezone.
        repeat: RFC 5545 RRULE, including the "RRULE:" prefix.
        repeat_from: Repeat origin. Currently supports "due_date" (default) or "1".
        sort_order: Manual position, as in edit_task.
    """
    client = _get_client(ctx)
    body = await _build_add_task_body(
        client,
        title=title,
        project=project,
        due=due,
        start=start,
        duration=duration,
        priority=priority,
        tags=tags,
        content=content,
        desc=desc,
        items=items,
        reminders=reminders,
        all_day=all_day,
        timezone=timezone,
        repeat=repeat,
        repeat_from=repeat_from,
        sort_order=sort_order,
    )

    return await client.v1_post("/task", body)


@tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def add_tasks(
    ctx: Context,
    tasks: list[dict[str, Any]],
    project: str | None = None,
) -> list[dict[str, Any]]:
    """Create multiple tasks in one MCP call.

    Each item accepts the same fields as add_task. The top-level project is
    used as the default, and an item-level project overrides it.

    Args:
        tasks: Task objects to create. Each object requires title and may include
            project, due, start, duration, priority, tags, content, desc, items,
            reminders, all_day, timezone, repeat, repeat_from, and sort_order.
        project: Default project name or ID for every task.
    """
    client = _get_client(ctx)
    created: list[dict[str, Any]] = []

    for i, task in enumerate(tasks):
        title = task.get("title")
        if not isinstance(title, str) or not title:
            raise ToolError(f"tasks[{i}].title is required")
        body = await _build_add_task_body(
            client,
            title=title,
            project=task.get("project") or project,
            due=task.get("due"),
            start=task.get("start"),
            duration=task.get("duration"),
            priority=task.get("priority", "none"),
            tags=task.get("tags"),
            content=task.get("content"),
            desc=task.get("desc"),
            items=task.get("items"),
            reminders=task.get("reminders"),
            all_day=task.get("all_day"),
            timezone=task.get("timezone"),
            repeat=task.get("repeat"),
            repeat_from=task.get("repeat_from"),
            sort_order=task.get("sort_order"),
        )
        created.append(await client.v1_post("/task", body))

    return created
