"HR Feishu settings service — manages app credentials and per-entity bitable config."

import logging
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.llm import decrypt_api_key, encrypt_api_key, mask_api_key
from app.modules.hr.models import HrFeishuAppSettings, HrFeishuEntitySetting
from app.modules.hr.schemas import (
    HrFeishuAppSettingsDetail,
    HrFeishuEntityFieldMappingBundle,
    HrFeishuEntitySettingItem,
    HrFeishuFieldOption,
    HrFeishuSettingsTestResult,
    HrFeishuSystemFieldOption,
    HrFeishuTableOption,
    UpdateHrFeishuAppSettingsRequest,
    UpdateHrFeishuEntitySettingRequest,
)
from app.platform.integrations.feishu.auth import FeishuAuth
from app.platform.integrations.feishu.bitable import BitableClient

logger = logging.getLogger(__name__)
_settings = get_settings()

# ─── Default HR entities ───

DEFAULT_HR_FEISHU_ENTITIES: list[tuple[str, str, str, int]] = [
    # (entity_code, entity_name, entity_group, sort_order)
    # 仅保留与飞书多维表格（Base VNXObZivrasMlDs5et2ckovRnxd）实际子表一一对应的实体，
    # 不在列表中的配置行会被 ensure_hr_feishu_entity_settings 物理清理
    ("employee", "员工花名册", "人事台账", 1),
    ("contract_management", "合同管理", "人事台账", 2),
    ("offboarding_record", "离职管理", "人事台账", 3),
    ("position_transfer", "岗位调动", "人事台账", 4),
    ("job_posting", "招聘职位表", "招聘入职", 5),
    ("candidate", "候选人表", "招聘入职", 6),
    ("onboarding", "入职信息表", "招聘入职", 7),
]

DEFAULT_HR_FEISHU_ENTITY_MAP = {e[0]: e for e in DEFAULT_HR_FEISHU_ENTITIES}

# ─── Environment variable prefill mapping ───

HR_FEISHU_ENTITY_ENV_PREFILLS: dict[str, dict[str, str]] = {
    "employee": {
        "app_token_setting": "FEISHU_BITABLE_APP_TOKEN",
        "table_id_setting": "FEISHU_BITABLE_EMPLOYEE_TABLE_ID",
    },
    "contract_management": {
        "app_token_setting": "FEISHU_BITABLE_APP_TOKEN",
        "table_id_setting": "FEISHU_BITABLE_CONTRACT_MANAGEMENT_TABLE_ID",
    },
    "offboarding_record": {
        "app_token_setting": "FEISHU_BITABLE_APP_TOKEN",
        "table_id_setting": "FEISHU_BITABLE_OFFBOARDING_TABLE_ID",
    },
    "position_transfer": {
        "app_token_setting": "FEISHU_BITABLE_APP_TOKEN",
        "table_id_setting": "FEISHU_BITABLE_POSITION_TRANSFER_TABLE_ID",
    },
}

# ─── System fields per entity (for field mapping UI) ───

HR_FEISHU_SYSTEM_FIELDS: dict[str, list[tuple[str, str, str]]] = {
    "employee": [
        ("employee_number", "工号", "both"),
        ("name", "姓名", "both"),
        ("domain_account", "域账户", "both"),
        ("department", "一级部门", "both"),
        ("sub_department", "二级部门", "both"),
        ("position", "职务|岗位", "both"),
        ("level", "职级", "both"),
        ("gender", "性别", "both"),
        ("ethnic_group", "民族", "both"),
        ("native_place", "籍贯", "both"),
        ("id_card", "身份证号", "both"),
        ("id_card_expiry", "身份证有效期截止日期", "both"),
        ("marital_status", "婚姻状况", "both"),
        ("political_status", "政治面貌", "both"),
        ("current_address", "现居住地址", "both"),
        ("household_type", "户口类别", "both"),
        ("education", "学历", "both"),
        ("degree", "学位", "both"),
        ("school", "毕业院校", "both"),
        ("major", "专业", "both"),
        ("graduation_date", "毕业时间", "both"),
        ("certificate_number", "证书编号", "both"),
        ("qualification_type", "职称", "both"),
        ("qualifications", "技能证书", "both"),
        ("certificate_review_date", "技能证书复审时间", "both"),
        ("work_start_date", "参加工作时间", "both"),
        ("hire_date", "入职日期", "both"),
        ("factory_entry_date", "进本公司时间", "both"),
        ("status", "在职状态", "both"),
        ("employment_type", "人员就业方式", "both"),
        ("phone", "联系电话", "both"),
        ("email", "电子邮箱", "both"),
        ("emergency_contact_name", "紧急联系人姓名", "both"),
        ("emergency_contact_relation", "与本人关系", "both"),
        ("emergency_contact_phone", "紧急联系人电话", "both"),
        ("probation_status", "转正状态", "both"),
        ("planned_probation_date", "拟转正日期", "both"),
        ("probation_effective_date", "转正生效日期", "both"),
        ("contract_start_date", "首次签订合同日期", "both"),
        ("contract_end_date", "首次签订合同截止日期", "both"),
        ("contract_start_2", "第二次续签合同日期", "both"),
        ("contract_end_2", "合同截止日期（2）", "both"),
        ("contract_start_3", "第三次续签合同日期", "both"),
        ("contract_end_3", "合同截止日期（3）", "both"),
        ("contract_start_4", "第四次续签合同日期", "both"),
        ("contract_end_4", "合同截止日期4", "both"),
        ("contract_start_5", "第五次续签合同日期", "both"),
        ("contract_end_5", "合同截止日期5", "both"),
        ("contract_start_6", "第六次续签合同日期", "both"),
        ("contract_end_6", "合同截止日期6", "both"),
        ("archive_number", "档案编号", "both"),
    ],
    "contract_management": [
        ("employee_number", "工号", "both"),
        ("name", "姓名", "both"),
        ("gender", "性别", "both"),
        ("dept_level1", "一级部门", "both"),
        ("dept_level2", "二级部门", "both"),
        ("position", "职务|岗位", "both"),
        ("job_level", "职级", "both"),
        ("domain_account", "域账户", "both"),
        ("id_card", "身份证号", "both"),
        ("id_card_expiry", "身份证有效期截止日期", "both"),
        ("archive_number", "档案编号", "both"),
        ("contract_sequence", "第几次合同续签", "both"),
        ("contract_start_1", "首次签订合同日期", "both"),
        ("contract_end_1", "首次签订合同截止日期", "both"),
        ("contract_start_2", "第二次续签合同日期", "both"),
        ("contract_end_2", "合同截止日期（2）", "both"),
        ("contract_start_3", "第三次续签合同日期", "both"),
        ("contract_end_3", "合同截止日期（3）", "both"),
        ("contract_start_4", "第四次续签合同日期", "both"),
        ("contract_end_4", "合同截止日期4", "both"),
        ("contract_start_5", "第五次续签合同日期", "both"),
        ("contract_end_5", "合同截止日期5", "both"),
        ("contract_start_6", "第六次续签合同日期", "both"),
        ("contract_end_6", "合同截止日期6", "both"),
    ],
    "offboarding_record": [
        ("employee_number", "工号", "both"),
        ("name", "姓名", "both"),
        ("department", "一级部门", "both"),
        ("sub_department", "二级部门", "both"),
        ("position", "职务|岗位", "both"),
        ("level", "职级", "both"),
        ("offboarding_date", "最后工作日", "both"),
        ("offboarding_type", "离职类型", "both"),
        ("gender", "性别", "both"),
        ("phone", "联系电话", "both"),
        ("email", "电子邮箱", "both"),
    ],
    "position_transfer": [
        ("employee_name", "申请人", "both"),
        ("department_before", "原部门", "both"),
        ("original_position", "原职位", "both"),
        ("effective_date", "生效日期", "both"),
        ("apply_department", "申请部门", "both"),
        ("apply_position", "申请职位", "both"),
        ("contact_phone", "联系电话", "both"),
        ("applicant_confirmation_text", "申请人确认说明", "both"),
        ("applicant_signature", "申请人签名", "both"),
        ("applicant_confirmation_date", "申请人确认日期", "both"),
    ],
}


# ─── Known Feishu Bitable defaults ───

# HR_FEISHU_BITABLE_APP_TOKEN 已从硬编码迁移到数据库配置
# 使用 _settings.FEISHU_BITABLE_APP_TOKEN 从环境变量读取

# 飞书多维表格真实子表 Table ID（经 API 核实，Base: VNXObZivrasMlDs5et2ckovRnxd）
HR_FEISHU_ENTITY_DEFAULT_TABLE_IDS: dict[str, str] = {
    "employee": "tblDThp5wAUfDopZ",
    "contract_management": "tblbClIxUJUP8rA3",
    "offboarding_record": "tbl9RpqAQf7t4Acw",
    "position_transfer": "tblHMBTmte529H9K",
    "job_posting": "tbldWBRTNm5RrQHw",
    "candidate": "tblx3KvkQoHdGjFL",
    "onboarding": "tblK1IWXATe2Nn2q",
}

# 飞书多维表格真实子表名称（回填 base_table_name 用）
HR_FEISHU_DEFAULT_TABLE_NAMES: dict[str, str] = {
    "employee": "员工档案",
    "contract_management": "合同管理",
    "offboarding_record": "离职管理",
    "position_transfer": "岗位调动台账",
    "job_posting": "招聘职位表",
    "candidate": "候选人表",
    "onboarding": "入职信息表",
}

# 已知的历史错误 Table ID，对账时自动修正
HR_FEISHU_LEGACY_TABLE_IDS: dict[str, str] = {
    # position_transfer 旧默认值（已失效）→ 岗位调动台账真实 ID
    "tbltUuhrvHWrnJWT": "tblHMBTmte529H9K",
}


# ─── Helper functions ───


def _get_entity_prefill(entity_code: str) -> dict[str, str | None]:
    """Get prefill values for an entity.

    Priority: environment variable > known default > None.
    """
    prefill_config = HR_FEISHU_ENTITY_ENV_PREFILLS.get(entity_code)
    if not prefill_config:
        # Fall back to known defaults if no env prefill config
        if entity_code in HR_FEISHU_ENTITY_DEFAULT_TABLE_IDS:
            return {
                "app_token": _settings.FEISHU_BITABLE_APP_TOKEN or None,
                "table_id": HR_FEISHU_ENTITY_DEFAULT_TABLE_IDS[entity_code],
            }
        return {"app_token": None, "table_id": None}

    app_token = (
        getattr(_settings, prefill_config.get("app_token_setting", ""), None) or None
    )
    table_id = (
        getattr(_settings, prefill_config.get("table_id_setting", ""), None) or None
    )

    # Fall back to known defaults if environment variables are not set
    if not app_token:
        app_token = _settings.FEISHU_BITABLE_APP_TOKEN or None
    if not table_id and entity_code in HR_FEISHU_ENTITY_DEFAULT_TABLE_IDS:
        table_id = HR_FEISHU_ENTITY_DEFAULT_TABLE_IDS[entity_code]

    return {"app_token": app_token, "table_id": table_id}


def _build_app_settings_detail(row: HrFeishuAppSettings) -> HrFeishuAppSettingsDetail:
    secret_masked = None
    if row.app_secret:
        try:
            secret_masked = mask_api_key(decrypt_api_key(row.app_secret))
        except Exception:
            secret_masked = "****"
    return HrFeishuAppSettingsDetail(
        app_id=row.app_id,
        app_secret_masked=secret_masked,
        is_enabled=row.is_enabled,
        last_test_status=row.last_test_status,
        last_test_error=row.last_test_error,
        last_tested_at=row.last_tested_at,
    )


def _build_entity_setting_item(row: HrFeishuEntitySetting) -> HrFeishuEntitySettingItem:
    return HrFeishuEntitySettingItem(
        entity_code=row.entity_code,
        entity_name=row.entity_name,
        entity_group=row.entity_group,
        source_note=None,
        app_token=row.app_token,
        base_table_name=row.base_table_name,
        base_table_id=row.base_table_id,
        is_enabled=row.is_enabled,
        enable_push_to_feishu=row.enable_push_to_feishu,
        enable_pull_from_feishu=row.enable_pull_from_feishu,
        field_mappings=row.field_mappings or [],
        sort_order=row.sort_order,
        last_sync_status=row.last_sync_status,
        last_sync_error=row.last_sync_error,
        last_synced_at=row.last_synced_at,
    )


def _build_system_fields(entity_code: str) -> list[HrFeishuSystemFieldOption]:
    fields = HR_FEISHU_SYSTEM_FIELDS.get(entity_code, [])
    return [
        HrFeishuSystemFieldOption(field_key=f[0], field_label=f[1], direction=f[2])
        for f in fields
    ]


# ─── Core service functions ───


async def _ensure_app_settings_seeded(db: AsyncSession) -> HrFeishuAppSettings:
    """Ensure the singleton app settings row exists, seeding from env vars."""
    result = await db.execute(select(HrFeishuAppSettings).limit(1))
    row = result.scalar_one_or_none()
    if row:
        return row

    row = HrFeishuAppSettings(
        app_id=_settings.FEISHU_APP_ID or "",
        app_secret=encrypt_api_key(_settings.FEISHU_APP_SECRET)
        if _settings.FEISHU_APP_SECRET
        else "",
        is_enabled=True,
    )
    db.add(row)
    await db.flush()
    return row


async def get_hr_feishu_app_credentials(db: AsyncSession) -> tuple[str, str]:
    """Return ``(app_id, decrypted_app_secret)`` from the HR Feishu app settings DB row.

    Falls back to environment variables when the DB row is missing or empty,
    so callers without DB config still work in pure-env-var deployments.
    """
    result = await db.execute(select(HrFeishuAppSettings).limit(1))
    row = result.scalar_one_or_none()

    app_id = ""
    app_secret = ""
    if row:
        app_id = row.app_id or ""
        if row.app_secret:
            try:
                app_secret = decrypt_api_key(row.app_secret)
            except Exception:
                logger.warning("Failed to decrypt HR Feishu app_secret", exc_info=True)

    # Fall back to env vars
    if not app_id:
        app_id = _settings.FEISHU_APP_ID or ""
    if not app_secret:
        app_secret = _settings.FEISHU_APP_SECRET or ""

    return app_id, app_secret


async def ensure_hr_feishu_entity_settings(db: AsyncSession) -> None:
    """Ensure all default entity settings exist in DB, creating missing ones.

    Idempotent reconciliation:
    - Physically deletes rows whose entity_code is not in the default list
      (obsolete entities and orphan rows).
    - Auto-fills app_token/base_table_id/base_table_name for existing rows
      when empty and a known default is available.
    - Corrects known legacy wrong table IDs (HR_FEISHU_LEGACY_TABLE_IDS).
    """
    result = await db.execute(select(HrFeishuEntitySetting))
    existing = {row.entity_code: row for row in result.scalars().all()}

    # 物理清理不在保留列表中的配置行（无用实体与孤儿行）
    obsolete_codes = sorted(set(existing) - set(DEFAULT_HR_FEISHU_ENTITY_MAP))
    if obsolete_codes:
        await db.execute(
            delete(HrFeishuEntitySetting).where(
                HrFeishuEntitySetting.entity_code.in_(obsolete_codes)
            )
        )
        for code in obsolete_codes:
            existing.pop(code, None)
        logger.info(
            "已清理无用的 HR 飞书实体配置",
            extra={"module": "hr", "entity_codes": obsolete_codes},
        )

    for (
        entity_code,
        entity_name,
        entity_group,
        sort_order,
    ) in DEFAULT_HR_FEISHU_ENTITIES:
        prefill = _get_entity_prefill(entity_code)
        default_table_name = HR_FEISHU_DEFAULT_TABLE_NAMES.get(entity_code)

        if entity_code in existing:
            row = existing[entity_code]
            # Update name/group/sort_order if changed
            if row.entity_name != entity_name or row.entity_group != entity_group:
                row.entity_name = entity_name
                row.entity_group = entity_group
            if row.sort_order != sort_order:
                row.sort_order = sort_order
            # Auto-fill app_token / base_table_id / base_table_name if empty
            if not row.app_token and prefill["app_token"]:
                row.app_token = prefill["app_token"]
            if not row.base_table_id and prefill["table_id"]:
                row.base_table_id = prefill["table_id"]
            if not row.base_table_name and default_table_name:
                row.base_table_name = default_table_name
            # Correct known legacy wrong table IDs
            if row.base_table_id in HR_FEISHU_LEGACY_TABLE_IDS:
                corrected = HR_FEISHU_LEGACY_TABLE_IDS[row.base_table_id]
                logger.info(
                    "修正历史错误 Table ID",
                    extra={
                        "module": "hr",
                        "entity_code": entity_code,
                        "old_table_id": row.base_table_id,
                        "new_table_id": corrected,
                    },
                )
                row.base_table_id = corrected
            continue

        row = HrFeishuEntitySetting(
            entity_code=entity_code,
            entity_name=entity_name,
            entity_group=entity_group,
            sort_order=sort_order,
            app_token=prefill["app_token"],
            base_table_name=default_table_name,
            base_table_id=prefill["table_id"],
            is_enabled=True,
            enable_push_to_feishu=True,
            enable_pull_from_feishu=True,
            field_mappings=[],
        )
        db.add(row)

    await db.flush()


async def get_hr_feishu_app_settings(db: AsyncSession) -> HrFeishuAppSettingsDetail:
    row = await _ensure_app_settings_seeded(db)
    await db.commit()
    return _build_app_settings_detail(row)


async def update_hr_feishu_app_settings(
    db: AsyncSession, data: UpdateHrFeishuAppSettingsRequest
) -> HrFeishuAppSettingsDetail:
    row = await _ensure_app_settings_seeded(db)
    row.app_id = data.app_id.strip()
    if data.app_secret.strip():
        row.app_secret = encrypt_api_key(data.app_secret.strip())
    row.is_enabled = data.is_enabled
    await db.flush()
    await db.commit()
    return _build_app_settings_detail(row)


async def test_hr_feishu_app_settings(db: AsyncSession) -> HrFeishuSettingsTestResult:
    row = await _ensure_app_settings_seeded(db)
    now = datetime.now(UTC)

    app_id = row.app_id
    try:
        app_secret = decrypt_api_key(row.app_secret) if row.app_secret else ""
    except Exception:
        app_secret = ""

    if not app_id or not app_secret:
        row.last_test_status = "failed"
        row.last_test_error = "App ID 或 App Secret 未配置"
        row.last_tested_at = now
        await db.flush()
        await db.commit()
        return HrFeishuSettingsTestResult(
            success=False,
            message="App ID 或 App Secret 未配置",
            checked_at=now,
        )

    try:
        await FeishuAuth.get_tenant_access_token(app_id=app_id, app_secret=app_secret)
        row.last_test_status = "success"
        row.last_test_error = None
        row.last_tested_at = now
        await db.flush()
        await db.commit()
        return HrFeishuSettingsTestResult(
            success=True,
            message="飞书应用连接成功",
            checked_at=now,
        )
    except Exception as e:
        error_msg = str(e)
        row.last_test_status = "failed"
        row.last_test_error = error_msg
        row.last_tested_at = now
        await db.flush()
        await db.commit()
        return HrFeishuSettingsTestResult(
            success=False,
            message=f"连接失败: {error_msg}",
            checked_at=now,
        )


async def list_hr_feishu_entity_settings(
    db: AsyncSession,
) -> list[HrFeishuEntitySettingItem]:
    await ensure_hr_feishu_entity_settings(db)
    await db.commit()
    result = await db.execute(
        select(HrFeishuEntitySetting).order_by(HrFeishuEntitySetting.sort_order)
    )
    rows = result.scalars().all()
    return [_build_entity_setting_item(row) for row in rows]


async def list_hr_feishu_tables(
    db: AsyncSession, entity_code: str, app_token: str | None = None
) -> list[HrFeishuTableOption]:
    """List tables in the bitable app for the given entity."""
    # Resolve app credentials
    app_settings = await _ensure_app_settings_seeded(db)
    app_id = app_settings.app_id
    try:
        app_secret = (
            decrypt_api_key(app_settings.app_secret) if app_settings.app_secret else ""
        )
    except Exception:
        app_secret = ""

    # Resolve app_token: use provided > entity config > env prefill
    resolved_app_token = app_token
    if not resolved_app_token:
        result = await db.execute(
            select(HrFeishuEntitySetting).where(
                HrFeishuEntitySetting.entity_code == entity_code
            )
        )
        entity_row = result.scalar_one_or_none()
        if entity_row and entity_row.app_token:
            resolved_app_token = entity_row.app_token
    if not resolved_app_token:
        prefill = _get_entity_prefill(entity_code)
        resolved_app_token = prefill["app_token"]
    if not resolved_app_token:
        raise ValueError("未配置 App Token，请先填写或从环境变量预填")

    client = BitableClient(
        app_token=resolved_app_token,
        app_id=app_id or None,
        app_secret=app_secret or None,
    )
    tables = await client.list_tables()
    return [
        HrFeishuTableOption(
            table_id=t.get("table_id", ""), table_name=t.get("name", "")
        )
        for t in tables
    ]


async def get_hr_feishu_entity_field_mapping_bundle(
    db: AsyncSession,
    entity_code: str,
    app_token: str | None = None,
    table_id: str | None = None,
) -> HrFeishuEntityFieldMappingBundle:
    """Get field mapping bundle for an entity."""
    if entity_code not in DEFAULT_HR_FEISHU_ENTITY_MAP:
        raise ValueError(f"实体 {entity_code} 不存在")

    entity_meta = DEFAULT_HR_FEISHU_ENTITY_MAP[entity_code]
    entity_name = entity_meta[1]

    # Get saved entity setting
    result = await db.execute(
        select(HrFeishuEntitySetting).where(
            HrFeishuEntitySetting.entity_code == entity_code
        )
    )
    entity_row = result.scalar_one_or_none()

    resolved_app_token = app_token or (entity_row.app_token if entity_row else None)
    resolved_table_id = table_id or (entity_row.base_table_id if entity_row else None)

    if not resolved_app_token:
        prefill = _get_entity_prefill(entity_code)
        resolved_app_token = prefill["app_token"]
    if not resolved_table_id:
        prefill = _get_entity_prefill(entity_code)
        resolved_table_id = prefill["table_id"]

    # System fields
    system_fields = _build_system_fields(entity_code)

    # Feishu fields (fetch from API if possible)
    feishu_fields: list[HrFeishuFieldOption] = []
    if resolved_app_token and resolved_table_id:
        app_settings = await _ensure_app_settings_seeded(db)
        app_id = app_settings.app_id
        try:
            app_secret = (
                decrypt_api_key(app_settings.app_secret)
                if app_settings.app_secret
                else ""
            )
        except Exception:
            app_secret = ""
        try:
            client = BitableClient(
                app_token=resolved_app_token,
                app_id=app_id or None,
                app_secret=app_secret or None,
            )
            fields = await client.list_fields(resolved_table_id)
            feishu_fields = [
                HrFeishuFieldOption(
                    field_id=f.get("field_id", ""),
                    field_name=f.get("field_name", ""),
                    field_type=f.get("type"),
                )
                for f in fields
            ]
        except Exception as e:
            logger.warning("Failed to fetch feishu fields for %s: %s", entity_code, e)

    # Saved field mappings
    saved_mappings = (
        entity_row.field_mappings if entity_row and entity_row.field_mappings else []
    )

    return HrFeishuEntityFieldMappingBundle(
        entity_code=entity_code,
        entity_name=entity_name,
        system_fields=system_fields,
        feishu_fields=feishu_fields,
        field_mappings=saved_mappings,
    )


async def update_hr_feishu_entity_setting(
    db: AsyncSession, entity_code: str, data: UpdateHrFeishuEntitySettingRequest
) -> HrFeishuEntitySettingItem:
    await ensure_hr_feishu_entity_settings(db)
    result = await db.execute(
        select(HrFeishuEntitySetting).where(
            HrFeishuEntitySetting.entity_code == entity_code
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise ValueError(f"实体配置 {entity_code} 不存在")

    row.app_token = data.app_token
    row.base_table_name = data.base_table_name
    row.base_table_id = data.base_table_id
    row.is_enabled = data.is_enabled
    row.enable_push_to_feishu = data.enable_push_to_feishu
    row.enable_pull_from_feishu = data.enable_pull_from_feishu
    if data.field_mappings is not None:
        row.field_mappings = [m.model_dump() for m in data.field_mappings]

    await db.flush()
    await db.commit()
    return _build_entity_setting_item(row)


async def test_hr_feishu_entity_setting(
    db: AsyncSession, entity_code: str
) -> HrFeishuSettingsTestResult:
    result = await db.execute(
        select(HrFeishuEntitySetting).where(
            HrFeishuEntitySetting.entity_code == entity_code
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise ValueError(f"实体配置 {entity_code} 不存在")

    now = datetime.now(UTC)

    # Resolve credentials
    app_settings = await _ensure_app_settings_seeded(db)
    app_id = app_settings.app_id
    try:
        app_secret = (
            decrypt_api_key(app_settings.app_secret) if app_settings.app_secret else ""
        )
    except Exception:
        app_secret = ""

    app_token = row.app_token
    table_id = row.base_table_id

    if not app_token:
        prefill = _get_entity_prefill(entity_code)
        app_token = prefill["app_token"]
    if not table_id:
        prefill = _get_entity_prefill(entity_code)
        table_id = prefill["table_id"]

    if not app_token or not table_id:
        row.last_sync_status = "failed"
        row.last_sync_error = "App Token 或 Table ID 未配置"
        row.last_synced_at = now
        await db.flush()
        await db.commit()
        return HrFeishuSettingsTestResult(
            success=False,
            message="App Token 或 Table ID 未配置",
            checked_at=now,
            entity_code=entity_code,
        )

    try:
        client = BitableClient(
            app_token=app_token,
            app_id=app_id or None,
            app_secret=app_secret or None,
        )
        records = await client.search_records(table_id, page_size=1)
        row.last_sync_status = "success"
        row.last_sync_error = None
        row.last_synced_at = now
        await db.flush()
        await db.commit()
        return HrFeishuSettingsTestResult(
            success=True,
            message=f"连接成功，读取到 {len(records)} 条测试记录",
            checked_at=now,
            entity_code=entity_code,
            table_id=table_id,
        )
    except Exception as e:
        error_msg = str(e)
        row.last_sync_status = "failed"
        row.last_sync_error = error_msg
        row.last_synced_at = now
        await db.flush()
        await db.commit()
        return HrFeishuSettingsTestResult(
            success=False,
            message=f"连接失败: {error_msg}",
            checked_at=now,
            entity_code=entity_code,
            table_id=table_id,
        )
