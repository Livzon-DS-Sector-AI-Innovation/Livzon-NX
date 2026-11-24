"""Administration business workflows.

覆盖「烟酒礼品管理」的飞书配置管理、只读镜像服务工厂与仪表台统计聚合。
"""

import asyncio
import logging
import uuid
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.llm import (
    LLMConfigError,
    LLMError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
    llm_client,
)
from app.core.secrets import decrypt_secret, encrypt_secret
from app.modules.administration.models import (
    AdministrationFeishuConfig,
    AdministrationFeishuReadField,
    AdministrationFeishuReadPageBinding,
    AdministrationFeishuReadRecord,
    AdministrationFeishuReadResource,
    AdministrationFeishuReadSourceRoot,
    AdministrationFeishuReadSyncRun,
)
from app.modules.administration.repository import (
    AdministrationRepository,
    MirroredTable,
)
from app.modules.administration.schemas import (
    AdministrationFeishuConfigInput,
    AdministrationFeishuConfigResponse,
    AdministrationFeishuConnectivityResult,
    AdministrationFeishuConnectivityStep,
    DormitoryCheckinInput,
    DormitoryCheckinResult,
    DormitoryOccupancyStats,
    DormitoryRecommendationItem,
    DormitoryRoomRecommendation,
    DormitoryRoomSummary,
    TobaccoGiftAiAnalysis,
    TobaccoGiftChartItem,
    TobaccoGiftDashboardStats,
)
from app.modules.hr.public_api import get_avatar_urls_by_emails
from app.platform.integrations.feishu.auth import FeishuAuth
from app.platform.integrations.feishu.bitable import BitableClient
from app.platform.integrations.feishu.read_mirror import (
    ModuleFeishuReadMirrorService,
    ReadMirrorModels,
)

logger = logging.getLogger("dazah.administration")

#: 行政模块镜像页面的 page key（与菜单、page_policy 登记保持一致）。
PAGE_KEY_TOBACCO_GIFT_ITEMS = "admin:tobacco-gift:items"
PAGE_KEY_TOBACCO_GIFT_RECORDS = "admin:tobacco-gift:records"
PAGE_KEY_SEALS = "admin:seals"
PAGE_KEY_SCRAP_MATERIALS = "admin:scrap-materials"
PAGE_KEY_DORMITORY = "admin:dormitory"
ADMINISTRATION_READ_PAGE_KEYS = frozenset(
    {
        PAGE_KEY_TOBACCO_GIFT_ITEMS,
        PAGE_KEY_TOBACCO_GIFT_RECORDS,
        PAGE_KEY_SEALS,
        PAGE_KEY_SCRAP_MATERIALS,
        PAGE_KEY_DORMITORY,
    }
)

READ_MIRROR_MODELS = ReadMirrorModels(
    root=AdministrationFeishuReadSourceRoot,
    resource=AdministrationFeishuReadResource,
    field=AdministrationFeishuReadField,
    record=AdministrationFeishuReadRecord,
    binding=AdministrationFeishuReadPageBinding,
    sync_run=AdministrationFeishuReadSyncRun,
)

#: 物品清单字段（实际表：物品名称/物品总数/物品单价/元/总金额/预警库存…）。
#: 先精确再包含匹配；数量候选不能用裸「库存」——会误命中「预警库存」。
_INVENTORY_NAME_FIELDS = ("物品名称", "名称")
_INVENTORY_QUANTITY_FIELDS = ("物品总数", "库存数量", "数量")
_INVENTORY_TOTAL_PRICE_FIELDS = ("总金额", "总价", "库存金额")
_INVENTORY_WARN_FIELDS = ("预警库存",)

#: 领用记录字段（实际表：领用物品/领用数量（一~五）、申请人、领取人、状态…）。
_REQUISITION_LINK_FIELDS = tuple(f"领用物品（{label}）" for label in "一二三四五")
_REQUISITION_QUANTITY_FIELDS = tuple(f"领用数量（{label}）" for label in "一二三四五")
_REQUISITION_STATUS_FIELDS = ("状态",)
#: 员工维度按申请人（每单必填）；领取人只有确认领用后才会填写。
_REQUISITION_EMPLOYEE_FIELDS = ("申请人", "领取人")
#: 已作废的单不进任何领用统计；「已领用物品总数」只计状态为已领用的单。
_REQUISITION_VOID_STATUSES = frozenset({"已作废"})
_REQUISITION_RECEIVED_STATUSES = frozenset({"已领用"})

#: 单图柱子上限（物品清单 35 种、申请人十余人），防止异常数据撑爆响应。
_CHART_LIMIT = 100

#: AI 分析生成超时：一次要输出概述+三组列表，比宿舍推荐的 15 秒放宽
_ANALYSIS_AI_TIMEOUT_SECONDS = 90


# ── 配置管理 ────────────────────────────────────────────────────


def _mask_secret(config: AdministrationFeishuConfig | None) -> str:
    return "****" if config is not None and config.encrypted_app_secret else ""


def _to_config_response(
    config: AdministrationFeishuConfig | None,
) -> AdministrationFeishuConfigResponse:
    if config is None:
        return AdministrationFeishuConfigResponse(
            config_name="行政管理飞书配置",
            app_id="",
            timezone="Asia/Shanghai",
            daily_sync_time="02:00",
            is_active=False,
            app_secret_configured=False,
        )
    return AdministrationFeishuConfigResponse(
        id=config.id,
        config_name=config.config_name,
        app_id=config.app_id,
        timezone=config.timezone,
        daily_sync_time=config.daily_sync_time,
        is_active=config.is_active,
        remark=config.remark,
        app_secret_configured=bool(config.encrypted_app_secret),
        app_secret_masked=_mask_secret(config),
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


def _resolve_active_secret(config: AdministrationFeishuConfig | None) -> str:
    if config is None or not config.encrypted_app_secret:
        return ""
    try:
        return decrypt_secret(config.encrypted_app_secret)
    except Exception:
        logger.exception("administration feishu secret decrypt failed")
        return ""


class AdministrationFeishuService:
    """飞书应用配置管理：保存、掩码回显与连通性测试。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AdministrationRepository(session)

    async def get_config_response(self) -> AdministrationFeishuConfigResponse:
        config = await self.repo.get_latest_config()
        return _to_config_response(config)

    async def save_config(
        self, data: AdministrationFeishuConfigInput
    ) -> AdministrationFeishuConfigResponse:
        config = await self.repo.get_latest_config()
        secret = data.app_secret.strip()
        if config is None:
            if not secret:
                raise AppException(message="首次保存飞书配置时必须填写 App Secret")
            config = AdministrationFeishuConfig(
                config_name=data.config_name,
                app_id=data.app_id,
                encrypted_app_secret=encrypt_secret(secret),
                is_active=data.is_active,
                timezone=data.timezone,
                daily_sync_time=data.daily_sync_time,
                remark=data.remark,
            )
            self.repo.add_config(config)
        else:
            config.config_name = data.config_name
            config.app_id = data.app_id
            if secret and secret != _mask_secret(config):
                config.encrypted_app_secret = encrypt_secret(secret)
            config.is_active = data.is_active
            config.timezone = data.timezone
            config.daily_sync_time = data.daily_sync_time
            config.remark = data.remark
        await self.session.flush()
        await self.session.refresh(config)
        return _to_config_response(config)

    async def test_connectivity(
        self, payload: AdministrationFeishuConfigInput | None = None
    ) -> AdministrationFeishuConnectivityResult:
        steps: list[AdministrationFeishuConnectivityStep] = []
        config = await self.repo.get_latest_config()
        fallback_app_id = config.app_id if config else ""
        app_id = str(getattr(payload, "app_id", "") or fallback_app_id)
        app_secret = str(getattr(payload, "app_secret", "") or "").strip()
        if not app_secret or app_secret == _mask_secret(config):
            app_secret = _resolve_active_secret(config)

        if not app_id or not app_secret:
            return AdministrationFeishuConnectivityResult(
                ok=False,
                steps=[
                    AdministrationFeishuConnectivityStep(
                        name="应用凭证",
                        status="error",
                        message="App ID 或 App Secret 未配置",
                    )
                ],
            )
        try:
            await asyncio.wait_for(
                FeishuAuth.get_tenant_access_token(app_id, app_secret),
                timeout=15,
            )
        except TimeoutError:
            logger.warning("administration feishu connectivity test timed out")
            steps.append(
                AdministrationFeishuConnectivityStep(
                    name="应用凭证", status="error", message="飞书认证超时，请稍后重试"
                )
            )
            return AdministrationFeishuConnectivityResult(ok=False, steps=steps)
        except Exception:
            logger.exception("administration feishu connectivity test failed")
            steps.append(
                AdministrationFeishuConnectivityStep(
                    name="应用凭证",
                    status="error",
                    message="飞书认证失败，请检查应用凭据",
                )
            )
            return AdministrationFeishuConnectivityResult(ok=False, steps=steps)
        steps.append(
            AdministrationFeishuConnectivityStep(
                name="应用凭证", status="ok", message="飞书认证成功"
            )
        )
        return AdministrationFeishuConnectivityResult(ok=True, steps=steps)


async def build_read_mirror_service(
    session: AsyncSession,
) -> ModuleFeishuReadMirrorService:
    """按最近一份已配置凭证构造平台只读镜像服务。

    is_active 表示「启用自动同步」，只由定时任务把关；页面读取与手动同步
    只要求凭证存在，避免用户关闭自动同步后台账和仪表台整体报错。
    """
    repo = AdministrationRepository(session)
    config = await repo.get_latest_config()
    if config is None or not config.app_id or not config.encrypted_app_secret:
        raise AppException(
            message="行政飞书应用凭据未配置，请先在「飞书设置」完成配置",
            status_code=400,
        )
    app_secret = _resolve_active_secret(config)
    if not app_secret:
        raise AppException(
            message="行政飞书应用凭据解密失败，请重新保存 App Secret",
            status_code=400,
        )
    return ModuleFeishuReadMirrorService(
        session,
        module_code="administration",
        app_id=config.app_id,
        app_secret=app_secret,
        models=READ_MIRROR_MODELS,
    )


#: 单次头像解析的邮箱数上限（镜像分页每页至多 100 行，人员字段去重后远小于此）。
_PERSON_AVATAR_EMAIL_LIMIT = 100


async def resolve_person_avatars(
    session: AsyncSession, emails: list[str]
) -> dict[str, str]:
    """按企业邮箱批量解析镜像人员头像（复用 hr 通讯录公开能力）。

    镜像记录的人员字段只带 open_id/name/email；open_id 跨应用不可关联，
    邮箱在全租户稳定，因此以邮箱为关联键。
    """
    normalized = [item.strip() for item in emails if item and item.strip()]
    if not normalized:
        return {}
    bounded = normalized[:_PERSON_AVATAR_EMAIL_LIMIT]
    return await get_avatar_urls_by_emails(session, bounded)


async def prune_resource_history(session: AsyncSession, resource_id: uuid.UUID) -> None:
    """同步成功后清理该数据表的非激活镜像版本与过期同步运行记录。

    平台镜像服务每轮全量插入新版本、只切换 active_mirror_version；行政模块
    15 分钟同步一次，不清理会让镜像表和同步记录无限增长。
    """
    resource = (
        (
            await session.execute(
                select(AdministrationFeishuReadResource).where(
                    AdministrationFeishuReadResource.id == resource_id,
                    AdministrationFeishuReadResource.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .first()
    )
    if resource is None or resource.active_mirror_version is None:
        return
    await session.execute(
        delete(AdministrationFeishuReadRecord).where(
            AdministrationFeishuReadRecord.resource_id == resource_id,
            AdministrationFeishuReadRecord.mirror_version
            != resource.active_mirror_version,
        )
    )
    await session.execute(
        delete(AdministrationFeishuReadSyncRun).where(
            AdministrationFeishuReadSyncRun.resource_id == resource_id,
            AdministrationFeishuReadSyncRun.started_at
            < datetime.now(UTC) - timedelta(days=7),
        )
    )
    await session.flush()


# ── 仪表台统计 ──────────────────────────────────────────────────
#
# 口径与行政侧飞书仪表盘一致（2026-11-09 用真实数据逐项核对：35 / 152,547 /
# 515 / 16 及各图柱值全部吻合）：
# - 物品品类 = 物品清单记录数；物品总价 = Σ总金额；物品总数 = Σ物品总数；
# - 已领用物品总数 = 状态为「已领用」的领用单上领用数量（一~五）合计；
# - 物品库存情况 / 领用物品总价分布 = 物品清单按物品的物品总数 / 总金额；
# - 物品领取分析 / 员工领用统计 = 未作废领用单按物品 / 申请人的领用数量合计。
#
# 镜像记录保存的是飞书 records/search 原始值：富文本是 [{"text":..}]，公式是
# {"type":..,"value":[x]}，关联字段只有 {"link_record_ids":[..]}（无名称）。


def _as_number(value: Any) -> float | None:
    """数字/货币直接用；公式取 value；单元素列表取首项；文本可解析则解析。"""
    if isinstance(value, dict):
        return _as_number(value.get("value"))
    if isinstance(value, list):
        return _as_number(value[0]) if len(value) == 1 else None
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("¥", "").replace("￥", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _as_text(value: Any) -> str:
    """文本/单选/富文本 → 展示文本。富文本片段直接拼接，多选以顿号分隔。"""
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, dict):
        for key in ("text", "name"):
            item = value.get(key)
            if isinstance(item, str):
                return item.strip()
        inner = value.get("value")
        return _as_text(inner) if inner is not None else ""
    if isinstance(value, list):
        if all(isinstance(item, dict) for item in value):
            return "".join(_as_text(item) for item in value).strip()
        return "、".join(text for text in (_as_text(item) for item in value) if text)
    return str(value).strip()


def _as_person_names(value: Any) -> list[str]:
    """飞书人员字段：[{"id": ..., "name": ...}] 或纯文本。"""
    if isinstance(value, list):
        names: list[str] = []
        for item in value:
            if isinstance(item, dict):
                name = str(item.get("name") or "")
            else:
                name = _as_text(item)
            if name.strip():
                names.append(name.strip())
        return names
    text = _as_text(value)
    return [text] if text else []


def _as_link(value: Any) -> tuple[list[str], list[str]]:
    """关联字段 → (接口自带的展示名, 关联记录 id)。名称优先用物品清单镜像解析。"""
    if not isinstance(value, dict):
        return ([], [])
    raw_ids = value.get("link_record_ids") or value.get("record_ids") or []
    record_ids = [str(item) for item in raw_ids if str(item)]
    raw_texts = value.get("text") or []
    if isinstance(raw_texts, str):
        raw_texts = [raw_texts]
    texts = [str(item).strip() for item in raw_texts if str(item).strip()]
    return (texts, record_ids)


def _resolve_field_name(
    candidates: tuple[str, ...], field_names: list[str]
) -> str | None:
    lowered = {name.strip().lower(): name for name in field_names}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    for candidate in candidates:
        key = candidate.lower()
        for name in field_names:
            if key in name.lower():
                return name
    return None


def _field_value(record: AdministrationFeishuReadRecord, field_name: str | None) -> Any:
    if field_name is None:
        return None
    return (record.raw_fields or {}).get(field_name)


def _chart(totals: Mapping[str, float]) -> list[TobaccoGiftChartItem]:
    """按数值降序取前 _CHART_LIMIT 项；展示顺序由前端按名称排序。"""
    items = sorted(totals.items(), key=lambda pair: (-pair[1], pair[0]))
    return [
        TobaccoGiftChartItem(name=name, value=round(value, 2))
        for name, value in items[:_CHART_LIMIT]
    ]


@dataclass(frozen=True)
class _InventoryExtraction:
    categories: int
    total_count: float
    total_value: float
    quantity_by_item: dict[str, float]
    value_by_item: dict[str, float]
    name_by_record: dict[str, str]


@dataclass(frozen=True)
class _RequisitionExtraction:
    received_total: float
    quantity_by_item: dict[str, float]
    quantity_by_employee: dict[str, float]


def _extract_inventory(table: MirroredTable | None) -> _InventoryExtraction:
    if table is None:
        return _InventoryExtraction(0, 0.0, 0.0, {}, {}, {})
    field_names = [field.field_name for field in table.fields]
    name_field = _resolve_field_name(_INVENTORY_NAME_FIELDS, field_names) or (
        table.fields[0].field_name if table.fields else None
    )
    quantity_field = _resolve_field_name(_INVENTORY_QUANTITY_FIELDS, field_names)
    value_field = _resolve_field_name(_INVENTORY_TOTAL_PRICE_FIELDS, field_names)
    if table.records and (quantity_field is None or value_field is None):
        logger.warning(
            "tobacco-gift inventory fields unresolved (quantity=%s, value=%s): %s",
            quantity_field,
            value_field,
            field_names,
        )

    quantity_by_item: defaultdict[str, float] = defaultdict(float)
    value_by_item: defaultdict[str, float] = defaultdict(float)
    name_by_record: dict[str, str] = {}
    total_count = 0.0
    total_value = 0.0
    for record in table.records:
        record_id = str(record.record_id)
        name = _as_text(_field_value(record, name_field))
        if not name:
            name = f"未命名物品·{record_id[-6:]}"
        name_by_record[record_id] = name
        quantity = _as_number(_field_value(record, quantity_field))
        if quantity is not None:
            total_count += quantity
            quantity_by_item[name] += quantity
        value = _as_number(_field_value(record, value_field))
        if value is not None:
            total_value += value
            value_by_item[name] += value
    return _InventoryExtraction(
        categories=len(table.records),
        total_count=total_count,
        total_value=total_value,
        quantity_by_item=dict(quantity_by_item),
        value_by_item=dict(value_by_item),
        name_by_record=name_by_record,
    )


def _resolve_item_name(
    texts: list[str],
    record_ids: list[str],
    name_by_record: Mapping[str, str],
) -> str | None:
    """解析关联物品名称；关联的是已删除物品且无任何名称时返回 None。"""
    for record_id in record_ids:
        name = name_by_record.get(record_id)
        if name:
            return name
    if texts:
        return texts[0]
    return None


def _extract_requisitions(
    table: MirroredTable | None,
    name_by_record: Mapping[str, str],
) -> _RequisitionExtraction:
    if table is None:
        return _RequisitionExtraction(0.0, {}, {})
    field_names = [field.field_name for field in table.fields]
    status_field = _resolve_field_name(_REQUISITION_STATUS_FIELDS, field_names)
    employee_field = _resolve_field_name(_REQUISITION_EMPLOYEE_FIELDS, field_names)

    quantity_by_item: defaultdict[str, float] = defaultdict(float)
    quantity_by_employee: defaultdict[str, float] = defaultdict(float)
    received_total = 0.0
    for record in table.records:
        status = _as_text(_field_value(record, status_field))
        if status in _REQUISITION_VOID_STATUSES:
            continue
        received = status in _REQUISITION_RECEIVED_STATUSES
        employees = _as_person_names(_field_value(record, employee_field))
        for link_field, quantity_field in zip(
            _REQUISITION_LINK_FIELDS, _REQUISITION_QUANTITY_FIELDS, strict=True
        ):
            texts, record_ids = _as_link(_field_value(record, link_field))
            quantity = _as_number(_field_value(record, quantity_field))
            if not quantity or not (texts or record_ids):
                continue
            # 已领用总数与员工统计按真实数量计；悬空关联（物品已删且无名称）
            # 不进按物品的图表，避免编造标签
            item_name = _resolve_item_name(texts, record_ids, name_by_record)
            if item_name:
                quantity_by_item[item_name] += quantity
            if employees:
                quantity_by_employee[employees[0]] += quantity
            if received:
                received_total += quantity
    return _RequisitionExtraction(
        received_total=received_total,
        quantity_by_item=dict(quantity_by_item),
        quantity_by_employee=dict(quantity_by_employee),
    )


def _extract_inventory_alerts(table: MirroredTable | None) -> list[str]:
    """库存低于预警线的物品（确定性检查，不依赖 LLM）：“名称：现有x，预警y”。"""
    if table is None:
        return []
    field_names = [field.field_name for field in table.fields]
    name_field = _resolve_field_name(_INVENTORY_NAME_FIELDS, field_names) or (
        table.fields[0].field_name if table.fields else None
    )
    quantity_field = _resolve_field_name(_INVENTORY_QUANTITY_FIELDS, field_names)
    warn_field = _resolve_field_name(_INVENTORY_WARN_FIELDS, field_names)
    if quantity_field is None or warn_field is None:
        return []
    alerts: list[tuple[float, str]] = []
    for record in table.records:
        quantity = _as_number(_field_value(record, quantity_field))
        warn = _as_number(_field_value(record, warn_field))
        if quantity is None or not warn or quantity >= warn:
            continue
        name = _as_text(_field_value(record, name_field)) or "未命名物品"
        alerts.append((quantity - warn, f"{name}：现有{quantity:g}，预警{warn:g}"))
    return [text for _gap, text in sorted(alerts)]


def _requisition_status_distribution(table: MirroredTable | None) -> dict[str, int]:
    """领用单状态分布（含已作废，供 AI 分析作废率与在途单判断）。"""
    if table is None:
        return {}
    status_field = _resolve_field_name(
        _REQUISITION_STATUS_FIELDS, [field.field_name for field in table.fields]
    )
    counts: Counter[str] = Counter()
    for record in table.records:
        counts[_as_text(_field_value(record, status_field)) or "未填写"] += 1
    return dict(counts)


def _build_analysis_digest(
    stats: TobaccoGiftDashboardStats,
    alerts: list[str],
    status_counts: dict[str, int],
) -> str:
    """把仪表台统计压缩成供 LLM 阅读的纯数据摘要（只含事实数字）。"""

    def top(items: list[TobaccoGiftChartItem], n: int = 5) -> str:
        return "、".join(f"{item.name}{item.value:g}" for item in items[:n])

    status_text = "、".join(
        f"{name}{count}" for name, count in sorted(status_counts.items())
    )
    alert_text = "；".join(alerts) if alerts else "无"
    return "\n".join(
        [
            f"物品品类：{stats.item_categories}",
            f"物品总数：{stats.item_total_count:g}",
            f"物品总价：{stats.item_total_value:g}元",
            f"已领用物品总数（已领用状态单合计）：{stats.requisitioned_total:g}",
            f"物品库存数量Top5：{top(stats.inventory_by_item)}",
            f"领用数量Top5（不含已作废）：{top(stats.requisition_by_item)}",
            f"领用物品总价Top5：{top(stats.value_by_item)}",
            f"员工领用数量Top3（按申请人）：{top(stats.requisition_by_employee, 3)}",
            f"领用单状态分布：{status_text or '无数据'}",
            f"低于预警库存的物品：{alert_text}",
        ]
    )


def _clean_str_list(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:limit]


async def _request_ai_analysis(digest: str) -> dict[str, Any]:
    system = (
        "你是制药工厂的行政管理助手。基于用户给出的烟酒礼品台账统计数据"
        "生成分析，只使用给定数字，不得虚构数据或建议处罚。"
        "回答务必简短，直接输出 JSON，不要输出任何解释："
        '{"summary":"总体态势概述，不超过80字",'
        '"insights":["关键发现2~4条，每条不超过40字"],'
        '"anomalies":["异常提示0~4条，如低于预警库存、作废单占比高，无则空数组"],'
        '"suggestions":["管理建议2~3条，每条不超过40字"]}'
    )
    user = f"统计数据：\n{digest}\n请按要求输出 JSON。"
    # token-plan 端点偶发瞬态网络错误（超时/对端断连/ConnectError），重试一次
    data: dict[str, Any] | None = None
    for attempt in range(2):
        try:
            data = await llm_client.chat_json(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                expected_keys=["summary", "insights", "anomalies", "suggestions"],
                temperature=0.2,
                timeout=_ANALYSIS_AI_TIMEOUT_SECONDS,
                enable_thinking=False,
            )
            break
        except LLMConfigError as exc:
            raise AppException(
                message="AI 分析不可用：模型未配置，请在系统设置中配置模型",
                status_code=503,
            ) from exc
        except LLMRateLimitError as exc:
            raise AppException(
                message="AI 调用触发限流，请稍后重试", status_code=429
            ) from exc
        except (LLMOutputError, LLMProviderError, LLMError) as exc:
            if attempt == 0:
                logger.warning(
                    "tobacco-gift AI analysis attempt 1 failed, retrying once",
                    exc_info=exc,
                )
                await asyncio.sleep(1.5)
                continue
            logger.warning("tobacco-gift AI analysis upstream failed", exc_info=exc)
            raise AppException(
                message="AI 生成失败，请稍后重试", status_code=502
            ) from exc
    if not isinstance(data, dict):
        raise AppException(message="AI 输出格式异常，请重试", status_code=502)
    return data


class AdministrationTobaccoGiftService:
    """烟酒礼品仪表台统计：从本地镜像聚合，未绑定/未同步时为零值。"""

    def __init__(self, session: AsyncSession) -> None:
        self.repo = AdministrationRepository(session)

    async def get_dashboard_stats(self) -> TobaccoGiftDashboardStats:
        inventory = await self.repo.get_default_bound_table(PAGE_KEY_TOBACCO_GIFT_ITEMS)
        requisition = await self.repo.get_default_bound_table(
            PAGE_KEY_TOBACCO_GIFT_RECORDS
        )
        if inventory is None and requisition is None:
            logger.info("tobacco-gift dashboard has no bound tables yet")

        stock = _extract_inventory(inventory)
        usage = _extract_requisitions(requisition, stock.name_by_record)
        return TobaccoGiftDashboardStats(
            item_categories=stock.categories,
            item_total_value=round(stock.total_value, 2),
            item_total_count=round(stock.total_count, 2),
            requisitioned_total=round(usage.received_total, 2),
            inventory_by_item=_chart(stock.quantity_by_item),
            requisition_by_item=_chart(usage.quantity_by_item),
            value_by_item=_chart(stock.value_by_item),
            requisition_by_employee=_chart(usage.quantity_by_employee),
            inventory_synced_at=(
                inventory.resource.last_complete_sync_at if inventory else None
            ),
            requisition_synced_at=(
                requisition.resource.last_complete_sync_at if requisition else None
            ),
        )

    async def generate_ai_analysis(self) -> TobaccoGiftAiAnalysis:
        """生成仪表台 AI 分析：确定性数据摘要 + 统一 LLM 结构化输出。"""
        stats = await self.get_dashboard_stats()
        inventory = await self.repo.get_default_bound_table(PAGE_KEY_TOBACCO_GIFT_ITEMS)
        requisition = await self.repo.get_default_bound_table(
            PAGE_KEY_TOBACCO_GIFT_RECORDS
        )
        digest = _build_analysis_digest(
            stats,
            _extract_inventory_alerts(inventory),
            _requisition_status_distribution(requisition),
        )
        data = await _request_ai_analysis(digest)
        summary = str(data.get("summary", "")).strip()
        if not summary:
            raise AppException(message="AI 输出缺少总体概述，请重试", status_code=502)
        return TobaccoGiftAiAnalysis(
            summary=summary,
            insights=_clean_str_list(data.get("insights"), 6),
            anomalies=_clean_str_list(data.get("anomalies"), 6),
            suggestions=_clean_str_list(data.get("suggestions"), 5),
            generated_at=datetime.now(UTC),
        )


async def decorate_records_for_display(
    session: AsyncSession, data: dict[str, Any]
) -> dict[str, Any]:
    """把镜像记录里的关联字段装饰为可读名称（展示层，不影响存储）。

    飞书 records/search 对单向关联字段只返回 ``link_record_ids``，没有名称，
    前端镜像表格会把这种复杂值渲染成「查看详情」按钮、抽屉里显示原始 JSON。
    这里用物品清单镜像把 ID 解析成名称，直接替换为纯文本字符串。
    """
    records = data.get("records") or []

    # 关联字段两种形态：带 ID 的 {"link_record_ids":[..]}，以及空关联的裸 {}；
    # 空关联装饰为空串（前端显示 "-"），否则会渲染成「查看详情」按钮。
    def _is_link_like(value: Any) -> bool:
        return isinstance(value, dict) and (
            "link_record_ids" in value or "record_ids" in value or not value
        )

    has_link = any(
        _is_link_like(value)
        for record in records
        for value in (record.get("fields") or {}).values()
    )
    if not has_link:
        return data

    inventory = await AdministrationRepository(session).get_default_bound_table(
        PAGE_KEY_TOBACCO_GIFT_ITEMS
    )
    name_by_record = _extract_inventory(inventory).name_by_record if inventory else {}
    for record in records:
        fields = record.get("fields") or {}
        for field_name, value in fields.items():
            if not _is_link_like(value):
                continue
            texts, record_ids = _as_link(value)
            # 悬空关联（物品已从清单删除且无名称）与空关联一样显示 "-"
            item_name = _resolve_item_name(texts, record_ids, name_by_record)
            fields[field_name] = item_name or ""
    return data


# ── 宿舍管理：入住率仪表盘 + AI 推荐入住 ────────────────────────
#
# 口径：宿舍清单镜像的公式字段（已住人数/剩余床位）由飞书计算并随镜像同步，
# 这里直接取值，不重复实现公式语义；镜像未同步时全部为 0/空，不报错。
# LLM 只在确定性候选（性别→宿舍类型、岗位→住宿标准房间类型、剩余床位>0）
# 过滤之后做排序与理由生成，不做业务裁决；用户确认后由 checkin 按既定
# 校验（房间存在、有空床位、性别与宿舍类型相符）回写飞书员工住宿退宿清单。

_ROOM_NO_FIELDS = ("宿舍编号", "房间编号", "编号")
_ROOM_BUILDING_FIELDS = ("楼号",)
_ROOM_UNIT_FIELDS = ("单元",)
_ROOM_TYPE_FIELDS = ("房间类型", "房型")
_ROOM_DORM_TYPE_FIELDS = ("宿舍类型",)
_ROOM_BED_FIELDS = ("床位数量", "床位数", "床位")
_ROOM_OCCUPIED_FIELDS = ("已住人数", "入住人数")
_ROOM_VACANT_FIELDS = ("剩余床位", "空床位")

_STANDARD_JOB_FIELDS = ("岗位", "职位")
_STANDARD_ROOM_TYPE_FIELDS = ("房间类型", "房型")

_EMPLOYEE_NAME_FIELDS = ("姓名",)
_EMPLOYEE_GENDER_FIELDS = ("性别",)

#: 员工住宿退宿清单（回写目标表）的识别特征：有房间编号+姓名，且没有床位字段。
_EMPLOYEE_ROOM_NO_FIELDS = ("房间编号", "宿舍编号")

_ROOM_LIST_LIMIT = 500
#: 送入 LLM 的候选房间上限（prompt 长度可控；超出部分按规则兜底排序）。
_AI_CANDIDATE_LIMIT = 30
_AI_TIMEOUT_SECONDS = 15
_REASON_MAX_CHARS = 120


@dataclass(frozen=True)
class _DormRoom:
    """宿舍清单单行摘要（数值字段统一取整；缺失按 0 处理）。"""

    room_no: str
    building: str
    unit: str
    room_type: str
    dorm_type: str
    beds: int
    occupied: int
    vacant: int


def _as_int(value: Any) -> int:
    number = _as_number(value)
    if number is None:
        return 0
    return int(round(number))


def _table_field_names(table: MirroredTable) -> set[str]:
    return {item.field_name for item in table.fields}


def _find_table(
    tables: list[MirroredTable],
    *,
    title: str,
    required: tuple[tuple[str, ...], ...],
    forbidden: tuple[str, ...] = (),
) -> MirroredTable | None:
    """先按资源标题找，退化按字段特征找（标题被改时仍可用）。"""
    for table in tables:
        if table.resource.title == title:
            return table
    for table in tables:
        names = _table_field_names(table)
        if any(token in names for token in forbidden):
            continue
        if all(
            _resolve_field_name(candidates, sorted(names)) for candidates in required
        ):
            return table
    return None


def _extract_rooms(table: MirroredTable | None) -> list[_DormRoom]:
    if table is None:
        return []
    names = sorted(_table_field_names(table))
    no_key = _resolve_field_name(_ROOM_NO_FIELDS, names)
    if no_key is None:
        return []
    building_key = _resolve_field_name(_ROOM_BUILDING_FIELDS, names)
    unit_key = _resolve_field_name(_ROOM_UNIT_FIELDS, names)
    type_key = _resolve_field_name(_ROOM_TYPE_FIELDS, names)
    dorm_key = _resolve_field_name(_ROOM_DORM_TYPE_FIELDS, names)
    bed_key = _resolve_field_name(_ROOM_BED_FIELDS, names)
    occupied_key = _resolve_field_name(_ROOM_OCCUPIED_FIELDS, names)
    vacant_key = _resolve_field_name(_ROOM_VACANT_FIELDS, names)
    rooms: list[_DormRoom] = []
    for record in table.records[:_ROOM_LIST_LIMIT]:
        fields = record.raw_fields or {}
        room_no = _as_text(fields.get(no_key))
        if not room_no:
            continue
        beds = _as_int(fields.get(bed_key)) if bed_key else 0
        occupied = _as_int(fields.get(occupied_key)) if occupied_key else 0
        vacant = (
            _as_int(fields.get(vacant_key)) if vacant_key else max(beds - occupied, 0)
        )
        rooms.append(
            _DormRoom(
                room_no=room_no,
                building=_as_text(fields.get(building_key)) if building_key else "",
                unit=_as_text(fields.get(unit_key)) if unit_key else "",
                room_type=_as_text(fields.get(type_key)) if type_key else "",
                dorm_type=_as_text(fields.get(dorm_key)) if dorm_key else "",
                beds=beds,
                occupied=occupied,
                vacant=max(vacant, 0),
            )
        )
    rooms.sort(key=lambda room: room.room_no)
    return rooms


def _extract_standards(table: MirroredTable | None) -> dict[str, str]:
    """住宿标准：岗位 → 房间类型（丢弃空行）。"""
    if table is None:
        return {}
    names = sorted(_table_field_names(table))
    job_key = _resolve_field_name(_STANDARD_JOB_FIELDS, names)
    type_key = _resolve_field_name(_STANDARD_ROOM_TYPE_FIELDS, names)
    if job_key is None or type_key is None:
        return {}
    standards: dict[str, str] = {}
    for record in table.records[:_ROOM_LIST_LIMIT]:
        fields = record.raw_fields or {}
        job = _as_text(fields.get(job_key))
        room_type = _as_text(fields.get(type_key))
        if job and room_type:
            standards[job] = room_type
    return standards


def _match_standard(standards: dict[str, str], job_title: str) -> str | None:
    """按岗位匹配住宿标准的房间类型：精确 → 双向包含；无标准返回 None（不限房型）。"""
    job = job_title.strip()
    if not job:
        return None
    if job in standards:
        return standards[job]
    lowered = {key.lower(): value for key, value in standards.items()}
    if job.lower() in lowered:
        return lowered[job.lower()]
    for key, value in standards.items():
        if key and (key in job or job in key):
            return value
    return None


def _normalize_gender(value: str) -> str:
    text = (value or "").strip().lower()
    if "男" in text or text.startswith("m"):
        return "男"
    if "女" in text or text.startswith("f"):
        return "女"
    return ""


def _gender_conflicts_with_dorm(gender: str, dorm_type: str) -> bool:
    """性别与宿舍类型不符判定（宿舍类型/性别任一未知则不拦截）。"""
    normalized = _normalize_gender(gender)
    if not normalized or not dorm_type:
        return False
    has_male = "男" in dorm_type
    has_female = "女" in dorm_type
    if has_male and not has_female:
        return normalized == "女"
    if has_female and not has_male:
        return normalized == "男"
    return False


def _room_summary(room: _DormRoom) -> DormitoryRoomSummary:
    return DormitoryRoomSummary(
        room_no=room.room_no,
        building=room.building,
        unit=room.unit,
        room_type=room.room_type,
        dorm_type=room.dorm_type,
        bed_count=room.beds,
        occupied=room.occupied,
        vacant=room.vacant,
    )


class AdministrationDormitoryService:
    """宿舍入住率统计、AI 房间推荐与入住登记回写飞书。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AdministrationRepository(session)

    # ── 入住率仪表盘 ────────────────────────────────────────────

    async def get_dashboard_stats(self) -> DormitoryOccupancyStats:
        rooms_table = await self.repo.get_default_bound_table(PAGE_KEY_DORMITORY)
        rooms = _extract_rooms(rooms_table)
        total_beds = sum(room.beds for room in rooms)
        occupied_beds = sum(
            min(room.occupied, max(room.beds, 0)) or room.occupied for room in rooms
        )
        empty = [room for room in rooms if room.occupied <= 0]
        full = [room for room in rooms if room.occupied > 0 and room.vacant <= 0]
        partial = [room for room in rooms if room not in empty and room not in full]
        return DormitoryOccupancyStats(
            total_rooms=len(rooms),
            empty_rooms=len(empty),
            full_rooms=len(full),
            partial_rooms=len(partial),
            total_beds=total_beds,
            occupied_beds=occupied_beds,
            occupancy_rate=(occupied_beds / total_beds) if total_beds > 0 else 0.0,
            empty_room_list=[_room_summary(room) for room in empty],
            full_room_list=[_room_summary(room) for room in full],
            synced_at=(
                rooms_table.resource.last_complete_sync_at if rooms_table else None
            ),
        )

    # ── AI 房间推荐 ─────────────────────────────────────────────

    async def recommend_rooms(
        self, payload: DormitoryCheckinInput
    ) -> DormitoryRoomRecommendation:
        tables = await self._bound_tables()
        rooms = _extract_rooms(self._rooms_table(tables))
        gender = _normalize_gender(payload.gender)
        standards = _extract_standards(self._standards_table(tables))
        required_type = _match_standard(standards, payload.job_title)

        candidates = [
            room
            for room in rooms
            if room.vacant > 0
            and not _gender_conflicts_with_dorm(gender, room.dorm_type)
            and (required_type is None or room.room_type == required_type)
        ]
        filter_summary = "；".join(
            item
            for item in (
                f"性别：{gender}" if gender else "",
                (
                    f"住宿标准房型：{required_type}（岗位：{payload.job_title}）"
                    if required_type
                    else ""
                ),
            )
            if item
        )
        if not candidates:
            message = (
                f"暂无符合条件的空床位房间（{filter_summary}）"
                if filter_summary
                else "暂无可入住房间（宿舍清单为空或未同步）"
            )
            return DormitoryRoomRecommendation(
                recommendations=[], source="rule", message=message
            )

        picked = await self._ai_rank_rooms(payload, gender, required_type, candidates)
        source = "ai"
        if picked is None:
            # 规则兜底：优先住满接近满员的房间（减少分散占用），再按编号稳定排序。
            ordered = sorted(candidates, key=lambda room: (room.vacant, room.room_no))
            picked = []
            for room in ordered[:3]:
                prefix = (
                    f"房型「{room.room_type}」符合岗位住宿标准，"
                    if required_type
                    else ""
                )
                reason = (
                    f"{prefix}规则推荐：剩余床位 {room.vacant}，优先安排接近住满的房间"
                )
                picked.append((room, reason))
            source = "rule"
        return DormitoryRoomRecommendation(
            recommendations=[
                DormitoryRecommendationItem(
                    room_no=room.room_no,
                    room_type=room.room_type,
                    dorm_type=room.dorm_type,
                    vacant_beds=room.vacant,
                    reason=reason[:_REASON_MAX_CHARS],
                    source=source,
                )
                for room, reason in picked
            ],
            source=source,
            message=(
                f"已按 {filter_summary} 过滤出 {len(candidates)} 间可入住房间"
                if filter_summary
                else f"共 {len(candidates)} 间可入住房间"
            ),
        )

    def _rooms_table(self, tables: list[MirroredTable]) -> MirroredTable | None:
        return _find_table(
            tables,
            title="宿舍清单",
            required=(_ROOM_BED_FIELDS, _ROOM_OCCUPIED_FIELDS),
        )

    def _standards_table(self, tables: list[MirroredTable]) -> MirroredTable | None:
        return _find_table(
            tables,
            title="住宿标准",
            required=(_STANDARD_JOB_FIELDS, _STANDARD_ROOM_TYPE_FIELDS),
            forbidden=(*_ROOM_BED_FIELDS, "姓名"),
        )

    def _employee_table(self, tables: list[MirroredTable]) -> MirroredTable | None:
        return _find_table(
            tables,
            title="员工住宿退宿清单",
            required=(
                _EMPLOYEE_ROOM_NO_FIELDS,
                _EMPLOYEE_NAME_FIELDS,
                _EMPLOYEE_GENDER_FIELDS,
            ),
            forbidden=(*_ROOM_BED_FIELDS, *_ROOM_VACANT_FIELDS),
        )

    async def _ai_rank_rooms(
        self,
        payload: DormitoryCheckinInput,
        gender: str,
        required_type: str | None,
        candidates: list[_DormRoom],
    ) -> list[tuple[_DormRoom, str]] | None:
        """LLM 在候选内排序推荐；不可用/输出无效返回 None（规则兜底）。"""
        shortlist = candidates[:_AI_CANDIDATE_LIMIT]
        listing = "\n".join(
            f"- 宿舍编号:{room.room_no}｜房间类型:{room.room_type or '未知'}"
            f"｜宿舍类型:{room.dorm_type or '未知'}"
            f"｜剩余床位:{room.vacant}｜已住:{room.occupied}"
            for room in shortlist
        )
        profile_lines = [f"姓名：{payload.name}"]
        if gender:
            profile_lines.append(f"性别：{gender}")
        if payload.job_title:
            profile_lines.append(f"岗位：{payload.job_title}")
        if payload.department:
            profile_lines.append(f"部门：{payload.department}")
        if payload.shift_type:
            profile_lines.append(f"倒班类型：{payload.shift_type}")
        system_prompt = (
            "你是制药厂宿舍分配助手。根据新员工信息从候选房间中推荐最合适的房间，"
            "只输出一个 JSON 对象：\n"
            '{"recommendations": [{"room_no": "宿舍编号（必须从候选清单原样复制）", '
            '"reason": "一句话推荐理由（30字内）"}]}\n'
            "规则：\n"
            "- 最多推荐 3 条，按推荐程度排序；只能从候选清单中选择，禁止编造房间\n"
            "- 同岗位优先相同房间类型；优先让同岗位员工同住、减少分散占用\n"
            "- 不得输出 JSON 以外的任何内容"
        )
        user_prompt = (
            f"新员工信息：{'；'.join(profile_lines)}\n"
            + (f"住宿标准要求房型：{required_type}\n" if required_type else "")
            + f"候选房间（共 {len(shortlist)} 间，均可入住）：\n{listing}"
        )
        try:
            data: Any = await llm_client.chat_json(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                expected_keys=["recommendations"],
                temperature=0.0,
                timeout=_AI_TIMEOUT_SECONDS,
                enable_thinking=False,
            )
        except LLMError:
            logger.info("宿舍 AI 推荐未生效（模型输出异常），走规则排序")
            return None
        except Exception:
            logger.warning("宿舍 AI 推荐调用失败，走规则排序", exc_info=True)
            return None

        raw_items = data.get("recommendations")
        if not isinstance(raw_items, list):
            return None
        by_no = {room.room_no: room for room in candidates}
        picked: list[tuple[_DormRoom, str]] = []
        seen: set[str] = set()
        for item in raw_items:
            if not isinstance(item, dict) or len(picked) >= 3:
                break
            room = by_no.get(str(item.get("room_no", "")).strip())
            if room is None or room.room_no in seen:
                continue
            seen.add(room.room_no)
            reason = str(item.get("reason", "")).strip()
            picked.append((room, reason or "AI 推荐"))
        return picked or None

    # ── 办理入住（回写飞书） ────────────────────────────────────

    async def checkin(self, payload: DormitoryCheckinInput) -> DormitoryCheckinResult:
        config = await self.repo.get_latest_config()
        if config is None or not config.app_id or not config.encrypted_app_secret:
            raise AppException(
                message="行政飞书应用凭据未配置，请先在「飞书设置」完成配置",
                status_code=400,
            )
        app_secret = _resolve_active_secret(config)

        tables = await self._bound_tables()
        rooms = _extract_rooms(self._rooms_table(tables))
        room_no = payload.room_no.strip()
        room = next((item for item in rooms if item.room_no == room_no), None)
        if room is None:
            display_no = room_no or payload.room_no
            raise AppException(
                message=f"宿舍编号「{display_no}」不在宿舍清单中，请重新选择",
                status_code=404,
            )
        if room.vacant <= 0:
            raise AppException(
                message=f"宿舍「{room.room_no}」已无空床位，请重新选择",
                status_code=400,
            )
        if _gender_conflicts_with_dorm(payload.gender, room.dorm_type):
            raise AppException(
                message=f"性别（{payload.gender}）与宿舍类型（{room.dorm_type}）不符，请重新选择",
                status_code=400,
            )
        employees = self._employee_table(tables)
        if employees is None:
            raise AppException(
                message="未找到「员工住宿退宿清单」数据表绑定，请先在飞书设置页完成绑定",
                status_code=400,
            )

        fields: dict[str, str] = {
            next(iter(_EMPLOYEE_ROOM_NO_FIELDS)): room.room_no,
            "姓名": payload.name.strip(),
            "性别": payload.gender.strip(),
        }
        optional_values: dict[str, str] = {
            "员工ID": payload.employee_id.strip(),
            "部门": payload.department.strip(),
            "岗位": payload.job_title.strip(),
            "联系方式": payload.phone.strip(),
            "倒班类型": payload.shift_type.strip(),
            "居住地址": payload.address.strip(),
            "押金是否缴纳": payload.deposit_paid.strip(),
            "是否签订协议": payload.agreement_signed.strip(),
            "备注": payload.remark.strip(),
        }
        existing_names = _table_field_names(employees)
        for key, value in optional_values.items():
            if value and key in existing_names:
                fields[key] = value

        client = BitableClient(
            app_token=employees.resource.app_token,
            app_id=config.app_id,
            app_secret=app_secret,
        )
        record = await client.create_record(employees.resource.table_id, fields)
        record_id = str(record.get("record_id") or "")

        synced = False
        try:
            mirror = await build_read_mirror_service(self.session)
            await mirror.sync_resource(employees.resource.id)
            synced = True
        except Exception:
            logger.warning(
                "入住记录已写入飞书，镜像即时同步失败（15 分钟定时同步会补上）",
                exc_info=True,
            )
        return DormitoryCheckinResult(
            record_id=record_id, room_no=room.room_no, synced=synced
        )

    async def _bound_tables(self) -> list[MirroredTable]:
        return await self.repo.list_bound_tables(PAGE_KEY_DORMITORY)
