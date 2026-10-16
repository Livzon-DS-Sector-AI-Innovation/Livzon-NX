"""关键作业重算（服务层）数据库测试：按规则批量刷新台账标记。"""

import pytest

from app.modules.safety.models import SpecialOperationReport
from app.modules.safety.service.special_operation_report import (
    SpecialOperationReportService,
)


async def _add(db, report_no: str, op_type: str, level: str, notes: str = "") -> None:
    db.add(
        SpecialOperationReport(
            report_no=report_no,
            operation_type=op_type,
            operation_level=level,
            status="approved",
            notes=notes or None,
            is_critical=False,
            is_critical_reason=None,
        )
    )
    await db.flush()


@pytest.mark.asyncio
async def test_recalculate_critical_flags_applies_level_and_notes_rules(
    db_session,
) -> None:
    report_nos = ["RC-1", "RC-2", "RC-3", "RC-4", "RC-5", "RC-6"]
    await _add(db_session, "RC-1", "hot_work", "grade1")
    await _add(db_session, "RC-2", "height_work", "grade1")
    await _add(db_session, "RC-3", "lifting", "special")
    await _add(db_session, "RC-4", "hot_work", "grade2")
    await _add(
        db_session,
        "RC-5",
        "hot_work",
        "grade2",
        notes="施工单位：机修；是否防爆区：是",
    )
    await _add(
        db_session,
        "RC-6",
        "lifting",
        "grade2",
        notes="是否提级管理：是；是否防爆区：否",
    )

    try:
        service = SpecialOperationReportService(db_session)
        result = await service.recalculate_critical_flags()

        assert result["total"] == 6
        assert result["critical"] == 5

        rows = {
            row.report_no: row
            for row in (
                await db_session.execute(
                    SpecialOperationReport.__table__.select().where(
                        SpecialOperationReport.report_no.in_(report_nos)
                    )
                )
            ).all()
        }
        assert rows["RC-1"].is_critical is True
        assert "一级动火作业" in (rows["RC-1"].is_critical_reason or "")
        assert "一级高处作业" in (rows["RC-2"].is_critical_reason or "")
        assert "特级吊装作业" in (rows["RC-3"].is_critical_reason or "")
        assert rows["RC-4"].is_critical is False
        assert rows["RC-4"].is_critical_reason is None
        assert "涉及防爆区" in (rows["RC-5"].is_critical_reason or "")
        assert "作业提级管理" in (rows["RC-6"].is_critical_reason or "")
    finally:
        # 重算方法内部 commit，超出 fixture 回滚范围：测试自行清理，避免污染测试库
        await db_session.execute(
            SpecialOperationReport.__table__.delete().where(
                SpecialOperationReport.report_no.in_(report_nos)
            )
        )
        await db_session.commit()
