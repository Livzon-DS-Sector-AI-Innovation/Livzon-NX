"""CPV service layer tests: product/parameter CRUD, statistics pure functions,
batch aggregation, and Excel import preview parsing (真实库 + 纯函数)."""

from __future__ import annotations

import io
from collections.abc import AsyncIterator
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.quality.models.cpv_batch import CpvBatch
from app.modules.quality.models.cpv_parameter import CpvParameter
from app.modules.quality.models.cpv_product import CpvProduct
from app.modules.quality.models.cpv_value import CpvValue
from app.modules.quality.schemas import (
    CpvParameterCreate,
    CpvParameterUpdate,
    CpvProductCreate,
    CpvProductUpdate,
)
from app.modules.quality.service import (
    cpv_import,
    cpv_parameter,
    cpv_product,
    cpv_statistics,
)


@pytest.fixture(autouse=True)
async def _clean_cpv_tables(db_session: AsyncSession) -> AsyncIterator[None]:
    for model in (CpvValue, CpvBatch, CpvParameter, CpvProduct):
        await db_session.execute(model.__table__.delete())  # type: ignore[attr-defined]
    await db_session.commit()
    yield
    for model in (CpvValue, CpvBatch, CpvParameter, CpvProduct):
        await db_session.execute(model.__table__.delete())  # type: ignore[attr-defined]
    await db_session.commit()


async def _make_product(db: AsyncSession, name: str = "阿卡波糖") -> CpvProduct:
    product = await cpv_product.create_product(
        db,
        CpvProductCreate(
            name=name,
            specification="50kg/桶",
            process_version="V2.0",
            status="active",
        ),
    )
    await db.commit()
    return product


# ─── 产品 CRUD ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_product_crud_and_pagination(db_session: AsyncSession) -> None:
    p1 = await _make_product(db_session, "阿卡波糖")
    p2 = await _make_product(db_session, "多拉菌素")

    # keyword + status 过滤
    listed, total = await cpv_product.get_products(
        db_session, keyword="阿卡", status="active", page=1, page_size=10
    )
    assert total == 1
    assert listed[0].id == p1.id

    # 分页：page_size=1 只返回第一条（按创建倒序，后创建在前）
    page1, total = await cpv_product.get_products(
        db_session, page=1, page_size=1
    )
    assert total == 2
    assert len(page1) == 1

    # update
    updated = await cpv_product.update_product(
        db_session, p2.id, CpvProductUpdate(status="inactive")
    )
    assert updated.status == "inactive"

    # delete + NotFound
    await cpv_product.delete_product(db_session, p2.id)
    with pytest.raises(NotFoundException):
        await cpv_product.get_product_by_id(db_session, p2.id)
    with pytest.raises(NotFoundException):
        await cpv_product.update_product(
            db_session, uuid4(), CpvProductUpdate(name="不存在")
        )


# ─── 参数 CRUD ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_parameter_crud_and_filtering(db_session: AsyncSession) -> None:
    product = await _make_product(db_session)
    param = await cpv_parameter.create_parameter(
        db_session,
        product.id,
        CpvParameterCreate(
            parameter_type="CPP",
            name="含量",
            code="CONTENT",
            unit="%",
            lower_limit=95.0,
            upper_limit=105.0,
            target_value=100.0,
            is_enabled=True,
            sort_order=1,
        ),
    )
    await db_session.commit()

    all_params = await cpv_parameter.get_parameters(db_session, product.id)
    assert len(all_params) == 1
    filtered = await cpv_parameter.get_parameters(
        db_session, product.id, parameter_type="CPP", is_enabled=True
    )
    assert filtered[0].id == param.id
    empty = await cpv_parameter.get_parameters(
        db_session, product.id, parameter_type="finished"
    )
    assert empty == []

    updated = await cpv_parameter.update_parameter(
        db_session, param.id, CpvParameterUpdate(upper_limit=108.0)
    )
    assert updated.upper_limit == 108.0

    await cpv_parameter.delete_parameter(db_session, param.id)
    with pytest.raises(NotFoundException):
        await cpv_parameter.get_parameter_by_id(db_session, param.id)


# ─── 统计纯函数 ────────────────────────────────────────────────────


def test_to_float_parsing() -> None:
    assert cpv_statistics._to_float("未检出") == 0.0
    assert cpv_statistics._to_float("-") == 0.0
    assert cpv_statistics._to_float("99.5") == 99.5
    assert cpv_statistics._to_float("") is None
    assert cpv_statistics._to_float(None) is None
    assert cpv_statistics._to_float("abc") is None


def test_calc_std_dev() -> None:
    assert cpv_statistics._calc_std_dev([5.0]) == 0.0
    # 样本 [2,4,4,4,5,5,7,9] 标准差 ≈ 2.138
    std = cpv_statistics._calc_std_dev([2, 4, 4, 4, 5, 5, 7, 9])
    assert abs(std - 2.138) < 0.01


def test_calc_cpk() -> None:
    assert cpv_statistics._calc_cpk([], 0, 10) == 0.0
    # 单值（std=0）→ 0
    assert cpv_statistics._calc_cpk([5.0], 0, 10) == 0.0
    # 对称限值：均值居中 → cpk 合理且非负
    cpk = cpv_statistics._calc_cpk([95, 96, 97, 98, 99], 95.0, 105.0)
    assert 0 < cpk < 10
    # 越界 → 钳到 0
    cpk_out = cpv_statistics._calc_cpk([50, 51, 52], 95.0, 105.0)
    assert cpk_out == 0.0


# ─── 批次聚合 + 统计 ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_batch_aggregation_and_statistics(db_session: AsyncSession) -> None:
    product = await _make_product(db_session)
    param = await cpv_parameter.create_parameter(
        db_session,
        product.id,
        CpvParameterCreate(
            parameter_type="CPP",
            name="含量",
            lower_limit=90.0,
            upper_limit=110.0,
        ),
    )
    await db_session.commit()

    batch_ids = []
    for i, value in enumerate(["95", "100", "105"]):
        from app.modules.quality.repository.cpv_batch import create_batch

        batch = await create_batch(
            db_session,
            {
                "product_id": product.id,
                "batch_no": f"B-{i}",
                "production_date": date(2026, 8, 1 + i),
                "data_type": "CPP",
                "source": "manual",
                "import_task_id": None,
            },
        )
        await db_session.flush()
        from app.modules.quality.repository.cpv_value import create_value

        await create_value(
            db_session,
            {
                "batch_id": batch.id,
                "parameter_id": param.id,
                "actual_value": str(value),
                "is_abnormal": False,
            },
        )
        batch_ids.append(batch.id)
    await db_session.commit()

    stats = await cpv_statistics.get_statistics(
        db_session, product.id, param.id
    )
    assert stats.total_batches == 3
    assert stats.min_value == 95.0
    assert stats.max_value == 105.0
    assert stats.avg_value == 100.0
    assert stats.std_dev > 0
    assert stats.cpk_value > 0
    assert stats.abnormal_count == 0


# ─── 导入预览解析 ──────────────────────────────────────────────────


def _make_import_workbook() -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["批号", "生产日期", "含量", "水分"])
    ws.append(["B-1001", "2026-08-01", "99.2", "0.5"])
    ws.append(["", "2026-08-02", "100.1", "0.6"])  # 批号为空 → 错误行
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_import_preview_parses_workbook(db_session: AsyncSession) -> None:
    product = await _make_product(db_session)
    for name in ("含量", "水分"):
        await cpv_parameter.create_parameter(
            db_session,
            product.id,
            CpvParameterCreate(
                parameter_type="CPP",
                name=name,
                lower_limit=0.0,
                upper_limit=110.0,
            ),
        )
    await db_session.commit()

    preview = await cpv_import.preview_import(
        db_session,
        _make_import_workbook(),
        product.id,
        "CPP",
        "overwrite",
    )
    # 1 行有效、1 行批号缺失报错；含量/水分两列已匹配
    assert preview.valid_rows == 1
    assert len(preview.error_rows) == 1
    assert any(
        "批号不能为空" in row.get("error_message", "") for row in preview.error_rows
    )
    assert "含量" in preview.matched_parameters
    assert "水分" in preview.matched_parameters
