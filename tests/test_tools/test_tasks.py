from __future__ import annotations

import json

import httpx
import pytest
import respx

from ticktick_mcp.client import V1_BASE, V2_BASE, TickTickClient
from ticktick_mcp.tools.tasks import _edit_task_v2


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


class TestListTrash:
    @pytest.mark.anyio
    async def test_trash(self, client: TickTickClient, mock_api: respx.MockRouter):
        mock_api.get(f"{V2_BASE}/project/all/trash/page").mock(
            return_value=httpx.Response(200, json={"tasks": [{"id": "t1", "title": "Trashed"}]})
        )
        data = await client.v2_get("/project/all/trash/page")
        assert len(data["tasks"]) == 1
