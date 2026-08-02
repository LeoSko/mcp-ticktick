from __future__ import annotations

import contextlib
import uuid
from typing import Any

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError

from ticktick_mcp.client import TickTickClient
from ticktick_mcp.dates import ParsedDateTime, normalize_reminders, parse_datetime, parse_duration
from ticktick_mcp.models import Project
from ticktick_mcp.resolve import resolve_name

PRIORITY_MAP = {"none": 0, "low": 1, "medium": 3, "high": 5}


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
) -> dict[str, Any]:
    """Update a task through the v2 batch endpoint used by the web UI."""
    task = await _prepare_edit_task_v2(client, task_id, project_id, updates, repeat, clear_repeat)

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
) -> dict[str, Any]:
    """Fetch and merge a task update without posting it."""
    task = await client.v1_get(f"/project/{project_id}/task/{task_id}")
    task.update({key: value for key, value in updates.items() if key != "taskId"})
    task["id"] = task_id
    task["projectId"] = project_id

    if clear_repeat:
        task["repeatFlag"] = None
        task["repeatFirstDate"] = task.get("startDate") or task.get("dueDate")
    elif repeat is not None:
        if not repeat.upper().startswith("RRULE:"):
            raise ToolError("Repeat must be an RRULE string beginning with 'RRULE:'")
        first_date = task.get("startDate") or task.get("dueDate")
        if not first_date:
            raise ToolError("A repeating task requires a start or due date")
        task["repeatFlag"] = repeat
        task["repeatFirstDate"] = first_date
        task.setdefault("repeatFrom", "1")

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


def _priority_value(priority: str) -> int:
    pri_val = PRIORITY_MAP.get(priority.lower())
    if pri_val is None:
        raise ToolError(f"Invalid priority '{priority}'. Use: none, low, medium, high")
    return pri_val


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
) -> dict[str, Any]:
    body: dict[str, Any] = {"title": title}

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

    return body


def register(mcp: FastMCP) -> None:
    @mcp.tool(
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
            except Exception:
                continue

        # Also try inbox
        try:
            inbox_id = await _get_inbox_id(client)
            data = await client.v1_get(f"/project/{inbox_id}/data")
            all_tasks.extend(data.get("tasks") or [])
        except Exception:
            pass

        return all_tasks

    @mcp.tool(
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

    @mcp.tool(
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

    @mcp.tool(
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

    @mcp.tool(
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

    @mcp.tool(
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

    @mcp.tool(
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
        )

        return await client.v1_post("/task", body)

    @mcp.tool(
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
                reminders, all_day, and timezone.
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
            )
            created.append(await client.v1_post("/task", body))

        return created

    @mcp.tool(
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
        clear_repeat: bool = False,
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
            clear_repeat: Set to true to make the task non-repeating.
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
        )

        return await _edit_task_v2(client, task_id, pid, body, repeat, clear_repeat)

    @mcp.tool(
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
                clear_start, reminders, clear_reminders, timezone, repeat, and
                clear_repeat.
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
            )
            edits.append(
                {
                    "task_id": task_id,
                    "updates": updates,
                    "repeat": repeat,
                    "clear_repeat": clear_repeat,
                }
            )

        return await _edit_tasks_v2(client, pid, edits)

    @mcp.tool(
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        }
    )
    async def complete_task(
        ctx: Context,
        task_id: str,
        project: str,
    ) -> str:
        """Mark a task as complete.

        Args:
            task_id: The task ID to complete.
            project: The project name or ID containing the task.
        """
        client = _get_client(ctx)
        pid = await _resolve_project_id(client, project)
        await client.v1_post_empty(f"/project/{pid}/task/{task_id}/complete")
        return f"Task {task_id} completed"

    @mcp.tool(
        annotations={
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": True,
            "openWorldHint": True,
        }
    )
    async def delete_task(
        ctx: Context,
        task_id: str,
        project: str,
    ) -> str:
        """Permanently delete a task.

        This action cannot be undone. The task is moved to trash first but
        this API call removes it entirely.

        Args:
            task_id: The task ID to delete.
            project: The project name or ID containing the task.
        """
        client = _get_client(ctx)
        pid = await _resolve_project_id(client, project)
        await client.v1_delete(f"/project/{pid}/task/{task_id}")
        return f"Task {task_id} deleted"

    @mcp.tool(
        annotations={
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": True,
            "openWorldHint": True,
        }
    )
    async def delete_tasks(
        ctx: Context,
        task_ids: list[str],
        project: str,
    ) -> dict[str, Any]:
        """Permanently delete multiple tasks in one MCP call.

        This action cannot be undone. Each task is moved to trash first but this
        API call removes it entirely.

        Args:
            task_ids: Task IDs to delete.
            project: The project name or ID containing the tasks.
        """
        client = _get_client(ctx)
        pid = await _resolve_project_id(client, project)
        deleted: list[str] = []

        for task_id in task_ids:
            await client.v1_delete(f"/project/{pid}/task/{task_id}")
            deleted.append(task_id)

        return {"deleted": deleted}

    @mcp.tool(
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        }
    )
    async def move_task(
        ctx: Context,
        task_id: str,
        from_project: str,
        to_project: str,
    ) -> str:
        """Move a task from one project to another.

        Args:
            task_id: The task ID to move.
            from_project: Source project name or ID.
            to_project: Destination project name or ID.
        """
        client = _get_client(ctx)
        from_pid = await _resolve_project_id(client, from_project)
        to_pid = await _resolve_project_id(client, to_project)
        await client.v2_post(
            "/batch/taskProject",
            [{"taskId": task_id, "fromProjectId": from_pid, "toProjectId": to_pid}],
        )
        return f"Task {task_id} moved to {to_project}"

    @mcp.tool(
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        }
    )
    async def set_subtask(
        ctx: Context,
        task_id: str,
        parent_id: str,
        project: str,
    ) -> str:
        """Make a task a subtask of another task.

        Both tasks must be in the same project.

        Args:
            task_id: The task ID to make a subtask.
            parent_id: The parent task ID.
            project: The project name or ID containing both tasks.
        """
        client = _get_client(ctx)
        pid = await _resolve_project_id(client, project)
        await client.v2_post(
            "/batch/taskParent",
            [{"taskId": task_id, "parentId": parent_id, "projectId": pid}],
        )
        return f"Task {task_id} is now a subtask of {parent_id}"

    @mcp.tool(
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        }
    )
    async def set_subtasks(
        ctx: Context,
        project: str,
        assignments: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Make multiple tasks subtasks in one TickTick batch request.

        All tasks and parents must be in the same project.

        Args:
            project: The project name or ID containing all tasks.
            assignments: Objects with task_id and parent_id.
        """
        client = _get_client(ctx)
        pid = await _resolve_project_id(client, project)
        payload: list[dict[str, str]] = []

        for i, assignment in enumerate(assignments):
            task_id = assignment.get("task_id")
            parent_id = assignment.get("parent_id")
            if not task_id:
                raise ToolError(f"assignments[{i}].task_id is required")
            if not parent_id:
                raise ToolError(f"assignments[{i}].parent_id is required")
            payload.append({"taskId": task_id, "parentId": parent_id, "projectId": pid})

        result = await client.v2_post("/batch/taskParent", payload)
        return {"assignments": payload, "result": result}

    @mcp.tool(
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        }
    )
    async def unparent_task(
        ctx: Context,
        task_id: str,
        project: str,
    ) -> dict[str, Any]:
        """Remove a task's parent, making it a top-level task.

        Args:
            task_id: The task ID to unparent.
            project: The project name or ID containing the task.
        """
        client = _get_client(ctx)
        pid = await _resolve_project_id(client, project)
        return await client.v1_post(
            f"/task/{task_id}", {"taskId": task_id, "projectId": pid, "parentId": ""}
        )

    @mcp.tool(
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
