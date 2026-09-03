from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.identity.models import (
    DataScopeRule,
    Department,
    DepartmentRoleRule,
    ExternalIdentityBinding,
    FeishuConfig,
    FeishuUserToken,
    Menu,
    Permission,
    Role,
    RoleMenu,
    RolePermission,
    User,
    UserRole,
)


class ExternalIdentityConflictError(ValueError):
    """Raised when supplied Feishu identifiers do not resolve to one binding."""


class ExternalIdentityBindingRepository:
    async def create(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        platform: str,
        app_fingerprint: str,
        external_user_id: str | None,
        external_open_id: str | None,
        external_union_id: str | None,
        local_user_id: UUID,
        source: str,
        actor_id: UUID,
    ) -> ExternalIdentityBinding:
        binding = ExternalIdentityBinding(
            tenant_id=tenant_id,
            platform=platform,
            app_fingerprint=app_fingerprint,
            external_user_id=external_user_id,
            external_open_id=external_open_id,
            external_union_id=external_union_id,
            local_user_id=local_user_id,
            status="active",
            source=source,
            verified_at=datetime.now(UTC),
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(binding)
        await session.flush()
        return binding

    async def get(
        self,
        session: AsyncSession,
        binding_id: UUID,
    ) -> ExternalIdentityBinding | None:
        return cast(
            ExternalIdentityBinding | None,
            await session.scalar(
                select(ExternalIdentityBinding).where(
                    ExternalIdentityBinding.id == binding_id,
                    ExternalIdentityBinding.is_deleted == False,  # noqa: E712
                )
            ),
        )

    async def set_status(
        self,
        session: AsyncSession,
        binding: ExternalIdentityBinding,
        *,
        status_value: str,
        actor_id: UUID,
    ) -> ExternalIdentityBinding:
        binding.status = status_value
        binding.updated_by = actor_id
        await session.flush()
        await session.refresh(binding)
        return binding

    async def resolve(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        platform: str,
        app_fingerprint: str,
        external_user_id: str | None,
        external_open_id: str | None,
        external_union_id: str | None,
    ) -> ExternalIdentityBinding | None:
        identifiers = [
            ExternalIdentityBinding.external_user_id == external_user_id
            if external_user_id
            else None,
            ExternalIdentityBinding.external_open_id == external_open_id
            if external_open_id
            else None,
            ExternalIdentityBinding.external_union_id == external_union_id
            if external_union_id
            else None,
        ]
        clauses = [item for item in identifiers if item is not None]
        if not clauses:
            return None
        result = await session.execute(
            select(ExternalIdentityBinding).where(
                ExternalIdentityBinding.tenant_id == tenant_id,
                ExternalIdentityBinding.platform == platform,
                ExternalIdentityBinding.app_fingerprint == app_fingerprint,
                ExternalIdentityBinding.status == "active",
                ExternalIdentityBinding.is_deleted == False,  # noqa: E712
                or_(*clauses),
            )
        )
        matches = list(result.scalars().unique().all())
        if len(matches) > 1:
            raise ExternalIdentityConflictError(
                "Feishu identity identifiers resolve to different bindings"
            )
        if not matches:
            return None
        binding = matches[0]
        supplied = {
            "external_user_id": external_user_id,
            "external_open_id": external_open_id,
            "external_union_id": external_union_id,
        }
        if any(
            value is not None
            and getattr(binding, field) is not None
            and getattr(binding, field) != value
            for field, value in supplied.items()
        ):
            raise ExternalIdentityConflictError(
                "Feishu identity identifiers conflict with the trusted binding"
            )
        return binding

    async def list_page(
        self,
        session: AsyncSession,
        *,
        page: int,
        page_size: int,
        keyword: str | None = None,
        tenant_id: str | None = None,
        status_value: str | None = None,
        department: str | None = None,
        active_since: datetime | None = None,
    ) -> tuple[list[tuple[ExternalIdentityBinding, User]], int]:
        conditions = [ExternalIdentityBinding.is_deleted == False]  # noqa: E712
        if tenant_id:
            conditions.append(ExternalIdentityBinding.tenant_id == tenant_id)
        if status_value:
            conditions.append(ExternalIdentityBinding.status == status_value)
        if department:
            conditions.append(User.department.ilike(f"%{department.strip()}%"))
        if active_since:
            conditions.append(ExternalIdentityBinding.last_seen_at >= active_since)
        if keyword:
            pattern = f"%{keyword.strip()}%"
            conditions.append(
                or_(
                    ExternalIdentityBinding.external_user_id.ilike(pattern),
                    ExternalIdentityBinding.external_open_id.ilike(pattern),
                    ExternalIdentityBinding.external_union_id.ilike(pattern),
                    User.name.ilike(pattern),
                    User.employee_no.ilike(pattern),
                )
            )
        total = int(
            await session.scalar(
                select(func.count())
                .select_from(ExternalIdentityBinding)
                .join(User, User.id == ExternalIdentityBinding.local_user_id)
                .where(*conditions)
            )
            or 0
        )
        result = await session.execute(
            select(ExternalIdentityBinding, User)
            .join(User, User.id == ExternalIdentityBinding.local_user_id)
            .where(*conditions)
            .order_by(ExternalIdentityBinding.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return [(row[0], row[1]) for row in result.all()], total

    async def list_for_app(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        app_fingerprint: str,
    ) -> list[ExternalIdentityBinding]:
        result = await session.execute(
            select(ExternalIdentityBinding).where(
                ExternalIdentityBinding.tenant_id == tenant_id,
                ExternalIdentityBinding.platform == "feishu",
                ExternalIdentityBinding.app_fingerprint == app_fingerprint,
                ExternalIdentityBinding.is_deleted == False,  # noqa: E712
            )
        )
        return list(result.scalars().all())


class UserRepository:
    async def get_by_id(
        self, session: AsyncSession, user_id: UUID | str
    ) -> User | None:
        if isinstance(user_id, str):
            try:
                user_id = UUID(user_id)
            except ValueError:
                return None
        result = await session.execute(
            select(User).where(
                User.id == user_id,
                User.is_deleted == False,  # noqa: E712
            ),
        )
        return result.scalar_one_or_none()

    async def get_by_username(
        self,
        session: AsyncSession,
        username: str,
    ) -> User | None:
        result = await session.execute(
            select(User).where(
                func.lower(User.username) == username.lower(),
                User.is_deleted == False,  # noqa: E712
            ),
        )
        return result.scalar_one_or_none()

    async def get_by_username_including_deleted(
        self,
        session: AsyncSession,
        username: str,
    ) -> User | None:
        result = await session.execute(
            select(User).where(
                func.lower(User.username) == username.lower(),
            ),
        )
        return result.scalar_one_or_none()

    async def get_by_login_identifier(
        self,
        session: AsyncSession,
        identifier: str,
    ) -> User | None:
        normalized = identifier.strip().lower()
        result = await session.execute(
            select(User).where(
                User.is_deleted == False,  # noqa: E712
                or_(
                    func.lower(User.username) == normalized,
                    func.lower(User.email) == normalized,
                    User.mobile == identifier,
                    User.employee_no == identifier,
                ),
            ),
        )
        return result.scalar_one_or_none()

    async def get_by_feishu_open_id(
        self,
        session: AsyncSession,
        open_id: str,
    ) -> User | None:
        result = await session.execute(
            select(User).where(
                User.feishu_open_id == open_id,
                User.is_deleted == False,  # noqa: E712
            ),
        )
        return result.scalar_one_or_none()

    async def get_by_feishu_user_id(
        self,
        session: AsyncSession,
        user_id: str,
    ) -> User | None:
        result = await session.execute(
            select(User).where(
                User.feishu_user_id == user_id,
                User.is_deleted == False,  # noqa: E712
            ),
        )
        return result.scalar_one_or_none()

    async def find_by_livzon_recipient_identifier(
        self,
        session: AsyncSession,
        identifier: str,
    ) -> list[User]:
        normalized = identifier.strip()
        if not normalized:
            return []

        user = await self.get_by_id(session, normalized)
        if user:
            return [user]

        lowered = normalized.lower()
        result = await session.execute(
            select(User).where(
                User.is_deleted == False,  # noqa: E712
                or_(
                    User.feishu_user_id == normalized,
                    User.feishu_open_id == normalized,
                    User.employee_no == normalized,
                    User.mobile == normalized,
                    func.lower(User.email) == lowered,
                    func.lower(User.enterprise_email) == lowered,
                    User.name == normalized,
                ),
            )
        )
        return list(result.scalars().all())

    async def create(
        self,
        session: AsyncSession,
        *,
        name: str,
        feishu_user_id: str | None = None,
        feishu_open_id: str | None = None,
        feishu_union_id: str | None = None,
        en_name: str | None = None,
        employee_no: str | None = None,
        email: str | None = None,
        enterprise_email: str | None = None,
        mobile: str | None = None,
        avatar_url: str | None = None,
        avatar_thumb: str | None = None,
        avatar_middle: str | None = None,
        avatar_big: str | None = None,
        tenant_key: str | None = None,
        department: str | None = None,
        position: str | None = None,
        feishu_department_ids: str | None = None,
        username: str | None = None,
        password_hash: str | None = None,
        role: str = "user",
        status: str = "active",
        auth_source: str = "feishu",
    ) -> User:
        user = User(
            name=name,
            username=username,
            password_hash=password_hash,
            role=role,
            status=status,
            auth_source=auth_source,
            feishu_user_id=feishu_user_id,
            feishu_open_id=feishu_open_id,
            feishu_union_id=feishu_union_id,
            en_name=en_name,
            employee_no=employee_no,
            email=email,
            enterprise_email=enterprise_email,
            mobile=mobile,
            avatar_url=avatar_url,
            avatar_thumb=avatar_thumb,
            avatar_middle=avatar_middle,
            avatar_big=avatar_big,
            tenant_key=tenant_key,
            department=department,
            position=position,
            feishu_department_ids=feishu_department_ids,
        )
        session.add(user)
        await session.flush()
        return user

    async def list_users(
        self,
        session: AsyncSession,
        *,
        keyword: str | None = None,
        role: str | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[User], int]:
        base = select(User).where(User.is_deleted == False)  # noqa: E712
        count_stmt = (
            select(func.count())
            .select_from(User)
            .where(
                User.is_deleted == False  # noqa: E712
            )
        )

        if keyword:
            pattern = f"%{keyword}%"
            filter_expr = or_(
                User.name.ilike(pattern),
                User.username.ilike(pattern),
                User.email.ilike(pattern),
                User.mobile.ilike(pattern),
                User.employee_no.ilike(pattern),
            )
            base = base.where(filter_expr)
            count_stmt = count_stmt.where(filter_expr)
        if role:
            base = base.where(User.role == role)
            count_stmt = count_stmt.where(User.role == role)
        if status:
            base = base.where(User.status == status)
            count_stmt = count_stmt.where(User.status == status)

        total = int((await session.execute(count_stmt)).scalar_one())
        result = await session.execute(
            base.order_by(User.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total

    async def list_all(
        self,
        session: AsyncSession,
        *,
        department_id: str | None = None,
        keyword: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[User], int]:
        """分页查询所有用户，支持按部门/关键词筛选。"""
        base = select(User).where(User.is_deleted == False)  # noqa: E712

        if department_id:
            base = base.where(
                User.feishu_department_ids.contains(department_id),
            )
        if keyword:
            base = base.where(
                User.name.ilike(f"%{keyword}%"),
            )

        count_stmt = select(User.id).where(User.is_deleted == False)  # noqa: E712
        if department_id:
            count_stmt = count_stmt.where(
                User.feishu_department_ids.contains(department_id),
            )
        if keyword:
            count_stmt = count_stmt.where(
                User.name.ilike(f"%{keyword}%"),
            )
        total_result = await session.execute(count_stmt)
        total = len(total_result.scalars().all())

        stmt = base.order_by(User.name).offset(offset).limit(limit)
        result = await session.execute(stmt)
        users = list(result.scalars().all())
        return users, total


class DepartmentRepository:
    async def get_by_feishu_id(
        self,
        session: AsyncSession,
        feishu_dept_id: str,
    ) -> Department | None:
        result = await session.execute(
            select(Department).where(
                Department.feishu_department_id == feishu_dept_id,
            ),
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        session: AsyncSession,
        *,
        include_deleted: bool = False,
    ) -> list[Department]:
        stmt = select(Department).where(
            Department.is_deleted == False,  # noqa: E712
        )
        if not include_deleted:
            stmt = stmt.where(Department.status_is_deleted == False)  # noqa: E712
        stmt = stmt.order_by(Department.order, Department.name)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_children(
        self,
        session: AsyncSession,
        parent_id: str,
    ) -> list[Department]:
        stmt = (
            select(Department)
            .where(
                Department.parent_feishu_department_id == parent_id,
                Department.is_deleted == False,  # noqa: E712
                Department.status_is_deleted == False,  # noqa: E712
            )
            .order_by(Department.order, Department.name)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


class FeishuConfigRepository:
    async def get_active(self, session: AsyncSession) -> FeishuConfig | None:
        result = await session.execute(
            select(FeishuConfig)
            .where(
                FeishuConfig.is_deleted == False,  # noqa: E712
                FeishuConfig.is_active.is_(True),
            )
            .order_by(FeishuConfig.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest(self, session: AsyncSession) -> FeishuConfig | None:
        result = await session.execute(
            select(FeishuConfig)
            .where(FeishuConfig.is_deleted == False)  # noqa: E712
            .order_by(FeishuConfig.updated_at.desc())
        )
        return result.scalar_one_or_none()

    async def get_by_name_including_deleted(
        self, session: AsyncSession, config_name: str
    ) -> FeishuConfig | None:
        result = await session.execute(
            select(FeishuConfig)
            .where(FeishuConfig.config_name == config_name)
            .order_by(FeishuConfig.updated_at.desc())
        )
        return result.scalar_one_or_none()

    async def save(self, session: AsyncSession, config: FeishuConfig) -> FeishuConfig:
        session.add(config)
        await session.flush()
        return config


class FeishuUserTokenRepository:
    async def get_by_user_and_app(
        self,
        session: AsyncSession,
        *,
        local_user_id: UUID | str,
        app_id: str,
    ) -> FeishuUserToken | None:
        if isinstance(local_user_id, str):
            try:
                local_user_id = UUID(local_user_id)
            except ValueError:
                return None
        result = await session.execute(
            select(FeishuUserToken).where(
                FeishuUserToken.local_user_id == local_user_id,
                FeishuUserToken.app_id == app_id,
                FeishuUserToken.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def save(
        self,
        session: AsyncSession,
        token: FeishuUserToken,
    ) -> FeishuUserToken:
        session.add(token)
        await session.flush()
        return token


class RbacRepository:
    """RBAC 查询与写入，保留当前身份仓储的兼容实现。"""

    async def list_roles(self, session: AsyncSession) -> list[Role]:
        result = await session.execute(
            select(Role)
            .where(Role.is_deleted.is_(False))
            .order_by(Role.is_system.desc(), Role.created_at)
        )
        return list(result.scalars().all())

    async def get_role_by_id(self, session: AsyncSession, role_id: UUID) -> Role | None:
        result = await session.execute(
            select(Role).where(Role.id == role_id, Role.is_deleted.is_(False))
        )
        return result.scalar_one_or_none()

    async def get_role_by_code(self, session: AsyncSession, code: str) -> Role | None:
        result = await session.execute(
            select(Role).where(Role.code == code, Role.is_deleted.is_(False))
        )
        return result.scalar_one_or_none()

    async def create_role(
        self,
        session: AsyncSession,
        *,
        name: str,
        code: str,
        description: str | None = None,
    ) -> Role:
        role = Role(name=name, code=code, description=description, is_system=False)
        session.add(role)
        await session.flush()
        return role

    async def update_role(
        self,
        session: AsyncSession,
        role: Role,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Role:
        if name is not None:
            role.name = name
        if description is not None:
            role.description = description
        await session.flush()
        return role

    async def soft_delete_role(self, session: AsyncSession, role: Role) -> None:
        role.is_deleted = True
        await session.flush()

    async def list_permissions(self, session: AsyncSession) -> list[Permission]:
        result = await session.execute(
            select(Permission)
            .where(Permission.is_deleted.is_(False))
            .order_by(Permission.module, Permission.action)
        )
        return list(result.scalars().all())

    async def list_role_permission_codes(
        self, session: AsyncSession, role_id: UUID
    ) -> list[str]:
        result = await session.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(
                RolePermission.role_id == role_id,
                RolePermission.is_deleted.is_(False),
                Permission.is_deleted.is_(False),
            )
        )
        return list(result.scalars().all())

    async def set_role_permissions(
        self,
        session: AsyncSession,
        role_id: UUID,
        permission_ids: list[UUID],
    ) -> None:
        await session.execute(
            delete(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.is_deleted.is_(False),
            )
        )
        for permission_id in dict.fromkeys(permission_ids):
            session.add(RolePermission(role_id=role_id, permission_id=permission_id))
        await session.flush()

    async def list_user_roles(self, session: AsyncSession, user_id: UUID) -> list[Role]:
        result = await session.execute(
            select(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(
                UserRole.user_id == user_id,
                UserRole.source == "manual",
                UserRole.is_deleted.is_(False),
                Role.is_deleted.is_(False),
            )
        )
        return list(result.scalars().all())

    async def assign_user_role(
        self, session: AsyncSession, user_id: UUID, role_id: UUID
    ) -> UserRole:
        result = await session.execute(
            select(UserRole).where(
                UserRole.user_id == user_id,
                UserRole.role_id == role_id,
                UserRole.source == "manual",
                UserRole.is_deleted.is_(False),
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = UserRole(user_id=user_id, role_id=role_id, source="manual")
            session.add(row)
            await session.flush()
        return row

    async def remove_user_role(
        self, session: AsyncSession, user_id: UUID, role_id: UUID
    ) -> bool:
        result = await session.execute(
            select(UserRole).where(
                UserRole.user_id == user_id,
                UserRole.role_id == role_id,
                UserRole.source == "manual",
                UserRole.is_deleted.is_(False),
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False
        row.is_deleted = True
        await session.flush()
        return True

    async def list_dept_rules(self, session: AsyncSession) -> list[DepartmentRoleRule]:
        result = await session.execute(
            select(DepartmentRoleRule)
            .where(DepartmentRoleRule.is_deleted.is_(False))
            .order_by(DepartmentRoleRule.created_at)
        )
        return list(result.scalars().all())

    async def create_dept_rule(
        self,
        session: AsyncSession,
        *,
        role_id: UUID,
        feishu_department_id: str | None = None,
        department_name: str | None = None,
    ) -> DepartmentRoleRule:
        rule = DepartmentRoleRule(
            role_id=role_id,
            feishu_department_id=feishu_department_id,
            department_name=department_name,
        )
        session.add(rule)
        await session.flush()
        return rule

    async def get_dept_rule_by_id(
        self, session: AsyncSession, rule_id: UUID
    ) -> DepartmentRoleRule | None:
        result = await session.execute(
            select(DepartmentRoleRule).where(
                DepartmentRoleRule.id == rule_id,
                DepartmentRoleRule.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def soft_delete_dept_rule(
        self, session: AsyncSession, rule: DepartmentRoleRule
    ) -> None:
        rule.is_deleted = True
        await session.flush()

    async def list_data_scope_rules(self, session: AsyncSession) -> list[DataScopeRule]:
        result = await session.execute(
            select(DataScopeRule)
            .where(DataScopeRule.is_deleted.is_(False))
            .order_by(DataScopeRule.created_at)
        )
        return list(result.scalars().all())

    async def get_data_scope_rule_by_id(
        self, session: AsyncSession, rule_id: UUID
    ) -> DataScopeRule | None:
        result = await session.execute(
            select(DataScopeRule).where(
                DataScopeRule.id == rule_id,
                DataScopeRule.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_data_scope_rule_by_target(
        self,
        session: AsyncSession,
        *,
        role_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> DataScopeRule | None:
        stmt = select(DataScopeRule).where(DataScopeRule.is_deleted.is_(False))
        if role_id is not None:
            stmt = stmt.where(DataScopeRule.role_id == role_id)
        if user_id is not None:
            stmt = stmt.where(DataScopeRule.user_id == user_id)
        result = await session.execute(stmt)
        return result.scalars().first()

    async def create_data_scope_rule(
        self,
        session: AsyncSession,
        *,
        role_id: UUID | None = None,
        user_id: UUID | None = None,
        scope_type: str,
        department_names: str | None = None,
    ) -> DataScopeRule:
        rule = DataScopeRule(
            role_id=role_id,
            user_id=user_id,
            scope_type=scope_type,
            department_names=department_names,
        )
        session.add(rule)
        await session.flush()
        return rule

    async def update_data_scope_rule(
        self, session: AsyncSession, rule: DataScopeRule, **fields: object
    ) -> DataScopeRule:
        for field, value in fields.items():
            setattr(rule, field, value)
        await session.flush()
        return rule

    async def soft_delete_data_scope_rule(
        self, session: AsyncSession, rule: DataScopeRule
    ) -> None:
        rule.is_deleted = True
        await session.flush()


class MenuRepository:
    """菜单与角色菜单绑定的查询/写入。"""

    async def list_all(self, session: AsyncSession) -> list[Menu]:
        result = await session.execute(
            select(Menu)
            .where(Menu.is_deleted.is_(False))
            .order_by(Menu.sort_order, Menu.created_at)
        )
        return list(result.scalars().all())

    async def get_by_id(self, session: AsyncSession, menu_id: UUID) -> Menu | None:
        result = await session.execute(
            select(Menu).where(Menu.id == menu_id, Menu.is_deleted.is_(False))
        )
        return result.scalar_one_or_none()

    async def get_by_key(
        self, session: AsyncSession, key: str, *, include_deleted: bool = False
    ) -> Menu | None:
        statement = select(Menu).where(Menu.key == key)
        if not include_deleted:
            statement = statement.where(Menu.is_deleted.is_(False))
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    async def list_children(self, session: AsyncSession, menu_id: UUID) -> list[Menu]:
        result = await session.execute(
            select(Menu).where(
                Menu.parent_id == menu_id,
                Menu.is_deleted.is_(False),
            )
        )
        return list(result.scalars().all())

    async def create(self, session: AsyncSession, **fields: object) -> Menu:
        menu = Menu(**fields)
        session.add(menu)
        await session.flush()
        return menu

    async def update(self, session: AsyncSession, menu: Menu, **fields: object) -> Menu:
        for field, value in fields.items():
            setattr(menu, field, value)
        await session.flush()
        return menu

    async def soft_delete(self, session: AsyncSession, menu: Menu) -> None:
        menu.is_deleted = True
        await session.execute(
            delete(RoleMenu).where(
                RoleMenu.menu_id == menu.id,
                RoleMenu.is_deleted.is_(False),
            )
        )
        await session.flush()

    async def list_role_menus(self, session: AsyncSession, role_id: UUID) -> list[Menu]:
        result = await session.execute(
            select(Menu)
            .join(RoleMenu, RoleMenu.menu_id == Menu.id)
            .where(
                RoleMenu.role_id == role_id,
                RoleMenu.is_deleted.is_(False),
                Menu.is_deleted.is_(False),
            )
        )
        return list(result.scalars().all())

    async def list_role_menu_ids(
        self, session: AsyncSession, role_id: UUID
    ) -> list[UUID]:
        return [menu.id for menu in await self.list_role_menus(session, role_id)]

    async def set_role_menus(
        self, session: AsyncSession, role_id: UUID, menu_ids: list[UUID]
    ) -> None:
        await session.execute(
            delete(RoleMenu).where(
                RoleMenu.role_id == role_id,
                RoleMenu.is_deleted.is_(False),
            )
        )
        for menu_id in dict.fromkeys(menu_ids):
            session.add(RoleMenu(role_id=role_id, menu_id=menu_id))
        await session.flush()
