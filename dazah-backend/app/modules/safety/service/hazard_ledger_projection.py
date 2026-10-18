"""隐患随手拍 → 公司隐患总台账汇总写入。

旧隐患登记流程（随手拍登记 + AI 识别 + 三级复核）保持不变；登记与状态
流转通过本模块把记录投影到「隐患随手拍」镜像页绑定的公司总台账飞书表，
使平台随手拍与飞书台账上的手工记录汇总在同一张表里展示。

设计要点：
- 全部经 ``submit_job`` 异步执行（best-effort），失败只记日志，不阻塞登记/复核；
- ``hazard_reports.ledger_record_id`` 是幂等锚点：首次写入建记录并回存 id，
  后续进度同步按 id 更新，不会重复建行；
- ``feishu_record_id`` 非空说明记录来自旧隐患流程飞书表（双向同步），跳过
  以免同一隐患在总台账出现两行；
- 人员字段解析走 IdentityResolver → bitable_id_mapper 两步链（安全应用
  open_id 命名空间与平台不同），失败则留空该字段不阻塞其它字段。
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.safety.feishu.bitable_client import SafetyBitableClient
from app.modules.safety.models import HazardReport, SafetyPageFeishuConfig

logger = logging.getLogger(__name__)

# 同一隐患的台账写入按提交顺序串行执行：三级复核的多个钩子几乎同时触发，
# 无序并发会出现「关闭后又被打回上一级进度」的覆盖竞态。
_hazard_locks: dict[UUID, asyncio.Lock] = {}


def _lock_for(hazard_id: UUID) -> asyncio.Lock:
    lock = _hazard_locks.get(hazard_id)
    if lock is None:
        lock = asyncio.Lock()
        _hazard_locks[hazard_id] = lock
    return lock

COMPANY_LEDGER_PAGE_KEY = "safety:risk-hazard:hazard-inspection:hazard-quick-report"

# 总台账列名（与飞书表字段名一致；表结构变更时同步调整这里）
_COL_DEPT = "部门/车间"
_COL_CONTENT = "隐患内容"
_COL_OWNER = "负责人"
_COL_TARGET_DATE = "目标完成日期"
_COL_CHECK_DATE = "检查内容"
_COL_DEFECT_PHOTOS = "隐患照片"
_COL_RECTIFIED_PHOTOS = "整改后照片"
_COL_CLOSE_STATUS = "关闭状态"
_COL_MEASURE = "隐患整改措施"
_COL_PROGRESS = "进度情况"

PHOTO_MAX_BYTES = 20 * 1024 * 1024

# rectification_status → 进度情况 文案（与前端台账口径一致）
_PROGRESS_LABELS = {
    "pending": "整改中",
    "in_progress": "整改中",
    "replied": "待复核",
    "level1_approved": "一级已通过",
    "level2_approved": "二级已通过",
    "level3_approved": "三级已通过",
    "closed": "已关闭",
    "rejected": "已驳回",
}


def _progress_label(status: str | None) -> str:
    return _PROGRESS_LABELS.get(status or "", "整改中")


def _date_to_ms(value: datetime | None) -> int | None:
    """datetime → 飞书日期毫秒（按东八区当天零点，与 field_codec 口径一致）。"""
    if value is None:
        return None
    from datetime import time as dt_time

    from app.modules.safety.feishu.field_codec import BITABLE_TIMEZONE

    local = value.astimezone(BITABLE_TIMEZONE) if value.tzinfo else value
    moment = datetime.combine(local.date(), dt_time.min, tzinfo=BITABLE_TIMEZONE)
    return int(moment.timestamp() * 1000)


def _parse_photo_paths(raw: str | None) -> list[Path]:
    """defect_photos/rectification_photos 存的是本地路径 JSON 数组字符串。"""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    if not isinstance(data, list):
        return []
    paths: list[Path] = []
    for item in data:
        text = str(item or "").strip().replace("\\", "/")
        if text:
            paths.append(Path(text))
    return paths


async def _ledger_binding(db: AsyncSession) -> SafetyPageFeishuConfig | None:
    """读公司总台账镜像页的绑定配置；未配置/停用/绑定不完整返回 None。"""
    model = (
        await db.execute(
            select(SafetyPageFeishuConfig).where(
                SafetyPageFeishuConfig.page_key == COMPANY_LEDGER_PAGE_KEY,
                SafetyPageFeishuConfig.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if model is None or not model.is_enabled:
        return None
    if not (model.app_token or "").strip() or not (model.table_id or "").strip():
        return None
    return model


async def _resolve_owner_open_id(
    db: AsyncSession, hazard: HazardReport
) -> list[dict[str, str]] | None:
    """整改责任人 → 安全应用 open_id（两步链，失败返回 None 不阻塞）。"""
    from app.modules.safety.feishu.bitable_id_mapper import get_bitable_person_value
    from app.modules.safety.feishu.identity_resolver import IdentityResolver

    resolver = IdentityResolver(db)
    try:
        resolved = await resolver.resolve_responsible_person(hazard)
    except Exception as exc:  # noqa: BLE001 —— 身份解析失败仅影响该字段
        logger.warning("总台账负责人解析失败 hazard=%s: %s", hazard.id, exc)
        return None
    if resolved is None:
        return None
    value = get_bitable_person_value(
        user_id=str(resolved.user_id) if resolved.user_id else None,
        name=resolved.name or hazard.rectification_responsible_person_name,
    )
    return value or None


async def _upload_photos(
    client: SafetyBitableClient, raw_paths: str | None
) -> list[dict[str, str]]:
    """把本地照片上传为飞书附件，返回 [{"file_token": ...}]（失败跳过单张）。"""
    tokens: list[dict[str, str]] = []
    for path in _parse_photo_paths(raw_paths):
        try:
            if not path.is_file() or path.stat().st_size > PHOTO_MAX_BYTES:
                logger.warning("总台账照片跳过（不存在或超限）: %s", path)
                continue
            token = await client.upload_media(path.read_bytes(), path.name)
        except Exception as exc:  # noqa: BLE001 —— 单张失败不阻塞
            logger.warning("总台账照片上传失败 %s: %s", path, exc)
            continue
        if token:
            tokens.append({"file_token": token})
    return tokens


async def project_hazard_to_company_ledger(hazard_id: UUID) -> None:
    """登记汇总：把一条随手拍隐患写入公司总台账（独立会话，幂等）。"""
    from app.core.database import async_session_factory

    async with _lock_for(hazard_id), async_session_factory() as db:
        try:
            binding = await _ledger_binding(db)
            if binding is None:
                logger.info("总台账未配置或停用，跳过汇总: hazard=%s", hazard_id)
                return
            hazard = (
                await db.execute(
                    select(HazardReport).where(HazardReport.id == hazard_id)
                )
            ).scalar_one_or_none()
            if hazard is None:
                logger.warning("汇总写入找不到隐患: %s", hazard_id)
                return
            if hazard.feishu_record_id:
                # 来自旧隐患流程飞书表（双向同步），总台账另行维护，避免重复
                return
            if hazard.ledger_record_id:
                # 已写入过：走进度同步而不是重复建行（同锁内直接调内部实现）
                client = SafetyBitableClient(
                    app_token=binding.app_token or "",
                    table_id=binding.table_id or "",
                )
                await _sync_progress_locked(db, binding, client, hazard)
                return

            client = SafetyBitableClient(
                app_token=binding.app_token or "",
                table_id=binding.table_id or "",
            )
            fields: dict[str, Any] = {
                _COL_DEPT: hazard.department or "",
                _COL_CONTENT: hazard.description or "",
                _COL_CHECK_DATE: _date_to_ms(hazard.discovered_at),
                _COL_TARGET_DATE: _date_to_ms(hazard.deadline),
                _COL_CLOSE_STATUS: "未关闭",
                _COL_PROGRESS: _progress_label(hazard.rectification_status),
            }
            owner = await _resolve_owner_open_id(db, hazard)
            if owner:
                fields[_COL_OWNER] = owner
            photos = await _upload_photos(client, hazard.defect_photos)
            if photos:
                fields[_COL_DEFECT_PHOTOS] = photos

            record_id = await client.create_record(
                fields, table_id=binding.table_id
            )
            if not record_id:
                logger.error("总台账写入失败: hazard=%s", hazard_id)
                return
            hazard.ledger_record_id = record_id
            await db.commit()
            await _refresh_mirror(binding, record_id)
            logger.info("总台账写入成功: hazard=%s record=%s", hazard_id, record_id)
        except Exception:
            await db.rollback()
            logger.exception("总台账汇总写入异常: hazard=%s", hazard_id)


async def sync_hazard_progress_to_company_ledger(hazard_id: UUID) -> None:
    """进度同步：整改回复/复核关闭后更新总台账对应记录（独立会话）。"""
    from app.core.database import async_session_factory

    async with _lock_for(hazard_id), async_session_factory() as db:
        try:
            binding = await _ledger_binding(db)
            if binding is None:
                return
            hazard = (
                await db.execute(
                    select(HazardReport).where(HazardReport.id == hazard_id)
                )
            ).scalar_one_or_none()
            if hazard is None or not hazard.ledger_record_id:
                return
            client = SafetyBitableClient(
                app_token=binding.app_token or "",
                table_id=binding.table_id or "",
            )
            await _sync_progress_locked(db, binding, client, hazard)
        except Exception:
            await db.rollback()
            logger.exception("总台账进度同步异常: hazard=%s", hazard_id)


async def _sync_progress_locked(
    db: AsyncSession,
    binding: SafetyPageFeishuConfig,
    client: SafetyBitableClient,
    hazard: HazardReport,
) -> None:
    """进度同步实现（调用方已持有该隐患的串行锁与数据库会话）。"""
    hazard_id = hazard.id
    record_id = hazard.ledger_record_id or ""
    try:
        fields: dict[str, Any] = {
            _COL_PROGRESS: _progress_label(hazard.rectification_status),
        }
        if hazard.rectification_status == "closed" or hazard.status == "closed":
            fields[_COL_CLOSE_STATUS] = "已关闭"
        else:
            fields[_COL_CLOSE_STATUS] = "未关闭"
        reply = (hazard.rectification_reply or "").strip()
        if reply:
            fields[_COL_MEASURE] = reply
        current = await client.get_record(record_id)
        from app.modules.safety.feishu.field_codec import (
            existing_attachment_tokens,
        )

        reply_photos = await _upload_photos(
            client, hazard.rectification_photos
        )
        if reply_photos:
            # 追加而不是覆盖：先读现有附件 token
            tokens = existing_attachment_tokens(current.get(_COL_RECTIFIED_PHOTOS))
            payload = [{"file_token": token} for token in tokens]
            payload.extend(reply_photos)
            fields[_COL_RECTIFIED_PHOTOS] = payload

        # 隐患照片补传：登记创建与照片上传后的 AI 重跑有时序差，首次写入
        # 可能还没有照片；按数量差补传（随手拍链路照片只增不减）
        local_defects = _parse_photo_paths(hazard.defect_photos)
        remote_tokens = existing_attachment_tokens(
            current.get(_COL_DEFECT_PHOTOS)
        )
        if len(local_defects) > len(remote_tokens):
            backlog = local_defects[len(remote_tokens) :]
            defect_payload = [
                {"file_token": token} for token in remote_tokens
            ]
            for path in backlog:
                try:
                    if not path.is_file() or path.stat().st_size > PHOTO_MAX_BYTES:
                        continue
                    token = await client.upload_media(
                        path.read_bytes(), path.name
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("总台账隐患照片补传失败 %s: %s", path, exc)
                    continue
                if token:
                    defect_payload.append({"file_token": token})
            if len(defect_payload) > len(remote_tokens):
                fields[_COL_DEFECT_PHOTOS] = defect_payload

        ok, error = await client.update_record_with_result(
            record_id, fields, table_id=binding.table_id
        )
        if not ok:
            logger.error(
                "总台账进度同步失败: hazard=%s record=%s err=%s",
                hazard_id,
                record_id,
                error,
            )
            return
        await _refresh_mirror(binding, record_id)
        logger.info(
            "总台账进度同步成功: hazard=%s status=%s",
            hazard_id,
            hazard.rectification_status,
        )
    except Exception:
        await db.rollback()
        logger.exception("总台账进度同步异常: hazard=%s", hazard_id)


async def _refresh_mirror(
    binding: SafetyPageFeishuConfig, record_id: str
) -> None:
    """写透本地镜像副本，让「隐患随手拍」页即时可见（不等 15 分钟同步）。"""
    from app.modules.safety.service.page_table import upsert_page_table_mirror_record

    try:
        await upsert_page_table_mirror_record(binding.page_key, record_id)
    except Exception:  # noqa: BLE001 —— 镜像刷新失败由定时同步兜底
        logger.warning(
            "总台账镜像刷新失败（等待定时同步兜底）: page=%s record=%s",
            binding.page_key,
            record_id,
        )
