"""合同管理 飞书多维表格同步 回归测试。

飞书多维表格是合同数据的唯一数据源：
- 飞书为空时，本地未删除记录应全部软删除（移除旧版「空表保护」，
  避免出现「飞书没数据但页面仍有数据」的不一致状态）。
- 正常对账：飞书有 -> 本地新建/覆盖；本地有但飞书没有 -> 软删除。
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.contract_sync_service import ContractSyncService
from app.modules.hr.models import ContractManagement, HrFeishuEntitySetting
from app.platform.integrations.feishu.bitable import BitableClient


async def _seed_entity_setting(session: AsyncSession) -> None:
    row = (
        await session.execute(
            select(HrFeishuEntitySetting).where(
                HrFeishuEntitySetting.entity_code == "contract_management"
            )
        )
    ).scalar_one_or_none()
    if row is None:
        session.add(
            HrFeishuEntitySetting(
                entity_code="contract_management",
                entity_name="合同管理",
                entity_group="人事台账",
                app_token="test_app_token",
                base_table_id="tbl_contract",
                is_enabled=True,
            )
        )
    else:
        row.app_token = "test_app_token"
        row.base_table_id = "tbl_contract"
        row.is_enabled = True
    await session.flush()


def _local_contract(employee_number: str, name: str, **kwargs) -> ContractManagement:
    return ContractManagement(employee_number=employee_number, name=name, **kwargs)


@pytest.fixture
def mock_feishu_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_search_records(self, table_id: str, **kwargs):
        return []

    monkeypatch.setattr(BitableClient, "search_records", fake_search_records)
    monkeypatch.setattr(
        "app.modules.hr.contract_sync_service.get_hr_feishu_app_credentials",
        AsyncMock(return_value=("app_id", "app_secret")),
    )


@pytest.fixture
def mock_feishu_records(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_search_records(self, table_id: str, **kwargs):
        return [
            {
                # 飞书有 -> 本地无：新建（姓名为飞书文本数组格式）
                "record_id": "rec_new",
                "fields": {
                    "工号": 9002,
                    "姓名": [{"text": "李四", "type": "text"}],
                    "首次签订合同日期": 1700000000000,
                },
            },
            {
                # 飞书有 -> 本地有：覆盖
                "record_id": "rec_upd",
                "fields": {
                    "工号": 9003,
                    "姓名": "王五",
                    "一级部门": "生产管理部",
                },
            },
        ]

    monkeypatch.setattr(BitableClient, "search_records", fake_search_records)
    monkeypatch.setattr(
        "app.modules.hr.contract_sync_service.get_hr_feishu_app_credentials",
        AsyncMock(return_value=("app_id", "app_secret")),
    )



@pytest.fixture(autouse=True)
def _safe_commit(db_session, monkeypatch):
    """同步类 service 内部会 session.commit()；测试内降级为 flush 保持隔离。"""
    monkeypatch.setattr(db_session, "commit", db_session.flush, raising=False)

@pytest.mark.asyncio
async def test_pull_empty_feishu_soft_deletes_all_local(
    db_session: AsyncSession, mock_feishu_empty,
) -> None:
    """飞书为空：本地未删除合同全部软删除，平台与飞书保持一致。

    回归点：旧版「空表保护」在飞书无数据时跳过本地软删除，
    导致「飞书没数据但页面仍有数据」；本用例确保空表也会清空本地。
    """
    await _seed_entity_setting(db_session)
    baseline_active = (
        await db_session.execute(
            select(ContractManagement).where(
                ContractManagement.is_deleted.is_(False)
            )
        )
    ).scalars().all()
    mine = [
        _local_contract("T9001", "张三"),
        _local_contract("T9002", "李四"),
    ]
    db_session.add_all(mine)
    await db_session.flush()

    result = await ContractSyncService(db_session).pull_from_feishu()

    assert result["created"] == 0
    assert result["updated"] == 0
    # 飞书为空时本地所有未删记录都软删（含测试前已存在的记录）
    assert result["deleted"] == len(baseline_active) + len(mine)

    remaining = (
        await db_session.execute(
            select(ContractManagement).where(
                ContractManagement.is_deleted.is_(False)
            )
        )
    ).scalars().all()
    assert remaining == []
    for rec in mine:
        refreshed = await db_session.get(ContractManagement, rec.id)
        assert refreshed is not None
        assert refreshed.is_deleted is True


@pytest.mark.asyncio
async def test_pull_reconciles_create_update_delete(
    db_session: AsyncSession, mock_feishu_records,
) -> None:
    """正常对账：飞书有->本地新建/覆盖；本地有但飞书无->软删除。"""
    await _seed_entity_setting(db_session)
    baseline_active = (
        await db_session.execute(
            select(ContractManagement).where(
                ContractManagement.is_deleted.is_(False)
            )
        )
    ).scalars().all()
    local = _local_contract("T9001", "张三")  # 飞书没有 -> 应软删除
    upd = _local_contract("9003", "王五-旧名")  # 与飞书工号一致 -> 应被覆盖
    db_session.add_all([local, upd])
    await db_session.flush()

    result = await ContractSyncService(db_session).pull_from_feishu()

    assert result["created"] == 1
    assert result["updated"] == 1
    assert result["deleted"] == len(baseline_active) + 1  # 基线 + 本地 T9001

    # 新员工 9002：由飞书创建，日期毫秒时间戳正确转成 date
    created = (
        await db_session.execute(
            select(ContractManagement).where(
                ContractManagement.employee_number == "9002"
            )
        )
    ).scalar_one()
    assert created.name == "李四"
    # 1700000000000ms = 2023-11-14T22:13Z，转换按本地时区（东八区）取日期
    assert created.contract_start_1 == date(2023, 11, 15)
    assert created.feishu_record_id == "rec_new"

    # 员工 9003：被飞书覆盖
    updated = (
        await db_session.execute(
            select(ContractManagement).where(
                ContractManagement.employee_number == "9003"
            )
        )
    ).scalar_one()
    assert updated.name == "王五"
    assert updated.dept_level1 == "生产管理部"
    assert updated.is_deleted is False

    # 员工 T9001：飞书没有 -> 已软删除
    deleted = (
        await db_session.execute(
            select(ContractManagement).where(
                ContractManagement.employee_number == "T9001"
            )
        )
    ).scalar_one()
    assert deleted.is_deleted is True
