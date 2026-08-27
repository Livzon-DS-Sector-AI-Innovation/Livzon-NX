"""Inspection Feishu pages service - dashboard configuration constants.

All dashboard entity codes, entity configs, source labels, and recipient
overrides for the finished product trend dashboard.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
#  成品趋势仪表盘
# ═══════════════════════════════════════════

FINISHED_DASHBOARD_BATCH_FIELD = "批号"
FINISHED_DASHBOARD_PRODUCT_DEPARTMENT_ENTITY_CODE = "oos_oot_product_department"
MPA_INTERNAL_DASHBOARD_ENTITY_CODE = "qc_finished_internal"
MPA_HIGH_SPEC_DASHBOARD_ENTITY_CODE = "qc_finished_high_spec"
MPA_DASHBOARD_DEFAULT_ENTITY_CODE = MPA_INTERNAL_DASHBOARD_ENTITY_CODE
MPA_DASHBOARD_ENTITY_CODE = (
    MPA_INTERNAL_DASHBOARD_ENTITY_CODE  # backward-compatible alias
)
MPA_DASHBOARD_SOURCE_LABEL = "霉酚酸（内控）"  # backward-compatible alias
MPA_DASHBOARD_OOT_PRODUCT_CODES: dict[str, str] = {
    MPA_INTERNAL_DASHBOARD_ENTITY_CODE: "MC-INTERNAL",
    MPA_HIGH_SPEC_DASHBOARD_ENTITY_CODE: "MC-HIGH",
}
MPA_DASHBOARD_ENTITY_CONFIGS: dict[str, dict[str, Any]] = {
    MPA_INTERNAL_DASHBOARD_ENTITY_CODE: {
        "source_label": "霉酚酸（内控）",
        "metric_configs": (
            {
                "metric_key": "干燥失重:≤0.50%",
                "metric_label": "干燥失重:≤0.50%",
                "oot_item_name": "干燥失重",
                "spec_lines": [{"label": "标准上限", "value": 0.5}],
            },
            {
                "metric_key": "熔点:140.0~144.0℃",
                "metric_label": "熔点:140.0~144.0℃",
                "oot_item_name": "熔点",
                "spec_lines": [
                    {"label": "标准下限", "value": 140.0},
                    {"label": "标准上限", "value": 144.0},
                ],
            },
            {
                "metric_key": "炽灼残渣:≤0.10%",
                "metric_label": "炽灼残渣:≤0.10%",
                "oot_item_name": "炽灼残渣",
                "spec_lines": [{"label": "标准上限", "value": 0.10}],
            },
            {
                "metric_key": "总杂质:≤1.00%",
                "metric_label": "总杂质:≤1.00%",
                "oot_item_name": "总杂质",
                "spec_lines": [{"label": "标准上限", "value": 1.0}],
            },
            {
                "metric_key": "最大单一杂质:≤0.50%",
                "metric_label": "单一最大杂质:≤0.50%",
                "oot_item_name": "单一最大杂质",
                "spec_lines": [{"label": "标准上限", "value": 0.5}],
            },
            {
                "metric_key": "含量（干品）:97.0%-103.0%",
                "metric_label": "含量（干品）:97.0%-103.0%",
                "oot_item_name": "含量（干品）",
                "spec_lines": [
                    {"label": "标准下限", "value": 97.0},
                    {"label": "标准上限", "value": 103.0},
                ],
            },
            {
                "metric_key": "乙酸丁酯:≤2000ppm",
                "metric_label": "残留溶剂（乙酸丁酯）:≤2000ppm",
                "oot_item_name": "残留溶剂（乙酸丁酯）",
                "spec_lines": [{"label": "标准上限", "value": 2000.0}],
            },
        ),
    },
    MPA_HIGH_SPEC_DASHBOARD_ENTITY_CODE: {
        "source_label": "霉酚酸（高规）",
        "metric_configs": (
            {
                "metric_key": "干燥失重:≤0.50%",
                "metric_label": "干燥失重:≤0.50%",
                "oot_item_name": "干燥失重",
                "spec_lines": [{"label": "标准上限", "value": 0.5}],
            },
            {
                "metric_key": "熔点:140.0-144.0℃",
                "metric_label": "熔点:140.0~144.0℃",
                "oot_item_name": "熔点",
                "spec_lines": [
                    {"label": "标准下限", "value": 140.0},
                    {"label": "标准上限", "value": 144.0},
                ],
            },
            {
                "metric_key": "炽灼残渣:≤0.10%",
                "metric_label": "炽灼残渣:≤0.10%",
                "oot_item_name": "炽灼残渣",
                "spec_lines": [{"label": "标准上限", "value": 0.10}],
            },
            {
                "metric_key": "总杂质:≤0.70%",
                "metric_label": "总杂质:≤0.70%",
                "oot_item_name": "总杂质",
                "spec_lines": [{"label": "标准上限", "value": 0.70}],
            },
            {
                "metric_key": "最大单一杂质:≤0.070%",
                "metric_label": "最大单一杂质:≤0.070%",
                "oot_item_name": "最大单一杂质",
                "spec_lines": [{"label": "标准上限", "value": 0.070}],
            },
            {
                "metric_key": "含量（干品）:98.0%-102.0%",
                "metric_label": "含量（干品）:98.0%-102.0%",
                "oot_item_name": "含量（干品）",
                "spec_lines": [
                    {"label": "标准下限", "value": 98.0},
                    {"label": "标准上限", "value": 102.0},
                ],
            },
            {
                "metric_key": "乙酸丁酯:≤2000ppm",
                "metric_label": "残留溶剂（乙酸丁酯）:≤2000ppm",
                "oot_item_name": "残留溶剂（乙酸丁酯）",
                "spec_lines": [{"label": "标准上限", "value": 2000.0}],
            },
        ),
    },
}

MVT_DASHBOARD_ENTITY_CODE = "qc_finished_mvt"
MVT_DASHBOARD_SOURCE_LABEL = "美伐他汀（DMF）"
MVT_DASHBOARD_OOT_PRODUCT_CODE = "MV"
MVT_DASHBOARD_METRIC_CONFIGS: tuple[dict[str, Any], ...] = (
    {
        "metric_key": "比旋度（按干燥品计算）：+265°~ +290°",
        "metric_label": "比旋度：+265°~+290°",
        "oot_item_name": "比旋度",
        "spec_lines": [
            {"label": "标准下限", "value": 265.0},
            {"label": "标准上限", "value": 290.0},
        ],
    },
    {
        "metric_key": "干燥失重：≤0.5%",
        "metric_label": "干燥失重：≤0.5%",
        "oot_item_name": "干燥失重",
        "spec_lines": [{"label": "标准上限", "value": 0.5}],
    },
    {
        "metric_key": "炽灼残渣：≤0.1%",
        "metric_label": "炽灼残渣：≤0.1%",
        "oot_item_name": "炽灼残渣",
        "spec_lines": [{"label": "标准上限", "value": 0.1}],
    },
    {
        "metric_key": "总杂质：≤3.0%",
        "metric_label": "总杂质：≤3.0%",
        "oot_item_name": "总杂质",
        "spec_lines": [{"label": "标准上限", "value": 3.0}],
    },
    {
        "metric_key": "单一最大杂质：≤0.6%",
        "metric_label": "单一最大杂质：≤0.6%",
        "oot_item_name": "单一最大杂质",
        "spec_lines": [{"label": "标准上限", "value": 0.6}],
    },
    {
        "metric_key": "脱水美伐他汀：≤2.0%",
        "metric_label": "脱水美伐他汀：≤2.0%",
        "oot_item_name": "脱水美伐他汀",
        "spec_lines": [{"label": "标准上限", "value": 2.0}],
    },
    {
        "metric_key": "杂质A：≤0.15%",
        "metric_label": "杂质A：≤0.15%",
        "oot_item_name": "杂质A",
        "spec_lines": [{"label": "标准上限", "value": 0.15}],
    },
    {
        "metric_key": "含量（干品）：≥95.0%",
        "metric_label": "含量（干品）：≥95.0%",
        "oot_item_name": "含量（干品）",
        "spec_lines": [{"label": "标准下限", "value": 95.0}],
    },
    {
        "metric_key": "丙酮：≤2000ppm",
        "metric_label": "丙酮：≤2000ppm",
        "oot_item_name": "丙酮",
        "spec_lines": [{"label": "标准上限", "value": 2000.0}],
    },
    {
        "metric_key": "正己烷：≤290ppm",
        "metric_label": "正己烷：≤290ppm",
        "oot_item_name": "正己烷",
        "spec_lines": [{"label": "标准上限", "value": 290.0}],
    },
    {
        "metric_key": "甲苯：≤89ppm",
        "metric_label": "甲苯：≤89ppm",
        "oot_item_name": "甲苯",
        "spec_lines": [{"label": "标准上限", "value": 89.0}],
    },
)

LFT_EP_DASHBOARD_ENTITY_CODE = "qc_finished_lft_ep"
LFT_USP_DASHBOARD_ENTITY_CODE = "qc_finished_lft_usp"
LFT_DASHBOARD_DEFAULT_ENTITY_CODE = LFT_EP_DASHBOARD_ENTITY_CODE
LFT_DASHBOARD_OOT_PRODUCT_CODES: dict[str, str] = {
    LFT_USP_DASHBOARD_ENTITY_CODE: "LV",
}
LFT_DASHBOARD_ENTITY_CONFIGS: dict[str, dict[str, Any]] = {
    LFT_EP_DASHBOARD_ENTITY_CODE: {
        "source_label": "洛伐他汀（EP）",
        "metric_configs": (
            {
                "metric_key": "比旋度（无水物）：‘＋325°～＋340°",
                "metric_label": "比旋度（无水物）：+325°~+340°",
                "oot_item_name": "比旋度",
                "spec_lines": [
                    {"label": "标准下限", "value": 325.0},
                    {"label": "标准上限", "value": 340.0},
                ],
            },
            {
                "metric_key": "水分：≤0.5%",
                "metric_label": "水分：≤0.5%",
                "oot_item_name": "干燥失重",
                "spec_lines": [{"label": "标准上限", "value": 0.5}],
            },
            {
                "metric_key": "硫酸盐灰分：≤0.2%",
                "metric_label": "硫酸盐灰分：≤0.2%",
                "oot_item_name": "炽灼残渣",
                "spec_lines": [{"label": "标准上限", "value": 0.2}],
            },
            {
                "metric_key": "杂质E（4，4a二氢洛伐他汀）：≤0.5%",
                "metric_label": "杂质E：≤0.5%",
                "spec_lines": [{"label": "标准上限", "value": 0.5}],
            },
            {
                "metric_key": "杂质A（美伐他汀）：≤0.3%",
                "metric_label": "杂质A：≤0.3%",
                "spec_lines": [{"label": "标准上限", "value": 0.3}],
            },
            {
                "metric_key": "杂质B（羟基酸洛伐他汀）：≤0.3%",
                "metric_label": "杂质B：≤0.3%",
                "spec_lines": [{"label": "标准上限", "value": 0.3}],
            },
            {
                "metric_key": "杂质C（脱水洛伐他汀）：≤0.3%",
                "metric_label": "杂质C：≤0.3%",
                "spec_lines": [{"label": "标准上限", "value": 0.3}],
            },
            {
                "metric_key": "杂质D（洛伐他汀二聚物）：≤0.3%",
                "metric_label": "杂质D：≤0.3%",
                "spec_lines": [{"label": "标准上限", "value": 0.3}],
            },
            {
                "metric_key": "杂质F：≤0.15%",
                "metric_label": "杂质F：≤0.15%",
                "spec_lines": [{"label": "标准上限", "value": 0.15}],
            },
            {
                "metric_key": "总杂质：≤1.0%",
                "metric_label": "总杂质：≤1.0%",
                "spec_lines": [{"label": "标准上限", "value": 1.0}],
            },
            {
                "metric_key": "未知杂质：≤0.10%",
                "metric_label": "未知杂质：≤0.10%",
                "spec_lines": [{"label": "标准上限", "value": 0.10}],
            },
            {
                "metric_key": "含量（无水物）：97.0%～102.0%",
                "metric_label": "含量（无水物）：97.0%～102.0%",
                "oot_item_name": "含量（干品）",
                "spec_lines": [
                    {"label": "标准下限", "value": 97.0},
                    {"label": "标准上限", "value": 102.0},
                ],
            },
            {
                "metric_key": "丙酮：≤5000ppm",
                "metric_label": "丙酮：≤5000ppm",
                "oot_item_name": "丙酮",
                "spec_lines": [],
            },
            {
                "metric_key": "甲苯：≤890ppm",
                "metric_label": "甲苯：≤890ppm",
                "oot_item_name": "甲苯",
                "spec_lines": [{"label": "标准上限", "value": 890.0}],
            },
        ),
    },
    LFT_USP_DASHBOARD_ENTITY_CODE: {
        "source_label": "洛伐他汀（USP）",
        "metric_configs": (
            {
                "metric_key": "比旋度（按无水计）：+324°~+338°",
                "metric_label": "比旋度（按无水计）：+324°~+338°",
                "oot_item_name": "比旋度",
                "spec_lines": [
                    {"label": "标准下限", "value": 324.0},
                    {"label": "标准上限", "value": 338.0},
                ],
            },
            {
                "metric_key": "干燥失重：≤0.3%",
                "metric_label": "干燥失重：≤0.3%",
                "oot_item_name": "干燥失重",
                "spec_lines": [{"label": "标准上限", "value": 0.3}],
            },
            {
                "metric_key": "炽灼残渣：≤0.2%",
                "metric_label": "炽灼残渣：≤0.2%",
                "oot_item_name": "炽灼残渣",
                "spec_lines": [{"label": "标准上限", "value": 0.2}],
            },
            {
                "metric_key": "有关物质A：≤0.5%",
                "metric_label": "有关物质A：≤0.5%",
                "oot_item_name": "有关物质A",
                "spec_lines": [{"label": "标准上限", "value": 0.5}],
            },
            {
                "metric_key": "总有关杂质：≤1.0%",
                "metric_label": "总有关杂质：≤1.0%",
                "oot_item_name": "总有关杂质",
                "spec_lines": [{"label": "标准上限", "value": 1.0}],
            },
            {
                "metric_key": "其他单一杂质：≤0.2%",
                "metric_label": "其他单一杂质：≤0.2%",
                "oot_item_name": "其他单一杂质",
                "spec_lines": [{"label": "标准上限", "value": 0.2}],
            },
            {
                "metric_key": "含量（干品）：98.5%~101.0%",
                "metric_label": "含量（干品）：98.5%~101.0%",
                "oot_item_name": "含量（干品）",
                "spec_lines": [
                    {"label": "标准下限", "value": 98.5},
                    {"label": "标准上限", "value": 101.0},
                ],
            },
            {
                "metric_key": "丙酮：≤5000ppm",
                "metric_label": "丙酮：≤5000ppm",
                "oot_item_name": "丙酮",
                "spec_lines": [],
            },
            {
                "metric_key": "甲苯：≤890ppm",
                "metric_label": "甲苯：≤890ppm",
                "oot_item_name": "甲苯",
                "spec_lines": [{"label": "标准上限", "value": 890.0}],
            },
        ),
    },
}

DLS_GB_DASHBOARD_ENTITY_CODE = "qc_finished_dor_gb"
DLS_VET_DASHBOARD_ENTITY_CODE = "qc_finished_dor_vet"
DLS_DASHBOARD_DEFAULT_ENTITY_CODE = DLS_GB_DASHBOARD_ENTITY_CODE
DLS_DASHBOARD_OOT_PRODUCT_CODE = "DR"
DLS_DASHBOARD_ENTITY_CONFIGS: dict[str, dict[str, Any]] = {
    DLS_GB_DASHBOARD_ENTITY_CODE: {
        "source_label": "多拉菌素（GB）",
        "metric_configs": (
            {
                "metric_key": "比旋度（按无水计）：+55°~ +65°",
                "metric_label": "比旋度（按无水计）：+55°~+65°",
                "oot_item_name": "比旋度（按无水计）",
                "spec_lines": [
                    {"label": "标准下限", "value": 55.0},
                    {"label": "标准上限", "value": 65.0},
                ],
            },
            {
                "metric_key": "水分：≤3.0%",
                "metric_label": "水分：≤3.0%",
                "oot_item_name": "水分",
                "spec_lines": [{"label": "标准上限", "value": 3.0}],
            },
            {
                "metric_key": "炽灼残渣：≤0.1%",
                "metric_label": "炽灼残渣：≤0.1%",
                "oot_item_name": "炽灼残渣",
                "spec_lines": [{"label": "标准上限", "value": 0.1}],
            },
            {
                "metric_key": "杂质2：≤1.0%",
                "metric_label": "杂质2：≤1.0%",
                "oot_item_name": "杂质2",
                "spec_lines": [{"label": "标准上限", "value": 1.0}],
            },
            {
                "metric_key": "杂质3：≤1.2%",
                "metric_label": "杂质3：≤1.2%",
                "oot_item_name": "杂质3",
                "spec_lines": [{"label": "标准上限", "value": 1.2}],
            },
            {
                "metric_key": "杂质4：≤0.5%",
                "metric_label": "杂质4：≤0.5%",
                "oot_item_name": "杂质4",
                "spec_lines": [{"label": "标准上限", "value": 0.5}],
            },
            {
                "metric_key": "杂质5：≤0.5%",
                "metric_label": "杂质5：≤0.5%",
                "oot_item_name": "杂质5",
                "spec_lines": [{"label": "标准上限", "value": 0.5}],
            },
            {
                "metric_key": "杂质6：≤0.50%",
                "metric_label": "杂质6：≤0.50%",
                "oot_item_name": "杂质6",
                "spec_lines": [{"label": "标准上限", "value": 0.5}],
            },
            {
                "metric_key": "杂质7：≤0.8%",
                "metric_label": "杂质7：≤0.8%",
                "oot_item_name": "杂质7",
                "spec_lines": [{"label": "标准上限", "value": 0.8}],
            },
            {
                "metric_key": "其他单个杂质：≤0.50%",
                "metric_label": "其他单个杂质：≤0.50%",
                "oot_item_name": "其他单个杂质",
                "spec_lines": [{"label": "标准上限", "value": 0.5}],
            },
            {
                "metric_key": "总杂质：≤5.0%",
                "metric_label": "总杂质：≤5.0%",
                "oot_item_name": "总杂质",
                "spec_lines": [{"label": "标准上限", "value": 5.0}],
            },
            {
                "metric_key": "含量（按无水计）：95.0%~102.0%",
                "metric_label": "含量（按无水计）：95.0%~102.0%",
                "oot_item_name": "含量（按无水计）",
                "spec_lines": [
                    {"label": "标准下限", "value": 95.0},
                    {"label": "标准上限", "value": 102.0},
                ],
            },
            {
                "metric_key": "BHT：200~1000ppm",
                "metric_label": "BHT：200~1000ppm",
                "oot_item_name": "BHT",
                "spec_lines": [
                    {"label": "标准下限", "value": 200.0},
                    {"label": "标准上限", "value": 1000.0},
                ],
            },
            {
                "metric_key": "甲醇：≤3000ppm",
                "metric_label": "甲醇：≤3000ppm",
                "oot_item_name": "甲醇",
                "spec_lines": [],
            },
            {
                "metric_key": "乙醇：≤5000ppm",
                "metric_label": "乙醇：≤5000ppm",
                "spec_lines": [],
            },
            {
                "metric_key": "丙酮：≤5000ppm",
                "metric_label": "丙酮：≤5000ppm",
                "oot_item_name": "丙酮",
                "spec_lines": [],
            },
            {
                "metric_key": "需氧菌总数 ≤1000cfu/g",
                "metric_label": "需氧菌总数：≤1000cfu/g",
                "oot_item_name": "需氧菌总数",
                "spec_lines": [{"label": "标准上限", "value": 1000.0}],
            },
            {
                "metric_key": "霉菌酵母菌数：≤100cfu/g",
                "metric_label": "霉菌、酵母菌数：≤100cfu/g",
                "oot_item_name": "霉菌、酵母菌数",
                "spec_lines": [{"label": "标准上限", "value": 100.0}],
            },
        ),
    },
    DLS_VET_DASHBOARD_ENTITY_CODE: {
        "source_label": "多拉菌素（兽药）",
        "metric_configs": (
            {
                "metric_key": "比旋度：+58°~+63°",
                "metric_label": "比旋度：+58°~+63°",
                "oot_item_name": "比旋度（按无水计）",
                "spec_lines": [
                    {"label": "标准下限", "value": 58.0},
                    {"label": "标准上限", "value": 63.0},
                ],
            },
            {
                "metric_key": "阿维菌素：≤3.0%",
                "metric_label": "阿维菌素：≤3.0%",
                "spec_lines": [{"label": "标准上限", "value": 3.0}],
            },
            {
                "metric_key": "总杂质：≤5.0%",
                "metric_label": "总杂质：≤5.0%",
                "oot_item_name": "总杂质",
                "spec_lines": [{"label": "标准上限", "value": 5.0}],
            },
            {
                "metric_key": "水分：≤3.0%",
                "metric_label": "水分：≤3.0%",
                "oot_item_name": "水分",
                "spec_lines": [{"label": "标准上限", "value": 3.0}],
            },
            {
                "metric_key": "炽灼残渣：≤0.5%",
                "metric_label": "炽灼残渣：≤0.5%",
                "oot_item_name": "炽灼残渣",
                "spec_lines": [{"label": "标准上限", "value": 0.5}],
            },
            {
                "metric_key": "含量测定（按无水物计算）：≥95.0%",
                "metric_label": "含量测定（按无水物计算）：≥95.0%",
                "oot_item_name": "含量（按无水计）",
                "spec_lines": [{"label": "标准下限", "value": 95.0}],
            },
            {
                "metric_key": "甲醇：≤3000ppm",
                "metric_label": "甲醇：≤3000ppm",
                "oot_item_name": "甲醇",
                "spec_lines": [],
            },
            {
                "metric_key": "乙醇：≤5000ppm",
                "metric_label": "乙醇：≤5000ppm",
                "spec_lines": [],
            },
            {
                "metric_key": "丙酮：≤5000ppm",
                "metric_label": "丙酮：≤5000ppm",
                "oot_item_name": "丙酮",
                "spec_lines": [],
            },
            {
                "metric_key": "需氧菌总数：≤1000cfu/g",
                "metric_label": "需氧菌总数：≤1000cfu/g",
                "oot_item_name": "需氧菌总数",
                "spec_lines": [{"label": "标准上限", "value": 1000.0}],
            },
            {
                "metric_key": "霉菌酵母菌数：≤100cfu/g",
                "metric_label": "霉菌、酵母菌数：≤100cfu/g",
                "oot_item_name": "霉菌、酵母菌数",
                "spec_lines": [{"label": "标准上限", "value": 100.0}],
            },
        ),
    },
}

LKMS_VET_DASHBOARD_ENTITY_CODE = "qc_finished_lkms_vet"
LKMS_VET_DASHBOARD_SOURCE_LABEL = "林可霉素（兽药）"
LKMS_VET_DASHBOARD_OOT_PRODUCT_CODE = "LN"
LKMS_VET_DASHBOARD_METRIC_CONFIGS: tuple[dict[str, Any], ...] = (
    {
        "metric_key": "酸度:PH值应为3.0-5.5",
        "metric_label": "酸度:3.0-5.5",
        "oot_item_name": "酸度",
        "spec_lines": [
            {"label": "标准下限", "value": 3.0},
            {"label": "标准上限", "value": 5.5},
        ],
    },
    {
        "metric_key": "其它单一最大杂质:≤1.0%",
        "metric_label": "其他单一最大杂质:≤1.0%",
        "oot_item_name": "其他单一最大杂质",
        "spec_lines": [{"label": "标准上限", "value": 1.0}],
    },
    {
        "metric_key": "总杂质:≤2.0%",
        "metric_label": "总杂质:≤2.0%",
        "oot_item_name": "总杂质",
        "spec_lines": [{"label": "标准上限", "value": 2.0}],
    },
    {
        "metric_key": "林可霉素:B≤5.0%",
        "metric_label": "林可霉素B:≤5.0%",
        "oot_item_name": "林可霉素B",
        "spec_lines": [{"label": "标准上限", "value": 5.0}],
    },
    {
        "metric_key": "水分:3.0%-6.0%",
        "metric_label": "水分:3.0%-6.0%",
        "oot_item_name": "水分",
        "spec_lines": [
            {"label": "标准下限", "value": 3.0},
            {"label": "标准上限", "value": 6.0},
        ],
    },
    {
        "metric_key": "炽灼残渣:≤0.5%",
        "metric_label": "炽灼残渣:≤0.5%",
        "oot_item_name": "炽灼残渣",
        "spec_lines": [{"label": "标准上限", "value": 0.5}],
    },
    {
        "metric_key": "丙酮:≤2000ppm",
        "metric_label": "残留溶剂（丙酮）:≤2000ppm",
        "oot_item_name": "残留溶剂（丙酮）",
        "spec_lines": [],
    },
    {
        "metric_key": "仲辛醇:≤500ppm",
        "metric_label": "残留溶剂（仲辛醇）:≤500ppm",
        "oot_item_name": "残留溶剂（仲辛醇）",
        "spec_lines": [{"label": "标准上限", "value": 500.0}],
    },
    {
        "metric_key": "含量测定:≥82.5%",
        "metric_label": "含量（无水物）:≥82.5%",
        "oot_item_name": "含量（无水物）",
        "spec_lines": [{"label": "标准下限", "value": 82.5}],
    },
)

BBAS_FCC14_DASHBOARD_ENTITY_CODE = "qc_finished_fcc14"
BBAS_HANGUANG_K1_DASHBOARD_ENTITY_CODE = "qc_finished_bbas_hanguang_k1"
BBAS_DASHBOARD_DEFAULT_ENTITY_CODE = BBAS_FCC14_DASHBOARD_ENTITY_CODE
BBAS_DASHBOARD_ENTITY_CONFIGS: dict[str, dict[str, Any]] = {
    BBAS_FCC14_DASHBOARD_ENTITY_CODE: {
        "source_label": "FCC14",
        "metric_configs": (
            {
                "metric_key": "酸度（pH）：5.4-6.0",
                "metric_label": "酸度（pH）：5.4-6.0",
                "spec_lines": [
                    {"label": "标准下限", "value": 5.4},
                    {"label": "标准上限", "value": 6.0},
                ],
            },
            {
                "metric_key": "比旋度：-33.2°~-35.2°",
                "metric_label": "比旋度：-33.2°~-35.2°",
                "spec_lines": [
                    {"label": "标准上限", "value": -33.2},
                    {"label": "标准下限", "value": -35.2},
                ],
            },
            {
                "metric_key": "含量（干燥品计）：98.5%-101.5%",
                "metric_label": "含量（干燥品计）：98.5%-101.5%",
                "spec_lines": [
                    {"label": "标准下限", "value": 98.5},
                    {"label": "标准上限", "value": 101.5},
                ],
            },
        ),
    },
    BBAS_HANGUANG_K1_DASHBOARD_ENTITY_CODE: {
        "source_label": "汉光（K1）",
        "metric_configs": (
            {
                "metric_key": "含量（以干基计）：98.5%-101.0%",
                "metric_label": "含量（以干基计）：98.5%-101.0%",
                "spec_lines": [
                    {"label": "标准下限", "value": 98.5},
                    {"label": "标准上限", "value": 101.0},
                ],
            },
            {
                "metric_key": "比旋度：-35.0°~-33.5°",
                "metric_label": "比旋度：-35.0°~-33.5°",
                "spec_lines": [
                    {"label": "标准下限", "value": -35.0},
                    {"label": "标准上限", "value": -33.5},
                ],
            },
            {
                "metric_key": "pH（1%水溶液）：5.4-6.0",
                "metric_label": "pH（1%水溶液）：5.4-6.0",
                "spec_lines": [
                    {"label": "标准下限", "value": 5.4},
                    {"label": "标准上限", "value": 6.0},
                ],
            },
            {
                "metric_key": "透光率：≥98.0%",
                "metric_label": "透光率：≥98.0%",
                "spec_lines": [{"label": "标准下限", "value": 98.0}],
            },
        ),
    },
}

TRYPTOPHAN_POWDER_DASHBOARD_ENTITY_CODE = "qc_finished_trp_powder"
TRYPTOPHAN_GRANULE_DASHBOARD_ENTITY_CODE = "qc_finished_trp_granule"
TRYPTOPHAN_DASHBOARD_DEFAULT_ENTITY_CODE = TRYPTOPHAN_GRANULE_DASHBOARD_ENTITY_CODE
TRYPTOPHAN_DASHBOARD_ENTITY_CONFIGS: dict[str, dict[str, Any]] = {
    TRYPTOPHAN_POWDER_DASHBOARD_ENTITY_CODE: {
        "source_label": "色氨酸粉末",
        "metric_configs": (
            {
                "metric_key": "含量(以 C11H12N2O2 计)(干基): ≥98.0%",
                "metric_label": "含量(计干基): ≥98.0%",
                "spec_lines": [{"label": "标准下限", "value": 98.0}],
            },
            {
                "metric_key": "比旋度:-29.0°～-32.8°",
                "metric_label": "比旋度:-29.0°~-32.8°",
                "spec_lines": [
                    {"label": "标准上限", "value": -29.0},
                    {"label": "标准下限", "value": -32.8},
                ],
            },
            {
                "metric_key": "干燥失重：≤0.5%",
                "metric_label": "干燥失重：≤0.5%",
                "spec_lines": [{"label": "标准上限", "value": 0.5}],
            },
            {
                "metric_key": "粗灰分：≤0.5%",
                "metric_label": "粗灰分：≤0.5%",
                "spec_lines": [{"label": "标准上限", "value": 0.5}],
            },
            {
                "metric_key": "pH (1%水溶液):5.0～7.0",
                "metric_label": "pH（1%水溶液）：5.0-7.0",
                "spec_lines": [
                    {"label": "标准下限", "value": 5.0},
                    {"label": "标准上限", "value": 7.0},
                ],
            },
        ),
    },
    TRYPTOPHAN_GRANULE_DASHBOARD_ENTITY_CODE: {
        "source_label": "色氨酸颗粒",
        "metric_configs": (
            {
                "metric_key": "含量(以 C11H12N2O2 计)(干基): ≥98.0%",
                "metric_label": "含量(计干基): ≥98.0%",
                "spec_lines": [{"label": "标准下限", "value": 98.0}],
            },
            {
                "metric_key": "干燥失重：≤1.0%",
                "metric_label": "干燥失重：≤1.0%",
                "spec_lines": [{"label": "标准上限", "value": 1.0}],
            },
            {
                "metric_key": "粗灰分：≤1.0%",
                "metric_label": "粗灰分：≤1.0%",
                "spec_lines": [{"label": "标准上限", "value": 1.0}],
            },
            {
                "metric_key": "pH (1%水溶液):4.5～7.0",
                "metric_label": "pH（1%水溶液）：4.5-7.0",
                "spec_lines": [
                    {"label": "标准下限", "value": 4.5},
                    {"label": "标准上限", "value": 7.0},
                ],
            },
        ),
    },
}

FORMULATIONS_FLU_DASHBOARD_ENTITY_CODE = "qc_finished_flu_powder"
FORMULATIONS_FEN_DASHBOARD_ENTITY_CODE = "qc_finished_fen_powder"
FORMULATIONS_DASHBOARD_DEFAULT_ENTITY_CODE = FORMULATIONS_FLU_DASHBOARD_ENTITY_CODE
FORMULATIONS_DASHBOARD_ENTITY_CONFIGS: dict[str, dict[str, Any]] = {
    FORMULATIONS_FLU_DASHBOARD_ENTITY_CODE: {
        "source_label": "2%氟苯尼考预混剂",
        "metric_configs": (
            {
                "metric_key": "干燥失重：≤10.0%",
                "metric_label": "干燥失重：≤10.0%",
                "spec_lines": [{"label": "标准上限", "value": 10.0}],
            },
            {
                "metric_key": "含量测定：90.0%~110.0%",
                "metric_label": "含量测定：90.0%~110.0%",
                "spec_lines": [
                    {"label": "标准下限", "value": 90.0},
                    {"label": "标准上限", "value": 110.0},
                ],
            },
        ),
    },
    FORMULATIONS_FEN_DASHBOARD_ENTITY_CODE: {
        "source_label": "5%芬苯达唑粉",
        "metric_configs": (
            {
                "metric_key": "干燥失重：≤2.5%",
                "metric_label": "干燥失重：≤2.5%",
                "spec_lines": [{"label": "标准上限", "value": 2.5}],
            },
            {
                "metric_key": "含量测定：95.0%~105.0%",
                "metric_label": "含量测定：95.0%~105.0%",
                "spec_lines": [
                    {"label": "标准下限", "value": 95.0},
                    {"label": "标准上限", "value": 105.0},
                ],
            },
        ),
    },
}

WATER_PURE_DASHBOARD_ENTITY_CODE = "qc_finished_pure_water"
WATER_DASHBOARD_DEFAULT_ENTITY_CODE = WATER_PURE_DASHBOARD_ENTITY_CODE
WATER_DASHBOARD_ENTITY_CONFIGS: dict[str, dict[str, Any]] = {
    WATER_PURE_DASHBOARD_ENTITY_CODE: {
        "source_label": "纯化水",
        "metric_configs": (
            {
                "metric_key": "电导率:符合规定",
                "metric_label": "电导率:符合规定",
                "spec_lines": [],
            },
            {
                "metric_key": "TOC:\n≤0.5mg/L",
                "metric_label": "TOC：≤0.5mg/L",
                "spec_lines": [{"label": "标准上限", "value": 0.5}],
            },
            {
                "metric_key": "不挥发物:≤1mg/100ml",
                "metric_label": "不挥发物:≤1mg/100ml",
                "spec_lines": [{"label": "标准上限", "value": 1.0}],
            },
            {
                ("metric_key"): (
                    "微生物限度:\n需氧菌每1ml不得过100cfu；警戒限度为每"
                    "1ml不得过 50cfu；纠偏限度不得过80cfu。"
                ),
                "metric_label": "微生物限度",
                "spec_lines": [
                    {"label": "警戒限度", "value": 50.0},
                    {"label": "纠偏限度", "value": 80.0},
                    {"label": "标准上限", "value": 100.0},
                ],
            },
        ),
    },
}

FINISHED_DASHBOARD_RECIPIENT_OVERRIDES: dict[str, tuple[dict[str, str], ...]] = {
    MPA_INTERNAL_DASHBOARD_ENTITY_CODE: (
        {"name": "陈连平"},
        {"name": "席晓"},
    ),
    MPA_HIGH_SPEC_DASHBOARD_ENTITY_CODE: (
        {"name": "陈连平"},
        {"name": "席晓"},
    ),
    MVT_DASHBOARD_ENTITY_CODE: (
        {"name": "罗勇"},
        {"name": "周方圆"},
    ),
    LFT_EP_DASHBOARD_ENTITY_CODE: (
        {"name": "罗勇"},
        {"name": "周方圆"},
    ),
    LFT_USP_DASHBOARD_ENTITY_CODE: (
        {"name": "罗勇"},
        {"name": "周方圆"},
    ),
    DLS_GB_DASHBOARD_ENTITY_CODE: (
        {"name": "梁友辉"},
        {"name": "席晓"},
    ),
    DLS_VET_DASHBOARD_ENTITY_CODE: (
        {"name": "梁友辉"},
        {"name": "席晓"},
    ),
    LKMS_VET_DASHBOARD_ENTITY_CODE: (
        {"name": "刘伟"},
        {"name": "严红玲"},
    ),
}
