from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from fastmcp.exceptions import ToolError

from ticktick_mcp.client import V1_BASE, V2_BASE, TickTickClient
from ticktick_mcp.tools.tasks import (
    _build_add_task_body,
    _build_edit_task_updates,
    _edit_task_v2,
    _edit_tasks_v2,
    _resolve_project_id,
)


class TestListTasks:
    @pytest.mark.anyio
    async def test_list_by_project(self, client: TickTickClient, mock_api: respx.MockRouter):
        mock_api.get(f"{V1_BASE}/project").mock(
            return_value=httpx.Response(200, json=[{"id": "p1", "name": "Work"}])
        )
        mock_api.get(f"{V1_BASE}/project/p1/data").mock(
            return_value=httpx.Response(200, json={"tasks": [{"id": "t1", "title": "Task 1"}]})
        )
        data = await client.v1_get("/project/p1/data")
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["title"] == "Task 1"

    @pytest.mark.anyio
    async def test_list_completed(self, client: TickTickClient, mock_api: respx.MockRouter):
        mock_api.get(f"{V2_BASE}/project/all/completedInAll/?limit=50").mock(
            return_value=httpx.Response(200, json=[{"id": "t2", "title": "Done", "status": 2}])
        )
        result = await client.v2_get("/project/all/completedInAll/?limit=50")
        assert result[0]["status"] == 2

    @pytest.mark.anyio
    async def test_resolves_project_with_null_closed_state(self, client: TickTickClient):
        client.sync_projects = AsyncMock(
            return_value=[{"id": "p1", "name": "Work", "closed": None}]
        )

        assert await _resolve_project_id(client, "Work") == "p1"

    @pytest.mark.anyio
    async def test_exact_project_id_skips_project_sync(self, client: TickTickClient):
        client.sync_projects = AsyncMock()

        project_id = "5c6dca84e4b0117beaa3e4b4"

        assert await _resolve_project_id(client, project_id) == project_id
        client.sync_projects.assert_not_awaited()


class TestAddTask:
    @pytest.mark.anyio
    async def test_create_simple(self, client: TickTickClient, mock_api: respx.MockRouter):
        mock_api.post(f"{V1_BASE}/task").mock(
            return_value=httpx.Response(
                200, json={"id": "t1", "title": "Buy milk", "projectId": "inbox123"}
            )
        )
        result = await client.v1_post("/task", {"title": "Buy milk"})
        assert result["id"] == "t1"
        assert result["title"] == "Buy milk"

    @pytest.mark.anyio
    async def test_create_with_timed_reminder(self, client: TickTickClient):
        body = await _build_add_task_body(
            client,
            title="Call",
            due="2026-02-16T14:30",
            reminders=["30m", "TRIGGER:PT0S"],
            timezone="UTC",
        )

        assert body["dueDate"] == "2026-02-16T14:30:00.000+0000"
        assert body["isAllDay"] is False
        assert body["timeZone"] == "UTC"
        assert body["reminders"] == ["TRIGGER:-PT30M", "TRIGGER:PT0S"]

    @pytest.mark.anyio
    async def test_create_with_all_day_reminder(self, client: TickTickClient):
        body = await _build_add_task_body(
            client,
            title="Birthday",
            due="2026-02-16",
            reminders=["TRIGGER:P0DT9H0M0S"],
            timezone="Europe/Stockholm",
        )

        assert body["isAllDay"] is True
        assert body["timeZone"] == "Europe/Stockholm"
        assert body["reminders"] == ["TRIGGER:P0DT9H0M0S"]


class TestEditTask:
    @pytest.mark.anyio
    async def test_updates_regular_fields_through_batch_endpoint(
        self, client: TickTickClient, mock_api: respx.MockRouter
    ):
        mock_api.get(f"{V1_BASE}/project/p1/task/t1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "t1",
                    "projectId": "p1",
                    "title": "Old title",
                    "startDate": "2026-07-27T21:00:00.000+0000",
                    "repeatFlag": "RRULE:FREQ=DAILY;INTERVAL=14",
                },
            )
        )
        route = mock_api.post(f"{V2_BASE}/batch/task").mock(
            return_value=httpx.Response(200, json={"id2etag": {"t1": "new-etag"}})
        )

        result = await _edit_task_v2(
            client,
            "t1",
            "p1",
            {"taskId": "t1", "projectId": "p1", "title": "New title"},
            None,
            False,
        )

        assert result["title"] == "New title"
        assert result["repeatFlag"] == "RRULE:FREQ=DAILY;INTERVAL=14"
        payload = json.loads(route.calls.last.request.content)
        assert payload["update"][0]["title"] == "New title"

    @pytest.mark.anyio
    async def test_updates_repeat_first_date_with_task_date(
        self, client: TickTickClient, mock_api: respx.MockRouter
    ):
        mock_api.get(f"{V1_BASE}/project/p1/task/t1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "t1",
                    "projectId": "p1",
                    "title": "Task",
                    "startDate": "2026-07-27T21:00:00.000+0000",
                    "repeatFirstDate": "2026-07-27T21:00:00.000+0000",
                },
            )
        )
        mock_api.post(f"{V2_BASE}/batch/task").mock(return_value=httpx.Response(200, json={}))

        result = await _edit_task_v2(
            client,
            "t1",
            "p1",
            {
                "taskId": "t1",
                "projectId": "p1",
                "startDate": "2026-07-29T21:00:00.000+0000",
                "dueDate": None,
            },
            None,
            False,
        )

        assert result["repeatFirstDate"] == "2026-07-29T21:00:00.000+0000"

    @pytest.mark.anyio
    async def test_updates_repeat_through_batch_endpoint(
        self, client: TickTickClient, mock_api: respx.MockRouter
    ):
        mock_api.get(f"{V1_BASE}/project/p1/task/t1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "t1",
                    "projectId": "p1",
                    "title": "Change pillowcases",
                    "startDate": "2026-07-27T21:00:00.000+0000",
                    "repeatFlag": "RRULE:FREQ=DAILY;INTERVAL=9",
                    "repeatFrom": "1",
                },
            )
        )
        route = mock_api.post(f"{V2_BASE}/batch/task").mock(
            return_value=httpx.Response(200, json={"id2etag": {"t1": "new-etag"}})
        )

        result = await _edit_task_v2(
            client,
            "t1",
            "p1",
            {"taskId": "t1", "projectId": "p1"},
            "RRULE:FREQ=DAILY;INTERVAL=14",
            False,
        )

        assert result["repeatFlag"] == "RRULE:FREQ=DAILY;INTERVAL=14"
        assert result["repeatFirstDate"] == "2026-07-27T21:00:00.000+0000"
        payload = json.loads(route.calls.last.request.content)
        assert payload["update"][0]["id"] == "t1"
        assert payload["update"][0]["repeatFlag"] == "RRULE:FREQ=DAILY;INTERVAL=14"

    @pytest.mark.anyio
    async def test_clears_repeat_through_batch_endpoint(
        self, client: TickTickClient, mock_api: respx.MockRouter
    ):
        mock_api.get(f"{V1_BASE}/project/p1/task/t1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "t1",
                    "projectId": "p1",
                    "title": "Change pillowcases",
                    "startDate": "2026-07-27T21:00:00.000+0000",
                    "repeatFlag": "RRULE:FREQ=DAILY;INTERVAL=9",
                },
            )
        )
        mock_api.post(f"{V2_BASE}/batch/task").mock(return_value=httpx.Response(200, json={}))

        result = await _edit_task_v2(
            client,
            "t1",
            "p1",
            {"taskId": "t1", "projectId": "p1"},
            None,
            True,
        )

        assert result["repeatFlag"] is None
        assert result["repeatFirstDate"] == "2026-07-27T21:00:00.000+0000"

    def test_build_replace_reminders(self):
        updates = _build_edit_task_updates(
            task_id="t1",
            project_id="p1",
            reminders=["1h", "PT0S"],
        )

        assert updates["reminders"] == ["TRIGGER:-PT1H", "TRIGGER:PT0S"]

    def test_build_clear_reminders(self):
        updates = _build_edit_task_updates(
            task_id="t1",
            project_id="p1",
            clear_reminders=True,
        )

        assert updates["reminders"] == []

    def test_rejects_replace_and_clear_reminders(self):
        with pytest.raises(ToolError, match="Use either reminders or clear_reminders"):
            _build_edit_task_updates(
                task_id="t1",
                project_id="p1",
                reminders=["30m"],
                clear_reminders=True,
            )

    @pytest.mark.anyio
    async def test_unrelated_edit_preserves_reminders(
        self, client: TickTickClient, mock_api: respx.MockRouter
    ):
        mock_api.get(f"{V1_BASE}/project/p1/task/t1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "t1",
                    "projectId": "p1",
                    "title": "Old title",
                    "reminders": ["TRIGGER:-PT30M"],
                },
            )
        )
        route = mock_api.post(f"{V2_BASE}/batch/task").mock(
            return_value=httpx.Response(200, json={"id2etag": {"t1": "new-etag"}})
        )

        result = await _edit_task_v2(
            client,
            "t1",
            "p1",
            {"taskId": "t1", "projectId": "p1", "title": "New title"},
            None,
            False,
        )

        assert result["reminders"] == ["TRIGGER:-PT30M"]
        payload = json.loads(route.calls.last.request.content)
        assert payload["update"][0]["reminders"] == ["TRIGGER:-PT30M"]

    @pytest.mark.anyio
    async def test_replace_reminders_persists_through_batch(
        self, client: TickTickClient, mock_api: respx.MockRouter
    ):
        mock_api.get(f"{V1_BASE}/project/p1/task/t1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "t1",
                    "projectId": "p1",
                    "title": "Task",
                    "dueDate": "2026-07-27T21:00:00.000+0000",
                    "reminders": ["TRIGGER:-PT30M"],
                },
            )
        )
        route = mock_api.post(f"{V2_BASE}/batch/task").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await _edit_task_v2(
            client,
            "t1",
            "p1",
            {
                "taskId": "t1",
                "projectId": "p1",
                "reminders": ["TRIGGER:-PT1H", "TRIGGER:PT0S"],
            },
            None,
            False,
        )

        assert result["reminders"] == ["TRIGGER:-PT1H", "TRIGGER:PT0S"]
        payload = json.loads(route.calls.last.request.content)
        assert payload["update"][0]["reminders"] == ["TRIGGER:-PT1H", "TRIGGER:PT0S"]

    @pytest.mark.anyio
    async def test_clear_reminders_persists_through_batch(
        self, client: TickTickClient, mock_api: respx.MockRouter
    ):
        mock_api.get(f"{V1_BASE}/project/p1/task/t1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "t1",
                    "projectId": "p1",
                    "title": "Task",
                    "reminders": ["TRIGGER:-PT30M"],
                },
            )
        )
        route = mock_api.post(f"{V2_BASE}/batch/task").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await _edit_task_v2(
            client,
            "t1",
            "p1",
            {"taskId": "t1", "projectId": "p1", "reminders": []},
            None,
            False,
        )

        assert result["reminders"] == []
        payload = json.loads(route.calls.last.request.content)
        assert payload["update"][0]["reminders"] == []

    @pytest.mark.anyio
    async def test_recurring_edit_with_reminders(
        self, client: TickTickClient, mock_api: respx.MockRouter
    ):
        mock_api.get(f"{V1_BASE}/project/p1/task/t1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "t1",
                    "projectId": "p1",
                    "title": "Task",
                    "startDate": "2026-07-27T21:00:00.000+0000",
                    "repeatFlag": "RRULE:FREQ=DAILY;INTERVAL=1",
                    "reminders": ["TRIGGER:-PT30M"],
                },
            )
        )
        route = mock_api.post(f"{V2_BASE}/batch/task").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await _edit_task_v2(
            client,
            "t1",
            "p1",
            {"taskId": "t1", "projectId": "p1", "reminders": ["TRIGGER:PT0S"]},
            "RRULE:FREQ=WEEKLY;INTERVAL=1",
            False,
        )

        assert result["repeatFlag"] == "RRULE:FREQ=WEEKLY;INTERVAL=1"
        assert result["reminders"] == ["TRIGGER:PT0S"]
        payload = json.loads(route.calls.last.request.content)
        assert payload["update"][0]["repeatFirstDate"] == "2026-07-27T21:00:00.000+0000"

    @pytest.mark.anyio
    async def test_updates_multiple_tasks_through_one_batch_endpoint(
        self, client: TickTickClient, mock_api: respx.MockRouter
    ):
        mock_api.get(f"{V1_BASE}/project/p1/task/t1").mock(
            return_value=httpx.Response(
                200,
                json={"id": "t1", "projectId": "p1", "title": "Old 1"},
            )
        )
        mock_api.get(f"{V1_BASE}/project/p1/task/t2").mock(
            return_value=httpx.Response(
                200,
                json={"id": "t2", "projectId": "p1", "title": "Old 2"},
            )
        )
        route = mock_api.post(f"{V2_BASE}/batch/task").mock(
            return_value=httpx.Response(200, json={"id2etag": {"t1": "e1", "t2": "e2"}})
        )

        result = await _edit_tasks_v2(
            client,
            "p1",
            [
                {"task_id": "t1", "updates": {"taskId": "t1", "title": "New 1"}},
                {"task_id": "t2", "updates": {"taskId": "t2", "priority": 3}},
            ],
        )

        assert [task["id"] for task in result] == ["t1", "t2"]
        payload = json.loads(route.calls.last.request.content)
        assert [task["title"] for task in payload["update"]] == ["New 1", "Old 2"]
        assert payload["update"][1]["priority"] == 3
        assert len(route.calls) == 1


class TestCompleteTask:
    @pytest.mark.anyio
    async def test_complete(self, client: TickTickClient, mock_api: respx.MockRouter):
        mock_api.post(f"{V1_BASE}/project/p1/task/t1/complete").mock(
            return_value=httpx.Response(200)
        )
        resp = await client.v1_post_empty("/project/p1/task/t1/complete")
        assert resp.status_code == 200


class TestDeleteTask:
    @pytest.mark.anyio
    async def test_delete(self, client: TickTickClient, mock_api: respx.MockRouter):
        mock_api.delete(f"{V1_BASE}/project/p1/task/t1").mock(return_value=httpx.Response(200))
        resp = await client.v1_delete("/project/p1/task/t1")
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_delete_multiple(self, client: TickTickClient, mock_api: respx.MockRouter):
        route1 = mock_api.delete(f"{V1_BASE}/project/p1/task/t1").mock(
            return_value=httpx.Response(200)
        )
        route2 = mock_api.delete(f"{V1_BASE}/project/p1/task/t2").mock(
            return_value=httpx.Response(200)
        )

        await client.v1_delete("/project/p1/task/t1")
        await client.v1_delete("/project/p1/task/t2")

        assert len(route1.calls) == 1
        assert len(route2.calls) == 1


class TestMoveTask:
    @pytest.mark.anyio
    async def test_move(self, client: TickTickClient, mock_api: respx.MockRouter):
        mock_api.post(f"{V2_BASE}/batch/taskProject").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        result = await client.v2_post(
            "/batch/taskProject",
            [{"taskId": "t1", "fromProjectId": "p1", "toProjectId": "p2"}],
        )
        assert result["ok"] is True


class TestSetSubtask:
    @pytest.mark.anyio
    async def test_set_parent(self, client: TickTickClient, mock_api: respx.MockRouter):
        mock_api.post(f"{V2_BASE}/batch/taskParent").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        result = await client.v2_post(
            "/batch/taskParent",
            [{"taskId": "t2", "parentId": "t1", "projectId": "p1"}],
        )
        assert result["ok"] is True

    @pytest.mark.anyio
    async def test_set_multiple_parents(self, client: TickTickClient, mock_api: respx.MockRouter):
        route = mock_api.post(f"{V2_BASE}/batch/taskParent").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        result = await client.v2_post(
            "/batch/taskParent",
            [
                {"taskId": "t2", "parentId": "t1", "projectId": "p1"},
                {"taskId": "t3", "parentId": "t1", "projectId": "p1"},
            ],
        )

        assert result["ok"] is True
        payload = json.loads(route.calls.last.request.content)
        assert [item["taskId"] for item in payload] == ["t2", "t3"]


class TestListTrash:
    @pytest.mark.anyio
    async def test_trash(self, client: TickTickClient, mock_api: respx.MockRouter):
        mock_api.get(f"{V2_BASE}/project/all/trash/page").mock(
            return_value=httpx.Response(200, json={"tasks": [{"id": "t1", "title": "Trashed"}]})
        )
        data = await client.v2_get("/project/all/trash/page")
        assert len(data["tasks"]) == 1
