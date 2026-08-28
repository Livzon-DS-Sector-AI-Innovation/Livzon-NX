"""邮件发送 - 支持 HTML 正文和附件。"""

import logging
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from app.shared.config_reader import get_module_setting

logger = logging.getLogger(__name__)


async def send_email_with_template(
    to_email: str,
    subject: str,
    html_body: str,
    attachment_path: str | None = None,
) -> bool:
    """通用邮件发送，支持自定义标题、HTML正文和附件。

    遵循后端规范：
    - 配置从 get_module_setting 读取，不用 os.getenv()
    - 不吞掉异常：失败记录 logger.exception
    """
    smtp_host = await get_module_setting("hr", "HR_MAIL_SMTP_HOST")
    smtp_port = int(await get_module_setting("hr", "HR_MAIL_SMTP_PORT", "465"))
    smtp_user = await get_module_setting("hr", "HR_MAIL_SMTP_USER")
    smtp_pass_encrypted = await get_module_setting("hr", "HR_MAIL_SMTP_PASS")
    from_addr = await get_module_setting("hr", "HR_MAIL_FROM", smtp_user or "")

    if not all([smtp_host, smtp_user, smtp_pass_encrypted]):
        logger.error("SMTP not configured")
        return False

    # 解密密码
    try:
        from app.core.llm import decrypt_api_key

        smtp_pass = decrypt_api_key(smtp_pass_encrypted)
    except Exception:
        smtp_pass = smtp_pass_encrypted

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email

    # 将纯文本转换为 HTML（\n 转 <br>）
    if "<html>" not in html_body.lower() and "<body>" not in html_body.lower():
        html_body = html_body.replace("\n", "<br>")

    # HTML 正文
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # 附件
    if attachment_path:
        file_path = Path(attachment_path).resolve()
        if file_path.exists():
            with open(file_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=("utf-8", "", file_path.name),
                )
                msg.attach(part)
            logger.info(
                "attachment added",
                extra={"file": str(file_path), "size": file_path.stat().st_size},
            )
        else:
            logger.error(
                "attachment file NOT found",
                extra={"path": attachment_path, "resolved": str(file_path)},
            )

    try:
        server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
        server.login(smtp_user, smtp_pass)
        server.sendmail(from_addr, [to_email], msg.as_string())
        server.quit()
        logger.info("email sent", extra={"to": to_email, "subject": subject})
        return True
    except Exception:
        logger.exception("failed to send email", extra={"to": to_email})
        return False
