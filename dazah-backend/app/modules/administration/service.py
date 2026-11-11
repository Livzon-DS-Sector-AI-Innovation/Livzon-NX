"""Administration business workflows.

覆盖「烟酒礼品管理」的飞书配置管理、只读镜像服务工厂与仪表台统计聚合。
"""

import asyncio
import logging
import uuid
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
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
    TobaccoGiftChartItem,
    TobaccoGiftDashboardStats,
)
from app.platform.integrations.feishu.auth import FeishuAuth
from app.platform.integrations.feishu.read_mirror import (
    ModuleFeishuReadMirrorService,
    ReadMirrorModels,
)

logger = logging.getLogger("dazah.administration")

#: 烟酒礼品两个镜像页面的 page key（与菜单、page_policy 登记保持一致）。
PAGE_KEY_TOBACCO_GIFT_ITEMS = "admin:tobacco-gift:items"
PAGE_KEY_TOBACCO_GIFT_RECORDS = "admin:tobacco-gift:records"
ADMINISTRATION_READ_PAGE_KEYS = frozenset(
    {PAGE_KEY_TOBACCO_GIFT_ITEMS, PAGE_KEY_TOBACCO_GIFT_RECORDS}
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


async def prune_resource_history(session: AsyncSession, resource_id: uuid.UUID) -> None:
    """同步成功后清理该数据表的非激活镜像版本与过期同步运行记录。

    平台镜像服务每轮全量插入新版本、只切换 active_mirror_version；行政模块
    15 分钟同步一次，不清理会让镜像表和同步记录无限增长。
    """
    resource = (
        await session.execute(
            select(AdministrationFeishuReadResource).where(
                AdministrationFeishuReadResource.id == resource_id,
                AdministrationFeishuReadResource.is_deleted.is_(False),
            )
        )
    ).scalars().first()
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
    *,
    inventory_available: bool,
) -> str:
    for record_id in record_ids:
        name = name_by_record.get(record_id)
        if name:
            return name
    if texts:
        return texts[0]
    if inventory_available:
        # 关联的物品已从物品清单删除（名称不可考），合并为一根柱子
        return "已删除物品"
    return f"物品·{record_ids[0][-6:]}"


def _extract_requisitions(
    table: MirroredTable | None,
    name_by_record: Mapping[str, str],
    *,
    inventory_available: bool,
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
            item_name = _resolve_item_name(
                texts,
                record_ids,
                name_by_record,
                inventory_available=inventory_available,
            )
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
        usage = _extract_requisitions(
            requisition,
            stock.name_by_record,
            inventory_available=inventory is not None and bool(inventory.records),
        )
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
