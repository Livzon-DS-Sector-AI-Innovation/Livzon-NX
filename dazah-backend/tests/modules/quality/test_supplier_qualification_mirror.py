"""供应商资质镜像表集成测试（列表/统计读本地镜像）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.external_quality import SupplierQualificationMirror
from app.modules.quality.service import quality_feishu_pages_supplier as supplier
from app.modules.quality.service.quality_feishu_pages_supplier import (
    get_supplier_statistics,
    list_supplier_qualification_records,
)
from app.modules.quality.service.quality_feishu_sync import (
    QualityFeishuEntityRuntimeConfig,
)

# 动态日期保证断言不随运行日漂移：已过期 / 30 天内到期 / 90 天外
_NOW = datetime.now(UTC)
_EXPIRED_ISO = (_NOW - timedelta(days=10)).isoformat()
_DUE30_ISO = (_NOW + timedelta(days=10)).isoformat()
_FAR_ISO = (_NOW + timedelta(days=400)).isoformat()


def _mirror(
    record_id: str,
    supplier_name: str,
    *,
    material_type: str = "原料",
    qualification_name: str = "营业执照",
    is_completed: bool = False,
    deadline: str | None = None,
) -> SupplierQualificationMirror:
    return SupplierQualificationMirror(
        feishu_record_id=record_id,
        supplier_name=supplier_name,
        material_name=f"物料-{record_id}",
        material_type=material_type,
        qualification_name=qualification_name,
        qualification_file=None,
        is_completed=is_completed,
        deadline=deadline,
        responsible_person="张三",
        remark=None,
        expiry_status="正常",
        source_created_at=datetime(2026, 8, 1, tzinfo=UTC),
        source_updated_at=datetime(2026, 8, 2, tzinfo=UTC),
    )


@pytest.fixture
async def seed_mirror(db_session: AsyncSession) -> None:
    await db_session.execute(
        delete(SupplierQualificationMirror).where(
            SupplierQualificationMirror.feishu_record_id.like("t-%")
        )
    )
    db_session.add_all(
        [
            _mirror("t-a", "供应商甲", is_completed=True, deadline=_EXPIRED_ISO),
            _mirror(
                "t-b",
                "供应商乙",
                material_type="包材",
                qualification_name="审计报告",
                deadline=_FAR_ISO,
            ),
            _mirror("t-c", "供应商丙", deadline=_DUE30_ISO),
        ]
    )
    await db_session.commit()
    yield
    await db_session.execute(
        delete(SupplierQualificationMirror).where(
            SupplierQualificationMirror.feishu_record_id.like("t-%")
        )
    )
    await db_session.commit()


@pytest.mark.anyio
async def test_list_reads_mirror_and_applies_filters(
    db_session: AsyncSession, seed_mirror: None
) -> None:
    result = await list_supplier_qualification_records(
        db_session, page=1, page_size=10
    )
    assert result["total"] == 3
    assert {item["record_id"] for item in result["items"]} == {
        "t-a",
        "t-b",
        "t-c",
    }
    # 按 deadline 倒序（最新在前）
    assert result["items"][0]["record_id"] == "t-b"
    assert result["items"][-1]["record_id"] == "t-a"

    filtered = await list_supplier_qualification_records(
        db_session,
        material_type="包材",
        page=1,
        page_size=10,
    )
    assert [item["record_id"] for item in filtered["items"]] == ["t-b"]

    completed = await list_supplier_qualification_records(
        db_session, is_completed=True, page=1, page_size=10
    )
    assert [item["record_id"] for item in completed["items"]] == ["t-a"]

    keyword = await list_supplier_qualification_records(
        db_session, keyword="供应商丙", page=1, page_size=10
    )
    assert [item["record_id"] for item in keyword["items"]] == ["t-c"]

    page2 = await list_supplier_qualification_records(
        db_session, page=2, page_size=2
    )
    assert page2["total"] == 3
    assert len(page2["items"]) == 1


@pytest.mark.anyio
async def test_statistics_aggregate_from_mirror(
    db_session: AsyncSession, seed_mirror: None
) -> None:
    stats = await get_supplier_statistics(db_session)
    assert stats["total"] == 3
    assert stats["completed"] == 1
    assert stats["pending"] == 2
    assert stats["supplier_count"] == 3
    assert stats["expired_count"] == 1  # t-a 已过期
    assert stats["due_30_count"] == 1  # t-c 30 天内到期
    assert stats["normal_count"] == 1  # t-b 远期
    assert stats["completion_rate"] == 33.3


# ── 写路径回写镜像（create/update/delete 仍直写飞书 + 同步镜像） ────────────


def _runtime() -> SimpleNamespace:
    return SimpleNamespace(app_id="cli-x", app_secret="secret-x")


def _entity() -> QualityFeishuEntityRuntimeConfig:
    return QualityFeishuEntityRuntimeConfig(
        app_token="app-token",
        table_id="table-id",
        is_enabled=True,
        enable_push_to_feishu=True,
        enable_pull_from_feishu=True,
        field_mappings={},
    )


def _remote_record(record_id: str, **overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "供应商名称": "供应商写",
        "物料名称": "原料W",
        "物料类型": "原料",
        "资质名称": "营业执照",
        "是否完成": True,
        "截止日期": int(datetime(2026, 10, 1, tzinfo=UTC).timestamp() * 1000),
        "备注": "远端备注",
    }
    fields.update(overrides.pop("fields", {}))
    record = {
        "record_id": record_id,
        "created_time": 1759276800000,
        "last_modified_time": 1759276800000,
        "fields": fields,
    }
    record.update(overrides)
    return record


class _FakeClient:
    def __init__(self, **_kwargs: Any) -> None:
        self.record: dict[str, Any] | None = _FakeClient.record
        self.updated: list[tuple[str, str, dict[str, Any]]] = []

    async def get_record(self, table_id: str, record_id: str) -> dict[str, Any] | None:
        return self.record

    async def update_record(
        self, table_id: str, record_id: str, fields: dict[str, Any]
    ) -> dict[str, str]:
        self.updated.append((table_id, record_id, fields))
        return {"record_id": record_id}


@pytest.fixture
async def cleanup_writeback_rows(db_session: AsyncSession) -> Any:
    await db_session.execute(
        delete(SupplierQualificationMirror).where(
            SupplierQualificationMirror.feishu_record_id.like("wb-%")
        )
    )
    await db_session.commit()
    yield db_session
    await db_session.execute(
        delete(SupplierQualificationMirror).where(
            SupplierQualificationMirror.feishu_record_id.like("wb-%")
        )
    )
    await db_session.commit()


@pytest.mark.anyio
async def test_create_writes_back_mirror_row(
    cleanup_writeback_rows: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = cleanup_writeback_rows
    monkeypatch.setattr(
        supplier,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(_runtime(), _entity())),
    )
    monkeypatch.setattr(
        supplier,
        "_create_entity_record",
        AsyncMock(return_value={"record_id": "wb-1", "table_id": "table-id"}),
    )
    _FakeClient.record = _remote_record("wb-1")
    monkeypatch.setattr(supplier, "BitableClient", _FakeClient)

    out = await supplier.create_supplier_qualification_record(
        db, {"supplier_name": "供应商写", "qualification_name": "营业执照"}
    )

    assert out["record_id"] == "wb-1"
    assert out["supplier_name"] == "供应商写"
    assert out["is_completed"] is True
    row = (
        await db.execute(
            select(SupplierQualificationMirror).where(
                SupplierQualificationMirror.feishu_record_id == "wb-1"
            )
        )
    ).scalar_one()
    assert row.supplier_name == "供应商写"
    assert row.remark == "远端备注"
    assert row.is_deleted is False


@pytest.mark.anyio
async def test_update_pushes_feishu_and_refreshes_mirror(
    cleanup_writeback_rows: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = cleanup_writeback_rows
    db.add(_mirror("wb-2", "旧名称", qualification_name="营业执照"))
    await db.commit()
    monkeypatch.setattr(
        supplier,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(_runtime(), _entity())),
    )
    _FakeClient.record = _remote_record("wb-2", fields={"供应商名称": "新名称"})
    client_holder: dict[str, _FakeClient] = {}

    def _factory(**kwargs: Any) -> _FakeClient:
        instance = _FakeClient(**kwargs)
        client_holder["client"] = instance
        return instance

    monkeypatch.setattr(supplier, "BitableClient", _factory)

    out = await supplier.update_supplier_qualification_record(
        db, "wb-2", {"supplier_name": "新名称"}
    )

    assert out["supplier_name"] == "新名称"
    assert client_holder["client"].updated, "应调用飞书 update_record"
    row = (
        await db.execute(
            select(SupplierQualificationMirror).where(
                SupplierQualificationMirror.feishu_record_id == "wb-2"
            )
        )
    ).scalar_one()
    assert row.supplier_name == "新名称"


@pytest.mark.anyio
async def test_delete_soft_deletes_mirror_after_feishu_delete(
    cleanup_writeback_rows: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = cleanup_writeback_rows
    db.add(_mirror("wb-3", "供应商丁"))
    await db.commit()
    deleted = AsyncMock()
    monkeypatch.setattr(supplier, "_delete_entity_record", deleted)

    await supplier.delete_supplier_qualification_record(db, "wb-3")

    deleted.assert_awaited_once()
    row = (
        await db.execute(
            select(SupplierQualificationMirror).where(
                SupplierQualificationMirror.feishu_record_id == "wb-3"
            )
        )
    ).scalar_one()
    assert row.is_deleted is True


# ── 到期分桶筛选（仪表盘卡片/图表点击弹窗的数据源） ──────────────────────


@pytest.mark.anyio
async def test_expiry_bucket_filter_matches_statistics(
    db_session: AsyncSession, seed_mirror: None
) -> None:
    """逐桶命中集合正确，且与 get_supplier_statistics 的分桶计数一致。"""
    stats = await get_supplier_statistics(db_session)
    for bucket, stat_key in (
        ("expired", "expired_count"),
        ("due_30", "due_30_count"),
        ("due_60", "due_60_count"),
        ("due_90", "due_90_count"),
    ):
        result = await list_supplier_qualification_records(
            db_session, expiry_bucket=bucket, page=1, page_size=50
        )
        assert result["total"] == stats[stat_key], bucket
    # 种子数据：t-a 已过期；t-b 400 天外（任何到期桶都不命中）；t-c 30 天内
    expired = await list_supplier_qualification_records(
        db_session, expiry_bucket="expired"
    )
    assert [item["record_id"] for item in expired["items"]] == ["t-a"]
    due_30 = await list_supplier_qualification_records(
        db_session, expiry_bucket="due_30"
    )
    assert [item["record_id"] for item in due_30["items"]] == ["t-c"]
    for empty_bucket in ("due_60", "due_90"):
        result = await list_supplier_qualification_records(
            db_session, expiry_bucket=empty_bucket
        )
        assert result["total"] == 0, empty_bucket


@pytest.mark.anyio
async def test_expiry_bucket_combines_with_other_filters(
    db_session: AsyncSession, seed_mirror: None
) -> None:
    result = await list_supplier_qualification_records(
        db_session, expiry_bucket="expired", is_completed=True
    )
    assert [item["record_id"] for item in result["items"]] == ["t-a"]
    result = await list_supplier_qualification_records(
        db_session, expiry_bucket="expired", is_completed=False
    )
    assert result["total"] == 0
