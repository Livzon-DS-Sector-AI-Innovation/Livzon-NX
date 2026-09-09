"""质量模块共享人员目录：统一以人事-飞书联系人（hr_feishu_members）为数据源。

「部门联系人」表下线后，质量模块的人员候选、open_id 反查、写飞书人员
字段前的身份换发统一收敛到本模块，与验证模块（validation）既有模式一致：

- 人员候选：仅在职（status=1）、同一 open_id 多部门记录去重；
- 写飞书成员字段：人事 open_id 经 ``hr_identity.translate_hr_open_ids_to_union_ids``
  换发为 union_id，配合 bitable 写接口 ``user_id_type=union_id`` 跨应用写人员字段；
- 数据新鲜度依赖「人事管理-飞书联系人」的手动同步，空表时给出明确引导。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException

logger = logging.getLogger(__name__)

_QA_DEPARTMENT_KEYWORDS = ("QA", "质量保证")


async def get_person_options(
    db: AsyncSession,
    keyword: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """人员选择器候选：人事管理-飞书联系人目录（hr_feishu_members）。

    仅返回在职人员（status=1），同一 open_id 的多部门记录去重；前端拉全量后
    做中文/拼音本地过滤。
    """
    from sqlalchemy import func, select

    from app.modules.hr.models import HrFeishuMember

    normalized = (keyword or "").strip()
    query = (
        select(
            HrFeishuMember.open_id,
            HrFeishuMember.name,
            func.min(HrFeishuMember.department).label("department"),
            func.min(HrFeishuMember.job_title).label("job_title"),
            func.min(HrFeishuMember.email).label("email"),
            func.min(HrFeishuMember.mobile).label("mobile"),
            func.min(HrFeishuMember.enterprise_email).label("enterprise_email"),
            func.min(HrFeishuMember.avatar_url).label("avatar_url"),
        )
        .where(
            HrFeishuMember.is_deleted.is_(False),
            HrFeishuMember.status == "1",  # 在职
            HrFeishuMember.open_id != "",
            HrFeishuMember.name != "",
        )
        .group_by(HrFeishuMember.open_id, HrFeishuMember.name)
        .order_by(HrFeishuMember.name)
        .limit(limit)
    )
    if normalized:
        query = query.where(HrFeishuMember.name.ilike(f"%{normalized}%"))
    rows = (await db.execute(query)).all()
    if not rows:
        total = (
            await db.execute(
                select(func.count())
                .select_from(HrFeishuMember)
                .where(HrFeishuMember.is_deleted.is_(False))
            )
        ).scalar_one()
        if total == 0:
            raise AppException(
                message=(
                    "人事管理-飞书联系人尚未同步，"
                    "请先到「人事管理-飞书联系人」完成同步后再选择人员"
                )
            )
    return [
        {
            "open_id": row.open_id,
            "name": row.name,
            "department": row.department,
            "job_title": row.job_title,
            "email": row.email,
            "mobile": row.mobile,
            "enterprise_email": row.enterprise_email,
            "avatar_url": row.avatar_url,
        }
        for row in rows
    ]


async def resolve_person_by_open_id(
    db: AsyncSession, open_id: str | None
) -> dict[str, Any] | None:
    """按 open_id 精确查找在职人员，返回 name/department/邮箱等；查不到返回 None。"""
    normalized = (open_id or "").strip()
    if not normalized:
        return None
    options = await get_person_options(db, limit=5000)
    for option in options:
        if str(option.get("open_id") or "").strip() == normalized:
            return option
    return None


async def resolve_person_by_name(
    db: AsyncSession,
    name: str | None,
    department: str | None = None,
) -> dict[str, Any] | None:
    """按姓名查找在职人员；给定部门时优先部门内匹配，仍无法唯一定位返回 None。"""
    normalized_name = (name or "").strip()
    if not normalized_name:
        return None
    normalized_department = (department or "").strip()
    options = await get_person_options(db, keyword=normalized_name, limit=5000)
    matches = [
        option
        for option in options
        if str(option.get("name") or "").strip() == normalized_name
    ]
    if not matches:
        return None
    if normalized_department:
        in_department = [
            option
            for option in matches
            if str(option.get("department") or "").strip() == normalized_department
        ]
        if in_department:
            matches = in_department
    if len(matches) != 1:
        # 同名多行且部门也无法消歧，宁可返回 None 由调用方报错，不能随机选人
        return None
    return matches[0]


async def resolve_person_write_id(
    db: AsyncSession,
    value: str | None,
    department: str | None = None,
) -> str | None:
    """把人员字段写入值归一为可写多维表格成员字段的 id。

    - ``on_`` 开头：已是 union_id，原样返回；
    - ``ou_`` 开头：视为人事应用 open_id，经 hr_identity 换发 union_id；
      换发失败（历史记录里质量应用视角的旧成员 id、飞书侧已删除等）原样
      返回，与既有"查不到不阻断"的兜底行为一致；
    - 其他（纯姓名等）：按姓名（可限定部门）唯一匹配在职人员后换发；
      匹配不到或同名无法消歧返回 None，由调用方决定报错语义。
    """
    normalized = str(value or "").strip()
    if not normalized:
        return None
    if normalized.startswith("on_"):
        return normalized

    from app.modules.quality.service.hr_identity import (
        translate_hr_open_ids_to_union_ids,
    )

    if normalized.startswith("ou_"):
        translated = await translate_hr_open_ids_to_union_ids(db, [normalized])
        return translated.get(normalized, normalized)

    person = await resolve_person_by_name(db, normalized, department=department)
    if person is None:
        return None
    open_id = str(person.get("open_id") or "").strip()
    if not open_id:
        return None
    translated = await translate_hr_open_ids_to_union_ids(db, [open_id])
    return translated.get(open_id)


def _is_qa_department(value: str | None) -> bool:
    normalized = str(value or "").strip()
    return any(keyword in normalized for keyword in _QA_DEPARTMENT_KEYWORDS)


async def get_qa_reminder_recipients(db: AsyncSession) -> list[dict[str, Any]]:
    """证书到期提醒/法规推送的 QA 通知人候选（保留部门关键字过滤口径）。

    从人员目录中筛选部门名含 QA/质量保证 的在职人员，按 open_id 去重，
    提供 open_id/name/department/enterprise_email 供邮件与飞书提醒使用。
    """
    options = await get_person_options(db, limit=5000)
    recipients: dict[str, dict[str, Any]] = {}
    for option in options:
        open_id = str(option.get("open_id") or "").strip()
        department = str(option.get("department") or "").strip()
        if not open_id or not _is_qa_department(department):
            continue
        if open_id in recipients:
            continue
        recipients[open_id] = {
            "open_id": open_id,
            "name": str(option.get("name") or "").strip() or "未命名联系人",
            "department": department or None,
            "enterprise_email": (
                str(option.get("enterprise_email") or "").strip() or None
            ),
        }
    return list(recipients.values())
