"""仓储公开接口：物料页镜像行读取（供设备备件同步等跨模块消费）。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.warehouse import public_api
from app.modules.warehouse.models import MaterialPageRow, MaterialPageSnapshot


async def _seed_inbound_snapshot(db_session: AsyncSession) -> None:
    snapshot = MaterialPageSnapshot(
        page_key="hardware-test-public-read",
        page_title="测试车间",
        table_name="101",
        table_id="tblTest",
        columns=[],
        total_rows=2,
    )
    db_session.add(snapshot)
    await db_session.flush()
    for order, code in ((1, "51018847"), (2, "51119736")):
        db_session.add(
            MaterialPageRow(
                page_snapshot_id=snapshot.id,
                source_record_id=f"rec-{order}",
                row_order=order,
                cells={"物料编号": code, "结存量": order},
                search_text=f"{code} {order}",
            )
        )
    await db_session.flush()


async def test_get_material_page_rows_returns_cells_in_order(
    db_session: AsyncSession,
) -> None:
    await _seed_inbound_snapshot(db_session)

    rows, synced_at = await public_api.get_material_page_rows(
        db_session, page_key="hardware-test-public-read"
    )
    assert rows == [
        {"物料编号": "51018847", "结存量": 1},
        {"物料编号": "51119736", "结存量": 2},
    ]
    assert synced_at is not None


async def test_get_material_page_rows_unknown_page(
    db_session: AsyncSession,
) -> None:
    rows, synced_at = await public_api.get_material_page_rows(
        db_session, page_key="hardware-not-exists"
    )
    assert rows == []
    assert synced_at is None


async def test_get_material_page_rows_filters_by_search_text(
    db_session: AsyncSession,
) -> None:
    await _seed_inbound_snapshot(db_session)

    rows, _ = await public_api.get_material_page_rows(
        db_session,
        page_key="hardware-test-public-read",
        search_text="51119736",
    )
    assert [row["物料编号"] for row in rows] == ["51119736"]


async def test_get_material_page_rows_filters_by_field_values(
    db_session: AsyncSession,
) -> None:
    await _seed_inbound_snapshot(db_session)

    rows, _ = await public_api.get_material_page_rows(
        db_session,
        page_key="hardware-test-public-read",
        field_values={"物料编号": ["51018847"]},
    )
    assert [row["物料编号"] for row in rows] == ["51018847"]

    # LIKE 通配符在 field_values 的精确匹配中不生效
    wildcard_rows, _ = await public_api.get_material_page_rows(
        db_session,
        page_key="hardware-test-public-read",
        field_values={"物料编号": ["%"]},
    )
    assert wildcard_rows == []


async def test_get_material_page_rows_respects_limit(
    db_session: AsyncSession,
) -> None:
    await _seed_inbound_snapshot(db_session)

    rows, _ = await public_api.get_material_page_rows(
        db_session,
        page_key="hardware-test-public-read",
        limit=1,
    )
    assert len(rows) == 1
