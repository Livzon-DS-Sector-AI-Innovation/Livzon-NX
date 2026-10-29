"""职业健康检测报告解析引擎测试（纯函数 + 夹具 PDF 全流程 + LLM 兜底 mock）。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

import app.modules.safety.service.oh_detection_report as oh_module
from app.core.llm.exceptions import LLMConfigError
from app.modules.safety.service.oh_detection_report import (
    OhDetectionParseError,
    ParsedReport,
    _detect_layout,
    _extract_metadata,
    _llm_parse_table,
    _map_dual_table,
    _map_field_table,
    _map_heat_table,
    _map_mac_table,
    _map_noise_table,
    _map_silica_table,
    _map_verdict,
    _measured,
    _parse_limit,
    _split_header,
    _TableFragment,
    clear_parse_cache,
    parse_report,
)

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "oh_detection_mini.pdf"


# ---------------------------------------------------------------------------
# 基础纯函数
# ---------------------------------------------------------------------------


def test_measured_keeps_below_detection_raw() -> None:
    assert _measured("＜0.44") == ("＜0.44", None)
    assert _measured("0.44") == ("0.44", 0.44)
    assert _measured("") == ("", None)


def test_map_verdict_variants() -> None:
    assert _map_verdict("未超标") == ("compliant", False)
    assert _map_verdict("超标") == ("exceed", False)
    assert _map_verdict("未超标（噪声作业岗位）") == ("compliant", True)
    assert _map_verdict("超标（噪声作业岗位）") == ("exceed", True)
    assert _map_verdict("40h等效声级85") == ("unknown", False)


def test_parse_limit_takes_last_number() -> None:
    assert _parse_limit("40h等效声级85dB(A)") == 85.0
    assert _parse_limit("5000") == 5000.0
    assert _parse_limit("") is None


def test_detect_layout_known_kinds() -> None:
    assert _detect_layout("表5-1 工作场所游离二氧化硅检测结果一览表", "") == "silica"
    assert _detect_layout("表5-18 噪声测量结果一览表", "") == "noise"
    assert _detect_layout("表5-19 工频电场测量结果一览表", "") == "field"
    assert _detect_layout("表5-20 高温测量结果一览表", "") == "heat"
    assert _detect_layout("表5-2 定点粉尘（总尘）", "PC-TWAPE") == "dust"
    assert _detect_layout("表5-6 硫酸", "PC-TWAPC-STEL") == "twa_stel"
    assert _detect_layout("表5-4 氢氧化钠", "MAC采样点") == "mac_single"
    assert _detect_layout("未知表格", "无特征") == "unknown"


def test_split_header_separates_and_drops_notes() -> None:
    grid = [
        ["序号", "车间", "岗位", "检测项目"],
        ["1", "101车间", "配料", "谷物粉尘"],
        ["备注", "超标判定依据：根据GBZ2.1-2019规定", "", ""],
    ]
    header, body = _split_header(grid)
    assert header == [grid[0]]
    assert body == [grid[1]]


# ---------------------------------------------------------------------------
# 版式映射器（合成网格）
# ---------------------------------------------------------------------------


def _dust_fragment() -> _TableFragment:
    return _TableFragment(
        caption="表5-2 定点粉尘（总尘）检测结果一览表",
        grid=[
            ["序号", "车间", "岗位", "检测项目", "岗位检测结果及判定", "", "",
             "采样点检测结果及判定", "", "", ""],
            ["", "", "", "", "CTWA（mg/m3）", "PC-TWA（mg/m3）", "结果判定",
             "采样点", "CPE（mg/m3）", "PE（mg/m3）", "结果判定"],
            ["1", "101车间", "配料", "谷物粉尘", "0.93", "4", "未超标",
             "投料口", "7.94", "15", "未超标"],
            ["2", "", "", "", "", "", "", "二层粉碎", "4.09", "12", "未超标"],
            ["3", "102车间", "包装", "其他粉尘", "7.14", "8", "超标",
             "包装口", "24.56", "40", "未超标"],
        ],
    )


def test_map_dual_table_splits_post_and_point() -> None:
    table = _map_dual_table(_dust_fragment(), "表5-2", "定点粉尘（总尘）", "dust_total")
    assert table.mode == "rules"
    assert len(table.rows) == 5
    posts = [r for r in table.rows if r.record_type == "post"]
    points = [r for r in table.rows if r.record_type == "point"]
    assert len(posts) == 2 and len(points) == 3
    # 合并单元格前向填充：第 2 行采样点归属 101车间/配料/谷物粉尘
    second = points[1]
    assert second.workshop == "101车间"
    assert second.post == "配料"
    assert second.factor_name == "谷物粉尘"
    assert second.measured_value == "4.09"
    assert second.limit_type == "PE" and second.limit_value_num == 12.0
    # 超标判定映射
    assert posts[1].verdict == "exceed"
    assert points[0].limit_type == "PE" and points[0].limit_value_num == 15.0


def test_map_mac_table() -> None:
    fragment = _TableFragment(
        caption="表5-4 氢氧化钠检测结果一览表",
        grid=[
            [
                "序号", "车间", "岗位", "采样点",
                "CME（mg/m3）", "MAC（mg/m3）", "结果判定",
            ],
            ["1", "201车间", "酸化", "钠化罐", "0.0320", "2", "未超标"],
            ["2", "", "", "液碱罐", "0.0084", "2", "未超标"],
        ],
    )
    table = _map_mac_table(fragment, "表5-4", "氢氧化钠")
    assert len(table.rows) == 2
    row = table.rows[1]
    assert row.workshop == "201车间" and row.post == "酸化"
    assert row.factor_name == "氢氧化钠" and row.factor_category == "chemical"
    assert row.limit_type == "MAC" and row.limit_value_num == 2.0


def test_map_noise_table_group_member_and_cross_context() -> None:
    fragment = _TableFragment(
        caption="表5-18 噪声测量结果一览表",
        grid=[
            ["序号", "车间", "岗位", "测量地点", "测量值dB（A）", "LEX,8h[dB(A)]",
             "LEX,40hdB(A)", "职业接触限值dB(A)", "判定结果"],
            ["1", "201车间", "值班", "3F发酵罐", "89.9", "81.0", "81.2",
             "40h等效声级85dB(A)", "未超标（噪声作业岗位）"],
            ["2", "", "", "3F控制室", "64.5", "", "", "", ""],
            ["3", "", "化验", "休息室", "62.1", "", "", "", "未超标"],
            ["4", "", "", "交接室", "60.5", "", "", "", ""],
        ],
    )
    table, trailing = _map_noise_table(fragment, "表5-18", "噪声测量结果一览表")
    assert len(table.rows) == 5  # 1 岗位接触 + 4 测量地点（组行自带 3F发酵罐）
    post = table.rows[0]
    assert post.record_type == "post" and post.post == "值班"
    assert post.measured_value == "81.2"
    assert post.limit_value_num == 85.0
    assert post.is_noise_post and post.extra == {"lex8h": 81.0, "lex40h": 81.2}
    # 无 LEX 的组行：不产生岗位记录，但成员行继承其判定与岗位
    late = [r for r in table.rows if r.post == "化验"]
    assert len(late) == 2
    assert all(r.workshop == "201车间" for r in late)
    assert trailing is not None and trailing["post"] == "化验"
    # 跨片段上下文：新片段成员行直接归属上一片段末尾组
    cont = _TableFragment(
        grid=[
            ["序号", "车间", "岗位", "测量地点", "测量值dB（A）", "", "", "", ""],
            ["5", "", "", "二楼休息室", "58.1", "", "", "", ""],
        ]
    )
    table2, _ = _map_noise_table(cont, "", "", trailing)
    assert len(table2.rows) == 1
    assert table2.rows[0].post == "化验" and table2.rows[0].verdict == "compliant"


def test_map_field_table_group_carries_own_point() -> None:
    fragment = _TableFragment(
        caption="表5-19 工频电场测量结果一览表",
        grid=[
            ["车间", "岗位", "采样点", "测量结果（V/m）", "E（V/m）8",
             "职业接触限值（V/m）", "判定结果"],
            ["辅助单元", "电工", "101高压室", "27", "11.7", "5000", "未超标"],
            ["", "", "103配电室", "18", "", "", ""],
            ["", "变电站", "主变压器", "654", "265.7", "5000", "未超标"],
            ["", "", "控制室", "123", "", "", ""],
        ],
    )
    table, _trailing = _map_field_table(fragment, "表5-19", "工频电场")
    assert len(table.rows) == 6  # 2 岗位 + 4 采样点
    first_point = table.rows[1]
    assert first_point.sample_point == "101高压室"
    assert first_point.workshop == "辅助单元" and first_point.post == "电工"
    assert first_point.limit_type == "E8" and first_point.limit_value_num == 5000.0
    last = table.rows[-1]
    assert last.sample_point == "控制室" and last.post == "变电站"


def test_map_heat_table() -> None:
    fragment = _TableFragment(
        caption="表5-20 高温测量结果一览表",
        grid=[
            [
                "车间", "岗位/工种", "测量地点", "接触时间（h）", "接触时间率（%）",
                "体力劳动强度分级", "WBGT指数平均值（℃）",
                "WBGT接触限值（℃）", "判定结果",
            ],
            ["热动站", "运行", "锅炉本体2F", "4", "50%", "I", "29.3", "32", "未超标"],
            ["", "", "脱碳罐", "1", "", "", "30.0", "", ""],
        ],
    )
    table = _map_heat_table(fragment, "表5-20", "高温")
    assert len(table.rows) == 2
    post = table.rows[0]
    assert post.record_type == "post" and post.measured_value == "29.3"
    assert post.limit_type == "WBGT" and post.limit_value_num == 32.0
    assert post.extra and post.extra["exposure_rate"] == "50%"
    point = table.rows[1]
    assert point.sample_point == "脱碳罐" and point.verdict == "compliant"


def test_map_silica_table() -> None:
    fragment = _TableFragment(
        caption="表5-1 工作场所游离二氧化硅检测结果一览表",
        grid=[
            ["序号", "取样点", "游离二氧化硅含量C（%）", "粉尘类别判定"],
            ["1", "103车间一层投料间", "5.67", "谷物粉尘（游离二氧化硅含量＜10%）"],
        ],
    )
    table = _map_silica_table(fragment, "表5-1", "工作场所游离二氧化硅")
    assert len(table.rows) == 1
    row = table.rows[0]
    assert row.factor_category == "free_silica"
    assert row.measured_value_num == 5.67
    assert row.extra == {"dust_class": "谷物粉尘（游离二氧化硅含量＜10%）"}


# ---------------------------------------------------------------------------
# 夹具 PDF 全流程
# ---------------------------------------------------------------------------


def test_parse_report_fixture_pdf() -> None:
    clear_parse_cache()
    parsed = asyncio.run(parse_report(FIXTURE.read_bytes(), "mini.pdf"))
    assert parsed.report_no == "TEST-J-2026-001"
    assert parsed.company_name == "测试制药有限公司"
    assert parsed.detection_agency == "宁夏测试检测技术有限公司"
    assert parsed.report_name == "职业病危害因素检测报告"
    assert parsed.parse_mode == "rules"
    assert len(parsed.tables) == 2
    assert parsed.total_points == 10
    assert parsed.exceed_points == 0
    assert parsed.noise_post_points == 5


def test_parse_report_rejects_non_pdf_and_empty() -> None:
    with pytest.raises(OhDetectionParseError):
        asyncio.run(parse_report(b"x", "report.docx"))
    with pytest.raises(OhDetectionParseError):
        asyncio.run(parse_report(b"", "report.pdf"))


# ---------------------------------------------------------------------------
# LLM 兜底（mock，不连真实模型）
# ---------------------------------------------------------------------------


class _FakeChatJson:
    def __init__(self, payload: dict[str, Any] | Exception):
        self._payload = payload
        self.calls: list[list[dict[str, str]]] = []

    async def __call__(self, messages, expected_keys=None, **_kwargs):
        self.calls.append(messages)
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _unknown_fragment() -> _TableFragment:
    return _TableFragment(
        caption="表9-1 未知版式检测结果一览表",
        grid=[
            ["车间", "岗位", "地点", "检测值", "限值", "判定"],
            ["A车间", "操作", "东投料口", "5.5", "10", "未超标"],
        ],
    )


def test_llm_fallback_accepts_validated_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeChatJson(
        {
            "rows": [
                {
                    "factor_category": "chemical",
                    "factor_name": "未知因素",
                    "record_type": "point",
                    "workshop": "A车间",
                    "post": "操作",
                    "sample_point": "东投料口",
                    "measured_value": "5.5",
                    "unit": "mg/m³",
                    "limit_type": "MAC",
                    "limit_value_num": 10,
                    "verdict": "compliant",
                    "is_noise_post": False,
                    "verdict_raw": "未超标",
                }
            ]
        }
    )
    monkeypatch.setattr(oh_module.llm_client, "chat_json", fake)
    drafts, warnings = asyncio.run(
        _llm_parse_table("表9-1 未知版式", _unknown_fragment().grid)
    )
    assert len(drafts) == 1 and not warnings
    assert drafts[0].measured_value == "5.5"


def test_llm_fallback_drops_hallucinated_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeChatJson(
        {
            "rows": [
                {
                    "factor_category": "chemical",
                    "factor_name": "未知因素",
                    "record_type": "point",
                    "workshop": "A车间",
                    "sample_point": "东投料口",
                    "measured_value": "999.9",
                    "limit_value_num": None,
                    "verdict": "compliant",
                },
                {
                    "factor_category": "chemical",
                    "factor_name": "未知因素",
                    "record_type": "point",
                    "workshop": "不存在车间",
                    "sample_point": "不存在地点",
                    "measured_value": "5.5",
                    "verdict": "compliant",
                },
            ]
        }
    )
    monkeypatch.setattr(oh_module.llm_client, "chat_json", fake)
    drafts, warnings = asyncio.run(
        _llm_parse_table("表9-1 未知版式", _unknown_fragment().grid)
    )
    assert drafts == []
    assert warnings and "丢弃" in warnings[0]


def test_unknown_layout_skipped_when_llm_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_parse_cache()

    class _Doc(oh_module._ExtractedDoc):
        pass

    doc = _Doc(first_page_text="测试公司检测报告 XJ-2026-1")
    doc.page_texts = ["测试公司检测报告 XJ-2026-1"]
    doc.fragments = [_unknown_fragment()]
    monkeypatch.setattr(
        oh_module, "_extract_pdf", lambda _bytes: doc, raising=True
    )
    fake = _FakeChatJson(LLMConfigError("未配置"))
    monkeypatch.setattr(oh_module.llm_client, "chat_json", fake)
    with pytest.raises(OhDetectionParseError):
        asyncio.run(parse_report(b"fake-pdf-bytes", "report.pdf"))


def test_metadata_extraction_from_doc() -> None:
    doc = oh_module._ExtractedDoc(
        first_page_text=(
            "丽珠集团（宁夏）制药有限公司职业病危害因素检测报告 NZXZW-J-2026-141\n"
            "5 检测结果与评价\n"
            "宁夏智信安全技术检测有限公司 0951-5671011 第 1 页 共200页"
        )
    )
    doc.page_texts = [doc.first_page_text]
    report_no, name, company, agency = _extract_metadata(doc)
    assert report_no == "NZXZW-J-2026-141"
    assert company == "丽珠集团（宁夏）制药有限公司"
    assert name == "职业病危害因素检测报告"
    assert agency == "宁夏智信安全技术检测有限公司"


def test_parsed_report_mode_aggregation() -> None:
    report = ParsedReport(tables=[])
    assert report.parse_mode == "rules"
    report.tables = [
        oh_module.ParsedTable(mode="rules", rows=[]),
        oh_module.ParsedTable(mode="skipped", skip_reason="x"),
    ]
    assert report.parse_mode == "rules"
