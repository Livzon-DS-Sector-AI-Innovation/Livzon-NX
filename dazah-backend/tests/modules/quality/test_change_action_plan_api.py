from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality import repository
from app.modules.quality.models.change_control import ChangeControl


@pytest.fixture(autouse=True)
async def _clean_change_action_plans(
    db_session: AsyncSession,
) -> AsyncIterator[Any]:
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
                owner_avatar_url VARCHAR(512) NULL,
                director_name VARCHAR(100) NULL,
                director_user_id VARCHAR(100) NULL,
                director_avatar_url VARCHAR(512) NULL,
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
            ADD COLUMN IF NOT EXISTS reminder_status VARCHAR(20) NOT NULL DEFAULT
            'pending',
            ADD COLUMN IF NOT EXISTS last_reminded_at TIMESTAMPTZ NULL,
            ADD COLUMN IF NOT EXISTS reminder_confirmed_at TIMESTAMPTZ NULL,
            ADD COLUMN IF NOT EXISTS reminder_confirmed_by VARCHAR(100) NULL,
            ADD COLUMN IF NOT EXISTS reminder_message_id VARCHAR(100) NULL,
            ADD COLUMN IF NOT EXISTS owner_avatar_url VARCHAR(512) NULL,
            ADD COLUMN IF NOT EXISTS director_avatar_url VARCHAR(512) NULL
            """
        )
    )
    await db_session.execute(text("DELETE FROM quality.quality_change_action_plans"))
    await db_session.execute(ChangeControl.__table__.delete())  # type: ignore[attr-defined]
    await db_session.commit()
    yield
    await db_session.execute(text("DELETE FROM quality.quality_change_action_plans"))
    await db_session.execute(
        ChangeControl.__table__.delete()  # type: ignore[attr-defined]
    )
    await db_session.commit()


@pytest.mark.anyio
async def test_change_action_plan_api_roundtrip(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_upsert(
        self: Any, db: Any, plan: Any, *, include_users: Any = True
    ) -> Any:  # noqa: ANN001
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
    async def _raise(
        self: Any, db: Any, plan: Any, *, include_users: Any = True
    ) -> Any:  # noqa: ANN001
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

    async def _fake_upsert(db: Any, plan: Any, *, include_users: Any = True) -> Any:  # noqa: ANN001
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
    async def _fake_get_all_users() -> Any:  # noqa: ANN001
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
async def test_change_action_plan_person_options_matches_pinyin_en_name(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_get_all_users() -> Any:  # noqa: ANN001
        return [
            {
                "name": "甄宁宁",
                "en_name": "ZhenNingNing",
                "open_id": "ou_pinyin_001",
                "user_id": "u_pinyin_001",
                "mobile": "",
                "email": "",
                "job_title": "质量专员",
            },
            {
                "name": "陈平",
                "en_name": "ChenPing",
                "open_id": "ou_pinyin_002",
                "user_id": "u_pinyin_002",
                "mobile": "",
                "email": "",
                "job_title": "",
            },
        ]

    monkeypatch.setattr(
        "app.modules.quality.service.change_action_plan.get_all_users",
        _fake_get_all_users,
    )

    response = await client.get(
        "/api/v1/quality/change-action-plans/person-options",
        params={"keyword": "zhen", "limit": 10},
    )

    assert response.status_code == 200
    assert [item["open_id"] for item in response.json()["data"]] == [
        "ou_pinyin_001"
    ]


@pytest.mark.anyio
async def test_change_action_plan_update_rejects_person_field_edits_for_existing_plan(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_upsert(plan: Any, include_users: Any = True) -> Any:  # noqa: ANN001
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
    async def _fake_upsert(plan: Any, include_users: Any = True) -> Any:  # noqa: ANN001
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
    async def _fake_upsert(_db: Any, plan: Any, include_users: Any = True) -> Any:  # noqa: ANN001
        return "rec_sync_back_001"

    async def _fake_search_records(_db: Any, change_code: Any = None) -> Any:  # noqa: ANN001
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

    sync_response = await client.post(
        "/api/v1/quality/change-action-plans/sync-from-feishu"
    )
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
async def test_sync_from_feishu_creates_plan_from_production_shaped_record(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空表全量拉取走 create 路径：人员字段带 avatar_url、日期为毫秒时间戳时同步成功。

    回归背景：同步 payload 曾写入模型不存在的 owner_avatar_url/director_avatar_url，
    ChangeActionPlan(**payload) 对每条记录抛 TypeError，生产 94 条全部失败。
    同时覆盖：缺「变更控制号/项目名称」的飞书记录不再跳过，按空值入库保证台账全量可见。
    """

    async def _fake_search_records(_db: Any, change_code: Any = None) -> Any:  # noqa: ANN001
        return [
            {
                "record_id": "rec_create_001",
                "fields": {
                    "变更控制号": [{"text": "BG-2601004", "type": "text"}],
                    "项目名称": [{"text": "修订检验规程", "type": "text"}],
                    "涉及工作": [{"text": "跟踪残留溶剂检测", "type": "text"}],
                    "总负责人": [
                        {
                            "name": "李文昊",
                            "id": "on_45aff2627b8d",
                            "avatar_url": "https://example.feishucdn.com/a.jpeg",
                        }
                    ],
                    "部门负责人": [
                        {
                            "name": "王经理",
                            "id": "on_director_001",
                            "avatar_url": "https://example.feishucdn.com/d.jpeg",
                        }
                    ],
                    "项目截止时间": 1773504000000,
                    "状态": "已完成",
                    "未完成是否延期": "否",
                    "延期后的日期": None,
                },
            },
            {
                "record_id": "rec_create_002",
                "fields": {
                    "涉及工作": [{"text": "待补录控制号的记录", "type": "text"}],
                    "状态": "推进中",
                },
            },
        ]

    monkeypatch.setattr(
        "app.modules.quality.service.change_action_plan.feishu_sync.search_records",
        _fake_search_records,
    )

    sync_response = await client.post(
        "/api/v1/quality/change-action-plans/sync-from-feishu"
    )
    assert sync_response.status_code == 200
    assert sync_response.json()["data"]["synced"] == 2
    assert sync_response.json()["data"]["failed"] == 0

    list_response = await client.get(
        "/api/v1/quality/change-action-plans",
        params={"change_code": "BG-2601004"},
    )
    assert list_response.status_code == 200
    items = list_response.json()["data"]
    assert len(items) == 1
    item = items[0]
    assert item["project_name"] == "修订检验规程"
    assert item["related_work"] == "跟踪残留溶剂检测"
    assert item["owner_name"] == "李文昊"
    assert item["owner_user_id"] == "on_45aff2627b8d"
    assert item["owner_avatar_url"] == "https://example.feishucdn.com/a.jpeg"
    assert item["director_name"] == "王经理"
    assert item["director_user_id"] == "on_director_001"
    assert item["director_avatar_url"] == "https://example.feishucdn.com/d.jpeg"
    assert item["status"] == "已完成"
    # 多维表时区为 Asia/Shanghai，1773504000000 = 上海 2026-03-15 00:00
    assert item["deadline_date"] == "2026-03-15"

    # 缺必填字段的记录不再被跳过：可按涉及工作检索到（空值序列化为 None，页面显示 -）
    missing_response = await client.get(
        "/api/v1/quality/change-action-plans",
        params={"related_work": "待补录控制号的记录"},
    )
    assert missing_response.status_code == 200
    missing_items = missing_response.json()["data"]
    assert len(missing_items) == 1
    assert missing_items[0]["change_code"] is None
    assert missing_items[0]["project_name"] is None
    assert missing_items[0]["status"] == "推进中"


@pytest.mark.anyio
async def test_change_action_plan_due_status_buckets(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """仪表盘逾期/临期明细：有效截止日（延期后优先）、已完成排除、窗口筛选、与统计同源。"""
    today = datetime.now(UTC).date()

    async def _seed(
        code: str,
        *,
        deadline: date | None = None,
        delayed: date | None = None,
        status: str | None = None,
        confirmed: bool = False,
    ) -> None:
        payload: dict[str, Any] = {
            "change_code": code,
            "project_name": f"{code} 项目",
            "deadline_date": deadline,
            "delayed_deadline_date": delayed,
            "status": status,
        }
        if confirmed:
            payload["reminder_confirmed_at"] = datetime.now(UTC)
        await repository.create_change_action_plan(db_session, payload)

    await _seed("BG-DUE-001", deadline=today - timedelta(days=1), status="推进中")
    await _seed("BG-DUE-002", deadline=today + timedelta(days=5))
    await _seed("BG-DUE-003", deadline=today - timedelta(days=2), status="已完成")
    await _seed(
        "BG-DUE-004",
        deadline=today - timedelta(days=10),
        delayed=today + timedelta(days=1),
        status="推进中",
    )
    await _seed("BG-DUE-005", status="推进中")
    await _seed(
        "BG-DUE-006",
        deadline=today - timedelta(days=3),
        status="推进中",
        confirmed=True,
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/quality/change-action-plans/due-status",
        params={"lead_days": 10},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["lead_days"] == 10
    assert data["total_count"] == 6
    assert data["confirmed_count"] == 1
    # 已完成(BG-DUE-003)与无截止日(BG-DUE-005)不进任何桶
    assert [item["change_code"] for item in data["overdue"]] == [
        "BG-DUE-006",
        "BG-DUE-001",
    ]
    assert data["overdue"][0]["days_offset"] == -3
    # BG-DUE-004 原截止日已过但延期到明天 → 按延期后日期进临期桶
    assert [item["change_code"] for item in data["due_soon"]] == [
        "BG-DUE-004",
        "BG-DUE-002",
    ]

    narrow = await client.get(
        "/api/v1/quality/change-action-plans/due-status",
        params={"lead_days": 2},
    )
    assert narrow.status_code == 200
    narrow_data = narrow.json()["data"]
    assert [item["change_code"] for item in narrow_data["due_soon"]] == ["BG-DUE-004"]
    assert len(narrow_data["overdue"]) == 2

    # 仪表盘统计的变更计划指标与 due-status 同源（真实计划表口径）
    stats = await client.get("/api/v1/quality/statistics/changes")
    assert stats.status_code == 200
    stats_data = stats.json()["data"]
    assert stats_data["actionPlanTotal"] == 6
    assert stats_data["actionPlanOverdue"] == 2
    assert stats_data["actionPlanConfirmed"] == 1


@pytest.mark.anyio
async def test_change_action_plan_reminder_api_flow(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_send(plan: Any, **kwargs: Any) -> Any:  # noqa: ANN001
        return "om_reminder_001"

    async def _fake_patch(plan: Any) -> Any:  # noqa: ANN001
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
