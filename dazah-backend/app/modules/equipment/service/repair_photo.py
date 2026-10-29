"""拍照报修：图片消息 → 视觉识别设备 → 确认卡片 → 人工确认建单。

设计约束：
- 只在图片不属于巡检流程时接管（无活跃巡检会话且无执行中巡检任务），
  路由入口见 inspection_feishu.process_feishu_image 的就地转交；
- 视觉识别只做"设备身份提取"，建单必须经确认卡片人工确认，绝不自动建单；
- LLM 统一走 app.core.llm.llm_client.chat_vision_json，失败/超时/限流
  静默回落文字报修引导，链路可用性不依赖模型在线；
- 照片临时落盘 + Redis 短期登记（10 分钟），确认建单后经 upload_images
  归档为工单附件，未确认的过期作废。
"""

from __future__ import annotations

import logging
import os
import uuid
from io import BytesIO
from typing import Any

from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.llm import LLMError, llm_client
from app.modules.equipment.feishu.notification import send_user_card
from app.modules.equipment.models.workshop import EquipmentWorkshop

logger = logging.getLogger(__name__)
settings = get_settings()

_MAX_IMAGE_BYTES = 10 * 1024 * 1024
_MAX_IMAGES_PER_MINUTE = 5
_PHOTO_TTL_SECONDS = 10 * 60
_EXPECTED_KEYS = ["workshop", "equipment_name", "equipment_no", "fault"]
_MAX_CANDIDATES = 5

_UPLOAD_SUB_DIR = "repair-photo-pending"


def _pending_dir() -> str:
    upload_dir = os.path.join(settings.UPLOAD_DIR, _UPLOAD_SUB_DIR)
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


def _button(
    label: str, value: dict[str, Any], *, primary: bool = False
) -> dict[str, Any]:
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": label},
        "type": "primary" if primary else "default",
        "value": value,
    }


async def _reply(
    open_id: str,
    title: str,
    content: str,
    elements: list[dict[str, Any]] | None = None,
) -> None:
    try:
        await send_user_card(
            open_id=open_id,
            title=title,
            receive_id_type="open_id",
            content=content,
            elements=elements,
        )
    except Exception:
        logger.exception("拍照报修回复卡片失败")


async def _registered_workshops(db: AsyncSession) -> list[EquipmentWorkshop]:
    rows = (
        (
            await db.execute(
                select(EquipmentWorkshop).where(
                    EquipmentWorkshop.is_enabled == True,  # noqa: E712
                    EquipmentWorkshop.is_deleted == False,  # noqa: E712
                )
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def _vision_prompt(workshop_names: list[str]) -> str:
    joined = "、".join(workshop_names) or "（暂无注册车间）"
    return (
        "你是制药厂设备报修照片分析器。照片通常是设备铭牌、设备标签或故障现场。"
        "从照片中提取结构化字段，只输出一个 JSON 对象：\n"
        '{"workshop": "车间名，必须从注册车间清单中选择语义最匹配的一个，'
        '照片没有线索则留空",\n'
        ' "equipment_name": "设备名称，尽量还原完整名称（含序号），没有则留空",\n'
        ' "equipment_no": "设备编号（如 LB-001），没有则留空",\n'
        ' "fault": "照片可见的故障现象描述，没有则留空"}\n'
        f"注册车间清单：{joined}\n"
        "判定规则：只提取照片实际可见的信息，禁止编造；"
        "编号中的字母、数字、连字符必须原样保留。\n"
        "不要输出 JSON 以外的任何内容。"
    )


async def _vision_identify(
    image_bytes: bytes, workshop_names: list[str]
) -> dict[str, str] | None:
    """视觉识别设备身份；LLM 不可用或输出非法时返回 None（回落规则/文字）。"""
    import base64

    data_url = f"data:image/jpeg;base64,{base64.b64encode(image_bytes).decode()}"
    try:
        data: Any = await llm_client.chat_vision_json(
            text_prompt=_vision_prompt(workshop_names),
            image_urls=[data_url],
            expected_keys=_EXPECTED_KEYS,
        )
    except LLMError:
        logger.info("拍照报修视觉识别未生效（模型异常/未配置），回落文字引导")
        return None
    except Exception:
        logger.warning("拍照报修视觉识别调用失败，回落文字引导", exc_info=True)
        return None

    intent = {k: str(data.get(k, "") or "").strip() for k in _EXPECTED_KEYS}
    if not any(intent[k] for k in ("workshop", "equipment_name", "equipment_no")):
        return None
    return intent


async def _save_pending_photo(image_bytes: bytes) -> str:
    """临时落盘并登记 Redis；返回一次性 nonce。"""
    from app.core.redis import redis_client

    nonce = uuid.uuid4().hex
    file_path = os.path.join(_pending_dir(), f"{nonce}.jpg")
    with open(file_path, "wb") as f:
        f.write(image_bytes)
    await redis_client.set(
        f"repair:photo:img:{nonce}", file_path, ex=_PHOTO_TTL_SECONDS
    )
    return nonce


async def _match_equipments(
    db: AsyncSession, intent: dict[str, str], workshops: list[EquipmentWorkshop]
) -> list[tuple[Any, EquipmentWorkshop]]:
    """确定性匹配：车间精确（名称/代码）→ 设备编号精确 → 名称包含。"""
    from app.modules.equipment.models.equipment import Equipment

    ws_key = intent.get("workshop", "")
    eq_name = intent.get("equipment_name", "")
    eq_no = intent.get("equipment_no", "")

    matched_ws = [
        ws
        for ws in workshops
        if ws_key and ws_key in (ws.name, ws.code)
    ] or [
        ws
        for ws in workshops
        if ws_key and (ws_key in ws.name or ws.name in ws_key)
    ]
    if not matched_ws:
        return []

    conds = [
        Equipment.workshop_code == matched_ws[0].code,
        Equipment.is_deleted == False,  # noqa: E712
    ]
    if eq_no:
        rows = (
            (
                await db.execute(
                    select(Equipment)
                    .where(*conds, Equipment.equipment_no == eq_no)
                    .limit(_MAX_CANDIDATES + 1)
                )
            )
            .scalars()
            .all()
        )
        if rows:
            return [(row, matched_ws[0]) for row in rows]
    if eq_name:
        rows = (
            (
                await db.execute(
                    select(Equipment)
                    .where(*conds, Equipment.name.contains(eq_name))
                    .limit(_MAX_CANDIDATES + 1)
                )
            )
            .scalars()
            .all()
        )
        return [(row, matched_ws[0]) for row in rows]
    return []


async def _send_confirm_card(
    open_id: str,
    equipment: Any,
    workshop: EquipmentWorkshop,
    fault: str,
    photo_nonce: str,
) -> None:
    label = f"{equipment.name}（{equipment.equipment_no or '无编号'}）"
    value = {
        "act": "photo_repair",
        "eq": str(equipment.id),
        "ft": fault[:120],
        "ph": photo_nonce,
    }
    await _reply(
        open_id,
        "📷 拍照报修确认",
        (
            f"识别结果：**{label}**\n"
            f"所属车间：**{workshop.name}**\n"
            f"故障现象：{fault or '（照片未识别到，可在网页端补充）'}\n\n"
            "请确认是否报修："
        ),
        elements=[
            {
                "tag": "action",
                "actions": [
                    _button("✅ 确认报修", value, primary=True),
                    _button("不是这台", {"act": "photo_cancel"}),
                ],
            }
        ],
    )


async def _send_candidates_card(
    open_id: str,
    workshop: EquipmentWorkshop,
    candidates: list[Any],
    fault: str,
    photo_nonce: str,
) -> None:
    actions = [
        _button(
            f"{eq.name}（{eq.equipment_no or '无编号'}）",
            {
                "act": "photo_repair",
                "eq": str(eq.id),
                "ft": fault[:120],
                "ph": photo_nonce,
            },
        )
        for eq in candidates[:_MAX_CANDIDATES]
    ]
    await _reply(
        open_id,
        "📷 拍照报修：请选择设备",
        f"在 **{workshop.name}** 匹配到多台设备，请点击要报修的那台：",
        elements=[{"tag": "action", "actions": actions}],
    )


async def _send_fallback_card(open_id: str) -> None:
    await _reply(
        open_id,
        "📷 拍照报修未识别成功",
        (
            "没能从照片中认出设备，请改用文字报修：\n"
            "`报修 车间 设备名 故障情况`\n"
            "示例：`报修 201一车间 离心泵A 密封漏了`\n\n"
            "也可以扫描设备上张贴的报修二维码，复制内容发送即可。"
        ),
    )


async def process_repair_photo(
    *,
    user_id: str,
    open_id: str,
    message_id: str,
    image_key: str,
    chat_id: str,
    chat_type: str,
) -> None:
    """处理报修拍照（无巡检会话时由 inspection_feishu 转交）。"""
    from app.core.redis import redis_client
    from app.modules.equipment.service.inspection_feishu import _download_image

    if not open_id:
        logger.warning("报修拍照缺少 open_id，忽略")
        return

    # 每人每分钟限流，防滥用与成本失控
    rl_key = f"repair:photo:rl:{open_id}"
    count = await redis_client.incr(rl_key)
    if count == 1:
        await redis_client.expire(rl_key, 60)
    if count > _MAX_IMAGES_PER_MINUTE:
        await _reply(
            open_id, "⏳ 稍后再试", "发送太频繁了，请一分钟后再拍照报修。"
        )
        return

    image_bytes, _mime = await _download_image(message_id, image_key)
    if not image_bytes:
        await _send_fallback_card(open_id)
        return
    if len(image_bytes) > _MAX_IMAGE_BYTES:
        await _reply(open_id, "📷 图片过大", "照片超过 10MB，请重新拍摄后发送。")
        return
    try:
        Image.open(BytesIO(image_bytes)).verify()
    except Exception:
        await _reply(open_id, "📷 图片无效", "照片无法解析，请重新拍摄后发送。")
        return

    async with async_session_factory() as db:
        workshops = await _registered_workshops(db)
        intent = await _vision_identify(image_bytes, [ws.name for ws in workshops])
        if intent is None:
            await _send_fallback_card(open_id)
            return

        matched = await _match_equipments(db, intent, workshops)
        if not matched:
            await _send_fallback_card(open_id)
            return

        photo_nonce = await _save_pending_photo(image_bytes)
        fault = intent.get("fault", "")
        if len(matched) == 1:
            equipment, workshop = matched[0]
            await _send_confirm_card(open_id, equipment, workshop, fault, photo_nonce)
        else:
            await _send_candidates_card(
                open_id, matched[0][1], [eq for eq, _ in matched], fault, photo_nonce
            )
