"""维修知识案例：草稿生成、确认入库与三层相似检索。

设计约束：
- 案例由维修人人工确认入库（飞书卡片或网页），LLM 只做关键步骤
  抽取建议且失败不影响草稿建立；
- 检索为确定性规则（设备层 → 同分类层 → 全局 + 字符二元组重合度），
  不依赖向量库与 LLM 在线。
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException
from app.modules.equipment.models.equipment import Equipment, EquipmentCategoryLink
from app.modules.equipment.models.failure_code import (
    FailureAction,
    FailureCause,
    FailureSymptom,
)
from app.modules.equipment.models.knowledge import RepairKnowledgeCase
from app.modules.equipment.models.work_order import WorkOrder

logger = logging.getLogger(__name__)

# 检索层级加成（同分时本设备优先，其次同分类）
_LAYER_BONUS_EQUIPMENT = 100.0
_LAYER_BONUS_CATEGORY = 50.0


def _char_bigrams(text: str) -> set[str]:
    """中英文通用的字符二元组集合（无分词依赖的相似度基础）。"""
    cleaned = "".join(text.split())
    if len(cleaned) <= 1:
        return {cleaned} if cleaned else set()
    return {cleaned[i : i + 2] for i in range(len(cleaned) - 1)}


def similarity_score(query: str, target: str) -> float:
    """字符二元组 Jaccard 相似度（0-1）。"""
    q = _char_bigrams(query or "")
    t = _char_bigrams(target or "")
    if not q or not t:
        return 0.0
    return len(q & t) / len(q | t)


# ── 草稿生成 ────────────────────────────────────────────────────────


async def create_case_draft(
    db: AsyncSession, wo: WorkOrder
) -> RepairKnowledgeCase | None:
    """故障维修工单验收合格后生成案例草稿。

    去重：同设备 + 同现象 + 同原因的 verified 案例已存在时不再生成；
    同一工单已有草稿时跳过（幂等）。
    """
    if wo.order_type != "故障维修":
        return None

    existing_for_wo = (
        await db.execute(
            select(RepairKnowledgeCase).where(
                RepairKnowledgeCase.source_work_order_id == wo.id,
                RepairKnowledgeCase.is_deleted == False,  # noqa: E712
            )
        )
    ).scalars().first()
    if existing_for_wo is not None:
        return None

    # 工单关系对象可能未加载（异步会话禁懒加载），按 ID 显式取
    symptom = (
        await db.get(FailureSymptom, wo.fault_symptom_id)
        if wo.fault_symptom_id
        else None
    )
    cause = (
        await db.get(FailureCause, wo.fault_cause_id)
        if wo.fault_cause_id
        else None
    )
    action = (
        await db.get(FailureAction, wo.fault_action_id)
        if wo.fault_action_id
        else None
    )
    equipment = (
        wo.equipment
        if "equipment" in wo.__dict__
        else (
            await db.get(Equipment, wo.equipment_id)
            if wo.equipment_id
            else None
        )
    )

    duplicate = (
        await db.execute(
            select(RepairKnowledgeCase).where(
                RepairKnowledgeCase.equipment_id == wo.equipment_id,
                RepairKnowledgeCase.status == "verified",
                RepairKnowledgeCase.is_deleted == False,  # noqa: E712
                (
                    RepairKnowledgeCase.symptom_code
                    == (symptom.code if symptom else None)
                ),
                (
                    RepairKnowledgeCase.cause_code
                    == (cause.code if cause else None)
                ),
            )
        )
    ).scalars().first()
    if duplicate is not None:
        logger.info(
            "案例草稿跳过（同设备同现象同原因已入库）: %s", wo.work_order_no
        )
        return None

    category_id = (
        (
            await db.execute(
                select(EquipmentCategoryLink.category_id)
                .where(EquipmentCategoryLink.equipment_id == wo.equipment_id)
                .limit(1)
            )
        )
        .scalars()
        .first()
    )

    case = RepairKnowledgeCase(
        source_work_order_id=wo.id,
        equipment_id=wo.equipment_id,
        equipment_category_id=category_id,
        workshop_code=equipment.workshop_code if equipment else None,
        symptom_code=symptom.code if symptom else None,
        symptom_name=symptom.name if symptom else None,
        cause_code=cause.code if cause else None,
        cause_name=cause.name if cause else None,
        action_code=action.code if action else None,
        action_name=action.name if action else None,
        fault_description=wo.fault_description,
        repair_summary=wo.repair_detail,
        status="draft",
        equipment_name=equipment.name if equipment else None,
        equipment_no=equipment.equipment_no if equipment else None,
    )
    db.add(case)
    await db.flush()
    return case


async def extract_key_steps(case_id: uuid.UUID) -> None:
    """后台任务：LLM 抽取关键维修步骤（失败留空，不阻塞草稿）。"""
    from app.core.database import async_session_factory
    from app.core.llm import LLMError, llm_client

    try:
        async with async_session_factory() as db:
            case = (
                await db.execute(
                    select(RepairKnowledgeCase).where(
                        RepairKnowledgeCase.id == case_id
                    )
                )
            ).scalars().first()
            if case is None or case.status != "draft":
                return
            source = case.repair_summary or case.fault_description or ""
            if not source.strip():
                return
            data = await llm_client.chat_json(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是制药设备维修经验整理器。从维修记录中提取"
                            "关键维修步骤（3-6 条，每条不超过 30 字），"
                            '只输出 JSON：{"steps": ["...", "..."]}。'
                            "记录中没有明确步骤时输出空数组，禁止编造。"
                        ),
                    },
                    {"role": "user", "content": source[:600]},
                ],
                expected_keys=["steps"],
                temperature=0.0,
                timeout=15,
            )
            steps = data.get("steps")
            if isinstance(steps, list):
                cleaned = [
                    str(s).strip()[:60] for s in steps if str(s).strip()
                ]
                case.key_steps = cleaned[:6]
                await db.commit()
    except LLMError:
        logger.info("案例关键步骤 LLM 抽取未生效（模型输出异常）: %s", case_id)
    except Exception:
        logger.warning("案例关键步骤抽取失败: %s", case_id, exc_info=True)


def schedule_draft_processing(case_id: uuid.UUID) -> None:
    """草稿后处理：LLM 抽取步骤 + 飞书确认卡片（均为非关键路径）。

    只传 ID，后台任务内重新加载，避免 ORM 对象逃逸请求会话。
    """
    import asyncio

    asyncio.ensure_future(extract_key_steps(case_id))
    asyncio.ensure_future(_send_case_confirm_card(case_id))


async def _send_case_confirm_card(case_id: uuid.UUID) -> None:
    """向来源工单维修人发送「维修经验入库确认」卡片。"""
    try:
        from app.core.database import async_session_factory
        from app.modules.equipment.feishu.notification import send_user_card

        async with async_session_factory() as db:
            case = (
                await db.execute(
                    select(RepairKnowledgeCase).where(
                        RepairKnowledgeCase.id == case_id
                    )
                )
            ).scalars().first()
            if case is None or case.status != "draft":
                return
            wo_no = ""
            feishu_uid = None
            if case.source_work_order_id is not None:
                wo = (
                    await db.execute(
                        select(WorkOrder)
                        .where(WorkOrder.id == case.source_work_order_id)
                        .options(selectinload(WorkOrder.assignee))
                    )
                ).scalars().first()
                if wo is not None:
                    wo_no = wo.work_order_no
                    assignee = wo.assignee
                    feishu_uid = (
                        getattr(assignee, "feishu_union_id", None)
                        if assignee is not None
                        else None
                    )

        if not feishu_uid:
            logger.info("案例确认卡片跳过（维修人未绑定飞书）: %s", wo_no)
            return

        lines = [
            f"**工单编号：**{wo_no or '-'}",
            f"**设备：**{case.equipment_name or '-'}（{case.equipment_no or '-'}）",
            f"**故障现象：**{case.symptom_name or '-'}",
            f"**故障原因：**{case.cause_name or '-'}",
            f"**维修措施：**{case.action_name or '-'}",
            "",
            "把这单的维修经验沉淀进知识库，供后续报修推荐参考？",
        ]
        elements = [
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "📚 入库"},
                        "type": "primary",
                        "value": {"act": "case_verify", "cid": str(case.id)},
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "忽略"},
                        "value": {"act": "case_dismiss", "cid": str(case.id)},
                    },
                ],
            }
        ]
        ok = await send_user_card(
            open_id=feishu_uid,
            title=f"📖 维修经验入库确认 - {wo_no or case.equipment_no or ''}",
            content="\n".join(lines),
            elements=elements,
            receive_id_type="union_id",
        )
        if not ok:
            logger.warning("案例确认卡片发送失败: %s", wo_no)
    except Exception:
        logger.exception("案例确认卡片发送异常: %s", case_id)


# ── 确认 / 忽略 ─────────────────────────────────────────────────────


async def verify_case(
    db: AsyncSession, case_id: uuid.UUID, user_id: uuid.UUID
) -> RepairKnowledgeCase:
    case = await _get_case(db, case_id)
    if case.status != "draft":
        raise AppException(
            message=(
                f"案例当前状态为「{case.status}」，只有草稿可确认入库"
            )
        )
    case.status = "verified"
    case.verified_by = user_id
    case.verified_at = datetime.now(UTC)
    await db.flush()
    return case


async def dismiss_case(
    db: AsyncSession, case_id: uuid.UUID, user_id: uuid.UUID
) -> RepairKnowledgeCase:
    case = await _get_case(db, case_id)
    if case.status != "draft":
        raise AppException(message=f"案例当前状态为「{case.status}」，只有草稿可忽略")
    case.status = "dismissed"
    case.updated_by = user_id
    await db.flush()
    return case


async def _get_case(db: AsyncSession, case_id: uuid.UUID) -> RepairKnowledgeCase:
    case = (
        (
            await db.execute(
                select(RepairKnowledgeCase).where(
                    RepairKnowledgeCase.id == case_id,
                    RepairKnowledgeCase.is_deleted == False,  # noqa: E712
                )
            )
        )
        .scalars()
        .first()
    )
    if case is None:
        raise AppException(message="案例不存在")
    return case


async def list_cases(
    db: AsyncSession,
    status: str | None = None,
    equipment_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[RepairKnowledgeCase], int]:
    conditions = [RepairKnowledgeCase.is_deleted == False]  # noqa: E712
    if status:
        conditions.append(RepairKnowledgeCase.status == status)
    if equipment_id:
        conditions.append(RepairKnowledgeCase.equipment_id == equipment_id)

    total = (
        await db.execute(
            select(func.count())
            .select_from(RepairKnowledgeCase)
            .where(*conditions)
        )
    ).scalar_one()
    rows = (
        (
            await db.execute(
                select(RepairKnowledgeCase)
                .where(*conditions)
                .order_by(RepairKnowledgeCase.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), int(total)


# ── 相似案例检索 ────────────────────────────────────────────────────


async def search_similar_cases(
    db: AsyncSession,
    query: str,
    equipment_id: uuid.UUID | None = None,
    symptom_code: str | None = None,
    top: int = 3,
) -> list[dict[str, Any]]:
    """三层检索相似案例：本设备 → 同分类 → 全局。

    评分 = 层级加成 + 文本相似度 + 现象代码命中加成。
    """
    top = max(1, min(10, top))

    equipment_category_id: uuid.UUID | None = None
    if equipment_id is not None:
        equipment_category_id = (
            (
                await db.execute(
                    select(EquipmentCategoryLink.category_id)
                    .where(EquipmentCategoryLink.equipment_id == equipment_id)
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )

    cases = (
        (
            await db.execute(
                select(RepairKnowledgeCase).where(
                    RepairKnowledgeCase.status == "verified",
                    RepairKnowledgeCase.is_deleted == False,  # noqa: E712
                )
                .order_by(RepairKnowledgeCase.use_count.desc())
                .limit(200)
            )
        )
        .scalars()
        .all()
    )

    scored: list[tuple[float, int, RepairKnowledgeCase]] = []
    for idx, case in enumerate(cases):
        layer_bonus = 0.0
        if equipment_id is not None and case.equipment_id == equipment_id:
            layer_bonus = _LAYER_BONUS_EQUIPMENT
        elif (
            equipment_category_id is not None
            and case.equipment_category_id == equipment_category_id
        ):
            layer_bonus = _LAYER_BONUS_CATEGORY

        text_score = max(
            similarity_score(query, case.fault_description or ""),
            similarity_score(query, case.symptom_name or ""),
        )
        symptom_bonus = 20.0 if (
            symptom_code and case.symptom_code == symptom_code
        ) else 0.0
        score = layer_bonus + text_score * 30.0 + symptom_bonus
        if score <= 0.0:
            continue
        scored.append((score, -case.use_count, case))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    results: list[dict[str, Any]] = []
    for score, _, case in scored[:top]:
        results.append(
            {
                "id": case.id,
                "equipment_name": case.equipment_name,
                "equipment_no": case.equipment_no,
                "symptom_name": case.symptom_name,
                "cause_name": case.cause_name,
                "action_name": case.action_name,
                "fault_description": case.fault_description,
                "repair_summary": case.repair_summary,
                "key_steps": case.key_steps or [],
                "use_count": case.use_count,
                "score": round(score, 2),
            }
        )
    return results


async def mark_case_used(db: AsyncSession, case_id: uuid.UUID) -> None:
    """案例被采纳（用户点击/展开使用）时计数。"""
    case = await _get_case(db, case_id)
    case.use_count = (case.use_count or 0) + 1
    await db.flush()
