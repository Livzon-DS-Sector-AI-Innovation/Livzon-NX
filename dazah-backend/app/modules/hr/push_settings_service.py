"""HR推送设置 Service - 推送模板管理、接收人配置、推送发送（含重试）、推送记录"""

import asyncio
import logging
import smtplib
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.hr.models import HrPushLog, HrPushRecipient, HrPushTemplate
from app.shared.config_reader import get_module_setting

logger = logging.getLogger(__name__)

# ─── 种子数据 ───

DEFAULT_PUSH_TEMPLATES: list[dict[str, Any]] = [
    {
        "entity_code": "recruitment",
        "scene_code": "interview_notice",
        "scene_label": "面试通知",
        "channel": "email",
        "title_template": "面试通知 - {name}",
        "body_template": (
            "<h2>面试通知</h2>"
            "<p>{name}：</p>"
            "<p>您已通过简历筛选，请于 {interview_time} 参加面试。</p>"
            "<p>面试官：{interviewer}</p>"
            "<p>地点：{location}</p>"
        ),
        "available_variables": [
            "name",
            "interview_time",
            "interviewer",
            "location",
            "position",
        ],
    },
    {
        "entity_code": "recruitment",
        "scene_code": "interview_notice",
        "scene_label": "面试通知",
        "channel": "feishu",
        "title_template": "面试安排提醒",
        "body_template": (
            "候选人 {name} 已安排面试\n"
            "时间：{interview_time}\n"
            "面试官：{interviewer}\n"
            "岗位：{position}"
        ),
        "available_variables": [
            "name",
            "interview_time",
            "interviewer",
            "position",
            "location",
        ],
    },
    {
        "entity_code": "recruitment",
        "scene_code": "offer_notice",
        "scene_label": "Offer录用通知",
        "channel": "email",
        "title_template": "录用通知 - {name}",
        "body_template": (
            "<h2>录用通知书</h2>"
            "<p>{name}：</p>"
            "<p>很高兴通知您，您已通过面试，被正式录用为 <strong>{positio"
            "n}</strong>。</p>"
            "<p>入职部门：{department}</p>"
            "<p>请于入职日携带身份证原件及复印件、学历证明、离职证明等材料报到。</p>"
        ),
        "available_variables": ["name", "position", "department", "onboard_date"],
    },
    {
        "entity_code": "recruitment",
        "scene_code": "offer_notice",
        "scene_label": "Offer录用通知",
        "channel": "feishu",
        "title_template": "录用确认通知",
        "body_template": (
            "候选人 {name} 已通过面试\n"
            "岗位：{position}\n"
            "部门：{department}\n"
            "请HR跟进发送正式Offer邮件"
        ),
        "available_variables": ["name", "position", "department"],
    },
]

DEFAULT_PUSH_RECIPIENTS: list[dict[str, Any]] = [
    {
        "entity_code": "recruitment",
        "scene_code": "interview_notice",
        "channel": "feishu",
        "department": None,
        "recipient_open_ids": [],
        "recipient_names": [],
        "use_dept_leader": True,
    },
    {
        "entity_code": "recruitment",
        "scene_code": "offer_notice",
        "channel": "feishu",
        "department": None,
        "recipient_open_ids": [],
        "recipient_names": [],
        "use_dept_leader": False,
    },
]


class PushSettingsService:
    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session

    # ─── 模板管理 ───

    async def list_push_templates(
        self, entity_code: str = "recruitment"
    ) -> list[HrPushTemplate]:
        if not self.session:
            return []
        result = await self.session.execute(
            select(HrPushTemplate)
            .where(
                HrPushTemplate.entity_code == entity_code,
                HrPushTemplate.is_deleted.is_(False),
            )
            .order_by(HrPushTemplate.scene_code, HrPushTemplate.channel)
        )
        return list(result.scalars().all())

    async def update_push_template(
        self, template_id: UUID, data: dict[str, Any]
    ) -> HrPushTemplate:
        if not self.session:
            raise RuntimeError("DB session not available")
        result = await self.session.execute(
            select(HrPushTemplate).where(
                HrPushTemplate.id == template_id,
                HrPushTemplate.is_deleted.is_(False),
            )
        )
        template = result.scalar_one_or_none()
        if not template:
            raise NotFoundException("推送模板", str(template_id))
        for key, value in data.items():
            setattr(template, key, value)
        await self.session.flush()
        # SQLAlchemy async 铁律：UPDATE 后必须 select re-fetch，禁止 refresh()
        result = await self.session.execute(
            select(HrPushTemplate).where(HrPushTemplate.id == template_id)
        )
        return result.scalar_one()

    # ─── 接收人配置 ───

    async def list_push_recipients(
        self, entity_code: str = "recruitment"
    ) -> list[HrPushRecipient]:
        if not self.session:
            return []
        result = await self.session.execute(
            select(HrPushRecipient)
            .where(
                HrPushRecipient.entity_code == entity_code,
                HrPushRecipient.is_deleted.is_(False),
            )
            .order_by(HrPushRecipient.scene_code)
        )
        return list(result.scalars().all())

    async def update_push_recipient(
        self, recipient_id: UUID, data: dict[str, Any]
    ) -> HrPushRecipient:
        if not self.session:
            raise RuntimeError("DB session not available")
        result = await self.session.execute(
            select(HrPushRecipient).where(
                HrPushRecipient.id == recipient_id,
                HrPushRecipient.is_deleted.is_(False),
            )
        )
        recipient = result.scalar_one_or_none()
        if not recipient:
            raise NotFoundException("接收人配置", str(recipient_id))
        for key, value in data.items():
            setattr(recipient, key, value)
        await self.session.flush()
        result = await self.session.execute(
            select(HrPushRecipient).where(HrPushRecipient.id == recipient_id)
        )
        return result.scalar_one()

    # ─── 推送记录 ───

    async def list_push_logs(
        self,
        entity_code: str = "recruitment",
        scene_code: str | None = None,
        channel: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[HrPushLog], int]:
        if not self.session:
            return [], 0
        query = select(HrPushLog).where(
            HrPushLog.entity_code == entity_code,
            HrPushLog.is_deleted.is_(False),
        )
        if scene_code:
            query = query.where(HrPushLog.scene_code == scene_code)
        if channel:
            query = query.where(HrPushLog.channel == channel)
        if status:
            query = query.where(HrPushLog.status == status)

        # count
        from sqlalchemy import func

        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.session.execute(count_query)).scalar() or 0

        # page
        query = (
            query.order_by(HrPushLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    # ─── 推送发送 ───

    async def send_notice_for_candidate(
        self,
        candidate_id: str,
        candidate_name: str,
        candidate_email: str,
        scene_code: str,
        variables: dict[str, Any],
        triggered_by: str | None = None,
    ) -> dict[str, Any]:
        """为候选人发送面试通知或Offer通知（邮件 + 飞书）"""
        result: dict[str, Any] = {
            "scene_code": scene_code,
            "email_sent": False,
            "email_recipient": None,
            "email_error": None,
            "feishu_sent": False,
            "feishu_recipients": [],
            "feishu_errors": [],
        }

        # 获取场景标签
        scene_labels = {
            "interview_notice": "面试通知",
            "offer_notice": "Offer录用通知",
        }
        result["scene_label"] = scene_labels.get(scene_code, scene_code)

        if not self.session:
            return result

        # 获取启用的模板
        templates_result = await self.session.execute(
            select(HrPushTemplate).where(
                HrPushTemplate.entity_code == "recruitment",
                HrPushTemplate.scene_code == scene_code,
                HrPushTemplate.is_enabled.is_(True),
                HrPushTemplate.is_deleted.is_(False),
            )
        )
        templates = list(templates_result.scalars().all())

        email_template = next((t for t in templates if t.channel == "email"), None)
        feishu_template = next((t for t in templates if t.channel == "feishu"), None)

        # 1. 发送邮件
        if email_template and candidate_email:
            title = _render_template(email_template.title_template, variables)
            body = _render_template(email_template.body_template, variables)
            try:
                await _send_email_with_retry(candidate_email, title, body)
                result["email_sent"] = True
                result["email_recipient"] = candidate_email
                await self._log_push(
                    entity_code="recruitment",
                    scene_code=scene_code,
                    channel="email",
                    recipient=candidate_email,
                    recipient_name=candidate_name,
                    title=title,
                    content=body,
                    status="success",
                    candidate_id=candidate_id,
                    candidate_name=candidate_name,
                    triggered_by=triggered_by,
                )
            except Exception as e:
                result["email_error"] = str(e)
                logger.exception(
                    "email send failed",
                    extra={"candidate_id": candidate_id, "to": candidate_email},
                )
                await self._log_push(
                    entity_code="recruitment",
                    scene_code=scene_code,
                    channel="email",
                    recipient=candidate_email,
                    recipient_name=candidate_name,
                    title=title,
                    content=body,
                    status="failed",
                    error=str(e),
                    candidate_id=candidate_id,
                    candidate_name=candidate_name,
                    triggered_by=triggered_by,
                )

        # 2. 发送飞书消息
        if feishu_template:
            open_ids = await self._resolve_recipients(
                scene_code, variables.get("department")
            )
            if open_ids:
                title = _render_template(feishu_template.title_template, variables)
                body = _render_template(feishu_template.body_template, variables)
                content = f"{title}\n\n{body}"
                for open_id in open_ids:
                    try:
                        await _send_feishu_with_retry(open_id, content)
                        result["feishu_sent"] = True
                        result["feishu_recipients"].append(open_id)
                        await self._log_push(
                            entity_code="recruitment",
                            scene_code=scene_code,
                            channel="feishu",
                            recipient=open_id,
                            title=title,
                            content=content,
                            status="success",
                            candidate_id=candidate_id,
                            candidate_name=candidate_name,
                            triggered_by=triggered_by,
                        )
                    except Exception as e:
                        result["feishu_errors"].append(f"{open_id}: {e}")
                        logger.exception(
                            "feishu send failed",
                            extra={"candidate_id": candidate_id, "open_id": open_id},
                        )
                        await self._log_push(
                            entity_code="recruitment",
                            scene_code=scene_code,
                            channel="feishu",
                            recipient=open_id,
                            title=title,
                            content=content,
                            status="failed",
                            error=str(e),
                            candidate_id=candidate_id,
                            candidate_name=candidate_name,
                            triggered_by=triggered_by,
                        )

        return result

    async def test_push(
        self, template_id: UUID, recipient: str, test_variables: dict[str, Any]
    ) -> dict[str, Any]:
        """手动测试推送"""
        if not self.session:
            raise RuntimeError("DB session not available")
        result = await self.session.execute(
            select(HrPushTemplate).where(HrPushTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()
        if not template:
            raise NotFoundException("推送模板", str(template_id))

        title = _render_template(template.title_template, test_variables)
        body = _render_template(template.body_template, test_variables)

        if template.channel == "email":
            try:
                await _send_email_with_retry(recipient, title, body)
                return {"success": True, "message": f"测试邮件已发送到 {recipient}"}
            except Exception as e:
                return {"success": False, "message": f"发送失败: {e}"}
        else:
            try:
                await _send_feishu_with_retry(recipient, f"{title}\n\n{body}")
                return {"success": True, "message": f"测试飞书消息已发送到 {recipient}"}
            except Exception as e:
                return {"success": False, "message": f"发送失败: {e}"}

    async def _resolve_recipients(
        self, scene_code: str, department: str | None = None
    ) -> list[str]:
        """解析飞书接收人列表"""
        if not self.session:
            return []
        query = select(HrPushRecipient).where(
            HrPushRecipient.entity_code == "recruitment",
            HrPushRecipient.scene_code == scene_code,
            HrPushRecipient.channel == "feishu",
            HrPushRecipient.is_enabled.is_(True),
            HrPushRecipient.is_deleted.is_(False),
        )
        if department:
            query = query.where(
                (HrPushRecipient.department == department)
                | (HrPushRecipient.department.is_(None))
            )
        result = await self.session.execute(query)
        recipients = list(result.scalars().all())

        open_ids: list[str] = []
        for r in recipients:
            open_ids.extend(r.recipient_open_ids or [])

        # TODO: 如果 use_dept_leader=True，从部门管理获取部门负责人的 open_id
        # 暂时跳过，后续接入部门负责人查询

        return list(set(open_ids))  # 去重

    async def _log_push(
        self,
        entity_code: str,
        scene_code: str,
        channel: str,
        recipient: str,
        title: str,
        content: str,
        status: str,
        error: str | None = None,
        recipient_name: str | None = None,
        candidate_id: str | None = None,
        candidate_name: str | None = None,
        triggered_by: str | None = None,
    ) -> None:
        """记录推送日志"""
        if not self.session:
            return
        log = HrPushLog(
            entity_code=entity_code,
            scene_code=scene_code,
            channel=channel,
            recipient=recipient,
            recipient_name=recipient_name,
            title=title,
            content_snippet=content[:500] if content else None,
            status=status,
            error_message=error,
            sent_at=datetime.now(UTC) if status == "success" else None,
            candidate_id=candidate_id,
            candidate_name=candidate_name,
            triggered_by=triggered_by,
        )
        self.session.add(log)
        await self.session.flush()


# ─── 模板渲染 ───


def _render_template(template: str, variables: dict[str, Any]) -> str:
    """渲染模板变量，安全替换 {var} 格式的占位符"""
    try:
        return template.format_map(_SafeDict(variables))
    except Exception:
        return template


class _SafeDict(dict[str, Any]):
    """安全的字典，缺少的 key 返回空字符串而非报错"""

    def __missing__(self, key: str) -> str:
        return ""


# ─── 带重试的发送函数 ───


async def _send_email_with_retry(to_email: str, subject: str, html_body: str) -> None:
    """SMTP 发送邮件，最多 3 次重试，指数退避（1s, 2s）"""
    from app.core.llm import decrypt_api_key

    smtp_host = await get_module_setting("hr", "HR_MAIL_SMTP_HOST")
    smtp_port = int(await get_module_setting("hr", "HR_MAIL_SMTP_PORT", "465"))
    smtp_user = await get_module_setting("hr", "HR_MAIL_SMTP_USER")
    smtp_pass_encrypted = await get_module_setting("hr", "HR_MAIL_SMTP_PASS")
    from_addr = await get_module_setting("hr", "HR_MAIL_FROM", smtp_user or "")

    if not all([smtp_host, smtp_user, smtp_pass_encrypted]):
        raise RuntimeError("SMTP 未配置")

    try:
        smtp_pass = decrypt_api_key(smtp_pass_encrypted)
    except Exception:
        smtp_pass = smtp_pass_encrypted

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    last_error = None
    for attempt in range(3):
        try:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, [to_email], msg.as_string())
            server.quit()
            logger.info("email sent", extra={"to": to_email, "attempt": attempt + 1})
            return
        except Exception as e:
            last_error = e
            logger.warning("SMTP attempt %d failed: %s", attempt + 1, e)
            if attempt < 2:
                await asyncio.sleep(2**attempt)  # 1s, 2s
    raise last_error  # type: ignore[misc]


async def _send_feishu_with_retry(open_id: str, content: str) -> None:
    """飞书消息发送，最多 3 次重试，指数退避（1s, 2s）"""
    from app.modules.hr.feishu.im import FeishuIM

    im = FeishuIM()
    last_error = None
    for attempt in range(3):
        try:
            await im.send_text_message(open_id, content)
            logger.info(
                "feishu sent", extra={"open_id": open_id, "attempt": attempt + 1}
            )
            return
        except Exception as e:
            last_error = e
            logger.warning("Feishu send attempt %d failed: %s", attempt + 1, e)
            if attempt < 2:
                await asyncio.sleep(2**attempt)
    raise last_error  # type: ignore[misc]


# ─── 种子数据初始化 ───


async def ensure_push_templates_seeded(session: AsyncSession) -> None:
    """确保推送模板和接收人种子数据存在"""
    result = await session.execute(select(HrPushTemplate))
    existing = {
        t.entity_code + t.scene_code + t.channel for t in result.scalars().all()
    }

    for tpl_data in DEFAULT_PUSH_TEMPLATES:
        key = tpl_data["entity_code"] + tpl_data["scene_code"] + tpl_data["channel"]
        if key not in existing:
            session.add(HrPushTemplate(**tpl_data))

    result = await session.execute(select(HrPushRecipient))
    existing_recipients = {
        r.entity_code + r.scene_code + r.channel for r in result.scalars().all()
    }

    for rec_data in DEFAULT_PUSH_RECIPIENTS:
        key = rec_data["entity_code"] + rec_data["scene_code"] + rec_data["channel"]
        if key not in existing_recipients:
            session.add(HrPushRecipient(**rec_data))

    await session.flush()
