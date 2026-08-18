"""MaterialCatalogRepository 批量写入路径的数据库集成测试。"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.procurement.models import MaterialCatalogRecord, MaterialSourceConfig
from app.modules.procurement.repository import MaterialCatalogRepository


async def _create_config(db: AsyncSession) -> MaterialSourceConfig:
    config = MaterialSourceConfig(
        config_key="material-master",
        source_url="https://feishu.cn/base/appToken123456?table=tbl123456",
        app_token="appToken123456",
        table_id="tbl123456",
        material_code_field="物料编码",
        material_description_field="物料说明",
        rule_model_field="规格型号",
    )
    db.add(config)
    await db.flush()
    return config


def _row(config: MaterialSourceConfig, record_id: str, code: str) -> dict:
    return {
        "source_config_id": config.id,
        "feishu_record_id": record_id,
        "material_code": code,
        "material_description": f"物料{code}",
        "rule_model": "A",
        "feishu_created_time": None,
        "feishu_last_modified_time": None,
        "last_synced_at": datetime.now(UTC),
        "is_deleted": False,
        "created_by": None,
        "updated_by": None,
    }


async def _catalog_records(
    db: AsyncSession,
    config: MaterialSourceConfig,
) -> list[MaterialCatalogRecord]:
    # Core 批量 upsert 不更新 ORM 身份映射，用 populate_existing 刷新已加载对象
    result = await db.execute(
        select(MaterialCatalogRecord)
        .where(MaterialCatalogRecord.source_config_id == config.id)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


@pytest.mark.anyio
async def test_list_option_records_filters_orders_and_limits_without_count(
    db_session: AsyncSession,
) -> None:
    config = await _create_config(db_session)
    repository = MaterialCatalogRepository(db_session)
    await repository.bulk_upsert(
        [
            _row(config, "rec-contains", "X-MAT-003"),
            _row(config, "rec-prefix-2", "MAT-002"),
            _row(config, "rec-exact", "MAT"),
            _row(config, "rec-prefix-1", "MAT-001"),
            _row(config, "rec-deleted", "MAT-000"),
        ]
    )
    await db_session.flush()
    await db_session.execute(
        MaterialCatalogRecord.__table__.update()
        .where(MaterialCatalogRecord.feishu_record_id == "rec-deleted")
        .values(is_deleted=True)
    )

    records = await repository.list_option_records(
        source_config_id=config.id,
        keyword="mat",
        limit=3,
    )

    assert [record.feishu_record_id for record in records] == [
        "rec-exact",
        "rec-prefix-1",
        "rec-prefix-2",
    ]
@pytest.mark.anyio
async def test_bulk_upsert_inserts_updates_and_reactivates_records(
    db_session: AsyncSession,
) -> None:
    config = await _create_config(db_session)
    repository = MaterialCatalogRepository(db_session)

    inserted = await repository.bulk_upsert(
        [
            _row(config, "rec-1", "MAT-001"),
            _row(config, "rec-2", "MAT-002"),
        ]
    )
    await db_session.flush()
    # asyncpg 对 ON CONFLICT DO UPDATE 不返回可靠 rowcount，按批内行数返回
    assert inserted == 2

    first_batch = await _catalog_records(db_session, config)
    assert {item.feishu_record_id for item in first_batch} == {"rec-1", "rec-2"}
    assert all(item.is_deleted is False for item in first_batch)

    for item in first_batch:
        item.is_deleted = True
    await db_session.flush()

    upserted = await repository.bulk_upsert(
        [
            _row(config, "rec-1", "MAT-001-NEW"),
            _row(config, "rec-3", "MAT-003"),
        ]
    )
    await db_session.flush()
    assert upserted == 2

    second_batch = await _catalog_records(db_session, config)
    assert {item.feishu_record_id for item in second_batch} == {
        "rec-1",
        "rec-2",
        "rec-3",
    }
    by_id = {item.feishu_record_id: item for item in second_batch}
    assert by_id["rec-1"].material_code == "MAT-001-NEW"
    assert by_id["rec-1"].is_deleted is False
    assert by_id["rec-2"].is_deleted is True
    assert by_id["rec-3"].is_deleted is False


@pytest.mark.anyio
async def test_deactivate_missing_only_touches_missing_active_records(
    db_session: AsyncSession,
) -> None:
    config = await _create_config(db_session)
    repository = MaterialCatalogRepository(db_session)
    await repository.bulk_upsert(
        [
            _row(config, "rec-1", "MAT-001"),
            _row(config, "rec-2", "MAT-002"),
        ]
    )
    await db_session.flush()

    count = await repository.deactivate_missing(config.id, ["rec-2"])
    assert count == 1
    # 已停用的记录不会重复计入
    assert await repository.deactivate_missing(config.id, ["rec-2"]) == 0

    records = await _catalog_records(db_session, config)
    by_id = {item.feishu_record_id: item for item in records}
    assert by_id["rec-1"].is_deleted is False
    assert by_id["rec-2"].is_deleted is True


@pytest.mark.anyio
async def test_list_feishu_record_ids_includes_soft_deleted(
    db_session: AsyncSession,
) -> None:
    config = await _create_config(db_session)
    repository = MaterialCatalogRepository(db_session)
    await repository.bulk_upsert(
        [
            _row(config, "rec-1", "MAT-001"),
            _row(config, "rec-2", "MAT-002"),
        ]
    )
    await db_session.flush()
    await repository.deactivate_missing(config.id, ["rec-2"])

    assert await repository.list_feishu_record_ids(config.id) == {
        "rec-1",
        "rec-2",
    }


@pytest.mark.anyio
async def test_bulk_upsert_batches_by_write_batch_size(
    db_session: AsyncSession,
) -> None:
    config = await _create_config(db_session)
    repository = MaterialCatalogRepository(db_session)
    rows = [
        _row(config, f"rec-{index}", f"MAT-{index:04d}")
        for index in range(MaterialCatalogRepository.WRITE_BATCH_SIZE + 10)
    ]

    await repository.bulk_upsert(rows)
    await db_session.flush()

    total = await db_session.scalar(
        select(func.count(MaterialCatalogRecord.id)).where(
            MaterialCatalogRecord.source_config_id == config.id,
        )
    )
    assert total == MaterialCatalogRepository.WRITE_BATCH_SIZE + 10
