"""部门联系人业务逻辑（Q1 拆分自 quality_management.py）。"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, DuplicateException, NotFoundException
from app.modules.quality.models import (
    DepartmentContact,
)
from app.modules.quality.schemas import (
    CreateDepartmentContactRequest,
    DepartmentContactOut,
    FeishuDepartmentContactOut,
    UpdateDepartmentContactRequest,
    UpdateFeishuDepartmentContactRequest,
)
from app.platform.identity.data_scope import DepartmentScope, department_in_clause

logger = logging.getLogger(__name__)


def _normalize_feishu_contact_value(value: Any) -> str | None:
    if value in (None, "", []):
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        parts = [_normalize_feishu_contact_value(item) for item in value]
        normalized_parts = [part for part in parts if part]
        return " / ".join(normalized_parts) if normalized_parts else None
    if isinstance(value, dict):
        for key in ("text", "name", "email", "link", "value"):
            if key in value:
                normalized_value = _normalize_feishu_contact_value(value[key])
                if normalized_value:
                    return normalized_value
        return None
    return str(value).strip() or None


def _format_feishu_contact_datetime(value: Any) -> str:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value) / 1000, tz=UTC).isoformat()
    return ""


def _normalize_feishu_contact_person_id(value: Any) -> str | None:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                person_id = str(item.get("id") or "").strip()
                if person_id:
                    return person_id
    if isinstance(value, dict):
        person_id = str(value.get("id") or "").strip()
        if person_id:
            return person_id
        nested_value = value.get("value")
        if isinstance(nested_value, list):
            for item in nested_value:
                if isinstance(item, dict):
                    person_id = str(item.get("id") or "").strip()
                    if person_id:
                        return person_id
    return None


def _normalize_feishu_contact_person_avatar(value: Any) -> str | None:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                avatar = str(item.get("avatar_url") or item.get("avatar") or "").strip()
                if avatar:
                    return avatar
    if isinstance(value, dict):
        avatar = str(value.get("avatar_url") or value.get("avatar") or "").strip()
        if avatar:
            return avatar
        nested_value = value.get("value")
        if isinstance(nested_value, list):
            for item in nested_value:
                if isinstance(item, dict):
                    avatar = str(
                        item.get("avatar_url") or item.get("avatar") or ""
                    ).strip()
                    if avatar:
                        return avatar
    return None


def _serialize_feishu_department_contact(
    record: dict[str, Any],
) -> FeishuDepartmentContactOut:
    fields = record.get("fields", {})
    return FeishuDepartmentContactOut(
        id=record.get("record_id", ""),
        name=_normalize_feishu_contact_value(fields.get("姓名 (人员 )")),
        avatar_url=_normalize_feishu_contact_person_avatar(fields.get("姓名 (人员 )")),
        bitable_user_id=_normalize_feishu_contact_person_id(fields.get("姓名 (人员 )")),
        department=_normalize_feishu_contact_value(fields.get("部门")) or "",
        enterprise_email=_normalize_feishu_contact_value(fields.get("企业邮箱")),
        open_id=_normalize_feishu_contact_value(fields.get("Open ID")),
        department_head_name=_normalize_feishu_contact_value(
            fields.get("上级负责人姓名 (人员 )")
        ),
        department_head_avatar_url=_normalize_feishu_contact_person_avatar(
            fields.get("上级负责人姓名 (人员 )")
        ),
        department_head_bitable_user_id=_normalize_feishu_contact_person_id(
            fields.get("上级负责人姓名 (人员 )")
        ),
        department_head_enterprise_email=_normalize_feishu_contact_value(
            fields.get("部门负责人企业邮箱")
        ),
        department_head_open_id=_normalize_feishu_contact_value(
            fields.get("部门负责人Open ID")
        ),
        feishu_record_id=record.get("record_id"),
        created_at=_format_feishu_contact_datetime(record.get("created_time")),
        updated_at=_format_feishu_contact_datetime(record.get("last_modified_time")),
    )


async def get_department_contact_list(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    scope: DepartmentScope | None = None,
) -> dict[str, Any]:
    query = select(DepartmentContact).where(DepartmentContact.is_deleted.is_(False))
    count_query = (
        select(func.count())
        .select_from(DepartmentContact)
        .where(DepartmentContact.is_deleted.is_(False))
    )
    # 部门数据隔离（后台可配置可见部门范围）
    scope_clause = (
        department_in_clause(DepartmentContact.department, scope) if scope else None
    )
    if scope_clause is not None:
        query = query.where(scope_clause)
        count_query = count_query.where(scope_clause)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = (
        query.order_by(DepartmentContact.department, DepartmentContact.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "items": [
            DepartmentContactOut.model_validate(item).model_dump(mode="json")
            for item in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_department_contact_list_from_feishu(
    db: AsyncSession, page: int = 1, page_size: int = 20
) -> dict[str, Any]:
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service
    from app.platform.integrations.feishu.bitable import BitableClient

    runtime = await feishu_sync_service.feishu_sync._resolve_runtime(db)
    entity = runtime.get_entity_config("department_contact", direction="pull")
    if (
        not runtime.is_enabled()
        or not entity
        or not entity.app_token
        or not entity.table_id
    ):
        raise AppException(message="部门联系人飞书同步未启用或未完成配置")

    client = BitableClient(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    # 全量拉取走 GET /records 列表接口：records/search 无过滤条件时
    # 最多返回 500 条且翻页循环，无法取到全部数据（实测验证）
    records = await client.list_all_records(
        entity.table_id,
        automatic_fields=True,
    )

    serialized = [_serialize_feishu_department_contact(record) for record in records]
    serialized.sort(key=lambda item: (item.department, item.name or ""))
    total = len(serialized)
    start = max(page - 1, 0) * page_size
    end = start + page_size
    return {
        "items": [item.model_dump(mode="json") for item in serialized[start:end]],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def _resolve_person_bitable_user_id(
    db: AsyncSession,
    open_id: str | None,
) -> str | None:
    """把 HR 飞书联系人的 open_id 解析为部门联系人多维表人员字段可用的 id。

    通过扫描部门联系人表按 open_id 匹配到对应 bitable_user_id；找不到则回退
    返回原 open_id（与既有 change_action_plan._resolve_bitable_user_id 一致）。
    """
    normalized = str(open_id or "").strip()
    if not normalized:
        return None

    contacts = await get_department_contact_list_from_feishu(
        db,
        page=1,
        page_size=1000,
    )
    for contact in contacts.get("items", []):
        if str(contact.get("open_id") or "").strip() == normalized:
            bitable_user_id = str(contact.get("bitable_user_id") or "").strip()
            if bitable_user_id:
                return bitable_user_id
        if str(contact.get("department_head_open_id") or "").strip() == normalized:
            bitable_user_id = str(
                contact.get("department_head_bitable_user_id") or ""
            ).strip()
            if bitable_user_id:
                return bitable_user_id
    return normalized


async def update_department_contact_from_feishu(
    db: AsyncSession,
    record_id: str,
    data: UpdateFeishuDepartmentContactRequest,
) -> dict[str, Any]:
    """把部门联系人整条记录写回飞书多维表。

    姓名、上级负责人两个人员字段身份来自 HR 飞书联系人（open_id），后端把
    open_id 解析为该表人员字段可用 id 后写回；文本字段直接写入。
    """
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service
    from app.platform.integrations.feishu.bitable import BitableClient

    runtime = await feishu_sync_service.feishu_sync._resolve_runtime(db)
    entity = runtime.get_entity_config("department_contact", direction="push")
    if (
        not runtime.is_enabled()
        or not entity
        or not entity.app_token
        or not entity.table_id
    ):
        raise AppException(message="部门联系人飞书同步未启用或未完成配置")

    fields: dict[str, Any] = {}
    if data.open_id is None:
        fields["姓名 (人员 )"] = []
    else:
        user_id = await _resolve_person_bitable_user_id(db, data.open_id)
        if not user_id:
            raise AppException(message="人员不能为空")
        fields["姓名 (人员 )"] = [{"id": user_id}]
    if data.department_head_open_id is None:
        fields["上级负责人姓名 (人员 )"] = []
    else:
        head_user_id = await _resolve_person_bitable_user_id(
            db, data.department_head_open_id
        )
        if not head_user_id:
            raise AppException(message="上级负责人不能为空")
        fields["上级负责人姓名 (人员 )"] = [{"id": head_user_id}]
    if data.department is not None:
        fields["部门"] = str(data.department).strip()
    if data.enterprise_email is not None:
        fields["企业邮箱"] = str(data.enterprise_email).strip()

    if not fields:
        raise AppException(message="没有可更新的字段")

    client = BitableClient(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    record = await client.update_record(entity.table_id, record_id, fields)

    return _serialize_feishu_department_contact(record).model_dump(mode="json")


async def _ensure_department_contact_open_id_unique(
    db: AsyncSession,
    open_id: str | None,
    *,
    exclude_contact_id: uuid.UUID | None = None,
) -> None:
    if not open_id:
        return
    conditions = [
        DepartmentContact.open_id == open_id,
        DepartmentContact.is_deleted.is_(False),
    ]
    if exclude_contact_id is not None:
        conditions.append(DepartmentContact.id != exclude_contact_id)
    result = await db.execute(select(DepartmentContact).where(*conditions))
    if result.scalar_one_or_none():
        raise DuplicateException(field="open_id", value=str(open_id))


async def upsert_department_contact(
    db: AsyncSession,
    data: CreateDepartmentContactRequest | UpdateDepartmentContactRequest,
    department: str | None,
    user_id: str,
) -> dict[str, bool]:
    del department, user_id
    if not isinstance(data, CreateDepartmentContactRequest):
        raise AppException(message="CreateDepartmentContactRequest required")
    await _ensure_department_contact_open_id_unique(db, data.open_id)

    contact = DepartmentContact(**data.model_dump())
    db.add(contact)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {"success": True}


async def update_department_contact(
    db: AsyncSession,
    contact_id: uuid.UUID,
    data: UpdateDepartmentContactRequest,
) -> dict[str, bool]:
    result = await db.execute(
        select(DepartmentContact).where(
            DepartmentContact.id == contact_id,
            DepartmentContact.is_deleted.is_(False),
        )
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise NotFoundException(resource="部门联系人", resource_id=str(contact_id))

    update_data = data.model_dump(exclude_unset=True)
    await _ensure_department_contact_open_id_unique(
        db,
        update_data.get("open_id"),
        exclude_contact_id=contact_id,
    )
    for field, value in update_data.items():
        setattr(contact, field, value)
    contact.updated_at = datetime.now(UTC)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {"success": True}


async def delete_department_contact(
    db: AsyncSession, contact_id: uuid.UUID
) -> dict[str, bool]:
    result = await db.execute(
        select(DepartmentContact).where(
            DepartmentContact.id == contact_id, DepartmentContact.is_deleted.is_(False)
        )
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise NotFoundException(resource="部门联系人", resource_id=str(contact_id))
    contact.is_deleted = True
    contact.updated_at = datetime.now(UTC)
    try:
        await db.commit()

    except Exception:
        await db.rollback()

        raise
    return {"success": True}
