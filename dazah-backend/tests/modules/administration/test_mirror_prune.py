"""镜像历史清理与定时同步调度测试（独立测试库）。"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.administration.models import (
    AdministrationFeishuConfig,
    AdministrationFeishuReadRecord,
    AdministrationFeishuReadResource,
    AdministrationFeishuReadSyncRun,
)
from app.modules.administration.scheduled import (
    READ_MIRROR_SYNC_MARGIN,
    AdministrationFeishuReadSyncGenerator,
)
from app.modules.administration.service import (
    build_read_mirror_service,
    prune_resource_history,
)

NOW = datetime.now(UTC)


async def _seed_resource(db_session: AsyncSession, *, stale_run: bool) -> uuid.UUID:
    """种子：一张数据表 + 激活版本 v2 与旧版本 v1 的记录 + 新旧同步运行。"""
    resource = AdministrationFeishuReadResource(
        source_root_id=uuid.uuid4(),
        app_token="app-token",
        table_id=f"tbl-{uuid.uuid4().hex[:8]}",
        title="领用记录",
        active_mirror_version=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        last_complete_sync_at=NOW,
        sync_status="success",
    )
    db_session.add(resource)
    await db_session.flush()
    for index, version in enumerate(
        (
            uuid.UUID("00000000-0000-0000-0000-000000000001"),
            uuid.UUID("00000000-0000-0000-0000-000000000002"),
        )
    ):
        for row in range(2):
            db_session.add(
                AdministrationFeishuReadRecord(
                    resource_id=resource.id,
                    record_id=f"rec-{version.hex[-4]}-{row}",
                    mirror_version=version,
                    raw_fields={
                        "名称": [{"text": f"物品{index}{row}", "type": "text"}]
                    },
                    normalized_fields={},
                )
            )
    db_session.add(
        AdministrationFeishuReadSyncRun(
            resource_id=resource.id,
            mirror_version=uuid.UUID("00000000-0000-0000-0000-000000000002"),
            status="success",
            started_at=NOW - timedelta(days=8),
            completed_at=NOW - timedelta(days=8),
        )
    )
    db_session.add(
        AdministrationFeishuReadSyncRun(
            resource_id=resource.id,
            mirror_version=uuid.UUID("00000000-0000-0000-0000-000000000002"),
            status="success",
            started_at=NOW - timedelta(hours=1),
            completed_at=NOW - timedelta(hours=1),
        )
    )
    await db_session.flush()
    return resource.id


async def _record_versions(
    db_session: AsyncSession, resource_id: uuid.UUID
) -> set[str]:
    rows = await db_session.execute(
        select(AdministrationFeishuReadRecord.mirror_version).where(
            AdministrationFeishuReadRecord.resource_id == resource_id
        )
    )
    return {str(v) for (v,) in rows.all()}


async def test_prune_removes_old_versions_and_stale_runs(
    db_session: AsyncSession,
) -> None:
    resource_id = await _seed_resource(db_session, stale_run=True)
    assert len(await _record_versions(db_session, resource_id)) == 2

    await prune_resource_history(db_session, resource_id)

    remaining = await _record_versions(db_session, resource_id)
    assert remaining == {"00000000-0000-0000-0000-000000000002"}
    runs = (
        await db_session.execute(
            select(AdministrationFeishuReadSyncRun).where(
                AdministrationFeishuReadSyncRun.resource_id == resource_id
            )
        )
    ).scalars().all()
    assert len(runs) == 1
    assert runs[0].started_at > NOW - timedelta(days=1)


async def test_prune_keeps_everything_when_never_synced(
    db_session: AsyncSession,
) -> None:
    resource_id = await _seed_resource(db_session, stale_run=True)
    resource = await db_session.get(AdministrationFeishuReadResource, resource_id)
    assert resource is not None
    resource.active_mirror_version = None
    await db_session.flush()

    await prune_resource_history(db_session, resource_id)
    # 从未完整同步过：保留现有记录不动（可能是最后一份可用镜像）
    assert len(await _record_versions(db_session, resource_id)) == 2


async def test_find_due_uses_margin_and_includes_stale_running(
    db_session: AsyncSession,
) -> None:
    db_session.add(
        AdministrationFeishuConfig(
            config_name="行政飞书",
            app_id="cli_x",
            encrypted_app_secret="secret",
            is_active=True,
        )
    )
    await db_session.flush()
    for title, synced_at in (
        ("新鲜表", NOW - timedelta(minutes=5)),
        ("刚过期表", NOW - READ_MIRROR_SYNC_MARGIN - timedelta(seconds=30)),
        ("从未同步表", None),
    ):
        db_session.add(
            AdministrationFeishuReadResource(
                source_root_id=uuid.uuid4(),
                app_token="app-token",
                table_id=f"tbl-{uuid.uuid4().hex[:8]}",
                title=title,
                last_complete_sync_at=synced_at,
                # 曾经同步中断留下的 running 也要能被再次调度
                sync_status=(
                    "running" if title == "从未同步表" else "success"
                ),
            )
        )
    await db_session.flush()

    due_titles = []
    for item in await AdministrationFeishuReadSyncGenerator().find_due(db_session):
        resource = await db_session.get(
            AdministrationFeishuReadResource, uuid.UUID(item)
        )
        due_titles.append(resource.title if resource else "")
    assert set(due_titles) == {"刚过期表", "从未同步表"}


async def test_find_due_skips_without_config(db_session: AsyncSession) -> None:
    assert await AdministrationFeishuReadSyncGenerator().find_due(db_session) == []


async def test_execute_one_prunes_after_sync(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource_id = await _seed_resource(db_session, stale_run=True)

    class _FakeService:
        async def sync_resource(self, _resource_id: uuid.UUID) -> dict[str, Any]:
            # 模拟平台服务：全量插入新版本 v3 并切换激活版本
            version = uuid.UUID("00000000-0000-0000-0000-000000000003")
            db_session.add(
                AdministrationFeishuReadRecord(
                    resource_id=resource_id,
                    record_id="rec-v3-0",
                    mirror_version=version,
                    raw_fields={},
                    normalized_fields={},
                )
            )
            resource = await db_session.get(
                AdministrationFeishuReadResource, resource_id
            )
            assert resource is not None
            resource.active_mirror_version = version
            await db_session.flush()
            return {
                "resource_id": str(resource_id),
                "record_count": 1,
            }

    async def _fake_build(_session: Any) -> _FakeService:
        return _FakeService()

    monkeypatch.setattr(
        "app.modules.administration.scheduled.build_read_mirror_service", _fake_build
    )
    await AdministrationFeishuReadSyncGenerator().execute_one(
        db_session, str(resource_id)
    )

    remaining = await _record_versions(db_session, resource_id)
    assert remaining == {"00000000-0000-0000-0000-000000000003"}


async def test_execute_one_swallows_expected_app_exception(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.exceptions import AppException

    class _LockedService:
        async def sync_resource(self, _resource_id: uuid.UUID) -> dict[str, Any]:
            raise AppException(message="该数据表正在同步，请稍后重试", status_code=409)

    async def _fake_build(_session: Any) -> _LockedService:
        return _LockedService()

    monkeypatch.setattr(
        "app.modules.administration.scheduled.build_read_mirror_service", _fake_build
    )
    # 不抛异常即可（409 属可预期，下一轮再试）
    await AdministrationFeishuReadSyncGenerator().execute_one(
        db_session, str(uuid.uuid4())
    )


async def test_build_read_mirror_service_uses_latest_config_even_inactive(
    db_session: AsyncSession,
) -> None:
    """is_active 只约束自动同步：读取/手动同步使用最近一份已配置凭证。"""
    db_session.add(
        AdministrationFeishuConfig(
            config_name="行政飞书",
            app_id="cli_latest",
            encrypted_app_secret="secret",
            is_active=False,
        )
    )
    await db_session.flush()
    service = await build_read_mirror_service(db_session)
    assert service.app_id == "cli_latest"
