"""Sync Feishu data to production tables — target router."""

import logging
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secrets import decrypt_secret
from app.modules.production.production_feishu_client import ProductionFeishuClient
from app.modules.production.production_feishu_models import ProductionFeishuConfig
from app.modules.production.models import ProductionPlan, SalesPlanDetail

logger = logging.getLogger(__name__)

# ── 生产计划飞书字段映射 ──
PLAN_FIELD_MAP = {
    "车间": "workshop",
    "产品": "product_name",
    "日期": "plan_date",
    "单位": "unit",
    "计划产量": "planned_yield",
    "实际完成": "actual_completion",
    "完成率": "completion_rate",
    "安环情况": "safety_status",
    "质量情况": "quality_status",
    "备注": "remarks",
}

# ── 销售计划执行表飞书字段映射 ──
SALES_FIELD_MAP = {
    "产品名称": "product_name",
    "单位": "unit",
    "上月已发货未开票": "last_month_delivered_uninvoiced",
    "2025年当月发货量": "current_year_delivered",
    "本月计划发货量": "month_planned_delivery",
    "本月已发货量": "month_delivered_qty",
    "未发货量": "undelivered_qty",
    "本月预计开票量": "month_planned_invoice",
    "已开票量": "invoiced_qty",
    "本月发货完成率（%）": "delivery_completion_rate",
    "上月底库存": "last_month_end_inventory",
    "本月预计产能": "month_planned_capacity",
    "本月底库存": "month_end_inventory",
    "备注": "remarks",
}

SYNC_TARGETS = {
    "production_plan": "生产计划",
    "sales_plan": "销售计划执行表",
    "fermentation_record": "发酵记录",
    "batch": "批次管理",
    "production_record": "生产记录",
    "material_balance": "物料平衡",
    "seed_culture": "种子培养",
    "broth_receive": "发酵液接收",
    "broth_pretreat": "预处理工艺",
    # 环保模块
    "wastewater": "废水监测",
    "exhaust_gas": "废气监测",
    "solid_waste": "固废台账",
    # DR 模块
    "dr_extraction": "DR 过滤萃取",
    "dr_chromatography": "DR 层析及一次结晶",
    "dr_refinement": "DR 一次精制",
    "dr_second_refinement": "DR 二次精制",
    "dr_third_refinement": "DR 三次精制",
    "dr_fourth_refinement": "DR 四次精制",
}


def _extract_text(field_value) -> str | None:
    if field_value is None:
        return None
    if isinstance(field_value, str):
        return field_value.strip() or None
    if isinstance(field_value, dict):
        return str(field_value.get("name") or field_value.get("text", "")).strip() or None
    if isinstance(field_value, list) and field_value:
        first = field_value[0]
        if isinstance(first, str):
            return first.strip() or None
        if isinstance(first, dict):
            return str(first.get("name") or first.get("text", "")).strip() or None
    return None


def _extract_number(field_value) -> float | None:
    if isinstance(field_value, dict) and field_value.get("type") == 2:
        vals = field_value.get("value") or []
        if vals and isinstance(vals[0], (int, float)):
            return float(vals[0])
    text = _extract_text(field_value)
    if text is None:
        return None
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


def _extract_date(ts) -> date | None:
    if ts is None:
        return None
    if isinstance(ts, (int, float)) and ts > 0:
        try:
            return datetime.fromtimestamp(ts / 1000).date()
        except (OSError, ValueError):
            return None
    text = _extract_text(ts)
    if text:
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None
    return None


async def _sync_production_plan(config: ProductionFeishuConfig, session: AsyncSession) -> dict:
    """从飞书同步生产计划数据"""
    app_secret = decrypt_secret(config.encrypted_app_secret)
    client = ProductionFeishuClient(
        app_id=config.app_id,
        app_secret=app_secret,
        app_token=config.bitable_app_token,
    )

    created = 0
    updated = 0
    page_token: str | None = None

    while True:
        result = await client.list_records(config.table_id, page_token=page_token)
        items = result["items"]
        for item in items:
            fields = item.get("fields") or {}

            mapped: dict = {}
            for feishu_name, db_name in PLAN_FIELD_MAP.items():
                val = fields.get(feishu_name)
                if db_name == "plan_date":
                    mapped[db_name] = _extract_date(val)
                elif db_name in ("planned_yield", "actual_completion", "completion_rate"):
                    mapped[db_name] = _extract_number(val)
                else:
                    mapped[db_name] = _extract_text(val)

            product_name = mapped.get("product_name") or config.product_name
            if not product_name:
                continue

            # 查重：按 产品+车间+日期 判断
            existing_result = await session.execute(
                select(ProductionPlan).where(
                    ProductionPlan.product_name == product_name,
                    ProductionPlan.workshop == mapped.get("workshop"),
                    ProductionPlan.plan_date == mapped.get("plan_date"),
                    ProductionPlan.is_deleted == False,
                )
            )
            record = existing_result.scalar_one_or_none()

            mapped["product_name"] = product_name
            mapped["source"] = "feishu"

            if record:
                for k, v in mapped.items():
                    if v is not None:
                        setattr(record, k, v)
                updated += 1
            else:
                session.add(ProductionPlan(**mapped))
                created += 1

        await session.flush()

        if not result["has_more"]:
            break
        page_token = result.get("page_token")

    logger.info("生产计划同步完成: created=%s, updated=%s", created, updated)
    return {"created": created, "updated": updated, "product": config.product_name}


async def _sync_sales_plan(config: ProductionFeishuConfig, session: AsyncSession) -> dict:
    """从飞书同步销售计划执行表数据"""
    app_secret = decrypt_secret(config.encrypted_app_secret)
    client = ProductionFeishuClient(app_id=config.app_id, app_secret=app_secret, app_token=config.bitable_app_token)

    created = 0; updated = 0
    page_token: str | None = None

    NUMBER_FIELDS = {"last_month_delivered_uninvoiced", "current_year_delivered", "month_planned_delivery",
                     "month_delivered_qty", "undelivered_qty", "month_planned_invoice", "invoiced_qty",
                     "delivery_completion_rate", "last_month_end_inventory", "month_planned_capacity",
                     "month_end_inventory"}

    while True:
        result = await client.list_records(config.table_id, page_token=page_token)
        for item in result["items"]:
            fields = item.get("fields") or {}
            mapped: dict = {}
            for feishu_name, db_name in SALES_FIELD_MAP.items():
                val = fields.get(feishu_name)
                if db_name in NUMBER_FIELDS:
                    mapped[db_name] = _extract_number(val)
                else:
                    mapped[db_name] = _extract_text(val)

            product_name = mapped.get("product_name") or config.product_name
            if not product_name:
                continue

            existing = await session.execute(
                select(SalesPlanDetail).where(
                    SalesPlanDetail.product_name == product_name,
                    SalesPlanDetail.is_deleted == False,
                )
            )
            record = existing.scalar_one_or_none()
            mapped["product_name"] = product_name
            mapped["source"] = "feishu"

            if record:
                for k, v in mapped.items():
                    if v is not None: setattr(record, k, v)
                updated += 1
            else:
                session.add(SalesPlanDetail(**mapped))
                created += 1
        await session.flush()
        if not result["has_more"]: break
        page_token = result.get("page_token")

    logger.info("销售计划同步完成: created=%s, updated=%s", created, updated)
    return {"created": created, "updated": updated, "product": config.product_name}


async def sync_config_by_target(config: ProductionFeishuConfig, session: AsyncSession) -> dict:
    """根据 sync_target 路由到对应的同步逻辑"""
    target = config.sync_target or "production_plan"
    if target == "production_plan":
        return await _sync_production_plan(config, session)
    elif target == "sales_plan":
        return await _sync_sales_plan(config, session)
    elif target == "fermentation_record":
        from app.modules.production.production_feishu_service import sync_config as fermentation_sync
        return await fermentation_sync(config, session)
    elif target == "seed_culture":
        from app.modules.production.seed_culture_sync import sync_seed_culture_to_table
        return await sync_seed_culture_to_table(config, session)
    elif target == "broth_receive":
        from app.modules.production.broth_receive_sync import sync_broth_receive
        return await sync_broth_receive(config, session)
    elif target == "broth_pretreat":
        from app.modules.production.pretreatment_sync import sync_pretreatment
        return await sync_pretreatment(config, session)
    elif target == "ceramic_feed":
        from app.modules.production.ceramic_feed_sync import sync_ceramic_feed
        return await sync_ceramic_feed(config, session)
    elif target == "ceramic_ops":
        from app.modules.production.ceramic_ops_sync import sync_ceramic_ops
        return await sync_ceramic_ops(config, session)
    elif target == "ceramic_clean":
        from app.modules.production.ceramic_clean_sync import sync_ceramic_clean
        return await sync_ceramic_clean(config, session)
    elif target == "ceramic_sep":
        from app.modules.production.ceramic_sep_sync import sync_ceramic_sep
        return await sync_ceramic_sep(config, session)
    elif target == "ceramic_equip":
        from app.modules.production.ceramic_equip_sync import sync_ceramic_equip
        return await sync_ceramic_equip(config, session)
    elif target == "decolor1":
        from app.modules.production.decolor1_sync import sync_decolor1
        return await sync_decolor1(config, session)
    elif target == "filter1":
        from app.modules.production.filter1_sync import sync_filter1
        return await sync_filter1(config, session)
    elif target == "conc1":
        from app.modules.production.conc1_sync import sync_conc1
        return await sync_conc1(config, session)
    elif target == "centrifuge1":
        from app.modules.production.centrifuge1_sync import sync_centrifuge1
        return await sync_centrifuge1(config, session)
    elif target == "recrystallize":
        from app.modules.production.recrystallize_sync import sync_recrystallize
        return await sync_recrystallize(config, session)
    elif target == "filter2":
        from app.modules.production.filter2_sync import sync_filter2
        return await sync_filter2(config, session)
    elif target == "conc2":
        from app.modules.production.conc2_sync import sync_conc2
        return await sync_conc2(config, session)
    elif target == "centrifuge2":
        from app.modules.production.centrifuge2_sync import sync_centrifuge2
        return await sync_centrifuge2(config, session)
    elif target == "dry":
        from app.modules.production.dry_sync import sync_dry
        return await sync_dry(config, session)
    elif target == "pack":
        from app.modules.production.pack_sync import sync_pack
        return await sync_pack(config, session)
    elif target == "dr_extraction":
        from app.modules.production.dr_feishu_sync import sync_dr_extraction
        return await sync_dr_extraction(config, session)
    elif target == "dr_chromatography":
        from app.modules.production.dr_chromatography_sync import sync_dr_chromatography
        return await sync_dr_chromatography(config, session)
    elif target == "dr_refinement":
        from app.modules.production.dr_refinement_sync import sync_dr_refinement
        return await sync_dr_refinement(config, session)
    elif target == "dr_second_refinement":
        from app.modules.production.dr_second_refinement_sync import sync_dr_second_refinement
        return await sync_dr_second_refinement(config, session)
    elif target == "dr_third_refinement":
        from app.modules.production.dr_third_refinement_sync import sync_dr_third_refinement
        return await sync_dr_third_refinement(config, session)
    elif target == "dr_fourth_refinement":
        from app.modules.production.dr_fourth_refinement_sync import sync_dr_fourth_refinement
        return await sync_dr_fourth_refinement(config, session)
    # ── 环保模块同步目标 ──
    elif target in ("wastewater", "exhaust_gas", "solid_waste"):
        from app.modules.environment.environment_feishu import sync_environment_table
        return await sync_environment_table(target, config, session)
    else:
        # batch, production_record, material_balance — 通用自动同步
        from app.modules.production.auto_sync_service import auto_sync_config
        return await auto_sync_config(config, session)
