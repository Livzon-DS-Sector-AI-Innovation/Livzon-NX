"""跨车间检修汇总：KPI、车间对比、高频榜单、趋势与接口层测试。"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.equipment.models.repair_ledger import (
    RepairFeishuConfig,
    RepairRecord,
    RepairSyncState,
)
from app.modules.equipment.service import repair_ledger as service


def _code() -> str:
    return f"ts{uuid.uuid4().hex[:6]}"


async def _purge(db: AsyncSession, codes: list[str]) -> None:
    await db.rollback()
    for model in (RepairRecord, RepairSyncState, RepairFeishuConfig):
        await db.execute(delete(model).where(model.workshop_code.in_(codes)))
    await db.commit()


def _record(code: str, record_id: str, **kwargs: object) -> RepairRecord:
    return RepairRecord(
        workshop_code=code,
        record_id=f"{code}-{record_id}",
        **kwargs,
    )


async def _seed(db: AsyncSession, code_a: str, code_b: str) -> None:
    db.add_all(
        [
            # A 车间：3 条（同一设备 2 次、两个故障写法）
            _record(
                code_a,
                "a1",
                equipment_text="离心泵A",
                repaired_at=date(2026, 11, 20),
                fault_desc="机封漏水",
                persons=[{"name": "张三", "open_id": "ou_a", "avatar_url": "https://img/a.png"}],
                result="正常",
            ),
            _record(
                code_a,
                "a2",
                equipment_text="离心泵A",
                repaired_at=date(2026, 11, 18),
                fault_desc="机封 漏水",
                person_text="张三、李四",
                result="待处理",
            ),
            _record(
                code_a,
                "a3",
                equipment_text="2#振动筛",
                repaired_at=date(2026, 11, 10),
                fault_desc="轴承坏",
                persons=[{"name": "李四", "open_id": "ou_b", "avatar_url": None}],
                result="停机",
            ),
            # B 车间：1 条，设备名与 A 相同但不跨车间合并
            _record(
                code_b,
                "b1",
                equipment_text="离心泵A",
                repaired_at=date(2026, 11, 19),
                fault_desc="机封漏水",
                person_text="王五",
                result="正常",
            ),
        ]
    )
    db.add(
        RepairFeishuConfig(
            workshop_code=code_a,
            app_token=f"base-{code_a}",
            table_id=f"tbl-{code_a}",
            is_enabled=True,
        )
    )
    db.add(
        RepairSyncState(
            workshop_code=code_a,
            total_rows=3,
            last_status="success",
        )
    )
    await db.flush()


async def test_summary_aggregates_cross_workshop_kpis_and_rankings(
    db_session: AsyncSession,
) -> None:
    code_a, code_b = _code(), _code()
    await _seed(db_session, code_a, code_b)
    try:
        data = await service.summary(db_session)

        kpi = data["kpi"]
        assert kpi["total_count"] == 4
        # 设备按「车间+设备名」去重：A 泵、A 筛、B 泵
        assert kpi["equipment_count"] == 3
        assert kpi["workshop_count"] == 2
        assert kpi["person_count"] == 3  # 张三 / 李四 / 王五
        assert kpi["abnormal_count"] == 2  # 待处理 + 停机
        assert kpi["daily_average"] > 0
        assert kpi["previous_total_count"] is None
        assert kpi["change_rate"] is None

        by_code = {row["workshop_code"]: row for row in data["workshops"]}
        assert by_code[code_a]["repair_count"] == 3
        assert by_code[code_a]["equipment_count"] == 2
        assert by_code[code_a]["person_count"] == 2
        assert by_code[code_a]["abnormal_count"] == 2
        assert by_code[code_a]["status"] == "normal"
        assert by_code[code_a]["configured"] is True
        assert by_code[code_a]["last_repaired_at"] == date(2026, 11, 20)
        assert by_code[code_b]["repair_count"] == 1
        assert by_code[code_b]["status"] == "not_configured"

        # 高频设备：A 泵 2 次排第一；B 的同名泵单独一行
        top = data["top_equipment"]
        assert top[0]["workshop_code"] == code_a
        assert top[0]["equipment_text"] == "离心泵A"
        assert top[0]["times"] == 2
        assert any(
            item["workshop_code"] == code_b and item["equipment_text"] == "离心泵A"
            for item in top
        )

        # 故障原文去空白后合并：机封漏水 3 次、涉及 2 台（车间+设备）设备
        faults = {item["fault_desc"]: item for item in data["top_faults"]}
        assert faults["机封漏水"]["times"] == 3
        assert faults["机封漏水"]["equipment_count"] == 2
        # 故障按车间拆分次数：A 车间 2 次、B 车间 1 次
        fault_workshops = {
            item["workshop_code"]: item["times"]
            for item in faults["机封漏水"]["workshops"]
        }
        assert fault_workshops == {code_a: 2, code_b: 1}

        # 人员：张三 2 次且带结构化头像；同名不跨车间合并之外的姓名也在列
        persons = {item["name"]: item for item in data["top_persons"]}
        assert persons["张三"]["times"] == 2
        assert persons["张三"]["avatar_url"] == "https://img/a.png"
        assert persons["李四"]["times"] == 2
        assert persons["王五"]["times"] == 1
        # 人员也按车间拆分次数
        assert {
            item["workshop_code"]: item["times"]
            for item in persons["张三"]["workshops"]
        } == {code_a: 2}
        assert {
            item["workshop_code"]: item["times"]
            for item in persons["王五"]["workshops"]
        } == {code_b: 1}

        # 无日期范围时趋势按月
        assert data["trend_granularity"] == "month"
        month_a = next(
            item
            for item in data["trend"]
            if item["period"] == "2026-11" and item["workshop_code"] == code_a
        )
        assert month_a["count"] == 3
    finally:
        await _purge(db_session, [code_a, code_b])


async def test_summary_filters_by_workshop_and_computes_change_rate(
    db_session: AsyncSession,
) -> None:
    code_a, code_b = _code(), _code()
    await _seed(db_session, code_a, code_b)
    try:
        data = await service.summary(
            db_session,
            workshops=[code_a],
            date_from=date(2026, 11, 19),
            date_to=date(2026, 11, 20),
        )
        # 只命中 A 的 11-20 一条（11-18 在区间外）
        assert data["kpi"]["total_count"] == 1
        assert all(
            row["workshop_code"] == code_a for row in data["workshops"]
        )
        # 上一周期 11-17~11-18 命中 A 的 11-18 一条 → 环比 0%
        assert data["kpi"]["previous_total_count"] == 1
        assert data["kpi"]["change_rate"] == 0.0
        assert data["trend_granularity"] == "week"
    finally:
        await _purge(db_session, [code_a, code_b])


async def test_summary_rejects_when_rows_exceed_limit(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    code = _code()
    db_session.add_all(
        [
            _record(code, "1", equipment_text="泵A", repaired_at=date(2026, 11, 1)),
            _record(code, "2", equipment_text="泵B", repaired_at=date(2026, 11, 2)),
        ]
    )
    await db_session.flush()
    monkeypatch.setattr(service, "_SUMMARY_MAX_ROWS", 1)
    try:
        with pytest.raises(AppException, match="超过"):
            await service.summary(db_session, workshops=[code])
    finally:
        await _purge(db_session, [code])


async def test_records_and_export_accept_multiple_workshops(
    _equipment_session: AsyncSession, client: AsyncClient
) -> None:
    code_a, code_b = _code(), _code()
    _equipment_session.add_all(
        [
            _record(
                code_a,
                "m1",
                equipment_text="离心泵A",
                repaired_at=date(2026, 11, 20),
            ),
            _record(
                code_b,
                "m2",
                equipment_text="离心泵B",
                repaired_at=date(2026, 11, 19),
            ),
        ]
    )
    await _equipment_session.flush()
    try:
        response = await client.get(
            "/api/v1/equipment/repair/records",
            params={"workshops": f"{code_a},{code_b}"},
        )
        assert response.status_code == 200
        assert response.json()["meta"]["total"] == 2

        exported = await client.get(
            "/api/v1/equipment/repair/export",
            params={"workshops": f"{code_a},{code_b}"},
        )
        assert exported.status_code == 200
        assert len(exported.content) > 100
    finally:
        await _purge(_equipment_session, [code_a, code_b])


async def test_summary_endpoint_returns_payload_and_validates_codes(
    _equipment_session: AsyncSession, client: AsyncClient
) -> None:
    code = _code()
    _equipment_session.add(
        _record(
            code,
            "e1",
            equipment_text="离心泵A",
            repaired_at=date(2026, 11, 20),
            fault_desc="机封漏水",
            person_text="张三",
            result="正常",
        )
    )
    await _equipment_session.flush()
    try:
        response = await client.get(
            f"/api/v1/equipment/repair/summary?workshops={code}"
        )
        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["kpi"]["total_count"] == 1
        assert payload["workshops"][0]["workshop_code"] == code
        assert payload["top_equipment"][0]["equipment_text"] == "离心泵A"
        assert payload["top_faults"][0]["fault_desc"] == "机封漏水"
        assert payload["top_persons"][0]["name"] == "张三"

        invalid = await client.get(
            "/api/v1/equipment/repair/summary?workshops=BAD!"
        )
        assert invalid.status_code == 400
    finally:
        await _purge(_equipment_session, [code])
