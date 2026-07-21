"""Quality Feishu settings service."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import NoReturn

from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.llm.encryption import decrypt_api_key, encrypt_api_key, mask_api_key
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
from app.platform.integrations.feishu.auth import FeishuAuth
from app.platform.integrations.feishu.utils import (
    build_bitable_client,
    resolve_bitable_reference,
)

settings = get_settings()

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
    ("change_ledger", "变更台账", "变更控制", 120),
    ("change_action_plan", "变更计划", "变更控制", 130),
    ("inspection_general", "通用检验", "检验管理", 140),
    ("inspection_lab_item", "实验室物品", "检验管理", 150),
    ("inspection_lab_instrument", "实验室仪器", "检验管理", 160),
    ("inspection_finished_product", "成品检验", "检验管理", 170),
    ("inspection_solid_material", "固体物料检验", "检验管理", 180),
    ("inspection_liquid_material", "液体物料检验", "检验管理", 190),
    ("oos_ledger", "OOS台账", "OOS/OOT管理", 200),
    ("oot_ledger", "OOT台账", "OOS/OOT管理", 210),
    ("oot_limit_product", "OOT限度产品", "OOS/OOT管理", 220),
    ("oot_limit_item", "OOT限度项目", "OOS/OOT管理", 230),
    ("supplier_ledger", "供应商台账", "外部质量", 240),
    ("supplier_qualification", "供应商资质", "外部质量", 250),
    ("complaint_ledger", "投诉台账", "外部质量", 260),
    ("return_recall_ledger", "退货召回台账", "外部质量", 270),
    ("product_quality_ledger", "产品质量记录", "外部质量", 280),
    ("product_quality_standard_item", "产品质量标准明细", "外部质量", 290),
]
DEFAULT_QUALITY_FEISHU_ENTITY_MAP = {
    entity_code: (entity_name, entity_group, sort_order)
    for entity_code, entity_name, entity_group, sort_order in DEFAULT_QUALITY_FEISHU_ENTITIES
}
QUALITY_FEISHU_AUTO_REFRESH_ENTITIES = {
    "deviation_report_record",
    "deviation_investigation_push_record",
    "deviation_ledger",
    "capa_ledger",
    "capa_plan_track",
}

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
    "inspection_general": [
        ("检验编号", "检验编号", "push"),
        ("产品/物料名称", "产品/物料名称", "push"),
        ("批号", "批号", "push"),
        ("检验类型", "检验类型", "push"),
        ("检验项目", "检验项目", "push"),
        ("标准规定", "标准规定", "push"),
        ("检验结果", "检验结果", "push"),
        ("检验结论", "检验结论", "push"),
        ("检验人", "检验人", "push"),
        ("检验日期", "检验日期", "push"),
        ("检验部门", "检验部门", "push"),
        ("备注", "备注", "push"),
    ],
    "inspection_lab_item": [
        ("物品名称", "物品名称", "push"),
        ("规格", "规格", "push"),
        ("类别", "类别", "push"),
        ("数量", "数量", "push"),
        ("单位", "单位", "push"),
        ("存放位置", "存放位置", "push"),
        ("供应商", "供应商", "push"),
        ("批号", "批号", "push"),
        ("有效期至", "有效期至", "push"),
        ("状态", "状态", "push"),
        ("备注", "备注", "push"),
    ],
    "inspection_lab_instrument": [
        ("仪器名称", "仪器名称", "push"),
        ("仪器序列号", "仪器序列号", "push"),
        ("型号", "型号", "push"),
        ("生产厂家", "生产厂家", "push"),
        ("所属部门", "所属部门", "push"),
        ("放置位置", "放置位置", "push"),
        ("最近校准日期", "最近校准日期", "push"),
        ("下次校准日期", "下次校准日期", "push"),
        ("状态", "状态", "push"),
        ("备注", "备注", "push"),
    ],
    "inspection_finished_product": [
        ("检验编号", "检验编号", "push"),
        ("产品/物料名称", "产品/物料名称", "push"),
        ("批号", "批号", "push"),
        ("检验项目", "检验项目", "push"),
        ("标准规定", "标准规定", "push"),
        ("检验结果", "检验结果", "push"),
        ("检验结论", "检验结论", "push"),
        ("检验人", "检验人", "push"),
        ("检验日期", "检验日期", "push"),
        ("备注", "备注", "push"),
    ],
    "inspection_solid_material": [
        ("检验编号", "检验编号", "push"),
        ("产品/物料名称", "产品/物料名称", "push"),
        ("批号", "批号", "push"),
        ("供应商", "供应商", "push"),
        ("检验项目", "检验项目", "push"),
        ("标准规定", "标准规定", "push"),
        ("检验结果", "检验结果", "push"),
        ("检验结论", "检验结论", "push"),
        ("检验人", "检验人", "push"),
        ("检验日期", "检验日期", "push"),
        ("备注", "备注", "push"),
    ],
    "inspection_liquid_material": [
        ("检验编号", "检验编号", "push"),
        ("产品/物料名称", "产品/物料名称", "push"),
        ("批号", "批号", "push"),
        ("供应商", "供应商", "push"),
        ("检验项目", "检验项目", "push"),
        ("标准规定", "标准规定", "push"),
        ("检验结果", "检验结果", "push"),
        ("检验结论", "检验结论", "push"),
        ("检验人", "检验人", "push"),
        ("检验日期", "检验日期", "push"),
        ("备注", "备注", "push"),
    ],
    "oos_ledger": [
        ("记录编号", "记录编号", "push"),
        ("事件标题", "事件标题", "push"),
        ("责任部门", "责任部门", "push"),
        ("产品名称", "产品名称", "push"),
        ("批号", "批号", "push"),
        ("检验项目", "检验项目", "push"),
        ("标准规定", "标准规定", "push"),
        ("检验结果", "检验结果", "push"),
        ("发现日期", "发现日期", "push"),
        ("事件描述", "事件描述", "push"),
        ("调查结论", "调查结论", "push"),
        ("纠正预防措施", "纠正预防措施", "push"),
        ("状态", "状态", "push"),
        ("关闭时间", "关闭时间", "push"),
    ],
    "oot_ledger": [
        ("记录编号", "记录编号", "push"),
        ("事件标题", "事件标题", "push"),
        ("责任部门", "责任部门", "push"),
        ("产品名称", "产品名称", "push"),
        ("批号", "批号", "push"),
        ("检验项目", "检验项目", "push"),
        ("标准规定", "标准规定", "push"),
        ("检验结果", "检验结果", "push"),
        ("发现日期", "发现日期", "push"),
        ("事件描述", "事件描述", "push"),
        ("调查结论", "调查结论", "push"),
        ("纠正预防措施", "纠正预防措施", "push"),
        ("状态", "状态", "push"),
        ("关闭时间", "关闭时间", "push"),
    ],
    "oot_limit_product": [
        ("产品编码", "产品编码", "push"),
        ("产品名称", "产品名称", "push"),
        ("标准文件编号", "标准文件编号", "push"),
        ("标准文件版本", "标准文件版本", "push"),
        ("是否启用", "是否启用", "push"),
        ("备注", "备注", "push"),
    ],
    "oot_limit_item": [
        ("产品编码", "产品编码", "push"),
        ("显示顺序", "显示顺序", "push"),
        ("项目分组", "项目分组", "push"),
        ("项目名称", "项目名称", "push"),
        ("标准规定", "标准规定", "push"),
        ("OOT限度", "OOT限度", "push"),
        ("备注", "备注", "push"),
    ],
    "supplier_ledger": [
        ("供应商编号", "供应商编号", "push"),
        ("供应商名称", "供应商名称", "push"),
        ("供应商类别", "供应商类别", "push"),
        ("联系人", "联系人", "push"),
        ("联系电话", "联系电话", "push"),
        ("地址", "地址", "push"),
        ("资质状态", "资质状态", "push"),
        ("最近审计日期", "最近审计日期", "push"),
        ("审计结论", "审计结论", "push"),
        ("下次审计日期", "下次审计日期", "push"),
        ("供应范围", "供应范围", "push"),
        ("状态", "状态", "push"),
        ("备注", "备注", "push"),
    ],
    "supplier_qualification": [
        ("供应商编号", "供应商编号", "push"),
        ("供应商名称", "供应商名称", "push"),
        ("资质编号", "资质编号", "push"),
        ("资质名称", "资质名称", "push"),
        ("文件编号", "文件编号", "push"),
        ("取得日期", "取得日期", "push"),
        ("到期日期", "到期日期", "push"),
        ("资质状态", "资质状态", "push"),
        ("责任人", "责任人", "push"),
        ("备注", "备注", "push"),
    ],
    "complaint_ledger": [
        ("投诉编号", "投诉编号", "push"),
        ("投诉标题", "投诉标题", "push"),
        ("投诉来源", "投诉来源", "push"),
        ("客户名称", "客户名称", "push"),
        ("产品名称", "产品名称", "push"),
        ("批号", "批号", "push"),
        ("投诉日期", "投诉日期", "push"),
        ("投诉类别", "投诉类别", "push"),
        ("投诉描述", "投诉描述", "push"),
        ("处理人", "处理人", "push"),
        ("调查结论", "调查结论", "push"),
        ("回复内容", "回复内容", "push"),
        ("回复日期", "回复日期", "push"),
        ("关联CAPA编号", "关联CAPA编号", "push"),
        ("状态", "状态", "push"),
        ("关闭时间", "关闭时间", "push"),
    ],
    "return_recall_ledger": [
        ("记录编号", "记录编号", "push"),
        ("记录类型", "记录类型", "push"),
        ("标题", "标题", "push"),
        ("产品名称", "产品名称", "push"),
        ("批号", "批号", "push"),
        ("数量", "数量", "push"),
        ("单位", "单位", "push"),
        ("客户/退货方", "客户/退货方", "push"),
        ("退货/召回原因", "退货/召回原因", "push"),
        ("发生日期", "发生日期", "push"),
        ("处理人", "处理人", "push"),
        ("评估日期", "评估日期", "push"),
        ("处置方式", "处置方式", "push"),
        ("完成日期", "完成日期", "push"),
        ("状态", "状态", "push"),
    ],
    "product_quality_ledger": [
        ("质量记录编号", "质量记录编号", "push"),
        ("记录类型", "记录类型", "push"),
        ("标题", "标题", "push"),
        ("产品名称", "产品名称", "push"),
        ("客户名称", "客户名称", "push"),
        ("标准文件编号", "标准文件编号", "push"),
        ("标准文件版本", "标准文件版本", "push"),
        ("质量趋势", "质量趋势", "push"),
        ("质量标准", "质量标准", "push"),
        ("特殊要求", "特殊要求", "push"),
        ("包装要求", "包装要求", "push"),
        ("标签要求", "标签要求", "push"),
        ("打托要求", "打托要求", "push"),
        ("目标市场", "目标市场", "push"),
        ("注册情况", "注册情况", "push"),
        ("评审结论", "评审结论", "push"),
        ("改进建议", "改进建议", "push"),
        ("评审人", "评审人", "push"),
        ("评审日期", "评审日期", "push"),
        ("状态", "状态", "push"),
        ("批准时间", "批准时间", "push"),
    ],
    "product_quality_standard_item": [
        ("质量记录编号", "质量记录编号", "push"),
        ("显示顺序", "显示顺序", "push"),
        ("要求分类", "要求分类", "push"),
        ("要求项目", "要求项目", "push"),
        ("要求内容", "要求内容", "push"),
        ("是否关键要求", "是否关键要求", "push"),
        ("备注", "备注", "push"),
    ],
}


def _is_settings_table_missing(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "quality_feishu_app_settings" in text
        or "quality_feishu_entity_settings" in text
        or "does not exist" in text
        or "undefinedtable" in text
        or "no such table" in text
    )


def _get_default_sync_directions(entity_code: str) -> tuple[bool, bool]:
    """Platform-owned quality ledgers start with explicit push-only bindings."""
    push_only_entities = {
        "oos_ledger",
        "oot_ledger",
        "oot_limit_product",
        "oot_limit_item",
        "supplier_ledger",
        "supplier_qualification",
        "complaint_ledger",
        "return_recall_ledger",
        "product_quality_ledger",
        "product_quality_standard_item",
    }
    return True, not (entity_code.startswith("inspection_") or entity_code in push_only_entities)


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
        for entity_code, entity_name, entity_group, sort_order in DEFAULT_QUALITY_FEISHU_ENTITIES
    ]


async def _get_app_settings_model(
    db: AsyncSession,
) -> QualityFeishuAppSettings | None:
    try:
        result = await db.execute(
            select(QualityFeishuAppSettings)
            .where(QualityFeishuAppSettings.is_deleted == False)
            .order_by(
                QualityFeishuAppSettings.updated_at.desc(),
                QualityFeishuAppSettings.created_at.desc(),
                QualityFeishuAppSettings.id.desc(),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()
    except (OperationalError, ProgrammingError) as exc:
        if _is_settings_table_missing(exc):
            return None
        raise


def _build_app_settings_detail(
    model: QualityFeishuAppSettings | None,
) -> QualityFeishuAppSettingsDetail:
    if not model:
        return QualityFeishuAppSettingsDetail()
    decrypted_secret = decrypt_api_key(model.app_secret) if model.app_secret else ""
    return QualityFeishuAppSettingsDetail(
        app_id=model.app_id or "",
        app_secret_masked=mask_api_key(decrypted_secret),
        is_enabled=model.is_enabled,
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
        for field_key, field_label, direction in QUALITY_FEISHU_SYSTEM_FIELDS.get(entity_code, [])
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


def _is_test_app_settings_model(model: QualityFeishuAppSettings) -> bool:
    decrypted_secret = decrypt_api_key(model.app_secret) if model.app_secret else ""
    return _looks_like_test_app_settings(model.app_id, decrypted_secret)


def _mask_feishu_identifier(value: str) -> str:
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}****{value[-4:]}"


def _sanitize_feishu_error_message(message: str) -> str:
    patterns = [
        r"\b(basc[A-Za-z0-9_-]{6,})\b",
        r"\b(tbl[A-Za-z0-9_-]{6,})\b",
    ]
    sanitized = message
    for pattern in patterns:
        for match in set(re.findall(pattern, sanitized)):
            sanitized = sanitized.replace(match, _mask_feishu_identifier(match))
    return sanitized


def _raise_feishu_metadata_error(action: str, exc: Exception) -> NoReturn:
    message = str(exc).strip() or exc.__class__.__name__
    message = _sanitize_feishu_error_message(message)
    raise ValueError(f"{action}失败：{message}") from exc


def _get_entity_prefill(entity_code: str) -> tuple[str | None, str | None, str | None]:
    attrs = QUALITY_FEISHU_ENTITY_ENV_PREFILLS.get(entity_code) or {}
    app_setting = attrs.get("app_token_setting", "").strip()
    table_setting = attrs.get("table_id_setting", "").strip()
    table_name = attrs.get("table_name", "").strip() or None
    reference = resolve_bitable_reference(
        app_token=_get_setting_value(app_setting) if app_setting else "",
        table_id=_get_setting_value(table_setting) if table_setting else "",
    )
    return reference.app_token, reference.table_id, table_name


def _build_entity_setting_item(
    model: QualityFeishuEntitySetting,
) -> QualityFeishuEntitySettingItem:
    item = QualityFeishuEntitySettingItem.model_validate(model, from_attributes=True)
    return item.model_copy(update={"source_note": _get_entity_source_note(model.entity_code)})


async def _ensure_quality_feishu_app_settings_seeded(
    db: AsyncSession,
) -> QualityFeishuAppSettings | None:
    model = await _get_app_settings_model(db)
    env_app_id = _get_setting_value("FEISHU_APP_ID")
    env_app_secret = _get_setting_value("FEISHU_APP_SECRET")
    if not env_app_id or not env_app_secret:
        return model

    if model is None:
        model = QualityFeishuAppSettings(
            app_id=env_app_id,
            app_secret=encrypt_api_key(env_app_secret),
            app_token=None,
            is_enabled=True,
        )
        db.add(model)
        await db.commit()
        await db.flush()
        return model

    if _is_test_app_settings_model(model):
        model.app_id = env_app_id
        model.app_secret = encrypt_api_key(env_app_secret)
        model.is_enabled = True
        await db.commit()
        await db.flush()
    return model


async def ensure_quality_feishu_entity_settings(
    db: AsyncSession,
) -> list[QualityFeishuEntitySetting]:
    try:
        result = await db.execute(
            select(QualityFeishuEntitySetting).where(
                QualityFeishuEntitySetting.is_deleted == False
            )
        )
        existing = {item.entity_code: item for item in result.scalars().all()}
        created = False
        changed = False
        for entity_code, entity_name, entity_group, sort_order in DEFAULT_QUALITY_FEISHU_ENTITIES:
            if entity_code in existing:
                model = existing[entity_code]
                if model.entity_name != entity_name:
                    model.entity_name = entity_name
                    changed = True
                if model.entity_group != entity_group:
                    model.entity_group = entity_group
                    changed = True
                if model.sort_order != sort_order:
                    model.sort_order = sort_order
                    changed = True
                continue
            prefill_app_token, prefill_table_id, prefill_table_name = _get_entity_prefill(entity_code)
            enable_push_to_feishu, enable_pull_from_feishu = _get_default_sync_directions(
                entity_code
            )
            item = QualityFeishuEntitySetting(
                entity_code=entity_code,
                entity_name=entity_name,
                entity_group=entity_group,
                sort_order=sort_order,
                app_token=prefill_app_token,
                base_table_name=prefill_table_name,
                base_table_id=prefill_table_id,
                is_enabled=bool(prefill_app_token and prefill_table_id),
                enable_push_to_feishu=enable_push_to_feishu,
                enable_pull_from_feishu=enable_pull_from_feishu,
            )
            db.add(item)
            created = True
            existing[entity_code] = item
        if created or changed:
            await db.commit()
        result = await db.execute(
            select(QualityFeishuEntitySetting)
            .where(QualityFeishuEntitySetting.is_deleted == False)
            .order_by(
                QualityFeishuEntitySetting.sort_order.asc(),
                QualityFeishuEntitySetting.created_at.asc(),
            )
        )
        return result.scalars().all()
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
                raise ValueError("App Secret 不能为空")
            model = QualityFeishuAppSettings(
                app_id=data.app_id.strip(),
                app_secret=encrypt_api_key(app_secret),
                app_token=None,
                is_enabled=data.is_enabled,
            )
            db.add(model)
        else:
            model.app_id = data.app_id.strip()
            model.is_enabled = data.is_enabled
            existing_secret = decrypt_api_key(model.app_secret) if model.app_secret else ""
            existing_secret_masked = mask_api_key(existing_secret)
            if app_secret and app_secret != existing_secret_masked:
                model.app_secret = encrypt_api_key(app_secret)
        await db.commit()
        await db.flush()
        return _build_app_settings_detail(model)
    except (OperationalError, ProgrammingError) as exc:
        if _is_settings_table_missing(exc):
            raise ValueError("飞书设置数据表未创建，请先执行质量模块数据库迁移")
        raise


async def test_quality_feishu_app_settings(
    db: AsyncSession,
) -> QualityFeishuSettingsTestResult:
    model = await _ensure_quality_feishu_app_settings_seeded(db)
    if not model:
        raise ValueError("请先保存飞书应用信息")
    checked_at = datetime.now(UTC)
    try:
        await FeishuAuth.get_tenant_access_token(
            app_id=model.app_id,
            app_secret=decrypt_api_key(model.app_secret),
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


async def _get_entity_settings_model(
    db: AsyncSession,
    entity_code: str,
) -> QualityFeishuEntitySetting | None:
    result = await db.execute(
        select(QualityFeishuEntitySetting).where(
            QualityFeishuEntitySetting.entity_code == entity_code,
            QualityFeishuEntitySetting.is_deleted == False,
        )
    )
    return result.scalar_one_or_none()


async def _mark_entity_refresh_status(
    db: AsyncSession,
    entity_code: str,
    *,
    status: str,
    error: str | None = None,
) -> QualityFeishuEntitySetting | None:
    model = await _get_entity_settings_model(db, entity_code)
    if model is None:
        return None
    model.last_sync_status = status
    model.last_sync_error = error
    model.last_synced_at = datetime.now(UTC)
    await db.commit()
    await db.flush()
    return model


async def _refresh_entity_data_after_save(
    db: AsyncSession,
    entity_code: str,
) -> QualityFeishuEntitySetting | None:
    model = await _get_entity_settings_model(db, entity_code)
    if (
        model is None
        or model.entity_code not in QUALITY_FEISHU_AUTO_REFRESH_ENTITIES
        or not model.is_enabled
        or not model.enable_pull_from_feishu
        or not model.app_token
        or not model.base_table_id
    ):
        return model

    try:
        from app.modules.quality.service import quality_feishu_sync as feishu_sync_service

        await feishu_sync_service.pull_quality_records_from_feishu(
            db,
            entity_code=model.entity_code,
        )
    except Exception as exc:  # noqa: BLE001 - save should persist even if refresh fails
        await db.rollback()
        return await _mark_entity_refresh_status(
            db,
            entity_code,
            status="failed",
            error=_sanitize_feishu_error_message(str(exc) or exc.__class__.__name__),
        )

    return await _mark_entity_refresh_status(
        db,
        entity_code,
        status="success",
    )


async def list_quality_feishu_tables(
    db: AsyncSession,
    entity_code: str,
    app_token: str | None = None,
    table_id: str | None = None,
) -> list[QualityFeishuTableOption]:
    try:
        app_model = await _ensure_quality_feishu_app_settings_seeded(db)
        if not app_model:
            raise ValueError("请先保存飞书应用信息")

        rows = await ensure_quality_feishu_entity_settings(db)
        row_map = {row.entity_code: row for row in rows}
        model = row_map.get(entity_code)
        if model is None and entity_code not in DEFAULT_QUALITY_FEISHU_ENTITY_MAP:
            raise ValueError("质量飞书实体配置不存在")

        reference = resolve_bitable_reference(
            app_token=app_token,
            table_id=table_id,
            fallback_app_token=model.app_token if model else None,
            fallback_table_id=model.base_table_id if model else None,
        )
        if not reference.app_token:
            raise ValueError("请先填写当前实体的 App Token")

        client = build_bitable_client(
            app_token=reference.app_token,
            app_id=app_model.app_id,
            app_secret=decrypt_api_key(app_model.app_secret),
        )
        tables = await client.list_tables(page_size=100)
    except Exception as exc:
        if isinstance(exc, ValueError):
            raise
        _raise_feishu_metadata_error("读取飞书表列表", exc)
    options = [
        QualityFeishuTableOption(
            table_id=item.get("table_id", ""),
            table_name=item.get("name", ""),
        )
        for item in tables
        if item.get("table_id") and item.get("name")
    ]
    if not reference.table_id:
        return options

    matched = [item for item in options if item.table_id == reference.table_id]
    if matched:
        return matched

    raise ValueError("未在该 App Token 对应的多维表格中找到当前 Base Table ID")


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

    reference = resolve_bitable_reference(
        app_token=app_token,
        table_id=table_id,
        fallback_app_token=saved_app_token,
        fallback_table_id=saved_table_id,
    )
    if not reference.app_token:
        raise ValueError("请先填写当前实体的 App Token")
    if not reference.table_id:
        raise ValueError("请先填写当前实体的 Base Table ID")

    app_model = await _ensure_quality_feishu_app_settings_seeded(db)
    if not app_model:
        raise ValueError("请先保存飞书应用信息")

    client = build_bitable_client(
        app_token=reference.app_token,
        app_id=app_model.app_id,
        app_secret=decrypt_api_key(app_model.app_secret),
    )
    try:
        fields = await client.list_fields(reference.table_id, page_size=500)
    except Exception as exc:
        _raise_feishu_metadata_error("读取飞书字段列表", exc)
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
            raise ValueError("质量飞书实体配置不存在")
        reference = resolve_bitable_reference(
            app_token=data.app_token,
            table_id=data.base_table_id,
        )
        model.app_token = reference.app_token
        model.base_table_name = data.base_table_name.strip() if data.base_table_name else None
        model.base_table_id = reference.table_id
        model.is_enabled = data.is_enabled
        model.enable_push_to_feishu = data.enable_push_to_feishu
        model.enable_pull_from_feishu = data.enable_pull_from_feishu
        if data.field_mappings is not None:
            model.field_mappings = [item.model_dump() for item in data.field_mappings]
        await db.commit()
        await db.flush()
        refreshed_model = await _refresh_entity_data_after_save(db, entity_code)
        return _build_entity_setting_item(refreshed_model or model)
    except (OperationalError, ProgrammingError) as exc:
        if _is_settings_table_missing(exc):
            raise ValueError("飞书设置数据表未创建，请先执行质量模块数据库迁移")
        raise


async def test_quality_feishu_entity_setting(
    db: AsyncSession,
    entity_code: str,
) -> QualityFeishuSettingsTestResult:
    try:
        app_model = await _ensure_quality_feishu_app_settings_seeded(db)
        if not app_model:
            raise ValueError("请先保存飞书应用信息")
        result = await db.execute(
            select(QualityFeishuEntitySetting).where(
                QualityFeishuEntitySetting.entity_code == entity_code,
                QualityFeishuEntitySetting.is_deleted == False,
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError("质量飞书实体配置不存在")
        if not model.app_token:
            raise ValueError("请先配置 App Token")
        if not model.base_table_id:
            raise ValueError("请先配置 Base Table ID")

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
            model.last_sync_error = str(exc)
            await db.commit()
            return QualityFeishuSettingsTestResult(
                success=False,
                message=str(exc),
                checked_at=checked_at,
                entity_code=model.entity_code,
                table_id=model.base_table_id,
            )
    except (OperationalError, ProgrammingError) as exc:
        if _is_settings_table_missing(exc):
            raise ValueError("飞书设置数据表未创建，请先执行质量模块数据库迁移")
        raise
