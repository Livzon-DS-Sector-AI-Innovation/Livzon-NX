"""合同管理飞书多维表格双向同步 Service"""

import logging
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.feishu_settings_service import (
    _get_entity_prefill,
    get_hr_feishu_app_credentials,
)
from app.modules.hr.models import ContractManagement, HrFeishuEntitySetting
from app.platform.integrations.feishu.bitable import BitableClient, _to_ms_timestamp

# 飞书日期字段为用户时区（东八区）语义；按系统本地时区解析会在
# UTC 运行环境（CI/生产容器）把跨零点的时刻少算一天
_CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")

logger = logging.getLogger(__name__)

ENTITY_CODE = "contract_management"
PREFILL = _get_entity_prefill(ENTITY_CODE)


def _build_contract_fields(record: ContractManagement) -> dict[str, Any]:
    """将 ContractManagement ORM 对象转换为飞书多维表格字段
    - 工号: Number 类型，需要 int
    - 第几次合同续签: SingleSelect 类型，直接传选项文本
    - 日期字段: DateTime 类型，用毫秒时间戳
    """
    fields: dict[str, Any] = {}

    # 工号：飞书是 Number 类型，需要传 int
    if record.employee_number:
        try:
            fields["工号"] = int(record.employee_number)
        except (ValueError, TypeError):
            fields["工号"] = record.employee_number

    if record.name:
        fields["姓名"] = record.name
    if record.gender:
        fields["性别"] = record.gender
    if record.dept_level1:
        fields["一级部门"] = record.dept_level1
    if record.dept_level2:
        fields["二级部门"] = record.dept_level2
    if record.position:
        fields["职务|岗位"] = record.position
    if record.job_level:
        fields["职级"] = record.job_level
    if record.domain_account:
        fields["域账户"] = record.domain_account
    if record.id_card:
        fields["身份证号"] = record.id_card
    if record.id_card_expiry:
        fields["身份证有效期截止日期"] = record.id_card_expiry
    if record.archive_number:
        fields["档案编号"] = record.archive_number
    if record.contract_sequence:
        fields["第几次合同续签"] = record.contract_sequence

    # 纯日期字段（飞书 DateTime 类型）用毫秒时间戳
    date_only_fields = [
        ("首次签订合同日期", record.contract_start_1),
        ("首次签订合同截止日期", record.contract_end_1),
        ("第二次续签合同日期", record.contract_start_2),
        ("第三次续签合同日期", record.contract_start_3),
        ("第四次续签合同日期", record.contract_start_4),
        ("第五次续签合同日期", record.contract_start_5),
    ]
    for field_name, date_value in date_only_fields:
        ts = _to_ms_timestamp(date_value)
        if ts != "":
            fields[field_name] = ts

    # 合同截止日期 2-5 在飞书是 Text 类型，直接赋值
    str_fields = [
        ("合同截止日期（2）", record.contract_end_2),
        ("合同截止日期（3）", record.contract_end_3),
        ("合同截止日期4", record.contract_end_4),
        ("合同截止日期5", record.contract_end_5),
    ]
    for field_name, str_value in str_fields:
        if str_value:
            fields[field_name] = str_value

    # 第六次合同（飞书是 Text 类型）
    if record.contract_start_6:
        fields["第六次续签合同日期"] = record.contract_start_6
    if record.contract_end_6:
        fields["合同截止日期6"] = record.contract_end_6

    return fields


class ContractSyncService:
    """合同管理与飞书多维表格双向同步"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._bitable: BitableClient | None = None

    async def _get_bitable_config(
        self,
    ) -> tuple[str | None, str | None, str | None, str | None]:
        """获取飞书多维表格配置：按优先级 DB entity setting > env prefill"""
        result = await self.session.execute(
            select(HrFeishuEntitySetting).where(
                HrFeishuEntitySetting.entity_code == ENTITY_CODE
            )
        )
        entity_row = result.scalar_one_or_none()

        app_token = (
            entity_row.app_token
            if entity_row and entity_row.app_token
            else PREFILL.get("app_token")
        )
        table_id = (
            entity_row.base_table_id
            if entity_row and entity_row.base_table_id
            else PREFILL.get("table_id")
        )

        if not app_token or not table_id:
            return None, None, None, None

        app_id, app_secret = await get_hr_feishu_app_credentials(self.session)
        return app_token, table_id, app_id, app_secret

    async def _get_bitable(self) -> BitableClient | None:
        """懒加载 BitableClient"""
        if self._bitable:
            return self._bitable
        app_token, table_id, app_id, app_secret = await self._get_bitable_config()
        if not app_token or not table_id:
            logger.warning("[ContractSync] 飞书多维表格未配置")
            return None
        self._bitable = BitableClient(
            app_token=app_token,
            app_id=app_id or None,
            app_secret=app_secret or None,
        )
        self._table_id = table_id
        return self._bitable

    # ─── 方向 A：本地 PostgreSQL → 飞书多维表格 ───

    async def push_create(self, record: ContractManagement) -> None:
        """页面新增 → 飞书新增"""
        bitable = await self._get_bitable()
        if not bitable:
            return
        try:
            fields = _build_contract_fields(record)
            feishu_record = await bitable.create_record(self._table_id, fields)
            feishu_record_id = feishu_record.get("record_id", "")
            record.feishu_record_id = feishu_record_id
            record.feishu_synced_at = datetime.now(UTC)
            await self.session.flush()
            logger.info(
                "[ContractSync] push_create success: %s (%s) -> feishu %s",
                record.name,
                record.employee_number,
                feishu_record_id,
            )
        except Exception as e:
            logger.error(
                "[ContractSync] push_create failed: %s (%s): %s",
                record.name,
                record.employee_number,
                e,
            )

    async def push_update(self, record: ContractManagement) -> None:
        """页面修改 -> 飞书更新（更新失败时自动 fallback 到创建）"""
        bitable = await self._get_bitable()
        if not bitable:
            return
        if not record.feishu_record_id:
            record.feishu_record_id = await self._find_feishu_record(
                record.employee_number
            )
            if not record.feishu_record_id:
                await self.push_create(record)
                return
        try:
            fields = _build_contract_fields(record)
            await bitable.update_record(self._table_id, record.feishu_record_id, fields)
            record.feishu_synced_at = datetime.now(UTC)
            await self.session.flush()
            logger.info(
                "[ContractSync] push_update success: %s (%s)",
                record.name,
                record.employee_number,
            )
        except Exception as e:
            logger.warning(
                (
                    "[ContractSync] push_update failed, fallb"
                    "ack to push_create: %s (%s): %s"
                ),
                record.name,
                record.employee_number,
                e,
            )
            # 更新失败（飞书记录可能已删除），清除旧 record_id 重新创建
            record.feishu_record_id = None
            await self.push_create(record)

    async def push_delete(self, record: ContractManagement) -> None:
        """页面删除 → 飞书删除"""
        bitable = await self._get_bitable()
        if not bitable:
            return
        if not record.feishu_record_id:
            record.feishu_record_id = await self._find_feishu_record(
                record.employee_number
            )
        if not record.feishu_record_id:
            logger.info(
                "[ContractSync] push_delete skipped: no feishu record for %s",
                record.employee_number,
            )
            return
        try:
            await bitable.delete_record(self._table_id, record.feishu_record_id)
            logger.info(
                "[ContractSync] push_delete success: %s (%s)",
                record.name,
                record.employee_number,
            )
        except Exception as e:
            logger.error(
                "[ContractSync] push_delete failed: %s (%s): %s",
                record.name,
                record.employee_number,
                e,
            )

    async def _find_feishu_record(self, employee_number: str) -> str | None:
        """按工号在飞书多维表格中查找 record_id（工号是 Number 类型）"""
        bitable = await self._get_bitable()
        if not bitable:
            return None
        items = await bitable.search_records(
            self._table_id,
            filter_info={
                "conjunction": "and",
                "conditions": [
                    {
                        "field_name": "工号",
                        "operator": "is",
                        "value": [str(employee_number)],
                    }
                ],
            },
        )
        return items[0].get("record_id") if items else None

    # ─── 方向 B：飞书多维表格 → 本地 PostgreSQL ───

    async def pull_from_feishu(self) -> dict[str, Any]:
        """从飞书多维表格全量拉取合同数据，同步到本地 PostgreSQL

        以飞书数据为主：
        - 飞书有 -> 本地有：更新（覆盖）
        - 飞书有 -> 本地无：创建
        - 飞书无 -> 本地有：删除（软删除）
        """
        bitable = await self._get_bitable()
        if not bitable:
            return {
                "created": 0,
                "updated": 0,
                "deleted": 0,
                "total": 0,
                "error": "飞书多维表格未配置",
            }

        try:
            feishu_records = await bitable.search_records(self._table_id, page_size=500)
            logger.info(
                "[ContractSync] pull_from_feishu: fetched %d records",
                len(feishu_records),
            )
        except Exception as e:
            logger.exception("[ContractSync] pull_from_feishu fetch failed")
            return {
                "created": 0,
                "updated": 0,
                "deleted": 0,
                "total": 0,
                "error": str(e),
            }

        created, updated, deleted = 0, 0, 0
        feishu_emp_nos = set()  # 收集飞书所有工号

        for feishu_r in feishu_records:
            try:
                feishu_fields = feishu_r.get("fields", {})
                emp_no = feishu_fields.get("工号", "")
                if not emp_no:
                    continue
                emp_no = str(emp_no)  # 飞书 Number 类型转 string
                feishu_emp_nos.add(emp_no)

                existing = await self.session.execute(
                    select(ContractManagement)
                    .where(
                        ContractManagement.employee_number == emp_no,
                        ContractManagement.is_deleted.is_(False),
                    )
                    .limit(1)
                )
                local_record = existing.scalars().first()

                data = self._convert_feishu_to_local(feishu_fields)
                data["feishu_record_id"] = feishu_r.get("record_id", "")
                data["feishu_synced_at"] = datetime.now(UTC)
                # 飞书同步来源标记（未走审批流程），台账列表据此与审批流程记录区分
                data["approval_status"] = "synced"

                if local_record:
                    # 飞书有 -> 本地有：完全覆盖
                    for k, v in data.items():
                        setattr(local_record, k, v)
                    updated += 1
                else:
                    # 飞书有 -> 本地无：创建
                    local_record = ContractManagement(**data)
                    self.session.add(local_record)
                    created += 1
            except Exception as e:
                logger.error(
                    "[ContractSync] pull_from_feishu error for %s: %s", emp_no, e
                )

        # 飞书无 -> 本地有：软删除（飞书为唯一数据源，飞书无对应数据即删除本地）
        if feishu_emp_nos:
            local_delete_stmt = select(ContractManagement).where(
                or_(
                    ~ContractManagement.employee_number.in_(feishu_emp_nos),
                    ContractManagement.employee_number.is_(None),
                )
            )
        else:
            # 飞书为空：本地全部软删除，保持平台与飞书一致
            local_delete_stmt = select(ContractManagement).where(
                ContractManagement.is_deleted.is_(False)
            )
        local_to_delete = await self.session.execute(local_delete_stmt)
        for record in local_to_delete.scalars().all():
            record.is_deleted = True
            deleted += 1

        await self.session.flush()

        result = {
            "created": created,
            "updated": updated,
            "deleted": deleted,
            "total": len(feishu_records),
        }
        logger.info("[ContractSync] pull_from_feishu done: %s", result)
        return result

    def _convert_feishu_to_local(self, feishu_fields: dict[str, Any]) -> dict[str, Any]:
        """将飞书字段映射为本地 ContractManagement 字段"""
        from datetime import datetime as dt

        mapping = {
            "工号": "employee_number",
            "姓名": "name",
            "性别": "gender",
            "一级部门": "dept_level1",
            "二级部门": "dept_level2",
            "职务|岗位": "position",
            "职级": "job_level",
            "域账户": "domain_account",
            "身份证号": "id_card",
            "身份证有效期截止日期": "id_card_expiry",
            "档案编号": "archive_number",
            "第几次合同续签": "contract_sequence",
            "首次签订合同日期": "contract_start_1",
            "首次签订合同截止日期": "contract_end_1",
            "第二次续签合同日期": "contract_start_2",
            "合同截止日期（2）": "contract_end_2",
            "第三次续签合同日期": "contract_start_3",
            "合同截止日期（3）": "contract_end_3",
            "第四次续签合同日期": "contract_start_4",
            "合同截止日期4": "contract_end_4",
            "第五次续签合同日期": "contract_start_5",
            "合同截止日期5": "contract_end_5",
            "第六次续签合同日期": "contract_start_6",
            "合同截止日期6": "contract_end_6",
        }

        # Date 类型字段（本地是 DATE），飞书返回毫秒时间戳需要转换
        date_fields = {
            "contract_start_1",
            "contract_end_1",
            "contract_start_2",
            "contract_start_3",
            "contract_start_4",
            "contract_start_5",
        }

        result: dict[str, Any] = {}
        for feishu_key, local_key in mapping.items():
            val = feishu_fields.get(feishu_key)
            # 以飞书为主：飞书字段不存在或无值 → 本地显式清空（覆盖旧值）
            if val is None or val == "":
                result[local_key] = None
                continue
            # 飞书文本字段格式：[{'text': '...', 'type': 'text'}]
            if (
                isinstance(val, list)
                and len(val) > 0
                and isinstance(val[0], dict)
                and "text" in val[0]
            ):
                val = val[0]["text"]
            # 工号在飞书是 Number 类型，转 string
            if local_key == "employee_number":
                val = str(val)
            # 飞书日期字段返回毫秒时间戳，需要转成 date 对象
            if local_key in date_fields and isinstance(val, (int, float)):
                val = dt.fromtimestamp(val / 1000, tz=_CHINA_TIMEZONE).date()
            result[local_key] = val

        return result
