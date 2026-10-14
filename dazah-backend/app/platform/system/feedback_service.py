import asyncio
import warnings
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import UUID

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.audit.service import record_audit_log
from app.platform.identity.models import User
from app.platform.system.feedback_models import FeedbackScreenshot, UserFeedback
from app.platform.system.feedback_repository import FeedbackRepository
from app.platform.system.feedback_schemas import (
    FeedbackListResponse,
    FeedbackResponse,
    FeedbackStatus,
    FeedbackUpdate,
)

MAX_SCREENSHOT_BYTES = 2 * 1024 * 1024


def validate_screenshot(content: bytes, content_type: str | None) -> tuple[bytes, str]:
    formats = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}
    if (
        content_type not in formats
        or not content
        or len(content) > MAX_SCREENSHOT_BYTES
    ):
        raise HTTPException(422, "截图须为 PNG、JPEG 或 WebP，每张不超过 2MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                if (
                    image.format != formats[content_type]
                    or image.width * image.height > 16_000_000
                ):
                    raise HTTPException(422, "截图格式不符或像素过大")
                image.verify()
            # Strip metadata and trailing payload; preserve only decoded pixels.
            with Image.open(BytesIO(content)) as image:
                output = BytesIO()
                image.convert("RGB").save(output, format="JPEG", quality=90)
                normalized = output.getvalue()
                if len(normalized) > MAX_SCREENSHOT_BYTES:
                    raise HTTPException(422, "截图像素过大，请压缩后上传")
                return normalized, "image/jpeg"
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise HTTPException(422, "截图无法读取，请上传有效图片") from exc


async def get_feedback(
    db: AsyncSession,
    feedback_id: UUID,
    owner_id: UUID | None = None,
    *,
    lock: bool = False,
) -> UserFeedback:
    record = await FeedbackRepository(db).get(feedback_id, owner_id, lock=lock)
    if record is None:
        raise HTTPException(404, "反馈不存在或无权访问")
    return record


async def create_feedback(
    db: AsyncSession,
    user: User,
    feedback_id: UUID,
    description: str,
    occurred_at: datetime,
    page_path: str,
    screenshots: list[UploadFile],
) -> FeedbackResponse:
    description = description.strip()
    if not 10 <= len(description) <= 5000:
        raise HTTPException(422, "请填写 10–5000 字的问题描述，包含操作步骤和实际结果")
    if occurred_at.tzinfo is None or occurred_at > datetime.now(UTC) + timedelta(
        minutes=5
    ):
        raise HTTPException(422, "发生时间须包含时区且不能晚于当前时间")
    if len(page_path) > 500 or (
        page_path
        and (
            not page_path.startswith("/")
            or page_path.startswith("//")
            or "?" in page_path
            or "#" in page_path
        )
    ):
        raise HTTPException(422, "页面路径须为站内路径，不能包含查询参数")
    if not 1 <= len(screenshots) <= 3:
        raise HTTPException(422, "请上传 1–3 张问题截图")
    images: list[tuple[bytes, str]] = []
    for screenshot in screenshots:
        content = await screenshot.read(MAX_SCREENSHOT_BYTES + 1)
        images.append(
            await asyncio.to_thread(
                validate_screenshot, content, screenshot.content_type
            )
        )
    record = UserFeedback(
        id=feedback_id,
        reporter_name=user.name or user.username or "用户",
        description=description,
        occurred_at=occurred_at,
        page_path=page_path,
        created_by=user.id,
        updated_by=user.id,
    )
    try:
        async with db.begin_nested():
            await FeedbackRepository(db).insert(record, images)
    except IntegrityError as exc:
        # The browser retains this ID across retries so a lost response cannot
        # submit the same feedback twice. Another user's ID never reveals data.
        existing = await FeedbackRepository(db).get(feedback_id, user.id)
        if existing is None:
            raise HTTPException(409, "反馈编号冲突，请重新打开表单") from exc
        return FeedbackResponse.model_validate(
            await get_feedback(db, feedback_id, user.id)
        )
    await record_audit_log(
        db,
        action="feedback_submitted",
        user_id=user.id,
        resource_type="user_feedback",
        resource_id=record.id,
        new_value={"screenshot_count": len(images)},
    )
    return FeedbackResponse.model_validate(await get_feedback(db, record.id, user.id))


async def list_feedback(
    db: AsyncSession,
    owner_id: UUID | None,
    status: FeedbackStatus | None,
    page: int,
    page_size: int,
) -> FeedbackListResponse:
    records, total, pending = await FeedbackRepository(db).list(
        owner_id, status, page, page_size
    )
    return FeedbackListResponse(
        items=[FeedbackResponse.model_validate(item) for item in records],
        total=total or 0,
        pending_count=pending or 0,
        page=page,
        page_size=page_size,
    )


async def update_feedback(
    db: AsyncSession, feedback_id: UUID, user: User, payload: FeedbackUpdate
) -> FeedbackResponse:
    record = await get_feedback(db, feedback_id, lock=True)
    if record.version != payload.version:
        raise HTTPException(409, "反馈已被其他管理员更新，请刷新后重试")
    reply = payload.reply.strip()
    if payload.status == "resolved" and not reply:
        raise HTTPException(422, "处理完成时请填写处理结果")
    old_status = record.status
    record.status, record.reply = payload.status, reply
    record.updated_by = user.id
    record.version += 1
    await db.flush()
    await record_audit_log(
        db,
        action="feedback_updated",
        user_id=user.id,
        resource_type="user_feedback",
        resource_id=feedback_id,
        old_value={"status": old_status},
        new_value={"status": payload.status},
    )
    return FeedbackResponse.model_validate(await get_feedback(db, feedback_id))


async def get_screenshot(
    db: AsyncSession, feedback_id: UUID, screenshot_id: UUID, owner_id: UUID | None
) -> FeedbackScreenshot:
    await get_feedback(db, feedback_id, owner_id)
    screenshot = await FeedbackRepository(db).screenshot(feedback_id, screenshot_id)
    if screenshot is None:
        raise HTTPException(404, "截图不存在")
    return screenshot
