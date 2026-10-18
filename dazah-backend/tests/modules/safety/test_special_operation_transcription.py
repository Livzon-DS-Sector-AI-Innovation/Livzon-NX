"""特殊作业台账自动转录测试（独立测试库）：映射、幂等与关键作业联动。"""

import pytest

from app.modules.safety.models import (
    SafetyPageTableMirrorRecord,
    SpecialOperationReport,
)
from app.modules.safety.service.special_operation_transcription import (
    sync_special_operation_ledger,
)


def _mirror(record_id: str, fields: dict) -> SafetyPageTableMirrorRecord:
    return SafetyPageTableMirrorRecord(
        page_key="safety:ops-safety:special-danger-work",
        record_id=record_id,
        fields=fields,
        search_text="",
    )


async def _seed(db) -> None:
    db.add(
        _mirror(
            "recA",
            {
                "申请编号": {"text": "TR-1", "link": "https://f/1"},
                "申请状态": "已通过",
                "作业类型": "动火作业",
                "作业分级": "一级",
                "部门": "203车间",
                "作业地点": "三楼",
                "作业内容": "焊接冷凝器",
                "作业开始时间": "2026-10-15",
                "作业结束时间": "2026-10-15",
                "发起人": [{"name": "张三"}],
                "监护人": [{"name": "李四"}],
                "特殊作业人员（姓名+工种）": "王五/焊工",
                "完成时间": "2026-10-15",
                "施工单位": "机修",
                "是否防爆区": "否",
                "作业是否提级管理": "是",
            },
        )
    )
    db.add(
        _mirror(
            "recB",
            {
                "申请编号": {"text": "TR-2"},
                "申请状态": "审批中",
                "作业类型": "高处作业",
                "作业分级": "二级",
            },
        )
    )
    # 无作业类型 → 跳过
    db.add(_mirror("recC", {"申请编号": {"text": "TR-3"}, "作业类型": ""}))
    # 飞书已删除 → 跳过
    db.add(
        _mirror(
            "recD",
            {
                "申请编号": {"text": "TR-4"},
                "作业类型": "动火作业",
                "申请状态": "已删除",
            },
        )
    )
    # 无申请编号 → FEISHU 兜底编号
    db.add(
        _mirror("recEFGHIJKL", {"作业类型": "吊装作业", "作业分级": "特级"})
    )
    await db.flush()


async def _rows(db) -> dict[str, SpecialOperationReport]:
    result = await db.execute(
        SpecialOperationReport.__table__.select().where(
            SpecialOperationReport.report_no.in_(
                ["TR-1", "TR-2", "TR-3", "TR-4", "FEISHU-recEFGHIJKL"]
            )
        )
    )
    return {row.report_no: row for row in result.all()}


@pytest.mark.asyncio
async def test_transcribe_maps_fields_and_recalculates_critical(db_session) -> None:
    await _seed(db_session)
    try:
        result = await sync_special_operation_ledger(db_session)

        assert result["created"] == 3
        assert result["skipped"] == 2
        # 关键作业联动：TR-1 一级动火+提级管理 → 关键；TR-2 二级高处 → 非关键
        assert result["critical"] == 2

        rows = await _rows(db_session)
        first = rows["TR-1"]
        assert first.operation_type == "hot_work"
        assert first.operation_level == "grade1"
        assert first.status == "approved"
        assert first.department == "203车间"
        assert first.work_leader_name == "张三"
        assert first.guardian_name == "李四"
        assert "是否提级管理：是" in (first.notes or "")
        assert "一级动火作业" in (first.is_critical_reason or "")
        assert "作业提级管理" in (first.is_critical_reason or "")
        assert first.approved_at is not None

        second = rows["TR-2"]
        assert second.operation_type == "height_work"
        assert second.status == "submitted"
        assert second.is_critical is False

        assert rows["FEISHU-recEFGHIJKL"].operation_type == "lifting"
        assert "TR-3" not in rows and "TR-4" not in rows
    finally:
        await db_session.execute(
            SpecialOperationReport.__table__.delete().where(
                SpecialOperationReport.report_no.in_(
                    ["TR-1", "TR-2", "TR-3", "TR-4", "FEISHU-recEFGHIJKL"]
                )
            )
        )
        await db_session.execute(
            SafetyPageTableMirrorRecord.__table__.delete().where(
                SafetyPageTableMirrorRecord.record_id.in_(
                    ["recA", "recB", "recC", "recD", "recEFGHIJKL"]
                )
            )
        )
        await db_session.commit()


@pytest.mark.asyncio
async def test_transcribe_is_idempotent_and_skips_unchanged(db_session) -> None:
    await _seed(db_session)
    try:
        first = await sync_special_operation_ledger(db_session)
        assert first["created"] == 3
        assert first["unchanged"] == 0

        # 重跑：全部命中已存在且值未变化 → 0 新增 0 更新
        second = await sync_special_operation_ledger(db_session)
        assert second["created"] == 0
        assert second["updated"] == 0
        assert second["unchanged"] == 3

        # 镜像字段变化（审批中 → 已通过）→ 只更新该条
        mirror = (

                await db_session.execute(
                    SafetyPageTableMirrorRecord.__table__.select().where(
                        SafetyPageTableMirrorRecord.record_id == "recB"
                    )
                )

        ).one()
        await db_session.execute(
            SafetyPageTableMirrorRecord.__table__.update()
            .where(SafetyPageTableMirrorRecord.record_id == "recB")
            .values(
                fields={
                    **mirror.fields,
                    "申请状态": "已通过",
                    "完成时间": "2026-10-15",
                }
            )
        )
        await db_session.commit()

        third = await sync_special_operation_ledger(db_session)
        assert third["created"] == 0
        assert third["updated"] == 1
        assert third["unchanged"] == 2
        assert (await _rows(db_session))["TR-2"].status == "approved"
    finally:
        await db_session.execute(
            SpecialOperationReport.__table__.delete().where(
                SpecialOperationReport.report_no.in_(
                    ["TR-1", "TR-2", "TR-3", "TR-4", "FEISHU-recEFGHIJKL"]
                )
            )
        )
        await db_session.execute(
            SafetyPageTableMirrorRecord.__table__.delete().where(
                SafetyPageTableMirrorRecord.record_id.in_(
                    ["recA", "recB", "recC", "recD", "recEFGHIJKL"]
                )
            )
        )
        await db_session.commit()
