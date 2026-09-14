"""Centralized filter rules for regulatory tracker crawler records."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlparse

from app.modules.regulatory_tracker.crawler.types import CrawledRegulationRecord

# 排除内容（用户要求）：医疗器械、中药、生物制品、抗肿瘤药物、儿童用药、
# 罕见病、新药/创新药、生物类似药、临床试验、疫苗。
# 每条均覆盖常见中英文变体（单复数、法规正式用语、缩写），匹配时统一转小写
# 子串匹配，避免因同义表达漏判；同时禁止出现超宽泛词（如 device、child、
# orphan 单独出现），防止误伤正常原料药/质量类文件。
EXCLUDED_KEYWORDS: tuple[str, ...] = (
    # 1. 医疗器械 / IVD
    "医疗器械",
    "医用器械",
    "体外诊断",
    "medical device",
    "medical devices",
    "medical-device",
    "in vitro diagnostic",
    "in-vitro diagnostic",
    "ivd",
    # 2. 中药 / 植物药
    "中药",
    "中药材",
    "中草药",
    "中医药",
    "天然药物",
    "植物药",
    "traditional chinese medicine",
    "chinese herbal",
    "herbal medicine",
    "herbal medicines",
    "botanical drug",
    "botanical drugs",
    "phytomedicine",
    "phytomedicines",
    # 3. 生物制品（含血液制品、细胞/基因治疗等先进疗法）
    "生物制品",
    "生物制剂",
    "血液制品",
    "细胞治疗",
    "基因治疗",
    "advanced therapy medicinal product",
    "advanced therapy medicinal products",
    "atmp",
    "atmps",
    "biologic",
    "biologics",
    "biological",
    "biological product",
    "biological products",
    "biologicals",
    "blood product",
    "blood products",
    "cell therapy",
    "gene therapy",
    "somatic cell",
    "tissue engineered",
    # 4. 抗肿瘤药物
    "抗肿瘤",
    "抗肿瘤药",
    "抗肿瘤药物",
    "抗癌",
    "肿瘤药",
    "anti-tumor",
    "antitumor",
    "anti-cancer",
    "anticancer",
    "anti cancer",
    "oncology",
    "oncologic",
    "neoplasm",
    "cancer therapy",
    "tumour",
    # 5. 儿童用药
    "儿童用药",
    "儿童",
    "儿科",
    "小儿",
    "新生儿",
    "pediatric",
    "paediatric",
    "pediatrics",
    "paediatrics",
    "pediatric drug",
    "paediatric drug",
    "pediatric medicines",
    "paediatric medicines",
    "neonatal",
    "neonate",
    "infant",
    "juvenile",
    # 6. 罕见病 / 孤儿药
    "罕见病",
    "罕见疾病",
    "孤儿药",
    "rare disease",
    "rare diseases",
    "rare disorder",
    "rare disorders",
    "orphan drug",
    "orphan drugs",
    "orphan medicinal product",
    "orphan medicinal products",
    "ultrarare",
    "ultra-rare",
    # 7. 新药 / 创新药
    "新药",
    "创新药",
    "首创药",
    "新分子实体",
    "new drug",
    "new drugs",
    "innovative drug",
    "innovative drugs",
    "novel drug",
    "novel drugs",
    "first-in-class",
    "new molecular entity",
    "new molecular entities",
    "nme",
    # 8. 生物类似药
    "生物类似药",
    "生物类似",
    "类似药",
    "biosimilar",
    "biosimilars",
    "biosimilarity",
    "similar biological",
    # 9. 临床试验（含 EU 正式用语 clinical investigation / IMP / FIH）
    "临床试验",
    "临床调查",
    "临床研究",
    "临床实验",
    "临床探究",
    "clinical trial",
    "clinical trials",
    "clinical investigation",
    "clinical investigations",
    "clinical study",
    "clinical studies",
    "clinical research",
    "investigational medicinal product",
    "investigational medicinal products",
    "investigational drug",
    "investigational drugs",
    "investigational new drug",
    "first-in-human",
    "first in human",
    "fih",
    "imp",
    # 10. 疫苗
    "疫苗",
    "免疫接种",
    "vaccine",
    "vaccines",
    "vaccination",
    "immunization",
    "immunisation",
)

TARGET_KEYWORDS: tuple[str, ...] = (
    "化学",
    "原料药",
    "api",
    "active pharmaceutical ingredient",
    "兽药",
    "veterinary",
    "药典",
    "pharmacopoeia",
    "pharmacopeia",
    "指导原则",
    "guideline",
    "guidance",
    "drug master file",
    "drug substance",
    "excipient",
    "packaging material",
    "container closure",
    "quality",
    "chemistry manufacturing and controls",
)

OFFICIAL_SITE_DOMAINS: dict[str, tuple[str, ...]] = {
    "nmpa": ("nmpa.gov.cn",),
    "cde": ("cde.org.cn",),
    "cfdi": ("cfdi.org.cn", "cfdi.nmpa.gov.cn"),
    "moa": ("moa.gov.cn",),
    "ivdc": ("ivdc.org.cn",),
    "fda": ("fda.gov",),
    "ema": ("ema.europa.eu",),
    "edqm": ("edqm.eu",),
    "eurlex": ("eur-lex.europa.eu",),
    "ich": ("ich.org",),
    "who": ("who.int",),
}


def is_official_site_url(url: str | None, site_code: str | None = None) -> bool:
    """Return whether the given URL belongs to an official regulatory site."""
    if not url:
        return False

    try:
        host = urlparse(url).hostname
    except ValueError:
        return False

    if not host:
        return False

    normalized_host = host.lower()
    expected_domains = OFFICIAL_SITE_DOMAINS.get((site_code or "").lower())
    if expected_domains:
        return _host_matches_domains(normalized_host, expected_domains)

    return any(
        _host_matches_domains(normalized_host, domains)
        for domains in OFFICIAL_SITE_DOMAINS.values()
    )


def is_recent_publish_date(
    publish_date: date | None,
    recent_days: int,
    reference_date: date | None = None,
) -> bool:
    """Return whether the publish date falls within the recent-day window."""
    if publish_date is None or recent_days < 1:
        return False

    today = reference_date or date.today()
    earliest_date = today - timedelta(days=recent_days - 1)
    return earliest_date <= publish_date <= today


def filter_record(
    record: CrawledRegulationRecord | Mapping[str, Any],
    recent_days: int,
    reference_date: date | None = None,
) -> tuple[bool, str]:
    """Apply centralized filter rules to a crawled regulation record."""
    site_code = _get_record_value(record, "source_site") or _get_record_value(
        record, "source_site_code"
    )
    original_url = _get_record_value(record, "original_url") or _get_record_value(
        record, "source_url"
    )
    publish_date = _get_record_value(record, "publish_date")
    search_text = _build_search_text(record)

    if not is_official_site_url(original_url, site_code):
        return False, "unofficial_url"

    if not is_recent_publish_date(publish_date, recent_days, reference_date):
        return False, "not_recent"

    excluded_keyword = _find_keyword(search_text, EXCLUDED_KEYWORDS)
    if excluded_keyword is not None:
        return False, f"excluded_keyword:{excluded_keyword}"

    if _find_keyword(search_text, TARGET_KEYWORDS) is None:
        return False, "not_target_scope"

    return True, "accepted"


def _host_matches_domains(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def _get_record_value(
    record: CrawledRegulationRecord | Mapping[str, Any],
    field_name: str,
) -> Any:
    if isinstance(record, Mapping):
        return record.get(field_name)
    return getattr(record, field_name, None)


def _build_search_text(record: CrawledRegulationRecord | Mapping[str, Any]) -> str:
    values: list[str] = []
    for field_name in ("title", "classification", "summary"):
        value = _get_record_value(record, field_name)
        if isinstance(value, str) and value:
            values.append(value)

    raw_data = _get_record_value(record, "raw_data")
    if raw_data is not None:
        values.extend(_flatten_text_values(raw_data))

    return "\n".join(values).lower()


def _flatten_text_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        flattened: list[str] = []
        for item in value.values():
            flattened.extend(_flatten_text_values(item))
        return flattened
    if isinstance(value, (list, tuple, set)):
        flattened = []
        for item in value:
            flattened.extend(_flatten_text_values(item))
        return flattened
    return []


def _match_keyword(text: str, keyword: str) -> bool:
    """单个关键词匹配：短 ASCII 缩写按整词匹配，其余按子串匹配。

    短缩写（imp/ivd/fih/nme/atmp/api 等）若按子串匹配会命中
    important、capital 等无关单词，导致大量正常文件被误拒；
    这里仅对 ≤4 位的纯英文缩写启用 \\b 词边界。
    """
    if len(keyword) <= 4 and re.fullmatch(r"[a-z0-9]+", keyword):
        return re.search(rf"\b{re.escape(keyword)}\b", text) is not None
    return keyword in text


def _find_keyword(text: str, keywords: tuple[str, ...]) -> str | None:
    for keyword in keywords:
        if _match_keyword(text, keyword):
            return keyword
    return None
