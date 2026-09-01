"""Primary sync flow for regulatory tracker site registry ingestion."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.regulatory_tracker import repository as repo
from app.modules.regulatory_tracker.crawler.site_registry import (
    SITE_REGISTRY,
    create_site_adapter,
    get_site_registry_entry,
)
from app.modules.regulatory_tracker.crawler.types import CrawledRegulationRecord
from app.modules.regulatory_tracker.models import DataChannel, DataSource
from app.modules.regulatory_tracker.services import filter_service
from app.modules.regulatory_tracker.services.content_summary_service import (
    generate_short_summary,
)

logger = logging.getLogger(__name__)

# 站点级并发与硬超时：一站卡死不再拖垮整轮抓取（用户确认：5 分钟保险上限）
SITE_SYNC_CONCURRENCY = 4
SITE_SYNC_TIMEOUT_SECONDS = 300

SITE_NAME_CN_MAP: dict[str, str] = {
    "U.S. Food and Drug Administration": "美国食品药品监督管理局",
    "European Medicines Agency": "欧洲药品管理局",
    "International Council for Harmonisation": "国际人用药品注册技术协调会",
    "European Directorate for the Quality of Medicines & HealthCare": (
        "欧洲药品质量管理局"
    ),
    "EUR-Lex": "欧盟法规数据库",
    "World Health Organization": "世界卫生组织",
}


class TrackerSyncService:
    """Run the registry-based ingestion flow for crawler adapters."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        recent_days: int = 2,
        reference_date: date | None = None,
    ) -> None:
        self.db = db
        self.recent_days = recent_days
        self.reference_date = reference_date

    async def run_all_sites(
        self,
        *,
        site_targets: Mapping[str, tuple[DataSource, DataChannel]] | None = None,
    ) -> dict[str, Any]:
        """并发遍历所有注册站点并聚合同步结果。

        站点间并发执行（最多 ``SITE_SYNC_CONCURRENCY`` 个），
        单站总时长超过 ``SITE_SYNC_TIMEOUT_SECONDS`` 即记为失败并跳过，
        不影响其他站点。
        """
        semaphore = asyncio.Semaphore(SITE_SYNC_CONCURRENCY)

        async def run_one(site_code: str) -> dict[str, Any]:
            source: DataSource | None = None
            channel: DataChannel | None = None
            if site_targets and site_code in site_targets:
                source, channel = site_targets[site_code]

            async with semaphore:
                try:
                    return await asyncio.wait_for(
                        self.run_site(
                            site_code,
                            source=source,
                            channel=channel,
                        ),
                        timeout=SITE_SYNC_TIMEOUT_SECONDS,
                    )
                except TimeoutError:
                    logger.warning(
                        "同步站点超时: %s（超过 %ds 硬上限）",
                        site_code,
                        SITE_SYNC_TIMEOUT_SECONDS,
                    )
                    return {
                        "site_code": site_code,
                        "site_name": get_site_registry_entry(site_code).site_name,
                        "totals": self._empty_totals(),
                        "rejection_reasons": {},
                        "changed_document_ids": [],
                        "error": f"站点抓取超时（{SITE_SYNC_TIMEOUT_SECONDS}s）",
                    }
                except Exception as exc:
                    logger.exception("同步站点失败: %s", site_code)
                    return {
                        "site_code": site_code,
                        "site_name": get_site_registry_entry(site_code).site_name,
                        "totals": self._empty_totals(),
                        "rejection_reasons": {},
                        "changed_document_ids": [],
                        "error": str(exc),
                    }

        site_results = await asyncio.gather(
            *(run_one(site_code) for site_code in SITE_REGISTRY)
        )

        totals = self._empty_totals()
        changed_document_ids: list[str] = []
        for site_result in site_results:
            self._merge_totals(totals, site_result["totals"])
            changed_document_ids.extend(site_result.get("changed_document_ids", []))

        return {
            "totals": totals,
            "sites": site_results,
            "changed_document_ids": changed_document_ids,
        }

    async def run_site(
        self,
        site_code: str,
        *,
        source: DataSource | None = None,
        channel: DataChannel | None = None,
    ) -> dict[str, Any]:
        """Run sync for a single site."""
        entry = get_site_registry_entry(site_code)
        adapter = create_site_adapter(site_code)
        totals = self._empty_totals()
        rejection_reasons: dict[str, int] = {}
        changed_document_ids: list[str] = []

        try:
            records = await adapter.fetch_recent_documents()
        except Exception as exc:
            logger.exception("抓取站点失败: %s", site_code)
            return {
                "site_code": site_code,
                "site_name": entry.site_name,
                "totals": totals,
                "rejection_reasons": rejection_reasons,
                "changed_document_ids": changed_document_ids,
                "error": str(exc),
            }

        for record in records:
            totals["checked"] += 1

            accepted, reason = filter_service.filter_record(
                record,
                recent_days=self.recent_days,
                reference_date=self.reference_date,
            )
            if not accepted:
                totals["rejected"] += 1
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                continue

            if source is None or channel is None:
                raise RuntimeError(
                    f"站点 {site_code} 缺少 source/channel 上下文，无法执行入库"
                )

            totals["accepted"] += 1
            upsert_result = await repo.upsert_document_by_unique_fields(
                self.db,
                await self._build_document_payload(
                    record=record,
                    source=source,
                    channel=channel,
                    site_code=site_code,
                    site_name=entry.site_name,
                    filter_reason=reason,
                ),
            )
            totals[upsert_result.action] += 1
            if upsert_result.action in {"inserted", "updated"}:
                changed_document_ids.append(str(upsert_result.document.id))

        return {
            "site_code": site_code,
            "site_name": entry.site_name,
            "totals": totals,
            "rejection_reasons": rejection_reasons,
            "changed_document_ids": changed_document_ids,
            "error": None,
        }

    async def _build_document_payload(
        self,
        *,
        record: CrawledRegulationRecord,
        source: DataSource,
        channel: DataChannel,
        site_code: str,
        site_name: str,
        filter_reason: str,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        capture_date = self.reference_date or now.date()
        raw_data = self._to_json_compatible(record.raw_data or {})
        version_text = self._derive_version_text(record, raw_data)
        effective_date = self._derive_effective_date(record, raw_data)
        summary_text = await generate_short_summary(
            title=record.title,
            raw_data=dict(raw_data),
            existing_summary=record.summary,
        )
        if not summary_text:
            summary_text = self._derive_summary_text(record, raw_data, site_name)

        payload = {
            "source_id": source.id,
            "channel_id": channel.id,
            "document_id": record.document_id
            or self._build_fallback_document_id(record),
            "title": record.title,
            "publish_date": record.publish_date,
            "status_text": self._pick_text(raw_data, "status_text", "status"),
            "classification": self._pick_text(raw_data, "classification"),
            "source_site_code": site_code,
            "source_site_name": site_name,
            "source_url": record.original_url,
            "version_text": version_text,
            "effective_date": effective_date,
            "summary_text": summary_text,
            "capture_date": capture_date,
            "filter_status": "accepted",
            "filter_reason": filter_reason,
            "original_url": record.original_url,
            "is_new": True,
            "first_found_at": now,
            "last_checked_at": now,
            "raw_data": raw_data,
        }
        payload["content_hash"] = repo.build_document_content_hash(payload)
        return payload

    @staticmethod
    def _build_fallback_document_id(record: CrawledRegulationRecord) -> str:
        identity = "|".join(
            [
                record.source_site,
                record.title,
                record.publish_date.isoformat() if record.publish_date else "",
                record.original_url,
            ]
        )
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    @staticmethod
    def _pick_text(raw_data: Mapping[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = raw_data.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    @staticmethod
    def _contains_cjk(text: str | None) -> bool:
        if not text:
            return False
        return bool(re.search(r"[\u4e00-\u9fff]", text))

    @classmethod
    def _localize_site_name(cls, site_name: str) -> str:
        return SITE_NAME_CN_MAP.get(site_name, site_name)

    @classmethod
    def _localize_classification(cls, classification: str | None) -> str | None:
        if not classification:
            return None

        normalized = classification.strip()
        replacements = (
            ("Scientific guideline", "技术指导原则"),
            ("ICH guideline news", "ICH 指导原则动态"),
            ("Generic Drugs", "仿制药"),
            ("Human", "人用药"),
            ("Veterinary", "兽药"),
            ("quality", "质量"),
            ("Quality", "质量"),
            ("guideline", "指导原则"),
            ("Guideline", "指导原则"),
            ("guidance", "指导文件"),
            ("Guidance", "指导文件"),
            ("good manufacturing practice", "药品生产质量管理规范"),
            ("Good Manufacturing Practice", "药品生产质量管理规范"),
            ("good distribution practice", "药品经营质量管理规范"),
            ("Good Distribution Practice", "药品经营质量管理规范"),
            ("regulatory", "法规"),
            ("Regulatory", "法规"),
        )
        for source, target in replacements:
            normalized = normalized.replace(source, target)

        normalized = re.sub(r"\s*;\s*", "、", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip(" 、")
        return normalized or None

    @staticmethod
    def _to_json_compatible(value: Any) -> Any:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, Mapping):
            return {
                str(key): TrackerSyncService._to_json_compatible(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [TrackerSyncService._to_json_compatible(item) for item in value]
        if isinstance(value, tuple):
            return [TrackerSyncService._to_json_compatible(item) for item in value]
        if isinstance(value, set):
            return [
                TrackerSyncService._to_json_compatible(item)
                for item in sorted(value, key=str)
            ]
        return value

    @staticmethod
    def _build_text_blob(
        record: CrawledRegulationRecord, raw_data: Mapping[str, Any]
    ) -> str:
        parts: list[str] = []
        if record.title:
            parts.append(record.title)
        if record.summary:
            parts.append(record.summary)

        for key in (
            "detail_excerpt",
            "detail_content",
            "content_text",
            "body_text",
            "contentSummary",
            "summary",
            "detail_title",
            "list_text",
        ):
            value = raw_data.get(key)
            if isinstance(value, str) and value:
                parts.append(value)
            elif isinstance(value, list):
                parts.extend(item for item in value if isinstance(item, str) and item)

        normalized_record = raw_data.get("normalized_record")
        if isinstance(normalized_record, Mapping):
            nested_raw = normalized_record.get("raw_data")
            if isinstance(nested_raw, Mapping):
                for value in nested_raw.values():
                    if isinstance(value, str) and value:
                        parts.append(value)

        return "\n".join(parts)

    @classmethod
    def _derive_version_text(
        cls,
        record: CrawledRegulationRecord,
        raw_data: Mapping[str, Any],
    ) -> str | None:
        if record.version:
            return record.version

        text = cls._build_text_blob(record, raw_data)
        patterns = (
            r"(药监[\u4e00-\u9fa5A-Za-z]*〔\d{4}〕\d+号)",
            r"(公告[（(]\d{4}年?第\d+号[）)])",
            r"(〔\d{4}〕\d+号)",
            r"(（[^）]*(?:年版|修订版|试行|征求意见稿)[^）]*）)",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    @classmethod
    def _derive_effective_date(
        cls,
        record: CrawledRegulationRecord,
        raw_data: Mapping[str, Any],
    ) -> date | None:
        if record.effective_date is not None:
            return record.effective_date

        text = cls._build_text_blob(record, raw_data)
        patterns = (
            r"(?:生效日期|施行日期)[:：]?\s*(\d{4}[年/-]\d{1,2}[月/-]\d{1,2}日?)",
            r"自\s*(\d{4}[年/-]\d{1,2}[月/-]\d{1,2}日?)\s*起?(?:施行|执行|实施)",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                parsed = cls._parse_date_like_text(match.group(1))
                if parsed is not None:
                    return parsed

        if "自发布之日起" in text and record.publish_date is not None:
            return record.publish_date
        return None

    @classmethod
    def _derive_summary_text(
        cls,
        record: CrawledRegulationRecord,
        raw_data: Mapping[str, Any],
        site_name: str,
    ) -> str | None:
        if record.summary and cls._contains_cjk(record.summary):
            return record.summary

        excerpt = raw_data.get("detail_excerpt")
        if isinstance(excerpt, str) and excerpt:
            summary = cls._summarize_excerpt(excerpt, record.title)
            if summary and cls._contains_cjk(summary):
                return summary

        detail_content = raw_data.get("detail_content")
        if isinstance(detail_content, str) and detail_content:
            summary = cls._summarize_excerpt(detail_content, record.title)
            if summary and cls._contains_cjk(summary):
                return summary

        detail_paragraphs = raw_data.get("detail_paragraphs")
        if isinstance(detail_paragraphs, list):
            paragraph_text = "；".join(
                item.strip()
                for item in detail_paragraphs
                if isinstance(item, str) and item.strip()
            )
            if paragraph_text:
                summary = cls._summarize_excerpt(paragraph_text, record.title)
                if summary and cls._contains_cjk(summary):
                    return summary

        classification = cls._localize_classification(
            cls._pick_text(raw_data, "classification")
        )
        localized_site_name = cls._localize_site_name(site_name)
        publish_part = (
            f"，发布日期为{record.publish_date.isoformat()}"
            if record.publish_date
            else ""
        )
        classification_part = (
            f"{classification}相关" if classification else "法规/指导原则"
        )
        return (
            f"{localized_site_name}发布的{classification_part}文件《{record.title}》"
            f"{publish_part}，系统已完成抓取整理。"
        )

    @staticmethod
    def _summarize_excerpt(excerpt: str, title: str) -> str | None:
        text = re.sub(r"\s+", " ", excerpt).strip()
        if not text:
            return None

        if title and title in text:
            text = text[text.index(title) + len(title) :].strip()

        text = re.sub(
            r"^.*?发布时间[:：]\s*\d{4}[-年/]\d{1,2}[-月/]\d{1,2}日?", "", text
        )
        text = re.sub(r"^各[\u4e00-\u9fa5、，,]{2,80}[:：]?", "", text).strip(
            " ：:;，,"
        )
        text = re.sub(r"^为贯彻落实[^，。；]*[，,]", "", text).strip()
        text = re.sub(r"^现(?:将|印发|发布)", "", text).strip(" ，。；")
        if not text:
            return None

        sentences = re.split(r"[。；!！?？]", text)
        normalized = [
            sentence.strip(" ，,;；")
            for sentence in sentences
            if sentence.strip(" ，,;；")
        ]
        if not normalized:
            return None

        return "；".join(normalized[:2])[:100]

    @staticmethod
    def _parse_date_like_text(value: str | None) -> date | None:
        if not value:
            return None
        match = re.search(r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?", value)
        if not match:
            return None
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None

    @staticmethod
    def _empty_totals() -> dict[str, int]:
        return {
            "checked": 0,
            "accepted": 0,
            "inserted": 0,
            "updated": 0,
            "unchanged": 0,
            "rejected": 0,
        }

    @staticmethod
    def _merge_totals(target: dict[str, int], incoming: Mapping[str, int]) -> None:
        for key in target:
            target[key] += incoming.get(key, 0)
