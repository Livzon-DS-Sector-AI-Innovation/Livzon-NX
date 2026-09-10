"""人事-飞书联系人身份桥接：人事应用 open_id → 跨应用 union_id。

飞书每个自建应用为同一用户生成不同的 open_id，人事应用目录里拿到的
open_id 无法直接写入质量应用访问的多维表格成员字段（报 1254066
UserFieldConvFail）。union_id 在同一租户的全部自建应用间保持一致，
配合 bitable 写接口的 user_id_type=union_id 即可跨应用写人员字段，
不再依赖「部门联系人」表做姓名反查。
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.redis import cache_get, cache_set

logger = logging.getLogger(__name__)

# union_id 永久稳定，长缓存即可
_UNION_ID_CACHE_PREFIX = "quality:hr_union_id:"
_UNION_ID_CACHE_TTL = 30 * 24 * 3600


async def translate_hr_open_ids_to_union_ids(
    db: AsyncSession,
    open_ids: list[str],
) -> dict[str, str]:
    """批量把人事应用 open_id 翻译为 union_id。

    结果按 open_id 缓存 30 天；查不到（人员已离职/未同步/缓存过期且
    飞书侧已删除）的 id 不出现在返回结果中，由调用方决定如何报错。
    """
    unique_ids = list(
        dict.fromkeys(oid.strip() for oid in open_ids if oid and oid.strip())
    )
    result: dict[str, str] = {}
    missing: list[str] = []
    for open_id in unique_ids:
        cached = await cache_get(f"{_UNION_ID_CACHE_PREFIX}{open_id}")
        if cached:
            result[open_id] = cached
        else:
            missing.append(open_id)
    if not missing:
        return result

    from app.modules.hr.feishu.contact import FeishuContact
    from app.modules.hr.feishu_settings_service import (
        HrFeishuNotConfigured,
        get_hr_feishu_app_credentials,
    )

    try:
        credentials = await get_hr_feishu_app_credentials(db)
    except HrFeishuNotConfigured as exc:
        raise AppException(
            message=(
                "人事模块飞书应用未配置，无法解析所选人员的飞书身份；"
                "请先在人事管理-设置中完成飞书应用配置"
            )
        ) from exc
    contact = FeishuContact(*credentials)

    for open_id in missing:
        try:
            union_id = await contact.get_user_union_id(open_id)
        except Exception:
            logger.warning(
                "人事 open_id 换 union_id 失败: %s", open_id, exc_info=True
            )
            union_id = None
        if union_id:
            result[open_id] = union_id
            await cache_set(
                f"{_UNION_ID_CACHE_PREFIX}{open_id}",
                union_id,
                ex=_UNION_ID_CACHE_TTL,
            )
    return result
