"""仪器档案：按设备编号跨表匹配维保/维修/校验/合同（mock 镜像读取）。"""

from __future__ import annotations

from typing import Any

import pytest

from app.core.exceptions import NotFoundException
from app.modules.quality.service import instrument_profile as profile

pytestmark = pytest.mark.anyio


def _page(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "items": items,
        "total": len(items),
        "page": 1,
        "page_size": 500,
        "configured": True,
        "fields": [],
        "last_sync_time": None,
    }


def _install_mirror(
    monkeypatch: pytest.MonkeyPatch, pages: dict[str, list[Any]]
) -> None:
    async def fake_list(
        db: Any, entity_code: str, *, page: int = 1, page_size: int = 500
    ):
        return _page(pages.get(entity_code, []))

    monkeypatch.setattr(profile, "list_instrument_mirror", fake_list)

    async def fake_load_cycle_page(db: Any, entity_code: str):
        return _page([])

    monkeypatch.setattr(
        "app.modules.quality.service.maintenance_schedule._load_page",
        fake_load_cycle_page,
    )


async def test_profile_matches_code_across_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = {
        "qc_instr_equipment": [
            {
                "record_id": "rec-eq",
                "设备名称": "气相色谱仪",
                "设备编号": "QC-1-2-010",
                "设备状态": "完好",
            },
        ],
        # 维护保养记录一格多编号（顿号分隔）：按编号分词后应命中
        "qc_instr_maintenance": [
            {
                "record_id": "m1",
                "设备编号": "QC-1-2-003、QC-1-2-010",
                "是否完成": "是",
            },
            {"record_id": "m2", "仪器编号": "QC-1-2-099", "是否完成": "否"},
        ],
        "qc_instr_repair": [
            {
                "record_id": "r1",
                "设备编号": "QC-1-2-010",
                "维修内容": "更换六通阀",
            },
            {"record_id": "r2", "设备编号": "QC-2-2-001", "维修内容": "无关设备"},
        ],
        "qc_instr_calibration": [
            {
                "record_id": "c1",
                "仪器、设备编号": "QC-1-2-010",
                "校验有效期": "46406",
            },
        ],
        "qc_instr_cal_plan": [
            {"record_id": "p1", "仪器、设备编号": "QC-1-2-010", "剩余天数": "12"},
        ],
        "qc_instr_cal_external": [
            {"record_id": "x1", "器具编号": "1916001004291"},
        ],
        # 维保合同：按「涉及仪器及编号」匹配（支持一格多台）
        "qc_instr_contracts": [
            {
                "record_id": "k1",
                "设备维保合同": "外协合同A",
                "涉及仪器及编号": "QC-1-2-010、QC-1-2-011",
            },
            {
                "record_id": "k2",
                "设备维保合同": "外协合同B",
                "涉及仪器及编号": "QC-2-2-001",
            },
            {
                "record_id": "k3",
                "设备维保合同": "未填写编号的合同",
            },
        ],
    }
    _install_mirror(monkeypatch, pages)

    result = await profile.get_instrument_profile(None, "rec-eq")

    assert result["matched_code"] == "QC-1-2-010"
    assert result["equipment"]["设备名称"] == "气相色谱仪"
    assert [row["record_id"] for row in result["maintenance"]] == ["m1"]
    assert [row["record_id"] for row in result["repairs"]] == ["r1"]
    summary_ids = [
        row["record_id"] for row in result["calibration"]["internal_summary"]
    ]
    assert summary_ids == ["c1"]
    plan_ids = [row["record_id"] for row in result["calibration"]["internal_plan"]]
    assert plan_ids == ["p1"]
    assert result["calibration"]["external"] == []
    # 合同按「涉及仪器及编号」匹配：只返回命中的合同
    assert [row["record_id"] for row in result["contracts"]] == ["k1"]
    assert result["contracts_total"] == 3


async def test_profile_missing_code_returns_all_sections_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = {
        "qc_instr_equipment": [{"record_id": "rec-eq", "设备名称": "无编号设备"}],
        "qc_instr_maintenance": [{"record_id": "m1", "设备编号": "QC-1-2-010"}],
        "qc_instr_contracts": [
            {"record_id": "k1", "涉及仪器及编号": "QC-1-2-010"},
        ],
    }
    _install_mirror(monkeypatch, pages)

    result = await profile.get_instrument_profile(None, "rec-eq")
    assert result["matched_code"] == ""
    assert result["maintenance"] == []
    assert result["contracts"] == []


async def test_profile_unknown_record_raises_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_mirror(monkeypatch, {"qc_instr_equipment": []})
    with pytest.raises(NotFoundException):
        await profile.get_instrument_profile(None, "missing")
