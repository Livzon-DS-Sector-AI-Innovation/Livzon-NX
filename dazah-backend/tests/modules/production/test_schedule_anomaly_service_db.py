"""排产异常记录服务：独立测试库上的读写与筛选。"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production import schedule_anomaly_service as service
from app.modules.production.schedule_anomaly_models import ScheduleAnomalyRecord

PRODUCT = "FA"


async def _cleanup(db_session: AsyncSession) -> None:
    # 该表当前仅由本文件测试写入（独立测试库），整表清理保证互不残留
    await db_session.execute(delete(ScheduleAnomalyRecord))
    await db_session.commit()


@pytest.fixture
async def clean_table(db_session: AsyncSession):
    await _cleanup(db_session)
    yield
    await _cleanup(db_session)


@pytest.mark.anyio
async def test_create_and_serialize_anomaly(
    db_session: AsyncSession, clean_table: None
) -> None:
    record = await service.create_anomaly(
        db_session,
        product_code=PRODUCT,
        batch_no="FA26314",
        anomaly_type="reseeded",
        event_date=date(2026, 11, 28),
        reason="移种延后，原接种作废",
        tank_no="202A",
        remark=" 种子超龄 ",
        created_by=None,
    )
    await db_session.commit()

    assert record.batch_no == "FA26314"
    assert record.tank_no == "202A"
    assert record.reason == "移种延后，原接种作废"
    # 入参两侧空白被清理
    assert record.remark == "种子超龄"

    data = service.serialize_anomaly(record, created_by_name="标记人")
    assert data["anomaly_type_label"] == "补种"
    assert data["event_date"] == "2026-11-28"
    assert data["created_by_name"] == "标记人"


@pytest.mark.anyio
async def test_create_trims_optional_fields_to_null(
    db_session: AsyncSession, clean_table: None
) -> None:
    record = await service.create_anomaly(
        db_session,
        product_code=PRODUCT,
        batch_no="FA26315",
        anomaly_type="delayed",
        event_date=date(2026, 11, 28),
        reason="等料",
        tank_no="   ",
        remark=None,
    )
    await db_session.commit()
    assert record.tank_no is None
    assert record.remark is None


@pytest.mark.anyio
async def test_create_validation_errors(db_session: AsyncSession) -> None:
    base = dict(
        product_code=PRODUCT,
        event_date=date(2026, 11, 28),
    )
    with pytest.raises(service.AnomalyValidationError, match="批号不能为空"):
        await service.create_anomaly(
            db_session, batch_no="  ", anomaly_type="delayed", reason="等料", **base
        )
    with pytest.raises(service.AnomalyValidationError, match="不支持的异常类型"):
        await service.create_anomaly(
            db_session,
            batch_no="FA26316",
            anomaly_type="unknown",
            reason="等料",
            **base,
        )
    with pytest.raises(service.AnomalyValidationError, match="原因不能为空"):
        await service.create_anomaly(
            db_session,
            batch_no="FA26316",
            anomaly_type="delayed",
            reason="  ",
            **base,
        )


@pytest.mark.anyio
async def test_list_filters_and_pagination(
    db_session: AsyncSession, clean_table: None
) -> None:
    for batch_no, anomaly_type, event_date in (
        ("FA26314", "reseeded", date(2026, 11, 28)),
        ("FA26315", "delayed", date(2026, 11, 29)),
        ("FA27001", "reduced", date(2026, 12, 24)),
    ):
        await service.create_anomaly(
            db_session,
            product_code=PRODUCT,
            batch_no=batch_no,
            anomaly_type=anomaly_type,
            event_date=event_date,
            reason=f"{batch_no} 测试",
        )
    await db_session.commit()

    items, total = await service.list_anomalies(
        db_session, product_code=PRODUCT
    )
    assert total == 3
    # 默认按发生日期倒序
    assert [row[0].batch_no for row in items] == ["FA27001", "FA26315", "FA26314"]

    items, total = await service.list_anomalies(
        db_session, product_code=PRODUCT, batch_no="FA26315"
    )
    assert total == 1 and items[0][0].anomaly_type == "delayed"

    items, total = await service.list_anomalies(
        db_session, product_code=PRODUCT, anomaly_type="reseeded"
    )
    assert total == 1 and items[0][0].batch_no == "FA26314"

    items, total = await service.list_anomalies(
        db_session,
        product_code=PRODUCT,
        date_from=date(2026, 11, 28),
        date_to=date(2026, 11, 29),
    )
    assert total == 2

    items, total = await service.list_anomalies(
        db_session, product_code=PRODUCT, page=2, page_size=2
    )
    assert total == 3 and len(items) == 1

    # 其他产品互不可见
    _, other_total = await service.list_anomalies(
        db_session, product_code="MC"
    )
    assert other_total == 0


@pytest.mark.anyio
async def test_export_lists_all_matching_rows_without_pagination(
    db_session: AsyncSession, clean_table: None
) -> None:
    for index, (batch_no, anomaly_type) in enumerate(
        (
            ("FA26314", "reseeded"),
            ("FA26315", "delayed"),
            ("FA27001", "reduced"),
        )
    ):
        await service.create_anomaly(
            db_session,
            product_code=PRODUCT,
            batch_no=batch_no,
            anomaly_type=anomaly_type,
            event_date=date(2026, 11, 28),
            reason=f"{batch_no} 导出测试",
        )
    await db_session.commit()

    rows = await service.list_anomalies_for_export(
        db_session, product_code=PRODUCT
    )
    assert len(rows) == 3

    # 导出与列表同筛选口径
    filtered = await service.list_anomalies_for_export(
        db_session, product_code=PRODUCT, anomaly_type="reduced"
    )
    assert [row[0].batch_no for row in filtered] == ["FA27001"]

    # 组装为 xlsx 字节流（xlsx 为 ZIP 容器，魔数 PK）
    content = service.build_anomalies_workbook(rows)
    assert content[:2] == b"PK"
