from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.identity.models import (
    Department,
    Menu,
    PermissionModuleRollout,
    Role,
    RolePageGrant,
    User,
    UserPageGrant,
)


class PagePermissionRepository:
    async def department_labels(self, db: AsyncSession) -> dict[str, str]:
        result = await db.execute(
            select(Department).where(
                Department.is_deleted.is_(False),
                Department.status_is_deleted.is_not(True),
            )
        )
        return {item.feishu_department_id: item.name for item in result.scalars().all()}

    async def active_page_keys(self, db: AsyncSession) -> set[str]:
        result = await db.execute(select(Menu))
        return active_menu_page_keys(list(result.scalars().all()))

    async def active_menu_page_catalog(
        self, db: AsyncSession
    ) -> list[ActiveMenuPage]:
        result = await db.execute(select(Menu))
        return active_menu_page_catalog(list(result.scalars().all()))

    async def existing_department_ids(
        self, db: AsyncSession, *, department_ids: set[str]
    ) -> set[str]:
        if not department_ids:
            return set()
        result = await db.execute(
            select(Department.feishu_department_id).where(
                Department.feishu_department_id.in_(department_ids),
                Department.is_deleted.is_(False),
                Department.status_is_deleted.is_not(True),
            )
        )
        return set(result.scalars().all())

    async def list_role_grants(
        self, db: AsyncSession, *, role_ids: list[UUID]
    ) -> list[RolePageGrant]:
        if not role_ids:
            return []
        result = await db.execute(
            select(RolePageGrant).where(
                RolePageGrant.role_id.in_(role_ids),
                RolePageGrant.is_deleted.is_(False),
            )
        )
        return list(result.scalars().all())

    async def list_user_grants(
        self, db: AsyncSession, *, user_id: UUID
    ) -> list[UserPageGrant]:
        result = await db.execute(
            select(UserPageGrant).where(
                UserPageGrant.user_id == user_id,
                UserPageGrant.is_deleted.is_(False),
            )
        )
        return list(result.scalars().all())

    async def replace_user_grants(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        grants: list[dict[str, Any]],
        actor_id: UUID,
    ) -> list[UserPageGrant]:
        await db.execute(delete(UserPageGrant).where(UserPageGrant.user_id == user_id))
        created: list[UserPageGrant] = []
        for item in grants:
            grant = UserPageGrant(user_id=user_id, **item)
            grant.created_by = actor_id
            grant.updated_by = actor_id
            db.add(grant)
            created.append(grant)
        await db.flush()
        return created

    async def replace_role_grants(
        self,
        db: AsyncSession,
        *,
        role_id: UUID,
        grants: list[dict[str, Any]],
        actor_id: UUID,
    ) -> list[RolePageGrant]:
        await db.execute(delete(RolePageGrant).where(RolePageGrant.role_id == role_id))
        created: list[RolePageGrant] = []
        for item in grants:
            grant = RolePageGrant(role_id=role_id, **item)
            grant.created_by = actor_id
            grant.updated_by = actor_id
            db.add(grant)
            created.append(grant)
        await db.flush()
        return created

    async def get_rollout(
        self, db: AsyncSession, *, module_code: str, for_update: bool = False
    ) -> PermissionModuleRollout | None:
        stmt = select(PermissionModuleRollout).where(
            PermissionModuleRollout.module_code == module_code,
            PermissionModuleRollout.is_deleted.is_(False),
        )
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_rollouts(self, db: AsyncSession) -> list[PermissionModuleRollout]:
        result = await db.execute(
            select(PermissionModuleRollout)
            .where(PermissionModuleRollout.is_deleted.is_(False))
            .order_by(PermissionModuleRollout.module_code)
        )
        return list(result.scalars().all())

    async def count_users(self, db: AsyncSession) -> int:
        result = await db.execute(
            select(User.id).where(User.is_deleted.is_(False), User.status == "active")
        )
        return len(result.scalars().all())

    async def list_active_users(self, db: AsyncSession) -> list[User]:
        result = await db.execute(
            select(User).where(User.is_deleted.is_(False), User.status == "active")
        )
        return list(result.scalars().all())

    async def get_role_for_update(
        self, db: AsyncSession, *, role_id: UUID
    ) -> Role | None:
        result = await db.execute(
            select(Role)
            .where(Role.id == role_id, Role.is_deleted.is_(False))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def bump_active_user_versions(
        self, db: AsyncSession, *, actor_id: UUID
    ) -> list[User]:
        result = await db.scalars(
            update(User)
            .where(User.is_deleted.is_(False), User.status == "active")
            .values(grant_version=User.grant_version + 1, updated_by=actor_id)
            .returning(User)
            .execution_options(populate_existing=True)
        )
        return list(result.all())


@dataclass(frozen=True)
class ActiveMenuPage:
    key: str | None
    name: str
    route_path: str
    root_key: str | None


def active_menu_page_catalog(menus: list[Menu]) -> list[ActiveMenuPage]:
    """Return live routable leaf menus without requiring permission registration."""

    by_id = {menu.id: menu for menu in menus}
    parent_ids = {
        menu.parent_id
        for menu in menus
        if not menu.is_deleted and menu.type != "button"
    }
    active: list[ActiveMenuPage] = []
    for menu in menus:
        if (
            menu.type != "menu"
            or menu.id in parent_ids
            or not menu.route_path
        ):
            continue
        current: Menu | None = menu
        visited: set[UUID] = set()
        root_key: str | None = None
        while current is not None:
            if (
                current.is_deleted
                or current.status != "active"
                or current.id in visited
            ):
                break
            visited.add(current.id)
            if current.parent_id is None:
                root_key = current.key
                active.append(
                    ActiveMenuPage(
                        key=menu.key,
                        name=menu.name,
                        route_path=menu.route_path,
                        root_key=root_key,
                    )
                )
                break
            current = by_id.get(current.parent_id)
    return sorted(active, key=lambda item: (item.route_path, item.key or ""))


def active_menu_page_keys(menus: list[Menu]) -> set[str]:
    """Return pages whose live menu route matches the permission definition."""
    from app.platform.identity.page_policy import get_page_definition

    active: set[str] = set()
    for item in active_menu_page_catalog(menus):
        definition = get_page_definition(item.key or "")
        if definition is not None and item.route_path == definition.route_path:
            active.add(definition.page_key)
    return active
