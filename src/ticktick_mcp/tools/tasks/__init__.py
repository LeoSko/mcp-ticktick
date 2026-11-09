"""Task tools: listing, comments, create, edit, and lifecycle."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from ticktick_mcp.tools.tasks import _comments, _create, _edit, _lifecycle, _read
from ticktick_mcp.tools.tasks._builders import _build_add_task_body, _build_edit_task_updates
from ticktick_mcp.tools.tasks._common import _TOOLS, _resolve_project_id
from ticktick_mcp.tools.tasks._v2 import (
    _add_task_comment_v2,
    _delete_task_comment_v2,
    _edit_task_comment_v2,
    _edit_task_v2,
    _edit_tasks_v2,
    _list_task_comments_v2,
)

if TYPE_CHECKING:
    from fastmcp import FastMCP

__all__ = [
    "_add_task_comment_v2",
    "_build_add_task_body",
    "_build_edit_task_updates",
    "_delete_task_comment_v2",
    "_edit_task_comment_v2",
    "_edit_task_v2",
    "_edit_tasks_v2",
    "_list_task_comments_v2",
    "_resolve_project_id",
    "register",
    "uuid",
]
_TOOL_MODULES = (_read, _comments, _create, _edit, _lifecycle)


def register(mcp: FastMCP) -> None:
    for fn, kwargs in _TOOLS:
        mcp.tool(**kwargs)(fn)
