"""安全承诺日报 AI 风险研判测试。

mock llm_client：正常输出、无配置、限流、输出格式无效、供应商故障、
风险档位非法。数据采集函数用真实测试库（无数据时也应有界返回）。
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm.exceptions import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
)
from app.modules.safety.models import SafetyCommitmentReport
from app.modules.safety.service import safety_commitment_risk


def _report() -> SafetyCommitmentReport:
    return SafetyCommitmentReport(
        id=uuid4(),
        report_date=date.today(),
        enterprise_status={"workshop_total": 6, "special_work_total": 1},
    )


def _install_llm(
    monkeypatch: pytest.MonkeyPatch,
    *,
    result: dict | None = None,
    exc: Exception | None = None,
) -> None:
    if exc is not None:
        fake = SimpleNamespace(chat_json=AsyncMock(side_effect=exc))
    else:
        fake = SimpleNamespace(chat_json=AsyncMock(return_value=result))
    monkeypatch.setattr(safety_commitment_risk, "llm_client", fake)


_GOOD_RAW = {
    "risk_level": "中",
    "summary": "当日有一处一级动火作业，需重点监护。",
    "key_risks": ["动火作业火花飞溅"],
    "suggestions": ["清理周边可燃物，配置监火人"],
}


async def test_generate_success(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _report()
    db_session.add(report)
    await db_session.flush()

    _install_llm(monkeypatch, result=_GOOD_RAW)
    updated, reason = await safety_commitment_risk.generate_risk_assessment(
        db_session, report
    )
    assert reason is None
    assert updated is not None
    assessment = updated.risk_assessment
    assert assessment is not None
    assert assessment["risk_level"] == "中"
    assert assessment["summary"].startswith("当日")
    assert assessment["key_risks"] == ["动火作业火花飞溅"]
    assert assessment["data_basis"]["ops_report_total"] >= 0
    assert assessment["edited"] is False


@pytest.mark.parametrize(
    ("exc", "expected_keyword"),
    [
        (LLMConfigError("no config"), "未配置"),
        (LLMRateLimitError("rate"), "限流"),
        (LLMOutputError("bad json", "{}"), "格式无效"),
        (LLMProviderError("down"), "暂不可用"),
    ],
)
async def test_generate_llm_errors(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    exc: Exception,
    expected_keyword: str,
) -> None:
    report = _report()
    db_session.add(report)
    await db_session.flush()

    _install_llm(monkeypatch, exc=exc)
    updated, reason = await safety_commitment_risk.generate_risk_assessment(
        db_session, report
    )
    assert updated is None
    assert reason is not None
    assert expected_keyword in reason


async def test_generate_invalid_risk_level(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """风险档位不在允许枚举内 → 视为无效输出。"""
    report = _report()
    db_session.add(report)
    await db_session.flush()

    _install_llm(
        monkeypatch,
        result={
            "risk_level": "极高",
            "summary": "x",
            "key_risks": [],
            "suggestions": [],
        },
    )
    updated, reason = await safety_commitment_risk.generate_risk_assessment(
        db_session, report
    )
    assert updated is None
    assert reason is not None and "风险等级无效" in reason


async def test_generate_missing_summary(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _report()
    db_session.add(report)
    await db_session.flush()

    _install_llm(
        monkeypatch,
        result={
            "risk_level": "低",
            "summary": "  ",
            "key_risks": [],
            "suggestions": [],
        },
    )
    updated, reason = await safety_commitment_risk.generate_risk_assessment(
        db_session, report
    )
    assert updated is None
    assert reason is not None and "研判结论" in reason


async def test_collect_daily_context_bounded(db_session: AsyncSession) -> None:
    """空库下数据采集也有界返回，不抛异常。"""
    context = await safety_commitment_risk.collect_daily_context(
        db_session, date.today()
    )
    assert context["ops_report_total"] == 0
    assert context["permit_total"] == 0
    assert context["hazard_total"] >= 0
    assert isinstance(context["over_limit_items"], list)
    assert isinstance(context["accidents"], list)
