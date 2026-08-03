import asyncio
import base64
import binascii
import json
import logging
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import httpx
from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.procurement.contract_generator import (
    TEMPLATE_DIR,
    TEMPLATE_FILES,
    get_contract_template_metadata,
)
from app.modules.procurement.schemas import ContractCategory
from app.platform.identity.models import User

from .models import (
    AgentConfirmation,
    AgentSession,
    AgentSkill,
    AgentWorkflow,
    AgentWorkflowRun,
)
from .repository import AgentRepository
from .schemas import (
    AgentBackendSource,
    AgentBackendV2Event,
    AgentBackendV2Request,
    AgentChatRequest,
    AgentChatResponse,
    AgentConfirmationOut,
    AgentMessageOut,
    AgentSessionDetail,
    AgentSessionItem,
    AgentSessionPage,
    AgentSkillCreate,
    AgentSkillOut,
    AgentSkillResolvedOut,
    AgentSkillResolveRequest,
    AgentSkillResolveResponse,
    AgentSkillUpdate,
    AgentToolExecuteRequest,
    AgentToolExecuteResponse,
    AgentTrustedSubject,
    AgentWorkflowCreate,
    AgentWorkflowOut,
    AgentWorkflowRunOut,
    AgentWorkflowUpdate,
)
from .tool_registration import ensure_agent_tools_registered
from .tools import ToolExecutor, tool_registry

logger = logging.getLogger(__name__)

AGENT_ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024
AGENT_ATTACHMENT_TOTAL_MAX_BYTES = 20 * 1024 * 1024
AGENT_ATTACHMENT_TEXT_MAX_CHARS = 50_000
AGENT_ATTACHMENT_TOTAL_TEXT_MAX_CHARS = 100_000
AGENT_ATTACHMENT_CONTENT_TYPES: dict[str, set[str]] = {
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".webp": {"image/webp"},
    ".gif": {"image/gif"},
    ".pdf": {"application/pdf"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    },
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".txt": {"text/plain"},
    ".md": {"text/markdown", "text/plain"},
    ".csv": {"text/csv", "application/vnd.ms-excel", "text/plain"},
}
AGENT_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _decode_text_attachment(data: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("文本文档编码不受支持，请使用 UTF-8 或 GB18030")


def _extract_attachment_text(extension: str, data: bytes) -> str:
    if extension in {".txt", ".md", ".csv"}:
        return _decode_text_attachment(data)
    if extension == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    if extension == ".docx":
        from docx import Document

        document = Document(BytesIO(data))
        paragraphs = [paragraph.text for paragraph in document.paragraphs]
        table_rows = [
            "\t".join(cell.text for cell in row.cells)
            for table in document.tables
            for row in table.rows
        ]
        return "\n".join([*paragraphs, *table_rows])
    if extension == ".xlsx":
        from openpyxl import load_workbook  # type: ignore[import-untyped]

        workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
        rows: list[str] = []
        try:
            for worksheet in workbook.worksheets:
                rows.append(f"工作表：{worksheet.title}")
                for row in worksheet.iter_rows(values_only=True):
                    rows.append(
                        "\t".join("" if value is None else str(value) for value in row)
                    )
        finally:
            workbook.close()
        return "\n".join(rows)
    raise ValueError("不支持的文档类型")


def _has_valid_image_signature(extension: str, data: bytes) -> bool:
    if extension == ".png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if extension in {".jpg", ".jpeg"}:
        return data.startswith(b"\xff\xd8\xff")
    if extension == ".webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if extension == ".gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    return False


@dataclass(frozen=True)
class OperationSpec:
    method: str
    path: str
    write: bool = False
    risk_level: str = "medium"
    summary: str = ""
    input_schema: dict[str, Any] | None = None
    output_hint: str = ""


OPERATION_WHITELIST: dict[str, OperationSpec] = {
    "analytics.aggregate": OperationSpec(
        "TOOL",
        "/agent/analytics/aggregate",
        summary="通用业务数据聚合统计",
        input_schema={
            "body": {
                "dataset": "数据集名称，例如 procurement.suppliers",
                "metrics": "聚合指标列表，支持 count/count_distinct/sum/avg/min/max",
                "group_by": "分组字段列表，例如 manufacturer_name",
                "filters": (
                    "过滤条件列表，支持 eq/ne/contains/not_empty/is_empty/gte/lte"
                ),
                "order_by": "按 metric 或 group_by 字段排序",
                "limit": "返回分组数量，默认 20，最大 200",
            }
        },
        output_hint="用于全量计数、去重计数、TopN、分布统计等场景，避免逐页读取全量明细。",
    ),
    "warehouse.list_raw_materials": OperationSpec(
        "GET", "/warehouse/raw-materials", summary="查询原辅料库存"
    ),
    "warehouse.list_packaging_materials": OperationSpec(
        "GET", "/warehouse/packaging-materials", summary="查询包材库存"
    ),
    "warehouse.list_products": OperationSpec(
        "GET", "/warehouse/products", summary="查询产品库存"
    ),
    "warehouse.list_feishu_tables": OperationSpec(
        "GET", "/warehouse/feishu/tables", summary="查询仓储飞书表目录"
    ),
    "warehouse.get_feishu_table_records": OperationSpec(
        "GET",
        "/warehouse/feishu/tables/{table_id}/records",
        summary="查询飞书表本地记录",
    ),
    "warehouse.get_feishu_ws_status": OperationSpec(
        "GET", "/warehouse/feishu/ws/status", summary="查询仓储飞书 WebSocket 状态"
    ),
    "warehouse.sync_feishu_table": OperationSpec(
        "POST",
        "/warehouse/feishu/tables/{table_id}/sync",
        True,
        "medium",
        "同步仓储飞书表",
    ),
    "warehouse.restart_feishu_ws": OperationSpec(
        "POST", "/warehouse/feishu/ws/restart", True, "high", "重启仓储飞书 WebSocket"
    ),
    "procurement.list_invoice_records": OperationSpec(
        "GET", "/procurement/invoices/recognition-records", summary="查询发票识别记录"
    ),
    "procurement.list_suppliers": OperationSpec(
        "GET",
        "/procurement/suppliers",
        summary="查询供应商清单",
        input_schema={
            "params": {
                "keyword": "跨供应商、物料、厂家、品类和原始字段关键词",
                "supplier_name": "供应商名称模糊查询",
                "material_name": "物料名称模糊查询",
                "purchase_category": "采购品类名称精确查询",
                "page": "页码，默认 1",
                "page_size": "每页条数，默认 20，最大 100",
            }
        },
        output_hint="返回供应商代码、供应商名称、物料、厂家、品类和导入原始字段。",
    ),
    "procurement.list_purchase_requests": OperationSpec(
        "GET", "/procurement/purchase-requests", summary="查询采购申请"
    ),
    "procurement.get_purchase_request": OperationSpec(
        "GET", "/procurement/purchase-requests/{request_id}", summary="查看采购申请详情"
    ),
    "procurement.create_purchase_request": OperationSpec(
        "POST", "/procurement/purchase-requests", True, "medium", "创建采购申请"
    ),
    "procurement.update_purchase_request": OperationSpec(
        "PUT",
        "/procurement/purchase-requests/{request_id}",
        True,
        "medium",
        "更新采购申请",
    ),
    "procurement.submit_purchase_request": OperationSpec(
        "POST",
        "/procurement/purchase-requests/{request_id}/submit",
        True,
        "medium",
        "提交采购申请",
    ),
    "procurement.approve_purchase_request": OperationSpec(
        "POST",
        "/procurement/purchase-requests/{request_id}/approve",
        True,
        "high",
        "审批通过采购申请",
    ),
    "procurement.reject_purchase_request": OperationSpec(
        "POST",
        "/procurement/purchase-requests/{request_id}/reject",
        True,
        "high",
        "驳回采购申请",
    ),
    "procurement.list_purchase_orders": OperationSpec(
        "GET", "/procurement/purchase-orders", summary="查询采购订单"
    ),
    "procurement.export_purchase_orders": OperationSpec(
        "GET", "/procurement/purchase-orders/export", summary="导出采购订单"
    ),
    "procurement.list_contract_templates": OperationSpec(
        "GET", "/procurement/contracts/templates", summary="查询四类合同模板字段"
    ),
    "procurement.get_contract_template": OperationSpec(
        "GET", "/procurement/contracts/templates/{category}", summary="查询合同模板"
    ),
    "procurement.generate_contract": OperationSpec(
        "POST", "/procurement/contracts/generate", True, "medium", "生成采购合同"
    ),
    "agent.list_workflow_capabilities": OperationSpec(
        "GET", "/agent/workflow-capabilities", summary="查询可编排业务能力"
    ),
    "agent.create_workflow": OperationSpec(
        "POST", "/agent/workflows", True, "medium", "创建助手工作流"
    ),
    "agent.list_workflows": OperationSpec(
        "GET", "/agent/workflows", summary="查询我的助手工作流"
    ),
    "agent.get_workflow": OperationSpec(
        "GET", "/agent/workflows/{workflow_id}", summary="查看助手工作流详情"
    ),
    "agent.update_workflow": OperationSpec(
        "PUT", "/agent/workflows/{workflow_id}", True, "medium", "修改助手工作流"
    ),
    "agent.set_workflow_enabled": OperationSpec(
        "POST",
        "/agent/workflows/{workflow_id}/enabled",
        True,
        "medium",
        "启停助手工作流",
    ),
    "agent.run_workflow": OperationSpec(
        "POST", "/agent/workflows/{workflow_id}/run", True, "medium", "运行助手工作流"
    ),
    "agent.cancel_workflow_run": OperationSpec(
        "POST",
        "/agent/workflow-runs/{run_id}/cancel",
        True,
        "medium",
        "取消助手工作流运行",
    ),
    "agent.get_workflow_run": OperationSpec(
        "GET", "/agent/workflow-runs/{run_id}", summary="查看助手工作流运行状态"
    ),
}

HUMAN_DECISION_REQUIRED_MESSAGE = (
    "抱歉，我不能代你完成审批决定、批准、驳回、拒绝或关键连接重启等"
    "需要最终责任判断的高风险操作。"
    "请你在对应业务页面自行查看资料、评估风险并手动操作；我可以帮助你查询待处理事项、"
    "整理背景信息或生成意见草稿供你参考。普通消息发送和其他可确认写操作不会被此策略拦截，"
    "系统会生成待确认项供你核对后执行。"
)

HUMAN_DECISION_ACTION_KEYWORDS = (
    "审批",
    "批准",
    "驳回",
    "拒绝",
    "重启",
)

HUMAN_DECISION_DELEGATION_KEYWORDS = (
    "帮我",
    "替我",
    "代我",
    "给我",
    "直接",
    "执行",
    "操作",
    "处理",
    "请",
)

BUILTIN_WORKFLOW_SKILL_NAME = "livzon-workflow-builder"
BUILTIN_WORKFLOW_SKILL_TITLE = "Livzon 工作流创建助手"
BUILTIN_WORKFLOW_SKILL_DESCRIPTION = (
    "当用户提到工作流、流程、自动化、编排、SOP、运行、启用、停用、状态等意图时，"
    "用于基于当前 Dazah 可操作业务能力创建、查询、启停和运行助手工作流。"
)
BUILTIN_WORKFLOW_SKILL_KEYWORDS = [
    "工作流",
    "流程",
    "自动化",
    "编排",
    "SOP",
    "运行",
    "启用",
    "停用",
    "状态",
]
BUILTIN_WORKFLOW_SKILL_CONTENT = (
    "# Livzon 工作流创建助手\n\n"
    "当用户希望创建、查询、启停、运行或查看工作流状态时，按以下流程处理。\n\n"
    "1. 先调用 `dazah_tool` 的 `agent.list_workflow_capabilities`，"
    "获取当前可编排业务能力。只能使用返回结果中的 "
    "`workflow_allowed=true` 操作。\n"
    "2. 如果用户需求缺少必要业务字段，先用简短问题澄清；"
    "不要编造库存、采购、合同、飞书同步等数据。\n"
    "3. 创建工作流时调用 `agent.create_workflow`，步骤必须按 "
    "`order/title/operation/params/body/description` 输出。\n"
    "4. 工作流步骤不得包含高风险人工责任判断操作，例如审批、驳回、"
    "批准、重启。遇到这类需求时，说明只能查询和整理背景，"
    "最终操作需要用户到业务页面自行判断。\n"
    "5. 不得创建把上一步查询结果自动循环带入写操作的批量工作流。"
    "带 `{request_id}`、`{table_id}` 等路径参数的步骤必须提供明确 ID；"
    "如果用户想批量提交、批量同步或批量修改，先创建查询/提醒步骤，"
    "并提示用户逐项确认或到业务页面操作。\n"
    "6. 查询、修改、启用、停用、运行工作流时分别使用 "
    "`agent.list_workflows`、`agent.update_workflow`、`agent.set_workflow_enabled`、"
    "`agent.run_workflow`、`agent.get_workflow_run`。\n"
    "7. 写操作只会生成确认项。用户确认前，不要声称工作流已经创建、"
    "启停或运行完成。\n"
    "8. 回答使用业务卡片式文本，展示工作流名称、状态、步骤、"
    "当前运行状态和下一步动作；不要使用 Markdown 表格。\n"
)


class AgentService:
    def __init__(
        self,
        settings: Settings,
        repo: AgentRepository | None = None,
        access_scope_service: Any = None,
    ) -> None:
        ensure_agent_tools_registered()
        self.settings = settings
        self.repo = repo or AgentRepository()
        if access_scope_service is None:
            from app.modules.agent.access_scope import AgentAccessScopeService

            access_scope_service = AgentAccessScopeService()
        self.access_scope_service = access_scope_service
        self.tool_executor = ToolExecutor(
            registry=tool_registry,
            repo=self.repo,
            confirmation_ttl_seconds=int(
                getattr(self.settings, "AGENT_WRITE_CONFIRM_TTL_SECONDS", 300)
            ),
            access_scope_service=self.access_scope_service,
        )

    def _hermes_timeout_seconds(self) -> int:
        return int(getattr(self.settings, "AGENT_HERMES_TIMEOUT_SECONDS", 210))

    def _internal_api_timeout_seconds(self) -> int:
        return int(getattr(self.settings, "AGENT_INTERNAL_API_TIMEOUT_SECONDS", 120))

    async def list_skills(self, db: AsyncSession) -> list[AgentSkillOut]:
        return [self._skill_out(skill) for skill in await self.repo.list_skills(db)]

    async def create_skill(
        self,
        db: AsyncSession,
        *,
        request: AgentSkillCreate,
        current_user: User,
    ) -> AgentSkillOut:
        existing = await self.repo.get_skill_by_name(db, request.name)
        if existing is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Agent skill name already exists"
            )
        skill = AgentSkill(
            name=request.name,
            title=request.title,
            description=request.description,
            trigger_keywords=self._normalize_string_list(request.trigger_keywords),
            content=request.content,
            status=request.status,
            is_builtin=request.is_builtin,
        )
        skill.created_by = current_user.id
        skill.updated_by = current_user.id
        db.add(skill)
        await db.flush()
        await db.commit()
        return self._skill_out(skill)

    async def get_skill(
        self,
        db: AsyncSession,
        *,
        skill_id: uuid.UUID,
    ) -> AgentSkillOut:
        skill = await self.repo.get_skill(db, skill_id)
        if skill is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent skill not found")
        return self._skill_out(skill)

    async def update_skill(
        self,
        db: AsyncSession,
        *,
        skill_id: uuid.UUID,
        request: AgentSkillUpdate,
        current_user: User,
    ) -> AgentSkillOut:
        skill = await self.repo.get_skill(db, skill_id)
        if skill is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent skill not found")
        update_data = request.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key == "trigger_keywords" and value is not None:
                value = self._normalize_string_list(value)
            setattr(skill, key, value)
        skill.version += 1
        skill.updated_by = current_user.id
        await db.flush()
        await db.commit()
        return self._skill_out(skill)

    async def set_skill_status(
        self,
        db: AsyncSession,
        *,
        skill_id: uuid.UUID,
        status_value: str,
        current_user: User,
    ) -> AgentSkillOut:
        skill = await self.repo.get_skill(db, skill_id)
        if skill is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent skill not found")
        skill.status = status_value
        skill.version += 1
        skill.updated_by = current_user.id
        await db.flush()
        await db.commit()
        return self._skill_out(skill)

    async def delete_skill(
        self,
        db: AsyncSession,
        *,
        skill_id: uuid.UUID,
        current_user: User,
    ) -> None:
        skill = await self.repo.get_skill(db, skill_id)
        if skill is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent skill not found")
        if skill.is_builtin:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Builtin Agent skills can be disabled but not deleted",
            )
        skill.is_deleted = True
        skill.updated_by = current_user.id
        await db.flush()
        await db.commit()

    async def resolve_skills(
        self,
        db: AsyncSession,
        *,
        request: AgentSkillResolveRequest,
    ) -> AgentSkillResolveResponse:
        message = self._normalize_match_text(request.message)
        matches: list[tuple[int, AgentSkill]] = []
        for skill in await self.repo.list_active_skills(db):
            score = self._skill_match_score(skill, message, request)
            if score > 0:
                matches.append((score, skill))
        matches.sort(key=lambda item: (-item[0], item[1].name))
        return AgentSkillResolveResponse(
            skills=[
                AgentSkillResolvedOut(
                    name=skill.name,
                    title=skill.title,
                    description=skill.description,
                    trigger_keywords=skill.trigger_keywords or [],
                    content=skill.content,
                    score=score,
                )
                for score, skill in matches[: request.limit]
            ]
        )

    async def _prepare_attachments(
        self, request: AgentChatRequest
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not request.attachments:
            return [], []

        prepared: list[dict[str, Any]] = []
        metadata: list[dict[str, Any]] = []
        total_bytes = 0
        total_text_chars = 0
        for attachment in request.attachments:
            filename = attachment.filename.strip()
            if (
                not filename
                or filename != Path(filename).name
                or "/" in filename
                or "\\" in filename
            ):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "附件文件名不合法")
            extension = Path(filename).suffix.lower()
            allowed_content_types = AGENT_ATTACHMENT_CONTENT_TYPES.get(extension)
            content_type = attachment.content_type.split(";", 1)[0].strip().lower()
            if not allowed_content_types or content_type not in allowed_content_types:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"不支持附件 {filename} 的文件类型",
                )
            try:
                data = base64.b64decode(attachment.data_base64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, f"附件 {filename} 内容无效"
                ) from exc
            if len(data) != attachment.size:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, f"附件 {filename} 大小校验失败"
                )
            if len(data) > AGENT_ATTACHMENT_MAX_BYTES:
                raise HTTPException(
                    status.HTTP_413_CONTENT_TOO_LARGE,
                    f"附件 {filename} 超过 10 MB 限制",
                )
            total_bytes += len(data)
            if total_bytes > AGENT_ATTACHMENT_TOTAL_MAX_BYTES:
                raise HTTPException(
                    status.HTTP_413_CONTENT_TOO_LARGE,
                    "附件总大小超过 20 MB 限制",
                )

            kind = "image" if extension in AGENT_IMAGE_EXTENSIONS else "document"
            item: dict[str, Any] = {
                "filename": filename,
                "content_type": content_type,
                "size": len(data),
                "kind": kind,
            }
            if kind == "image":
                if not _has_valid_image_signature(extension, data):
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        f"图片 {filename} 的实际格式与扩展名不一致",
                    )
                item["data_base64"] = attachment.data_base64
            else:
                try:
                    extracted_text = await asyncio.to_thread(
                        _extract_attachment_text, extension, data
                    )
                except Exception as exc:
                    logger.info("Agent attachment parse failed: filename=%s", filename)
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        f"无法读取文档 {filename}，请确认文件未损坏或未加密",
                    ) from exc
                remaining = AGENT_ATTACHMENT_TOTAL_TEXT_MAX_CHARS - total_text_chars
                extracted_text = extracted_text.strip()[
                    :AGENT_ATTACHMENT_TEXT_MAX_CHARS
                ]
                extracted_text = extracted_text[: max(0, remaining)]
                total_text_chars += len(extracted_text)
                item["text"] = extracted_text or "（未提取到可读文本）"
                item["truncated"] = (
                    len(extracted_text) >= AGENT_ATTACHMENT_TEXT_MAX_CHARS
                )
            prepared.append(item)
            metadata.append(
                {
                    "filename": filename,
                    "content_type": content_type,
                    "size": len(data),
                    "kind": kind,
                }
            )
        return prepared, metadata

    async def chat(
        self,
        db: AsyncSession,
        *,
        request: AgentChatRequest,
        current_user: User,
    ) -> AgentChatResponse:
        attachments, attachment_metadata = await self._prepare_attachments(request)
        session, history = await self._prepare_chat_context(
            db,
            request=request,
            current_user=current_user,
            attachment_metadata=attachment_metadata,
        )
        policy_response = await self._human_decision_required_chat_response(
            db,
            session_id=session.id,
            message=request.message,
            current_user=current_user,
        )
        if policy_response:
            return policy_response

        hermes_result = await self._call_hermes(
            session_id=session.id,
            user=current_user,
            message=request.message,
            context=request.context,
            history=history,
            attachments=attachments,
        )
        assistant_text = str(
            hermes_result.get("message") or hermes_result.get("final_response") or ""
        )
        if not assistant_text:
            assistant_text = "Livzon Agent 已返回空结果，请稍后重试或换一种描述。"
        assistant = await self.repo.add_message(
            db,
            session_id=session.id,
            role="assistant",
            content=assistant_text,
            metadata=self._assistant_metadata(hermes_result, request.context),
            user_id=current_user.id if current_user else None,
        )

        pending_confirmations = [
            self._confirmation_out(item)
            for item in await self._resolve_pending_confirmations(
                db,
                hermes_result,
                session_id=session.id,
            )
        ]
        return AgentChatResponse(
            session_id=session.id,
            message=AgentMessageOut(
                id=assistant.id,
                role="assistant",
                content=assistant.content,
                created_at=assistant.created_at,
                metadata=assistant.message_metadata,
            ),
            pending_confirmations=pending_confirmations,
            tool_trace=list(hermes_result.get("tool_trace") or []),
        )

    async def stream_chat(
        self,
        db: AsyncSession,
        *,
        request: AgentChatRequest,
        current_user: User,
    ) -> AsyncIterator[str]:
        attachments, attachment_metadata = await self._prepare_attachments(request)
        session, history = await self._prepare_chat_context(
            db,
            request=request,
            current_user=current_user,
            attachment_metadata=attachment_metadata,
        )
        policy_response = await self._human_decision_required_chat_response(
            db,
            session_id=session.id,
            message=request.message,
            current_user=current_user,
        )
        if policy_response:
            trace_id = uuid.uuid4()
            run_id = uuid.uuid4()
            yield self._sse_backend_event(
                AgentBackendV2Event(
                    trace_id=trace_id,
                    run_id=run_id,
                    sequence=1,
                    type="accepted",
                    data={"session_id": str(session.id)},
                )
            )
            yield self._sse_backend_event(
                AgentBackendV2Event(
                    trace_id=trace_id,
                    run_id=run_id,
                    sequence=2,
                    type="finished",
                    data=policy_response.model_dump(mode="json"),
                )
            )
            return

        assistant_text = ""
        last_event: AgentBackendV2Event | None = None
        async for backend_event in self._call_hermes_stream(
            session_id=session.id,
            user=current_user,
            message=request.message,
            context=request.context,
            history=history,
            attachments=attachments,
        ):
            last_event = backend_event
            event = backend_event.type
            data = backend_event.data
            if event == "accepted":
                yield self._sse_backend_event(
                    backend_event.model_copy(
                        update={"data": {**data, "session_id": str(session.id)}}
                    )
                )
                continue

            if event == "text_delta":
                text = str(data.get("text") or "")
                assistant_text += text
                yield self._sse_backend_event(backend_event)
                continue

            if event == "error":
                yield self._sse_backend_event(backend_event)
                return

            if event != "finished":
                yield self._sse_backend_event(backend_event)
                continue

            hermes_result = {
                "message": data.get("message") or assistant_text,
                "pending_confirmations": data.get("pending_confirmations") or [],
                "tool_trace": data.get("tool_trace") or [],
            }
            assistant_text = str(hermes_result["message"] or assistant_text)
            if not assistant_text:
                assistant_text = "Livzon Agent 已返回空结果，请稍后重试或换一种描述。"
            assistant = await self.repo.add_message(
                db,
                session_id=session.id,
                role="assistant",
                content=assistant_text,
                metadata=self._assistant_metadata(hermes_result, request.context),
                user_id=current_user.id if current_user else None,
            )
            await db.commit()
            pending_confirmations = [
                self._confirmation_out(item)
                for item in await self._resolve_pending_confirmations(
                    db,
                    hermes_result,
                    session_id=session.id,
                )
            ]
            response = AgentChatResponse(
                session_id=session.id,
                message=AgentMessageOut(
                    id=assistant.id,
                    role="assistant",
                    content=assistant.content,
                    created_at=assistant.created_at,
                    metadata=assistant.message_metadata,
                ),
                pending_confirmations=pending_confirmations,
                tool_trace=list(hermes_result.get("tool_trace") or []),
            )
            yield self._sse_backend_event(
                backend_event.model_copy(
                    update={"data": response.model_dump(mode="json")}
                )
            )
            return

        if last_event is None:
            trace_id = uuid.uuid4()
            run_id = uuid.uuid4()
            sequence = 1
        else:
            trace_id = last_event.trace_id
            run_id = last_event.run_id
            sequence = last_event.sequence + 1
        yield self._sse_backend_event(
            AgentBackendV2Event(
                trace_id=trace_id,
                run_id=run_id,
                sequence=sequence,
                type="error",
                data={
                    "message": (
                        "Livzon Agent 连接已中断，未收到 V2 finished 事件，请重试。"
                    )
                },
            )
        )

    async def _prepare_chat_context(
        self,
        db: AsyncSession,
        *,
        request: AgentChatRequest,
        current_user: User,
        attachment_metadata: list[dict[str, Any]] | None = None,
    ) -> tuple[Any, list[dict[str, Any]]]:
        user_id = current_user.id if current_user else None
        session = None
        if request.session_id:
            session = await self.repo.get_session(db, request.session_id)
            if session is None:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, "Agent session not found"
                )
            if session.user_id and session.user_id != user_id:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    "Agent session does not belong to current user",
                )
            if session.status != "active":
                session.status = "active"
                session.updated_by = user_id
                await db.flush()
        if session is None:
            session = await self.repo.create_session(
                db,
                user_id=user_id,
                context=request.context,
                title=request.message[:80],
            )

        await self.repo.add_message(
            db,
            session_id=session.id,
            role="user",
            content=request.message,
            metadata={
                "context": request.context,
                "attachments": attachment_metadata or [],
            },
            user_id=user_id,
        )
        history = await self.repo.list_messages(db, session_id=session.id)
        # Hermes executes tools through a separate HTTP request and database
        # session. Commit the session and user message before handing control
        # to Hermes so tool-call audit rows do not wait on an uncommitted
        # foreign-key target.
        await db.commit()
        return (
            session,
            [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "metadata": msg.message_metadata,
                }
                for msg in history
                if msg.role in {"user", "assistant"}
            ],
        )

    async def list_sessions(
        self,
        db: AsyncSession,
        *,
        current_user: User,
        page: int,
        page_size: int,
    ) -> AgentSessionPage:
        rows, total = await self.repo.list_user_sessions(
            db,
            user_id=current_user.id,
            page=page,
            page_size=page_size,
        )
        return AgentSessionPage(
            items=[self._session_item(*row) for row in rows],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def get_session_detail(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        current_user: User,
    ) -> AgentSessionDetail:
        session = await self.repo.get_session(db, session_id)
        if session is None or session.user_id != current_user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent session not found")
        messages = await self.repo.list_all_messages(db, session_id=session.id)
        confirmations = await self.repo.list_session_confirmations(
            db, session_id=session.id
        )
        pending_count = sum(
            item.status == "pending" and item.expires_at > datetime.now(UTC)
            for item in confirmations
        )
        return AgentSessionDetail(
            session=self._session_item(
                session,
                len(messages),
                messages[-1].content if messages else None,
                pending_count,
            ),
            messages=[
                AgentMessageOut(
                    id=item.id,
                    role=item.role,
                    content=item.content,
                    created_at=item.created_at,
                    metadata=item.message_metadata,
                )
                for item in messages
                if item.role in {"system", "user", "assistant", "tool"}
            ],
            confirmations=[self._confirmation_out(item) for item in confirmations],
        )

    async def archive_session(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        current_user: User,
    ) -> AgentSessionItem:
        session = await self.repo.get_session(db, session_id)
        if session is None or session.user_id != current_user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent session not found")
        await self.repo.archive_session(db, session=session, user_id=current_user.id)
        return self._session_item(session, 0, None, 0)

    async def _human_decision_required_chat_response(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        message: str,
        current_user: User,
    ) -> AgentChatResponse | None:
        if not self._is_human_decision_required_message(message):
            return None
        assistant = await self.repo.add_message(
            db,
            session_id=session_id,
            role="assistant",
            content=HUMAN_DECISION_REQUIRED_MESSAGE,
            metadata={"source": "policy", "policy": "human_decision_required"},
            user_id=current_user.id if current_user else None,
        )
        await db.commit()
        return AgentChatResponse(
            session_id=session_id,
            message=AgentMessageOut(
                id=assistant.id,
                role="assistant",
                content=assistant.content,
                created_at=assistant.created_at,
                metadata=assistant.message_metadata,
            ),
            pending_confirmations=[],
            tool_trace=[],
        )

    async def execute_tool(
        self,
        db: AsyncSession,
        *,
        request: AgentToolExecuteRequest,
    ) -> AgentToolExecuteResponse:
        request = self._normalize_tool_request(request)
        validation_error = self._tool_request_validation_error(request)
        if validation_error:
            session_id = request.session_id
            call = await self.repo.create_tool_call(
                db,
                session_id=session_id,
                operation=request.operation,
                request_payload=request.model_dump(mode="json"),
            )
            result = AgentToolExecuteResponse(
                ok=False,
                operation=request.operation,
                data={"message": validation_error},
                meta={"validation": "failed"},
            )
            await self.repo.finish_tool_call(
                db,
                call,
                status="invalid_request",
                response_payload=result.model_dump(mode="json"),
            )
            return result

        return await self.tool_executor.execute(
            db,
            request=request,
            agent_service=self,
        )

    async def execute_confirmation(
        self,
        db: AsyncSession,
        *,
        confirmation_id: uuid.UUID,
        current_user: User,
    ) -> tuple[AgentConfirmation, AgentToolExecuteResponse]:
        confirmation = await self.repo.get_confirmation_for_update(db, confirmation_id)
        if confirmation is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Agent confirmation not found"
            )
        if confirmation.user_id and confirmation.user_id != current_user.id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Agent confirmation does not belong to current user",
            )
        if confirmation.status != "pending":
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Agent confirmation is not pending"
            )
        if confirmation.expires_at <= datetime.now(UTC):
            confirmation.status = "expired"
            await db.flush()
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Agent confirmation has expired"
            )

        payload = confirmation.request_payload
        request = AgentToolExecuteRequest.model_validate(payload)
        request = self._normalize_tool_request(request)
        validation_error = self._tool_request_validation_error(request)
        if validation_error:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, validation_error)
        confirmation.request_payload = request.model_dump(mode="json")
        try:
            result = await self.tool_executor.execute_confirmed(
                db,
                request=request,
                current_user=current_user,
                confirmation=confirmation,
                agent_service=self,
            )
        except HTTPException as exc:
            if exc.status_code == status.HTTP_403_FORBIDDEN:
                confirmation.status = "cancelled"
                confirmation.updated_by = current_user.id
                await db.flush()
            raise

        workflow_context = request.execution_context
        workflow_run_id = self._uuid_or_none(workflow_context.get("workflow_run_id"))
        if workflow_run_id:
            workflow_data = await self._continue_workflow_after_step_confirmation(
                db,
                run_id=workflow_run_id,
                user_id=current_user.id,
                step_result=result.model_dump(mode="json"),
            )
            result.meta["workflow_run"] = workflow_data
        confirmation = await self.repo.execute_confirmation(
            db,
            confirmation,
            result_payload=result.model_dump(mode="json"),
            user_id=current_user.id,
        )
        await self.repo.add_message(
            db,
            session_id=confirmation.session_id,
            role="assistant",
            content=f"已执行确认操作：{confirmation.summary}",
            metadata={
                "confirmation_id": str(confirmation.id),
                "result": result.model_dump(mode="json"),
            },
            user_id=current_user.id,
        ) if confirmation.session_id else None
        return confirmation, result

    async def cancel_confirmation(
        self,
        db: AsyncSession,
        *,
        confirmation_id: uuid.UUID,
        current_user: User,
    ) -> AgentConfirmation:
        confirmation = await self.repo.get_confirmation_for_update(db, confirmation_id)
        if confirmation is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Agent confirmation not found"
            )
        if confirmation.user_id and confirmation.user_id != current_user.id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Agent confirmation does not belong to current user",
            )
        if confirmation.status != "pending":
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Agent confirmation is not pending"
            )
        confirmation = await self.repo.cancel_confirmation(
            db,
            confirmation,
            user_id=current_user.id,
        )
        if confirmation.session_id:
            await self.repo.add_message(
                db,
                session_id=confirmation.session_id,
                role="assistant",
                content=f"已取消确认操作：{confirmation.summary}",
                metadata={"confirmation_id": str(confirmation.id)},
                user_id=current_user.id,
            )
        return confirmation

    async def _call_hermes(
        self,
        *,
        session_id: uuid.UUID,
        user: User,
        message: str,
        context: dict[str, Any],
        history: list[dict[str, Any]],
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not self.settings.HERMES_AGENT_V2_URL:
            return {
                "message": (
                    "Livzon Agent 服务尚未配置。请设置 HERMES_AGENT_V2_URL "
                    "后再使用业务智能助手。"
                ),
                "pending_confirmations": [],
                "tool_trace": [],
            }
        headers = {"Content-Type": "application/json"}
        if self.settings.HERMES_AGENT_TOKEN:
            headers["Authorization"] = f"Bearer {self.settings.HERMES_AGENT_TOKEN}"
        payload = AgentBackendV2Request(
            session_id=f"web:{session_id}",
            subject=AgentTrustedSubject(
                tenant_id=user.tenant_key or "default",
                user_id=user.id,
                display_name=user.name,
                source="web",
            ),
            source=AgentBackendSource(platform="web"),
            message=message,
            messages=history,
            attachments=attachments or [],
            client_capabilities=["structured_events"],
        ).model_dump(mode="json")
        try:
            async with httpx.AsyncClient(
                timeout=self._hermes_timeout_seconds()
            ) as client:
                response = await client.post(
                    self.settings.HERMES_AGENT_V2_URL,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
                if (
                    isinstance(data, dict)
                    and "data" in data
                    and isinstance(data["data"], dict)
                ):
                    return data["data"]
                return data if isinstance(data, dict) else {"message": str(data)}
        except httpx.HTTPError:
            logger.exception(
                "Hermes-Lite request failed: url=%s session_id=%s user_id=%s",
                self.settings.HERMES_AGENT_V2_URL,
                session_id,
                user.id,
            )
            return {
                "message": "Livzon Agent 服务暂不可用，已保留你的问题。请稍后重试。",
                "pending_confirmations": [],
                "tool_trace": [],
            }

    async def _call_hermes_stream(
        self,
        *,
        session_id: uuid.UUID,
        user: User,
        message: str,
        context: dict[str, Any],
        history: list[dict[str, Any]],
        attachments: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[AgentBackendV2Event]:
        agent_request = AgentBackendV2Request(
            session_id=f"web:{session_id}",
            subject=AgentTrustedSubject(
                tenant_id=user.tenant_key or "default",
                user_id=user.id,
                display_name=user.name,
                source="web",
            ),
            source=AgentBackendSource(platform="web"),
            message=message,
            messages=history,
            attachments=attachments or [],
            client_capabilities=["structured_events", "streaming"],
        )
        if not self.settings.HERMES_AGENT_V2_URL:
            yield AgentBackendV2Event(
                trace_id=agent_request.trace_id,
                run_id=agent_request.run_id,
                sequence=1,
                type="error",
                data={
                    "message": (
                        "Livzon Agent 服务尚未配置。请设置 HERMES_AGENT_V2_URL "
                        "后再使用业务智能助手。"
                    )
                },
            )
            return
        headers = {"Content-Type": "application/json"}
        if self.settings.HERMES_AGENT_TOKEN:
            headers["Authorization"] = f"Bearer {self.settings.HERMES_AGENT_TOKEN}"
        payload = agent_request.model_dump(mode="json")
        stream_url = self._hermes_stream_url()
        last_sequence = 0
        try:
            hermes_timeout = self._hermes_timeout_seconds()
            timeout = httpx.Timeout(hermes_timeout, read=hermes_timeout)
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    stream_url,
                    json=payload,
                    headers=headers,
                ) as response:
                    if response.status_code >= 400:
                        content = await response.aread()
                        yield AgentBackendV2Event(
                            trace_id=agent_request.trace_id,
                            run_id=agent_request.run_id,
                            sequence=1,
                            type="error",
                            data={
                                "message": content.decode(errors="ignore")[:1000]
                            },
                        )
                        return
                    event = "message"
                    data_lines: list[str] = []
                    async for line in response.aiter_lines():
                        if line.startswith("event:"):
                            event = line.removeprefix("event:").strip() or "message"
                        elif line.startswith("data:"):
                            data_lines.append(line.removeprefix("data:").strip())
                        elif line == "":
                            if not data_lines:
                                event = "message"
                                continue
                            raw_data = "\n".join(data_lines)
                            data_lines = []
                            try:
                                data = json.loads(raw_data)
                            except json.JSONDecodeError:
                                data = None
                            try:
                                backend_event = AgentBackendV2Event.model_validate(data)
                            except ValidationError:
                                yield AgentBackendV2Event(
                                    trace_id=agent_request.trace_id,
                                    run_id=agent_request.run_id,
                                    sequence=last_sequence + 1,
                                    type="error",
                                    data={
                                        "message": (
                                            "Hermes-Lite 返回了无效的 AgentBackend "
                                            "V2 流事件。"
                                        )
                                    },
                                )
                                return
                            if (
                                backend_event.type != event
                                or backend_event.trace_id != agent_request.trace_id
                                or backend_event.run_id != agent_request.run_id
                                or backend_event.sequence <= last_sequence
                            ):
                                yield AgentBackendV2Event(
                                    trace_id=agent_request.trace_id,
                                    run_id=agent_request.run_id,
                                    sequence=last_sequence + 1,
                                    type="error",
                                    data={
                                        "message": (
                                            "Hermes-Lite 返回了不一致的 AgentBackend "
                                            "V2 流事件。"
                                        )
                                    },
                                )
                                return
                            last_sequence = backend_event.sequence
                            yield backend_event
                            event = "message"
        except httpx.HTTPError:
            logger.exception(
                "Hermes-Lite stream request failed: url=%s session_id=%s user_id=%s",
                stream_url,
                session_id,
                getattr(user, "id", None),
            )
            yield AgentBackendV2Event(
                trace_id=agent_request.trace_id,
                run_id=agent_request.run_id,
                sequence=last_sequence + 1,
                type="error",
                data={
                    "message": (
                        "Livzon Agent 服务暂不可用，已保留你的问题。请稍后重试。"
                    )
                },
            )

    def _hermes_stream_url(self) -> str:
        base = self.settings.HERMES_AGENT_V2_URL.rstrip("/")
        return f"{base}/stream"

    @staticmethod
    def _sse_backend_event(event: AgentBackendV2Event) -> str:
        return (
            f"event: {event.type}\n"
            f"data: {event.model_dump_json()}\n\n"
        )

    async def _perform_operation(
        self,
        operation: str,
        spec: OperationSpec,
        params: dict[str, Any],
        body: dict[str, Any] | None,
        *,
        db: AsyncSession | None = None,
        session_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> Any:
        local_result = await self._perform_local_operation(
            operation,
            params,
            body,
            db=db,
            session_id=session_id,
            user_id=user_id,
        )
        if local_result is not None:
            return local_result

        base_url = self.settings.AGENT_INTERNAL_API_BASE_URL.rstrip("/")
        path = self._format_path(spec.path, params)
        api_prefix = self.settings.API_V1_PREFIX.rstrip("/")
        if (
            api_prefix
            and base_url.endswith(api_prefix)
            and path.startswith(api_prefix + "/")
        ):
            path = path[len(api_prefix) :]
        query_params = {
            key: value
            for key, value in params.items()
            if "{" + key + "}" not in spec.path
        }
        headers: dict[str, str] = {}
        if self.settings.AGENT_INTERNAL_API_TOKEN:
            headers["Authorization"] = (
                f"Bearer {self.settings.AGENT_INTERNAL_API_TOKEN}"
            )
        async with httpx.AsyncClient(
            base_url=base_url,
            timeout=self._internal_api_timeout_seconds(),
            headers=headers,
        ) as client:
            response = await client.request(
                spec.method, path, params=query_params, json=body
            )
            if response.status_code >= 400:
                raise HTTPException(response.status_code, response.text[:1000])
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                return response.json()
            content = response.content
            result = {
                "content_type": content_type,
                "content_disposition": response.headers.get("content-disposition"),
                "size": len(content),
                "operation": operation,
            }
            if operation == "procurement.generate_contract":
                content_disposition = response.headers.get("content-disposition")
                result["artifact"] = {
                    "kind": "file",
                    "filename": self._download_filename(content_disposition)
                    or "采购合同.docx",
                    "content_type": content_type
                    or (
                        "application/vnd.openxmlformats-officedocument."
                        "wordprocessingml.document"
                    ),
                    "base64": base64.b64encode(content).decode("ascii"),
                    "size": len(content),
                }
            return result

    async def _perform_local_operation(
        self,
        operation: str,
        params: dict[str, Any],
        body: dict[str, Any] | None = None,
        *,
        db: AsyncSession | None = None,
        session_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> Any:
        if operation == "procurement.list_contract_templates":
            return {
                "templates": [
                    self._contract_template_info(category)
                    for category in ContractCategory
                ],
                "generate_operation": "procurement.generate_contract",
                "template_lookup_operation": "procurement.get_contract_template",
            }
        if operation == "procurement.get_contract_template":
            category = self._normalize_contract_category(params.get("category"))
            if not category:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "Missing required contract template category",
                )
            try:
                return self._contract_template_info(ContractCategory(str(category)))
            except ValueError as exc:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"Unsupported contract template category: {category}",
                ) from exc
        if operation == "agent.list_workflow_capabilities":
            return self._workflow_capabilities()
        if operation == "agent.create_workflow":
            self._require_local_db(db)
            assert db is not None
            request = AgentWorkflowCreate.model_validate(body or params)
            workflow = await self._create_workflow_from_request(
                db,
                request=request,
                user_id=user_id,
                session_id=session_id,
            )
            return {"workflow": self._workflow_out(workflow).model_dump(mode="json")}
        if operation == "agent.list_workflows":
            self._require_local_db(db)
            assert db is not None
            workflows = await self.repo.list_workflows(db, user_id=user_id)
            return {
                "workflows": [
                    self._workflow_out(workflow).model_dump(mode="json")
                    for workflow in workflows
                ]
            }
        if operation == "agent.get_workflow":
            self._require_local_db(db)
            assert db is not None
            workflow = await self._get_user_workflow(db, params, user_id=user_id)
            return {"workflow": self._workflow_out(workflow).model_dump(mode="json")}
        if operation == "agent.set_workflow_enabled":
            self._require_local_db(db)
            assert db is not None
            workflow = await self._get_user_workflow(db, params, user_id=user_id)
            enabled = bool((body or params).get("enabled"))
            workflow.status = "enabled" if enabled else "disabled"
            workflow.updated_by = user_id
            await db.flush()
            workflow = await self._refetch_workflow(db, workflow)
            return {"workflow": self._workflow_out(workflow).model_dump(mode="json")}
        if operation == "agent.run_workflow":
            self._require_local_db(db)
            assert db is not None
            workflow = await self._get_user_workflow(db, params, user_id=user_id)
            run = await self._start_workflow_run(
                db,
                workflow=workflow,
                user_id=user_id,
                session_id=session_id,
            )
            return run
        if operation == "agent.cancel_workflow_run":
            self._require_local_db(db)
            assert db is not None
            workflow_run = await self._get_user_workflow_run(
                db, params, user_id=user_id
            )
            if workflow_run.status in {"succeeded", "failed", "cancelled"}:
                return {
                    "run": self._workflow_run_out(workflow_run).model_dump(mode="json")
                }
            workflow_run.status = "cancelled"
            workflow_run.finished_at = datetime.now(UTC)
            workflow_run.updated_by = user_id
            await db.flush()
            workflow_run = await self._refetch_workflow_run(db, workflow_run)
            return {"run": self._workflow_run_out(workflow_run).model_dump(mode="json")}
        if operation == "agent.get_workflow_run":
            self._require_local_db(db)
            assert db is not None
            workflow_run = await self._get_user_workflow_run(
                db, params, user_id=user_id
            )
            return {"run": self._workflow_run_out(workflow_run).model_dump(mode="json")}
        return None

    def _workflow_capabilities(self) -> dict[str, Any]:
        capabilities = []
        for spec in tool_registry.list():
            if spec.name.startswith("agent."):
                continue
            capabilities.append(
                {
                    "operation": spec.name,
                    "summary": spec.summary or spec.name,
                    "method": spec.method,
                    "path": spec.path,
                    "write": spec.write,
                    "risk_level": spec.risk_level,
                    "workflow_allowed": spec.workflow_allowed
                    and not spec.human_decision_required,
                    "input_schema": spec.input_schema or {},
                    "output_hint": spec.output_hint
                    or (
                        "写操作会暂停工作流并生成确认卡"
                        if spec.write
                        else "查询操作可在工作流中自动执行"
                    ),
                }
            )
        return {
            "capabilities": capabilities,
            "workflow_operations": [
                spec.name
                for spec in tool_registry.list()
                if spec.name.startswith("agent.")
            ],
        }

    async def _create_workflow_from_request(
        self,
        db: AsyncSession,
        *,
        request: AgentWorkflowCreate,
        user_id: uuid.UUID | None,
        session_id: uuid.UUID | None,
    ) -> AgentWorkflow:
        steps = self._validated_workflow_steps(request.steps)
        if user_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "工作流必须归属已登录用户")
        user = await db.get(User, user_id) if hasattr(db, "get") else None
        for step in steps:
            spec = tool_registry.require(str(step["operation"]))
            await self.access_scope_service.require_tool_access(
                db,
                user=user,
                tool_name=spec.name,
                module=spec.module,
                for_workflow=True,
            )
        workflow = await self.repo.create_workflow(
            db,
            user_id=user_id,
            session_id=session_id,
            name=request.name,
            description=request.description,
            trigger_phrases=self._normalize_string_list(request.trigger_phrases),
            steps=steps,
            source_skill=request.source_skill or BUILTIN_WORKFLOW_SKILL_NAME,
            source_request=request.source_request,
        )
        await db.flush()
        return workflow

    async def _update_workflow_from_request(
        self,
        db: AsyncSession,
        *,
        workflow_id: uuid.UUID,
        request: AgentWorkflowUpdate,
        user_id: uuid.UUID | None,
    ) -> AgentWorkflow:
        workflow = await self._get_user_workflow(
            db, {"workflow_id": workflow_id}, user_id=user_id
        )
        if request.steps is not None:
            steps = self._validated_workflow_steps(request.steps)
            user = (
                await db.get(User, user_id) if user_id and hasattr(db, "get") else None
            )
            for step in steps:
                spec = tool_registry.require(str(step["operation"]))
                await self.access_scope_service.require_tool_access(
                    db,
                    user=user,
                    tool_name=spec.name,
                    module=spec.module,
                    for_workflow=True,
                )
            workflow.steps = steps
        if request.name is not None:
            workflow.name = request.name
        if "description" in request.model_fields_set:
            workflow.description = request.description
        if request.trigger_phrases is not None:
            workflow.trigger_phrases = self._normalize_string_list(
                request.trigger_phrases
            )
        workflow.updated_by = user_id
        await db.flush()
        return await self._refetch_workflow(db, workflow)

    @classmethod
    def _validated_workflow_steps(cls, steps: list[Any]) -> list[dict[str, Any]]:
        validated = []
        for raw_step in steps:
            step = (
                raw_step.model_dump(mode="json")
                if hasattr(raw_step, "model_dump")
                else dict(raw_step)
            )
            operation = str(step.get("operation") or "")
            spec = tool_registry.get(operation)
            if spec is None or operation.startswith("agent."):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"Workflow step operation is not allowed: {operation}",
                )
            if spec.human_decision_required or not spec.workflow_allowed:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"Workflow cannot include human-decision operation: {operation}",
                )
            params = step.get("params") or {}
            try:
                spec.input_model.model_validate({**params, **(step.get("body") or {})})
            except ValidationError as exc:
                missing = [
                    ".".join(str(part) for part in error.get("loc", ()))
                    for error in exc.errors()
                    if error.get("type") == "missing"
                ]
                if missing:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        (
                            f"Workflow step {operation} is missing required "
                            f"field(s): {', '.join(missing)}. "
                            "当前工作流不支持把上一步查询结果自动批量映射到写操作；"
                            "请指定明确 ID，或改为查询和提醒步骤。"
                        ),
                    ) from exc
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"Workflow step {operation} input is invalid: {exc.errors()[0]}",
                ) from exc
            validated.append(
                {
                    "order": int(step["order"]),
                    "title": str(step["title"]),
                    "operation": operation,
                    "params": params,
                    "body": step.get("body"),
                    "description": step.get("description"),
                }
            )
        return sorted(validated, key=lambda item: item["order"])

    async def _get_user_workflow(
        self,
        db: AsyncSession,
        params: dict[str, Any],
        *,
        user_id: uuid.UUID | None,
    ) -> AgentWorkflow:
        workflow_id = self._uuid_or_none(params.get("workflow_id") or params.get("id"))
        if workflow_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing workflow_id")
        workflow = await self.repo.get_workflow(db, workflow_id, user_id=user_id)
        if workflow is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent workflow not found")
        return workflow

    async def _get_user_workflow_run(
        self,
        db: AsyncSession,
        params: dict[str, Any],
        *,
        user_id: uuid.UUID | None,
    ) -> AgentWorkflowRun:
        run_id = self._uuid_or_none(params.get("run_id") or params.get("id"))
        if run_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing run_id")
        run = await self.repo.get_workflow_run(db, run_id, user_id=user_id)
        if run is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Agent workflow run not found"
            )
        return run

    async def _start_workflow_run(
        self,
        db: AsyncSession,
        *,
        workflow: AgentWorkflow,
        user_id: uuid.UUID | None,
        session_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        if workflow.status != "enabled":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Agent workflow is disabled"
            )
        run = await self.repo.create_workflow_run(
            db, workflow=workflow, user_id=user_id, session_id=session_id
        )
        return await self._continue_workflow_run(db, run=run, workflow=workflow)

    async def _continue_workflow_after_step_confirmation(
        self,
        db: AsyncSession,
        *,
        run_id: uuid.UUID,
        user_id: uuid.UUID | None,
        step_result: dict[str, Any],
    ) -> dict[str, Any]:
        run = await self.repo.get_workflow_run(db, run_id, user_id=user_id)
        if run is None:
            return {"status": "missing", "run_id": str(run_id)}
        workflow = await self.repo.get_workflow(db, run.workflow_id, user_id=user_id)
        if workflow is None:
            return {"status": "missing_workflow", "run_id": str(run_id)}
        step_index = run.current_step
        run.step_results = [
            *list(run.step_results or []),
            {
                "step_index": step_index,
                "status": "succeeded",
                "result": step_result,
                "completed_at": datetime.now(UTC).isoformat(),
            },
        ]
        run.current_step = step_index + 1
        run.status = "running"
        await db.flush()
        return await self._continue_workflow_run(db, run=run, workflow=workflow)

    async def _continue_workflow_run(
        self,
        db: AsyncSession,
        *,
        run: AgentWorkflowRun,
        workflow: AgentWorkflow,
    ) -> dict[str, Any]:
        steps = list(run.steps_snapshot or [])
        while run.current_step < len(steps):
            step_index = run.current_step
            step = steps[step_index]
            operation = str(step.get("operation") or "")
            spec = tool_registry.get(operation)
            if (
                spec is None
                or operation.startswith("agent.")
                or spec.human_decision_required
                or not spec.workflow_allowed
            ):
                run.status = "failed"
                run.error_message = (
                    f"Workflow step operation is not allowed: {operation}"
                )
                run.finished_at = datetime.now(UTC)
                await self._sync_workflow_last_run(workflow, run)
                await db.flush()
                run = await self._refetch_workflow_run(db, run)
                return {"run": self._workflow_run_out(run).model_dump(mode="json")}
            acting_user = await db.get(User, run.user_id) if run.user_id else None
            try:
                await self.access_scope_service.require_tool_access(
                    db,
                    user=acting_user,
                    tool_name=spec.name,
                    module=spec.module,
                    for_workflow=True,
                )
            except HTTPException as exc:
                run.status = "failed"
                run.error_message = str(exc.detail)
                run.finished_at = datetime.now(UTC)
                await self._sync_workflow_last_run(workflow, run)
                await db.flush()
                run = await self._refetch_workflow_run(db, run)
                return {"run": self._workflow_run_out(run).model_dump(mode="json")}
            if spec.write:
                summary = f"工作流「{workflow.name}」：{step.get('title') or operation}"
                execution_context = {
                    "workflow_id": str(workflow.id),
                    "workflow_run_id": str(run.id),
                    "workflow_step_index": step_index,
                }
                confirmation = await self.repo.create_confirmation(
                    db,
                    session_id=run.session_id,
                    user_id=run.user_id,
                    operation=operation,
                    summary=summary,
                    risk_level=spec.risk_level,
                    request_payload=AgentToolExecuteRequest(
                        operation=operation,
                        params=step.get("params") or {},
                        body=step.get("body"),
                        subject=AgentTrustedSubject(
                            tenant_id=acting_user.tenant_key or "default",
                            user_id=acting_user.id,
                            display_name=acting_user.name,
                            source="automation",
                        ),
                        session_id=run.session_id,
                        execution_context=execution_context,
                        reason=summary,
                    ).model_dump(mode="json"),
                    expires_at=datetime.now(UTC)
                    + timedelta(
                        seconds=getattr(
                            self.settings,
                            "AGENT_WRITE_CONFIRM_TTL_SECONDS",
                            300,
                        )
                    ),
                )
                run.status = "waiting_confirmation"
                run.step_results = [
                    *list(run.step_results or []),
                    {
                        "step_index": step_index,
                        "status": "waiting_confirmation",
                        "operation": operation,
                        "confirmation_id": str(confirmation.id),
                        "created_at": datetime.now(UTC).isoformat(),
                    },
                ]
                await self._sync_workflow_last_run(workflow, run)
                await db.flush()
                run = await self._refetch_workflow_run(db, run)
                return {
                    "run": self._workflow_run_out(run).model_dump(mode="json"),
                    "pending_confirmation": self._confirmation_out(
                        confirmation
                    ).model_dump(mode="json"),
                }
            try:
                result = await self.tool_executor.execute(
                    db,
                    request=AgentToolExecuteRequest(
                        operation=operation,
                        params=step.get("params") or {},
                        body=step.get("body"),
                        subject=AgentTrustedSubject(
                            tenant_id=acting_user.tenant_key or "default",
                            user_id=acting_user.id,
                            display_name=acting_user.name,
                            source="automation",
                        ),
                        session_id=run.session_id,
                        execution_context={
                            "workflow_id": str(workflow.id),
                            "workflow_run_id": str(run.id),
                            "workflow_step_index": step_index,
                        },
                        reason=str(step.get("title") or operation),
                    ),
                    agent_service=self,
                )
            except Exception as exc:
                run.status = "failed"
                run.error_message = str(exc)
                run.finished_at = datetime.now(UTC)
                await self._sync_workflow_last_run(workflow, run)
                await db.flush()
                run = await self._refetch_workflow_run(db, run)
                return {"run": self._workflow_run_out(run).model_dump(mode="json")}
            run.step_results = [
                *list(run.step_results or []),
                {
                    "step_index": step_index,
                    "status": "succeeded",
                    "operation": operation,
                    "result": result.model_dump(mode="json"),
                    "completed_at": datetime.now(UTC).isoformat(),
                },
            ]
            run.current_step = step_index + 1
            await db.flush()
        run.status = "succeeded"
        run.finished_at = datetime.now(UTC)
        await self._sync_workflow_last_run(workflow, run)
        await db.flush()
        run = await self._refetch_workflow_run(db, run)
        return {"run": self._workflow_run_out(run).model_dump(mode="json")}

    async def _sync_workflow_last_run(
        self, workflow: AgentWorkflow, run: AgentWorkflowRun
    ) -> None:
        workflow.last_run_id = run.id
        workflow.last_run_status = run.status
        workflow.last_run_at = datetime.now(UTC)

    async def _refetch_workflow(
        self, db: AsyncSession, workflow: AgentWorkflow
    ) -> AgentWorkflow:
        if not hasattr(db, "execute"):
            return workflow
        result = await db.execute(
            select(AgentWorkflow)
            .where(
                AgentWorkflow.id == workflow.id,
                AgentWorkflow.is_deleted.is_(False),
            )
            .execution_options(populate_existing=True)
        )
        return result.scalar_one()

    async def _refetch_workflow_run(
        self, db: AsyncSession, run: AgentWorkflowRun
    ) -> AgentWorkflowRun:
        if not hasattr(db, "execute"):
            return run
        result = await db.execute(
            select(AgentWorkflowRun)
            .where(
                AgentWorkflowRun.id == run.id,
                AgentWorkflowRun.is_deleted.is_(False),
            )
            .execution_options(populate_existing=True)
        )
        return result.scalar_one()

    def _contract_template_info(self, category: ContractCategory) -> dict[str, Any]:
        metadata = get_contract_template_metadata(category)
        template_file = TEMPLATE_FILES[category]
        template_path = TEMPLATE_DIR / template_file
        fields = [field.model_dump(mode="json") for field in metadata.fields]
        required_fields = [field["name"] for field in fields if field.get("required")]
        return {
            "category": metadata.category.value,
            "label": metadata.label,
            "template": {
                "file": template_file,
                "exists": template_path.exists(),
                "size": template_path.stat().st_size if template_path.exists() else 0,
            },
            "fields": fields,
            "required_fields": required_fields,
            "item_required_fields": ["name", "quantity", "unit_price"],
            "generate_required_fields": [
                "category",
                "contract_number",
                "contract_date",
                "items",
            ],
            "notes": (
                "生成合同时必须至少提供一条 items 明细；items 每条至少需要 "
                "name、quantity、unit_price。seller 字段可逐项补充，未提供时为空。"
            ),
        }

    async def _resolve_user_id(
        self,
        db: AsyncSession,
        session_id: uuid.UUID | None,
        user_id: Any,
    ) -> uuid.UUID | None:
        parsed = self._uuid_or_none(user_id)
        if parsed:
            return parsed
        if session_id:
            session = await self.repo.get_session(db, session_id)
            if session:
                return session.user_id
        return None

    async def _resolve_pending_confirmations(
        self,
        db: AsyncSession,
        hermes_result: dict[str, Any],
        *,
        session_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> list[AgentConfirmation]:
        confirmations: list[AgentConfirmation] = []
        seen: set[uuid.UUID] = set()

        async def append_confirmation(confirmation: AgentConfirmation | None) -> None:
            if confirmation is None:
                return
            if confirmation.id in seen:
                return
            if confirmation.status != "pending":
                return
            if confirmation.expires_at <= datetime.now(UTC):
                return
            seen.add(confirmation.id)
            confirmations.append(confirmation)

        for confirmation in await self.repo.list_pending_confirmations(
            db,
            session_id=session_id,
            user_id=user_id,
        ):
            await append_confirmation(confirmation)

        for confirmation_id in self._extract_confirmation_ids(hermes_result):
            parsed_id = self._uuid_or_none(confirmation_id)
            if not parsed_id:
                continue
            fetched_confirmation = await self.repo.get_confirmation(db, parsed_id)
            await append_confirmation(fetched_confirmation)
        return confirmations

    def _extract_confirmation_ids(self, value: Any) -> list[str]:
        ids: list[str] = []
        if isinstance(value, str):
            ids.extend(
                match.group(0)
                for match in re.finditer(
                    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
                    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                    r"[0-9a-fA-F]{12}\b",
                    value,
                )
            )
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                return ids
            ids.extend(self._extract_confirmation_ids(decoded))
            return ids
        if isinstance(value, list):
            for item in value:
                ids.extend(self._extract_confirmation_ids(item))
            return ids
        if not isinstance(value, dict):
            return ids

        for key in ("id", "confirmation_id"):
            item = value.get(key)
            if isinstance(item, str):
                ids.append(item)
        confirmation = value.get("confirmation")
        if isinstance(confirmation, dict):
            confirmation_id = confirmation.get("id")
            if isinstance(confirmation_id, str):
                ids.append(confirmation_id)
        pending_confirmation = value.get("pending_confirmation")
        if isinstance(pending_confirmation, dict):
            confirmation_id = pending_confirmation.get("id")
            if isinstance(confirmation_id, str):
                ids.append(confirmation_id)
        for item in value.values():
            ids.extend(self._extract_confirmation_ids(item))
        return ids

    def _format_path(self, path: str, params: dict[str, Any]) -> str:
        formatted = path
        for key, value in params.items():
            formatted = formatted.replace("{" + key + "}", str(value))
        if "{" in formatted or "}" in formatted:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Missing required operation path parameter"
            )
        return self.settings.API_V1_PREFIX.rstrip("/") + formatted

    @staticmethod
    def _path_param_names(path: str) -> list[str]:
        names: list[str] = []
        for part in path.split("{")[1:]:
            name = part.split("}", 1)[0].strip()
            if name:
                names.append(name)
        return names

    @staticmethod
    def _download_filename(content_disposition: str | None) -> str | None:
        if not content_disposition:
            return None
        lower = content_disposition.lower()
        marker = "filename*=utf-8''"
        if marker in lower:
            start = lower.index(marker) + len(marker)
            encoded = content_disposition[start:].split(";", 1)[0].strip().strip('"')
            return unquote(encoded)
        filename_marker = "filename="
        if filename_marker not in lower:
            return None
        start = lower.index(filename_marker) + len(filename_marker)
        return content_disposition[start:].split(";", 1)[0].strip().strip('"') or None

    @staticmethod
    def _requires_human_decision(spec: OperationSpec) -> bool:
        return spec.write and spec.risk_level == "high"

    @staticmethod
    def _is_human_decision_required_message(message: str) -> bool:
        normalized = "".join(str(message).lower().split())
        if not normalized:
            return False
        has_action = any(
            keyword in normalized for keyword in HUMAN_DECISION_ACTION_KEYWORDS
        )
        has_delegation = any(
            keyword in normalized for keyword in HUMAN_DECISION_DELEGATION_KEYWORDS
        )
        if not has_action or not has_delegation:
            return False
        read_only_markers = ("查看", "查询", "列出", "详情", "明细", "统计")
        if any(marker in normalized for marker in read_only_markers):
            return False
        return True

    def _normalize_tool_request(
        self, request: AgentToolExecuteRequest
    ) -> AgentToolExecuteRequest:
        if request.operation == "procurement.get_contract_template":
            source = self._unwrap_payload(request.body, request.params)
            source_text = " ".join(
                str(value)
                for value in [request.reason, *source.values()]
                if value is not None
            )
            category = self._normalize_contract_category(
                source.get("category")
                or source.get("contract_category")
                or source.get("template")
                or source.get("type")
                or source_text
            )
            return request.model_copy(update={"params": {"category": category}})
        if request.operation == "procurement.create_purchase_request":
            body = self._normalize_purchase_request_body(request.body, request.params)
            return request.model_copy(update={"body": body, "params": {}})
        if request.operation == "agent.create_workflow":
            body = self._normalize_workflow_body(
                request.body,
                request.params,
                request.reason,
            )
            return request.model_copy(update={"body": body, "params": {}})
        if request.operation == "procurement.generate_contract":
            body = self._normalize_contract_body(
                request.body,
                request.params,
                request.reason,
            )
            return request.model_copy(update={"body": body, "params": {}})
        return request

    @staticmethod
    def _tool_request_validation_error(request: AgentToolExecuteRequest) -> str | None:
        if request.operation == "agent.create_workflow":
            return AgentService._workflow_request_validation_error(request.body)
        if request.operation != "procurement.generate_contract":
            return None
        body = request.body or {}
        if not body.get("category"):
            return "合同生成缺少合同分类，请补充固定资产、耗材、五金或原材料分类。"
        items = body.get("items")
        if not isinstance(items, list) or not items:
            return "合同生成缺少合同明细，请至少补充一个物品名称、数量和单价。"
        missing_name = [
            index + 1
            for index, item in enumerate(items)
            if isinstance(item, dict) and not item.get("name")
        ]
        if missing_name:
            return f"合同生成第 {missing_name[0]} 条明细缺少物品名称。"
        return None

    @staticmethod
    def _workflow_request_validation_error(body: dict[str, Any] | None) -> str | None:
        try:
            workflow = AgentWorkflowCreate.model_validate(body or {})
        except ValidationError as exc:
            missing = [
                ".".join(str(part) for part in error.get("loc", ()))
                for error in exc.errors()
                if error.get("type") == "missing"
            ]
            if missing:
                return "工作流创建缺少必要字段：" + "、".join(missing)
            return f"工作流创建参数格式不正确：{exc.errors()[0].get('msg', str(exc))}"

        try:
            AgentService._validated_workflow_steps(workflow.steps)
        except HTTPException as exc:
            return str(exc.detail)
        return None

    def _normalize_workflow_body(
        self,
        body: dict[str, Any] | None,
        params: dict[str, Any],
        reason: str | None,
    ) -> dict[str, Any]:
        source = self._unwrap_payload(body, params)
        nested = source.get("workflow")
        if isinstance(nested, dict):
            source = {**source, **nested}
        if not source.get("name") and source.get("title"):
            source["name"] = source.get("title")
        if not source.get("source_request") and reason:
            source["source_request"] = reason
        return source

    def _normalize_contract_body(
        self,
        body: dict[str, Any] | None,
        params: dict[str, Any],
        reason: str | None,
    ) -> dict[str, Any]:
        source = self._unwrap_payload(body, params)
        source_text = " ".join(
            str(value) for value in [reason, *source.values()] if value is not None
        )
        category = self._normalize_contract_category(
            source.get("category")
            or source.get("contract_category")
            or source.get("template")
            or source.get("type")
            or source_text
        )
        items_source = self._extract_items_source(source)
        if not items_source and self._is_sample_contract_request(source_text):
            items_source = [
                {
                    "name": self._sample_contract_item_name(category, source_text),
                    "department": (
                        source.get("department")
                        or source.get("request_department")
                        or source.get("dept")
                        or ""
                    ),
                    "quantity": source.get("quantity") or source.get("qty") or 1,
                    "unit": source.get("unit") or self._default_contract_unit(category),
                    "unit_price": source.get("unit_price") or source.get("price") or 0,
                    "remarks": source.get("remarks") or source.get("remark") or "示例",
                }
            ]

        return {
            **source,
            "title": (
                source.get("title")
                or source.get("contract_title")
                or source.get("name")
                or self._default_contract_title(category, source_text)
            ),
            "category": category,
            "contract_number": (
                source.get("contract_number")
                or source.get("contract_no")
                or source.get("number")
                or self._default_contract_number(category)
            ),
            "contract_date": (
                source.get("contract_date")
                or source.get("date")
                or source.get("sign_date")
                or datetime.now(UTC).date().isoformat()
            ),
            "tax_rate": source.get("tax_rate") or 13,
            "seller": (
                source.get("seller") if isinstance(source.get("seller"), dict) else {}
            ),
            "items": [
                self._normalize_contract_item(item)
                for item in items_source
                if isinstance(item, dict)
            ],
        }

    @staticmethod
    def _unwrap_payload(
        body: dict[str, Any] | None,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        source: dict[str, Any] = dict(body or {})
        if not source:
            source = dict(params or {})
        for wrapper_key in (
            "payload",
            "request",
            "contract",
            "contract_request",
            "data",
        ):
            nested = source.get(wrapper_key)
            if isinstance(nested, dict):
                return {**source, **nested}
        return source

    def _extract_items_source(self, source: dict[str, Any]) -> list[Any]:
        items_source = source.get("items")
        if isinstance(items_source, list) and items_source:
            return items_source
        item_source = source.get("item")
        if isinstance(item_source, dict):
            return [item_source]
        single_item = {
            key: source.get(key)
            for key in (
                "item_code",
                "product_name",
                "name",
                "item_name",
                "title",
                "specification",
                "spec",
                "quality_standard",
                "manufacturer",
                "department",
                "quantity",
                "qty",
                "unit",
                "unit_price",
                "price",
                "amount",
                "remarks",
                "remark",
            )
            if key in source
        }
        item_markers = (
            "product_name",
            "name",
            "item_name",
            "title",
            "quantity",
            "qty",
            "unit_price",
            "price",
            "amount",
        )
        return [single_item] if any(key in single_item for key in item_markers) else []

    @staticmethod
    def _is_sample_contract_request(text: str) -> bool:
        return any(keyword in text for keyword in ("示例", "样例", "模板", "demo"))

    @staticmethod
    def _default_contract_number(category: Any) -> str:
        category_text = str(category or "contract").replace("-", "").upper()
        today = datetime.now(UTC).strftime("%Y%m%d")
        return f"AI-{category_text}-{today}-001"

    @staticmethod
    def _default_contract_title(category: Any, text: str) -> str:
        if "办公" in text or category == "consumables":
            return "办公用品耗材采购合同"
        if category == "hardware":
            return "五金备件采购合同"
        if category == "raw-materials":
            return "原材料采购合同"
        if category == "fixed-assets":
            return "固定资产采购合同"
        return "采购合同"

    @staticmethod
    def _default_contract_unit(category: Any) -> str:
        if category == "raw-materials":
            return "吨"
        if category == "fixed-assets":
            return "台"
        return "个"

    @staticmethod
    def _sample_contract_item_name(category: Any, text: str) -> str:
        if "办公" in text or category == "consumables":
            return "办公用品耗材"
        if category == "hardware":
            return "五金备件"
        if category == "raw-materials":
            return "原材料"
        if category == "fixed-assets":
            return "固定资产设备"
        return "采购物品"

    @staticmethod
    def _normalize_contract_category(value: Any) -> Any:
        if value is None:
            return value
        raw = str(value).strip()
        lower = raw.lower()
        aliases = {
            "fixed_assets": "fixed-assets",
            "fixed-assets": "fixed-assets",
            "固定资产": "fixed-assets",
            "设备": "fixed-assets",
            "consumables": "consumables",
            "耗材": "consumables",
            "办公用品": "consumables",
            "办公用品耗材": "consumables",
            "hardware": "hardware",
            "五金": "hardware",
            "五金备件": "hardware",
            "raw_materials": "raw-materials",
            "raw-materials": "raw-materials",
            "原材料": "raw-materials",
            "原料": "raw-materials",
        }
        for keyword, category in aliases.items():
            if keyword in raw or keyword in lower:
                return category
        return raw

    @staticmethod
    def _normalize_contract_item(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "item_code": item.get("item_code") or item.get("code") or "",
            "name": (
                item.get("name")
                or item.get("product_name")
                or item.get("item_name")
                or item.get("title")
            ),
            "specification": item.get("specification") or item.get("spec") or "",
            "quality_standard": item.get("quality_standard") or "",
            "manufacturer": item.get("manufacturer") or item.get("factory") or "",
            "department": (
                item.get("department") or item.get("request_department") or ""
            ),
            "quantity": item.get("quantity") or item.get("qty") or 1,
            "unit": item.get("unit") or "",
            "unit_price": item.get("unit_price") or item.get("price") or 0,
            "amount": item.get("amount"),
            "remarks": item.get("remarks") or item.get("remark") or "",
        }

    def _normalize_purchase_request_body(
        self,
        body: dict[str, Any] | None,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        source = self._unwrap_payload(body, params)

        items_source = source.get("items")
        if not isinstance(items_source, list) or not items_source:
            single_item = {
                key: source.get(key)
                for key in (
                    "product_name",
                    "name",
                    "item_name",
                    "specification",
                    "spec",
                    "purpose",
                    "note",
                    "quantity",
                    "unit",
                    "unit_price",
                    "price",
                    "remarks",
                    "remark",
                )
                if key in source
            }
            items_source = [single_item] if single_item else []

        return {
            "category": self._normalize_purchase_category(source.get("category")),
            "request_department": (
                source.get("request_department")
                or source.get("department")
                or source.get("request_dept")
                or source.get("dept")
                or source.get("applying_department")
            ),
            "request_date": (
                source.get("request_date")
                or source.get("date")
                or source.get("apply_date")
                or datetime.now(UTC).date().isoformat()
            ),
            "items": [
                self._normalize_purchase_request_item(item)
                for item in items_source
                if isinstance(item, dict)
            ],
        }

    @staticmethod
    def _normalize_purchase_category(value: Any) -> Any:
        if value is None:
            return value
        raw = str(value).strip()
        aliases = {
            "IT设备": "computer",
            "it设备": "computer",
            "电脑": "computer",
            "电脑材料": "computer",
            "计算机": "computer",
            "信息设备": "computer",
            "办公电脑": "computer",
            "五金": "hardware",
            "五金备件": "hardware",
            "五金材料": "hardware",
            "办公": "office",
            "办公用品": "office",
            "原辅料": "raw-auxiliary",
            "原辅材料": "raw-auxiliary",
            "原料": "raw-auxiliary",
            "辅料": "raw-auxiliary",
            "化玻": "chemical-glass",
            "化学玻璃": "chemical-glass",
            "化学试剂": "chemical-glass",
            "电气": "electrical",
            "电器": "electrical",
            "电气材料": "electrical",
            "劳保": "labor-protection",
            "劳动防护": "labor-protection",
            "劳保用品": "labor-protection",
        }
        return aliases.get(raw, raw)

    @staticmethod
    def _normalize_purchase_request_item(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "product_name": (
                item.get("product_name")
                or item.get("name")
                or item.get("item_name")
                or item.get("title")
            ),
            "specification": (
                item.get("specification") or item.get("spec") or item.get("model") or ""
            ),
            "purpose": item.get("purpose") or item.get("use") or item.get("note") or "",
            "material": item.get("material") or "",
            "brand": item.get("brand") or "",
            "quantity": item.get("quantity") or item.get("qty"),
            "unit": item.get("unit") or "",
            "unit_price": item.get("unit_price") or item.get("price"),
            "remarks": item.get("remarks") or item.get("remark") or "",
        }

    @staticmethod
    def _require_local_db(db: AsyncSession | None) -> None:
        if db is None:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Local Agent operation requires database session",
            )

    @staticmethod
    def _normalize_string_list(values: list[Any]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values or []:
            text = str(value).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result

    @staticmethod
    def _normalize_match_text(value: str) -> str:
        return "".join(str(value).lower().split())

    def _skill_match_score(
        self,
        skill: AgentSkill,
        message: str,
        request: AgentSkillResolveRequest,
    ) -> int:
        score = 0
        for keyword in skill.trigger_keywords or []:
            normalized = self._normalize_match_text(keyword)
            if normalized and normalized in message:
                score += 100
        haystack = self._normalize_match_text(
            " ".join([skill.name, skill.title, skill.description])
        )
        for token in [*request.business_scope, *request.available_tools]:
            normalized = self._normalize_match_text(token)
            if normalized and normalized in haystack:
                score += 10
        if message and message in haystack:
            score += 20
        return score

    @staticmethod
    def _skill_out(skill: AgentSkill) -> AgentSkillOut:
        return AgentSkillOut(
            id=skill.id,
            name=skill.name,
            title=skill.title,
            description=skill.description,
            trigger_keywords=skill.trigger_keywords or [],
            content=skill.content,
            status=skill.status,
            is_builtin=skill.is_builtin,
            version=skill.version,
            created_at=skill.created_at,
            updated_at=skill.updated_at,
        )

    @staticmethod
    def _workflow_out(workflow: AgentWorkflow) -> AgentWorkflowOut:
        return AgentWorkflowOut(
            id=workflow.id,
            user_id=workflow.user_id,
            session_id=workflow.session_id,
            name=workflow.name,
            description=workflow.description,
            status=workflow.status,
            trigger_phrases=workflow.trigger_phrases or [],
            steps=workflow.steps or [],
            source_skill=workflow.source_skill,
            source_request=workflow.source_request,
            last_run_id=workflow.last_run_id,
            last_run_status=workflow.last_run_status,
            last_run_at=workflow.last_run_at,
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
        )

    @staticmethod
    def _workflow_run_out(run: AgentWorkflowRun) -> AgentWorkflowRunOut:
        return AgentWorkflowRunOut(
            id=run.id,
            workflow_id=run.workflow_id,
            user_id=run.user_id,
            session_id=run.session_id,
            status=run.status,
            current_step=run.current_step,
            steps_snapshot=run.steps_snapshot or [],
            step_results=run.step_results or [],
            error_message=run.error_message,
            started_at=run.started_at,
            finished_at=run.finished_at,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )

    def _confirmation_out(
        self, confirmation: AgentConfirmation
    ) -> AgentConfirmationOut:
        return AgentConfirmationOut(
            id=confirmation.id,
            operation=confirmation.operation,
            summary=confirmation.summary,
            risk_level=confirmation.risk_level,
            status=confirmation.status,
            expires_at=confirmation.expires_at,
            request_payload=confirmation.request_payload,
            result_payload=confirmation.result_payload,
            executed_at=confirmation.executed_at,
            updated_at=confirmation.updated_at,
        )

    @staticmethod
    def _session_item(
        session: AgentSession,
        message_count: int,
        last_message: str | None,
        pending_confirmation_count: int,
    ) -> AgentSessionItem:
        preview = " ".join((last_message or "").split())
        if len(preview) > 100:
            preview = f"{preview[:100]}..."
        return AgentSessionItem(
            id=session.id,
            title=session.title,
            status=session.status,
            channel=str(session.context.get("channel") or "web"),
            message_count=message_count,
            last_message_preview=preview or None,
            pending_confirmation_count=pending_confirmation_count,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

    @staticmethod
    def _assistant_metadata(
        hermes_result: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        tool_trace = hermes_result.get("tool_trace") or []
        sources: list[dict[str, Any]] = []
        seen: set[str] = set()
        for trace in tool_trace:
            if not isinstance(trace, dict):
                continue
            operation = trace.get("operation")
            if not isinstance(operation, str) or operation in seen:
                continue
            seen.add(operation)
            params = (
                trace.get("params") if isinstance(trace.get("params"), dict) else {}
            )
            sources.append(
                {
                    "operation": operation,
                    "module": operation.split(".", 1)[0],
                    "params": params,
                    "ok": trace.get("ok"),
                }
            )
        return {
            "source": "hermes",
            "raw": hermes_result,
            "evidence": {
                "queried_at": datetime.now(UTC).isoformat(),
                "sources": sources,
                "scope": context.get("scope") or [],
                "truncated": any(
                    isinstance(item.get("params"), dict)
                    and item["params"].get("page_size") is not None
                    for item in sources
                ),
            },
        }

    def _uuid_or_none(self, value: Any) -> uuid.UUID | None:
        if not value:
            return None
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(str(value))
        except ValueError:
            return None
