"""消防器材台账投影与点检提交测试（独立测试库）。

覆盖：镜像字段启发式映射（编号/部门/位置/类型）、幂等重跑、镜像消失后
软删、点检提交的整卡校验/结论汇总/最近点检回写，飞书写回（字段映射、
一键建表、补写幂等），以及 API 依赖的核心服务分支（缺检查项 400、非法
检查项 400、器材不存在 404）。
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.safety.models import (
    FireEquipment,
    FireInspectionRecord,
    SafetyPageFeishuConfig,
    SafetyPageTableMirrorRecord,
)
from app.modules.safety.service import fire_equipment as fire_equipment_module
from app.modules.safety.service.fire_equipment import (
    CHECK_ITEMS_BY_TYPE,
    EQUIPMENT_TYPE_EXTINGUISHER,
    EQUIPMENT_TYPE_HYDRANT,
    create_fire_inspection,
    get_fire_equipment,
    get_fire_equipment_stats,
    sync_fire_equipment_ledger,
)

PAGE_KEY = "safety:emergency-accident:fire-equipment-inspection"

_SEEDED_RECORD_IDS = ["recE1", "recE2", "recH1", "recGone"]


def _mirror(record_id: str, table_id: str, fields: dict) -> SafetyPageTableMirrorRecord:
    return SafetyPageTableMirrorRecord(
        page_key=PAGE_KEY,
        table_id=table_id,
        record_id=record_id,
        fields=fields,
        search_text="",
    )


async def _seed(db: AsyncSession) -> None:
    # 先清理可能的残留（此前失败运行会留下已提交数据），保证播种幂等
    await _cleanup(db)
    # 灭火器子表：编号/部门/位置列名都在精确候选名单里
    db.add(
        _mirror(
            "recE1",
            "tblExt",
            {
                "灭火器编号": "MQC-001",
                "所属部门": "101一车间",
                "存放位置": "东侧通道口",
                "备注": "新换的压力表",
            },
        )
    )
    # 无精确列名：靠包含关键词兜底（编号 → 器材编号X）
    db.add(
        _mirror(
            "recE2",
            "tblExt",
            {
                "器材编号X": "MQC-002",
                "责任部门X": "102二车间",
                "具体位置X": "配电室门口",
            },
        )
    )
    # 消防栓：子表名带「消防栓」→ hydrant
    db.add(
        _mirror(
            "recH1",
            "tblHyd",
            {
                "消防栓编号": "XFS-101",
                "部门": "101一车间",
                "所在地点": "一楼楼梯口",
            },
        )
    )
    # 同步后从镜像消失 → 投影软删
    db.add(_mirror("recGone", "tblExt", {"灭火器编号": "MQC-GONE"}))
    await db.flush()


async def _cleanup(db: AsyncSession) -> None:
    await db.execute(
        delete(FireInspectionRecord).where(
            FireInspectionRecord.equipment_id.in_(
                select(FireEquipment.id).where(
                    FireEquipment.record_id.in_(_SEEDED_RECORD_IDS)
                )
            )
        )
    )
    await db.execute(
        delete(FireEquipment).where(
            FireEquipment.record_id.in_(_SEEDED_RECORD_IDS)
        )
    )
    await db.execute(
        delete(SafetyPageTableMirrorRecord).where(
            SafetyPageTableMirrorRecord.record_id.in_(_SEEDED_RECORD_IDS)
        )
    )
    await db.commit()


async def _equipment_by_record(
    db: AsyncSession, record_id: str
) -> FireEquipment | None:
    result = await db.execute(
        select(FireEquipment).where(FireEquipment.record_id == record_id)
    )
    return result.scalar_one_or_none()


@pytest.mark.asyncio
async def test_projection_maps_fields_and_soft_deletes_gone_mirror(
    db_session: AsyncSession,
) -> None:
    await _seed(db_session)
    try:
        result = await sync_fire_equipment_ledger(db_session)
        assert result["created"] == 4

        ext1 = await _equipment_by_record(db_session, "recE1")
        assert ext1 is not None
        assert ext1.equipment_type == EQUIPMENT_TYPE_EXTINGUISHER
        assert ext1.equipment_no == "MQC-001"
        assert ext1.department == "101一车间"
        assert ext1.location == "东侧通道口"
        assert ext1.fields["备注"] == "新换的压力表"

        # 无精确列名时按包含关键词兜底
        ext2 = await _equipment_by_record(db_session, "recE2")
        assert ext2 is not None
        assert ext2.equipment_no == "MQC-002"
        assert ext2.department == "102二车间"
        assert ext2.location == "配电室门口"

        # 子表名（此处回退为 table_id）不含消防栓时，字段列名可判型
        hydrant = await _equipment_by_record(db_session, "recH1")
        assert hydrant is not None
        assert hydrant.equipment_type == EQUIPMENT_TYPE_HYDRANT

        # 幂等重跑：无新增、无更新
        again = await sync_fire_equipment_ledger(db_session)
        assert again["created"] == 0
        assert again["updated"] == 0
        assert again["unchanged"] == 4

        # 镜像行消失后重跑 → 软删
        await db_session.execute(
            delete(SafetyPageTableMirrorRecord).where(
                SafetyPageTableMirrorRecord.record_id == "recGone"
            )
        )
        await db_session.commit()
        removed = await sync_fire_equipment_ledger(db_session)
        assert removed["removed"] == 1
        gone = await _equipment_by_record(db_session, "recGone")
        assert gone is not None and gone.is_deleted is True
    finally:
        await _cleanup(db_session)


@pytest.mark.asyncio
async def test_stats_counts_types_and_month_coverage(
    db_session: AsyncSession,
) -> None:
    baseline = await get_fire_equipment_stats(db_session)
    await _seed(db_session)
    try:
        await sync_fire_equipment_ledger(db_session)
        stats = await get_fire_equipment_stats(db_session)
        # 与基线对比，避免测试库其他残留数据影响断言
        assert stats["total"] == baseline["total"] + 4
        assert stats["extinguisher_count"] == baseline["extinguisher_count"] + 3
        assert stats["hydrant_count"] == baseline["hydrant_count"] + 1
        assert (
            stats["inspected_this_month"] == baseline["inspected_this_month"]
        )
        assert (
            stats["uninspected_this_month"]
            == baseline["uninspected_this_month"] + 4
        )
    finally:
        await _cleanup(db_session)


@pytest.mark.asyncio
async def test_create_inspection_full_card_pass_updates_equipment(
    db_session: AsyncSession,
) -> None:
    await _seed(db_session)
    try:
        await sync_fire_equipment_ledger(db_session)
        equipment = await _equipment_by_record(db_session, "recE1")
        assert equipment is not None
        items = [
            {"key": key, "result": "ok"}
            for key, _ in CHECK_ITEMS_BY_TYPE[EQUIPMENT_TYPE_EXTINGUISHER]
        ]
        record = await create_fire_inspection(
            db_session,
            equipment.id,
            items=items,
            abnormal_action=None,
            inspected_at=None,
            inspector_id=None,
            inspector_name="张三",
            source="scan",
        )
        assert record.result == "pass"
        assert record.inspector_name == "张三"
        assert record.equipment_no == "MQC-001"
        assert len(record.items) == 4
        # 提交的 label 由服务端检查卡回填
        assert record.items[0]["label"].startswith("灭火器钢体")

        refreshed = await get_fire_equipment(db_session, equipment.id)
        assert refreshed.last_inspected_at is not None
        assert refreshed.last_inspection_result == "pass"
    finally:
        await _cleanup(db_session)


@pytest.mark.asyncio
async def test_create_inspection_fail_collects_failed_items(
    db_session: AsyncSession,
) -> None:
    await _seed(db_session)
    try:
        await sync_fire_equipment_ledger(db_session)
        equipment = await _equipment_by_record(db_session, "recH1")
        assert equipment is not None
        checklist = CHECK_ITEMS_BY_TYPE[EQUIPMENT_TYPE_HYDRANT]
        items = [
            {
                "key": key,
                "result": "fail" if index == 2 else "ok",
                "remark": "水带卡口松动" if index == 2 else None,
            }
            for index, (key, _) in enumerate(checklist)
        ]
        record = await create_fire_inspection(
            db_session,
            equipment.id,
            items=items,
            abnormal_action="已报修，限期更换卡扣",
            inspected_at=None,
            inspector_id=None,
            inspector_name="李四",
            source="scan",
        )
        assert record.result == "fail"
        assert [item["key"] for item in record.failed_items] == [
            [key for key, _ in checklist][2]
        ]
        assert record.abnormal_action == "已报修，限期更换卡扣"
        assert record.items[2]["remark"] == "水带卡口松动"
    finally:
        await _cleanup(db_session)


@pytest.mark.asyncio
async def test_create_inspection_rejects_incomplete_card(
    db_session: AsyncSession,
) -> None:
    await _seed(db_session)
    try:
        await sync_fire_equipment_ledger(db_session)
        equipment = await _equipment_by_record(db_session, "recE1")
        assert equipment is not None
        items = [{"key": "body", "result": "ok"}]
        with pytest.raises(AppException) as exc:
            await create_fire_inspection(
                db_session,
                equipment.id,
                items=items,
                abnormal_action=None,
                inspected_at=None,
                inspector_id=None,
                inspector_name="张三",
                source="web",
            )
        assert exc.value.status_code == 400
        assert "未点检" in exc.value.message

        bad_key = [{"key": "not-exists", "result": "ok"}]
        with pytest.raises(AppException) as exc_bad:
            await create_fire_inspection(
                db_session,
                equipment.id,
                items=bad_key,
                abnormal_action=None,
                inspected_at=None,
                inspector_id=None,
                inspector_name="张三",
                source="web",
            )
        assert exc_bad.value.status_code == 400
    finally:
        await _cleanup(db_session)


@pytest.mark.asyncio
async def test_create_inspection_missing_equipment_returns_404(
    db_session: AsyncSession,
) -> None:
    from uuid import uuid4

    with pytest.raises(AppException) as exc:
        await create_fire_inspection(
            db_session,
            uuid4(),
            items=[{"key": "body", "result": "ok"}],
            abnormal_action=None,
            inspected_at=None,
            inspector_id=None,
            inspector_name="张三",
            source="web",
        )
    assert exc.value.status_code == 404


# ── 点检记录写回飞书 ──


class _FakeWritebackClient:
    """可编程的 Bitable fake：记录建表与写入调用。"""

    tables: list[dict[str, str]] = []
    created_tables: list[tuple[str, list[dict]]] = []
    next_record_id = "FeRec-1"
    fail_create = False

    def __init__(
        self, app_token: str | None = None, table_id: str | None = None
    ) -> None:
        self.app_token = app_token or ""
        self.table_id = table_id or ""

    async def list_tables(self, app_token: str | None = None) -> list[dict[str, str]]:
        return list(_FakeWritebackClient.tables)

    async def create_table(self, name, fields, *, app_token=None, **kwargs):
        _FakeWritebackClient.created_tables.append((name, fields))
        return "tblWB-New", None

    async def create_record_with_result(self, fields, table_id=None):
        if _FakeWritebackClient.fail_create:
            return None, "飞书错误"
        _FakeWritebackClient.records.append((table_id, fields))
        return _FakeWritebackClient.next_record_id, None


@pytest.fixture
def fake_writeback_client(monkeypatch):
    _FakeWritebackClient.tables = []
    _FakeWritebackClient.created_tables = []
    _FakeWritebackClient.records = []
    _FakeWritebackClient.next_record_id = "FeRec-1"
    _FakeWritebackClient.fail_create = False
    monkeypatch.setattr(
        fire_equipment_module, "SafetyBitableClient", _FakeWritebackClient
    )
    return _FakeWritebackClient


async def _seed_writeback_config(
    db: AsyncSession, *, writeback_table_id: str | None
) -> None:
    db.add(
        SafetyPageFeishuConfig(
            page_key=PAGE_KEY,
            app_token="appTokenX",
            table_id="tblMain",
            writeback_table_id=writeback_table_id,
        )
    )
    await db.flush()


async def _cleanup_config(db: AsyncSession) -> None:
    await db.execute(
        SafetyPageFeishuConfig.__table__.delete().where(
            SafetyPageFeishuConfig.page_key == PAGE_KEY
        )
    )
    await db.commit()


def test_writeback_fields_mapping() -> None:
    record = FireInspectionRecord(
        equipment_id=uuid4(),
        equipment_type=EQUIPMENT_TYPE_HYDRANT,
        equipment_no="XFS-101",
        department="101一车间",
        location="一楼楼梯口",
        items=[],
        result="fail",
        failed_items=[{"key": "hose", "label": "消防水带无损伤"}],
        abnormal_action="已报修",
        inspector_name="李四",
        inspected_at=datetime(2026, 10, 20, 3, 0, tzinfo=UTC),
        source="scan",
    )
    fields = fire_equipment_module._inspection_writeback_fields(record)
    assert fields["器材类型"] == "消防栓"
    assert fields["器材编号"] == "XFS-101"
    assert fields["检查结果"] == "不合格"
    assert fields["不合格项"] == "消防水带无损伤"
    assert fields["异常处理措施"] == "已报修"
    assert fields["点检人"] == "李四"
    assert fields["来源"] == "扫码"
    assert fields["点检日期"] == int(record.inspected_at.timestamp() * 1000)


@pytest.mark.asyncio
async def test_ensure_writeback_table_creates_and_reuses(
    db_session: AsyncSession, fake_writeback_client
) -> None:
    try:
        await _seed_writeback_config(db_session, writeback_table_id=None)

        result = await fire_equipment_module.ensure_writeback_table(db_session)
        assert result == {
            "table_id": "tblWB-New",
            "table_name": "点检记录",
            "created": True,
        }
        assert fake_writeback_client.created_tables[0][0] == "点检记录"
        spec_names = [
            f["field_name"] for f in fake_writeback_client.created_tables[0][1]
        ]
        assert spec_names[0] == "点检日期"

        # 已绑定且表存在 → 复用不重建
        fake_writeback_client.tables = [
            {"table_id": "tblWB-New", "name": "点检记录"}
        ]
        again = await fire_equipment_module.ensure_writeback_table(db_session)
        assert again["created"] is False
        assert again["table_id"] == "tblWB-New"
    finally:
        await _cleanup_config(db_session)


@pytest.mark.asyncio
async def test_ensure_writeback_table_requires_binding(
    db_session: AsyncSession, fake_writeback_client
) -> None:
    with pytest.raises(AppException) as exc:
        await fire_equipment_module.ensure_writeback_table(db_session)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_retry_pending_inspection_writebacks(
    db_session: AsyncSession, fake_writeback_client
) -> None:
    await _seed(db_session)
    try:
        await _seed_writeback_config(
            db_session, writeback_table_id="tblWB-New"
        )
        await fire_equipment_module.sync_fire_equipment_ledger(db_session)
        equipment = await _equipment_by_record(db_session, "recE1")
        assert equipment is not None
        items = [
            {"key": key, "result": "ok"}
            for key, _ in CHECK_ITEMS_BY_TYPE[EQUIPMENT_TYPE_EXTINGUISHER]
        ]
        record = await create_fire_inspection(
            db_session,
            equipment.id,
            items=items,
            abnormal_action=None,
            inspected_at=None,
            inspector_id=None,
            inspector_name="张三",
            source="scan",
        )
        assert record.feishu_record_id is None

        result = await fire_equipment_module.retry_pending_inspection_writebacks(
            db_session
        )
        assert result["written"] == 1
        await db_session.refresh(record)
        assert record.feishu_record_id == "FeRec-1"
        table_id, fields = fake_writeback_client.records[0]
        assert table_id == "tblWB-New"
        assert fields["器材编号"] == "MQC-001"

        # 幂等：已回写的不再补写
        again = await fire_equipment_module.retry_pending_inspection_writebacks(
            db_session
        )
        assert again["pending"] == 0
    finally:
        await _cleanup(db_session)
        await _cleanup_config(db_session)


@pytest.mark.asyncio
async def test_projection_prefers_sub_table_name_for_primary(
    db_session: AsyncSession,
) -> None:
    """主绑定表在 sub_tables 里携带真实表名时，投影用它而不是「主表」。"""
    await _seed(db_session)
    try:
        db_session.add(
            SafetyPageFeishuConfig(
                page_key=PAGE_KEY,
                app_token="appTokenX",
                table_id="tblExt",
                sub_tables=[
                    {
                        "table_id": "tblExt",
                        "tab_name": "201-2车间（MC）",
                        "hidden_field_names": [],
                    }
                ],
            )
        )
        await db_session.commit()
        await fire_equipment_module.sync_fire_equipment_ledger(db_session)
        ext1 = await _equipment_by_record(db_session, "recE1")
        assert ext1 is not None
        assert ext1.tab_name == "201-2车间（MC）"
    finally:
        await _cleanup(db_session)
        await _cleanup_config(db_session)


@pytest.mark.asyncio
async def test_projection_skips_writeback_table_rows(
    db_session: AsyncSession,
) -> None:
    """回写表被误勾进页签子表时，其记录不会投影成器材。"""
    await _seed(db_session)
    try:
        # 把器材来源表 tblExt 同时当作回写表 → 该表全部记录应被跳过，
        # 其它来源表（tblHyd）不受影响
        await _seed_writeback_config(db_session, writeback_table_id="tblExt")
        result = await fire_equipment_module.sync_fire_equipment_ledger(db_session)
        assert result["created"] == 1
        assert await _equipment_by_record(db_session, "recE1") is None
        assert await _equipment_by_record(db_session, "recE2") is None
        assert await _equipment_by_record(db_session, "recH1") is not None
    finally:
        await _cleanup(db_session)
        await _cleanup_config(db_session)


# ── 仪表盘聚合 ──


_DASHBOARD_RECORD_IDS = ["recD1", "recD2", "recD3"]


async def _cleanup_dashboard(db: AsyncSession) -> None:
    await db.execute(
        delete(FireInspectionRecord).where(
            FireInspectionRecord.equipment_id.in_(
                select(FireEquipment.id).where(
                    FireEquipment.record_id.in_(_DASHBOARD_RECORD_IDS)
                )
            )
        )
    )
    await db.execute(
        delete(FireEquipment).where(
            FireEquipment.record_id.in_(_DASHBOARD_RECORD_IDS)
        )
    )
    await db.execute(
        delete(SafetyPageTableMirrorRecord).where(
            SafetyPageTableMirrorRecord.record_id.in_(_DASHBOARD_RECORD_IDS)
        )
    )
    await db.commit()


async def _seed_dashboard_fixtures(db: AsyncSession) -> None:
    from datetime import date, timedelta

    # 先清掉此前失败运行可能留下的残行（recD0 只作占位，播种后即删）
    await _cleanup(db)
    await _cleanup_dashboard(db)
    today = date.today()
    db.add(_mirror("recD0", "tblExt", {"灭火器编号": "MQC-D0"}))
    await db.execute(
        delete(SafetyPageTableMirrorRecord).where(
            SafetyPageTableMirrorRecord.record_id == "recD0"
        )
    )
    await db.flush()
    # 追加带有效日期的记录：-3 天（过期）/ +5 天（7 天内）/ +20 天（30 天内）
    db.add(
        _mirror(
            "recD1",
            "tblExt",
            {
                "灭火器编号": "MQC-D1",
                "有效日期": (today - timedelta(days=3)).isoformat(),
            },
        )
    )
    db.add(
        _mirror(
            "recD2",
            "tblExt",
            {
                "灭火器编号": "MQC-D2",
                "有效日期": (today + timedelta(days=5)).isoformat(),
            },
        )
    )
    db.add(
        _mirror(
            "recD3",
            "tblExt",
            {
                "灭火器编号": "MQC-D3",
                "有效日期": (today + timedelta(days=20)).isoformat(),
            },
        )
    )
    await db.flush()
    await fire_equipment_module.sync_fire_equipment_ledger(db)


@pytest.mark.asyncio
async def test_dashboard_aggregates_expiry_trend_coverage(
    db_session: AsyncSession,
) -> None:
    await _seed_dashboard_fixtures(db_session)
    try:
        # 给 MQC-D2 提交一次点检（当月），撑起趋势与覆盖
        equipment = await _equipment_by_record(db_session, "recD2")
        assert equipment is not None
        items = [
            {"key": key, "result": "ok"}
            for key, _ in CHECK_ITEMS_BY_TYPE[EQUIPMENT_TYPE_EXTINGUISHER]
        ]
        await create_fire_inspection(
            db_session,
            equipment.id,
            items=items,
            abnormal_action=None,
            inspected_at=None,
            inspector_id=None,
            inspector_name="张三",
            source="scan",
        )

        dashboard = await fire_equipment_module.get_fire_equipment_dashboard(
            db_session
        )
        summary = dashboard["expiry_summary"]
        assert summary["overdue"] == 1
        assert summary["within_7"] == 1
        assert summary["within_15"] == 1
        assert summary["within_30"] == 2

        # 趋势：当月至少 1 条（历史月份可能为 0，长度固定 6）
        assert len(dashboard["trend"]) == 6
        assert dashboard["trend"][-1]["count"] >= 1

        # 覆盖：tblExt 一张表 3 台（recD1-3）、本月已检 1
        coverage = {
            row["tab_name"]: row for row in dashboard["workshop_coverage"]
        }
        assert coverage["tblExt"]["total"] == 3
        assert coverage["tblExt"]["inspected"] == 1
    finally:
        await _cleanup(db_session)
        await _cleanup_dashboard(db_session)
