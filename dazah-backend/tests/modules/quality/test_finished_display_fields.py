from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.modules.quality.service.inspection_finished_material import (
    get_finished_display_fields,
)


def test_picks_batch_quantity_and_spec() -> None:
    fields = [
        "批号",
        "年",
        "月",
        "日",
        "包装规格",
        "批量kg",
        "含量（干品）:97.0%-103.0%",
        "总杂质:≤1.00%",
        "报告日期",
        "报告单号",
        "报告单",
    ]
    result = get_finished_display_fields("qc_finished_internal", fields)
    assert "批号" in result
    assert "批量kg" in result
    assert "包装规格" in result
    # 检测项保留（含量/杂质在仪表盘 metric 交集内）
    assert "含量（干品）:97.0%-103.0%" in result
    assert "总杂质:≤1.00%" in result
    # 非展示列不出现
    assert "年" not in result
    assert "报告单号" not in result


def test_falls_back_to_quantity_when_no_batch_qty_field() -> None:
    fields = ["批号", "数量kg", "外观:白色", "含量:≥70%", "总杂质:≤5.0%"]
    result = get_finished_display_fields("qc_finished_crude", fields)
    assert "批号" in result
    assert "数量kg" in result


def test_metric_fallback_uses_content_impurity_keywords() -> None:
    fields = [
        "批号",
        "批量kg",
        "含量（干品）:98.0%-102.0%",
        "总杂质:≤0.70%",
        "干燥失重:≤0.50%",
        "外观:粉末",
    ]
    # 该实体无仪表盘配置（客户子表），交集为空 → 按含量/杂质兜底
    result = get_finished_display_fields("qc_finished_mpa_emcure_k2", fields)
    assert "含量（干品）:98.0%-102.0%" in result
    assert "总杂质:≤0.70%" in result
    assert "干燥失重:≤0.50%" not in result
    assert "外观:粉末" not in result


def test_metric_cap_at_five_with_priority_order() -> None:
    fields = [
        "批号",
        "数量kg",
        "杂质1:≤0.5%",
        "杂质2:≤0.5%",
        "杂质3:≤0.5%",
        "未知杂质:≤0.1%",
        "单一最大杂质:≤0.5%",
        "总杂质:≤1.0%",
        "含量（干品）:97.0%-103.0%",
    ]
    # 使用无仪表盘配置的客户子表实体，走「含量/杂质」兜底 + 上限 5
    result = get_finished_display_fields("qc_finished_mpa_emcure_k2", fields)
    metrics = [f for f in result if ("含量" in f or "杂质" in f)]
    # 检验项目最多 5 个
    assert len(metrics) <= 5
    # 优先级：含量 → 总杂质 → 单一/最大杂质 → 未知杂质 → 其他
    assert metrics[0] == "含量（干品）:97.0%-103.0%"
    assert metrics[1] == "总杂质:≤1.0%"
    assert metrics[2] == "单一最大杂质:≤0.5%"
    assert metrics[3] == "未知杂质:≤0.1%"
    assert metrics[4] == "杂质1:≤0.5%"


def _fields_meta_fake():
    return {
        "items": [
            {"record_id": "rec_1", "批号": "B-001", "含量（干品）:97.0%-103.0%": "99.2"}
        ],
        "total": 1,
        "page": 1,
        "page_size": 20,
        "fields": ["批号", "含量（干品）:97.0%-103.0%", "总杂质:≤1.00%", "年"],
    }


@pytest.mark.anyio
async def test_finished_records_list_meta_includes_display_fields(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.quality import api as quality_api

    monkeypatch.setattr(
        quality_api.inspection_feishu,
        "list_finished_by_entity",
        AsyncMock(return_value=_fields_meta_fake()),
    )

    resp = await client.get(
        "/api/v1/quality/inspection-finished/mpa/records?entity_code=qc_finished_internal"
    )
    assert resp.status_code == 200
    meta = resp.json()["meta"]
    assert "display_fields" in meta
    assert "批号" in meta["display_fields"]
    assert "含量（干品）:97.0%-103.0%" in meta["display_fields"]
    assert "年" not in meta["display_fields"]


def test_spec_falls_back_to_package_unit_field() -> None:
    fields = [
        "批号",
        "批量kg",
        "kg/Drum",
        "Drum",
        "含量（干品）:97.0%-103.0%",
        "总杂质:≤1.00%",
    ]
    result = get_finished_display_fields("qc_finished_internal", fields)
    assert "批号" in result
    assert "批量kg" in result
    assert "kg/Drum" in result
    assert "Drum" not in result
