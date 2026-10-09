"""EHS 法规雷达编排。

流程：
1. 抓取各来源站点栏目页（crawler 层）→ 权威清单（名称/日期/链接/标准号）
2. 与飞书表格现有记录按「法规名称」比对（名称稳定，版本会变）
3. 分类产出：新法规 / 已修订（日期更新）/ 链接失效需修复
4. AI 做相关性过滤与结构化（输出经 Pydantic 校验）
5. 新法规写入飞书表格；版本变化与链接修复提示到批次
6. 记录扫描批次，供页面顶部提示

设计要点：
- 名称匹配是核心（用户实测：法规名称基本不变，只有版本/日期变）
- 标准号通道（国标全文公开）返回现行/废止，是版本检测的权威依据
- 全程只读本地库；仅「新法规」会写入飞书表格，且可干跑预演
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urljoin

import httpx
from lxml import html  # type: ignore[import-untyped]
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.safety.crawler import (
    CrawledRegulation,
    column_specs,
    fetch_column_items,
)
from app.modules.safety.crawler.column import (
    BASE_HEADERS as _CRAWL_HEADERS,
)
from app.modules.safety.crawler.column import (
    decode_response,
)
from app.modules.safety.crawler.specs import STANDARD_SEARCH_SITE as _STD_SITE
from app.modules.safety.crawler.specs import SiteSpec
from app.modules.safety.crawler.standard import search_standard
from app.modules.safety.crawler.types import CrawlResult, core_name
from app.modules.safety.feishu.bitable_client import SafetyBitableClient
from app.modules.safety.models import (
    RegulationRadarRun,
    SafetyFeishuAppSettings,
    SafetyKnowledgeArticle,
)

logger = logging.getLogger(__name__)

# 单批最多写入飞书表格的新法规数（防异常批量灌入）
MAX_NEW_PER_RUN = 20
# 附件下载上限（字节）；详情页附件链接识别
ATTACHMENT_MAX_BYTES = 20 * 1024 * 1024
ATTACH_HREF_RE = re.compile(r"\.(pdf|docx?|xlsx?|wps)(?:[?#]|$)", re.IGNORECASE)
ATTACH_TEXT_RE = re.compile(r"附件|原文|全文|下载|PDF", re.IGNORECASE)
# 判定为「新法规」的发布日期窗口（天）：超出窗口的历史条目不入库，只提示
NEW_ITEM_WINDOW_DAYS = 730


@dataclass(slots=True)
class RadarOutcome:
    """一次扫描的产出（与批次表字段对应）。"""

    sites_total: int = 0
    sites_failed: int = 0
    found_count: int = 0
    new_count: int = 0
    revised_count: int = 0
    link_fixed_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    items: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _norm_key(title: str) -> str:
    """名称匹配键：去标准号/年份/标点后的小写核心串。"""
    return core_name(title).lower()


def _build_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """按核心名称建立索引，用于名称匹配。"""
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _norm_key(str(row.get("name") or ""))
        if len(key) >= 4:
            index.setdefault(key, row)
    return index


def _find_match(
    item: CrawledRegulation, index: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    """名称精确匹配优先，其次做包含匹配（长度足够时才允许）。"""
    key = _norm_key(item.title)
    if len(key) < 4:
        return None
    hit = index.get(key)
    if hit:
        return hit
    if len(key) >= 8:
        for k, row in index.items():
            if k == key or (len(k) >= 8 and (k in key or key in k)):
                return row
    return None


def _parse_row_date(value: Any) -> date | None:
    """把飞书日期（毫秒时间戳）或 ISO 字符串解析为 date。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value / 1000, tz=UTC).date()
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(value, str):
        m = re.search(r"(20\d{2})-(\d{1,2})-(\d{1,2})", value)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                return None
    return None


async def _load_settings(db: AsyncSession) -> SafetyFeishuAppSettings:
    row = (
        await db.execute(
            select(SafetyFeishuAppSettings)
            .where(SafetyFeishuAppSettings.is_deleted.is_(False))
            .order_by(SafetyFeishuAppSettings.updated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise AppException(
            message=(
                "请先在 安全管理 → 系统配置 → 飞书设置 "
                "保存应用凭证与 EHS 法规库绑定"
            )
        )
    if not (row.knowledge_app_token or "").strip() or not (
        row.knowledge_table_id or ""
    ).strip():
        raise AppException(
        message="请先在 飞书设置 中配置 EHS 法规库的 App Token 与 Table ID"
    )
    return row


def _table_row(raw: dict[str, Any]) -> dict[str, Any]:
    """把飞书记录字段规整为比对所需结构。"""

    def txt(value: Any) -> str:
        if isinstance(value, list):
            return "".join(
                s.get("text", "") for s in value if isinstance(s, dict)
            )
        if isinstance(value, dict):
            return str(value.get("link") or value.get("text") or "")
        return str(value or "")

    fields = raw.get("fields") or {}
    return {
        "record_id": raw.get("record_id", ""),
        "no": txt(fields.get("法规编号")),
        "name": txt(fields.get("法律法规及标准名称")),
        "category": txt(fields.get("法规类别")),
        "issuer": txt(fields.get("颁布机关")),
        "status": txt(fields.get("法规状态")),
        "link": txt(fields.get("法规链接")).strip(),
        "promulgation_date": fields.get("颁布修订日期"),
        "implement_date": fields.get("实施日期"),
    }


async def fetch_table_rows(
    client: SafetyBitableClient, table_id: str
) -> list[dict[str, Any]]:
    """读取飞书表格全部记录（只读）。"""
    records = await client.search_records(table_id=table_id, page_size=500)
    return [_table_row(r) for r in records]


async def collect_all_sites(
    specs: tuple[SiteSpec, ...] | None = None,
) -> tuple[list[CrawledRegulation], RadarOutcome]:
    """并发抓取全部栏目站点，单站失败隔离。"""
    specs = specs or column_specs()
    outcome = RadarOutcome(sites_total=len(specs))
    items: list[CrawledRegulation] = []

    results = await _gather_sites(specs)
    for res in results:
        if res.ok:
            items.extend(res.items)
        else:
            outcome.sites_failed += 1
            outcome.errors.append(f"{res.site_name}: {res.error}")
            logger.warning("雷达站点抓取失败 %s: %s", res.site_name, res.error)
    outcome.found_count = len(items)
    return items, outcome


async def _gather_sites(specs: tuple[SiteSpec, ...]) -> list[CrawlResult]:
    import asyncio

    sem = asyncio.Semaphore(3)

    async def one(spec: SiteSpec) -> CrawlResult:
        async with sem:
            return await fetch_column_items(spec)

    return list(await asyncio.gather(*[one(s) for s in specs]))


async def run_radar(
    db: AsyncSession,
    *,
    dry_run: bool = False,
    trigger: str = "manual",
) -> dict[str, Any]:
    """执行一次法规雷达扫描。

    dry_run=True 时只比对与分类，不写入飞书表格，用于上线前验证。
    """
    settings = await _load_settings(db)
    app_token = (settings.knowledge_app_token or "").strip()
    table_id = (settings.knowledge_table_id or "").strip()
    if not settings.is_enabled:
        raise AppException(message="安全模块飞书集成未启用，请先在 飞书设置 中启用")

    run = RegulationRadarRun(
        started_at=datetime.now(UTC),
        status="running",
        trigger=trigger,
        dry_run=dry_run,
    )
    db.add(run)
    await db.commit()

    client = SafetyBitableClient(app_token=app_token, table_id=table_id)
    try:
        table_rows = await fetch_table_rows(client, table_id)
        items, outcome = await collect_all_sites()
        version_changes = await check_standard_versions(db, limit=20)
        outcome.revised_count += len(version_changes)
        outcome.items.extend(version_changes)

        index = _build_index(table_rows)
        seen_keys: set[str] = set()
        candidates: list[tuple[CrawledRegulation, dict[str, Any]]] = []

        for item in items:
            key = _norm_key(item.title)
            if not key or key in seen_keys:
                outcome.skipped_count += 1
                continue
            seen_keys.add(key)

            matched = _find_match(item, index)
            if matched:
                # 已有该法规：核对日期是否更新（= 已修订）
                # 实施日期语义的栏目（标准库）不参与比较，避免把实施日期
                # 当成发布日期而误报「已修订」
                old_date = _parse_row_date(matched.get("promulgation_date"))
                if (
                    item.date_semantics == "publish"
                    and item.publish_date
                    and old_date
                    and item.publish_date > old_date
                    and item.publish_date <= date.today()
                ):
                    outcome.revised_count += 1
                    # 直接更新表格对应列（颁布修订日期 + 法规链接）
                    record_id = matched.get("record_id")
                    if record_id and not dry_run:
                        new_ms = int(
                            datetime.combine(
                                item.publish_date,
                                datetime.min.time(),
                                tzinfo=UTC,
                            ).timestamp()
                            * 1000
                        )
                        await client.update_record(
                            record_id,
                            {
                                "颁布修订日期": new_ms,
                                "法规链接": {
                                    "link": item.url,
                                    "text": "官方来源",
                                },
                            },
                        )
                        await db.execute(
                            update(SafetyKnowledgeArticle)
                            .where(
                                SafetyKnowledgeArticle.feishu_record_id
                                == record_id
                            )
                            .values(
                                promulgation_date=datetime.combine(
                                    item.publish_date,
                                    datetime.min.time(),
                                    tzinfo=UTC,
                                ),
                                regulation_link=item.url,
                            )
                        )
                    outcome.items.append(
                        {
                            "action": "revised",
                            "name": matched.get("name") or item.title,
                            "old_date": old_date.isoformat(),
                            "new_date": item.publish_date.isoformat(),
                            "url": item.url,
                            "site": item.site_name,
                            "table_updated": bool(record_id) and not dry_run,
                        }
                    )
                else:
                    outcome.skipped_count += 1
                continue

            # 未匹配到：候选新法规（受发布日期窗口约束）
            if item.publish_date is None or item.date_semantics != "publish":
                outcome.skipped_count += 1
                continue
            age_days = (date.today() - item.publish_date).days
            if age_days > NEW_ITEM_WINDOW_DAYS or age_days < 0:
                outcome.skipped_count += 1
                continue

            candidates.append((item, {}))

        # AI 相关性过滤：只保留与原料药工厂相关的候选，避免污染表格
        # （干跑也执行过滤，预演结果与真实写入一致；干跑仅跳过写入动作）
        if candidates:
            kept, ai_error = await _ai_relevance_filter(
                [it.title for it, _ in candidates]
            )
            if ai_error:
                outcome.errors.append(f"AI 相关性过滤不可用：{ai_error}")
                outcome.skipped_count += len(candidates)
                candidates = []
            else:
                filtered = [
                    pair for pair, keep in zip(candidates, kept) if keep
                ]
                outcome.skipped_count += len(candidates) - len(filtered)
                candidates = filtered

        if len(candidates) > MAX_NEW_PER_RUN:
            outcome.skipped_count += len(candidates) - MAX_NEW_PER_RUN
            candidates = candidates[:MAX_NEW_PER_RUN]

        # 顺序编号：沿用表格现有「法规编号」递进（如 163 → 164）
        seq_nos = _next_sequential_nos(table_rows, len(candidates))

        enrichment = httpx.AsyncClient(timeout=40, verify=False)
        try:
            for (item, _meta), seq_no in zip(candidates, seq_nos):
                analysis = await _analyze_regulation(enrichment, item)
                attachment = None
                if not dry_run and item.url:
                    attachment = await _fetch_attachment_for_record(
                        enrichment, item.url, client
                    )
                record_id = None
                if not dry_run:
                    record_id = await _create_in_table(
                        client,
                        table_id,
                        item,
                        outcome,
                        analysis,
                        seq_no=seq_no,
                        attachment_token=attachment,
                    )
                outcome.new_count += 1
                outcome.items.append(
                    {
                        "action": "new",
                        "name": item.title,
                        "no": seq_no,
                        "date": (
                            item.publish_date.isoformat()
                            if item.publish_date
                            else None
                        ),
                        "url": item.url,
                        "site": item.site_name,
                        "standard_no": item.standard_no,
                        "category": (analysis or {}).get("category"),
                        "summary": (analysis or {}).get("summary"),
                        "record_id": record_id,
                    }
                )
        finally:
            await enrichment.aclose()

        # 通知：按设置推送扫描结果（真实扫描且确有发现时）
        if not dry_run and (outcome.new_count or outcome.revised_count):
            summary_lines = _build_summary_lines(outcome.items)
            sent, notify_errors = await send_radar_notifications(
                db,
                summary_lines=summary_lines,
                new_count=outcome.new_count,
                revised_count=outcome.revised_count,
            )
            if sent:
                logger.info("法规雷达通知已发送 %s 条", sent)
            if notify_errors:
                outcome.errors.extend(f"通知：{e}" for e in notify_errors)

        run.finished_at = datetime.now(UTC)
        run.status = "success" if not outcome.errors else "partial"
        run.sites_total = outcome.sites_total
        run.sites_failed = outcome.sites_failed
        run.found_count = outcome.found_count
        run.new_count = outcome.new_count
        run.revised_count = outcome.revised_count
        run.link_fixed_count = outcome.link_fixed_count
        run.skipped_count = outcome.skipped_count
        run.failed_count = outcome.failed_count
        run.items = outcome.items
        run.error_message = "; ".join(outcome.errors[:5]) or None
        await db.commit()
    except Exception as exc:
        await db.rollback()
        run.status = "failed"
        run.finished_at = datetime.now(UTC)
        run.error_message = str(exc)[:500]
        db.add(run)
        await db.commit()
        raise

    return {
        "run_id": str(run.id),
        "dry_run": dry_run,
        "status": run.status,
        "sites_total": outcome.sites_total,
        "sites_failed": outcome.sites_failed,
        "found_count": outcome.found_count,
        "new_count": outcome.new_count,
        "revised_count": outcome.revised_count,
        "skipped_count": outcome.skipped_count,
        "items": outcome.items,
        "errors": outcome.errors,
    }


RELEVANCE_SYSTEM_PROMPT = (
    "你是原料药工厂的 EHS 合规专家。该工厂为化学合成类原料药生产，"
    "涉及危险化学品、发酵、提炼、有机溶剂、锅炉与压力容器、粉尘、噪声、"
    "消防与特种设备。"
    "判断候选法规/标准是否与该工厂的**安全生产**（含职业健康、消防、"
    "特种设备、危化品、特殊作业）**实质相关**。"
    "以下一律判为不相关：环境保护/污染防治/排污许可/危废/温室气体类法规"
    "（归环保模块管理）；表彰/奖励/评优/先进个人类公示；人事任免；"
    "会议纪要；培训通知；无关行业（摩托车/船舶/汽车排放、食品、金融、"
    "教育、旅游等）。征求意见稿、新法规发布、旧法规废止判为相关。"
    "只输出 JSON。"
)


async def _ai_relevance_filter(
    titles: list[str],
) -> tuple[list[bool], str | None]:
    """批量判断候选法规与原料药工厂的相关性。

    返回 (逐条是否保留, 错误信息)。AI 不可用或输出无效时返回全 False 并带错误——
    宁可不写入，也不把无关法规灌进表格。
    """
    if not titles:
        return [], None
    try:
        from app.core.llm import llm_client
        from app.core.llm.exceptions import LLMConfigError, LLMOutputError
    except ImportError as exc:  # pragma: no cover —— 依赖缺失时保守跳过
        return [False] * len(titles), f"LLM 客户端不可用：{exc}"

    listing = "\n".join(f"{i}. {t}" for i, t in enumerate(titles))
    messages = [
        {"role": "system", "content": RELEVANCE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"候选法规清单（共 {len(titles)} 条）：\n{listing}\n\n"
                '按序号返回 JSON：{"results": [{"index": 0, "relevant": true, '
                '"reason": "简短理由"}]}。仅保留与原料药工厂相关的条目。'
            ),
        },
    ]
    try:
        data = await llm_client.chat_json(
            messages, expected_keys=["results"], temperature=0.0
        )
    except LLMConfigError as exc:
        return [False] * len(titles), f"未配置 LLM：{exc}"
    except LLMOutputError as exc:
        return [False] * len(titles), f"LLM 输出无效：{exc}"
    except Exception as exc:  # noqa: BLE001 —— 供应商失败/限流/超时统一保守处理
        logger.warning("AI 相关性过滤失败: %s", exc)
        return [False] * len(titles), f"{type(exc).__name__}: {str(exc)[:80]}"

    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        return [False] * len(titles), "LLM 输出结构不符合预期"

    keep = [False] * len(titles)
    for entry in results:
        if not isinstance(entry, dict):
            continue
        idx = entry.get("index")
        if not isinstance(idx, int) or not 0 <= idx < len(titles):
            continue
        keep[idx] = bool(entry.get("relevant"))
    return keep, None


ANALYSIS_SYSTEM_PROMPT = (
    "你是原料药工厂的 EHS 合规专家。根据给定的法规/标准标题与正文节选，"
    "输出 JSON 对象："
    "category（法规类别，只能取：一安全类/二职业健康类/特种设备/"
    "建筑防火与消防/特殊作业/化学品管理/其他相关法规）；"
    "issuer（颁布机关，如 应急管理部/全国人大/国务院）；"
    "implement_date（实施日期 YYYY-MM-DD，正文未提及则 null）；"
    "summary（核心要点总结，2~3 句，面向原料药生产企业说明核心要求）。"
    "只输出 JSON，日期格式必须为 YYYY-MM-DD 或 null。"
)

REGULATION_CATEGORIES = (
    "一安全类",
    "二职业健康类",
    "特种设备",
    "建筑防火与消防",
    "特殊作业",
    "化学品管理",
    "其他相关法规",
)

# 详情页正文抓取上限（字符），超出截断后交给 AI
DETAIL_TEXT_MAX_CHARS = 3000


async def _fetch_detail_text(
    client: httpx.AsyncClient, url: str
) -> str | None:
    """抓取法规详情页正文纯文本；PDF/失败/内容过短返回 None。"""

    try:
        resp = await client.get(
            url, headers=_CRAWL_HEADERS,
            follow_redirects=True,
        )
    except Exception:  # noqa: BLE001
        return None
    if resp.status_code != 200:
        return None
    ctype = resp.headers.get("content-type", "")
    if "pdf" in ctype or url.lower().endswith(".pdf"):
        return None
    text = decode_response(resp)
    try:
        doc = html.fromstring(text)
        for bad in doc.xpath("//script|//style|//nav|//footer|//header"):
            parent = bad.getparent()
            if parent is not None:
                parent.remove(bad)
        body = " ".join(doc.text_content().split())
    except Exception:  # noqa: BLE001
        body = " ".join(re.sub(r"<[^>]+>", " ", text).split())
    return body[:DETAIL_TEXT_MAX_CHARS] if len(body) >= 120 else None


async def _analyze_regulation(
    client: httpx.AsyncClient,
    item: CrawledRegulation,
) -> dict[str, Any] | None:
    """AI 结构化：类别/颁布机关/实施日期/核心要点总结。

    失败返回 None（仍会写入基础字段，不丢发现）。
    """
    try:
        from app.core.llm import llm_client
    except ImportError:  # pragma: no cover
        return None

    page_text = await _fetch_detail_text(client, item.url)
    content = f"标题：{item.title}"
    if page_text:
        content += f"\n\n正文节选：\n{page_text}"

    messages = [
        {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]
    try:
        data = await llm_client.chat_json(
            messages,
            expected_keys=["category", "issuer", "summary"],
            temperature=0.0,
        )
    except Exception as exc:  # noqa: BLE001 —— 分析失败不影响入库
        logger.warning("法规 AI 分析失败 %s: %s", item.title[:40], exc)
        return None

    category = str(data.get("category") or "").strip()
    if category not in REGULATION_CATEGORIES:
        category = "其他相关法规"
    implement_date: str | None = str(data.get("implement_date") or "").strip()
    if implement_date and not re.match(r"^\d{4}-\d{2}-\d{2}$", implement_date):
        implement_date = None
    return {
        "category": category,
        "issuer": str(data.get("issuer") or "").strip() or None,
        "implement_date": implement_date or None,
        "summary": str(data.get("summary") or "").strip() or None,
        "analyzed_at": datetime.now(UTC).isoformat(),
    }


def _next_sequential_nos(
    table_rows: list[dict[str, Any]], count: int
) -> list[str]:
    """沿用表格现有「法规编号」的数字递进（如 163 → 164、165）。"""
    mx = 0
    for row in table_rows:
        v = str(row.get("no") or "").strip()
        if v.isdigit():
            mx = max(mx, int(v))
    return [str(mx + i + 1) for i in range(count)]


async def _fetch_attachment_for_record(
    client: httpx.AsyncClient,
    detail_url: str,
    bitable: SafetyBitableClient,
) -> str | None:
    """从详情页找附件并上传到多维表格，返回 file_token（尽力而为）。

    任一步骤失败都返回 None，不影响记录创建；上传上限 20MB。
    """

    try:
        resp = await client.get(
            detail_url, headers=_CRAWL_HEADERS, follow_redirects=True
        )
    except Exception:  # noqa: BLE001
        return None
    if resp.status_code != 200:
        return None
    page = decode_response(resp)
    try:
        doc = html.fromstring(page)
    except Exception:  # noqa: BLE001
        return None
    base = str(resp.url)
    for a in doc.xpath("//a[@href]"):
        href = urljoin(base, a.get("href") or "")
        if not ATTACH_HREF_RE.search(href):
            continue
        label = " ".join(a.text_content().split()) or None
        try:
            dl = await client.get(href, headers=_CRAWL_HEADERS, follow_redirects=True)
        except Exception:  # noqa: BLE001
            continue
        if dl.status_code != 200 or not dl.content:
            continue
        if len(dl.content) > ATTACHMENT_MAX_BYTES:
            return None
        name = label or href.rsplit("/", 1)[-1].split("?")[0] or "attachment.pdf"
        return await bitable.upload_media(dl.content, name)
    return None


async def _create_in_table(
    client: SafetyBitableClient,
    table_id: str,
    item: CrawledRegulation,
    outcome: RadarOutcome,
    analysis: dict[str, Any] | None = None,
    seq_no: str | None = None,
    attachment_token: str | None = None,
) -> str | None:
    """把新法规写入飞书表格（AI 结构化填充各列 + 顺序编号 + 附件 + 标记）。"""
    fields: dict[str, Any] = {
        "法律法规及标准名称": item.title,
        "法规状态": "现行有效",
        "备注": f"[AI发现 {date.today().isoformat()}] 来源：{item.site_name}",
        "法规链接": {"link": item.url, "text": "官方来源"},
    }
    if seq_no:
        fields["法规编号"] = seq_no
    if attachment_token:
        fields["附件"] = [{"file_token": attachment_token}]

    if item.publish_date:
        fields["颁布修订日期"] = int(
            datetime.combine(
                item.publish_date, datetime.min.time(), tzinfo=UTC
            ).timestamp()
            * 1000
        )
    if analysis:
        fields["法规类别"] = analysis["category"]
        if analysis.get("issuer"):
            fields["颁布机关"] = analysis["issuer"]
        if analysis.get("implement_date"):
            try:
                impl = datetime.strptime(
                    analysis["implement_date"], "%Y-%m-%d"
                ).replace(tzinfo=UTC)
                fields["实施日期"] = int(impl.timestamp() * 1000)
            except ValueError:
                pass
        if analysis.get("summary"):
            fields["核心要点总结"] = analysis["summary"]
        if analysis.get("summary"):
            fields["核心要点总结"] = analysis["summary"]
    elif item.site_name.startswith("应急管理部"):
        # AI 分析不可用时的兜底：栏目来源可确定颁布机关
        fields["颁布机关"] = "应急管理部"
    record_id = await client.create_record(fields, table_id=table_id)
    if record_id is None:
        outcome.failed_count += 1
        logger.warning("新法规写入飞书失败: %s", item.title)
    return record_id


async def check_standard_versions(
    db: AsyncSession, *, limit: int = 20
) -> list[dict[str, Any]]:
    """按标准号在国标全文公开系统核查版本状态（滚动分批，每次最旧优先）。

    只核查「法规编号」为标准号形态的记录（GB/AQ/HJ/TSG 等）；
    顺序编号（001、002）的记录跳过。返回发生变化的明细。
    """
    from datetime import timedelta

    from app.modules.safety.crawler.types import (
        STANDARD_NO_RE,
        normalize_standard_no,
    )

    rows = (
        await db.execute(
            select(SafetyKnowledgeArticle)
            .where(
                SafetyKnowledgeArticle.is_deleted.is_(False),
                SafetyKnowledgeArticle.article_no.is_not(None),
                SafetyKnowledgeArticle.feishu_record_id.is_not(None),
            )
            .order_by(
                SafetyKnowledgeArticle.version_checked_at.asc().nulls_first(),
                SafetyKnowledgeArticle.article_no.asc(),
            )
            .limit(limit)
        )
    ).scalars().all()

    now = datetime.now(UTC)
    stale_cutoff = now - timedelta(days=180)
    changes: list[dict[str, Any]] = []

    for row in rows:
        # 标准号优先取法规名称里的（表里「法规编号」多为顺序号 001/002），
        # 名称如《建筑设计防火规范》GB 50016-2025 → GB 50016-2025
        std = normalize_standard_no(row.title) or normalize_standard_no(
            row.article_no
        )
        # 无标准号形态（顺序编号/纯法律）或近期已核查的跳过
        if not std or not STANDARD_NO_RE.search(std):
            continue
        if (
            row.version_checked_at is not None
            and row.version_checked_at > stale_cutoff
        ):
            continue

        core_no = re.sub(r"\s*[-—]\s*\d{4}\s*$", "", std)
        found = await search_standard(core_no)
        row.version_checked_at = now

        current_match = next(
            (i for i in found if i.standard_no and i.version_status == "current"),
            None,
        )
        exact = next(
            (i
             for i in found
             if i.standard_no and i.standard_no.upper() == std.upper()),
            None,
        )

        if exact is None:
            # 库里查无此标准号：可能编号有误，不轻易判定
            continue
        if exact.version_status == "obsolete":
            row.version_status = "obsolete"
            reason = f"该标准已废止（{std}）"
            if (
                current_match
                and (current_match.standard_no or "").upper() != std.upper()
            ):
                reason += f"；发现替代版本 {current_match.standard_no}"
            changes.append(
                {
                    "action": "obsolete",
                    "name": row.title,
                    "standard_no": std,
                    "old_date": (
                        row.promulgation_date.isoformat()
                        if row.promulgation_date
                        else None
                    ),
                    "url": exact.url,
                    "site": _STD_SITE.site_name,
                    "reason": reason,
                }
            )
        elif (
            current_match
            and (current_match.standard_no or "").upper() != std.upper()
            and row.version_status == "current"
        ):
            row.version_status = "revised"
            changes.append(
                {
                    "action": "revised",
                    "name": row.title,
                    "standard_no": std,
                    "new_standard_no": current_match.standard_no,
                    "old_date": (
                        row.promulgation_date.isoformat()
                        if row.promulgation_date
                        else None
                    ),
                    "new_date": (
                        current_match.publish_date.isoformat()
                        if current_match.publish_date
                        else None
                    ),
                    "url": current_match.url,
                    "site": _STD_SITE.site_name,
                    "reason": f"发现新版本 {current_match.standard_no}",
                }
            )
        else:
            row.version_status = "current"

    await db.commit()
    if changes:
        logger.info("标准版本核查发现 %s 条变化", len(changes))
    return changes


async def send_radar_notifications(
    db: AsyncSession,
    *,
    summary_lines: list[str],
    new_count: int,
    revised_count: int,
    is_test: bool = False,
) -> tuple[int, list[str] | None]:
    """按飞书设置推送扫描结果到群/个人，返回 (成功条数, 错误列表)。

    未启用/未配置目标时返回 (0, None)；单目标失败不影响其他目标。
    """
    from app.modules.safety.feishu.notification import send_group_card, send_user_card

    settings = await _load_settings(db)
    if not settings.radar_notify_enabled and not is_test:
        # 未启用/未配置目标是正常状态而非错误，静默跳过
        logger.info("法规雷达通知未启用或未配置目标，跳过推送")
        return 0, None
    chat_ids = [
        str(c).strip()
        for c in (settings.radar_notify_chat_ids or [])
        if str(c).strip()
    ]
    user_ids = [
        str(u).strip()
        for u in (settings.radar_notify_user_ids or [])
        if str(u).strip()
    ]
    if not chat_ids and not user_ids:
        if is_test:
            # 测试发送时给出明确错误，方便排查配置
            return 0, ["未配置通知目标（群 chat_id / 个人 open_id）"]
        logger.info("法规雷达通知未配置目标，跳过推送")
        return 0, None

    if is_test:
        title = "EHS 法规雷达 · 通知测试"
        content = (
            "这是一条**测试通知**。\n\n"
            "配置验证成功后，每周一 08:00 自动扫描发现新法规/修订时，"
            "会按本配置推送到这里。"
        )
    else:
        title = (
            f"EHS 法规动态 · 新增 {new_count} 部、修订 {revised_count} 部"
        )
        content = "\n".join(summary_lines[:10])
        if len(summary_lines) > 10:
            content += f"\n…… 共 {len(summary_lines)} 条，详见 安全管理 → 安全知识库"

    sent, errors = 0, []
    for cid in chat_ids:
        try:
            if await send_group_card(cid, title, content, header_template="blue"):
                sent += 1
            else:
                errors.append(f"群 {cid[:12]}… 发送失败")
        except Exception as exc:  # noqa: BLE001 —— 单目标失败不影响其他
            errors.append(f"群 {cid[:12]}… {type(exc).__name__}")
    for uid in user_ids:
        try:
            if await send_user_card(uid, title, content):
                sent += 1
            else:
                errors.append(f"个人 {uid[:12]}… 发送失败")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"个人 {uid[:12]}… {type(exc).__name__}")
    return sent, errors


def _build_summary_lines(items: list[dict[str, Any]]) -> list[str]:
    """把批次明细转成卡片里的 Markdown 行（新增在前，带链接）。"""
    lines: list[str] = []
    for it in items:
        if it.get("action") == "new":
            name = str(it.get("name") or "")
            url = it.get("url")
            date = it.get("date") or ""
            line = f"**新增** [{name}]({url})" if url else f"**新增** {name}"
            if date:
                line += f"（{date}）"
            lines.append(line)
        elif it.get("action") == "revised":
            lines.append(
                f"**已修订** {it.get('name') or ''}"
                f"（{it.get('old_date') or ''} → {it.get('new_date') or ''}）"
            )
        elif it.get("action") == "obsolete":
            lines.append(f"**已废止** {it.get('name') or ''}")
    return lines


async def send_test_notification(db: AsyncSession) -> dict[str, Any]:
    """向已配置的群/个人发送测试通知，返回发送结果摘要。"""
    sent, errors = await send_radar_notifications(
        db,
        summary_lines=["这是一条测试通知，用于验证通知目标配置。"],
        new_count=0,
        revised_count=0,
        is_test=True,
    )
    if sent == 0 and errors:
        raise AppException(message="；".join(errors[:3]))
    return {"sent": sent, "errors": errors}
