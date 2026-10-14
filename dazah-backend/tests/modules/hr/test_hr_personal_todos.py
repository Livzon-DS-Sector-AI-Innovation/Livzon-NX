from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.models import PlanTrackingRecord, PositionTransferRecord
from app.modules.hr.todos import PAGES, router
from app.platform.identity.data_scope import DepartmentScope
from app.platform.identity.models import User
from tests.todo_helpers import make_todo_user, scoped_todo_client


@pytest.mark.asyncio
async def test_transfer_todos_enforce_approval_scope_current_step_and_stable_id(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = await make_todo_user(db_session)
    actor.feishu_open_id = f"todo-{uuid4().hex}"
    department = f"授权部门{uuid4().hex}"
    expected = []
    for variant in (
        "own-id",
        "own-name",
        "wrong-id",
        "outside",
        "done",
        "deleted",
        "next-step",
    ):
        step = {"signer": actor.name, "signer_open_id": actor.feishu_open_id}
        if variant == "own-name":
            step["signer_open_id"] = ""
        if variant in {"wrong-id", "next-step"}:
            step["signer_open_id"] = "another-id"
        record = PositionTransferRecord(
            employee_name=variant,
            effective_date=date(2026, 10, 13),
            department_before=department if variant != "outside" else "范围外",
            apply_department="其他部门",
            approval_status="已通过" if variant == "done" else "待审批",
            is_deleted=variant == "deleted",
            approval_flow={
                "current_step": 0,
                "steps": [step, {"signer_open_id": actor.feishu_open_id}],
            },
        )
        db_session.add(record)
        await db_session.flush()
        if variant.startswith("own"):
            expected.append(str(record.id))
    for operate, approve in ((False, True), (True, False), (True, True)):
        async with scoped_todo_client(
            db_session,
            actor,
            router,
            "hr",
            PAGES["position-transfer"],
            DepartmentScope(department_names={department}),
            monkeypatch,
            operate=operate,
            approve=approve,
        ) as client:
            response = await client.get("/api/v1/hr/my-todos?kind=position-transfer")
            if not operate or not approve:
                assert response.status_code == 403
            else:
                assert response.status_code == 200, response.text
                assert response.json()["total"] == 2
                assert {item["id"] for item in response.json()["items"]} == set(
                    expected
                )
                db_session.add(User(name=actor.name, status="inactive"))
                await db_session.flush()
                response = await client.get(
                    "/api/v1/hr/my-todos?kind=position-transfer"
                )
                assert response.json()["total"] == 1
                assert response.json()["items"][0]["id"] == expected[0]


@pytest.mark.asyncio
async def test_hr_tasks_are_personal_scoped_live_and_paginated(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await make_todo_user(db_session)
    department = f"授权部门{uuid4().hex}"
    expected = []
    for variant in ("own", "own2", "other", "outside", "company", "done", "deleted"):
        record = PlanTrackingRecord(
            training_content=variant,
            tracker=user.name if variant != "other" else "别人",
            department=department
            if variant not in {"outside", "company"}
            else "外部门"
            if variant == "outside"
            else None,
            is_completed=variant == "done",
            is_deleted=variant == "deleted",
        )
        db_session.add(record)
        await db_session.flush()
        if variant.startswith("own"):
            expected.append(str(record.id))
    async with scoped_todo_client(
        db_session,
        user,
        router,
        "hr",
        PAGES["plan-tracking"],
        DepartmentScope(department_names={department}),
        monkeypatch,
    ) as client:
        response = await client.get(
            "/api/v1/hr/my-todos?kind=plan-tracking&page_size=1"
        )
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 2
        second = await client.get(
            "/api/v1/hr/my-todos?kind=plan-tracking&page_size=1&page=2"
        )
        assert second.status_code == 200
        assert {
            response.json()["items"][0]["id"],
            second.json()["items"][0]["id"],
        } == set(expected)
        wrong = await client.get(
            "/api/v1/hr/my-todos?kind=plan-tracking",
            headers={"X-Dazah-Page-Key": "hr:training:annual-plan"},
        )
        assert wrong.status_code == 403
        db_session.add(User(name=user.name, status="inactive", is_deleted=True))
        await db_session.flush()
        assert (await client.get("/api/v1/hr/my-todos?kind=plan-tracking")).json()[
            "total"
        ] == 0
    async with scoped_todo_client(
        db_session,
        user,
        router,
        "hr",
        PAGES["plan-tracking"],
        DepartmentScope(is_all=True),
        monkeypatch,
        operate=False,
    ) as client:
        assert (
            await client.get("/api/v1/hr/my-todos?kind=plan-tracking")
        ).status_code == 403
