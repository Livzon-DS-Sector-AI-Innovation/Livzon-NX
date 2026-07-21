"""Validation Audit business logic."""

import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.registration.models.validation_audit import (
    ValidationAuditFile,
    ValidationAuditIssue,
    ValidationAuditKnowledgeBase,
    ValidationAuditReport,
    ValidationAuditTask,
)
from app.modules.registration.prompts.validation_audit import (
    AUDIT_CROSS_SYSTEM,
    AUDIT_CROSS_USER_TEMPLATE,
    AUDIT_PROTOCOL_SYSTEM,
    AUDIT_PROTOCOL_USER_TEMPLATE,
    AUDIT_REPORT_SYSTEM,
    AUDIT_REPORT_USER_TEMPLATE,
    GOLDEN_STANDARD_SYSTEM,
    GOLDEN_STANDARD_USER_TEMPLATE,
    REPORT_GENERATION_SYSTEM,
    REPORT_GENERATION_USER_TEMPLATE,
)
from app.modules.registration.repository.validation_audit import (
    ValidationAuditFileRepository,
    ValidationAuditIssueRepository,
    ValidationAuditKnowledgeBaseRepository,
    ValidationAuditReportRepository,
    ValidationAuditTaskRepository,
)
from app.modules.registration.schemas.validation_audit import (
    AuditMode,
    AuditResult,
    TaskStatus,
    ValidationAuditTaskCreate,
    ValidationAuditTaskUpdate,
)
from app.core.llm import llm_client
from app.platform.integrations.ai.document_parser import DocumentParser

logger = logging.getLogger(__name__)

# 存储根目录
STORAGE_SUBDIR = "registration/validation-audit"


def _task_storage_path(task_id: UUID, subdir: str = "files") -> Path:
    """返回任务存储目录: storage/registration/validation-audit/tasks/{task_id}/{subdir}/"""
    settings = get_settings()
    base = Path(settings.STORAGE_ROOT) / STORAGE_SUBDIR / "tasks" / str(task_id) / subdir
    base.mkdir(parents=True, exist_ok=True)
    return base


class ValidationAuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.task_repo = ValidationAuditTaskRepository(session)
        self.file_repo = ValidationAuditFileRepository(session)
        self.issue_repo = ValidationAuditIssueRepository(session)
        self.report_repo = ValidationAuditReportRepository(session)
        self.kb_repo = ValidationAuditKnowledgeBaseRepository(session)

    # ── 任务 CRUD ─────────────────────────────────────────

    async def create_task(self, data: ValidationAuditTaskCreate) -> ValidationAuditTask:
        task = ValidationAuditTask(
            task_name=data.task_name,
            product_name=data.product_name,
            method_name=data.method_name,
            source_company=data.source_company,
            audit_mode=data.audit_mode.value,
            status=TaskStatus.DRAFT.value,
        )
        return await self.task_repo.create(task)

    async def get_task(self, task_id: UUID) -> ValidationAuditTask | None:
        return await self.task_repo.get_by_id(task_id)

    async def list_tasks(
        self,
        *,
        product_name: str | None = None,
        source_company: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ValidationAuditTask], int]:
        return await self.task_repo.list_tasks(
            product_name=product_name,
            source_company=source_company,
            status=status,
            page=page,
            page_size=page_size,
        )

    async def update_task(
        self, task: ValidationAuditTask, data: ValidationAuditTaskUpdate
    ) -> ValidationAuditTask:
        updates = data.model_dump(exclude_unset=True)
        if "audit_mode" in updates and updates["audit_mode"]:
            updates["audit_mode"] = updates["audit_mode"].value
        return await self.task_repo.update(task, **updates)

    async def delete_task(self, task: ValidationAuditTask) -> None:
        """级联软删除任务及其关联文件、问题、报告"""
        await self.task_repo.soft_delete(task)

    # ── 文件管理 ──────────────────────────────────────────

    async def save_uploaded_file(
        self,
        task: ValidationAuditTask,
        filename: str,
        content: bytes,
        file_type: str,
    ) -> ValidationAuditFile:
        """保存上传文件到磁盘并创建文件记录"""
        storage_dir = _task_storage_path(task.id, "files")
        unique_name = f"{uuid.uuid4().hex}_{filename}"
        file_path = storage_dir / unique_name
        file_path.write_bytes(content)

        audit_file = ValidationAuditFile(
            task_id=str(task.id),
            file_type=file_type,
            original_filename=filename,
            file_path=str(file_path),
            file_size=len(content),
        )
        return await self.file_repo.create(audit_file)

    async def list_files(self, task_id: UUID) -> list[ValidationAuditFile]:
        return await self.file_repo.list_by_task_id(task_id)

    # ── 文件解析 ──────────────────────────────────────────

    async def parse_files(self, task: ValidationAuditTask) -> None:
        """解析任务下所有待解析文件"""
        files = await self.file_repo.list_by_task_id(task.id)
        pending_files = [f for f in files if f.parse_status in ("pending", "failed")]
        
        if not pending_files:
            return

        await self.task_repo.update(task, status=TaskStatus.PARSING.value)

        for audit_file in pending_files:
            try:
                await self.file_repo.update_parse_result(
                    audit_file, parse_status="parsing"
                )
                text = DocumentParser.extract_text(audit_file.file_path, max_chars=80000)
                await self.file_repo.update_parse_result(
                    audit_file, parse_status="completed", parsed_text=text
                )
            except Exception as e:
                logger.exception("文件解析失败: %s", audit_file.original_filename)
                await self.file_repo.update_parse_result(
                    audit_file, parse_status="failed"
                )
                await self.task_repo.update(task, status=TaskStatus.FAILED.value)
                raise RuntimeError(f"文件解析失败: {audit_file.original_filename}: {e}") from e

        await self.task_repo.update(task, status=TaskStatus.UPLOADED.value)

    # ── 审核模式判定 ──────────────────────────────────────

    def determine_audit_mode(self, files: list[ValidationAuditFile]) -> str:
        """根据上传文件自动判定审核模式"""
        has_protocol = any(f.file_type == "protocol" for f in files)
        has_report = any(f.file_type == "report" for f in files)

        if has_protocol and has_report:
            return AuditMode.PROTOCOL_REPORT.value
        elif has_protocol:
            return AuditMode.PROTOCOL.value
        elif has_report:
            return AuditMode.REPORT.value
        else:
            return AuditMode.PROTOCOL.value

    # ── 黄金标准提取 ──────────────────────────────────────

    async def build_golden_standard(self, document_text: str, file_type: str) -> dict:
        """从文件中提取黄金标准"""
        user_prompt = GOLDEN_STANDARD_USER_TEMPLATE.format(
            file_type=file_type,
            document_text=document_text,
        )
        messages = [
            {"role": "system", "content": GOLDEN_STANDARD_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]
        raw = await llm_client.chat(messages, response_format="json_object", temperature=0.1)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("黄金标准提取返回非 JSON: %s", raw[:200])
            return {"golden_standard": {"items": [], "summary": raw[:500]}}

    # ── 执行审核 ──────────────────────────────────────────

    async def run_audit(self, task: ValidationAuditTask) -> AuditResult:
        """执行 AI 审核"""
        files = await self.file_repo.list_by_task_id(task.id)
        parsed_files = [f for f in files if f.parse_status == "completed" and f.parsed_text]

        if not parsed_files:
            raise RuntimeError("没有已解析的文件可供审核")

        await self.task_repo.update(task, status=TaskStatus.AUDITING.value)

        audit_mode = task.audit_mode

        try:
            if audit_mode == AuditMode.PROTOCOL.value:
                result = await self._audit_protocol(task, parsed_files)
            elif audit_mode == AuditMode.REPORT.value:
                result = await self._audit_report(task, parsed_files)
            elif audit_mode == AuditMode.PROTOCOL_REPORT.value:
                result = await self._audit_cross(task, parsed_files)
            else:
                raise RuntimeError(f"未知审核模式: {audit_mode}")

            return result

        except Exception as e:
            logger.exception("审核执行失败")
            await self.task_repo.update(task, status=TaskStatus.FAILED.value)
            raise RuntimeError(f"审核执行失败: {e}") from e

    async def _audit_protocol(
        self, task: ValidationAuditTask, files: list[ValidationAuditFile]
    ) -> AuditResult:
        protocol_file = next((f for f in files if f.file_type == "protocol"), files[0])
        golden = await self.build_golden_standard(protocol_file.parsed_text or "", "验证方案")

        user_prompt = AUDIT_PROTOCOL_USER_TEMPLATE.format(
            product_name=task.product_name,
            method_name=task.method_name,
            golden_standard=json.dumps(golden, ensure_ascii=False, indent=2),
            document_text=protocol_file.parsed_text or "",
        )
        messages = [
            {"role": "system", "content": AUDIT_PROTOCOL_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]
        raw = await llm_client.chat(messages, response_format="json_object", temperature=0.1, max_tokens=32768)
        return self._parse_audit_result(raw)

    async def _audit_report(
        self, task: ValidationAuditTask, files: list[ValidationAuditFile]
    ) -> AuditResult:
        report_file = next((f for f in files if f.file_type == "report"), files[0])
        golden = await self.build_golden_standard(report_file.parsed_text or "", "验证报告")

        user_prompt = AUDIT_REPORT_USER_TEMPLATE.format(
            product_name=task.product_name,
            method_name=task.method_name,
            golden_standard=json.dumps(golden, ensure_ascii=False, indent=2),
            document_text=report_file.parsed_text or "",
        )
        messages = [
            {"role": "system", "content": AUDIT_REPORT_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]
        raw = await llm_client.chat(messages, response_format="json_object", temperature=0.1, max_tokens=32768)
        return self._parse_audit_result(raw)

    async def _audit_cross(
        self, task: ValidationAuditTask, files: list[ValidationAuditFile]
    ) -> AuditResult:
        protocol_file = next((f for f in files if f.file_type == "protocol"), None)
        report_file = next((f for f in files if f.file_type == "report"), None)

        if not protocol_file or not report_file:
            raise RuntimeError("模式 C 需要同时上传方案和报告文件")

        golden_protocol = await self.build_golden_standard(
            protocol_file.parsed_text or "", "验证方案"
        )
        golden_report = await self.build_golden_standard(
            report_file.parsed_text or "", "验证报告"
        )

        user_prompt = AUDIT_CROSS_USER_TEMPLATE.format(
            product_name=task.product_name,
            method_name=task.method_name,
            golden_standard_protocol=json.dumps(golden_protocol, ensure_ascii=False, indent=2),
            golden_standard_report=json.dumps(golden_report, ensure_ascii=False, indent=2),
            protocol_text=protocol_file.parsed_text or "",
            report_text=report_file.parsed_text or "",
        )
        messages = [
            {"role": "system", "content": AUDIT_CROSS_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]
        raw = await llm_client.chat(messages, response_format="json_object", temperature=0.1, max_tokens=32768)
        return self._parse_audit_result(raw)

    def _parse_audit_result(self, raw: str) -> AuditResult:
        """解析 AI 返回的审核结果"""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("审核结果非 JSON: %s", raw[:300])
            return AuditResult(
                conclusion="fail",
                risk_level="high",
                summary=f"AI 返回格式异常，需人工审核。原始返回: {raw[:200]}",
            )

        issues_data = data.get("issues", [])
        issues = []
        for item in issues_data:
            issues.append({
                "issue_no": item.get("issue_no", "P000"),
                "dimension": item.get("dimension", "未分类"),
                "check_item": item.get("check_item", ""),
                "description": item.get("description", ""),
                "suggestion": item.get("suggestion"),
                "issue_type": item.get("issue_type", "general"),
                "page_no": item.get("page_no"),
                "evidence_text": item.get("evidence_text"),
            })

        return AuditResult(
            conclusion=data.get("conclusion", "fail"),
            risk_level=data.get("risk_level", "medium"),
            compliant_count=data.get("compliant_count", 0),
            non_compliant_count=data.get("non_compliant_count", 0),
            summary=data.get("summary", ""),
            issues=issues,
        )

    # ── 保存审核结果 ──────────────────────────────────────

    async def save_issues(
        self, task: ValidationAuditTask, result: AuditResult
    ) -> list[ValidationAuditIssue]:
        """保存审核问题到数据库"""
        issue_models = []
        for idx, issue_data in enumerate(result.issues, start=1):
            issue_type = issue_data["issue_type"] if isinstance(issue_data, dict) else issue_data.issue_type
            issue_no = issue_data["issue_no"] if isinstance(issue_data, dict) else issue_data.issue_no
            dimension = issue_data["dimension"] if isinstance(issue_data, dict) else issue_data.dimension
            check_item = issue_data["check_item"] if isinstance(issue_data, dict) else issue_data.check_item
            description = issue_data["description"] if isinstance(issue_data, dict) else issue_data.description
            suggestion = issue_data.get("suggestion") if isinstance(issue_data, dict) else issue_data.suggestion
            page_no = issue_data.get("page_no") if isinstance(issue_data, dict) else issue_data.page_no
            evidence_text = issue_data.get("evidence_text") if isinstance(issue_data, dict) else issue_data.evidence_text

            issue_model = ValidationAuditIssue(
                task_id=str(task.id),
                issue_no=issue_no if issue_no else f"P{idx:03d}",
                dimension=dimension,
                check_item=check_item,
                description=description,
                suggestion=suggestion,
                issue_type=issue_type,
                page_no=page_no,
                evidence_text=evidence_text,
            )
            issue_models.append(issue_model)

        saved_issues = await self.issue_repo.create_batch(issue_models)

        # 统计问题数量
        serious = sum(1 for i in result.issues if (i["issue_type"] if isinstance(i, dict) else i.issue_type) == "serious")
        general = sum(1 for i in result.issues if (i["issue_type"] if isinstance(i, dict) else i.issue_type) == "general")
        suggestion = sum(1 for i in result.issues if (i["issue_type"] if isinstance(i, dict) else i.issue_type) == "suggestion")

        # 更新任务状态和统计
        await self.task_repo.update(
            task,
            status=TaskStatus.COMPLETED.value,
            conclusion=result.conclusion.value if hasattr(result.conclusion, "value") else result.conclusion,
            risk_level=result.risk_level,
            serious_count=serious,
            general_count=general,
            suggestion_count=suggestion,
            compliant_count=result.compliant_count,
            non_compliant_count=result.non_compliant_count,
        )

        return saved_issues

    # ── 生成审核报告 ──────────────────────────────────────

    async def generate_report(
        self, task: ValidationAuditTask, result: AuditResult
    ) -> ValidationAuditReport:
        """生成 Markdown 审核报告"""
        issues = await self.issue_repo.list_by_task_id(task.id)

        issues_detail_lines = []
        for issue in issues:
            issues_detail_lines.append(
                f"### {issue.issue_no} [{issue.issue_type}] {issue.dimension} - {issue.check_item}\n"
                f"- **描述**: {issue.description}\n"
                f"- **建议**: {issue.suggestion or '无'}\n"
                f"- **页码**: {issue.page_no or '未知'}\n"
                f"- **证据**: {issue.evidence_text or '无'}\n"
            )
        issues_detail = "\n".join(issues_detail_lines)

        audit_mode_labels = {
            "protocol": "模式 A - 验证方案审核",
            "report": "模式 B - 验证报告审核",
            "protocol_report": "模式 C - 方案+报告联合审核",
        }

        user_prompt = REPORT_GENERATION_USER_TEMPLATE.format(
            task_name=task.task_name,
            product_name=task.product_name,
            method_name=task.method_name,
            source_company=task.source_company,
            audit_mode=audit_mode_labels.get(task.audit_mode, task.audit_mode),
            conclusion=task.conclusion or "待判定",
            risk_level=task.risk_level or "待评估",
            serious_count=task.serious_count,
            general_count=task.general_count,
            suggestion_count=task.suggestion_count,
            compliant_count=task.compliant_count,
            non_compliant_count=task.non_compliant_count,
            summary=result.summary,
            issues_detail=issues_detail,
        )
        messages = [
            {"role": "system", "content": REPORT_GENERATION_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]
        markdown = await llm_client.chat(messages, temperature=0.2, max_tokens=32768)

        # 保存报告文件
        report_dir = _task_storage_path(task.id, "reports")
        report_filename = f"audit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        report_path = report_dir / report_filename
        report_path.write_text(markdown, encoding="utf-8")

        # 获取当前最大版本号
        existing = await self.report_repo.get_by_task_id(task.id)
        version = (existing.version + 1) if existing else 1

        report = ValidationAuditReport(
            task_id=str(task.id),
            report_title=f"{task.task_name} - 审核报告 V{version}",
            report_markdown=markdown,
            report_file_path=str(report_path),
            version=version,
        )
        saved_report = await self.report_repo.create(report)

        # 更新任务的报告路径
        await self.task_repo.update(task, report_path=str(report_path))

        return saved_report

    # ── 查询问题列表 ──────────────────────────────────────

    async def list_issues(
        self, task_id: UUID, *, issue_type: str | None = None
    ) -> list[ValidationAuditIssue]:
        return await self.issue_repo.list_by_task_id(task_id, issue_type=issue_type)

    # ── 查询审核报告 ──────────────────────────────────────

    async def get_report(self, task_id: UUID) -> ValidationAuditReport | None:
        return await self.report_repo.get_by_task_id(task_id)

    # ── 导出报告 ──────────────────────────────────────────

    async def export_report(self, task_id: UUID) -> str | None:
        """返回报告文件路径"""
        report = await self.report_repo.get_by_task_id(task_id)
        if report and report.report_file_path:
            return report.report_file_path
        return None
