"""成品异常记录 AI 分类服务（产品 × 异常类型）。

口径经用户确认（2026-09-08）：异常类型 10 类固定枚举、产品 9 选 1，
人设为原料药生产企业资深现场 QA。模式仿 trend_ai_analysis：
错误码映射（no_config/rate_limited/invalid_output/timeout/provider_error），
绝不回传 raw_response 或完整 prompt。

结果缓存复用 quality_ai_analysis_logs：
- entity_type = "fp_anomaly_classification"（≤32 字符）
- entity_id = uuid5(固定命名空间, "{year}:{record_id}")（列为 UUID）
- input_snapshot.content_hash 用于增量去重（只分析新增/变更记录）
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Any, TypedDict
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.exceptions import AppException
from app.core.jobs import update_job_progress
from app.core.llm import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
    llm_client,
)
from app.core.llm.config import get_config
from app.modules.quality.models.ai_analysis_log import QualityAiAnalysisLog
from app.modules.quality.service.finished_product_anomaly_analysis_prompt import (
    ANOMALY_TYPE_OPTIONS,
    ANOMALY_TYPE_OTHER,
    PRODUCT_OPTIONS,
    PRODUCT_OTHER,
    PRODUCT_PREFIX_HINTS,
    build_classification_prompt,
)
from app.modules.quality.service.inspection_feishu_crud import (
    list_bitable_feishu_records,
)

logger = logging.getLogger(__name__)

ENTITY_TYPE = "fp_anomaly_classification"
ANALYSIS_TYPE = "product_anomaly_classification"

ANALYSIS_YEARS: tuple[int, ...] = (2025, 2026, 2027, 2028)

_BATCH_SIZE = 15
_MAX_PAGES = 10
_PAGE_SIZE = 200
_AI_SINGLE_TIMEOUT = 240
_MAX_RETRIES = 3

_UUID_NAMESPACE = uuid.UUID("6f2f6e50-4b7d-5a8e-9a3f-2c1d0b4e5a7f")

# 2025 年子表：产品以附件列表达（列名 → 规范产品名）
_PRODUCT_ATTACHMENT_FIELDS: dict[str, str] = {
    "洛伐他汀": "洛伐他汀",
    "美伐他汀": "美伐他汀",
    "霉酚酸": "霉酚酸",
    "多拉菌素": "多拉菌素",
    "盐酸林可霉素": "盐酸林可霉素",
    "苯丙氨酸": "L-苯丙氨酸",
    "色氨酸": "色氨酸",
}

_TYPE_FALLBACK = ANOMALY_TYPE_OTHER
_PRODUCT_FALLBACK = PRODUCT_OTHER


def _entity_uuid(year: int, record_id: str) -> uuid.UUID:
    return uuid.uuid5(_UUID_NAMESPACE, f"{year}:{record_id}")


def _entity_key(year: int, record_id: str) -> str:
    return f"{year}:{record_id}"


def _field_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("name") or item.get("text") or ""))
            else:
                parts.append(str(item))
        return "/".join(part for part in parts if part)
    if isinstance(value, dict):
        return str(value.get("name") or value.get("text") or value.get("link") or "")
    return str(value)


def _canonicalize_product(text: str) -> str:
    """把"MC（霉酚酸）"等带代码的原文归一到标准产品名。

    优先完全匹配 → 名称包含 → 批号前缀映射（前缀最长优先）→ 空串。
    """
    value = (text or "").strip()
    if not value:
        return ""
    if value in PRODUCT_OPTIONS:
        return value
    for option in PRODUCT_OPTIONS:
        if option != PRODUCT_OTHER and option in value:
            return option
    prefix = "".join(ch for ch in value[:8] if ch.isalpha()).upper()
    matched = ""
    best_len = 0
    for code, product in PRODUCT_PREFIX_HINTS.items():
        if prefix.startswith(code) and len(code) > best_len:
            matched = product
            best_len = len(code)
    return matched


def _product_hint(item: dict[str, Any], year: int) -> str:
    """结构化产品线索：2026 用涉及产品字段；2025 用产品附件列。结果为标准产品名。"""
    product_field = _field_text(item.get("涉及产品"))
    if product_field:
        canonical = _canonicalize_product(product_field)
        if canonical:
            return canonical
    if year <= 2025:
        for field, product in _PRODUCT_ATTACHMENT_FIELDS.items():
            if item.get(field):
                return product
    return ""


def _record_snapshot(item: dict[str, Any], year: int) -> dict[str, Any]:
    desc = _field_text(item.get("不合格项目描述")) or _field_text(
        item.get("不合格项目")
    )
    snapshot = {
        "year": year,
        "record_id": str(item.get("record_id") or ""),
        "desc": desc,
        "product_hint": _product_hint(item, year),
        "source": _field_text(item.get("数据来源")),
    }
    return snapshot


def _content_hash(snapshot: dict[str, Any]) -> str:
    normalized = json.dumps(snapshot, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def _list_year_items(db: AsyncSession, year: int) -> list[dict[str, Any]]:
    """翻页拉取某年飞书子表全部记录（最多 10 页）。"""
    items: list[dict[str, Any]] = []
    for page in range(1, _MAX_PAGES + 1):
        result = await list_bitable_feishu_records(
            db, f"finished_product_anomaly_{year}", page=page, page_size=_PAGE_SIZE
        )
        if not result.get("table_configured"):
            raise AppException(
                message=f"{year} 年成品异常报告飞书表未配置，无法分析",
                status_code=400,
            )
        items.extend(result.get("items") or [])
        total = int(result.get("total") or 0)
        if len(items) >= total or not result.get("items"):
            break
    return items


async def _load_cached_classifications(
    db: AsyncSession, year: int, record_ids: list[str]
) -> dict[str, dict[str, Any]]:
    """加载已缓存的分类结果，entity_id 取每个记录的最新一条。"""
    if not record_ids:
        return {}
    uuids = [_entity_uuid(year, record_id) for record_id in record_ids]
    result = await db.execute(
        select(QualityAiAnalysisLog)
        .where(
            QualityAiAnalysisLog.entity_type == ENTITY_TYPE,
            QualityAiAnalysisLog.entity_id.in_(uuids),
        )
        .order_by(QualityAiAnalysisLog.created_at.desc())
    )
    rows = result.scalars().all()
    cached: dict[str, dict[str, Any]] = {}
    for row in rows:
        snapshot = row.input_snapshot or {}
        record_id = str(snapshot.get("record_id") or "")
        if not record_id or record_id in cached:
            continue
        cached[record_id] = {
            "content_hash": str(snapshot.get("content_hash") or ""),
            "payload": row.output_payload or {},
            "status": row.status,
            "created_at": row.created_at,
        }
    return cached


async def _call_llm_batch(
    prompt: str,
) -> tuple[dict[str, Any] | None, str, str | None]:
    """单批分类调用，返回 (payload|None, model_name, error_code)。"""
    try:
        config = await get_config("text")
    except LLMConfigError:
        return None, "", "no_config"
    model_name = str(getattr(config, "model_name", "") or "unknown")
    payload: dict[str, Any] | None = None
    error_code: str | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            payload = await asyncio.wait_for(
                llm_client.chat_json(
                    [{"role": "user", "content": prompt}],
                    expected_keys=["items"],
                    temperature=0.2,
                    # 思考型模型（qwen 等）开启思维链会污染 JSON 输出，分类任务无需推理
                    enable_thinking=False,
                ),
                timeout=_AI_SINGLE_TIMEOUT + 15,
            )
            error_code = None
            break
        except LLMRateLimitError:
            error_code = "rate_limited"
            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(2**attempt)
                continue
        except LLMConfigError:
            return None, model_name, "no_config"
        except LLMOutputError:
            return None, model_name, "invalid_output"
        except LLMProviderError:
            return None, model_name, "provider_error"
        except TimeoutError:
            return None, model_name, "timeout"
    if error_code is not None:
        return None, model_name, error_code
    return payload, model_name, None


def _validate_batch_result(
    payload: dict[str, Any] | None, expected_ids: list[str]
) -> dict[str, dict[str, str]]:
    """白名单校验：非法产品/类型回退"其他"，未返回的记录视为缺失。"""
    validated: dict[str, dict[str, str]] = {}
    raw_items = payload.get("items") if isinstance(payload, dict) else []
    if not isinstance(raw_items, list):
        return validated
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        record_id = str(raw.get("id") or "")
        if record_id not in expected_ids or record_id in validated:
            continue
        product = str(raw.get("product") or "").strip()
        if product not in PRODUCT_OPTIONS:
            product = _PRODUCT_FALLBACK
        anomaly_type = str(raw.get("anomaly_type") or "").strip()
        if anomaly_type not in ANOMALY_TYPE_OPTIONS:
            anomaly_type = _TYPE_FALLBACK
        validated[record_id] = {
            "product": product,
            "anomaly_type": anomaly_type,
            "reason": str(raw.get("reason") or "")[:120],
        }
    return validated


async def classify_year(
    db: AsyncSession,
    year: int,
    *,
    job_id: str | None = None,
) -> dict[str, Any]:
    """对某年全部记录做增量 AI 分类，返回计数摘要。"""
    items = await _list_year_items(db, year)
    record_ids = [str(item.get("record_id") or "") for item in items]
    cached = await _load_cached_classifications(db, year, record_ids)

    pending: list[dict[str, Any]] = []
    skipped = 0
    for item in items:
        snapshot = _record_snapshot(item, year)
        content_hash = _content_hash(snapshot)
        previous = cached.get(snapshot["record_id"])
        if previous and previous.get("status") == "completed" and previous.get(
            "content_hash"
        ) == content_hash:
            skipped += 1
            continue
        pending.append({**snapshot, "content_hash": content_hash})

    analyzed = 0
    failed = 0
    last_error: str | None = None
    model_name = ""
    for start in range(0, len(pending), _BATCH_SIZE):
        batch = pending[start : start + _BATCH_SIZE]
        if job_id:
            done = analyzed + failed + skipped
            await update_job_progress(
                job_id,
                f"{year} 年分类进度 {done}/{len(items)}（本批 {len(batch)} 条）",
            )
        prompt = build_classification_prompt(
            [
                {
                    "id": entry["record_id"],
                    "year": entry["year"],
                    "desc": entry["desc"],
                    "product_hint": entry["product_hint"],
                    "source": entry["source"],
                }
                for entry in batch
            ]
        )
        payload, model_name, error_code = await _call_llm_batch(prompt)
        if payload is None:
            failed += len(batch)
            last_error = error_code
            logger.warning(
                "成品异常分类批次失败",
                extra={"module_name": "quality", "year": year, "error": error_code},
            )
            continue
        validated = _validate_batch_result(payload, [b["record_id"] for b in batch])
        for entry in batch:
            result = validated.get(entry["record_id"])
            log = QualityAiAnalysisLog(
                entity_type=ENTITY_TYPE,
                entity_id=_entity_uuid(year, entry["record_id"]),
                analysis_type=ANALYSIS_TYPE,
                input_snapshot={
                    "year": year,
                    "record_id": entry["record_id"],
                    "desc": entry["desc"],
                    "product_hint": entry["product_hint"],
                    "source": entry["source"],
                    "content_hash": entry["content_hash"],
                },
                output_payload=result,
                model_name=model_name or "unknown",
                status="completed" if result else "failed",
                error_message=None if result else "模型未返回该记录",
            )
            db.add(log)
            if result:
                analyzed += 1
            else:
                failed += 1
        await db.commit()

    return {
        "year": year,
        "total": len(items),
        "analyzed": analyzed,
        "skipped": skipped,
        "failed": failed,
        "last_error": last_error,
    }


async def run_analysis_job(
    years: list[int],
    job_id: str | None = None,
) -> dict[str, Any]:
    """后台 job 入口：自带数据库会话，逐年分类；未配置的年份跳过。"""
    summaries: list[dict[str, Any]] = []
    async with async_session_factory() as db:
        for year in years:
            if job_id:
                await update_job_progress(job_id, f"正在分析 {year} 年记录…")
            try:
                summaries.append(await classify_year(db, year, job_id=job_id))
            except AppException as exc:
                logger.warning(
                    "成品异常分类跳过年份",
                    extra={
                        "module_name": "quality",
                        "year": year,
                        "error": exc.message,
                    },
                )
                summaries.append(
                    {
                        "year": year,
                        "total": 0,
                        "analyzed": 0,
                        "skipped": 0,
                        "failed": 0,
                        "last_error": str(exc.message),
                    }
                )
    return {
        "years": years,
        "summaries": summaries,
        "analyzed": sum(item["analyzed"] for item in summaries),
        "skipped": sum(item["skipped"] for item in summaries),
        "failed": sum(item["failed"] for item in summaries),
    }


# 各年子表的记录日期字段（未关闭看板排序与聊天月份过滤共用）
YEAR_DATE_FIELD = {2025: "发现时间", 2026: "提交时间"}

# 飞书毫秒时间戳为用户时区（东八区）语义；按本地时区解析在 UTC 容器下会少一天
# （先例：a8bba08 合同同步时区修复）
_CHINA_TZ = ZoneInfo("Asia/Shanghai")


def record_date_millis(item: dict[str, Any], year: int) -> int | None:
    """取记录日期毫秒值（飞书 DateTime/CreatedTime 为 ms 数字或数字字符串）。"""
    field = YEAR_DATE_FIELD.get(year)
    if not field:
        return None
    value = item.get(field)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip()
    if text.isdigit():
        return int(text)
    return None


def _has_investigation_report(item: dict[str, Any]) -> bool:
    """调查结果说明（附件字段）是否有内容——未关闭看板分流与行标签共用同一判定。"""
    investigation = item.get("调查结果说明")
    if isinstance(investigation, (list, dict)):
        return bool(investigation)
    if isinstance(investigation, str):
        return bool(investigation.strip())
    return False


def _is_open_record(item: dict[str, Any]) -> bool:
    """未关闭口径（用户确认，2026-09-09 修订）：无调查结果说明 **且** 未结案
    （是否结案≠是）才计入看板；有报告或已结案任占其一，即不算未关闭。"""
    if _field_text(item.get("是否结案")) == "是":
        return False
    return not _has_investigation_report(item)


async def get_dashboard_aggregation(
    db: AsyncSession, year: int | None
) -> dict[str, Any]:
    """仪表盘聚合：记录实时读飞书，分类关联本地缓存，Python 侧聚合。"""
    years = [year] if year in ANALYSIS_YEARS else list(ANALYSIS_YEARS)
    try:
        await get_config("text")
        ai_configured = True
    except LLMConfigError:
        ai_configured = False

    product_type_counter: Counter[tuple[str, str]] = Counter()
    product_counter: Counter[str] = Counter()
    type_counter: Counter[str] = Counter()
    total = 0
    analyzed = 0
    last_analyzed_at: datetime | None = None
    open_count = 0
    by_year_open: dict[int, dict[str, int]] = {}
    open_rows: list[dict[str, Any]] = []

    for item_year in years:
        try:
            items = await _list_year_items(db, item_year)
        except AppException:
            # 未配置的年份直接跳过，不影响已配置年份的聚合
            continue
        year_open = by_year_open.setdefault(item_year, {"open_count": 0, "total": 0})
        record_ids = [str(item.get("record_id") or "") for item in items]
        cached = await _load_cached_classifications(db, item_year, record_ids)
        for item in items:
            snapshot = _record_snapshot(item, item_year)
            record_id = snapshot["record_id"]
            total += 1
            year_open["total"] += 1
            hint = snapshot["product_hint"]
            previous = cached.get(record_id)
            if (
                previous
                and previous.get("status") == "completed"
                and previous.get("content_hash") == _content_hash(snapshot)
            ):
                payload = previous.get("payload") or {}
                product = str(payload.get("product") or "") or hint or _PRODUCT_FALLBACK
                anomaly_type = (
                    str(payload.get("anomaly_type") or "") or _TYPE_FALLBACK
                )
                analyzed += 1
                created_at = previous.get("created_at")
                if isinstance(created_at, datetime) and (
                    last_analyzed_at is None or created_at > last_analyzed_at
                ):
                    last_analyzed_at = created_at
            else:
                product = hint or "待分析"
                anomaly_type = "待分析"
            product_counter[product] += 1
            type_counter[anomaly_type] += 1
            product_type_counter[(product, anomaly_type)] += 1
            if _is_open_record(item):
                open_count += 1
                year_open["open_count"] += 1
                date_millis = record_date_millis(item, item_year)
                open_rows.append(
                    {
                        "id": record_id,
                        "year": item_year,
                        "date": (
                            datetime.fromtimestamp(
                                date_millis / 1000, tz=_CHINA_TZ
                            ).strftime("%Y-%m-%d")
                            if date_millis
                            else ""
                        ),
                        "date_millis": date_millis or 0,
                        "product": product,
                        "anomaly_type": anomaly_type,
                        "desc": snapshot["desc"][:200],
                    }
                )
    open_rows.sort(key=lambda row: row["date_millis"], reverse=True)
    for row in open_rows:
        row.pop("date_millis", None)

    products = [
        {
            "product": product,
            "count": count,
            "types": [
                {"type": anomaly_type, "count": type_count}
                for (inner_product, anomaly_type), type_count in sorted(
                    product_type_counter.items(), key=lambda pair: -pair[1]
                )
                if inner_product == product
            ],
        }
        for product, count in product_counter.most_common()
    ]
    type_totals = [
        {"type": anomaly_type, "count": count}
        for anomaly_type, count in type_counter.most_common()
    ]
    return {
        "years": years,
        "total": total,
        "analyzed": analyzed,
        "unclassified": total - analyzed,
        "ai_configured": ai_configured,
        "last_analyzed_at": last_analyzed_at.isoformat() if last_analyzed_at else None,
        "products": products,
        "type_totals": type_totals,
        "open_count": open_count,
        "by_year_open": [
            {"year": year, "open_count": stat["open_count"], "total": stat["total"]}
            for year, stat in sorted(by_year_open.items())
        ],
        "open_recent": open_rows[:_OPEN_RECENT_LIMIT],
    }


_OPEN_RECENT_LIMIT = 500


class ClassificationExportRow(TypedDict):
    year: int
    record_id: str
    content_hash: str
    product: str
    anomaly_type: str
    reason: str
    model_name: str


async def export_classifications(db: AsyncSession) -> dict[str, Any]:
    """导出全部已完成的成品异常分类结果（每记录取最新一条），供环境间搬运。"""
    result = await db.execute(
        select(QualityAiAnalysisLog)
        .where(
            QualityAiAnalysisLog.entity_type == ENTITY_TYPE,
            QualityAiAnalysisLog.status == "completed",
        )
        .order_by(QualityAiAnalysisLog.created_at.desc())
    )
    rows: list[ClassificationExportRow] = []
    seen: set[uuid.UUID] = set()
    for log in result.scalars().all():
        if log.entity_id in seen:
            continue
        seen.add(log.entity_id)
        snapshot = log.input_snapshot or {}
        payload = log.output_payload or {}
        if not payload.get("anomaly_type"):
            continue
        rows.append(
            {
                "year": int(snapshot.get("year") or 0),
                "record_id": str(snapshot.get("record_id") or ""),
                "content_hash": str(snapshot.get("content_hash") or ""),
                "product": str(payload.get("product") or ""),
                "anomaly_type": str(payload.get("anomaly_type") or ""),
                "reason": str(payload.get("reason") or ""),
                "model_name": log.model_name,
            }
        )
    return {
        "entity_type": ENTITY_TYPE,
        "exported_at": datetime.now(UTC).isoformat(),
        "count": len(rows),
        "rows": rows,
    }


_MAX_IMPORT_ROWS = 1000


async def import_classifications_from_rows(
    db: AsyncSession, payload_rows: list[dict[str, Any]]
) -> dict[str, int]:
    """导入分类结果（幂等）：本环境已有 completed 分类的记录直接跳过（不覆盖）。

    导入行的 content_hash 原样携带（由源环境按同一快照算法算得），保证导入后
    classify_year/看板 的去重判定命中、不触发 AI 重跑；行未带 hash 时以行内快照
    重算兜底（仅对手工附快照字段的行有效，标准导出行必须带 hash）。
    """
    if not isinstance(payload_rows, list):
        raise AppException(message="导入数据格式错误：rows 必须是数组", status_code=400)
    if len(payload_rows) > _MAX_IMPORT_ROWS:
        raise AppException(
            message=f"单批导入行数不能超过 {_MAX_IMPORT_ROWS}", status_code=400
        )
    existing = await db.execute(
        select(QualityAiAnalysisLog.entity_id).where(
            QualityAiAnalysisLog.entity_type == ENTITY_TYPE,
            QualityAiAnalysisLog.status == "completed",
        )
    )
    existing_keys = set(existing.scalars().all())
    imported = 0
    skipped = 0
    for raw in payload_rows:
        if not isinstance(raw, dict):
            raise AppException(
                message="导入数据格式错误：行必须是对象", status_code=400
            )
        year_value = raw.get("year")
        record_id = str(raw.get("record_id") or "").strip()
        anomaly_type = str(raw.get("anomaly_type") or "").strip()
        if (
            not isinstance(year_value, int)
            or year_value not in ANALYSIS_YEARS
            or not record_id
            or not anomaly_type
        ):
            raise AppException(
                message=f"导入行缺少必要字段或年份不支持: {record_id or '(无记录ID)'}",
                status_code=400,
            )
        entity_uuid = _entity_uuid(year_value, record_id)
        if entity_uuid in existing_keys:
            skipped += 1
            continue
        snapshot = {
            "year": year_value,
            "record_id": record_id,
            "desc": str(raw.get("desc") or ""),
            "product_hint": str(raw.get("product_hint") or ""),
            "source": str(raw.get("source") or ""),
        }
        content_hash = str(raw.get("content_hash") or "") or _content_hash(snapshot)
        db.add(
            QualityAiAnalysisLog(
                entity_type=ENTITY_TYPE,
                entity_id=entity_uuid,
                analysis_type=ANALYSIS_TYPE,
                input_snapshot={**snapshot, "content_hash": content_hash},
                output_payload={
                    "product": str(raw.get("product") or ""),
                    "anomaly_type": anomaly_type,
                    "reason": str(raw.get("reason") or ""),
                },
                model_name=str(raw.get("model_name") or "imported")[:128],
                status="completed",
            )
        )
        existing_keys.add(entity_uuid)
        imported += 1
    await db.commit()
    return {"imported": imported, "skipped": skipped}
