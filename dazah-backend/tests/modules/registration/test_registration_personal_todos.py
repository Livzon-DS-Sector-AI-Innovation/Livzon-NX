import pytest
from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.registration.api.validation_audit import router as audit_router
from app.modules.registration.models.validation_audit import ValidationAuditTask
from app.modules.registration.todos import PAGES, router
from app.platform.identity.data_scope import DepartmentScope
from tests.todo_helpers import make_todo_user, scoped_todo_client


@pytest.mark.asyncio
async def test_registration_todos_use_creator_and_actionable_status(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = await make_todo_user(db_session)
    other = await make_todo_user(db_session)
    expected = []
    for variant in (
        "draft",
        "uploaded",
        "failed",
        "parsing",
        "auditing",
        "completed",
        "other",
        "unknown",
        "deleted",
    ):
        task = ValidationAuditTask(
            task_name=variant,
            product_name="品种",
            method_name="方法",
            source_company="公司",
            audit_mode="protocol",
            status=variant
            if variant
            in {"draft", "uploaded", "failed", "parsing", "auditing", "completed"}
            else "draft",
            created_by=other.id
            if variant == "other"
            else None
            if variant == "unknown"
            else actor.id,
            is_deleted=variant == "deleted",
        )
        db_session.add(task)
        await db_session.flush()
        if variant in {"draft", "uploaded", "failed"}:
            expected.append(str(task.id))
    key = PAGES["validation-audits"]
    async with scoped_todo_client(
        db_session,
        actor,
        router,
        "registration",
        key,
        DepartmentScope(is_all=True),
        monkeypatch,
    ) as client:
        response = await client.get(
            "/api/v1/registration/my-todos?kind=validation-audits"
        )
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 3
        assert {item["id"] for item in response.json()["items"]} == set(expected)
        assert (
            await client.get(
                "/api/v1/registration/my-todos?kind=validation-audits&page_size=1000"
            )
        ).status_code == 422
        assert (
            await client.get(
                "/api/v1/registration/my-todos?kind=validation-audits",
                headers={"X-Dazah-Page-Key": "registration:knowledge"},
            )
        ).status_code == 403
    for operate, scope in (
        (False, DepartmentScope(is_all=True)),
        (True, DepartmentScope(department_names={"部门"})),
    ):
        async with scoped_todo_client(
            db_session,
            actor,
            router,
            "registration",
            key,
            scope,
            monkeypatch,
            operate=operate,
        ) as client:
            response = await client.get(
                "/api/v1/registration/my-todos?kind=validation-audits"
            )
            assert response.status_code == (200 if operate else 403)
            if operate:
                assert response.json()["total"] == 0


@pytest.mark.asyncio
async def test_new_audit_task_records_authenticated_creator(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = await make_todo_user(db_session)
    combined = APIRouter()
    combined.include_router(router)
    combined.include_router(audit_router, prefix="/validation-audit")
    async with scoped_todo_client(
        db_session,
        actor,
        combined,
        "registration",
        PAGES["validation-audits"],
        DepartmentScope(is_all=True),
        monkeypatch,
    ) as client:
        response = await client.post(
            "/api/v1/registration/validation-audit/tasks",
            json={
                "task_name": "本人新建任务",
                "product_name": "品种",
                "method_name": "方法",
                "source_company": "公司",
                "audit_mode": "protocol",
            },
        )
        assert response.status_code == 200, response.text
        tasks = await client.get("/api/v1/registration/my-todos?kind=validation-audits")
        assert tasks.status_code == 200
        assert tasks.json()["total"] == 1
        assert tasks.json()["items"][0]["id"] == response.json()["data"]["id"]
