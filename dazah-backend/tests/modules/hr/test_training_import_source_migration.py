"""培训统计导入 AI 识别模块测试。

测试范围：
- header_fingerprint：表头指纹稳定、与列顺序无关、忽略空表头
- field_catalog_payload：字段目录完整性
- analyze_headers_by_llm：合法映射过滤、非法字段/列号丢弃、LLM 异常不阻塞
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.llm import LLMOutputError, LLMProviderError, LLMRateLimitError
from app.modules.hr.api import _calc_duration_from_text
from app.modules.hr.training_import_ai import (
    FIELD_CATALOG,
    analyze_headers_by_llm,
    field_catalog_payload,
    header_fingerprint,
)

# ── _calc_duration_from_text ────────────────────────────


def test_calc_duration_tilde():
    """半角波浪号时间段应正确计算。"""
    assert _calc_duration_from_text("2026.01.06 09:00~10:00") == 1.0


def test_calc_duration_fullwidth_tilde():
    """全角波浪号时间段应正确计算。"""
    assert _calc_duration_from_text("2026.01.06 13:30～17:30") == 4.0


def test_calc_duration_dash_half_hour():
    """短横线时间段含半小时应正确计算。"""
    assert _calc_duration_from_text("2026.01.20 08:00-08:30") == 0.5


def test_calc_duration_newline_text():
    """带换行的原始单元格文本应正确计算。"""
    assert _calc_duration_from_text("2026.01.06\n09:00~10:00") == 1.0


def test_calc_duration_no_range():
    """无时间段（仅日期）应返回 None，不猜测。"""
    assert _calc_duration_from_text("2026.01.06") is None
    assert _calc_duration_from_text(None) is None
    assert _calc_duration_from_text("") is None


def test_calc_duration_invalid_range():
    """结束早于开始或非法时间应返回 None。"""
    assert _calc_duration_from_text("2026.01.06 10:00~09:00") is None
    assert _calc_duration_from_text("2026.01.06 25:00~26:00") is None


# ── header_fingerprint ──────────────────────────────────


def test_header_fingerprint_deterministic():
    """相同表头集应返回相同指纹。"""
    headers_a = ["序号", "培训时间", "培训内容", "授课人", "考核方式"]
    headers_b = ["序号", "培训时间", "培训内容", "授课人", "考核方式"]
    assert header_fingerprint(headers_a) == header_fingerprint(headers_b)


def test_header_fingerprint_order_independent():
    """表头指纹应与列顺序无关（排序后拼接）。"""
    headers_a = ["培训时间", "培训内容", "授课人"]
    headers_b = ["授课人", "培训时间", "培训内容"]
    assert header_fingerprint(headers_a) == header_fingerprint(headers_b)


def test_header_fingerprint_ignores_empty():
    """空表头与空白字符串不应影响指纹。"""
    headers_a = ["培训时间", "", "   ", "培训内容"]
    headers_b = ["培训内容", "培训时间"]
    assert header_fingerprint(headers_a) == header_fingerprint(headers_b)


def test_header_fingerprint_strips_whitespace():
    """指纹应基于去除首尾空格后的表头文本。"""
    headers_a = ["培训时间", "培训内容"]
    headers_b = [" 培训时间 ", "培训内容"]
    assert header_fingerprint(headers_a) == header_fingerprint(headers_b)


# ── field_catalog_payload ───────────────────────────────


def test_field_catalog_payload_keys_match_catalog():
    """字段目录应完整返回 key/label，且 key 与 FIELD_CATALOG 一致。"""
    payload = field_catalog_payload()
    assert len(payload) == len(FIELD_CATALOG)
    keys = [item["key"] for item in payload]
    expected = [key for key, _ in FIELD_CATALOG]
    assert keys == expected
    for item in payload:
        assert set(item.keys()) == {"key", "label"}


# ── analyze_headers_by_llm ──────────────────────────────


@pytest.mark.asyncio
async def test_analyze_headers_llm_filters_invalid():
    """LLM 返回的 mapping 应只保留合法字段名与合法列号。"""
    headers = ["序号", "培训时间", "培训内容", "授课人"]
    llm_result = {
        "mapping": {
            "1": "training_datetime",  # 合法
            "2": "training_content",  # 合法
            "3": "instructor",  # 合法
            "0": "非法字段",  # 非法字段名 → 丢弃
            "99": "remarks",  # 列号越界 → 丢弃
            "abc": "trainees",  # 非整数列号 → 丢弃
        },
        "judgment": "这是一份培训统计数据表",
    }
    fake_client = MagicMock()
    fake_client.chat_json = AsyncMock(return_value=llm_result)

    with patch("app.modules.hr.training_import_ai.llm_client", fake_client):
        result = await analyze_headers_by_llm("Sheet1", headers)

    assert result["mapping"] == {
        "1": "training_datetime",
        "2": "training_content",
        "3": "instructor",
    }
    assert result["judgment"] == "这是一份培训统计数据表"


@pytest.mark.asyncio
async def test_analyze_headers_llm_empty_mapping():
    """LLM 完全不识别时应返回空 mapping，不抛异常。"""
    fake_client = MagicMock()
    fake_client.chat_json = AsyncMock(return_value={"mapping": {}, "judgment": ""})

    with patch("app.modules.hr.training_import_ai.llm_client", fake_client):
        result = await analyze_headers_by_llm("Sheet1", ["序号", "乱七八糟"])

    assert result["mapping"] == {}
    assert result["judgment"] == ""


@pytest.mark.asyncio
async def test_analyze_headers_llm_non_string_field_skipped():
    """mapping 里 field 不是字符串（如列表）时应跳过。"""
    headers = ["培训时间"]
    llm_result = {"mapping": {"0": ["training_datetime"]}, "judgment": "x"}
    fake_client = MagicMock()
    fake_client.chat_json = AsyncMock(return_value=llm_result)

    with patch("app.modules.hr.training_import_ai.llm_client", fake_client):
        result = await analyze_headers_by_llm("Sheet1", headers)

    assert result["mapping"] == {}


@pytest.mark.asyncio
async def test_analyze_headers_llm_non_string_judgment():
    """judgment 不是字符串时回退为空字符串。"""
    headers = ["培训时间"]
    llm_result = {"mapping": {}, "judgment": {"extra": 1}}
    fake_client = MagicMock()
    fake_client.chat_json = AsyncMock(return_value=llm_result)

    with patch("app.modules.hr.training_import_ai.llm_client", fake_client):
        result = await analyze_headers_by_llm("Sheet1", headers)

    assert result == {"mapping": {}, "judgment": ""}


@pytest.mark.asyncio
async def test_analyze_headers_llm_output_error_returns_empty():
    """LLM 输出格式错误（LLMOutputError）应返回空 mapping 且不抛异常。"""
    fake_client = MagicMock()
    fake_client.chat_json = AsyncMock(side_effect=LLMOutputError("无法解析"))

    with patch("app.modules.hr.training_import_ai.llm_client", fake_client):
        result = await analyze_headers_by_llm("Sheet1", ["培训时间"])

    assert result == {"mapping": {}, "judgment": ""}


@pytest.mark.asyncio
async def test_analyze_headers_llm_provider_error_returns_empty():
    """LLM 服务异常（LLMProviderError）应返回空 mapping 且不抛异常。"""
    fake_client = MagicMock()
    fake_client.chat_json = AsyncMock(side_effect=LLMProviderError("服务不可用"))

    with patch("app.modules.hr.training_import_ai.llm_client", fake_client):
        result = await analyze_headers_by_llm("Sheet1", ["培训时间"])

    assert result == {"mapping": {}, "judgment": ""}


@pytest.mark.asyncio
async def test_analyze_headers_llm_rate_limit_returns_empty():
    """LLM 限流（LLMRateLimitError）应返回空 mapping 且不抛异常。"""
    fake_client = MagicMock()
    fake_client.chat_json = AsyncMock(side_effect=LLMRateLimitError("限流"))

    with patch("app.modules.hr.training_import_ai.llm_client", fake_client):
        result = await analyze_headers_by_llm("Sheet1", ["培训时间"])

    assert result == {"mapping": {}, "judgment": ""}
