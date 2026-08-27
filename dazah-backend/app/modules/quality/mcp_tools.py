"""Quality 模块暴露给 AI Agent 的 MCP Tools。

覆盖：偏差、CAPA、OOS/OOT、投诉、退货/召回、供应商、检验、产品质量、变更。
数据源：优先查 PostgreSQL，为空则回退飞书多维表格直读。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from app.modules.quality.models.capa import CAPA
from app.modules.quality.models.change_control import ChangeControl
from app.modules.quality.models.complaint import ComplaintRecord
from app.modules.quality.models.deviations import Deviation
from app.modules.quality.models.inspection import InspectionRecord
from app.modules.quality.models.oos_oot import OosOotRecord
from app.modules.quality.models.product_quality import ProductQualityRecord
from app.modules.quality.models.return_recall import ReturnRecallRecord
from app.modules.quality.models.supplier import Supplier
from app.platform.mcp.deps import get_db
from app.platform.mcp.server import mcp

# ── Feishu 直读 helper ────────────────────────────────────


async def _find_deviation(db: Any, deviation_code: str) -> Any:
    """按偏差编号查询本地库偏差。返回对象或 None。"""
    from sqlalchemy import select

    from app.modules.quality.models.deviations import Deviation

    stmt = select(Deviation).where(
        Deviation.deviation_code == deviation_code,
        Deviation.is_deleted == False,  # noqa: E712
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ── Tool 1: 偏差 ──────────────────────────────────────────


@mcp.tool()
async def quality_query_deviations(
    keyword: str | None = None,
    status: str | None = None,
    department: str | None = None,
    level: str | None = None,
) -> list[dict[str, Any]]:
    """
    查询偏差记录。可按关键词（编号/描述）、状态、部门、等级过滤。

    Args:
        keyword: 搜索关键词（匹配偏差编号、描述等），可选
        status: 偏差状态，可选：draft/reviewing/investigating/closed，可选
        department: 部门名称，可选
        level: 偏差等级，可选
    """
    db = get_db()
    stmt = select(Deviation).where(Deviation.is_deleted == False)  # noqa: E712

    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            (Deviation.deviation_code.ilike(pattern))
            | (Deviation.description.ilike(pattern))
            | (Deviation.title.ilike(pattern))
        )
    if status:
        stmt = stmt.where(Deviation.status == status)
    if department:
        stmt = stmt.where(Deviation.department.ilike(f"%{department}%"))
    if level:
        stmt = stmt.where(Deviation.level == level)

    stmt = stmt.order_by(Deviation.created_at.desc()).limit(30)
    result = await db.execute(stmt)
    items = result.scalars().all()

    return [
        {
            "id": str(d.id),
            "deviation_code": d.deviation_code or "",
            "title": d.title or "",
            "status": d.status or "",
            "level": d.level or "",
            "department": d.department or "",
            "discovery_date": d.discovery_date.isoformat() if d.discovery_date else "",
            "handler": d.handler or "",
            "root_cause_category": d.root_cause_category or "",
        }
        for d in items
    ]


# ── Tool 2: CAPA ──────────────────────────────────────────


@mcp.tool()
async def quality_query_capas(
    keyword: str | None = None,
    status: str | None = None,
    source: str | None = None,
    department: str | None = None,
) -> list[dict[str, Any]]:
    """
    查询 CAPA 记录。可按关键词、状态、来源、部门过滤。

    Args:
        keyword: 搜索关键词，可选
        status: CAPA 状态，可选
        source: 来源（如 deviation/audit），可选
        department: 部门，可选
    """
    db = get_db()
    stmt = select(CAPA).where(CAPA.is_deleted == False)  # noqa: E712

    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            (CAPA.capa_code.ilike(pattern))
            | (CAPA.non_conformity_description.ilike(pattern))
            | (CAPA.title.ilike(pattern))
        )
    if status:
        stmt = stmt.where(CAPA.status == status)
    if source:
        stmt = stmt.where(CAPA.source == source)
    if department:
        stmt = stmt.where(CAPA.department.ilike(f"%{department}%"))

    stmt = stmt.order_by(CAPA.created_at.desc()).limit(30)
    result = await db.execute(stmt)
    items = result.scalars().all()

    # DB 为空时回退飞书
    if not items:
        try:
            from app.modules.quality.service.quality_feishu_pages import (
                sync_capas_from_feishu,
            )

            await sync_capas_from_feishu(db)
            # sync 后重新查 DB
            result = await db.execute(stmt)
            items = result.scalars().all()
        except Exception:
            pass

    return [
        {
            "id": str(c.id),
            "capa_code": c.capa_code or "",
            "title": c.title or "",
            "status": c.status or "",
            "source": c.source or "",
            "category": c.category or "",
            "department": c.department or "",
            "expected_completion_date": c.expected_completion_date.isoformat()
            if c.expected_completion_date
            else "",
            "qa_confirmer": c.qa_confirmer or "",
        }
        for c in items
    ]


# ═══════════════════ 偏差调查工具 ═══════════════════

# 偏差管理 SOP（SMP-QA-011）调查框架
_DEVIATION_INVESTIGATION_SOP = """
## 偏差调查规范（SMP-QA-011）

### 调查原则
从人、机、料、法、环（5M1E）角度进行全面、彻底调查：
- **人**：培训情况、工作状态、操作熟练度；人为差错分为"错误"(无意)和"
违规"(故意)。培训可以通过平台人事管理查询
- **机**：设备维保/维护/校验记录，设备日志及预防维修记录
- **料**：物料质量、留样复核、供应商审计
- **法**：SOP清晰度和可执行性，文件是否有利于人员操作；质量标准、验证报告、变更控制
- **环**：环境条件、温湿度等

### 调查步骤
1. 回顾最近6个月同类偏差事件
2. 与涉及人员面谈，调查操作者对程序的知晓和熟练程度
3. 复核批记录、辅助记录、设备日志
4. 复核相关产品、物料、留样
5. 必要时访问或审计供应商
6. 调查延伸至相关联的其他批次
7. 采用头脑风暴法、原因分析法找出所有可能原因，再用排除法找到根本原因

### 根本原因判定
- 人为差错不能作为根本原因，必须进一步调查是"错误"还是"违规"
- "错误"：无意的行为或决定（纰漏/疏忽/判断失误）→ 改进设计、加强培训
- "违规"：故意偏离规则 → 了解违规原因（同事压力、不可行的规则、不完整理解）

### 调查报告模板
1. **事件描述**：时间、地点、人物、过程、违背了什么
2. **调查内容**：从人机料法环展开，提供明确证据
3. **结论**：直接原因 + 根本原因
4. **纠正及预防措施（CAPA）**：具体可行的改进方案
5. **CAPA有效性评估**：如何验证措施有效

### 偏差处理时限
一般30天内完成，最长延期不超过3个月，仅允许1次延期。

### 审核要点
对调查文件审核时检查：调查内容是否充分、逻辑是否通顺、有无错别字、是否覆盖5M1E每个维度。
"""


@mcp.tool()
async def quality_ai_investigate_deviation(
    deviation_code: str,
    operator_name: str = "AI助手",
    additional_context: str = "",
) -> dict[str, Any]:
    """
    对指定偏差执行全面的 AI 调查分析，生成符合 SMP-QA-011 规范的调查报告。
    调查从人、机、料、法、环五个维度展开，输出结构化的调查报告。

    使用场景：
    - "帮我调查一下 PC-2607002 这条偏差"
    - "对 DEV-001 做全面调查分析"
    - 用户还可提供补充信息：additional_context = "附件中提到反应釜温度计上周校准过"

    Args:
        deviation_code: 偏差编号
        operator_name: 操作人
        additional_context: 额外的调查补充信息（如附件内容、用户说明），可选
    """
    db = get_db()
    from sqlalchemy import select

    from app.core.llm import llm_client
    from app.modules.quality.models.capa import CAPA

    # 1. 查询偏差详情（DB → 飞书回退）
    deviation = await _find_deviation(db, deviation_code)
    if not deviation:
        return {"error": f"未找到偏差: {deviation_code}"}

    # 2. 查询关联的历史偏差（同类）
    related_stmt = (
        select(Deviation)
        .where(
            Deviation.is_deleted == False,  # noqa: E712
            Deviation.deviation_code != deviation_code,
            (
                Deviation.title.ilike(f"%{deviation.title or ''}%")
                | (Deviation.department.isnot(None) if deviation.department else False)
            ),
        )
        .limit(5)
    )
    related_result = await db.execute(related_stmt)
    related_deviations = related_result.scalars().all()

    # 3. 查询关联 CAPA
    capa_stmt = (
        select(CAPA)
        .where(
            CAPA.is_deleted == False,  # noqa: E712
            CAPA.source_code == deviation_code,
        )
        .limit(5)
    )
    capa_result = await db.execute(capa_stmt)
    related_capas = capa_result.scalars().all()

    # 4. 构建偏差快照
    deviation_snapshot = {
        "偏差编号": deviation.deviation_code or "",
        "标题": deviation.title or "",
        "部门": deviation.department or "",
        "等级": deviation.level or "",
        "发现日期": deviation.discovery_date.isoformat()
        if deviation.discovery_date
        else "",
        "发现地点": deviation.discovery_location or "",
        "描述": deviation.description or "",
        "应急措施": deviation.immediate_actions or "",
        "批次号": deviation.batch_number or "",
        "是否重复发生": "是" if deviation.has_occurred_before else "否/未知",
        "根因类别": deviation.root_cause_category or "",
        "纠正措施": deviation.corrective_actions or "",
        "根因分析": deviation.root_cause_analysis or "",
        "状态": deviation.status or "",
    }

    # 5. 构建消息
    user_content = f"""请对以下偏差进行符合 SMP-QA-011 规范的全面调查分析。

## 偏差信息
{json.dumps(deviation_snapshot, ensure_ascii=False, indent=2)}

## 历史相关偏差（{len(related_deviations)} 条）
{
        json.dumps(
            [
                {
                    ("编号"): d.deviation_code,
                    "标题": d.title,
                    "部门": d.department,
                    "状态": d.status,
                }
                for d in related_deviations
            ],
            ensure_ascii=False,
            indent=2,
        )
        if related_deviations
        else "无"
    }

## 关联 CAPA（{len(related_capas)} 条）
{
        json.dumps(
            [
                {("编号"): c.capa_code, "标题": c.title, "状态": c.status}
                for c in related_capas
            ],
            ensure_ascii=False,
            indent=2,
        )
        if related_capas
        else "无"
    }

## 补充信息
{additional_context or "无"}

## 要求
请严格遵循偏差调查 SOP，输出以下结构化 JSON：
{{
    "事件描述": "整合偏差信息的完整事件描述",
    "调查分析": {{
        "人": "人员方面的调查分析（培训、操作熟练度等）",
        "机": "设备方面的调查分析（维保、校验等）",
        "料": "物料方面的调查分析",
        "法": "SOP/文件方面的调查分析",
        "环": "环境方面的调查分析"
    }},
    "可能原因列表": ["可能原因1", "可能原因2"],
    "直接原因": "导致偏差的直接原因",
    "根本原因": "经排除法确定的根本原因（注意：人为差错不能作为根本原因）",
    "纠正与预防措施": ["CAPA建议1", "CAPA建议2"],
    "CAPA有效性评估": "如何验证措施有效的方案",
    "风险评估": "对产品质量的潜在影响评估",
    "建议时限": "建议的调查完成时间（一般30天内）",
    "需要进一步核实的信息": ["需要确认的事项1", "需要确认的事项2"]
}}"""

    messages = [
        {"role": "system", "content": _DEVIATION_INVESTIGATION_SOP},
        {"role": "user", "content": user_content},
    ]

    try:
        result = await llm_client.chat_json(
            messages=messages,
            expected_keys=[
                "事件描述",
                "调查分析",
                "可能原因列表",
                "直接原因",
                "根本原因",
                "纠正与预防措施",
                "CAPA有效性评估",
                "风险评估",
                "建议时限",
                "需要进一步核实的信息",
            ],
            temperature=0.3,
        )
        return {
            "deviation_code": deviation_code,
            "investigation_report": result,
            "_note": "此报告由 AI 生成，仅供参考，请 QA 审核后正式使用",
        }
    except Exception as e:
        return {"error": f"AI 调查分析失败: {e}"}


# ═══════════════════ AI 分析工具 ═══════════════════


# ── Tool 14: AI 分析偏差 ──────────────────────────────────


@mcp.tool()
async def quality_ai_analyze_deviation(
    deviation_code: str,
    operator_name: str = "AI助手",
) -> dict[str, Any]:
    """
    用 AI 自动分析一条偏差记录，生成风险等级、根因分析、CAPA 建议等。
    使用场景：提交偏差后，让 AI 帮忙做初步分析。

    Args:
        deviation_code: 偏差编号（如 DEV-2026-0001 或 PC-2607002）
        operator_name: 操作人，默认"AI助手"
    """
    db = get_db()
    from app.modules.quality.service.quality_ai import (
        analyze_deviation_async,
    )

    deviation = await _find_deviation(db, deviation_code)
    if not deviation:
        return {"error": f"未找到偏差: {deviation_code}"}

    # 异步 AI 分析（会自己开独立 session）
    log = await analyze_deviation_async(deviation.id, operator_name)
    if not log:
        return {"error": "AI 分析失败"}

    return {
        "id": str(log.id),
        "summary": log.output_payload.get("summary", "") if log.output_payload else "",
        "risk_level": log.output_payload.get("risk_level", "")
        if log.output_payload
        else "",
        "risks": log.output_payload.get("risks", []) if log.output_payload else [],
        "suggestions": log.output_payload.get("suggestions", [])
        if log.output_payload
        else [],
        "root_cause_analysis": (
            log.output_payload.get("structured_fields", {}).get(
                "preliminary_cause_analysis", ""
            )
            if log.output_payload
            else ""
        ),
        "capa_suggestions": (
            log.output_payload.get("structured_fields", {}).get("capa_suggestions", "")
            if log.output_payload
            else ""
        ),
        "model_name": log.model_name or "",
        "status": log.status or "",
    }


# ── Tool 15: AI 推荐 CAPA ──────────────────────────────────


@mcp.tool()
async def quality_ai_suggest_capa(
    deviation_code: str,
    operator_name: str = "AI助手",
) -> dict[str, Any]:
    """
    用 AI 为指定偏差生成 CAPA（纠正与预防措施）建议。
    使用场景：偏差调查完成后，让 AI 推荐针对性的 CAPA 措施。

    Args:
        deviation_code: 偏差编号
        operator_name: 操作人，默认"AI助手"
    """
    db = get_db()
    from app.modules.quality.service.quality_ai import (
        suggest_capa_for_deviation,
    )

    deviation = await _find_deviation(db, deviation_code)
    if not deviation:
        return {"error": f"未找到偏差: {deviation_code}"}

    log = await suggest_capa_for_deviation(db, deviation.id, operator_name)
    return {
        "id": str(log.id),
        "summary": log.output_payload.get("summary", "") if log.output_payload else "",
        "suggestions": log.output_payload.get("suggestions", [])
        if log.output_payload
        else [],
        "capa_suggestions": (
            log.output_payload.get("structured_fields", {}).get("capa_suggestions", "")
            if log.output_payload
            else ""
        ),
        "model_name": log.model_name or "",
        "status": log.status or "",
    }


# ── Tool 16: AI 分析 CAPA ──────────────────────────────────


@mcp.tool()
async def quality_ai_analyze_capa(
    capa_code: str,
    operator_name: str = "AI助手",
) -> dict[str, Any]:
    """
    用 AI 分析一条 CAPA 记录的有效性和执行情况。
    使用场景：CAPA 执行后，让 AI 评估措施是否有效。

    Args:
        capa_code: CAPA 编号
        operator_name: 操作人，默认"AI助手"
    """
    db = get_db()
    from sqlalchemy import select

    from app.modules.quality.models.capa import CAPA
    from app.modules.quality.service.quality_ai import (
        analyze_capa_record,
    )

    stmt = select(CAPA).where(
        CAPA.capa_code == capa_code,
        CAPA.is_deleted == False,  # noqa: E712
    )
    result = await db.execute(stmt)
    capa = result.scalar_one_or_none()
    if not capa:
        return {"error": f"未找到 CAPA: {capa_code}"}

    log = await analyze_capa_record(db, capa.id, operator_name)
    return {
        "id": str(log.id),
        "summary": log.output_payload.get("summary", "") if log.output_payload else "",
        "suggestions": log.output_payload.get("suggestions", [])
        if log.output_payload
        else [],
        "root_cause_analysis": (
            log.output_payload.get("structured_fields", {}).get(
                "root_cause_analysis", ""
            )
            if log.output_payload
            else ""
        ),
        "effectiveness_review": (
            log.output_payload.get("structured_fields", {}).get(
                "effectiveness_review", ""
            )
            if log.output_payload
            else ""
        ),
        "model_name": log.model_name or "",
        "status": log.status or "",
    }


# ═══════════════════ 写操作工具 ═══════════════════


# ── Tool 10: 上报偏差 ─────────────────────────────────────


@mcp.tool()
async def quality_create_deviation(
    title: str,
    department: str,
    description: str,
    operator_name: str,
    level: str = "次要",
    discovery_date: str = "",
    batch_number: str = "",
    immediate_actions: str = "",
) -> dict[str, str]:
    """
    上报一条新的质量偏差记录。
    使用场景：现场发现质量问题，通过飞书快速上报。

    Args:
        title: 偏差标题（简短描述，如"反应釜温度异常"）
        department: 部门名称（如"生产部"、"质量部"、"二车间"）
        description: 偏差的详细描述
        operator_name: 操作人姓名（谁上报的）
        level: 偏差等级，默认"次要"，可选"重大"、"严重"、"次要"
        discovery_date: 发现日期（YYYY-MM-DD格式），默认当天
        batch_number: 相关批号，可选
        immediate_actions: 已采取的应急措施，可选
    """
    db = get_db()
    from app.modules.quality.schemas.deviations import CreateDeviationRequest
    from app.modules.quality.service.quality_deviation import (
        create_deviation,
    )

    data = CreateDeviationRequest(
        title=title,
        department=department,
        description=description,
        level=level,
        discovery_date=discovery_date or None,
        batch_number=batch_number or None,
        immediate_actions=immediate_actions or None,
        handler=operator_name,
    )
    result = await create_deviation(db, data, operator_name)
    return result


# ── Tool 11: 创建 CAPA ────────────────────────────────────


@mcp.tool()
async def quality_create_capa(
    title: str,
    capa_content: str,
    operator_name: str,
    source: str = "",
    source_code: str = "",
    category: str = "",
    root_cause_analysis: str = "",
    expected_completion_date: str = "",
) -> dict[str, str]:
    """
    创建一条 CAPA（纠正与预防措施）记录。
    使用场景：针对偏差或审核发现的问题，制定纠正措施。

    Args:
        title: CAPA 标题
        capa_content: CAPA 措施内容
        operator_name: 操作人姓名
        source: 来源（如 deviation/audit/complaint），可选
        source_code: 来源编号（关联的偏差编号等），可选
        category: CAPA 类别，可选
        root_cause_analysis: 根本原因分析，可选
        expected_completion_date: 预计完成日期（YYYY-MM-DD），可选
    """
    db = get_db()
    from app.modules.quality.schemas.capa import CreateCapaRequest
    from app.modules.quality.service.quality_capa import create_capa

    data = CreateCapaRequest(
        title=title,
        capa_content=capa_content,
        source=source or None,
        source_code=source_code or None,
        category=category or None,
        root_cause_analysis=root_cause_analysis or None,
        expected_completion_date=expected_completion_date or None,
        reporter=operator_name,
    )
    result = await create_capa(db, data, operator_name)
    return result


# ── Tool 12: 提交投诉 ─────────────────────────────────────


@mcp.tool()
async def quality_create_complaint(
    product_name: str,
    description: str,
    customer_name: str,
    operator_name: str,
    batch_number: str = "",
    complaint_category: str = "",
) -> dict[str, str]:
    """
    提交一条客户投诉记录。
    使用场景：收到客户质量投诉，通过飞书快速登记。

    Args:
        product_name: 产品名称
        description: 投诉内容描述
        customer_name: 客户名称
        operator_name: 操作人姓名
        batch_number: 相关批号，可选
        complaint_category: 投诉类别，可选
    """
    db = get_db()
    from datetime import date

    from app.modules.quality.models.complaint import ComplaintRecord

    complaint = ComplaintRecord(
        product_name=product_name,
        description=description,
        customer_name=customer_name,
        handler=operator_name,
        batch_number=batch_number or None,
        complaint_category=complaint_category or None,
        complaint_date=date.today(),
        status="pending",
    )
    db.add(complaint)
    await db.flush()
    return {
        "id": str(complaint.id),
        "complaint_code": complaint.complaint_code or "",
        "status": complaint.status or "pending",
        "message": f"投诉已登记，编号: {complaint.complaint_code or '待生成'}",
    }


# ── Tool 13: 关闭偏差 ─────────────────────────────────────


@mcp.tool()
async def quality_close_deviation(
    deviation_id: str,
    operator_name: str,
) -> dict[str, str]:
    """
    关闭一条偏差记录（状态流转为已关闭）。
    使用场景：偏差调查完成、CAPA 执行完毕后，关闭偏差。

    Args:
        deviation_id: 偏差记录的 UUID
        operator_name: 操作人姓名
    """
    db = get_db()
    import uuid as uuid_mod

    from app.modules.quality.service.quality_deviation import (
        batch_update_status,
    )

    deviation_uuid = uuid_mod.UUID(deviation_id)
    result = await batch_update_status(db, [deviation_uuid], "closed", operator_name)
    return {"message": f"已关闭 {result.get('updated_count', 0)} 条偏差"}


# ── Tool 3: OOS/OOT ──────────────────────────────────────


@mcp.tool()
async def quality_query_oos_oot(
    keyword: str | None = None,
    record_type: str | None = None,
    status: str | None = None,
    department: str | None = None,
) -> list[dict[str, Any]]:
    """
    查询 OOS/OOT 记录。可按编号/产品/批次搜索。

    Args:
        keyword: 搜索关键词，可选
        record_type: 类型：OOS 或 OOT，可选
        status: 状态：open/investigating/closed，可选
        department: 部门，可选
    """
    db = get_db()
    stmt = select(OosOotRecord).where(OosOotRecord.is_deleted == False)  # noqa: E712

    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            (OosOotRecord.record_code.ilike(pattern))
            | (OosOotRecord.product_name.ilike(pattern))
            | (OosOotRecord.batch_number.ilike(pattern))
            | (OosOotRecord.test_item.ilike(pattern))
        )
    if record_type:
        stmt = stmt.where(OosOotRecord.record_type == record_type)
    if status:
        stmt = stmt.where(OosOotRecord.status == status)
    if department:
        stmt = stmt.where(OosOotRecord.department.ilike(f"%{department}%"))

    stmt = stmt.order_by(OosOotRecord.created_at.desc()).limit(30)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return [
        {
            "id": str(o.id),
            "record_code": o.record_code or "",
            "record_type": o.record_type or "",
            "status": o.status or "",
            "department": o.department or "",
            "product_name": o.product_name or "",
            "batch_number": o.batch_number or "",
            "test_item": o.test_item or "",
            "specification": o.specification or "",
            "test_result": o.test_result or "",
            "discovery_date": o.discovery_date.isoformat() if o.discovery_date else "",
        }
        for o in items
    ]


# ── Tool 4: 投诉 ──────────────────────────────────────────


@mcp.tool()
async def quality_query_complaints(
    keyword: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """
    查询客户投诉记录。

    Args:
        keyword: 搜索关键词（投诉编号、产品、客户名），可选
        status: 状态：pending/investigating/responded/closed，可选
    """
    db = get_db()
    stmt = select(ComplaintRecord).where(ComplaintRecord.is_deleted == False)  # noqa: E712

    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            (ComplaintRecord.complaint_code.ilike(pattern))
            | (ComplaintRecord.product_name.ilike(pattern))
            | (ComplaintRecord.customer_name.ilike(pattern))
            | (ComplaintRecord.description.ilike(pattern))
        )
    if status:
        stmt = stmt.where(ComplaintRecord.status == status)

    stmt = stmt.order_by(ComplaintRecord.created_at.desc()).limit(30)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "complaint_code": c.complaint_code or "",
            "status": c.status or "",
            "customer_name": c.customer_name or "",
            "product_name": c.product_name or "",
            "batch_number": c.batch_number or "",
            "complaint_date": c.complaint_date.isoformat() if c.complaint_date else "",
            "complaint_category": c.complaint_category or "",
            "handler": c.handler or "",
            "response_date": c.response_date.isoformat() if c.response_date else "",
        }
        for c in items
    ]


# ── Tool 5: 退货/召回 ─────────────────────────────────────


@mcp.tool()
async def quality_query_return_recalls(
    keyword: str | None = None,
    record_type: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """
    查询退货/召回记录。

    Args:
        keyword: 搜索关键词，可选
        record_type: 类型：return/recall，可选
        status: 状态，可选
    """
    db = get_db()
    stmt = select(ReturnRecallRecord).where(ReturnRecallRecord.is_deleted == False)  # noqa: E712

    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            (ReturnRecallRecord.record_code.ilike(pattern))
            | (ReturnRecallRecord.product_name.ilike(pattern))
            | (ReturnRecallRecord.customer_name.ilike(pattern))
        )
    if record_type:
        stmt = stmt.where(ReturnRecallRecord.record_type == record_type)
    if status:
        stmt = stmt.where(ReturnRecallRecord.status == status)

    stmt = stmt.order_by(ReturnRecallRecord.created_at.desc()).limit(30)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "record_code": r.record_code or "",
            "record_type": r.record_type or "",
            "status": r.status or "",
            "product_name": r.product_name or "",
            "batch_number": r.batch_number or "",
            "quantity": float(r.quantity) if r.quantity else 0,
            "unit": r.unit or "",
            "customer_name": r.customer_name or "",
            "occurrence_date": r.occurrence_date.isoformat()
            if r.occurrence_date
            else "",
            "handler": r.handler or "",
        }
        for r in items
    ]


# ── Tool 6: 供应商 ────────────────────────────────────────


@mcp.tool()
async def quality_query_suppliers(
    keyword: str | None = None,
    status: str | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """
    查询供应商信息。

    Args:
        keyword: 搜索关键词（供应商名称、编号），可选
        status: 状态：active/suspended/blacklisted，可选
        category: 类别：原料/辅料/包材/设备/服务，可选
    """
    db = get_db()
    stmt = select(Supplier).where(Supplier.is_deleted == False)  # noqa: E712

    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            (Supplier.name.ilike(pattern))
            | (Supplier.supplier_code.ilike(pattern))
            | (Supplier.contact_person.ilike(pattern))
        )
    if status:
        stmt = stmt.where(Supplier.status == status)
    if category:
        stmt = stmt.where(Supplier.category == category)

    stmt = stmt.limit(30)
    result = await db.execute(stmt)
    items = result.scalars().all()

    # DB 为空时回退飞书
    if not items:
        try:
            from app.modules.quality.service.quality_feishu_pages_supplier import (
                list_supplier_qualification_records,
            )

            feishu_result = await list_supplier_qualification_records(
                db, keyword=keyword, page=1, page_size=30
            )
            feishu_items = feishu_result.get("items", [])
            items = [
                type(
                    "SupplierStub",
                    (),
                    {  # noqa: SIM115
                        "id": item.get("record_id", ""),
                        "supplier_code": item.get("supplier_code", ""),
                        "name": item.get("name", ""),
                        "status": item.get("status", ""),
                        "category": item.get("category", ""),
                        "qualification_status": item.get("qualification_status", ""),
                        "contact_person": item.get("contact_person", ""),
                        "contact_phone": item.get("contact_phone", ""),
                        "scope_of_supply": item.get("scope_of_supply", ""),
                        "next_audit_date": None,
                    },
                )()
                for item in feishu_items
            ]
        except Exception:
            pass

    return [
        {
            "id": str(s.id),
            "supplier_code": s.supplier_code or "",
            "name": s.name or "",
            "status": s.status or "",
            "category": s.category or "",
            "qualification_status": s.qualification_status or "",
            "contact_person": s.contact_person or "",
            "contact_phone": s.contact_phone or "",
            "scope_of_supply": s.scope_of_supply or "",
            "next_audit_date": s.next_audit_date.isoformat()
            if s.next_audit_date
            else "",
        }
        for s in items
    ]


# ── Tool 7: 检验 ──────────────────────────────────────────


@mcp.tool()
async def quality_query_inspections(
    keyword: str | None = None,
    conclusion: str | None = None,
    inspection_type: str | None = None,
    department: str | None = None,
) -> list[dict[str, Any]]:
    """
    查询检验记录。

    Args:
        keyword: 搜索关键词（检验编号、产品名、批号），可选
        conclusion: 结论：合格/不合格，可选
        inspection_type: 类型：来料/中间体/成品/留样，可选
        department: 部门，可选
    """
    db = get_db()
    stmt = select(InspectionRecord).where(InspectionRecord.is_deleted == False)  # noqa: E712

    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            (InspectionRecord.inspection_no.ilike(pattern))
            | (InspectionRecord.product_name.ilike(pattern))
            | (InspectionRecord.batch_no.ilike(pattern))
            | (InspectionRecord.inspection_item.ilike(pattern))
        )
    if conclusion:
        stmt = stmt.where(InspectionRecord.conclusion == conclusion)
    if inspection_type:
        stmt = stmt.where(InspectionRecord.inspection_type == inspection_type)
    if department:
        stmt = stmt.where(InspectionRecord.department.ilike(f"%{department}%"))

    stmt = stmt.order_by(InspectionRecord.inspection_date.desc()).limit(30)
    result = await db.execute(stmt)
    items = result.scalars().all()

    # DB 为空时从飞书搜索检验记录
    if not items:
        try:
            from app.modules.quality.service.quality_feishu_sync import (
                QualityFeishuSync,
            )

            sync = QualityFeishuSync()
            # 尝试搜索固体/液体物料检验 entity
            for ec in ("solid_inspection", "liquid_inspection"):
                try:
                    records = await sync.search_records(db, ec, field_names=None)
                    if records:
                        items = [
                            type(
                                "InspStub",
                                (),
                                {
                                    "id": r.get("record_id", ""),
                                    "inspection_no": r.get("inspection_no", ""),
                                    "product_name": r.get("product_name", ""),
                                    "batch_no": r.get("batch_no", ""),
                                    "inspection_type": r.get("inspection_type", ""),
                                    "inspection_item": r.get("inspection_item", ""),
                                    "conclusion": r.get("conclusion", ""),
                                    "inspector": r.get("inspector", ""),
                                    "department": r.get("department", ""),
                                    "inspection_date": None,
                                },
                            )()
                            for r in records[:30]
                        ]
                        break
                except Exception:
                    continue
        except Exception:
            pass

    return [
        {
            "id": str(i.id),
            "inspection_no": i.inspection_no or "",
            "product_name": i.product_name or "",
            "batch_no": i.batch_no or "",
            "inspection_type": i.inspection_type or "",
            "inspection_item": i.inspection_item or "",
            "conclusion": i.conclusion or "",
            "inspector": i.inspector or "",
            "department": i.department or "",
            "inspection_date": i.inspection_date.isoformat()
            if i.inspection_date
            else "",
        }
        for i in items
    ]


# ── Tool 8: 产品质量回顾 ──────────────────────────────────


@mcp.tool()
async def quality_query_product_quality(
    keyword: str | None = None,
    review_type: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """
    查询产品质量回顾记录。

    Args:
        keyword: 搜索关键词（编号、产品名），可选
        review_type: 回顾类型：年度回顾/批释放/稳定性考察/留样观察，可选
        status: 状态：draft/completed/approved，可选
    """
    db = get_db()
    stmt = select(ProductQualityRecord).where(
        ProductQualityRecord.is_deleted == False  # noqa: E712
    )

    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            (ProductQualityRecord.record_code.ilike(pattern))
            | (ProductQualityRecord.product_name.ilike(pattern))
            | (ProductQualityRecord.title.ilike(pattern))
        )
    if review_type:
        stmt = stmt.where(ProductQualityRecord.review_type == review_type)
    if status:
        stmt = stmt.where(ProductQualityRecord.status == status)

    stmt = stmt.order_by(ProductQualityRecord.created_at.desc()).limit(30)
    result = await db.execute(stmt)
    items = result.scalars().all()

    # DB 为空时从飞书搜产品质量记录（多产品分表，逐个尝试）
    if not items:
        try:
            from app.modules.quality.service.quality_feishu_sync import (
                QualityFeishuSync,
            )

            sync = QualityFeishuSync()
            # 常见产品 entity codes
            for ec in (
                "mfn_product_quality",
                "dljs_product_quality",
                "lft_product_quality",
                "zla_product_quality",
            ):
                try:
                    records = await sync.search_records(db, ec, field_names=None)
                    if records:
                        items = [
                            type(
                                "PQStub",
                                (),
                                {
                                    "id": r.get("record_id", ""),
                                    "record_code": r.get("record_code", ""),
                                    "title": r.get("title", ""),
                                    "product_name": r.get("product_name", ""),
                                    "batch_number": r.get("batch_number", ""),
                                    "review_type": r.get("review_type", ""),
                                    "status": r.get("status", ""),
                                    "quality_trend": r.get("quality_trend", ""),
                                    "conclusion": r.get("conclusion", ""),
                                    "reviewer": r.get("reviewer", ""),
                                    "review_date": None,
                                },
                            )()
                            for r in records[:30]
                        ]
                        break
                except Exception:
                    continue
        except Exception:
            pass

    return [
        {
            "id": str(p.id),
            "record_code": p.record_code or "",
            "title": p.title or "",
            "product_name": p.product_name or "",
            "batch_number": p.batch_number or "",
            "review_type": p.review_type or "",
            "status": p.status or "",
            "quality_trend": p.quality_trend or "",
            "conclusion": p.conclusion or "",
            "reviewer": p.reviewer or "",
            "review_date": p.review_date.isoformat() if p.review_date else "",
        }
        for p in items
    ]


# ── Tool 9: 变更 ──────────────────────────────────────────


@mcp.tool()
async def quality_query_changes(
    keyword: str | None = None,
    change_level: str | None = None,
    applicant_department: str | None = None,
) -> list[dict[str, Any]]:
    """
    查询变更控制记录。

    Args:
        keyword: 搜索关键词（变更编号、对象、内容），可选
        change_level: 变更等级，可选
        applicant_department: 申请部门，可选
    """
    db = get_db()
    stmt = select(ChangeControl).where(ChangeControl.is_deleted == False)  # noqa: E712

    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            (ChangeControl.change_code.ilike(pattern))
            | (ChangeControl.change_object.ilike(pattern))
            | (ChangeControl.change_content.ilike(pattern))
        )
    if change_level:
        stmt = stmt.where(ChangeControl.change_level == change_level)
    if applicant_department:
        stmt = stmt.where(
            ChangeControl.applicant_department.ilike(f"%{applicant_department}%")
        )

    stmt = stmt.order_by(ChangeControl.created_at.desc()).limit(30)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "change_code": c.change_code or "",
            "change_object": c.change_object or "",
            "change_level": c.change_level or "",
            "applicant_department": c.applicant_department or "",
            "application_date": c.application_date.isoformat()
            if c.application_date
            else "",
            "execution_date": c.execution_date.isoformat() if c.execution_date else "",
            "closure_date": c.closure_date.isoformat() if c.closure_date else "",
            "impact_assessment": c.impact_assessment or "",
        }
        for c in items
    ]
