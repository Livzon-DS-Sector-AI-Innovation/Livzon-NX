"""Quality module Feishu Base sync service."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import false, select
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException, NotFoundException
from app.core.llm.encryption import decrypt_api_key
from app.modules.quality import repository
from app.modules.quality.models import (
    CAPA,
    CapaPlanTrack,
    Deviation,
    DeviationInvestigationPushRecord,
    QualityFeishuAppSettings,
    QualityFeishuEntitySetting,
)
from app.modules.quality.service.quality_feishu_material_groups import (
    MATERIAL_ENTITY_CODES,
)
from app.platform.identity.models import User
from app.platform.integrations.feishu.bitable import (
    BitableClient,
)
from app.platform.integrations.feishu.bitable import (
    _to_ms_timestamp as _to_ms_timestamp,
)

logger = logging.getLogger(__name__)
settings = get_settings()
SyncModel = Deviation | CAPA | DeviationInvestigationPushRecord | CapaPlanTrack
SKIP_REMOTE_FIELD = object()

QUALITY_PULL_ENTITY_LABELS: dict[str, str] = {
    "deviation_report_record": "报告记录",
    "deviation_investigation_push_record": "调查推送",
    "capa_ledger": "CAPA台账",
    "capa_plan_track": "CAPA计划跟踪",
    "oos_oot_report_record": "OOSOOT报告记录",
    "oos_oot_investigation_push": "OOSOOT调查推送记录",
    "oos_ledger": "OOS台账",
    "oot_ledger": "OOT台账",
    "oos_oot_product_department": "产品涉及部门",
    "complaint_ledger": "投诉台账",
    "return_application": "退货申请表",
    "return_ledger": "退回台账",
    "product_quality_mfn": "霉酚酸",
    "product_quality_dljs": "多拉菌素",
    "product_quality_lftt": "洛伐他汀",
    "product_quality_mftt": "美伐他汀",
    "product_quality_yslkms": "盐酸林可霉素",
    "product_quality_bbas": "L-苯丙氨酸",
    "product_quality_sas": "L-色氨酸",
    "supplier_qualification": "供应商资质",
}

QUALITY_FEISHU_ENTITY_ENV_FALLBACKS: dict[str, str] = {
    "capa_ledger": "QUALITY_FEISHU_CAPA_TABLE_ID",
    "deviation_report_record": "QUALITY_FEISHU_DEVIATION_REPORT_TABLE_ID",
    (
        "deviation_investigation_push_record"
    ): "QUALITY_FEISHU_DEVIATION_INVESTIGATION_PUSH_TABLE_ID",
    "capa_plan_track": "QUALITY_FEISHU_CAPA_PLAN_TABLE_ID",
    "department_contact": "QUALITY_DEPARTMENT_CONTACT_FEISHU_TABLE_ID",
    "change_ledger": "QUALITY_CHANGE_LEDGER_FEISHU_TABLE_ID",
    "change_action_plan": "QUALITY_CHANGE_ACTION_PLAN_FEISHU_TABLE_ID",
    "validation_master_plan": "QUALITY_VALIDATION_FEISHU_TABLE_ID",
    "validation_equipment_qualification": "QUALITY_VALIDATION_FEISHU_TABLE_ID",
    "validation_process": "QUALITY_VALIDATION_FEISHU_TABLE_ID",
    "validation_cleaning": "QUALITY_VALIDATION_FEISHU_TABLE_ID",
    "validation_other": "QUALITY_VALIDATION_FEISHU_TABLE_ID",
    "oos_oot_report_record": "QUALITY_OOS_OOT_REPORT_RECORD_TABLE_ID",
    "oos_oot_investigation_push": "QUALITY_OOS_OOT_INVESTIGATION_PUSH_TABLE_ID",
    "oos_ledger": "QUALITY_OOS_LEDGER_TABLE_ID",
    "oot_ledger": "QUALITY_OOT_LEDGER_TABLE_ID",
    "oos_oot_product_department": "QUALITY_OOS_OOT_PRODUCT_DEPARTMENT_TABLE_ID",
    "complaint_ledger": "QUALITY_COMPLAINT_LEDGER_TABLE_ID",
    "return_application": "QUALITY_RETURN_APPLICATION_TABLE_ID",
    "return_ledger": "QUALITY_RETURN_LEDGER_TABLE_ID",
    "product_quality_mfn": "QUALITY_PRODUCT_QUALITY_MFN_TABLE_ID",
    "product_quality_dljs": "QUALITY_PRODUCT_QUALITY_DLJS_TABLE_ID",
    "product_quality_lftt": "QUALITY_PRODUCT_QUALITY_LFTT_TABLE_ID",
    "product_quality_mftt": "QUALITY_PRODUCT_QUALITY_MFTT_TABLE_ID",
    "product_quality_yslkms": "QUALITY_PRODUCT_QUALITY_YSLKMS_TABLE_ID",
    "product_quality_bbas": "QUALITY_PRODUCT_QUALITY_BBAS_TABLE_ID",
    "product_quality_sas": "QUALITY_PRODUCT_QUALITY_SAS_TABLE_ID",
    "supplier_qualification": "",  # PREFILLS 中已硬编码，无需环境变量回退
    # ── 质量检验子模块 (DB-only, no env fallbacks) ──
    # 物品管理
    "qc_items_inventory": "",
    "qc_items_inbound": "",
    "qc_items_outbound": "",
    # 仪器管理
    "qc_instr_equipment": "",
    "qc_instr_maintenance": "",
    "qc_instr_calibration": "",
    "qc_instr_repair": "",
    "qc_instr_change": "",
    "qc_instr_contracts": "",
    "qc_instr_plans": "",
    "qc_instr_assets": "",
    # 成品检验 - 仅保留 DEFAULT_ENTITIES 中存在的客户特定子表
    "qc_finished_bbas_hanguang_k1": "",
    "qc_finished_bbas_weiduo_k2": "",
    "qc_finished_bbas_changmao_k3": "",
    "qc_finished_bbas_jinghai_k4": "",
    "qc_finished_bbas_xiehe_k5": "",
    "qc_finished_bbas_jiuling_k7": "",
    "qc_finished_bbas_jirong_k8": "",
    "qc_finished_bbas_yuanda_k9": "",
    "qc_finished_bbas_hongshan_k10": "",
    "qc_finished_bbas_bafeng_k11": "",
    "qc_finished_bbas_haitian_k12": "",
    "qc_finished_bbas_feed_q": "",
    "qc_finished_mvt_bt_k1": "",
    "qc_finished_mvt_tw_k2": "",
    "qc_finished_mvt_zh_k3": "",
    "qc_finished_mvt_tapi_k5": "",
    "qc_finished_lft_lp_k3": "",
    "qc_finished_lft_tapi_k4": "",
    "qc_finished_lft_gn_k6": "",
    "qc_finished_lft_jingxin_k7": "",
    "qc_finished_lft_jb_k9": "",
    "qc_finished_lft_jinbao_k10": "",
    "qc_finished_lft_lp_crude_k11": "",
    "qc_finished_dls_norbrook_k2": "",
    "qc_finished_dls_zenex_k10": "",
    "qc_finished_dls_microsules_k6": "",
    "qc_finished_dls_elanco_kr_k11": "",
    "qc_finished_dls_adwia_k12": "",
    "qc_finished_dls_qilu_k13": "",
    "qc_finished_dls_eurofarwa_k14": "",
    "qc_finished_dls_msd_k15": "",
    "qc_finished_dls_haoze_k16": "",
    "qc_finished_dls_vetni_k17": "",
    "qc_finished_dls_eva_k18": "",
    "qc_finished_dls_cronus_k19": "",
    "qc_finished_mpa_tapi_k1": "",
    "qc_finished_mpa_emcure_k2": "",
    "qc_finished_mpa_rakshit_k3": "",
    "qc_finished_mpa_apotex_k4": "",
    "qc_finished_mpa_sloara_k6": "",
    "qc_finished_mpa_concord_k7": "",
    "qc_finished_mpa_concord_high_spec_k11": "",
    "qc_finished_mpa_taiwan_china_k12": "",
    "qc_finished_mpa_biocon_k13": "",
    "qc_finished_mpa_dasami_k14": "",
    "qc_finished_mpa_fis_k15": "",
    "qc_finished_mpa_intas_k16": "",
    "qc_finished_lkms_internal": "",
    "qc_finished_lkms_usp": "",
    "qc_finished_lkms_k1": "",
    "qc_finished_lkms_k2": "",
    "qc_finished_lkms_k3": "",
    "qc_finished_boiler_water": "",
    # 固体/液体物料
    **{entity_code: "" for entity_code in MATERIAL_ENTITY_CODES},
}


@dataclass(slots=True)
class QualityFeishuEntityRuntimeConfig:
    app_token: str | None
    table_id: str | None
    is_enabled: bool
    enable_push_to_feishu: bool
    enable_pull_from_feishu: bool
    field_mappings: dict[str, str]


def _require_table_id(
    entity: QualityFeishuEntityRuntimeConfig | None,
) -> str:
    if entity is None or not entity.table_id:
        raise RuntimeError("飞书实体未配置 table_id")
    return entity.table_id


@dataclass(slots=True)
class QualityFeishuRuntimeConfig:
    app_id: str | None
    app_secret: str | None
    is_app_enabled: bool
    legacy_app_token: str | None
    entities: dict[str, QualityFeishuEntityRuntimeConfig]

    def is_enabled(self) -> bool:
        return self.is_app_enabled and bool(self.app_id) and bool(self.app_secret)

    def get_entity_config(
        self,
        entity_code: str,
        *,
        direction: str,
    ) -> QualityFeishuEntityRuntimeConfig | None:
        entity = self.entities.get(entity_code)
        if entity is None or not entity.is_enabled:
            return None
        if direction == "push" and not entity.enable_push_to_feishu:
            return None
        if direction == "pull" and not entity.enable_pull_from_feishu:
            return None
        resolved_app_token = entity.app_token or self.legacy_app_token
        if not resolved_app_token or not entity.table_id:
            return None
        return QualityFeishuEntityRuntimeConfig(
            app_token=resolved_app_token,
            table_id=_require_table_id(entity),
            is_enabled=entity.is_enabled,
            enable_push_to_feishu=entity.enable_push_to_feishu,
            enable_pull_from_feishu=entity.enable_pull_from_feishu,
            field_mappings=entity.field_mappings,
        )


def _extract_feishu_link(value: Any) -> str | None:
    """Normalize Feishu URL/link field shapes without persisting raw objects."""
    if value in (None, "", []):
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        for item in value:
            link = _extract_feishu_link(item)
            if link:
                return link
        return None
    if isinstance(value, dict):
        for key in ("link", "url", "href", "value", "text", "name"):
            link = _extract_feishu_link(value.get(key))
            if link:
                return link
        return None
    normalized = str(value).strip()
    return normalized or None


def _parse_feishu_datetime(value: Any) -> datetime | None:
    if value in (None, "", []):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value) / 1000, tz=UTC)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.isdigit():
            return datetime.fromtimestamp(int(raw) / 1000, tz=UTC)
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _normalize_text(value: Any) -> str | None:
    if value in (None, "", []):
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, list):
        parts = [_normalize_text(item) for item in value]
        normalized = [part for part in parts if part]
        return " / ".join(normalized) if normalized else None
    if isinstance(value, dict):
        for key in ("text", "name", "display_name", "en_name", "link", "value"):
            if key in value:
                normalized_value = _normalize_text(value[key])
                if normalized_value:
                    return normalized_value
        return None
    return str(value).strip() or None


def _parse_person_field(value: Any) -> list[dict[str, str]] | None:
    "解析飞书人员字段（[{id,name,en_name,ava"
    "tar_url,...}]）为 [{name, avatar"
    "_url, id}]。"
    if not isinstance(value, list):
        return None
    persons = []
    for item in value:
        if not isinstance(item, dict):
            continue
        person = {
            "name": str(
                item.get("name") or item.get("en_name") or item.get("text") or ""
            ),
            "avatar_url": str(item.get("avatar_url") or item.get("url") or ""),
            "id": str(item.get("id") or ""),
        }
        if person["name"] or person["avatar_url"] or person["id"]:
            persons.append(person)
    return persons or None


def _parse_attachment_field(value: Any) -> list[dict[str, Any]] | None:
    "解析飞书附件字段（[{name,url,type,size,"
    "tmp_url,...}]）为 [{name, url, t"
    "ype, size}]。"
    if not isinstance(value, list):
        return None
    attachments = []
    for item in value:
        if not isinstance(item, dict):
            continue
        attachment = {
            "name": str(item.get("name") or ""),
            "url": str(item.get("url") or item.get("tmp_url") or ""),
            "type": str(item.get("type") or ""),
            "size": item.get("size") or 0,
        }
        if attachment["url"]:
            attachments.append(attachment)
    return attachments or None


def _normalize_bool_from_yes_no(value: Any) -> bool | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    if normalized in {"是", "已确认", "true", "True"}:
        return True
    if normalized in {"否", "未确认", "false", "False"}:
        return False
    return None


def _normalize_review_result(value: Any) -> str | None:
    if isinstance(value, bool):
        return "approved" if value else "rejected"
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    if normalized in {"是", "已确认", "approved", "true", "True", "TRUE", "1", "通过"}:
        return "approved"
    if normalized in {
        "否",
        "已拒绝",
        "rejected",
        "false",
        "False",
        "FALSE",
        "0",
        "不通过",
    }:
        return "rejected"
    if normalized in {"已退回", "resubmitted"}:
        return "resubmitted"
    return normalized


def _to_feishu_review_option(value: str | None) -> str:
    normalized = _normalize_review_result(value)
    if normalized == "approved":
        return "通过"
    if normalized == "rejected":
        return "不通过"
    if normalized in {"通过", "不通过"}:
        return normalized
    return ""


def _to_feishu_url_field_value(value: str | None) -> dict[str, str] | str:
    normalized = (value or "").strip()
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return {
            "link": normalized,
            "text": normalized,
            "type": "url",
        }
    raise ValueError("偏差调查报告必须填写有效链接")


def _join_non_empty(parts: list[str | None], sep: str = "/") -> str | None:
    values = [part.strip() for part in parts if isinstance(part, str) and part.strip()]
    return sep.join(values) if values else None


def _looks_like_test_app_settings(
    app_id: str | None,
    app_secret: str | None,
) -> bool:
    normalized_app_id = (app_id or "").strip().lower()
    normalized_secret = (app_secret or "").strip().lower()
    return normalized_app_id in {
        "cli_app_seeded",
        "test_app_seeded",
    } or normalized_secret in {
        "cli_secret_seeded",
        "test_secret_seeded",
    }


def _fallback_runtime_entity(table_id: str | None) -> QualityFeishuEntityRuntimeConfig:
    return QualityFeishuEntityRuntimeConfig(
        app_token=None,
        table_id=table_id,
        is_enabled=bool(table_id),
        enable_push_to_feishu=bool(table_id),
        enable_pull_from_feishu=bool(table_id),
        field_mappings={},
    )


# Fallback field name mapping for product quality entities (when field_mappings is
# empty)
# Maps system field name → Chinese feishu field label
_PRODUCT_QUALITY_FIELD_FALLBACK: dict[str, str] = {
    "customer_name": "客户名称",
    "quality_standard": "质量标准",
    "shipping_trend_url": "历史发货趋势",
    "special_requirements": "特殊要求",
    "packaging_requirements": "包装要求",
    "label_requirements": "标签要求",
    "pallet_requirements": "发货打托要求",
    "target_market": "目标市场",
    "registration_status": "注册情况",
    "other_notes": "其他注意事项",
    "serial_number": "序号",
}


def _resolve_remote_field_name(
    entity: QualityFeishuEntityRuntimeConfig | None,
    system_field: str,
) -> str:
    if entity is None:
        return system_field
    # Try entity field_mappings first
    mapped = entity.field_mappings.get(system_field)
    if mapped:
        return mapped
    # Fallback: use built-in mapping for product quality fields
    if system_field in _PRODUCT_QUALITY_FIELD_FALLBACK:
        return _PRODUCT_QUALITY_FIELD_FALLBACK[system_field]
    return system_field


def _map_push_fields(
    entity: QualityFeishuEntityRuntimeConfig | None,
    fields: dict[str, Any],
) -> dict[str, Any]:
    return {
        _resolve_remote_field_name(entity, system_field): value
        for system_field, value in fields.items()
    }


def _coerce_remote_field_value(field_meta: dict[str, Any], value: Any) -> Any:
    ui_type = str(field_meta.get("ui_type") or "").strip()
    if ui_type == "User":
        if value in (None, "", []):
            return SKIP_REMOTE_FIELD
        if isinstance(value, str):
            normalized = value.strip()
            return [{"id": normalized}] if normalized else SKIP_REMOTE_FIELD
        if isinstance(value, dict):
            return [value]
        if isinstance(value, list):
            return value or SKIP_REMOTE_FIELD
        return SKIP_REMOTE_FIELD
    if ui_type in {"Lookup", "DuplexLink"}:
        return SKIP_REMOTE_FIELD
    if ui_type == "DateTime":
        if value in (None, ""):
            return SKIP_REMOTE_FIELD
        property_config = field_meta.get("property") or {}
        if property_config.get("date_formatter") == "yyyy-MM-dd":
            if isinstance(value, (int, float)):
                dt = datetime.fromtimestamp(float(value) / 1000, tz=UTC)
                return int(
                    datetime(dt.year, dt.month, dt.day, tzinfo=UTC).timestamp() * 1000
                )
            if isinstance(value, datetime):
                return int(
                    datetime(value.year, value.month, value.day, tzinfo=UTC).timestamp()
                    * 1000
                )
            if isinstance(value, date):
                return int(
                    datetime(value.year, value.month, value.day, tzinfo=UTC).timestamp()
                    * 1000
                )
    if ui_type == "Checkbox":
        normalized_bool = _normalize_bool_from_yes_no(value)
        if normalized_bool is not None:
            return normalized_bool
    return value


def _get_mapped_field_value(
    entity: QualityFeishuEntityRuntimeConfig | None,
    fields: dict[str, Any],
    system_field: str,
) -> Any:
    return fields.get(_resolve_remote_field_name(entity, system_field))


def _escape_feishu_filter_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _build_search_filter(
    entity: QualityFeishuEntityRuntimeConfig | None,
    conditions: list[tuple[str, str]],
    available_fields: set[str] | None = None,
) -> str | None:
    expressions: list[str] = []
    for system_field, value in conditions:
        remote_field = _resolve_remote_field_name(entity, system_field)
        if available_fields is not None and remote_field not in available_fields:
            continue
        expressions.append(
            f'CurrentValue.[{remote_field}] = "{_escape_feishu_filter_value(value)}"'
        )
    return " && ".join(expressions) or None


def _get_record_modified_at(record: dict[str, Any]) -> datetime | None:
    return _parse_feishu_datetime(
        record.get("last_modified_time") or record.get("created_time")
    )


def _to_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _has_local_changes_since_last_sync(model: SyncModel) -> bool:
    if not model.feishu_synced_at or not model.updated_at:
        return False
    updated_at = _to_utc_datetime(model.updated_at)
    synced_at = _to_utc_datetime(model.feishu_synced_at)
    if not updated_at or not synced_at:
        return False
    return updated_at > synced_at


def _has_remote_changes_since_last_sync(
    model: SyncModel, source_updated_at: datetime | None
) -> bool:
    if not model.feishu_synced_at or not source_updated_at:
        return False
    previous_source_updated_at = _to_utc_datetime(model.feishu_source_updated_at)
    if previous_source_updated_at is None:
        return True
    return source_updated_at > previous_source_updated_at


def _should_mark_conflict(model: SyncModel, source_updated_at: datetime | None) -> bool:
    return _has_local_changes_since_last_sync(
        model
    ) and _has_remote_changes_since_last_sync(model, source_updated_at)


def _build_conflict_message(source_updated_at: datetime | None) -> str:
    if source_updated_at is None:
        return "检测到系统与飞书 Base 均已更新，请人工确认后再处理同步冲突"
    return (
        "检测到系统与飞书 Base 均已更新，飞书最新修改时间为 "
        f"{source_updated_at.isoformat()}，请人工确认后再处理同步冲突"
    )


class QualityFeishuSync:
    async def _get_department_contacts(self, db: AsyncSession) -> list[dict[str, Any]]:
        return await _get_department_contacts_from_feishu(db)

    async def _resolve_runtime(self, db: AsyncSession) -> QualityFeishuRuntimeConfig:
        app_model = None
        rows: list[QualityFeishuEntitySetting] = []
        try:
            app_model = (
                (
                    await db.execute(
                        select(QualityFeishuAppSettings)
                        .where(QualityFeishuAppSettings.is_deleted.is_(False))
                        .order_by(QualityFeishuAppSettings.updated_at.desc())
                        .limit(1)
                    )
                )
                .scalars()
                .first()
            )
            rows = list(
                (
                    await db.execute(
                        select(QualityFeishuEntitySetting).where(
                            QualityFeishuEntitySetting.is_deleted.is_(False)
                        )
                    )
                )
                .scalars()
                .all()
            )
        except (OperationalError, ProgrammingError):
            # 无模块配置时禁用同步；不得回退登录应用。
            app_model = None
            rows = []

        app_id = ""
        app_secret = ""
        legacy_app_token = settings.QUALITY_FEISHU_APP_TOKEN
        is_app_enabled = bool(app_id and app_secret)
        if (
            app_model
            and app_model.is_enabled
            and app_model.app_id
            and app_model.app_secret
            and not _looks_like_test_app_settings(
                app_model.app_id, app_model.app_secret
            )
        ):
            app_id = app_model.app_id
            app_secret = decrypt_api_key(app_model.app_secret)
            legacy_app_token = app_model.app_token or legacy_app_token
            is_app_enabled = app_model.is_enabled

        entity_models = {row.entity_code: row for row in rows}
        entity_configs: dict[str, QualityFeishuEntityRuntimeConfig] = {}
        for entity_code, env_name in QUALITY_FEISHU_ENTITY_ENV_FALLBACKS.items():
            model = entity_models.get(entity_code)
            if model is not None:
                table_id = (model.base_table_id or "").strip() or None
                app_token = (model.app_token or "").strip() or legacy_app_token
                field_mappings = {
                    str(item.get("system_field")): str(item.get("feishu_field"))
                    for item in (model.field_mappings or [])
                    if isinstance(item, dict)
                    and item.get("system_field")
                    and item.get("feishu_field")
                }
                entity_configs[entity_code] = QualityFeishuEntityRuntimeConfig(
                    app_token=app_token,
                    table_id=table_id,
                    is_enabled=model.is_enabled and bool(table_id) and bool(app_token),
                    enable_push_to_feishu=model.enable_push_to_feishu,
                    enable_pull_from_feishu=model.enable_pull_from_feishu,
                    field_mappings=field_mappings,
                )
                continue

            fallback_table_id = getattr(settings, env_name, None)
            entity_configs[entity_code] = QualityFeishuEntityRuntimeConfig(
                app_token=legacy_app_token,
                table_id=fallback_table_id,
                is_enabled=bool(fallback_table_id and legacy_app_token),
                enable_push_to_feishu=bool(fallback_table_id),
                enable_pull_from_feishu=bool(fallback_table_id),
                field_mappings={},
            )

        # 加载数据库中存在但不在 QUALITY_FEISHU_ENTITY_ENV_FALLBACKS 中的实体
        # （如成品检验 qc_finished_internal、固体/液体物料 qc_solid_ys001 等）
        for entity_code, model in entity_models.items():
            if entity_code in entity_configs:
                continue
            table_id = (model.base_table_id or "").strip() or None
            app_token = (model.app_token or "").strip() or legacy_app_token
            field_mappings = {
                str(item.get("system_field")): str(item.get("feishu_field"))
                for item in (model.field_mappings or [])
                if isinstance(item, dict)
                and item.get("system_field")
                and item.get("feishu_field")
            }
            entity_configs[entity_code] = QualityFeishuEntityRuntimeConfig(
                app_token=app_token,
                table_id=table_id,
                is_enabled=model.is_enabled and bool(table_id) and bool(app_token),
                enable_push_to_feishu=model.enable_push_to_feishu,
                enable_pull_from_feishu=model.enable_pull_from_feishu,
                field_mappings=field_mappings,
            )

        return QualityFeishuRuntimeConfig(
            app_id=app_id,
            app_secret=app_secret,
            is_app_enabled=is_app_enabled,
            legacy_app_token=legacy_app_token,
            entities=entity_configs,
        )

    async def _upsert_record(
        self,
        db: AsyncSession,
        entity_code: str,
        table_id: str | None,
        record_id: str | None,
        fields: dict[str, Any],
        *,
        search_conditions: list[tuple[str, str]] | None = None,
    ) -> tuple[str, str]:
        runtime = await self._resolve_runtime(db)
        entity = runtime.get_entity_config(entity_code, direction="push")
        if not runtime.is_enabled() or not entity or not entity.app_token:
            raise AppException(
                message="质量模块飞书 Base 同步未启用，请先在「飞书设置」完成配置",
                status_code=400,
            )
        resolved_table_id = _require_table_id(entity)
        client = BitableClient(
            app_token=entity.app_token,
            app_id=runtime.app_id,
            app_secret=runtime.app_secret,
        )
        remote_fields = await client.list_fields(resolved_table_id)
        remote_field_names = {
            str(item.get("field_name")).strip()
            for item in remote_fields
            if item.get("field_name")
        }
        remote_field_map = {
            str(item.get("field_name")).strip(): item
            for item in remote_fields
            if item.get("field_name")
        }
        mapped_fields = {
            field_name: coerced_value
            for field_name, value in _map_push_fields(entity, fields).items()
            if field_name in remote_field_names
            for coerced_value in [
                _coerce_remote_field_value(remote_field_map[field_name], value)
            ]
            if coerced_value is not SKIP_REMOTE_FIELD
        }

        if record_id:
            record = await client.update_record(
                resolved_table_id, record_id, mapped_fields
            )
            return str(record.get("record_id") or record_id), resolved_table_id

        search_filter = _build_search_filter(
            entity,
            search_conditions or [],
            available_fields=remote_field_names,
        )
        if search_filter:
            try:
                records = await client.search_records(
                    resolved_table_id,
                    filter_str=search_filter,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    (
                        "Feishu search failed for %s with filter "
                        "%s, fallback to create: %s"
                    ),
                    entity_code,
                    search_filter,
                    exc,
                )
                records = []
            if records:
                existing_id = records[0].get("record_id")
                if existing_id:
                    record = await client.update_record(
                        resolved_table_id,
                        existing_id,
                        mapped_fields,
                    )
                    return str(
                        record.get("record_id") or existing_id
                    ), resolved_table_id

        record = await client.create_record(resolved_table_id, mapped_fields)
        return str(record.get("record_id", "")), resolved_table_id

    async def search_records(
        self,
        db: AsyncSession,
        entity_code: str,
        table_id: str | None = None,
        *,
        filter_str: str | None = None,
        field_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        runtime = await self._resolve_runtime(db)
        entity = runtime.get_entity_config(entity_code, direction="pull")
        if not runtime.is_enabled() or not entity or not entity.app_token:
            return []
        resolved_table_id = _require_table_id(entity)
        client = BitableClient(
            app_token=entity.app_token,
            app_id=runtime.app_id,
            app_secret=runtime.app_secret,
        )
        return await client.search_records(
            resolved_table_id,
            filter_str=filter_str,
            page_size=500,
            automatic_fields=True,
            field_names=field_names,
        )


feishu_sync = QualityFeishuSync()


async def _mark_sync_success(
    db: AsyncSession,
    model: SyncModel,
    *,
    table_id: str,
    record_id: str,
    direction: str,
    source_updated_at: datetime | None = None,
) -> None:
    synced_at = datetime.now(UTC)
    model.feishu_base_table_id = table_id
    model.feishu_base_record_id = record_id or model.feishu_base_record_id
    model.feishu_sync_status = "synced"
    model.feishu_last_sync_error = None
    model.feishu_last_sync_direction = direction
    model.feishu_synced_at = synced_at
    model.feishu_source_updated_at = source_updated_at or synced_at
    await db.commit()


async def _mark_sync_failed(
    db: AsyncSession,
    model: SyncModel,
    exc: Exception,
) -> None:
    model.feishu_sync_status = "failed"
    model.feishu_last_sync_error = str(exc)
    await db.commit()


async def _mark_sync_conflict(
    db: AsyncSession,
    model: SyncModel,
    *,
    table_id: str,
    record_id: str | None,
    source_updated_at: datetime | None,
    direction: str,
) -> None:
    model.feishu_base_table_id = table_id or model.feishu_base_table_id
    model.feishu_base_record_id = record_id or model.feishu_base_record_id
    model.feishu_sync_status = "conflict"
    model.feishu_last_sync_direction = direction
    model.feishu_last_sync_error = _build_conflict_message(source_updated_at)
    model.feishu_source_updated_at = source_updated_at or model.feishu_source_updated_at
    await db.commit()


async def _run_best_effort_sync(
    db: AsyncSession,
    *,
    entity_code: str,
    entity_label: str,
    entity_id: uuid.UUID,
    sync_coro: Any,
) -> None:
    runtime = await feishu_sync._resolve_runtime(db)
    if not runtime.is_enabled() or not runtime.get_entity_config(
        entity_code, direction="push"
    ):
        return
    try:
        await sync_coro
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to auto sync %s %s to Feishu Base: %s",
            entity_label,
            entity_id,
            exc,
        )


async def _resolve_deviation_reporter_name(
    db: AsyncSession, deviation: Deviation
) -> str:
    if deviation.discoverer:
        return deviation.discoverer
    if deviation.reporter_id:
        reporter = await db.get(User, deviation.reporter_id)
        if reporter and reporter.name:
            return reporter.name
    return ""


async def _resolve_deviation_reporter_contact(
    db: AsyncSession, deviation: Deviation
) -> dict[str, Any] | None:
    reporter_name = await _resolve_deviation_reporter_name(db, deviation)
    normalized_reporter_name = reporter_name.strip()
    normalized_department = (deviation.department or "").strip()
    if not normalized_reporter_name or not normalized_department:
        return None

    contacts = await _get_department_contacts_from_feishu(db)
    for contact in contacts:
        contact_name = str(contact.get("name") or "").strip()
        contact_department = str(contact.get("department") or "").strip()
        if (
            contact_name == normalized_reporter_name
            and contact_department == normalized_department
        ):
            return contact
    return None


async def _get_department_contacts_from_feishu(
    db: AsyncSession,
) -> list[dict[str, Any]]:
    from app.modules.quality.service.department_contacts import (
        get_department_contact_list_from_feishu,
    )

    result = await get_department_contact_list_from_feishu(
        db,
        page=1,
        page_size=1000,
    )
    items = result.get("items", [])
    return items if isinstance(items, list) else []


async def _resolve_contact_bitable_user_value(
    db: AsyncSession,
    name: str | None,
    *,
    department: str | None = None,
) -> list[dict[str, str]] | None:
    normalized_name = (name or "").strip()
    if not normalized_name:
        return None
    normalized_department = (department or "").strip()
    contacts = await _get_department_contacts_from_feishu(db)

    for require_department in (True, False):
        for contact in contacts:
            contact_name = str(contact.get("name") or "").strip()
            contact_department = str(contact.get("department") or "").strip()
            if contact_name != normalized_name:
                continue
            if (
                require_department
                and normalized_department
                and contact_department != normalized_department
            ):
                continue
            bitable_user_id = str(contact.get("bitable_user_id") or "").strip()
            if bitable_user_id:
                return [{"id": bitable_user_id}]
    return None


async def sync_deviation_report_record_to_feishu(
    db: AsyncSession,
    deviation_id: uuid.UUID,
    target_record_id: str | None = None,
) -> dict[str, Any]:
    deviation = await repository.get_deviation_by_id(db, deviation_id)
    if not deviation:
        raise NotFoundException(resource="偏差")
    runtime = await feishu_sync._resolve_runtime(db)
    entity = runtime.get_entity_config("deviation_report_record", direction="push")
    current_record_id = target_record_id or (
        deviation.feishu_base_record_id
        if entity
        and deviation.feishu_base_table_id
        and deviation.feishu_base_table_id == entity.table_id
        else None
    )

    reporter_contact = await _resolve_deviation_reporter_contact(db, deviation)
    report_time = deviation.discovery_date or deviation.created_at
    fields = {
        "偏差编号": deviation.deviation_code,
        "报告时间": _to_ms_timestamp(report_time),
        "偏差内容": deviation.description or deviation.title or "",
        "偏差报告": deviation.report_content or "",
        "涉及产品名称/批号": deviation.affected_items or "",
        "部门": deviation.department or "",
        "报告人": (
            [{"id": str(reporter_contact.get("bitable_user_id")).strip()}]
            if reporter_contact
            and str(reporter_contact.get("bitable_user_id") or "").strip()
            else None
        ),
        "报告状态": deviation.status or "",
    }
    record_id, table_id = await feishu_sync._upsert_record(
        db,
        "deviation_report_record",
        None,
        current_record_id,
        fields,
        search_conditions=[("偏差编号", deviation.deviation_code)],
    )
    return {"record_id": record_id, "table_id": table_id}


async def auto_sync_deviation_after_write(
    db: AsyncSession, deviation_id: uuid.UUID
) -> None:
    await _run_best_effort_sync(
        db,
        entity_code="deviation_report_record",
        entity_label="deviation_report_record",
        entity_id=deviation_id,
        sync_coro=sync_deviation_report_record_to_feishu(db, deviation_id),
    )


async def sync_capa_to_feishu(db: AsyncSession, capa_id: uuid.UUID) -> dict[str, Any]:
    capa = await repository.get_capa_by_id(db, capa_id)
    if not capa:
        raise NotFoundException(resource="CAPA")
    tracks = await repository.get_capa_plan_tracks_by_capa_ids(db, [capa.id])
    started_on = capa.created_at.date() if capa.created_at else None
    closure_on = (
        capa.closure_date.date()
        if isinstance(capa.closure_date, datetime)
        else capa.closure_date
    )
    qa_confirm_on = (
        capa.qa_confirm_date.date()
        if isinstance(capa.qa_confirm_date, datetime)
        else capa.qa_confirm_date
    )
    fields = {
        "CAPA编号": capa.capa_code,
        "启动日期": _to_ms_timestamp(started_on),
        "事件部门": capa.department or "",
        "涉及产品": capa.affected_product or "",
        "CAPA简述": capa.capa_content or capa.title or "",
        "CAPA效果评估": capa.evaluation_result or "",
        "关闭日期": _to_ms_timestamp(closure_on),
        "QA质量员": capa.qa_confirmer or "",
        "QA质量员确认日期": _to_ms_timestamp(qa_confirm_on),
        "CAPA状态": capa.status or "",
        "关联CAPA计划": "；".join(track.plan_content for track in tracks),
    }
    try:
        record_id, table_id = await feishu_sync._upsert_record(
            db,
            "capa_ledger",
            None,
            capa.feishu_base_record_id,
            fields,
            search_conditions=[("CAPA编号", capa.capa_code)],
        )
        await _mark_sync_success(
            db,
            capa,
            table_id=table_id,
            record_id=record_id,
            direction="system_to_base",
        )
        return {"record_id": record_id, "table_id": table_id}
    except Exception as exc:
        await _mark_sync_failed(db, capa, exc)
        raise


async def auto_sync_capa_after_write(db: AsyncSession, capa_id: uuid.UUID) -> None:
    await _run_best_effort_sync(
        db,
        entity_code="capa_ledger",
        entity_label="capa",
        entity_id=capa_id,
        sync_coro=sync_capa_to_feishu(db, capa_id),
    )


async def sync_deviation_investigation_push_record_to_feishu(
    db: AsyncSession,
    record_id: uuid.UUID,
) -> dict[str, Any]:
    record = await repository.get_deviation_investigation_push_record_by_id(
        db, record_id
    )
    if not record:
        raise NotFoundException(resource="偏差调查推送记录")
    deviation = await repository.get_deviation_by_id(db, record.deviation_id)
    department = deviation.department if deviation else None

    fields = {
        "偏差编号": record.deviation_code,
        "第N次推送": record.push_round,
        "偏差调查报告": _to_feishu_url_field_value(record.investigation_report_url),
        "提交日期": _to_ms_timestamp(record.submitted_at),
        "提交人": await _resolve_contact_bitable_user_value(
            db,
            record.submitter,
            department=department,
        ),
        "部门负责人审核结果": _to_feishu_review_option(record.department_head_result),
        "部门负责人审核时间": _to_ms_timestamp(record.department_head_reviewed_at),
        "QA": await _resolve_contact_bitable_user_value(db, record.qa_name),
        "QA审核结果": _to_feishu_review_option(record.qa_result),
        "QA审核时间": _to_ms_timestamp(record.qa_reviewed_at),
        "QA负责人": await _resolve_contact_bitable_user_value(db, record.qa_head_name),
        "QA负责人审核结果": _to_feishu_review_option(record.qa_head_result),
        "QA负责人审核时间": _to_ms_timestamp(record.qa_head_reviewed_at),
    }
    try:
        next_record_id, table_id = await feishu_sync._upsert_record(
            db,
            "deviation_investigation_push_record",
            None,
            record.feishu_base_record_id,
            fields,
            search_conditions=[
                ("偏差编号", record.deviation_code),
                ("第N次推送", record.push_round),
            ],
        )
        await _mark_sync_success(
            db,
            record,
            table_id=table_id,
            record_id=next_record_id,
            direction="system_to_base",
        )
        return {"record_id": next_record_id, "table_id": table_id}
    except Exception as exc:
        await _mark_sync_failed(db, record, exc)
        raise


async def auto_sync_deviation_investigation_push_record_after_write(
    db: AsyncSession, record_id: uuid.UUID
) -> None:
    await _run_best_effort_sync(
        db,
        entity_code="deviation_investigation_push_record",
        entity_label="deviation_investigation_push_record",
        entity_id=record_id,
        sync_coro=sync_deviation_investigation_push_record_to_feishu(db, record_id),
    )


async def sync_capa_plan_track_to_feishu(
    db: AsyncSession,
    track_id: uuid.UUID,
) -> dict[str, Any]:
    track = await repository.get_capa_plan_track_by_id(db, track_id)
    if not track:
        raise NotFoundException(resource="CAPA计划跟踪")
    fields = {
        "CAPA编号": track.capa_code,
        "计划内容": track.plan_content,
        "完成时间": _to_ms_timestamp(track.due_date),
        "责任人": track.owner_name or "",
        "责任人确认": "是" if track.owner_confirmed else "否",
        "部门负责人": track.department_head or "",
        "部门负责人确认": "是" if track.department_head_confirmed else "否",
        "进度": track.progress or "",
        "提醒状态": track.reminder_status,
        "关联CAPA编号": track.capa_code,
    }
    try:
        next_record_id, table_id = await feishu_sync._upsert_record(
            db,
            "capa_plan_track",
            None,
            track.feishu_base_record_id,
            fields,
            search_conditions=[
                ("CAPA编号", track.capa_code),
                ("计划内容", track.plan_content),
            ],
        )
        await _mark_sync_success(
            db,
            track,
            table_id=table_id,
            record_id=next_record_id,
            direction="system_to_base",
        )
        return {"record_id": next_record_id, "table_id": table_id}
    except Exception as exc:
        await _mark_sync_failed(db, track, exc)
        raise


async def auto_sync_capa_plan_track_after_write(
    db: AsyncSession, track_id: uuid.UUID
) -> None:
    await _run_best_effort_sync(
        db,
        entity_code="capa_plan_track",
        entity_label="capa_plan_track",
        entity_id=track_id,
        sync_coro=sync_capa_plan_track_to_feishu(db, track_id),
    )


async def sync_deviation_to_feishu(
    db: AsyncSession,
    deviation_id: uuid.UUID,
) -> dict[str, Any]:
    """Push one local deviation to the configured deviation ledger.

    This compatibility entry point retains the old record-id rule: a remote
    record may only be updated when its saved table id still matches the
    current runtime table, otherwise the upsert starts a new remote record.
    """
    deviation = await repository.get_deviation_by_id(db, deviation_id)
    if not deviation:
        raise ValueError("偏差不存在")
    runtime = await feishu_sync._resolve_runtime(db)
    entity = runtime.get_entity_config("deviation_ledger", direction="push")
    current_record_id = (
        deviation.feishu_base_record_id
        if entity and deviation.feishu_base_table_id == entity.table_id
        else None
    )
    related_capas = await repository.get_related_capas_for_deviation(
        db, deviation.id, deviation.deviation_code
    )
    fields = {
        "偏差编号": deviation.deviation_code,
        "产品名称/批号": _join_non_empty(
            [deviation.affected_items, deviation.batch_number]
        ),
        "偏差简要描述": deviation.description or deviation.title,
        "偏差是否曾发生": "是" if deviation.has_occurred_before else "否",
        "根本原因": deviation.root_cause_analysis or "",
        "偏差等级": deviation.level or "",
        "调查完成时间": _to_ms_timestamp(deviation.investigation_completed_at),
        "纠正预防措施": deviation.corrective_actions or "",
        "产品/物料处理结果": deviation.material_disposition or "",
        "是否关闭": "是" if deviation.status == "closed" else "否",
        "关闭时间": _to_ms_timestamp(
            deviation.status_updated_at if deviation.status == "closed" else None
        ),
        "关联capa": "、".join(related_capa.capa_code for related_capa in related_capas),
    }
    record_id, table_id = await feishu_sync._upsert_record(
        db,
        "deviation_ledger",
        None,
        current_record_id,
        fields,
        search_conditions=[("偏差编号", deviation.deviation_code)],
    )
    await _mark_sync_success(
        db,
        deviation,
        table_id=table_id,
        record_id=record_id,
        direction="system_to_base",
    )
    return {"record_id": record_id, "table_id": table_id}


async def _sync_deviation_investigation_push_records_from_feishu(
    db: AsyncSession,
    entity: QualityFeishuEntityRuntimeConfig | None,
    records: list[dict[str, Any]],
) -> tuple[int, int, int]:
    """Refresh existing local push-record snapshots without creating locals."""
    if entity is None:
        return 0, 0, 0
    synced = 0
    failed = 0
    conflicts = 0
    for remote in records:
        fields = remote.get("fields") or {}
        record_id = str(remote.get("record_id") or "")
        deviation_code = _normalize_text(
            _get_mapped_field_value(entity, fields, "偏差编号")
        )
        push_round = (
            _normalize_text(_get_mapped_field_value(entity, fields, "第N次推送"))
            or "第1次"
        )
        if not deviation_code:
            failed += 1
            continue
        deviation = await repository.get_deviation_by_code(db, deviation_code)
        if deviation is None:
            # Feishu remains the source for this record, but without a local
            # deviation there is no safe FK target for a local snapshot.
            synced += 1
            continue
        local_record = None
        if record_id:
            push_result = await db.execute(
                select(DeviationInvestigationPushRecord).where(
                    DeviationInvestigationPushRecord.feishu_base_record_id == record_id,
                    DeviationInvestigationPushRecord.is_deleted.is_(False),
                )
            )
            local_record = push_result.scalar_one_or_none()
        if local_record is None:
            get_push_record = getattr(
                repository,
                "get_deviation_investigation_push_record_by_deviation_and_round",
            )
            local_record = await get_push_record(db, deviation.id, push_round)
        if local_record is None:
            synced += 1
            continue
        source_updated_at = _get_record_modified_at(remote)
        if _should_mark_conflict(local_record, source_updated_at):
            await _mark_sync_conflict(
                db,
                local_record,
                table_id=_require_table_id(entity),
                record_id=record_id,
                source_updated_at=source_updated_at,
                direction="base_to_system",
            )
            conflicts += 1
            continue
        await repository.update_deviation_investigation_push_record(
            db,
            local_record,
            {
                "deviation_code": deviation_code,
                "push_round": push_round,
                "investigation_report_url": _extract_feishu_link(
                    _get_mapped_field_value(entity, fields, "偏差调查报告")
                ),
                "submitted_at": _parse_feishu_datetime(
                    _get_mapped_field_value(entity, fields, "提交日期")
                ),
                "submitter": _normalize_text(
                    _get_mapped_field_value(entity, fields, "提交人")
                ),
                "department_head": _normalize_text(
                    _get_mapped_field_value(entity, fields, "部门负责人")
                ),
                "department_head_result": _normalize_review_result(
                    _get_mapped_field_value(entity, fields, "部门负责人审核结果")
                ),
                "department_head_reviewed_at": _parse_feishu_datetime(
                    _get_mapped_field_value(entity, fields, "部门负责人审核时间")
                ),
                "qa_name": _normalize_text(
                    _get_mapped_field_value(entity, fields, "QA")
                ),
                "qa_result": _normalize_review_result(
                    _get_mapped_field_value(entity, fields, "QA审核结果")
                ),
                "qa_reviewed_at": _parse_feishu_datetime(
                    _get_mapped_field_value(entity, fields, "QA审核时间")
                ),
                "qa_head_name": _normalize_text(
                    _get_mapped_field_value(entity, fields, "QA负责人")
                ),
                "qa_head_result": _normalize_review_result(
                    _get_mapped_field_value(entity, fields, "QA负责人审核结果")
                ),
                "qa_head_reviewed_at": _parse_feishu_datetime(
                    _get_mapped_field_value(entity, fields, "QA负责人审核时间")
                ),
            },
        )
        await _mark_sync_success(
            db,
            local_record,
            table_id=_require_table_id(entity),
            record_id=record_id,
            direction="base_to_system",
            source_updated_at=source_updated_at,
        )
        synced += 1
    return synced, failed, conflicts


async def pull_quality_records_from_feishu(
    db: AsyncSession,
    entity_code: str | None = None,
) -> dict[str, int | str | None]:
    runtime = await feishu_sync._resolve_runtime(db)
    if not runtime.is_enabled():
        raise AppException(message="质量模块飞书 Base 同步未启用")

    if entity_code and entity_code not in QUALITY_PULL_ENTITY_LABELS:
        raise ValueError("不支持的飞书回拉实体")

    synced = 0
    failed = 0
    conflicts = 0
    deviation_entity = runtime.get_entity_config("deviation_ledger", direction="pull")
    capa_entity = runtime.get_entity_config("capa_ledger", direction="pull")
    plan_entity = runtime.get_entity_config("capa_plan_track", direction="pull")
    report_entity = runtime.get_entity_config(
        "deviation_investigation_push_record", direction="pull"
    )
    report_record_entity = runtime.get_entity_config(
        "deviation_report_record", direction="pull"
    )

    if entity_code == "deviation_ledger" and not deviation_entity:
        raise AppException(message="偏差台账飞书 Base 回拉未启用")
    if entity_code == "capa_ledger" and not capa_entity:
        raise AppException(message="CAPA台账飞书 Base 回拉未启用")
    if entity_code == "capa_plan_track" and not plan_entity:
        raise AppException(message="CAPA计划跟踪飞书 Base 回拉未启用")
    if entity_code == "deviation_investigation_push_record" and not report_entity:
        raise AppException(message="调查推送飞书 Base 回拉未启用")
    if entity_code == "deviation_report_record" and not report_record_entity:
        raise AppException(message="报告记录飞书 Base 回拉未启用")

    deviation_records = (
        await feishu_sync.search_records(db, "deviation_ledger", None)
        if deviation_entity and entity_code in (None, "deviation_ledger")
        else []
    )
    for record in deviation_records:
        if deviation_entity is None:
            continue
        fields = record.get("fields") or {}
        source_updated_at = _get_record_modified_at(record)
        deviation = None
        if record.get("record_id"):
            result = await db.execute(
                select(Deviation).where(
                    Deviation.feishu_base_record_id == record["record_id"],
                    Deviation.is_deleted.is_(False),
                )
            )
            deviation = result.scalar_one_or_none()
        code = _normalize_text(
            _get_mapped_field_value(deviation_entity, fields, "偏差编号")
        )
        if deviation is None and code:
            deviation = await repository.get_deviation_by_code(db, code)
        if deviation is None:
            if not code:
                failed += 1
                continue
            try:
                deviation = await repository.create_deviation(
                    db,
                    {
                        "deviation_code": code,
                        "title": _normalize_text(
                            _get_mapped_field_value(
                                deviation_entity, fields, "偏差简要描述"
                            )
                        )
                        or code,
                        "description": _normalize_text(
                            _get_mapped_field_value(
                                deviation_entity, fields, "偏差简要描述"
                            )
                        ),
                        "status": "closed"
                        if _normalize_bool_from_yes_no(
                            _get_mapped_field_value(
                                deviation_entity, fields, "是否关闭"
                            )
                        )
                        else "draft",
                    },
                )
            except IntegrityError:
                await db.rollback()
                deviation = await repository.get_deviation_by_code(db, code)
                if deviation is None:
                    raise
        if deviation is None:
            failed += 1
            continue
        if _should_mark_conflict(deviation, source_updated_at):
            await _mark_sync_conflict(
                db,
                deviation,
                table_id=_require_table_id(deviation_entity),
                record_id=record.get("record_id"),
                source_updated_at=source_updated_at,
                direction="base_to_system",
            )
            conflicts += 1
            continue
        deviation.description = (
            _normalize_text(
                _get_mapped_field_value(deviation_entity, fields, "偏差简要描述")
            )
            or deviation.description
        )
        deviation.affected_items = (
            _normalize_text(
                _get_mapped_field_value(deviation_entity, fields, "产品名称/批号")
            )
            or deviation.affected_items
        )
        deviation.root_cause_analysis = (
            _normalize_text(
                _get_mapped_field_value(deviation_entity, fields, "根本原因")
            )
            or deviation.root_cause_analysis
        )
        closed = _normalize_bool_from_yes_no(
            _get_mapped_field_value(deviation_entity, fields, "是否关闭")
        )
        if closed:
            deviation.status = "closed"
            deviation.status_updated_at = (
                _parse_feishu_datetime(
                    _get_mapped_field_value(deviation_entity, fields, "关闭时间")
                )
                or deviation.status_updated_at
            )
        await _mark_sync_success(
            db,
            deviation,
            table_id=_require_table_id(deviation_entity),
            record_id=record.get("record_id", ""),
            direction="base_to_system",
            source_updated_at=source_updated_at,
        )
        synced += 1

    capa_records = (
        await feishu_sync.search_records(
            db,
            "capa_ledger",
            None,
        )
        if capa_entity and entity_code in (None, "capa_ledger")
        else []
    )
    for record in capa_records:
        if capa_entity is None:
            continue
        fields = record.get("fields", {})
        source_updated_at = _get_record_modified_at(record)
        capa: CAPA | None = None
        if record.get("record_id"):
            capa_result = await db.execute(
                select(CAPA).where(
                    CAPA.feishu_base_record_id == record["record_id"],
                    CAPA.is_deleted.is_(False),
                )
            )
            capa = capa_result.scalar_one_or_none()
        if not capa:
            code = _normalize_text(
                _get_mapped_field_value(capa_entity, fields, "CAPA编号")
            )
            if code:
                capa = await repository.get_capa_by_code(db, code)
        if not capa:
            code = _normalize_text(
                _get_mapped_field_value(capa_entity, fields, "CAPA编号")
            )
            if not code:
                failed += 1
                continue
            capa_content = _normalize_text(
                _get_mapped_field_value(capa_entity, fields, "CAPA简述")
            )
            closure_at = _parse_feishu_datetime(
                _get_mapped_field_value(capa_entity, fields, "关闭日期")
            )
            capa = await repository.create_capa(
                db,
                {
                    "capa_code": code,
                    "title": capa_content or code,
                    "status": _normalize_text(
                        _get_mapped_field_value(capa_entity, fields, "CAPA状态")
                    )
                    or "draft",
                    "department": _normalize_text(
                        _get_mapped_field_value(capa_entity, fields, "事件部门")
                    ),
                    "affected_product": _normalize_text(
                        _get_mapped_field_value(capa_entity, fields, "涉及产品")
                    ),
                    "capa_content": capa_content,
                    "evaluation_result": _normalize_text(
                        _get_mapped_field_value(capa_entity, fields, "CAPA效果评估")
                    ),
                    "qa_confirmer": _normalize_text(
                        _get_mapped_field_value(capa_entity, fields, "QA质量员")
                    ),
                    "qa_confirm_date": _parse_feishu_datetime(
                        _get_mapped_field_value(capa_entity, fields, "QA质量员确认日期")
                    ),
                    "closure_date": closure_at,
                    "status_updated_at": closure_at,
                },
            )
        if capa is None:
            failed += 1
            continue
        if _should_mark_conflict(capa, source_updated_at):
            await _mark_sync_conflict(
                db,
                capa,
                table_id=_require_table_id(capa_entity),
                record_id=record.get("record_id"),
                source_updated_at=source_updated_at,
                direction="base_to_system",
            )
            conflicts += 1
            continue

        capa.department = (
            _normalize_text(_get_mapped_field_value(capa_entity, fields, "事件部门"))
            or capa.department
        )
        capa.affected_product = (
            _normalize_text(_get_mapped_field_value(capa_entity, fields, "涉及产品"))
            or capa.affected_product
        )
        capa.capa_content = (
            _normalize_text(_get_mapped_field_value(capa_entity, fields, "CAPA简述"))
            or capa.capa_content
        )
        capa.evaluation_result = (
            _normalize_text(
                _get_mapped_field_value(capa_entity, fields, "CAPA效果评估")
            )
            or capa.evaluation_result
        )
        capa.qa_confirmer = (
            _normalize_text(_get_mapped_field_value(capa_entity, fields, "QA质量员"))
            or capa.qa_confirmer
        )
        capa.qa_confirm_date = (
            _parse_feishu_datetime(
                _get_mapped_field_value(capa_entity, fields, "QA质量员确认日期")
            )
            or capa.qa_confirm_date
        )
        capa.closure_date = (
            _parse_feishu_datetime(
                _get_mapped_field_value(capa_entity, fields, "关闭日期")
            )
            or capa.closure_date
        )
        capa.status = (
            _normalize_text(_get_mapped_field_value(capa_entity, fields, "CAPA状态"))
            or capa.status
        )
        await _mark_sync_success(
            db,
            capa,
            table_id=_require_table_id(capa_entity),
            record_id=record.get("record_id", ""),
            direction="base_to_system",
            source_updated_at=source_updated_at,
        )
        synced += 1

    plan_records = (
        await feishu_sync.search_records(
            db,
            "capa_plan_track",
            None,
        )
        if plan_entity and entity_code in (None, "capa_plan_track")
        else []
    )
    for record in plan_records:
        if plan_entity is None:
            continue
        fields = record.get("fields", {})
        source_updated_at = _get_record_modified_at(record)
        capa_code = _normalize_text(
            _get_mapped_field_value(plan_entity, fields, "CAPA编号")
        )
        plan_content = _normalize_text(
            _get_mapped_field_value(plan_entity, fields, "计划内容")
        )
        if not capa_code or not plan_content:
            failed += 1
            continue

        plan_result = await db.execute(
            select(CapaPlanTrack).where(
                CapaPlanTrack.is_deleted.is_(False),
                (
                    (CapaPlanTrack.feishu_base_record_id == record.get("record_id"))
                    if record.get("record_id")
                    else false()
                )
                | (
                    (CapaPlanTrack.capa_code == capa_code)
                    & (CapaPlanTrack.plan_content == plan_content)
                ),
            )
        )
        track: CapaPlanTrack | None = plan_result.scalar_one_or_none()
        if not track:
            capa = await repository.get_capa_by_code(db, capa_code)
            if not capa:
                capa = await repository.create_capa(
                    db,
                    {
                        "capa_code": capa_code,
                        "title": capa_code,
                        "status": "draft",
                    },
                )
            due_date = _parse_feishu_datetime(
                _get_mapped_field_value(plan_entity, fields, "完成时间")
            )
            track = await repository.create_capa_plan_track(
                db,
                {
                    "capa_id": capa.id,
                    "capa_code": capa.capa_code,
                    "plan_content": plan_content,
                    "due_date": due_date.date() if due_date else None,
                    "owner_name": _normalize_text(
                        _get_mapped_field_value(plan_entity, fields, "责任人")
                    ),
                    "owner_confirmed": _normalize_bool_from_yes_no(
                        _get_mapped_field_value(plan_entity, fields, "责任人确认")
                    )
                    or False,
                    "department_head": _normalize_text(
                        _get_mapped_field_value(plan_entity, fields, "部门负责人")
                    ),
                    "department_head_confirmed": _normalize_bool_from_yes_no(
                        _get_mapped_field_value(plan_entity, fields, "部门负责人确认")
                    )
                    or False,
                    "progress": _normalize_text(
                        _get_mapped_field_value(plan_entity, fields, "进度")
                    ),
                    "reminder_status": _normalize_text(
                        _get_mapped_field_value(plan_entity, fields, "提醒状态")
                    )
                    or "pending",
                },
            )
        if _should_mark_conflict(track, source_updated_at):
            await _mark_sync_conflict(
                db,
                track,
                table_id=_require_table_id(plan_entity),
                record_id=record.get("record_id"),
                source_updated_at=source_updated_at,
                direction="base_to_system",
            )
            conflicts += 1
            continue

        track.owner_name = (
            _normalize_text(_get_mapped_field_value(plan_entity, fields, "责任人"))
            or track.owner_name
        )
        owner_confirmed = _normalize_bool_from_yes_no(
            _get_mapped_field_value(plan_entity, fields, "责任人确认")
        )
        if owner_confirmed is not None:
            track.owner_confirmed = owner_confirmed
        track.department_head = (
            _normalize_text(_get_mapped_field_value(plan_entity, fields, "部门负责人"))
            or track.department_head
        )
        dept_head_confirmed = _normalize_bool_from_yes_no(
            _get_mapped_field_value(plan_entity, fields, "部门负责人确认")
        )
        if dept_head_confirmed is not None:
            track.department_head_confirmed = dept_head_confirmed
        track.progress = (
            _normalize_text(_get_mapped_field_value(plan_entity, fields, "进度"))
            or track.progress
        )
        track.reminder_status = (
            _normalize_text(_get_mapped_field_value(plan_entity, fields, "提醒状态"))
            or track.reminder_status
        )
        due_date = _parse_feishu_datetime(
            _get_mapped_field_value(plan_entity, fields, "完成时间")
        )
        track.due_date = due_date.date() if due_date else track.due_date
        await _mark_sync_success(
            db,
            track,
            table_id=_require_table_id(plan_entity),
            record_id=record.get("record_id", ""),
            direction="base_to_system",
            source_updated_at=source_updated_at,
        )
        synced += 1

    deviation_report_records = (
        await feishu_sync.search_records(
            db,
            "deviation_investigation_push_record",
            None,
        )
        if report_entity
        and entity_code in (None, "deviation_investigation_push_record")
        else []
    )
    if entity_code in (None, "deviation_investigation_push_record"):
        (
            push_synced,
            push_failed,
            push_conflicts,
        ) = await _sync_deviation_investigation_push_records_from_feishu(
            db, report_entity, deviation_report_records
        )
        synced += push_synced
        failed += push_failed
        conflicts += push_conflicts

    deviation_report_record_records = (
        await feishu_sync.search_records(
            db,
            "deviation_report_record",
            None,
        )
        if report_record_entity and entity_code == "deviation_report_record"
        else []
    )
    if entity_code == "deviation_report_record":
        synced += len(deviation_report_record_records)

    return {
        "entity_code": entity_code,
        "entity_label": QUALITY_PULL_ENTITY_LABELS.get(entity_code)
        if entity_code
        else None,
        "synced": synced,
        "failed": failed,
        "conflicts": conflicts,
    }


def _build_conflict_item(
    *,
    entity_type: str,
    entity_label: str,
    entity_id: uuid.UUID,
    record_code: str,
    record_title: str | None,
    route_path: str,
    model: SyncModel,
) -> dict[str, Any]:
    return {
        "entity_type": entity_type,
        "entity_label": entity_label,
        "entity_id": entity_id,
        "record_code": record_code,
        "record_title": record_title,
        "route_path": route_path,
        "feishu_base_table_id": model.feishu_base_table_id,
        "feishu_base_record_id": model.feishu_base_record_id,
        "feishu_sync_status": model.feishu_sync_status,
        "feishu_last_sync_error": model.feishu_last_sync_error,
        "feishu_last_sync_direction": model.feishu_last_sync_direction,
        "feishu_synced_at": model.feishu_synced_at,
        "feishu_source_updated_at": model.feishu_source_updated_at,
        "updated_at": model.updated_at,
        "created_at": model.created_at,
    }


async def get_quality_sync_conflicts(
    db: AsyncSession, *, limit: int = 50
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    deviations = (
        (
            await db.execute(
                select(Deviation)
                .where(
                    Deviation.is_deleted.is_(False),
                    Deviation.feishu_sync_status == "conflict",
                )
                .order_by(Deviation.updated_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    results.extend(
        _build_conflict_item(
            entity_type="deviation",
            entity_label="偏差台账",
            entity_id=item.id,
            record_code=item.deviation_code,
            record_title=item.title,
            route_path="/quality/deviations",
            model=item,
        )
        for item in deviations
    )

    capas = (
        (
            await db.execute(
                select(CAPA)
                .where(
                    CAPA.is_deleted.is_(False), CAPA.feishu_sync_status == "conflict"
                )
                .order_by(CAPA.updated_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    results.extend(
        _build_conflict_item(
            entity_type="capa",
            entity_label="CAPA台账",
            entity_id=item.id,
            record_code=item.capa_code,
            record_title=item.title or item.capa_content,
            route_path="/quality/capas",
            model=item,
        )
        for item in capas
    )

    push_records = (
        (
            await db.execute(
                select(DeviationInvestigationPushRecord)
                .where(
                    DeviationInvestigationPushRecord.is_deleted.is_(False),
                    DeviationInvestigationPushRecord.feishu_sync_status == "conflict",
                )
                .order_by(DeviationInvestigationPushRecord.updated_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    results.extend(
        _build_conflict_item(
            entity_type="deviation_investigation_push_record",
            entity_label="偏差调查推送",
            entity_id=item.id,
            record_code=item.deviation_code,
            record_title=item.push_round,
            route_path="/quality/deviations/investigations",
            model=item,
        )
        for item in push_records
    )

    plan_tracks = (
        (
            await db.execute(
                select(CapaPlanTrack)
                .where(
                    CapaPlanTrack.is_deleted.is_(False),
                    CapaPlanTrack.feishu_sync_status == "conflict",
                )
                .order_by(CapaPlanTrack.updated_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    results.extend(
        _build_conflict_item(
            entity_type="capa_plan_track",
            entity_label="CAPA计划跟踪",
            entity_id=item.id,
            record_code=item.capa_code,
            record_title=item.plan_content,
            route_path="/quality/capas/plans",
            model=item,
        )
        for item in plan_tracks
    )

    results.sort(key=lambda item: item["updated_at"], reverse=True)
    return results[:limit]
