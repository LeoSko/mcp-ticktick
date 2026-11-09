from __future__ import annotations

from typing import Any

from fastmcp.exceptions import ToolError

from ticktick_mcp.client import TickTickClient
from ticktick_mcp.dates import ParsedDateTime, normalize_reminders, parse_datetime, parse_duration
from ticktick_mcp.tools.tasks._common import _priority_value, _resolve_project_id
from ticktick_mcp.tools.tasks._repeat import _normalize_repeat_from, _normalize_repeat_rule


async def _build_add_task_body(
    client: TickTickClient,
    *,
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
    body: dict[str, Any] = {"title": title}
    if sort_order is not None:
        body["sortOrder"] = sort_order

    if project:
        body["projectId"] = await _resolve_project_id(client, project)

    pri_val = _priority_value(priority)
    if pri_val != 0:
        body["priority"] = pri_val

    if tags:
        body["tags"] = tags
    if content is not None:
        body["content"] = content
    if desc is not None:
        body["desc"] = desc
    if items:
        body["items"] = [{"title": t, "status": 0} for t in items]
    if reminders is not None:
        body["reminders"] = normalize_reminders(reminders)

    parsed_due: ParsedDateTime | None = None
    parsed_start: ParsedDateTime | None = None

    if due:
        parsed_due = parse_datetime(due)
        body["dueDate"] = parsed_due.to_api_string(timezone)
        if all_day is None:
            body["isAllDay"] = parsed_due.is_all_day
        else:
            body["isAllDay"] = all_day

    if start:
        parsed_start = parse_datetime(start)
        body["startDate"] = parsed_start.to_api_string(timezone)
        if all_day is None and "isAllDay" not in body:
            body["isAllDay"] = parsed_start.is_all_day

    if duration:
        dur = parse_duration(duration)
        base = parsed_start or parsed_due
        if base is None:
            raise ToolError("Duration requires a start or due date with a time component")
        if base.is_all_day:
            raise ToolError("Duration requires a date with a time component (use YYYY-MM-DDTHH:MM)")
        end = base.add_duration(dur)
        if parsed_start and not parsed_due:
            body["dueDate"] = end.to_api_string(timezone)
        elif parsed_due and not parsed_start:
            body["startDate"] = parsed_due.to_api_string(timezone)
            body["dueDate"] = end.to_api_string(timezone)

    if timezone:
        body["timeZone"] = timezone

    if repeat is not None:
        first_date = body.get("startDate") or body.get("dueDate")
        if not first_date:
            raise ToolError("A repeating task requires a start or due date")
        body["repeatFlag"] = _normalize_repeat_rule(repeat)
        body["repeatFirstDate"] = first_date
        body["repeatFrom"] = _normalize_repeat_from(repeat_from)

    return body


def _build_edit_task_updates(
    *,
    task_id: str,
    project_id: str,
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
    sort_order: int | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"taskId": task_id, "projectId": project_id}

    if title is not None:
        body["title"] = title
    if tags is not None:
        body["tags"] = tags
    if content is not None:
        body["content"] = content
    if desc is not None:
        body["desc"] = desc
    if reminders is not None and clear_reminders:
        raise ToolError("Use either reminders or clear_reminders, not both")
    if clear_reminders:
        body["reminders"] = []
    elif reminders is not None:
        body["reminders"] = normalize_reminders(reminders)

    if priority is not None:
        body["priority"] = _priority_value(priority)

    if clear_due:
        body["dueDate"] = None
    elif due:
        parsed = parse_datetime(due)
        body["dueDate"] = parsed.to_api_string(timezone)
        body["isAllDay"] = parsed.is_all_day

    if clear_start:
        body["startDate"] = None
    elif start:
        parsed = parse_datetime(start)
        body["startDate"] = parsed.to_api_string(timezone)

    if timezone:
        body["timeZone"] = timezone
    if sort_order is not None:
        body["sortOrder"] = sort_order

    return body
