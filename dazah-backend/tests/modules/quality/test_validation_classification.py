"""验证名称 AI 分类服务测试。

按 AGENTS 规范 mock 业务模块实际导入的 llm_client，覆盖：
正常分类/缓存命中不再调用、LLMConfigError/RateLimit/输出错误/供应商失败
降级关键词、AI 返回非法类别忽略、"确认"不再一律当设备确认。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
)
from app.modules.quality.models import ValidationTitleClassification
from app.modules.quality.service import validation_classification as service


@pytest.fixture(autouse=True)
async def _clean_classification_table(db_session: AsyncSession) -> AsyncIterator[None]:
    from tests.conftest import _test_engine

    async with _test_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: ValidationTitleClassification.__table__.create(
                sync_conn, checkfirst=True
            )
        )
    await db_session.execute(delete(ValidationTitleClassification))
    await db_session.commit()
    yield
    await db_session.execute(delete(ValidationTitleClassification))
    await db_session.commit()


def _mock_llm(monkeypatch: pytest.MonkeyPatch, result: dict | Exception) -> None:
    if isinstance(result, Exception):
        monkeypatch.setattr(
            service, "llm_client", SimpleNamespaceAsync(chat_json=_raise(result))
        )
    else:
        monkeypatch.setattr(
            service, "llm_client", SimpleNamespaceAsync(chat_json=_return(result))
        )


class SimpleNamespaceAsync:
    def __init__(self, chat_json) -> None:
        self.chat_json = chat_json


def _raise(exc: Exception):
    async def _inner(*args, **kwargs):
        raise exc

    return _inner


def _return(payload: dict):
    async def _inner(*args, **kwargs):
        return payload

    return _inner


def _ai_payload(pairs: dict[str, str]) -> dict:
    return {
        "items": [
            {"index": i, "category": cat}
            for i, (title, cat) in enumerate(pairs.items(), start=1)
        ]
    }


@pytest.mark.anyio
async def test_classifies_via_llm_and_caches(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    titles = ["卧式矩形压力蒸汽灭菌器确认", "霉酚酸发酵设备清洁验证"]
    _mock_llm(
        monkeypatch,
        _ai_payload(
            {
                titles[0]: "equipment_qualification",
                titles[1]: "cleaning_validation",
            }
        ),
    )
    result = await service.resolve_validation_categories(db_session, titles)
    assert result == {
        titles[0]: "equipment_qualification",
        titles[1]: "cleaning_validation",
    }
    rows = (
        (
            await db_session.execute(select(ValidationTitleClassification))
        )
        .scalars()
        .all()
    )
    assert {row.category for row in rows} == {
        "equipment_qualification",
        "cleaning_validation",
    }
    assert all(row.source == "ai" for row in rows)

    # 第二次调用命中缓存，不再调用 LLM
    llm = service.llm_client
    monkeypatch.setattr(
        llm, "chat_json", AsyncMock(side_effect=AssertionError("不应再次调用 LLM"))
    )
    cached = await service.resolve_validation_categories(db_session, titles)
    assert cached == result


@pytest.mark.anyio
@pytest.mark.parametrize(
    "llm_error",
    [
        LLMConfigError("not configured"),
        LLMRateLimitError("rate limited"),
        LLMOutputError("bad json", "raw"),
        LLMProviderError("provider down"),
    ],
)
async def test_llm_failure_falls_back_to_conservative_keywords(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    llm_error: Exception,
) -> None:
    titles = [
        "发酵设备转产清洁验证",
        "霉酚酸发酵生产工艺验证",
        "303冷库温度分布确认",
        "厂房设施确认",
        "卧式矩形压力蒸汽灭菌器确认",
    ]
    _mock_llm(monkeypatch, llm_error)
    result = await service.resolve_validation_categories(db_session, titles)
    # 关键：含"确认"不再被当成设备确认
    assert result["303冷库温度分布确认"] == "other_validation"
    assert result["厂房设施确认"] == "other_validation"
    assert result["卧式矩形压力蒸汽灭菌器确认"] == "other_validation"
    assert result["发酵设备转产清洁验证"] == "cleaning_validation"
    assert result["霉酚酸发酵生产工艺验证"] == "process_validation"
    rows = (
        (await db_session.execute(select(ValidationTitleClassification)))
        .scalars()
        .all()
    )
    assert {row.source for row in rows} == {"fallback"}


@pytest.mark.anyio
async def test_invalid_llm_categories_fall_back(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    title = "培养间（四）温度分布确认"
    # AI 返回白名单外的类别 + 缺失一条
    _mock_llm(monkeypatch, {"items": [{"index": 1, "category": "厂房确认"}]})
    result = await service.resolve_validation_categories(db_session, [title])
    assert result[title] == "other_validation"
    row = (
        (
            await db_session.execute(
                select(ValidationTitleClassification).where(
                    ValidationTitleClassification.title == title
                )
            )
        )
        .scalars()
        .one()
    )
    assert row.source == "fallback"


@pytest.mark.anyio
async def test_empty_titles_noop(db_session: AsyncSession) -> None:
    assert await service.resolve_validation_categories(db_session, []) == {}
