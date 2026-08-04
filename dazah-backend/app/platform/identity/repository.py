from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.identity.models import (
    Department,
    ExternalIdentityBinding,
    FeishuConfig,
    FeishuUserToken,
    User,
)


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
        return result.scalar_one_or_none()

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
