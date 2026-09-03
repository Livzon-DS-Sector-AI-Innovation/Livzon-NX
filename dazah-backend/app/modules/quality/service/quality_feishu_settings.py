"""Quality Feishu settings service."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.llm.encryption import decrypt_api_key, encrypt_api_key, mask_api_key
from app.core.llm.exceptions import LLMConfigError
from app.modules.quality.models import (
    QualityFeishuAppSettings,
    QualityFeishuEntitySetting,
)
from app.modules.quality.schemas.feishu_settings import (
    QualityFeishuAppSettingsDetail,
    QualityFeishuEntityFieldMappingBundle,
    QualityFeishuEntitySettingItem,
    QualityFeishuFieldMappingItem,
    QualityFeishuFieldOption,
    QualityFeishuSettingsTestResult,
    QualityFeishuSystemFieldOption,
    QualityFeishuTableOption,
    UpdateQualityFeishuAppSettingsRequest,
    UpdateQualityFeishuEntitySettingRequest,
)
from app.modules.quality.service.quality_feishu_material_groups import (
    MATERIAL_DEFAULT_QUALITY_FEISHU_ENTITIES,
    MATERIAL_ENTITY_PREFILLS,
)
from app.platform.integrations.feishu.auth import FeishuAuth
from app.platform.integrations.feishu.utils import (
    build_bitable_client,
    resolve_bitable_reference,
)

logger = logging.getLogger(__name__)

settings = get_settings()

_FEISHU_IDENTIFIER_PATTERN = re.compile(
    r"\b(?:bascn?|tbl|cli_)[A-Za-z0-9_-]{4,}\b",
    re.IGNORECASE,
)


def _mask_feishu_identifier(value: str | None) -> str:
    normalized = (value or "").strip()
    if len(normalized) <= 8:
        return "****"
    return f"{normalized[:4]}****{normalized[-4:]}"


def _sanitize_feishu_error_message(message: str) -> str:
    return _FEISHU_IDENTIFIER_PATTERN.sub(
        lambda match: _mask_feishu_identifier(match.group()),
        message,
    )


def _raise_feishu_metadata_error(action: str, exc: Exception) -> None:
    detail = _sanitize_feishu_error_message(str(exc))
    raise ValueError(f"飞书元数据{action}失败：{detail}") from exc


# 偏差报告新建表单链接（飞书多维表格表单）
DEVIATION_REPORT_FORM_URL = (
    "https://j0eukrlohu.feishu.cn/share/base/form/shrcnPO2JJt1gEVoMWHXtPUxske"
)

# 偏差调查推送新建表单链接（飞书多维表格表单）
DEVIATION_INVESTIGATION_PUSH_FORM_URL = (
    "https://j0eukrlohu.feishu.cn/share/base/form/shrcnzeKBo8EJze3h00kpsbxRVo"
)

# OOSOOT报告新建表单链接（飞书多维表格表单）
OOS_OOT_REPORT_FORM_URL = (
    "https://j0eukrlohu.feishu.cn/share/base/form/shrcnQrwet0LSPEL2RLFuGaLvub"
)

# OOSOOT调查推送新建表单链接（飞书多维表格表单）
OOS_OOT_INVESTIGATION_PUSH_FORM_URL = (
    "https://j0eukrlohu.feishu.cn/share/base/form/shrcnBFO62RSpL99u5sCLF9UCLf"
)

# Base/table identifiers are deployment data, not source-code defaults. Keep
# existing database values intact and require new deployments to configure
# identifiers through the module settings/environment path.
DEVIATION_REPORT_RECORD_APP_TOKEN = ""
DEVIATION_REPORT_RECORD_TABLE_ID = ""
OOS_OOT_REPORT_RECORD_APP_TOKEN = ""
OOS_OOT_REPORT_RECORD_TABLE_ID = ""
OOS_OOT_INVESTIGATION_PUSH_APP_TOKEN = ""
OOS_OOT_INVESTIGATION_PUSH_TABLE_ID = ""

DEFAULT_QUALITY_FEISHU_ENTITIES: list[tuple[str, str, str, int]] = [
    ("deviation_report_record", "报告记录", "偏差管理", 10),
    ("deviation_investigation_push_record", "调查推送", "偏差管理", 20),
    ("deviation_ledger", "偏差台账", "偏差管理", 30),
    ("capa_ledger", "CAPA台账", "CAPA管理", 40),
    ("capa_plan_track", "计划跟踪", "CAPA管理", 50),
    ("department_contact", "部门联系人", "部门联系人", 60),
    ("validation_master_plan", "验证主计划", "验证与确认", 70),
    ("validation_equipment_qualification", "设备确认", "验证与确认", 80),
    ("validation_process", "工艺验证", "验证与确认", 90),
    ("validation_cleaning", "清洁验证", "验证与确认", 100),
    ("validation_other", "其他验证", "验证与确认", 110),
    # 验证主计划/QC验证 年度子表：按年各配一张飞书表，未配置年度实体时页面
    # 回落到验证总表（主计划）或提示未配置（QC验证）
    ("validation_master_plan_2024", "验证主计划-2024年", "验证与确认", 111),
    ("validation_master_plan_2025", "验证主计划-2025年", "验证与确认", 112),
    ("validation_master_plan_2026", "验证主计划-2026年", "验证与确认", 113),
    ("validation_master_plan_2027", "验证主计划-2027年", "验证与确认", 114),
    ("validation_master_plan_2028", "验证主计划-2028年", "验证与确认", 115),
    ("validation_qc_2024", "QC验证-2024年", "验证与确认", 116),
    ("validation_qc_2025", "QC验证-2025年", "验证与确认", 117),
    ("validation_qc_2026", "QC验证-2026年", "验证与确认", 118),
    ("validation_qc_2027", "QC验证-2027年", "验证与确认", 119),
    ("validation_qc_2028", "QC验证-2028年", "验证与确认", 120),
    ("change_ledger", "变更台账", "变更控制", 120),
    ("change_action_plan", "变更计划", "变更控制", 130),
    # OOS/OOT 管理
    ("oos_oot_report_record", "OOSOOT报告记录", "OOS/OOT管理", 140),
    ("oos_oot_investigation_push", "OOSOOT调查推送记录", "OOS/OOT管理", 150),
    ("oos_ledger", "OOS台账", "OOS/OOT管理", 160),
    ("oot_ledger", "OOT台账", "OOS/OOT管理", 170),
    ("oot_limit_product", "OOT限度产品", "OOS/OOT管理", 175),
    ("oot_limit_item", "OOT限度项目", "OOS/OOT管理", 176),
    ("oos_oot_product_department", "产品涉及部门", "OOS/OOT管理", 180),
    # 投诉与退货召回管理
    ("complaint_ledger", "投诉台账", "投诉管理", 190),
    ("return_application", "退货申请表", "退货与召回管理", 200),
    ("return_ledger", "退回台账", "退货与召回管理", 210),
    ("return_recall_ledger", "退货/召回台账", "退货与召回管理", 211),
    # 供应商管理
    ("supplier_ledger", "供应商台账", "供应商管理", 214),
    ("supplier_qualification", "供应商资质", "供应商管理", 215),
    # 产品质量客户标准
    ("product_quality_ledger", "产品质量台账", "产品质量", 219),
    ("product_quality_standard_item", "产品质量标准项目", "产品质量", 219),
    ("product_quality_mfn", "霉酚酸", "产品质量", 220),
    ("product_quality_dljs", "多拉菌素", "产品质量", 230),
    ("product_quality_lftt", "洛伐他汀", "产品质量", 240),
    ("product_quality_mftt", "美伐他汀", "产品质量", 250),
    ("product_quality_yslkms", "盐酸林可霉素", "产品质量", 260),
    ("product_quality_bbas", "L-苯丙氨酸", "产品质量", 270),
    ("product_quality_sas", "L-色氨酸", "产品质量", 280),
    # 质量检验 - 成品检验补充真实子表
    ("qc_finished_bbas_hanguang_k1", "汉光（K1）", "成品检验", 294),
    ("qc_finished_bbas_weiduo_k2", "维多（K2）", "成品检验", 295),
    ("qc_finished_bbas_changmao_k3", "常茂（K3）", "成品检验", 296),
    ("qc_finished_bbas_jinghai_k4", "晶海（k4）", "成品检验", 297),
    ("qc_finished_bbas_xiehe_k5", "协和（K5）", "成品检验", 298),
    ("qc_finished_bbas_jiuling_k7", "久凌（K7）", "成品检验", 299),
    ("qc_finished_bbas_jirong_k8", "冀荣（k8）", "成品检验", 300),
    ("qc_finished_bbas_yuanda_k9", "远大（K9）", "成品检验", 301),
    ("qc_finished_bbas_hongshan_k10", "红衫（K10）未做", "成品检验", 302),
    ("qc_finished_bbas_bafeng_k11", "八峰（k11）", "成品检验", 303),
    ("qc_finished_bbas_haitian_k12", "海天（k12）", "成品检验", 304),
    ("qc_finished_bbas_feed_q", "饲料（Q）", "成品检验", 305),
    ("qc_finished_mvt_bt_k1", "BT-K1", "成品检验", 306),
    ("qc_finished_mvt_tw_k2", "TW-K2", "成品检验", 307),
    ("qc_finished_mvt_zh_k3", "ZH-K3（未做）", "成品检验", 308),
    ("qc_finished_mvt_tapi_k5", "TAPI-K5", "成品检验", 309),
    ("qc_finished_lft_lp_k3", "LP-K3", "成品检验", 310),
    ("qc_finished_lft_tapi_k4", "TAPI-K4", "成品检验", 311),
    ("qc_finished_lft_gn_k6", "GN-K6", "成品检验", 312),
    ("qc_finished_lft_jingxin_k7", "京新-K7", "成品检验", 313),
    ("qc_finished_lft_jb_k9", "JB-K9", "成品检验", 314),
    ("qc_finished_lft_jinbao_k10", "金宝-K10", "成品检验", 315),
    ("qc_finished_lft_lp_crude_k11", "LP粗品-K11", "成品检验", 316),
    ("qc_finished_dls_norbrook_k2", "Norbrook-K2", "成品检验", 317),
    ("qc_finished_dls_zenex_k10", "Zenex-K10", "成品检验", 318),
    ("qc_finished_dls_microsules_k6", "Microsules-K6", "成品检验", 319),
    ("qc_finished_dls_elanco_kr_k11", "Elanco韩国-K11", "成品检验", 320),
    ("qc_finished_dls_adwia_k12", "ADWIA-K12", "成品检验", 321),
    ("qc_finished_dls_qilu_k13", "齐鲁动保-K13", "成品检验", 322),
    ("qc_finished_dls_eurofarwa_k14", "EUROFARWA-K14", "成品检验", 323),
    ("qc_finished_dls_msd_k15", "MSD-K15", "成品检验", 324),
    ("qc_finished_dls_haoze_k16", "昊泽-K16", "成品检验", 325),
    ("qc_finished_dls_vetni_k17", "Vetni-K17", "成品检验", 326),
    ("qc_finished_dls_eva_k18", "EVA-K18", "成品检验", 327),
    ("qc_finished_dls_cronus_k19", "Cronus-K19", "成品检验", 328),
    ("qc_finished_mpa_tapi_k1", "TAPI-K1", "成品检验", 329),
    ("qc_finished_mpa_emcure_k2", "Emcure-K2", "成品检验", 330),
    ("qc_finished_mpa_rakshit_k3", "RAKSHIT-K3", "成品检验", 331),
    ("qc_finished_mpa_apotex_k4", "APOTEX-K4", "成品检验", 332),
    ("qc_finished_mpa_sloara_k6", "Sloara-K6", "成品检验", 333),
    ("qc_finished_mpa_concord_k7", "Concord-K7", "成品检验", 334),
    ("qc_finished_mpa_concord_high_spec_k11", "Concord高规-K11", "成品检验", 335),
    ("qc_finished_mpa_taiwan_china_k12", "台湾中化-K12", "成品检验", 336),
    ("qc_finished_mpa_biocon_k13", "Biocon-K13", "成品检验", 337),
    ("qc_finished_mpa_dasami_k14", "Dasami-K14", "成品检验", 338),
    ("qc_finished_mpa_fis_k15", "FIS-K15", "成品检验", 339),
    ("qc_finished_mpa_intas_k16", "Intas-K16", "成品检验", 340),
    ("qc_finished_lkms_internal", "林可霉素内控-未做", "成品检验", 341),
    ("qc_finished_lkms_usp", "林可霉素USP", "成品检验", 342),
    ("qc_finished_lkms_k1", "林可霉素K1", "成品检验", 343),
    ("qc_finished_lkms_k2", "林可霉素K2", "成品检验", 344),
    ("qc_finished_lkms_k3", "林可霉素K3", "成品检验", 345),
    ("qc_finished_boiler_water", "锅炉水", "成品检验", 346),
    ("inspection_general", "通用检验", "检验管理", 350),
    ("inspection_lab_item", "实验室物品", "检验管理", 351),
    ("inspection_lab_instrument", "实验室仪器", "检验管理", 352),
    ("inspection_finished_product", "成品检验", "检验管理", 353),
    ("inspection_solid_material", "固体物料检验", "检验管理", 354),
    ("inspection_liquid_material", "液体物料检验", "检验管理", 355),
    *MATERIAL_DEFAULT_QUALITY_FEISHU_ENTITIES,
]
DEFAULT_QUALITY_FEISHU_ENTITY_MAP = {
    entity_code: (entity_name, entity_group, sort_order)
    for (
        entity_code,
        entity_name,
        entity_group,
        sort_order,
    ) in DEFAULT_QUALITY_FEISHU_ENTITIES
}

PUSH_ONLY_QUALITY_FEISHU_ENTITIES = {
    "oos_ledger",
    "oot_ledger",
    "oot_limit_product",
    "oot_limit_item",
    "inspection_general",
    "inspection_lab_item",
    "inspection_lab_instrument",
    "inspection_finished_product",
    "inspection_solid_material",
    "inspection_liquid_material",
    "supplier_ledger",
    "supplier_qualification",
    "complaint_ledger",
    "return_recall_ledger",
    "product_quality_ledger",
    "product_quality_standard_item",
}
LEGACY_PUSH_ONLY_QUALITY_FEISHU_ENTITIES = {
    "inspection_records",
    "finished_product_inspections",
    "solid_material_inspections",
    "liquid_material_inspections",
    "lab_items",
    "lab_instruments",
}


def _get_default_sync_directions(entity_code: str) -> tuple[bool, bool]:
    """Return the compatibility default for push and pull directions."""
    push_only_codes = (
        PUSH_ONLY_QUALITY_FEISHU_ENTITIES | LEGACY_PUSH_ONLY_QUALITY_FEISHU_ENTITIES
    )
    return True, entity_code not in push_only_codes


QUALITY_FEISHU_ENTITY_ENV_PREFILLS: dict[str, dict[str, str]] = {
    "deviation_report_record": {
        "app_token_setting": "QUALITY_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_FEISHU_DEVIATION_REPORT_TABLE_ID",
        "table_name": "报告记录",
    },
    "deviation_investigation_push_record": {
        "app_token_setting": "QUALITY_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_FEISHU_DEVIATION_INVESTIGATION_PUSH_TABLE_ID",
        "table_name": "偏差调查推送记录",
    },
    "deviation_ledger": {
        "app_token_setting": "QUALITY_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_FEISHU_DEVIATION_TABLE_ID",
        "table_name": "偏差台账",
    },
    "capa_ledger": {
        "app_token_setting": "QUALITY_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_FEISHU_CAPA_TABLE_ID",
        "table_name": "CAPA台账",
    },
    "capa_plan_track": {
        "app_token_setting": "QUALITY_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_FEISHU_CAPA_PLAN_TABLE_ID",
        "table_name": "CAPA计划跟踪",
    },
    "department_contact": {
        "app_token_setting": "QUALITY_DEPARTMENT_CONTACT_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_DEPARTMENT_CONTACT_FEISHU_TABLE_ID",
        "table_name": "部门联系人",
    },
    "change_ledger": {
        "app_token_setting": "QUALITY_CHANGE_LEDGER_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_CHANGE_LEDGER_FEISHU_TABLE_ID",
        "table_name": "变更总表",
    },
    "change_action_plan": {
        "app_token_setting": "QUALITY_CHANGE_ACTION_PLAN_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_CHANGE_ACTION_PLAN_FEISHU_TABLE_ID",
        "table_name": "变更计划",
    },
    "validation_master_plan": {
        "app_token_setting": "QUALITY_VALIDATION_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_VALIDATION_FEISHU_TABLE_ID",
        "table_name": "验证总表",
        "source_note": "验证与确认共用同一张飞书源表，平台按验证类型截取到不同模块。",
    },
    "validation_equipment_qualification": {
        "app_token_setting": "QUALITY_VALIDATION_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_VALIDATION_FEISHU_TABLE_ID",
        "table_name": "验证总表",
        "source_note": "验证与确认共用同一张飞书源表，平台按验证类型截取到不同模块。",
    },
    "validation_process": {
        "app_token_setting": "QUALITY_VALIDATION_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_VALIDATION_FEISHU_TABLE_ID",
        "table_name": "验证总表",
        "source_note": "验证与确认共用同一张飞书源表，平台按验证类型截取到不同模块。",
    },
    "validation_cleaning": {
        "app_token_setting": "QUALITY_VALIDATION_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_VALIDATION_FEISHU_TABLE_ID",
        "table_name": "验证总表",
        "source_note": "验证与确认共用同一张飞书源表，平台按验证类型截取到不同模块。",
    },
    "validation_other": {
        "app_token_setting": "QUALITY_VALIDATION_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_VALIDATION_FEISHU_TABLE_ID",
        "table_name": "验证总表",
        "source_note": "验证与确认共用同一张飞书源表，平台按验证类型截取到不同模块。",
    },
    # QC验证 2026 年表固定绑定专用 Base；其余年份由用户在同步设置中自行绑定
    "validation_qc_2026": {
        "app_token": "GMFmbYxSlaVv16szQHHc51Dwn4d",
        "table_id": "tbl39A8QUDCrC1TJ",
        "table_name": "2026年",
        "source_note": (
            "QC验证按年分表，2026 年已固定绑定飞书源表；其余年份请在同步设置中配置。"
        ),
    },
    # OOS/OOT 管理（复用主 Base QUALITY_FEISHU_APP_TOKEN）
    "oos_oot_report_record": {
        "app_token_setting": "QUALITY_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_OOS_OOT_REPORT_RECORD_TABLE_ID",
        "table_name": "OOSOOT报告记录",
    },
    "oos_oot_investigation_push": {
        "app_token_setting": "QUALITY_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_OOS_OOT_INVESTIGATION_PUSH_TABLE_ID",
        "table_name": "OOSOOT调查推送记录",
    },
    "oos_ledger": {
        "app_token_setting": "QUALITY_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_OOS_LEDGER_TABLE_ID",
        "table_name": "OOS台账",
    },
    "oot_ledger": {
        "app_token_setting": "QUALITY_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_OOT_LEDGER_TABLE_ID",
        "table_name": "OOT台账",
    },
    "oos_oot_product_department": {
        "app_token_setting": "QUALITY_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_OOS_OOT_PRODUCT_DEPARTMENT_TABLE_ID",
        "table_name": "产品涉及部门",
    },
    # 投诉与退货召回管理
    "complaint_ledger": {
        "app_token_setting": "QUALITY_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_COMPLAINT_LEDGER_TABLE_ID",
        "table_name": "投诉台账",
    },
    "return_application": {
        "app_token_setting": "QUALITY_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_RETURN_APPLICATION_TABLE_ID",
        "table_name": "退货申请表",
    },
    "return_ledger": {
        "app_token_setting": "QUALITY_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_RETURN_LEDGER_TABLE_ID",
        "table_name": "退回台账",
    },
    # 供应商管理（固定 Base 配置）
    "supplier_qualification": {
        "app_token": "Mbi5bHLMnaahEJs8gizcR2CNnTc",
        "table_id": "tbly4nZgfCYWQOVk",
        "table_name": "供应商资质",
    },
    # 产品质量客户标准（共用一个 App Token，各产品独立子表）
    "product_quality_mfn": {
        "app_token_setting": "QUALITY_PRODUCT_QUALITY_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_PRODUCT_QUALITY_MFN_TABLE_ID",
        "table_name": "霉酚酸",
    },
    "product_quality_dljs": {
        "app_token_setting": "QUALITY_PRODUCT_QUALITY_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_PRODUCT_QUALITY_DLJS_TABLE_ID",
        "table_name": "多拉菌素",
    },
    "product_quality_lftt": {
        "app_token_setting": "QUALITY_PRODUCT_QUALITY_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_PRODUCT_QUALITY_LFTT_TABLE_ID",
        "table_name": "洛伐他汀",
    },
    "product_quality_mftt": {
        "app_token_setting": "QUALITY_PRODUCT_QUALITY_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_PRODUCT_QUALITY_MFTT_TABLE_ID",
        "table_name": "美伐他汀",
    },
    "product_quality_yslkms": {
        "app_token_setting": "QUALITY_PRODUCT_QUALITY_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_PRODUCT_QUALITY_YSLKMS_TABLE_ID",
        "table_name": "盐酸林可霉素",
    },
    "product_quality_bbas": {
        "app_token_setting": "QUALITY_PRODUCT_QUALITY_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_PRODUCT_QUALITY_BBAS_TABLE_ID",
        "table_name": "L-苯丙氨酸",
    },
    "product_quality_sas": {
        "app_token_setting": "QUALITY_PRODUCT_QUALITY_FEISHU_APP_TOKEN",
        "table_id_setting": "QUALITY_PRODUCT_QUALITY_SAS_TABLE_ID",
        "table_name": "L-色氨酸",
    },
    **MATERIAL_ENTITY_PREFILLS,
    # 物品管理（固定 Base 配置）
    "qc_items_inventory": {
        "app_token": "AApmbavGQaSpjCsCR8uc66fInsd",
        "table_id": "tblOhnO2pAdrxd32",
        "table_name": "关键物资库存",
    },
    "qc_items_inbound": {
        "app_token": "AApmbavGQaSpjCsCR8uc66fInsd",
        "table_id": "tblq63K9NVUPIvvH",
        "table_name": "关键物资入库明细",
    },
    "qc_items_outbound": {
        "app_token": "AApmbavGQaSpjCsCR8uc66fInsd",
        "table_id": "tblKdYydWBsCeQYy",
        "table_name": "关键物资领用明细",
    },
    # 仪器管理（固定 Base 配置）
    "qc_instr_equipment": {
        "app_token": "O0S2bHK6Ca5UiCsABPLcZtYhn6d",
        "table_id": "tblUUbPOOokfxnUE",
        "table_name": "设备数据管理",
    },
    "qc_instr_maintenance": {
        "app_token": "O0S2bHK6Ca5UiCsABPLcZtYhn6d",
        "table_id": "tbl9P17KgdD7XuEu",
        "table_name": "设备维护保养记录",
    },
    "qc_instr_calibration": {
        "app_token": "O0S2bHK6Ca5UiCsABPLcZtYhn6d",
        "table_id": "tblBUZbc5FPZLuJS",
        "table_name": "设备校验记录",
    },
    "qc_instr_repair": {
        "app_token": "O0S2bHK6Ca5UiCsABPLcZtYhn6d",
        "table_id": "tblQbwxJHCOzffKQ",
        "table_name": "设备维修记录",
    },
    "qc_instr_change": {
        "app_token": "O0S2bHK6Ca5UiCsABPLcZtYhn6d",
        "table_id": "tblO8Pg0axL0JLvc",
        "table_name": "设备变更记录",
    },
    "qc_instr_contracts": {
        "app_token": "O0S2bHK6Ca5UiCsABPLcZtYhn6d",
        "table_id": "tblLLsCm7uizb5Fn",
        "table_name": "设备维保合同",
    },
    "qc_instr_plans": {
        "app_token": "O0S2bHK6Ca5UiCsABPLcZtYhn6d",
        "table_id": "tbl11SKGWMVVllf3",
        "table_name": "设备维护保养方案",
    },
    "qc_instr_assets": {
        "app_token": "O0S2bHK6Ca5UiCsABPLcZtYhn6d",
        "table_id": "tblkdru2FMOSIzxo",
        "table_name": "固资台账",
    },
    # 成品检验（固定 Base 配置 - 所有成品检验子表共用同一 Base）
    "qc_finished_internal": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblLHGBtnNSTycVW",
        "table_name": "霉酚酸（内控）",
    },
    "qc_finished_high_spec": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblxFdgNvgDNBH3Y",
        "table_name": "霉酚酸（高规）",
    },
    "qc_finished_mvt": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tbllOn1w98wx62j9",
        "table_name": "美伐他汀（DMF）",
    },
    "qc_finished_lft_ep": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblfb12ATBt5fzQn",
        "table_name": "洛伐他汀（EP）",
    },
    "qc_finished_lft_usp": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblFuap3CgPGNVNN",
        "table_name": "洛伐他汀（USP）",
    },
    "qc_finished_dor_gb": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tbl2TxHcba13Dgol",
        "table_name": "多拉菌素（GB）",
    },
    "qc_finished_dor_vet": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tbljZItMlTCvpsVR",
        "table_name": "多拉菌素（兽药）",
    },
    "qc_finished_fcc14": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblmexymttbNuJGg",
        "table_name": "FCC14",
    },
    "qc_finished_usp": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblxybI5aqt77ggf",
        "table_name": "USP",
    },
    "qc_finished_trp_granule": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblFvH1NpacCF5av",
        "table_name": "色氨酸颗粒",
    },
    "qc_finished_trp_powder": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tbl1DY6IuHzn3LHs",
        "table_name": "色氨酸粉末",
    },
    "qc_finished_flu_powder": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblNYlmhR82aODYU",
        "table_name": "2%氟苯尼考预混剂",
    },
    "qc_finished_fen_powder": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tbl8cTBptuFKqxjf",
        "table_name": "5%芬苯达唑粉",
    },
    "qc_finished_pure_water": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblWXddq7Mm5jETP",
        "table_name": "纯化水",
    },
    "qc_finished_lkms_vet": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblTum9YOFjj47TC",
        "table_name": "林可霉素（兽药）",
    },
    "qc_finished_mpa_crude": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblRMscJ9eaFV8N8",
        "table_name": "霉酚酸（粗品）",
    },
    "qc_finished_bbas_hanguang_k1": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblAGoyVIcpbBOZj",
        "table_name": "汉光（K1）",
    },
    "qc_finished_bbas_weiduo_k2": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblve2eOf5t9Y71X",
        "table_name": "维多（K2）",
    },
    "qc_finished_bbas_changmao_k3": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tbll7UgN84lOt5vR",
        "table_name": "常茂（K3）",
    },
    "qc_finished_bbas_jinghai_k4": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblhIsGioRvTSXow",
        "table_name": "晶海（k4）",
    },
    "qc_finished_bbas_xiehe_k5": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblrcXfpw3IBbQpc",
        "table_name": "协和（K5）",
    },
    "qc_finished_bbas_hongshan_k10": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblgZPABjiyMCNuO",
        "table_name": "红衫（K10）未做",
    },
    "qc_finished_bbas_bafeng_k11": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tbl7ZCKelHNbymba",
        "table_name": "八峰（k11）",
    },
    "qc_finished_bbas_haitian_k12": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tbldWGmEJnlqXAWF",
        "table_name": "海天（k12）",
    },
    "qc_finished_bbas_feed_q": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblPhk0sfKvZIDhD",
        "table_name": "饲料（Q）",
    },
    "qc_finished_mvt_bt_k1": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblEOE4dlJ2ERX9u",
        "table_name": "BT-K1",
    },
    "qc_finished_mvt_tw_k2": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblTqssB44WRvjzk",
        "table_name": "TW-K2",
    },
    "qc_finished_mvt_zh_k3": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tbllIWEYyTNfAUNP",
        "table_name": "ZH-K3（未做）",
    },
    "qc_finished_mvt_tapi_k5": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblGkFOmlskC9Qoo",
        "table_name": "TAPI-K5",
    },
    "qc_finished_lft_lp_k3": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblVyUJTYFZ4c0bf",
        "table_name": "LP-K3",
    },
    "qc_finished_lft_tapi_k4": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblsuSGLP8m3ZDg0",
        "table_name": "TAPI-K4",
    },
    "qc_finished_lft_gn_k6": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tbl0vEUeypHl244b",
        "table_name": "GN-K6",
    },
    "qc_finished_lft_jingxin_k7": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tbldchgRe5BXJwZT",
        "table_name": "京新-K7",
    },
    "qc_finished_lft_jb_k9": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblynYofqJLU99Lc",
        "table_name": "JB-K9",
    },
    "qc_finished_lft_jinbao_k10": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tbl7JvQADKLIKinx",
        "table_name": "金宝-K10",
    },
    "qc_finished_lft_lp_crude_k11": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tbl0n3yArcxpcaro",
        "table_name": "LP粗品-K11",
    },
    "qc_finished_dls_norbrook_k2": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblhPMV6eBRPVXau",
        "table_name": "Norbrook-K2",
    },
    "qc_finished_dls_zenex_k10": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblAL9qgbAdC5jaO",
        "table_name": "Zenex-K10",
    },
    "qc_finished_dls_microsules_k6": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblC9y7KOFMgCV8V",
        "table_name": "Microsules-K6",
    },
    "qc_finished_dls_elanco_kr_k11": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblvc7VhgQK5B0vu",
        "table_name": "Elanco韩国-K11",
    },
    "qc_finished_dls_adwia_k12": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblpjHrHjlKoo2Rc",
        "table_name": "ADWIA-K12",
    },
    "qc_finished_dls_qilu_k13": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblOjgHWDFCvAUK1",
        "table_name": "齐鲁动保-K13",
    },
    "qc_finished_dls_eurofarwa_k14": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblJACySZwYlCN21",
        "table_name": "EUROFARWA-K14",
    },
    "qc_finished_dls_msd_k15": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblGHeQUhyGr1jb3",
        "table_name": "MSD-K15",
    },
    "qc_finished_dls_haoze_k16": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblcLJFhuT6Va6KQ",
        "table_name": "昊泽-K16",
    },
    "qc_finished_dls_vetni_k17": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblshNVhBoViP4b0",
        "table_name": "Vetni-K17",
    },
    "qc_finished_dls_eva_k18": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblRDedoJTvZ3Ljm",
        "table_name": "EVA-K18",
    },
    "qc_finished_dls_cronus_k19": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblwz5Jqul5FkNyA",
        "table_name": "Cronus-K19",
    },
    "qc_finished_mpa_tapi_k1": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblzs67J6sQv1v7Z",
        "table_name": "TAPI-K1",
    },
    "qc_finished_mpa_emcure_k2": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tbl8EgiHi5JvMI2D",
        "table_name": "Emcure-K2",
    },
    "qc_finished_mpa_rakshit_k3": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblvGhcNpp0bXTts",
        "table_name": "RAKSHIT-K3",
    },
    "qc_finished_mpa_apotex_k4": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblIzMJ2Cs1Olzqn",
        "table_name": "APOTEX-K4",
    },
    "qc_finished_mpa_sloara_k6": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblah6pn1ErmsNS6",
        "table_name": "Sloara-K6",
    },
    "qc_finished_mpa_concord_k7": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tbld8O1fTubJRuNG",
        "table_name": "Concord-K7",
    },
    "qc_finished_mpa_concord_high_spec_k11": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tbl3VPwVSgAqAbGw",
        "table_name": "Concord高规-K11",
    },
    "qc_finished_mpa_taiwan_china_k12": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblNkvOo2kg7KRvn",
        "table_name": "台湾中化-K12",
    },
    "qc_finished_mpa_biocon_k13": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblzzr6xEKXzuXSj",
        "table_name": "Biocon-K13",
    },
    "qc_finished_mpa_fis_k15": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblk4cY4V8rmsrn8",
        "table_name": "FIS-K15",
    },
    "qc_finished_mpa_dasami_k14": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblAjsxrRrr31l2v",
        "table_name": "Dasami-K14",
    },
    "qc_finished_mpa_intas_k16": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblvAhPgp4Ezdjbr",
        "table_name": "Intas-K16",
    },
    "qc_finished_lkms_internal": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tbla0qYIg56AIa3F",
        "table_name": "林可霉素内控-未做",
    },
    "qc_finished_lkms_usp": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblPODoZLCCtUQq8",
        "table_name": "林可霉素USP",
    },
    "qc_finished_lkms_k1": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblQJNON5Nw4Glgw",
        "table_name": "林可霉素K1",
    },
    "qc_finished_lkms_k2": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblnAN35kgthjE2G",
        "table_name": "林可霉素K2",
    },
    "qc_finished_lkms_k3": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblyKfZLWfV8Nfco",
        "table_name": "林可霉素 K3",
    },
    "qc_finished_boiler_water": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tbldfvO2te01xsws",
        "table_name": "锅炉水",
    },
    "qc_finished_lkms_ep": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tbljSra2VKUGCe12",
        "table_name": "林可霉素（EP）",
    },
    "qc_finished_bbas_weizhisu_k6": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblmxRy6iGYhKHwk",
        "table_name": "味之素（k6）",
    },
    "qc_finished_pf": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblIWylGRweSu9a0",
        "table_name": "PF",
    },
    "qc_finished_drinking_water": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblEX9Bc8P6Ca04e",
        "table_name": "饮用水",
    },
    # 补充缺失 token 的实体
    "qc_finished_bbas_jiuling_k7": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblvFqlwWnepXFtD",
        "table_name": "久凌（K7）",
    },
    "qc_finished_bbas_jirong_k8": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tblOTjIv3onxL15u",
        "table_name": "冀荣（k8）",
    },
    "qc_finished_bbas_yuanda_k9": {
        "app_token": "CB1LbgkpGa8hxUsQ8fZcwgpPnUd",
        "table_id": "tbluIp6Lk0ohzQlq",
        "table_name": "远大（K9）",
    },
}

QUALITY_FEISHU_SYSTEM_FIELDS: dict[str, list[tuple[str, str, str]]] = {
    "deviation_ledger": [
        ("偏差编号", "偏差编号", "both"),
        ("产品名称/批号", "产品名称/批号", "both"),
        ("偏差简要描述", "偏差简要描述", "both"),
        ("偏差是否曾发生", "偏差是否曾发生", "both"),
        ("根本原因", "根本原因", "both"),
        ("偏差等级", "偏差等级", "both"),
        ("调查完成时间", "调查完成时间", "both"),
        ("纠正预防措施", "纠正预防措施", "both"),
        ("产品/物料处理结果", "产品/物料处理结果", "both"),
        ("是否关闭", "是否关闭", "both"),
        ("关闭时间", "关闭时间", "both"),
        ("关联capa", "关联capa", "push"),
    ],
    "capa_ledger": [
        ("CAPA编号", "CAPA编号", "both"),
        ("启动日期", "启动日期", "push"),
        ("事件部门", "事件部门", "push"),
        ("涉及产品", "涉及产品", "push"),
        ("CAPA简述", "CAPA简述", "push"),
        ("CAPA效果评估", "CAPA效果评估", "push"),
        ("关闭日期", "关闭日期", "both"),
        ("QA质量员", "QA质量员", "push"),
        ("QA质量员确认日期", "QA质量员确认日期", "push"),
        ("CAPA状态", "CAPA状态", "both"),
        ("关联CAPA计划", "关联CAPA计划", "push"),
    ],
    "deviation_report_record": [
        ("偏差编号", "偏差编号", "both"),
        ("报告时间", "报告时间", "both"),
        ("偏差内容", "偏差内容", "both"),
        ("涉及产品名称/批号", "涉及产品名称/批号", "both"),
        ("部门", "部门", "both"),
        ("报告人", "报告人", "both"),
        ("部门负责人", "部门负责人", "both"),
        ("部门负责人确认", "部门负责人确认", "both"),
        ("部门负责人确认时间", "部门负责人确认时间", "both"),
        ("QA", "QA", "both"),
        ("QA确认", "QA确认", "both"),
        ("QA确认时间", "QA确认时间", "both"),
        ("QA负责人", "QA负责人", "both"),
        ("QA负责人确认", "QA负责人确认", "both"),
        ("QA负责人确认时间", "QA负责人确认时间", "both"),
        ("报告状态", "报告状态", "both"),
        ("附件", "附件", "both"),
    ],
    "deviation_investigation_push_record": [
        ("偏差编号", "偏差编号", "both"),
        ("第N次推送", "第N次推送", "both"),
        ("偏差调查报告", "偏差调查报告", "both"),
        ("提交日期", "提交日期", "both"),
        ("提交人", "提交人", "both"),
        ("部门负责人", "部门负责人", "pull"),
        ("部门负责人审核结果", "部门负责人审核结果", "both"),
        ("部门负责人审核时间", "部门负责人审核时间", "both"),
        ("QA", "QA", "both"),
        ("QA审核结果", "QA审核结果", "both"),
        ("QA审核时间", "QA审核时间", "both"),
        ("QA负责人", "QA负责人", "both"),
        ("QA负责人审核结果", "QA负责人审核结果", "both"),
        ("QA负责人审核时间", "QA负责人审核时间", "both"),
    ],
    "capa_plan_track": [
        ("CAPA编号", "CAPA编号", "both"),
        ("计划内容", "计划内容", "both"),
        ("完成时间", "完成时间", "both"),
        ("责任人", "责任人", "push"),
        ("责任人确认", "责任人确认", "push"),
        ("部门负责人", "部门负责人", "push"),
        ("部门负责人确认", "部门负责人确认", "both"),
        ("进度", "进度", "both"),
        ("提醒状态", "提醒状态", "push"),
        ("关联CAPA编号", "关联CAPA编号", "push"),
    ],
    # OOS/OOT System Fields
    "oos_oot_report_record": [
        ("报告时间", "报告时间", "both"),
        ("内容", "内容", "both"),
        ("涉及产品名称", "涉及产品名称", "both"),
        ("涉及批号", "涉及批号", "both"),
        ("报告部门", "报告部门", "both"),
        ("报告人", "报告人", "both"),
        ("部门负责人确认", "部门负责人确认", "both"),
        ("QA确认", "QA确认", "both"),
        ("QA负责人确认", "QA负责人确认", "both"),
        ("附件", "附件", "both"),
    ],
    "oos_oot_investigation_push": [
        ("OOS/OOT编号", "OOS/OOT编号", "both"),
        ("第N次推送", "第N次推送", "both"),
        ("调查报告", "调查报告", "both"),
        ("提交日期", "提交日期", "both"),
        ("部门", "部门", "both"),
        ("提交人", "提交人", "both"),
        ("部门负责人审核结果", "部门负责人审核结果", "both"),
        ("部门负责人审核时间", "部门负责人审核时间", "both"),
        ("QA审核结果", "QA审核结果", "both"),
        ("QA审核时间", "QA审核时间", "both"),
        ("QA负责人审核结果", "QA负责人审核结果", "both"),
        ("QA负责人审核时间", "QA负责人审核时间", "both"),
        ("流程状态", "流程状态", "both"),
        ("已退回待重新提交", "已退回待重新提交", "both"),
    ],
    "oos_ledger": [
        ("序号", "序号", "both"),
        ("日期", "日期", "both"),
        ("物料名称", "物料名称", "both"),
        ("批号", "批号", "both"),
        ("调查编号", "调查编号", "both"),
        ("问题描述", "问题描述", "both"),
        ("产生原因", "产生原因", "both"),
        ("纠正预防措施", "纠正预防措施", "both"),
        ("最终处理结果", "最终处理结果", "both"),
        ("登记人", "登记人", "both"),
        ("备注", "备注", "both"),
    ],
    "oot_ledger": [
        ("序号", "序号", "both"),
        ("日期", "日期", "both"),
        ("物料名称", "物料名称", "both"),
        ("批号", "批号", "both"),
        ("调查编号", "调查编号", "both"),
        ("问题描述", "问题描述", "both"),
        ("产生原因", "产生原因", "both"),
        ("纠正预防措施", "纠正预防措施", "both"),
        ("最终处理结果", "最终处理结果", "both"),
        ("登记人", "登记人", "both"),
        ("备注", "备注", "both"),
    ],
    "oos_oot_product_department": [
        ("序号", "序号", "both"),
        ("产品代码", "产品代码", "both"),
        ("涉及发酵部门", "涉及发酵部门", "both"),
        ("涉及发酵部门负责人", "涉及发酵部门负责人", "both"),
        ("涉及提炼部门", "涉及提炼部门", "both"),
        ("涉及提炼部门负责人", "涉及提炼部门负责人", "both"),
    ],
    # 投诉与退货召回管理
    "complaint_ledger": [
        ("序号", "序号", "both"),
        ("投诉编号", "投诉编号", "both"),
        ("投诉内容", "投诉内容", "both"),
        ("原因分析", "原因分析", "both"),
        ("回复日期", "回复日期", "both"),
        ("关闭时限", "关闭时限", "both"),
        ("投诉级别", "投诉级别", "both"),
        ("投诉单位（个人）", "投诉单位（个人）", "both"),
        ("品名", "品名", "both"),
        ("数量", "数量", "both"),
        ("处理结果", "处理结果", "both"),
        ("CAPA实施情况及结果", "CAPA实施情况及结果", "both"),
        ("批号", "批号", "both"),
    ],
    "return_application": [
        ("序号", "序号", "both"),
        ("品名", "品名", "both"),
        ("退货总量", "退货总量", "both"),
        ("规格", "规格", "both"),
        ("批号", "批号", "both"),
        ("数量", "数量", "both"),
        ("生产日期", "生产日期", "both"),
        ("有效期/复验期", "有效期/复验期", "both"),
        ("批号1", "批号1", "both"),
        ("数量1", "数量1", "both"),
        ("生产日期1", "生产日期1", "both"),
        ("有效期/复验期1", "有效期/复验期1", "both"),
        ("批号2", "批号2", "both"),
        ("数量2", "数量2", "both"),
        ("生产日期2", "生产日期2", "both"),
        ("有效期/复验期2", "有效期/复验期2", "both"),
        ("退货单位及地址", "退货单位及地址", "both"),
        ("退货原因", "退货原因", "both"),
        ("申请人", "申请人", "both"),
        ("申请日期", "申请日期", "both"),
        ("QA负责人意见", "QA负责人意见", "both"),
        ("QA负责人", "QA负责人", "both"),
        ("QA负责人日期", "QA负责人日期", "both"),
        ("质量管理负责人建议", "质量管理负责人建议", "both"),
        ("质量管理负责人", "质量管理负责人", "both"),
        ("质量管理负责人日期", "质量管理负责人日期", "both"),
        ("备注", "备注", "both"),
    ],
    "return_ledger": [
        ("序号", "序号", "both"),
        ("品名", "品名", "both"),
        ("规格", "规格", "both"),
        ("产品批号", "产品批号", "both"),
        ("数量", "数量", "both"),
        ("退货单位及地址", "退货单位及地址", "both"),
        ("退回日期", "退回日期", "both"),
        ("经办人", "经办人", "both"),
        ("退回产品处理结果", "退回产品处理结果", "both"),
    ],
}

# 产品质量客户标准字段（所有产品共用同一套字段结构）
_PRODUCT_QUALITY_SYSTEM_FIELDS: list[tuple[str, str, str]] = [
    ("客户名称", "客户名称", "both"),
    ("质量标准", "质量标准", "both"),
    ("历史发货趋势", "历史发货趋势", "both"),
    ("特殊要求", "特殊要求", "both"),
    ("包装要求", "包装要求", "both"),
    ("标签要求", "标签要求", "both"),
    ("发货时包装照片", "发货时包装照片", "both"),
    ("发货打托要求", "发货打托要求", "both"),
    ("目标市场", "目标市场", "both"),
    ("注册情况", "注册情况", "both"),
    ("其他注意事项", "其他注意事项", "both"),
]

for _pq_code in [
    "product_quality_mfn",
    "product_quality_dljs",
    "product_quality_lftt",
    "product_quality_mftt",
    "product_quality_yslkms",
    "product_quality_bbas",
    "product_quality_sas",
]:
    QUALITY_FEISHU_SYSTEM_FIELDS[_pq_code] = _PRODUCT_QUALITY_SYSTEM_FIELDS


def _is_settings_table_missing(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "quality_feishu_app_settings" in text
        or "quality_feishu_entity_settings" in text
        or "does not exist" in text
        or "undefinedtable" in text
        or "no such table" in text
    )


def _build_default_entity_items() -> list[QualityFeishuEntitySettingItem]:
    return [
        QualityFeishuEntitySettingItem(
            entity_code=entity_code,
            entity_name=entity_name,
            entity_group=entity_group,
            source_note=_get_entity_source_note(entity_code),
            app_token=None,
            base_table_name=None,
            base_table_id=None,
            is_enabled=False,
            enable_push_to_feishu=_get_default_sync_directions(entity_code)[0],
            enable_pull_from_feishu=_get_default_sync_directions(entity_code)[1],
            field_mappings=[],
            sort_order=sort_order,
            last_sync_status=None,
            last_sync_error=None,
            last_synced_at=None,
        )
        for (
            entity_code,
            entity_name,
            entity_group,
            sort_order,
        ) in DEFAULT_QUALITY_FEISHU_ENTITIES
    ]


async def _get_app_settings_model(
    db: AsyncSession,
) -> QualityFeishuAppSettings | None:
    try:
        result = await db.execute(
            select(QualityFeishuAppSettings)
            .where(QualityFeishuAppSettings.is_deleted.is_(False))
            .order_by(QualityFeishuAppSettings.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
    except (OperationalError, ProgrammingError) as exc:
        if _is_settings_table_missing(exc):
            return None
        raise


async def _get_entity_settings_model(
    db: AsyncSession,
    entity_code: str,
) -> QualityFeishuEntitySetting | None:
    result = await db.execute(
        select(QualityFeishuEntitySetting).where(
            QualityFeishuEntitySetting.entity_code == entity_code,
            QualityFeishuEntitySetting.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


def _decrypt_stored_app_secret(encrypted: str | None) -> str:
    """解密存量 App Secret；密钥轮换导致解密失败时返回空串。

    返回空串而非抛错，保证设置页可加载、可重新保存覆盖损坏的存量密文。
    """
    if not encrypted:
        return ""
    try:
        return decrypt_api_key(encrypted)
    except LLMConfigError:
        logger.warning("质量飞书 App Secret 解密失败（加密密钥已轮换），需重新保存")
        return ""


def _build_app_settings_detail(
    model: QualityFeishuAppSettings | None,
) -> QualityFeishuAppSettingsDetail:
    if not model:
        return QualityFeishuAppSettingsDetail()
    decrypted_secret = _decrypt_stored_app_secret(model.app_secret)
    return QualityFeishuAppSettingsDetail(
        app_id=model.app_id or "",
        app_secret_masked=mask_api_key(decrypted_secret),
        is_enabled=model.is_enabled,
        deviation_report_form_url=model.deviation_report_form_url,
        deviation_investigation_push_form_url=model.deviation_investigation_push_form_url,
        oos_oot_report_form_url=model.oos_oot_report_form_url,
        oos_oot_investigation_push_form_url=model.oos_oot_investigation_push_form_url,
        last_test_status=model.last_test_status,
        last_test_error=model.last_test_error,
        last_tested_at=model.last_tested_at,
    )


def _build_system_fields(entity_code: str) -> list[QualityFeishuSystemFieldOption]:
    return [
        QualityFeishuSystemFieldOption(
            field_key=field_key,
            field_label=field_label,
            direction=direction,
        )
        for field_key, field_label, direction in QUALITY_FEISHU_SYSTEM_FIELDS.get(
            entity_code, []
        )
    ]


def _get_setting_value(name: str) -> str:
    value = getattr(settings, name, "")
    return value.strip() if isinstance(value, str) else ""


def _get_entity_source_note(entity_code: str) -> str | None:
    attrs = QUALITY_FEISHU_ENTITY_ENV_PREFILLS.get(entity_code) or {}
    source_note = attrs.get("source_note", "").strip()
    return source_note or None


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


def _get_entity_prefill(entity_code: str) -> tuple[str | None, str | None, str | None]:
    attrs = QUALITY_FEISHU_ENTITY_ENV_PREFILLS.get(entity_code) or {}
    app_setting = attrs.get("app_token_setting", "").strip()
    table_setting = attrs.get("table_id_setting", "").strip()
    table_name = attrs.get("table_name", "").strip() or None
    app_token = attrs.get("app_token", "").strip() or (
        _get_setting_value(app_setting) if app_setting else ""
    )
    table_id = attrs.get("table_id", "").strip() or (
        _get_setting_value(table_setting) if table_setting else ""
    )
    return app_token or None, table_id or None, table_name


def _build_entity_setting_item(
    model: QualityFeishuEntitySetting,
) -> QualityFeishuEntitySettingItem:
    item = QualityFeishuEntitySettingItem.model_validate(model, from_attributes=True)
    return item.model_copy(
        update={"source_note": _get_entity_source_note(model.entity_code)}
    )


async def _refresh_entity_data_after_save(
    db: AsyncSession,
    entity_code: str,
) -> QualityFeishuEntitySetting:
    model = await _get_entity_settings_model(db, entity_code)
    if model is None:
        raise AppException(message="质量飞书实体配置不存在")
    if not model.is_enabled or not model.enable_pull_from_feishu:
        return model

    from app.modules.quality.service import quality_feishu_sync

    try:
        await quality_feishu_sync.pull_quality_records_from_feishu(
            db,
            entity_code=entity_code,
        )
        model.last_sync_status = "success"
        model.last_sync_error = None
        model.last_synced_at = datetime.now(UTC)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        model = await _get_entity_settings_model(db, entity_code) or model
        model.last_sync_status = "failed"
        model.last_sync_error = _sanitize_feishu_error_message(str(exc))
        model.last_synced_at = datetime.now(UTC)
        await db.commit()
    return model


async def _ensure_quality_feishu_app_settings_seeded(
    db: AsyncSession,
) -> QualityFeishuAppSettings | None:
    model = await _get_app_settings_model(db)
    if model is None:
        return None

    # 回填默认偏差报告新建表单链接（仅当为空时回填，避免覆盖用户已保存的值）
    if not (model.deviation_report_form_url or "").strip():
        model.deviation_report_form_url = DEVIATION_REPORT_FORM_URL
        await db.commit()
        result = await db.execute(
            select(QualityFeishuAppSettings).where(
                QualityFeishuAppSettings.id == model.id
            )
        )
        model = result.scalar_one()

    # 回填默认偏差调查推送新建表单链接（仅当为空时回填）
    if not (model.deviation_investigation_push_form_url or "").strip():
        model.deviation_investigation_push_form_url = (
            DEVIATION_INVESTIGATION_PUSH_FORM_URL
        )
        await db.commit()
        result = await db.execute(
            select(QualityFeishuAppSettings).where(
                QualityFeishuAppSettings.id == model.id
            )
        )
        model = result.scalar_one()

    # 回填默认OOSOOT报告新建表单链接（仅当为空时回填）
    if not (model.oos_oot_report_form_url or "").strip():
        model.oos_oot_report_form_url = OOS_OOT_REPORT_FORM_URL
        await db.commit()
        result = await db.execute(
            select(QualityFeishuAppSettings).where(
                QualityFeishuAppSettings.id == model.id
            )
        )
        model = result.scalar_one()

    # 回填默认OOSOOT调查推送新建表单链接（仅当为空时回填）
    if not (model.oos_oot_investigation_push_form_url or "").strip():
        model.oos_oot_investigation_push_form_url = OOS_OOT_INVESTIGATION_PUSH_FORM_URL
        await db.commit()
        result = await db.execute(
            select(QualityFeishuAppSettings).where(
                QualityFeishuAppSettings.id == model.id
            )
        )
        model = result.scalar_one()

    return model


async def ensure_quality_feishu_entity_settings(
    db: AsyncSession,
) -> list[QualityFeishuEntitySetting]:
    try:
        result = await db.execute(
            select(QualityFeishuEntitySetting).where(
                QualityFeishuEntitySetting.is_deleted.is_(False)
            )
        )
        existing = {item.entity_code: item for item in result.scalars().all()}
        created = False
        changed = False
        legacy_entity_codes = {
            "qc_solid_ledger",
            "qc_liquid_ledger",
            "qc_solid_inspection",
            "qc_liquid_inspection",
        }

        for legacy_entity_code in legacy_entity_codes:
            legacy_model = existing.get(legacy_entity_code)
            if legacy_model and not legacy_model.is_deleted:
                legacy_model.is_deleted = True
                changed = True

        for (
            entity_code,
            entity_name,
            entity_group,
            sort_order,
        ) in DEFAULT_QUALITY_FEISHU_ENTITIES:
            prefill_app_token, prefill_table_id, prefill_table_name = (
                _get_entity_prefill(entity_code)
            )
            if entity_code in existing:
                model = existing[entity_code]
                if entity_code in PUSH_ONLY_QUALITY_FEISHU_ENTITIES:
                    if not model.enable_push_to_feishu:
                        model.enable_push_to_feishu = True
                        changed = True
                    if model.enable_pull_from_feishu:
                        model.enable_pull_from_feishu = False
                        changed = True
                if model.entity_name != entity_name:
                    model.entity_name = entity_name
                    changed = True
                if model.entity_group != entity_group:
                    model.entity_group = entity_group
                    changed = True
                if model.sort_order != sort_order:
                    model.sort_order = sort_order
                    changed = True
                identifiers_backfilled = False
                if not (model.app_token or "").strip() and prefill_app_token:
                    model.app_token = prefill_app_token
                    changed = True
                    identifiers_backfilled = True
                if not (model.base_table_id or "").strip() and prefill_table_id:
                    model.base_table_id = prefill_table_id
                    changed = True
                    identifiers_backfilled = True
                if not (model.base_table_name or "").strip() and prefill_table_name:
                    model.base_table_name = prefill_table_name
                    changed = True
                if (
                    identifiers_backfilled
                    and not model.is_enabled
                    and (model.app_token or "").strip()
                    and (model.base_table_id or "").strip()
                ):
                    model.is_enabled = True
                    changed = True
                continue
            item = QualityFeishuEntitySetting(
                entity_code=entity_code,
                entity_name=entity_name,
                entity_group=entity_group,
                sort_order=sort_order,
                app_token=prefill_app_token,
                base_table_name=prefill_table_name,
                base_table_id=prefill_table_id,
                is_enabled=bool(prefill_app_token and prefill_table_id),
                enable_push_to_feishu=_get_default_sync_directions(entity_code)[0],
                enable_pull_from_feishu=_get_default_sync_directions(entity_code)[1],
            )
            db.add(item)
            created = True
            existing[entity_code] = item
        if created or changed:
            await db.commit()
        result = await db.execute(
            select(QualityFeishuEntitySetting)
            .where(QualityFeishuEntitySetting.is_deleted.is_(False))
            .order_by(
                QualityFeishuEntitySetting.sort_order.asc(),
                QualityFeishuEntitySetting.created_at.asc(),
            )
        )
        return list(result.scalars().all())
    except (OperationalError, ProgrammingError) as exc:
        if _is_settings_table_missing(exc):
            return []
        raise


async def get_quality_feishu_app_settings(
    db: AsyncSession,
) -> QualityFeishuAppSettingsDetail:
    model = await _ensure_quality_feishu_app_settings_seeded(db)
    return _build_app_settings_detail(model)


async def update_quality_feishu_app_settings(
    db: AsyncSession,
    data: UpdateQualityFeishuAppSettingsRequest,
) -> QualityFeishuAppSettingsDetail:
    try:
        model = await _get_app_settings_model(db)
        app_secret = data.app_secret.strip()
        if model is None:
            if not app_secret:
                raise AppException(message="App Secret 不能为空")
            model = QualityFeishuAppSettings(
                app_id=data.app_id.strip(),
                app_secret=encrypt_api_key(app_secret),
                app_token=None,
                is_enabled=data.is_enabled,
                deviation_report_form_url=data.deviation_report_form_url,
                deviation_investigation_push_form_url=data.deviation_investigation_push_form_url,
                oos_oot_report_form_url=data.oos_oot_report_form_url,
                oos_oot_investigation_push_form_url=data.oos_oot_investigation_push_form_url,
            )
            db.add(model)
        else:
            model.app_id = data.app_id.strip()
            model.is_enabled = data.is_enabled
            current_secret = _decrypt_stored_app_secret(model.app_secret)
            # The UI sends the masked value back when the secret was not
            # changed. Never encrypt the mask as if it were a new credential.
            # 存量密文解密失败时 current_secret 为空串（掩码为 ****），
            # 用户重新输入的密钥按新值写入，避免"存不进"死锁。
            if app_secret and app_secret != mask_api_key(current_secret):
                model.app_secret = encrypt_api_key(app_secret)
            # 保留已存值：仅当请求显式携带该字段时写入（空字符串也按空字符
            # 串保存，不回退默认）
            if "deviation_report_form_url" in data.model_fields_set:
                model.deviation_report_form_url = data.deviation_report_form_url
            if "deviation_investigation_push_form_url" in data.model_fields_set:
                model.deviation_investigation_push_form_url = (
                    data.deviation_investigation_push_form_url
                )
            if "oos_oot_report_form_url" in data.model_fields_set:
                model.oos_oot_report_form_url = data.oos_oot_report_form_url
            if "oos_oot_investigation_push_form_url" in data.model_fields_set:
                model.oos_oot_investigation_push_form_url = (
                    data.oos_oot_investigation_push_form_url
                )
        await db.commit()
        return _build_app_settings_detail(model)
    except (OperationalError, ProgrammingError) as exc:
        if _is_settings_table_missing(exc):
            raise AppException(
                message="飞书设置数据表未创建，请先执行质量模块数据库迁移"
            )
        raise


async def test_quality_feishu_app_settings(
    db: AsyncSession,
) -> QualityFeishuSettingsTestResult:
    model = await _ensure_quality_feishu_app_settings_seeded(db)
    if not model:
        raise AppException(message="请先保存飞书应用信息")
    checked_at = datetime.now(UTC)
    stored_secret = _decrypt_stored_app_secret(model.app_secret)
    if model.app_secret and not stored_secret:
        raise AppException(
            message=(
                "已保存的 App Secret 无法解密（加密密钥已轮换），"
                "请重新输入 App Secret 并保存后再测试连接"
            ),
            status_code=400,
        )
    try:
        await FeishuAuth.get_tenant_access_token(
            app_id=model.app_id,
            app_secret=stored_secret,
        )
        model.last_test_status = "success"
        model.last_test_error = None
        model.last_tested_at = checked_at
        await db.commit()
        return QualityFeishuSettingsTestResult(
            success=True,
            message="飞书应用连接成功",
            checked_at=checked_at,
        )
    except Exception as exc:
        model.last_test_status = "failed"
        model.last_test_error = str(exc)
        model.last_tested_at = checked_at
        await db.commit()
        return QualityFeishuSettingsTestResult(
            success=False,
            message=str(exc),
            checked_at=checked_at,
        )


async def list_quality_feishu_entity_settings(
    db: AsyncSession,
) -> list[QualityFeishuEntitySettingItem]:
    rows = await ensure_quality_feishu_entity_settings(db)
    if not rows:
        return _build_default_entity_items()
    return [_build_entity_setting_item(row) for row in rows]


async def list_quality_feishu_tables(
    db: AsyncSession,
    entity_code: str,
    app_token: str | None = None,
    table_id: str | None = None,
) -> list[QualityFeishuTableOption]:
    app_model = await _ensure_quality_feishu_app_settings_seeded(db)
    if not app_model:
        raise AppException(message="请先保存飞书应用信息")

    rows = await ensure_quality_feishu_entity_settings(db)
    row_map = {row.entity_code: row for row in rows}
    model = row_map.get(entity_code)
    if model is None and entity_code not in DEFAULT_QUALITY_FEISHU_ENTITY_MAP:
        raise ValueError("质量飞书实体配置不存在")

    resolved_app_token = (app_token or "").strip() or (
        model.app_token if model else None
    )
    if not resolved_app_token:
        raise AppException(message="请先填写当前实体的 App Token")

    client = build_bitable_client(
        app_token=resolved_app_token,
        app_id=app_model.app_id,
        app_secret=decrypt_api_key(app_model.app_secret),
    )
    try:
        tables = await client.list_tables(page_size=100)
    except Exception as exc:
        raise ValueError(f"读取飞书表列表失败：{exc}") from exc
    return [
        QualityFeishuTableOption(
            table_id=item.get("table_id", ""),
            table_name=item.get("name", ""),
        )
        for item in tables
        if item.get("table_id")
        and item.get("name")
        and (not table_id or item.get("table_id") == table_id)
    ]


async def get_quality_feishu_entity_field_mapping_bundle(
    db: AsyncSession,
    entity_code: str,
    app_token: str | None = None,
    table_id: str | None = None,
) -> QualityFeishuEntityFieldMappingBundle:
    rows = await ensure_quality_feishu_entity_settings(db)
    row_map = {row.entity_code: row for row in rows}
    model = row_map.get(entity_code)
    if model is None and entity_code not in DEFAULT_QUALITY_FEISHU_ENTITY_MAP:
        raise ValueError("质量飞书实体配置不存在")

    if model is not None:
        entity_name = model.entity_name
        saved_app_token = model.app_token
        saved_table_id = model.base_table_id
        saved_mappings = model.field_mappings or []
    else:
        entity_name = DEFAULT_QUALITY_FEISHU_ENTITY_MAP[entity_code][0]
        saved_app_token = None
        saved_table_id = None
        saved_mappings = []

    resolved_app_token = (app_token or "").strip() or (saved_app_token or "")
    resolved_table_id = (table_id or "").strip() or (saved_table_id or "")
    if not resolved_app_token:
        raise AppException(message="请先填写当前实体的 App Token")
    if not resolved_table_id:
        raise AppException(message="请先填写当前实体的 Base Table ID")

    app_model = await _ensure_quality_feishu_app_settings_seeded(db)
    if not app_model:
        raise AppException(message="请先保存飞书应用信息")

    client = build_bitable_client(
        app_token=resolved_app_token,
        app_id=app_model.app_id,
        app_secret=decrypt_api_key(app_model.app_secret),
    )
    try:
        fields = await client.list_fields(resolved_table_id, page_size=500)
    except Exception as exc:
        _raise_feishu_metadata_error("读取", exc)
    feishu_fields = [
        QualityFeishuFieldOption(
            field_id=item.get("field_id", ""),
            field_name=item.get("field_name", ""),
            field_type=item.get("type"),
        )
        for item in fields
        if item.get("field_id") and item.get("field_name")
    ]
    system_fields = _build_system_fields(entity_code)
    existing_map = {
        item.get("system_field"): item.get("feishu_field")
        for item in saved_mappings
        if isinstance(item, dict) and item.get("system_field")
    }
    field_mappings = [
        QualityFeishuFieldMappingItem(
            system_field=field.field_key,
            feishu_field=existing_map.get(field.field_key),
        )
        for field in system_fields
    ]
    return QualityFeishuEntityFieldMappingBundle(
        entity_code=entity_code,
        entity_name=entity_name,
        system_fields=system_fields,
        feishu_fields=feishu_fields,
        field_mappings=field_mappings,
    )


async def update_quality_feishu_entity_setting(
    db: AsyncSession,
    entity_code: str,
    data: UpdateQualityFeishuEntitySettingRequest,
) -> QualityFeishuEntitySettingItem:
    try:
        await ensure_quality_feishu_entity_settings(db)
        model = await _get_entity_settings_model(db, entity_code)
        if model is None:
            raise AppException(message="质量飞书实体配置不存在")
        reference = resolve_bitable_reference(
            app_token=data.app_token,
            table_id=data.base_table_id,
        )
        model.app_token = reference.app_token
        model.base_table_name = (
            data.base_table_name.strip() if data.base_table_name else None
        )
        model.base_table_id = reference.table_id
        model.is_enabled = data.is_enabled
        model.enable_push_to_feishu = data.enable_push_to_feishu
        model.enable_pull_from_feishu = data.enable_pull_from_feishu
        if data.field_mappings is not None:
            model.field_mappings = [item.model_dump() for item in data.field_mappings]
        await db.commit()
        model = await _refresh_entity_data_after_save(db, entity_code)
        return _build_entity_setting_item(model)
    except (OperationalError, ProgrammingError) as exc:
        if _is_settings_table_missing(exc):
            raise AppException(
                message="飞书设置数据表未创建，请先执行质量模块数据库迁移"
            )
        raise


async def test_quality_feishu_entity_setting(
    db: AsyncSession,
    entity_code: str,
) -> QualityFeishuSettingsTestResult:
    try:
        app_model = await _ensure_quality_feishu_app_settings_seeded(db)
        if not app_model:
            raise AppException(message="请先保存飞书应用信息")
        model = await _get_entity_settings_model(db, entity_code)
        if model is None:
            raise AppException(message="质量飞书实体配置不存在")
        if not model.app_token:
            raise AppException(message="请先配置 App Token")
        if not model.base_table_id:
            raise AppException(message="请先配置 Base Table ID")

        client = build_bitable_client(
            app_token=model.app_token,
            app_id=app_model.app_id,
            app_secret=decrypt_api_key(app_model.app_secret),
        )
        checked_at = datetime.now(UTC)
        try:
            await client.search_records(model.base_table_id, page_size=1)
            model.last_sync_status = "success"
            model.last_sync_error = None
            model.last_synced_at = checked_at
            await db.commit()
            return QualityFeishuSettingsTestResult(
                success=True,
                message=f"{model.entity_name} 配置可访问",
                checked_at=checked_at,
                entity_code=model.entity_code,
                table_id=model.base_table_id,
            )
        except Exception as exc:
            model.last_sync_status = "failed"
            safe_error = _sanitize_feishu_error_message(str(exc))
            model.last_sync_error = safe_error
            await db.commit()
            return QualityFeishuSettingsTestResult(
                success=False,
                message=safe_error,
                checked_at=checked_at,
                entity_code=model.entity_code,
                table_id=model.base_table_id,
            )
    except (OperationalError, ProgrammingError) as exc:
        if _is_settings_table_missing(exc):
            raise AppException(
                message="飞书设置数据表未创建，请先执行质量模块数据库迁移"
            )
        raise
