from __future__ import annotations

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.change_control import ChangeControl


@pytest.fixture(autouse=True)
async def _clean_change_action_plans(
    db_session: AsyncSession,
) -> None:
    await db_session.execute(text("CREATE SCHEMA IF NOT EXISTS quality"))
    await db_session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS quality.quality_change_controls (
                serial_number VARCHAR(50),
                change_code VARCHAR(100) NOT NULL UNIQUE,
                applicant_department VARCHAR(100),
                change_object VARCHAR(255),
                change_content TEXT,
                impact_assessment TEXT,
                change_level VARCHAR(50),
                application_date DATE,
                planned_approval_date DATE,
                execution_date DATE,
                closure_date DATE,
                id UUID PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                created_by UUID NULL,
                updated_by UUID NULL,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE
            )
            """
        )
    )
    await db_session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS quality.quality_change_action_plans (
                id UUID PRIMARY KEY,
                change_id UUID NULL,
                change_code VARCHAR(100) NOT NULL,
                project_name VARCHAR(255) NOT NULL,
                related_work TEXT NULL,
                owner_name VARCHAR(100) NULL,
                owner_user_id VARCHAR(100) NULL,
                director_name VARCHAR(100) NULL,
                director_user_id VARCHAR(100) NULL,
                deadline_date DATE NULL,
                status VARCHAR(100) NULL,
                delay_flag VARCHAR(100) NULL,
                delayed_deadline_date DATE NULL,
                feishu_record_id VARCHAR(100) NULL,
                sync_status VARCHAR(20) NOT NULL DEFAULT 'pending',
                sync_error TEXT NULL,
                last_synced_at TIMESTAMPTZ NULL,
                reminder_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                reminder_status VARCHAR(20) NOT NULL DEFAULT 'pending',
                last_reminded_at TIMESTAMPTZ NULL,
                reminder_confirmed_at TIMESTAMPTZ NULL,
                reminder_confirmed_by VARCHAR(100) NULL,
                reminder_message_id VARCHAR(100) NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                created_by UUID NULL,
                updated_by UUID NULL,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE
            )
            """
        )
    )
    await db_session.execute(
        text(
            """
            ALTER TABLE quality.quality_change_action_plans
            ADD COLUMN IF NOT EXISTS reminder_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            ADD COLUMN IF NOT EXISTS reminder_status VARCHAR(20) NOT NULL DEFAULT 'pending',
            ADD COLUMN IF NOT EXISTS last_reminded_at TIMESTAMPTZ NULL,
            ADD COLUMN IF NOT EXISTS reminder_confirmed_at TIMESTAMPTZ NULL,
            ADD COLUMN IF NOT EXISTS reminder_confirmed_by VARCHAR(100) NULL,
            ADD COLUMN IF NOT EXISTS reminder_message_id VARCHAR(100) NULL
            """
        )
    )
    await db_session.execute(
        text("DELETE FROM quality.quality_change_action_plans")
    )
    await db_session.execute(ChangeControl.__table__.delete())
    await db_session.commit()
    yield
    await db_session.execute(text("DELETE FROM quality.quality_change_action_plans"))
    await db_session.execute(
        ChangeControl.__table__.delete()
    )
    await db_session.commit()


@pytest.mark.anyio
async def test_change_action_plan_api_roundtrip(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_upsert(self, db, plan, *, include_users=True):  # noqa: ANN001
        return f"rec_{plan.id.hex[:8]}"

    monkeypatch.setattr(
        "app.modules.quality.service.change_action_plan.ChangeActionPlanFeishuSync.upsert_record",
        _fake_upsert,
    )

    change = ChangeControl(
        id=uuid.uuid4(),
        change_code="BG-PLAN-002",
        applicant_department="工程部",
    )
    db_session.add(change)
    await db_session.commit()

    create_response = await client.post(
        "/api/v1/quality/change-action-plans",
        json={
            "change_id": str(change.id),
            "change_code": "BG-PLAN-002",
            "project_name": "验证报告修订",
            "related_work": "补充偏差影响评估",
            "owner_name": "李四",
            "status": "未启动",
        },
    )
    assert create_response.status_code == 200
    plan_id = create_response.json()["data"]["id"]
    assert create_response.json()["data"]["sync_status"] == "synced"
    assert create_response.json()["data"]["reminder_status"] == "pending"

    list_response = await client.get(
        "/api/v1/quality/change-action-plans",
        params={"change_code": "BG-PLAN-002"},
    )
    assert list_response.status_code == 200
    assert list_response.json()["meta"]["total"] == 1

    detail_response = await client.get(
        f"/api/v1/quality/changes/{change.id}/action-plans"
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["data"][0]["id"] == plan_id

    update_response = await client.put(
        f"/api/v1/quality/change-action-plans/{plan_id}",
        json={
            "status": "推进中",
            "deadline_date": date(2026, 7, 10).isoformat(),
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"]["status"] == "推进中"


@pytest.mark.anyio
async def test_change_action_plan_sync_failure_marks_failed(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise(self, db, plan, *, include_users=True):  # noqa: ANN001
        raise RuntimeError("feishu unavailable")

    monkeypatch.setattr(
        "app.modules.quality.service.change_action_plan.ChangeActionPlanFeishuSync.upsert_record",
        _raise,
    )

    response = await client.post(
        "/api/v1/quality/change-action-plans",
        json={
            "change_code": "BG-PLAN-003",
            "project_name": "清洁验证",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["sync_status"] == "failed"
    assert "feishu unavailable" in response.json()["data"]["sync_error"]


@pytest.mark.anyio
async def test_change_action_plan_sync_retries_without_user_fields(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[bool] = []

    async def _fake_upsert(db, plan, *, include_users=True):  # noqa: ANN001
        calls.append(include_users)
        if include_users:
            raise RuntimeError(
                "Feishu API error: code=1254066, msg=UserFieldConvFail, field=总负责人"
            )
        return "rec_retry_ok"

    monkeypatch.setattr(
        "app.modules.quality.service.change_action_plan.feishu_sync.upsert_record",
        _fake_upsert,
    )

    response = await client.post(
        "/api/v1/quality/change-action-plans",
        json={
            "change_code": "BG-PLAN-003-RETRY",
            "project_name": "同步重试测试",
            "owner_name": "张起智",
            "owner_user_id": "ou_wrong_app_id",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["sync_status"] == "synced"
    assert response.json()["data"]["feishu_record_id"] == "rec_retry_ok"
    assert response.json()["data"]["sync_error"] is None
    assert calls == [True, False]


@pytest.mark.anyio
async def test_change_action_plan_person_options_search_returns_open_ids(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_get_all_users():  # noqa: ANN001
        return [
            {
                "name": "张起智",
                "open_id": "ou_owner_001",
                "user_id": "u_owner_001",
                "mobile": "13927666434",
                "email": "zhang@example.com",
                "job_title": "质量经理",
            },
            {
                "name": "李四",
                "open_id": "ou_owner_002",
                "user_id": "u_owner_002",
                "mobile": "13800000000",
                "email": "li@example.com",
                "job_title": "主任",
            },
        ]

    monkeypatch.setattr(
        "app.modules.quality.service.change_action_plan.get_all_users",
        _fake_get_all_users,
    )

    response = await client.get(
        "/api/v1/quality/change-action-plans/person-options",
        params={"keyword": "张起", "limit": 10},
    )

    assert response.status_code == 200
    assert response.json()["data"] == [
        {
            "open_id": "ou_owner_001",
            "name": "张起智",
            "user_id": "u_owner_001",
            "mobile": "13927666434",
            "email": "zhang@example.com",
            "job_title": "质量经理",
        }
    ]


@pytest.mark.anyio
async def test_change_action_plan_update_rejects_person_field_edits_for_existing_plan(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_upsert(plan, include_users=True):  # noqa: ANN001
        return "rec_existing_plan"

    monkeypatch.setattr(
        "app.modules.quality.service.change_action_plan.feishu_sync.upsert_record",
        _fake_upsert,
    )

    create_response = await client.post(
        "/api/v1/quality/change-action-plans",
        json={
            "change_code": "BG-FEISHU-SOURCE-001",
            "project_name": "人员来源锁定测试",
            "owner_name": "张起智",
            "owner_user_id": "ou_owner_001",
        },
    )
    assert create_response.status_code == 200
    plan_id = create_response.json()["data"]["id"]

    update_response = await client.put(
        f"/api/v1/quality/change-action-plans/{plan_id}",
        json={"owner_name": "李四"},
    )

    assert update_response.status_code == 400
    assert "请在飞书多维表中维护" in update_response.text


@pytest.mark.anyio
async def test_change_action_plan_update_allows_non_person_fields(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_upsert(plan, include_users=True):  # noqa: ANN001
        return "rec_non_person_update"

    monkeypatch.setattr(
        "app.modules.quality.service.change_action_plan.feishu_sync.upsert_record",
        _fake_upsert,
    )

    create_response = await client.post(
        "/api/v1/quality/change-action-plans",
        json={
            "change_code": "BG-FEISHU-SOURCE-002",
            "project_name": "非人员字段更新测试",
        },
    )
    assert create_response.status_code == 200
    plan_id = create_response.json()["data"]["id"]

    update_response = await client.put(
        f"/api/v1/quality/change-action-plans/{plan_id}",
        json={
            "status": "推进中",
            "deadline_date": date(2026, 7, 20).isoformat(),
        },
    )

    assert update_response.status_code == 200
    assert update_response.json()["data"]["status"] == "推进中"


@pytest.mark.anyio
async def test_sync_from_feishu_overwrites_owner_fields_for_existing_plan(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_upsert(_db, plan, include_users=True):  # noqa: ANN001
        return "rec_sync_back_001"

    async def _fake_search_records(_db, change_code=None):  # noqa: ANN001
        return [
            {
                "record_id": "rec_sync_back_001",
                "fields": {
                    "变更控制号": "BG-FEISHU-SOURCE-003",
                    "项目名称": "飞书回写负责人测试",
                    "涉及工作": "更新负责人与总监",
                    "总负责人": [{"name": "张起智", "id": "ou_new_owner"}],
                    "部门总监": [{"name": "王经理", "id": "ou_new_director"}],
                    "状态": "推进中",
                },
            }
        ]

    monkeypatch.setattr(
        "app.modules.quality.service.change_action_plan.feishu_sync.upsert_record",
        _fake_upsert,
    )
    monkeypatch.setattr(
        "app.modules.quality.service.change_action_plan.feishu_sync.search_records",
        _fake_search_records,
    )

    create_response = await client.post(
        "/api/v1/quality/change-action-plans",
        json={
            "change_code": "BG-FEISHU-SOURCE-003",
            "project_name": "飞书回写负责人测试",
            "related_work": "更新负责人与总监",
            "owner_name": "旧负责人",
            "owner_user_id": "ou_old_owner",
        },
    )
    assert create_response.status_code == 200

    sync_response = await client.post("/api/v1/quality/change-action-plans/sync-from-feishu")
    assert sync_response.status_code == 200
    assert sync_response.json()["data"]["synced"] == 1

    list_response = await client.get(
        "/api/v1/quality/change-action-plans",
        params={"change_code": "BG-FEISHU-SOURCE-003"},
    )
    assert list_response.status_code == 200
    item = list_response.json()["data"][0]
    assert item["owner_name"] == "张起智"
    assert item["owner_user_id"] == "ou_new_owner"
    assert item["director_name"] == "王经理"
    assert item["director_user_id"] == "ou_new_director"


@pytest.mark.anyio
async def test_change_action_plan_reminder_api_flow(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_send(plan):  # noqa: ANN001
        return "om_reminder_001"

    async def _fake_patch(plan):  # noqa: ANN001
        return None

    monkeypatch.setattr(
        "app.modules.quality.service.change_action_plan._send_reminder_card",
        _fake_send,
    )
    monkeypatch.setattr(
        "app.modules.quality.service.change_action_plan._patch_confirmation_card",
        _fake_patch,
    )

    create_response = await client.post(
        "/api/v1/quality/change-action-plans",
        json={
            "change_code": "BG-PLAN-004",
            "project_name": "标签模板修订",
            "owner_name": "王五",
            "owner_user_id": "ou_test_owner",
            "deadline_date": date(2026, 7, 3).isoformat(),
        },
    )
    assert create_response.status_code == 200
    plan_id = create_response.json()["data"]["id"]

    remind_response = await client.post(
        f"/api/v1/quality/change-action-plans/{plan_id}/reminders/send"
    )
    assert remind_response.status_code == 200
    assert remind_response.json()["data"]["reminder_status"] == "reminded"
    assert remind_response.json()["data"]["reminder_message_id"] == "om_reminder_001"

    confirm_response = await client.post(
        f"/api/v1/quality/change-action-plans/{plan_id}/reminders/confirm",
        params={"confirmed_by": "飞书按钮确认"},
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["data"]["success"] is True
    assert confirm_response.json()["data"]["reminder_status"] == "confirmed"
    assert confirm_response.json()["data"]["reminder_confirmed_by"] == "飞书按钮确认"
