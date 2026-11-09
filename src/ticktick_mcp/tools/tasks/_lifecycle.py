from __future__ import annotations

from typing import Any

from fastmcp import Context
from fastmcp.exceptions import ToolError

from ticktick_mcp.tools.tasks._common import _get_client, _resolve_project_id, tool


@tool(
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


@tool(
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


@tool(
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


@tool(
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


@tool(
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


@tool(
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


@tool(
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
