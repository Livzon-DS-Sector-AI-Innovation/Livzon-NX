from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models import (
    CAPA,
    CapaPlanTrack,
    ChangeActionPlan,
    ChangeControl,
    Deviation,
)
from app.modules.quality.todos import PAGES, router
from app.platform.identity.data_scope import DepartmentScope
from app.platform.identity.models import User
from tests.todo_helpers import make_todo_user, scoped_todo_client


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", list(PAGES))
async def test_quality_tasks_filter_owner_department_terminal_and_deleted(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    actor = await make_todo_user(db_session)
    suffix = uuid4().hex[:12]
    own_dept = f"授权质量部门{suffix}"
    expected = []
    for variant in ("own", "other-owner", "outside-scope", "finished", "deleted"):
        personal = variant != "other-owner"
        department = "范围外" if variant == "outside-scope" else own_dept
        code = f"TODO-{suffix}-{variant}"
        terminal = variant == "finished"
        if kind == "deviations":
            record = Deviation(
                deviation_code=code,
                title="偏差调查",
                handler=actor.name if personal else "其他人",
                department=department,
                status="closed" if terminal else "pending_investigation",
            )
        elif kind == "capas":
            record = CAPA(
                capa_code=code,
                title="CAPA执行",
                executors=[actor.name if personal else "其他人"],
                department=department,
                status="closed" if terminal else "executing",
                expected_completion_date=datetime(
                    2026, 10, 12, 0, 30, tzinfo=timezone(timedelta(hours=8))
                ),
            )
        elif kind == "capa-plans":
            parent = CAPA(capa_code=code, department=department, status="executing")
            db_session.add(parent)
            await db_session.flush()
            record = CapaPlanTrack(
                capa_id=parent.id,
                capa_code=code,
                plan_content="待完成计划",
                owner_name=actor.name if personal else "其他人",
                owner_confirmed=terminal,
                progress="已完成" if terminal else "执行中",
                due_date=date(2026, 10, 12),
            )
        else:
            parent = ChangeControl(change_code=code, applicant_department=department)
            db_session.add(parent)
            await db_session.flush()
            record = ChangeActionPlan(
                change_code=code,
                project_name="变更计划",
                owner_user_id=str(actor.id) if personal else str(uuid4()),
                owner_name=actor.name,
                status="已完成" if terminal else "进行中",
                deadline_date=date(2026, 10, 10),
                delayed_deadline_date=date(2026, 10, 13),
            )
        record.is_deleted = variant == "deleted"
        db_session.add(record)
        await db_session.flush()
        if variant == "own":
            expected.append(str(record.id))
    async with scoped_todo_client(
        db_session,
        actor,
        router,
        "quality",
        PAGES[kind],
        DepartmentScope(department_names={own_dept}),
        monkeypatch,
    ) as client:
        result = await client.get(
            f"/api/v1/quality/my-todos?kind={kind}&user_id={uuid4()}"
        )
        assert result.status_code == 200, result.text
        data = result.json()
        assert data["total"] == 1
        assert [item["id"] for item in data["items"]] == expected
        if kind == "capas":
            assert data["items"][0]["due_date"] == "2026-10-12"
        if kind == "change-plans":
            assert data["items"][0]["due_date"] == "2026-10-13"


@pytest.mark.asyncio
async def test_completed_plan_waits_for_correct_confirmation_and_namesakes_are_excluded(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = await make_todo_user(db_session)
    parent = CAPA(capa_code=f"TODO-{uuid4()}", department="质量部", status="executing")
    db_session.add(parent)
    await db_session.flush()
    plan = CapaPlanTrack(
        capa_id=parent.id,
        capa_code=parent.capa_code,
        plan_content="已执行待确认",
        owner_name="其他责任人",
        department_head=actor.name,
        owner_confirmed=True,
        department_head_confirmed=False,
        progress="已完成",
    )
    db_session.add(plan)
    await db_session.flush()
    for approve in (False, True):
        async with scoped_todo_client(
            db_session,
            actor,
            router,
            "quality",
            PAGES["capa-plans"],
            DepartmentScope(is_all=True),
            monkeypatch,
            approve=approve,
        ) as client:
            result = await client.get("/api/v1/quality/my-todos?kind=capa-plans")
            assert result.status_code == 200
            assert result.json()["total"] == int(approve)
    db_session.add(User(id=uuid4(), name=actor.name, role="user", status="active"))
    await db_session.flush()
    async with scoped_todo_client(
        db_session,
        actor,
        router,
        "quality",
        PAGES["capa-plans"],
        DepartmentScope(is_all=True),
        monkeypatch,
        approve=True,
    ) as client:
        assert (await client.get("/api/v1/quality/my-todos?kind=capa-plans")).json()[
            "total"
        ] == 0


@pytest.mark.asyncio
async def test_quality_todo_rejects_readonly_cross_page_and_invalid_queries(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = await make_todo_user(db_session)
    for operate in (False, True):
        async with scoped_todo_client(
            db_session,
            actor,
            router,
            "quality",
            PAGES["deviations"],
            DepartmentScope(is_all=True),
            monkeypatch,
            operate=operate,
        ) as client:
            assert (
                await client.get("/api/v1/quality/my-todos?kind=deviations")
            ).status_code == (200 if operate else 403)
            assert (
                await client.get("/api/v1/quality/my-todos?kind=capas")
            ).status_code == 403
            assert (
                await client.get(
                    "/api/v1/quality/my-todos?kind=deviations&page_size=1000"
                )
            ).status_code == 422
            assert (
                await client.get("/api/v1/quality/my-todos?kind=unknown")
            ).status_code == 422
