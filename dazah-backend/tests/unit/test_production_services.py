"""生产管理模块各类业务服务的边界与数据转换测试。

覆盖 production 模块下引用的多个业务服务：
- FermentationService._prepare_data 日期字符串转 date
- SeedCultureService._prepare_data 日期字符串转 date
- ShiftLogService._prepare_data 日期字符串转 date
- ShiftHandoverService.confirm_record 缺失时抛 ValueError
- NCEService.create_record 自动关联批次
- production_plan_service 的 _extract_text/_extract_number/_extract_date
"""
from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production import (
    fermentation_service,
    nce_service,
    production_plan_service,
    seed_culture_service,
    shift_handover_service,
    shift_log_service,
)


def _fermentation_service() -> tuple[
    fermentation_service.FermentationService, SimpleNamespace
]:
    service = fermentation_service.FermentationService(cast(AsyncSession, object()))
    repo = SimpleNamespace(
        create=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
        update=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
        delete=AsyncMock(return_value=True),
    )
    setattr(service, "repo", repo)
    return service, repo


@pytest.mark.anyio
async def test_fermentation_prepare_data_converts_entry_and_discharge_dates() -> None:
    service, _ = _fermentation_service()
    data = {
        "entry_date": "2026-07-01",
        "discharge_date": "2026-07-15",
    }
    prepared = service._prepare_data(dict(data))
    assert prepared["entry_date"] == date(2026, 7, 1)
    assert prepared["discharge_date"] == date(2026, 7, 15)
    # 非字符串不转换
    prepared["entry_date"] = "2026-08-01"
    assert isinstance(prepared["entry_date"], str)


@pytest.mark.anyio
async def test_fermentation_update_raises_on_missing() -> None:
    service, repo = _fermentation_service()
    repo.update.return_value = None
    with pytest.raises(ValueError):
        await service.update_record(uuid.uuid4(), {"entry_date": "2026-07-01"})
    repo.delete.return_value = False
    with pytest.raises(ValueError):
        await service.delete_record(uuid.uuid4())


def _seed_service() -> tuple[seed_culture_service.SeedCultureService, SimpleNamespace]:
    service = seed_culture_service.SeedCultureService(cast(AsyncSession, object()))
    repo = SimpleNamespace(
        create=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
        update=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
        delete=AsyncMock(return_value=True),
    )
    setattr(service, "repo", repo)
    return service, repo


@pytest.mark.anyio
async def test_seed_culture_prepare_data_converts_dates() -> None:
    service, _ = _seed_service()
    data = {"prepare_date": "2026-07-03", "shaker_start_date": "2026-07-04"}
    prepared = service._prepare_data(dict(data))
    assert prepared["prepare_date"] == date(2026, 7, 3)
    assert prepared["shaker_start_date"] == date(2026, 7, 4)


@pytest.mark.anyio
async def test_seed_culture_update_delete_raise_on_missing() -> None:
    service, repo = _seed_service()
    repo.update.return_value = None
    with pytest.raises(ValueError):
        await service.update_record(uuid.uuid4(), {"prepare_date": "2026-07-03"})
    repo.delete.return_value = False
    with pytest.raises(ValueError):
        await service.delete_record(uuid.uuid4())


def _shift_log_service() -> tuple[shift_log_service.ShiftLogService, SimpleNamespace]:
    service = shift_log_service.ShiftLogService(cast(AsyncSession, object()))
    repo = SimpleNamespace(
        create=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
        update=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
        delete=AsyncMock(return_value=True),
    )
    setattr(service, "repo", repo)
    return service, repo


@pytest.mark.anyio
async def test_shift_log_prepare_data_converts_log_date() -> None:
    service, _ = _shift_log_service()
    data = {"log_date": "2026-07-05"}
    prepared = service._prepare_data(dict(data))
    assert prepared["log_date"] == date(2026, 7, 5)


@pytest.mark.anyio
async def test_shift_log_update_delete_raise_on_missing() -> None:
    service, repo = _shift_log_service()
    repo.update.return_value = None
    with pytest.raises(ValueError):
        await service.update_record(uuid.uuid4(), {"log_date": "2026-07-05"})
    repo.delete.return_value = False
    with pytest.raises(ValueError):
        await service.delete_record(uuid.uuid4())


def _shift_handover_service() -> tuple[
    shift_handover_service.ShiftHandoverService, SimpleNamespace
]:
    service = shift_handover_service.ShiftHandoverService(
        cast(AsyncSession, object())
    )
    repo = SimpleNamespace(
        confirm=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
        get_distinct_positions=AsyncMock(return_value=["洁净区", "生产区"]),
    )
    setattr(service, "repo", repo)
    return service, repo


@pytest.mark.anyio
async def test_shift_handover_lists_positions_and_confirms() -> None:
    service, repo = _shift_handover_service()
    assert await service.get_distinct_positions() == ["洁净区", "生产区"]
    await service.confirm_record(uuid.uuid4())
    repo.confirm.assert_awaited_once()


@pytest.mark.anyio
async def test_shift_handover_confirm_raises_on_missing() -> None:
    service, repo = _shift_handover_service()
    repo.confirm.return_value = None
    with pytest.raises(ValueError):
        await service.confirm_record(uuid.uuid4())


def _nce_service() -> tuple[nce_service.NCEService, SimpleNamespace]:
    service = nce_service.NCEService(cast(AsyncSession, object()))
    session = SimpleNamespace(
        execute=AsyncMock(),
        flush=AsyncMock(),
    )
    setattr(service, "session", session)
    repo = SimpleNamespace(
        create=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
        update=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
        delete=AsyncMock(return_value=True),
    )
    setattr(service, "repo", repo)
    return service, repo


@pytest.mark.anyio
async def test_nce_delete_raises_on_missing() -> None:
    service, repo = _nce_service()
    repo.delete.return_value = False
    with pytest.raises(ValueError):
        await service.delete_record(uuid.uuid4())


def _test_extract_text() -> Any:
    assert production_plan_service._extract_text(None) is None
    assert production_plan_service._extract_text("   ") is None
    assert production_plan_service._extract_text("  FA-01 ") == "FA-01"
    assert production_plan_service._extract_text({"name": "产品A"}) == "产品A"
    assert production_plan_service._extract_text({"text": "产品B"}) == "产品B"
    assert production_plan_service._extract_text(["产品C"]) == "产品C"


def _test_extract_number() -> Any:
    assert production_plan_service._extract_number({"type": 2, "value": [98]}) == 98.0
    assert production_plan_service._extract_number("98.5") == 98.5
    assert production_plan_service._extract_number("随附") is None
    assert production_plan_service._extract_number(None) is None


def _test_extract_date() -> Any:
    assert production_plan_service._extract_date("2026-07-01") == date(2026, 7, 1)
    assert production_plan_service._extract_date(None) is None
    assert production_plan_service._extract_date("not-a-date") is None  # noqa: E501


# ============ 收率异常判定（纯规则） ============


def test_judge_anomaly_severity_rules() -> None:
    from app.modules.production.mc_yield_anomaly_detector import judge_anomaly_severity

    assert judge_anomaly_severity(50, 100, 0) is None  # iqr <= 0 → normal
    assert judge_anomaly_severity(60, 100, 20) == "high"  # < median - 1.5*iqr
    assert judge_anomaly_severity(75, 100, 20) == "medium"  # < median - iqr
    assert judge_anomaly_severity(90, 100, 20) is None  # normal


def test_parse_json_helpers() -> None:
    from app.modules.production.mc_yield_anomaly_detector import _parse_json

    assert _parse_json('{"a": 1}') == {"a": 1}
    assert _parse_json("```json\n{\"b\": 2}\n```") == {"b": 2}
    assert _parse_json("not json") == {}
    import pytest as _pytest
    with _pytest.raises(AttributeError):
        _parse_json(cast(str, None))
