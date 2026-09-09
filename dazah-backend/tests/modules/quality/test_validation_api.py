from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.validation_record import ValidationRecord
from tests.modules.quality.validation_migration import (
    assert_validation_migration_state,
    reset_validation_records_table,
)


@pytest.fixture(autouse=True)
async def _clean_validation_records(db_session: AsyncSession) -> Any:
    await reset_validation_records_table(db_session)
    yield
    await reset_validation_records_table(db_session)


@pytest.mark.anyio
async def test_validation_migration_upgrade_tracks_target_revision(
    db_session: AsyncSession,
) -> None:
    await assert_validation_migration_state(db_session)


@pytest.mark.anyio
async def test_list_validations_api_returns_filtered_rows(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    db_session.add(
        ValidationRecord(
            id=uuid.uuid4(),
            record_type="equipment_qualification",
            record_code="VAL-2026-001",
            title="纯化水系统 IQ",
            status="pending",
            department="工程部",
            planned_end_date=date(2026, 7, 1),
        )
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/quality/validations",
        params={
            "record_code": "VAL-2026-001",
            "validation_type": "equipment_qualification",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["record_code"] == "VAL-2026-001"
    assert body["data"][0]["validation_type"] == "equipment_qualification"


@pytest.mark.anyio
async def test_create_validation_api_returns_created_row(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/quality/validations",
        json={
            "validation_type": "cleaning_validation",
            "record_code": "VAL-2026-002",
            "title": "多功能车间清洁验证",
            "status": "pending",
            "department": "质量部",
            "equipment_code": "EQ-001",
            "product_codes": ["MC", "LV"],
            "planned_end_date": "2026-07-03",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["record_code"] == "VAL-2026-002"
    assert body["data"]["validation_type"] == "cleaning_validation"

    execution_response = await client.get(
        "/api/v1/quality/validation-executions/cleaning_validation"
    )
    assert execution_response.status_code == 200
    execution_body = execution_response.json()
    assert execution_body["meta"]["total"] == 1
    assert execution_body["data"][0]["master_validation_id"] == body["data"]["id"]


@pytest.mark.anyio
async def test_get_validation_api_returns_detail(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    record = ValidationRecord(
        id=uuid.uuid4(),
        record_type="process_validation",
        record_code="VAL-2026-003",
        title="关键工艺参数再验证",
        status="completed",
        department="生产部",
        equipment_code="EQ-003",
        product_codes=["DR"],
        planned_end_date=date(2026, 7, 5),
    )
    db_session.add(record)
    await db_session.commit()

    response = await client.get(f"/api/v1/quality/validations/{record.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["id"] == str(record.id)
    assert body["data"]["title"] == "关键工艺参数再验证"
    assert body["data"]["validation_type"] == "process_validation"


@pytest.mark.anyio
async def test_update_validation_api_updates_row(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    record = ValidationRecord(
        id=uuid.uuid4(),
        record_type="cleaning_validation",
        record_code="VAL-2026-004",
        title="原始清洁验证",
        status="draft",
    )
    db_session.add(record)
    await db_session.commit()

    response = await client.put(
        f"/api/v1/quality/validations/{record.id}",
        json={
            "validation_type": "process_validation",
            "title": "更新后的工艺验证",
            "status": "completed",
            "department": "生产部",
            "equipment_code": "EQ-004",
            "planned_end_date": "2026-08-01",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["validation_type"] == "process_validation"
    assert body["data"]["title"] == "更新后的工艺验证"
    assert body["data"]["status"] == "completed"


@pytest.mark.anyio
async def test_delete_validation_api_soft_deletes_row(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    record = ValidationRecord(
        id=uuid.uuid4(),
        record_type="equipment_qualification",
        record_code="VAL-2026-005",
        title="待删除验证",
    )
    db_session.add(record)
    await db_session.commit()

    response = await client.delete(f"/api/v1/quality/validations/{record.id}")

    assert response.status_code == 200
    assert response.json()["data"]["success"] is True

    detail_response = await client.get(f"/api/v1/quality/validations/{record.id}")
    assert detail_response.status_code == 404


@pytest.mark.anyio
async def test_update_validation_execution_api_updates_child_row(
    client: AsyncClient,
) -> None:
    create_response = await client.post(
        "/api/v1/quality/validations",
        json={
            "validation_type": "other_validation",
            "record_code": "VAL-2026-006",
            "title": "其他验证执行",
            "department": "质量部",
        },
    )
    assert create_response.status_code == 200
    record_id = create_response.json()["data"]["id"]

    response = await client.put(
        f"/api/v1/quality/validation-executions/other_validation/{record_id}",
        json={
            "plan_name": "2026年其他验证方案",
            "plan_code": "PLAN-006",
            "report_no": "REPORT-006",
            "revalidation_cycle_years": 3,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["plan_name"] == "2026年其他验证方案"
    assert body["data"]["plan_code"] == "PLAN-006"
    assert body["data"]["report_no"] == "REPORT-006"
    assert body["data"]["revalidation_cycle_years"] == 3


@pytest.mark.anyio
async def test_batch_delete_validation_api_soft_deletes_rows(
    client: AsyncClient,
) -> None:
    create_ids: list[Any] = []
    for index in range(2):
        response = await client.post(
            "/api/v1/quality/validations",
            json={
                "validation_type": "equipment_qualification",
                "record_code": f"VAL-2026-B0{index + 1}",
                "title": f"批量删除验证{index + 1}",
            },
        )
        assert response.status_code == 200
        create_ids.append(response.json()["data"]["id"])

    response = await client.post(
        "/api/v1/quality/validations/batch-delete",
        json=create_ids,
    )

    assert response.status_code == 200
    assert response.json()["data"]["deleted"] == 2

    list_response = await client.get(
        "/api/v1/quality/validation-executions/equipment_qualification"
    )
    assert list_response.status_code == 200
    assert list_response.json()["meta"]["total"] == 0


# ── 飞书侧边挂载端点（feishu/validations 读写） ──


@pytest.mark.anyio
async def test_feishu_validation_get_and_create_endpoints(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import AsyncMock

    from app.modules.quality.api import validation as validation_api

    monkeypatch.setattr(
        validation_api,
        "get_validation_record_from_feishu",
        AsyncMock(return_value={"record_id": "rec-1", "title": "纯化水系统 IQ"}),
    )
    resp = await client.get(
        "/api/v1/quality/feishu/validations/rec-1"
        "?validation_type=equipment_qualification&year=2026"
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["record_id"] == "rec-1"

    monkeypatch.setattr(
        validation_api,
        "create_validation_record_in_feishu",
        AsyncMock(return_value=[{"record_id": "rec-new", "title": "新验证"}]),
    )
    resp = await client.post(
        "/api/v1/quality/feishu/validations?year=2026",
        json={"title": "新验证"},
    )
    assert resp.status_code == 201
    assert resp.json()["data"][0]["record_id"] == "rec-new"
@pytest.mark.anyio
async def test_validation_person_options_reads_hr_feishu_members(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """人员选择候选必须来自人事管理-飞书联系人（在职、按 open_id 去重）。"""
    from sqlalchemy import delete

    from app.modules.hr.models import HrFeishuMember

    # 清理历史运行残留，避免唯一约束冲突
    await db_session.execute(
        delete(HrFeishuMember).where(HrFeishuMember.open_id.in_(["ou_1", "ou_2"]))
    )
    await db_session.commit()

    db_session.add_all(
        [
            HrFeishuMember(
                open_id="ou_1", name="张三", department="质量部", status="1"
            ),
            HrFeishuMember(
                open_id="ou_1", name="张三", department="生产部", status="1"
            ),
            # 离职
            HrFeishuMember(
                open_id="ou_2", name="李四", department="生产部", status="2"
            ),
        ]
    )
    await db_session.commit()

    response = await client.get("/api/v1/quality/validations/person-options")

    assert response.status_code == 200
    # 测试库为共享数据，断言只看本用例播种的 open_id
    data = [
        item
        for item in response.json()["data"]
        if item["open_id"] in ("ou_1", "ou_2")
    ]
    assert len(data) == 1
    assert data[0]["open_id"] == "ou_1"
    assert data[0]["name"] == "张三"
    # 多部门去重后保留其中一个部门（取 min，不依赖具体值）
    assert data[0]["department"] in ("质量部", "生产部")

    filtered = await client.get(
        "/api/v1/quality/validations/person-options",
        params={"keyword": "张"},
    )
    ids = [item["open_id"] for item in filtered.json()["data"]]
    assert [item for item in ids if item in ("ou_1", "ou_2")] == ["ou_1"]
@pytest.mark.anyio
async def test_validation_form_links_cover_reserved_years(
    client: AsyncClient,
) -> None:
    """表单链接：2024-2026 预填默认表单；2027/2028 预留（链接为空）。"""
    response = await client.get("/api/v1/quality/feishu/validations/form-links")

    assert response.status_code == 200
    years = response.json()["data"]["years"]
    by_year = {item["year"]: item for item in years}
    assert set(by_year) == {2024, 2025, 2026, 2027, 2028}
    assert "shrcnw2P5gEnFsiwKGpR8TuJ1Nh" in by_year[2026]["form_url"]
    assert "shrcnrXPjhpZb40QhpQnUqgodHc" in by_year[2025]["form_url"]
    assert "shrcnQEeBbkDhG8CrvmW5urZ8vd" in by_year[2024]["form_url"]
    assert by_year[2026]["table_configured"] is True
    assert by_year[2027]["form_url"] == ""
    assert by_year[2027]["table_configured"] is False
