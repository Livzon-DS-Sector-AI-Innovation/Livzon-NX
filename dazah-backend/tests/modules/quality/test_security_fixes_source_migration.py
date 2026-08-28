"""P0 安全修复回归测试：鉴权 401 与删除审计留痕（SEC1/SEC2/SEC3）。"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.main import app  # noqa: A001
from app.modules.quality import service as quality_service
from app.modules.quality.models import CAPA, ChangeControl, Deviation
from app.platform.audit.models import AuditLog
from app.platform.identity.models import User


@pytest.fixture
async def actor_user(db_session: AsyncSession) -> User:
    """创建一个真实用户（audit.logs.user_id 有 FK 约束）。"""
    user = User(
        feishu_open_id=f"sec3-test-{uuid.uuid4().hex[:8]}",
        name="删除审计测试用户",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def anon_client(client: AsyncClient) -> AsyncIterator[AsyncClient]:
    """覆盖身份解析为 None，模拟未登录请求（绕过 DEV_BYPASS_AUTH）。"""

    async def _no_user():
        return None

    app.dependency_overrides[get_current_user] = _no_user
    yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path"),
    [
        # SEC1: 人员候选搜索（员工 PII）
        ("GET", "/api/v1/quality/change-action-plans/person-options?keyword=zhang"),
        # SEC2: inspection pull 写端点与查询端点
        ("POST", "/api/v1/quality/items/inventory/pull"),
        ("POST", "/api/v1/quality/items/inbound/pull"),
        ("POST", "/api/v1/quality/instruments/maintenance/pull"),
        ("POST", "/api/v1/quality/instruments/repair/pull"),
        ("GET", "/api/v1/quality/instruments/change"),
        (
            "POST",
            "/api/v1/quality/inspection-finished/mpa/pull?entity_code=qc_finished_internal",
        ),
        ("POST", "/api/v1/quality/inspection-solid/g1/pull?entity_code=x"),
        ("POST", "/api/v1/quality/inspection-liquid/g1/pull?entity_code=x"),
        # 看板鉴权收敛：统一入口与 9 个产品组仪表盘
        ("GET", "/api/v1/quality/inspection-dashboard/mpa"),
        ("GET", "/api/v1/quality/inspection-finished/mpa/dashboard"),
        ("GET", "/api/v1/quality/inspection-finished/mvt/dashboard"),
        ("GET", "/api/v1/quality/inspection-finished/water/dashboard"),
    ],
)
async def test_quality_endpoints_require_login(
    anon_client: AsyncClient, method: str, path: str
) -> None:
    response = await anon_client.request(method, path)
    assert response.status_code == 401, response.text


@pytest.mark.anyio
async def test_delete_change_records_audit(
    db_session: AsyncSession, actor_user: User
) -> None:
    change = ChangeControl(change_code=f"SEC3-AUDIT-{uuid.uuid4().hex[:8]}")
    db_session.add(change)
    await db_session.flush()

    actor = actor_user.id
    result = await quality_service.delete_change(
        db_session, change.id, deleted_by=actor
    )

    assert result == {"success": True}
    assert change.is_deleted is True
    assert change.deleted_by == actor
    assert change.deleted_at is not None

    logs = (
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.resource_type == "quality.change_control",
                    AuditLog.resource_id == change.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(logs) == 1
    assert logs[0].action == "delete"
    assert logs[0].user_id == actor
    assert logs[0].old_value["change_code"] == change.change_code


@pytest.mark.anyio
async def test_delete_deviation_records_audit(
    db_session: AsyncSession, actor_user: User
) -> None:
    deviation = Deviation(
        deviation_code=f"SEC3-AUDIT-{uuid.uuid4().hex[:8]}",
        title="删除审计测试偏差",
    )
    db_session.add(deviation)
    await db_session.flush()

    actor = actor_user.id
    await quality_service.delete_deviation(db_session, deviation.id, deleted_by=actor)

    assert deviation.is_deleted is True
    assert deviation.deleted_by == actor
    logs = (
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.resource_type == "quality.deviation",
                    AuditLog.resource_id == deviation.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(logs) == 1
    assert logs[0].user_id == actor


@pytest.mark.anyio
async def test_delete_capa_records_audit(
    db_session: AsyncSession, actor_user: User
) -> None:
    capa = CAPA(capa_code=f"SEC3-AUDIT-{uuid.uuid4().hex[:8]}")
    db_session.add(capa)
    await db_session.flush()

    actor = actor_user.id
    await quality_service.delete_capa(db_session, capa.id, deleted_by=actor)

    assert capa.is_deleted is True
    assert capa.deleted_by == actor
    logs = (
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.resource_type == "quality.capa",
                    AuditLog.resource_id == capa.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(logs) == 1
    assert logs[0].user_id == actor
