"""人员月度工作统计：聚合口径、身份归组与端点序列化。"""

import uuid
from datetime import date
from types import SimpleNamespace
from typing import Any

from httpx import AsyncClient
from sqlalchemy import pool as sa_pool
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import get_db as _get_db
from app.main import app
from app.modules.production.seed_culture_service import (
    aggregate_person_monthly,
)
from tests.db_safety import get_pytest_database_url


def _record(
    batch_no: str,
    prepare_date: date,
    **people: Any,
) -> SimpleNamespace:
    """people: 角色列名 → PersonRef 字典列表（模拟 ORM 行属性）。"""
    return SimpleNamespace(
        batch_no=batch_no, prepare_date=prepare_date, **people
    )


def _person(name: str, open_id: str | None = None, avatar: str | None = None):
    return SimpleNamespace(name=name, open_id=open_id, avatar_url=avatar)


def test_aggregate_counts_roles_and_dedupes_batches() -> None:
    """同一人同批多环节计 1 批、各环节分别计数；月外记录剔除。"""
    records = [
        _record(
            "SC-1",
            date(2026, 11, 3),
            prepare_operator=[_person("张三", "ou_z")],
            inoculation_operator=[_person("张三", "ou_z")],
            merge_operator=[_person("李四")],
        ),
        _record(
            "SC-2",
            date(2026, 11, 10),
            prepare_operator=[_person("张三", "ou_z")],
        ),
        # 月外记录：不计入
        _record(
            "SC-3",
            date(2026, 10, 20),
            prepare_operator=[_person("张三", "ou_z")],
        ),
    ]

    rows = aggregate_person_monthly(records, date(2026, 11, 1), date(2026, 11, 30))

    assert len(rows) == 2
    top = rows[0]
    assert top["name"] == "张三"
    assert top["total_batches"] == 2
    assert top["role_counts"]["配制"] == 2
    assert top["role_counts"]["接种"] == 1
    assert top["role_counts"]["并瓶"] == 0
    assert len(top["details"]) == 3
    assert top["details"][0] == {
        "date": "2026-11-03",
        "batch_no": "SC-1",
        "role": "配制",
    }
    second = rows[1]
    assert second["name"] == "李四"
    assert second["total_batches"] == 1


def test_aggregate_groups_by_open_id_then_name() -> None:
    """有 open_id 按 open_id 归组；无 open_id 的手工录入按姓名归组。"""
    records = [
        _record(
            "SC-1",
            date(2026, 11, 3),
            prepare_operator=[
                _person("张三", "ou_z", avatar="https://avatar/z.png")
            ],
        ),
        # 手工录入（无 open_id）：同名归组，头像补齐
        _record(
            "SC-2",
            date(2026, 11, 8),
            prepare_operator=[_person("张三")],
        ),
        # 同名但不同 open_id：不与无名/其他组合并
        _record(
            "SC-3",
            date(2026, 11, 9),
            prepare_operator=[_person("张三", "ou_other")],
        ),
    ]

    rows = aggregate_person_monthly(records, date(2026, 11, 1), date(2026, 11, 30))

    # 同名手工录入（无 open_id）并入同名飞书成员组；不同 open_id 不合并
    assert len(rows) == 2
    z = next(r for r in rows if r["open_id"] == "ou_z")
    assert z["total_batches"] == 2
    assert z["role_counts"]["配制"] == 2
    assert z["avatar_url"] == "https://avatar/z.png"
    other = next(r for r in rows if r["open_id"] == "ou_other")
    assert other["total_batches"] == 1


async def test_person_monthly_endpoint_returns_stats(
    client: AsyncClient,
) -> None:
    """端点真库冒烟：插入两批数据 → 统计返回聚合行与明细。"""

    from app.modules.production.seed_culture_models import SeedCulture

    engine = create_async_engine(
        get_pytest_database_url(get_settings()),
        poolclass=sa_pool.NullPool,
    )
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        inserted: list[str] = []
        async with factory() as session:
            await session.execute(
                SeedCulture.__table__.delete().where(
                    SeedCulture.batch_no.in_(["SC-PM-01", "SC-PM-02"])
                )
            )
            await session.commit()
            for batch_no, day, person in (
                ("SC-PM-01", 3, {"name": "张三", "open_id": "ou_pm"}),
                ("SC-PM-02", 8, {"name": "张三", "open_id": "ou_pm"}),
            ):
                session.add(
                    SeedCulture(
                        batch_no=batch_no,
                        product_name="盐酸林可霉素",
                        prepare_date=date(2026, 11, day),
                        prepare_operator=[person],
                    )
                )
                inserted.append(batch_no)
            await session.commit()

        # 认证覆盖（PermissionMiddleware 认 dependency_overrides）
        from app.platform.identity.models import User

        async def _override_user() -> User:
            return User(
                id=uuid.uuid4(),
                name="统计测试用户",
                username=f"pm-test-{uuid.uuid4().hex[:10]}",
                role="admin",
                status="active",
                auth_source="local",
                grant_version=0,
            )

        import app.platform.identity.deps as identity_deps

        app.dependency_overrides[identity_deps.get_current_user] = _override_user
        res = await client.get(
            "/api/v1/production/seed-cultures/person-monthly",
            params={"month": "2026-11", "product_name": "盐酸林可霉素"},
        )
        assert res.status_code == 200
        rows = res.json()["data"]
        target = next(r for r in rows if r["open_id"] == "ou_pm")
        assert target["name"] == "张三"
        assert target["total_batches"] == 2
        assert target["role_counts"]["配制"] == 2
        assert len(target["details"]) == 2
        app.dependency_overrides.pop(identity_deps.get_current_user, None)

        # 清理
        async with factory() as session:
            await session.execute(
                SeedCulture.__table__.delete().where(
                    SeedCulture.batch_no.in_(inserted)
                )
            )
            await session.commit()
    finally:
        await engine.dispose()


from contextlib import asynccontextmanager  # noqa: E402


@asynccontextmanager
async def _test_db_override(engine: Any):
    """端点请求走同一测试库会话工厂（get_db 覆盖）。"""
    from sqlalchemy.ext.asyncio import AsyncSession

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncSession:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[_get_db] = _override
    try:
        yield
    finally:
        app.dependency_overrides.pop(_get_db, None)
