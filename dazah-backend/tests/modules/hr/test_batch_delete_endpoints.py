"""批量删除端点测试（培训台账 / ESG 培训记录）.

口径：
- POST */batch-delete，body {ids}；软删除；
- 未命中/已删除的 ID 计入 data.failed，不中断整批；
- 空 ids → 400。
"""

from collections.abc import AsyncIterator
from datetime import date
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.main import app
from app.modules.hr.models import EsgTrainingRecord, TrainingLedger

_LEDGER_URL = "/api/v1/hr/training-ledgers/batch-delete"
_ESG_URL = "/api/v1/hr/esg-training-records/batch-delete"
_SUBJ = "SPEC批量删除台账"
_NAME = "SPEC批量删除ESG"


@pytest.fixture(autouse=True)
async def _share_db_session(
    client: AsyncClient, db_session: AsyncSession
) -> AsyncIterator[None]:
    """API 调用与测试种子共用同一会话（conftest 全回滚）。"""

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)


def _ledger(subject: str) -> TrainingLedger:
    return TrainingLedger(
        employee_number=f"SPEC-{subject}",
        training_date=date(2031, 10, 15),
        training_datetime="2031-10-15",
        training_subject=subject,
        teaching_dept="SPEC测试车间",
        trainees="测张三",
        ledger_department="SPEC测试车间",
        source_type="manual",  # 库表 NOT NULL
    )


def _esg_record(name: str) -> EsgTrainingRecord:
    return EsgTrainingRecord(
        training_date=date(2031, 10, 15),
        training_name=name,
        training_method="线下",
        caliber="部门组织",
        employee_name="测张三",
        department="SPEC测试车间",
    )


@pytest.mark.asyncio
async def test_batch_delete_training_ledgers(
    client: AsyncClient, db_session: AsyncSession
):
    """台账批量删除：命中软删，未命中 ID 计入 failed。"""
    r1, r2 = _ledger(f"{_SUBJ}-1"), _ledger(f"{_SUBJ}-2")
    db_session.add_all([r1, r2])
    await db_session.flush()
    missing = uuid4()

    resp = await client.post(
        _LEDGER_URL, json={"ids": [str(r1.id), str(r2.id), str(missing)]}
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["deleted"] == 2
    assert data["failed"] == [str(missing)]

    await db_session.refresh(r1)
    await db_session.refresh(r2)
    assert r1.is_deleted is True
    assert r2.is_deleted is True


@pytest.mark.asyncio
async def test_batch_delete_esg_records(client: AsyncClient, db_session: AsyncSession):
    """ESG 记录批量删除：命中软删，未命中 ID 计入 failed。"""
    r1 = _esg_record(f"{_NAME}-1")
    db_session.add(r1)
    await db_session.flush()
    missing = uuid4()

    resp = await client.post(_ESG_URL, json={"ids": [str(r1.id), str(missing)]})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["deleted"] == 1
    assert data["failed"] == [str(missing)]

    await db_session.refresh(r1)
    assert r1.is_deleted is True


@pytest.mark.asyncio
async def test_batch_delete_rejects_empty_ids(client: AsyncClient):
    """空 ids → 400。"""
    for url in (_LEDGER_URL, _ESG_URL):
        resp = await client.post(url, json={"ids": []})
        assert resp.status_code == 400
        assert "请先选择" in resp.json()["message"]
