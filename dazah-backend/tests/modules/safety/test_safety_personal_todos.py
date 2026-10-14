from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.safety.models import Accident, EhsChange, HazardReport, SafetyCheck
from app.modules.safety.todos import PAGES, router
from app.platform.identity.data_scope import DepartmentScope
from app.platform.identity.models import Department
from tests.todo_helpers import make_todo_user, scoped_todo_client


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", list(PAGES))
async def test_safety_todos_filter_current_responsibility_scope_and_state(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    actor = await make_todo_user(db_session)
    other_actor = await make_todo_user(db_session)
    own_dept = f"授权安全部门{uuid4().hex[:10]}"
    expected = []
    for variant in ("own", "other-owner", "outside-scope", "finished", "deleted"):
        personal = variant != "other-owner"
        terminal = variant == "finished"
        department = "范围外" if variant == "outside-scope" else own_dept
        number = f"S-{uuid4().hex[:15]}"
        if kind == "hazards":
            record = HazardReport(
                hazard_no=number,
                description="隐患整改",
                hazard_type="人的不安全行为",
                department=department,
                discovered_at=datetime.now(UTC),
                rectification_responsible_person=actor.id
                if personal
                else other_actor.id,
                rectification_responsible_person_name=actor.name,
                rectification_status="closed" if terminal else "pending",
                status="closed" if terminal else "open",
            )
        elif kind == "accidents":
            record = Accident(
                accident_no=number,
                accident_type="other",
                happened_at=datetime.now(UTC),
                reported_at=datetime.now(UTC),
                description="待完成措施",
                department=department,
                corrective_action_responsible=actor.name
                if personal
                else other_actor.name,
                corrective_action_status="completed" if terminal else "pending",
            )
        elif kind == "checks":
            record = SafetyCheck(
                check_no=number,
                check_date=datetime.now(UTC),
                department=department,
                inspector=actor.id if personal else other_actor.id,
                inspector_name=actor.name,
                status="submitted" if terminal else "draft",
            )
        else:
            record = EhsChange(
                change_no=number,
                title="EHS实施",
                change_type="equipment_facility",
                department=department,
                status="closed" if terminal else "in_progress",
                action_items=[
                    {
                        "task": "当前行动项",
                        "owner": actor.name if personal else other_actor.name,
                        "due_date": "invalid-date",
                        "status": "pending",
                    },
                    {
                        "task": "其他人的行动项",
                        "owner": other_actor.name,
                        "status": "pending",
                    },
                    {
                        "task": "已完成行动项",
                        "owner": actor.name,
                        "status": "completed",
                    },
                ],
            )
        record.is_deleted = variant == "deleted"
        db_session.add(record)
        await db_session.flush()
        if variant == "own":
            expected.append(
                f"{record.id}:1" if kind == "ehs-actions" else str(record.id)
            )
    async with scoped_todo_client(
        db_session,
        actor,
        router,
        "safety",
        PAGES[kind],
        DepartmentScope(department_names={own_dept}),
        monkeypatch,
    ) as client:
        response = await client.get(f"/api/v1/safety/my-todos?kind={kind}")
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 1
        assert [item["id"] for item in response.json()["items"]] == expected
        if kind == "ehs-actions":
            assert "其他人的行动项" not in response.text
            assert "已完成行动项" not in response.text


@pytest.mark.asyncio
async def test_hazard_verification_requires_current_stage_and_approval_permission(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = await make_todo_user(db_session)
    actor.feishu_user_id = f"user-{uuid4().hex}"
    department = Department(
        name=f"安全复核部门{uuid4().hex[:10]}",
        feishu_department_id=f"d-{uuid4().hex}",
        leader_user_id=actor.feishu_user_id,
    )
    db_session.add(department)
    expected = []
    for stage in ("first", "last", "wrong-stage", "finished"):
        hazard = HazardReport(
            hazard_no=f"H-{uuid4().hex[:15]}",
            description="隐患复核",
            hazard_type="人的不安全行为",
            department=department.name,
            discovered_at=datetime.now(UTC),
            discovered_by=actor.id,
            rectification_status="replied"
            if stage == "first"
            else "level2_approved"
            if stage in {"last", "finished"}
            else "pending",
            verify_level_1_status="pending" if stage == "first" else "approved",
            verify_level_3_status="approved" if stage == "finished" else "pending",
        )
        db_session.add(hazard)
        await db_session.flush()
        if stage in {"first", "last"}:
            expected.append(str(hazard.id))
    for approve in (False, True):
        async with scoped_todo_client(
            db_session,
            actor,
            router,
            "safety",
            PAGES["hazards"],
            DepartmentScope(department_names={department.name}),
            monkeypatch,
            approve=approve,
        ) as client:
            result = await client.get("/api/v1/safety/my-todos?kind=hazards")
            assert result.status_code == 200, result.text
            assert {item["id"] for item in result.json()["items"]} == (
                set(expected) if approve else set()
            )


@pytest.mark.asyncio
async def test_safety_todo_rejects_cross_page_and_view_only(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = await make_todo_user(db_session)
    async with scoped_todo_client(
        db_session,
        actor,
        router,
        "safety",
        PAGES["checks"],
        DepartmentScope(is_all=True),
        monkeypatch,
        operate=False,
    ) as client:
        assert (
            await client.get("/api/v1/safety/my-todos?kind=checks")
        ).status_code == 403
        assert (
            await client.get("/api/v1/safety/my-todos?kind=hazards")
        ).status_code == 403
