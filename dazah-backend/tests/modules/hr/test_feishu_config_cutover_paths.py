"""飞书配置收口改造的分支覆盖补测。

覆盖：
- _resolve_feishu_sync_session 未绑定/已绑定两分支；
- OnboardingRecordService.sync_from_feishu 未配置时的 503 业务异常；
- get_onboarding_service 凭证缺失/实体缺失分支；
- sync_contract_from_onboarding 按姓名查工号分支。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr import service as hr_service
from app.modules.hr.feishu_settings_service import HrFeishuNotConfigured
from app.modules.hr.models import HrFeishuEntitySetting


@pytest.mark.asyncio
async def test_resolve_feishu_sync_session_unbound_returns_none(
    db_session: AsyncSession,
) -> None:
    """员工实体未绑定/未启用时返回 None（调用方跳过推送）。"""
    result = await hr_service._resolve_feishu_sync_session(db_session)
    assert result is None


@pytest.mark.asyncio
async def test_resolve_feishu_sync_session_builds_sync_when_bound(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """已绑定时按 DB 配置构造 FeishuBitableSync。"""
    row = HrFeishuEntitySetting(
        entity_code="employee",
        entity_name="员工花名册",
        entity_group="人事台账",
        app_token="tok-employee",
        base_table_id="tbl-employee",
        is_enabled=True,
    )
    db_session.add(row)
    await db_session.flush()

    async def fake_creds(session, purpose="bitable"):
        return ("cli_hr_test", "secret-plain")

    monkeypatch.setattr(hr_service, "get_hr_feishu_app_credentials", fake_creds)
    result = await hr_service._resolve_feishu_sync_session(db_session)
    assert result is not None
    assert result.employee_table == "tbl-employee"
    assert result.bitable.app_token == "tok-employee"


@pytest.mark.asyncio
async def test_sync_from_feishu_raises_503_when_unconfigured() -> None:
    """数据源未配置时显式抛 503 业务异常，而非裸 RuntimeError。"""

    class _FakeBitable:
        def _is_enabled(self) -> bool:
            return False

    svc = hr_service.OnboardingRecordService.__new__(hr_service.OnboardingRecordService)
    svc.record_label = "入职记录"
    svc.bitable = _FakeBitable()
    with pytest.raises(HrFeishuNotConfigured):
        await svc.sync_from_feishu()


@pytest.mark.asyncio
async def test_get_onboarding_service_handles_missing_credentials(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """凭证缺失时不抛错，数据源按未配置处理。"""
    from app.modules.hr import api as hr_api

    async def no_creds(session, purpose="bitable"):
        raise HrFeishuNotConfigured()

    monkeypatch.setattr(hr_api, "get_hr_feishu_app_credentials", no_creds)
    svc = await hr_api.get_onboarding_service(db_session)
    assert svc.bitable._is_enabled() is False


@pytest.mark.asyncio
async def test_get_onboarding_service_reads_entity_binding(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """凭证与实体绑定都在时，构造的数据源携带 DB 配置值。"""
    from app.modules.hr import api as hr_api

    row = HrFeishuEntitySetting(
        entity_code="onboarding",
        entity_name="入职信息表",
        entity_group="招聘入职",
        app_token="tok-onboard",
        base_table_id="tbl-onboard",
        is_enabled=True,
    )
    db_session.add(row)
    await db_session.flush()

    async def fake_creds(session, purpose="bitable"):
        return ("cli_hr_test", "secret-plain")

    monkeypatch.setattr(hr_api, "get_hr_feishu_app_credentials", fake_creds)
    svc = await hr_api.get_onboarding_service(db_session)
    assert svc.bitable._is_enabled() is True
    assert svc.bitable.table_id == "tbl-onboard"


@pytest.mark.asyncio
async def test_sync_contract_from_onboarding_resolves_employee_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无工号时按姓名从员工档案表查工号（表 id 只认 DB 配置）。"""
    from app.modules.hr import contract_api

    async def fake_table_id(entity_code: str) -> str:
        return "tbl-employee"

    client = SimpleNamespace(
        search_records=AsyncMock(
            return_value=[
                {
                    "record_id": "emp-1",
                    "fields": {"姓名": [{"text": "新员工"}], "工号": 10086},
                }
            ]
        )
    )
    repo = SimpleNamespace(
        _get_client=AsyncMock(return_value=client), _table_id=fake_table_id
    )
    monkeypatch.setattr(
        "app.modules.hr.recruitment_repository.RecruitmentBitableRepo",
        lambda: repo,
    )

    service = SimpleNamespace(
        sync_from_onboarding=AsyncMock(return_value=SimpleNamespace(id="contract-1"))
    )
    monkeypatch.setattr(contract_api, "ContractService", lambda _db: service)
    monkeypatch.setattr(contract_api, "_require_user", lambda *a, **k: None)

    data = contract_api.OnboardingSyncRequest(name="新员工")
    await contract_api.sync_contract_from_onboarding(
        data, db=AsyncMock(), current_user=object()
    )
    assert data.employee_number == "10086"
    service.sync_from_onboarding.assert_awaited_once()
