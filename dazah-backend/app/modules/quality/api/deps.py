"""Quality module API shared dependencies."""

import logging
import uuid
from typing import Any
from urllib.parse import quote

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.redis import acquire_lock, release_lock
from app.platform.identity.data_scope import (
    DepartmentScope,
    resolve_user_department_scope,
)
from app.platform.identity.rbac import resolve_user_permissions

logger = logging.getLogger(__name__)

# 台账 Word 导入文件大小上限（与文件管理模块保持一致）
IMPORT_FILE_MAX_SIZE = 20 * 1024 * 1024


def current_user_id(user_id: uuid.UUID | str) -> str:
    """将 require_user 返回的用户 ID 转为字符串（用于审计追踪）。"""
    return str(user_id)


def build_docx_download_headers(
    filename_utf8: str, fallback_ascii: str
) -> dict[str, str]:
    encoded = quote(filename_utf8)
    return {
        "Content-Disposition": (
            f"attachment; filename={fallback_ascii}; filename*=UTF-8''{encoded}"
        )
    }


def require_user(current_user: CurrentUser) -> uuid.UUID:
    """业务接口默认要求登录：已登录返回用户 ID，未登录抛 401。"""
    if not current_user:
        raise AppException(message="需要登录才能执行此操作", status_code=401)
    return current_user.id


async def try_acquire_action_lock(scope: str, timeout: int = 60) -> bool:
    """短期幂等守卫：防止快速连点重复触发同步/生成类操作。

    返回 True 表示拿到锁；Redis 不可用时降级放行（不阻塞业务）。
    """
    try:
        return await acquire_lock(f"quality:{scope}", timeout=timeout)
    except Exception:
        logger.warning(
            "quality action lock unavailable, degrade to pass-through",
            extra={"module_name": "quality", "scope": scope},
        )
        return True


async def release_action_lock(scope: str) -> None:
    try:
        await release_lock(f"quality:{scope}")
    except Exception:
        logger.debug(
            "quality action lock release skipped",
            extra={"module_name": "quality", "scope": scope},
        )


# ─── 质量 QA 角色细粒度编辑权限 ─────────────────────────────────────────
# 子域 → 全编辑权限码。中间件对任意 quality:*:write 均放行写请求，
# 子域区分由质量端点内 assert_quality_edit_scope 精校验（沿用 warehouse 先例）。
QUALITY_QA_SCOPE_PERMISSIONS: dict[str, str] = {
    "qc": "quality:qc:write",
    "product_qa": "quality:product_qa:write",
    "change_qa": "quality:change_qa:write",
    "validation_qa": "quality:validation_qa:write",
    "system_qa": "quality:system_qa:write",
    "material_qa": "quality:material_qa:write",
}
QUALITY_QA_SCOPE_CODE_SET = frozenset(QUALITY_QA_SCOPE_PERMISSIONS.values())

# 记录"人员列"兜底映射：模型类 → 属性名列表（优先用户ID字段，姓名列兜底）。
# created_by 始终优先；此映射用于存量/未写 created_by 的记录按负责人判定。
_QUALITY_RECORD_PERSON_FIELDS: dict[type, tuple[str, ...]] = {}


def _record_person_field_names(record: Any) -> tuple[str, ...]:
    """返回记录的人员列属性名（懒加载避免模块循环导入）。"""
    if not _QUALITY_RECORD_PERSON_FIELDS:
        from app.modules.quality.models import (
            CapaPlanTrack,
            ChangeActionPlan,
            CleaningValidationRecord,
            Deviation,
            EquipmentQualificationRecord,
            OtherValidationRecord,
            ProcessValidationRecord,
            ValidationRecord,
        )

        _QUALITY_RECORD_PERSON_FIELDS.update(
            {
                Deviation: ("reporter_id", "discoverer"),
                ChangeActionPlan: ("owner_user_id", "owner_name"),
                CapaPlanTrack: ("owner_name",),
                ValidationRecord: ("owner_name",),
                EquipmentQualificationRecord: ("owner_name",),
                ProcessValidationRecord: ("owner_name",),
                CleaningValidationRecord: ("owner_name",),
                OtherValidationRecord: ("owner_name",),
            }
        )
    return _QUALITY_RECORD_PERSON_FIELDS.get(type(record), ())


def _is_uuid_text(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def _record_owner_match(current_user: Any, record: Any) -> bool:
    """记录是否归属当前用户：created_by 命中，或记录人员列命中当前用户。"""
    created_by = getattr(record, "created_by", None)
    if created_by is not None:
        try:
            if str(created_by) == str(current_user.id):
                return True
        except Exception:  # noqa: BLE001
            pass
    for field in _record_person_field_names(record):
        value = getattr(record, field, None)
        if value is None or value == "":
            continue
        if isinstance(value, uuid.UUID) or (
            isinstance(value, str) and _is_uuid_text(value)
        ):
            if str(value) == str(current_user.id):
                return True
        elif isinstance(value, str) and current_user.name:
            if value.strip() == current_user.name.strip():
                return True
    return False


async def assert_quality_edit_scope(
    db: AsyncSession,
    current_user: CurrentUser,
    *,
    scope_permission: str | None = None,
    record: Any = None,
) -> None:
    """质量记录编辑/删除准入（端点内精校验）。

    通过条件（任一）：
      - "*" 通配（超管/DEV 本地开发用户）或模块级 quality:write
      - 命中 scope_permission（当前角色所属子域的全编辑权限）
      - 记录归属当前用户（created_by == 本人，或记录人员列命中本人）
    否则抛 403。列表/详情读取不受此限制（可见性由 resolve_quality_list_scope 控制）。
    """
    assert current_user is not None
    permissions = await resolve_user_permissions(db, current_user.id)
    if "*" in permissions or "quality:write" in permissions:
        return
    if scope_permission and scope_permission in permissions:
        return
    if record is not None and _record_owner_match(current_user, record):
        return
    raise AppException(
        message="无权限编辑该记录（仅可编辑自己创建/负责的记录）",
        status_code=403,
    )


async def resolve_quality_list_scope(
    db: AsyncSession, current_user: CurrentUser
) -> DepartmentScope:
    """质量模块列表/导出可见范围：QA 角色/quality:write/通配 → 全部；否则部门范围。

    仅作用于质量模块端点，不影响 HR/仓储等其他模块的数据范围隔离。
    """
    assert current_user is not None
    permissions = await resolve_user_permissions(db, current_user.id)
    if (
        "*" in permissions
        or "quality:write" in permissions
        or bool(QUALITY_QA_SCOPE_CODE_SET.intersection(permissions))
    ):
        return DepartmentScope(is_all=True)
    return await resolve_user_department_scope(db, current_user)
