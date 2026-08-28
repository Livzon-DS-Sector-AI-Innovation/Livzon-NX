"""合同管理 Service"""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.contract_repository import ContractRepository
from app.modules.hr.contract_schemas import (
    ContractManagementCreate,
    ContractManagementResponse,
    ContractManagementUpdate,
)

logger = logging.getLogger(__name__)

# 合同期次标签（单一来源，contract_api 期次+1 复用）
_SEQ_LABELS = {
    1: "首次",
    2: "第二次",
    3: "第三次",
    4: "第四次",
    5: "第五次",
    6: "第六次",
}


class ContractService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = ContractRepository(session)
        self.session = session

    async def list(self, page: Any = 1, page_size: Any = 20, **filters: Any) -> Any:
        records, total = await self.repo.list(page=page, page_size=page_size, **filters)
        return type(
            "ListResult",
            (),
            {
                "data": [ContractManagementResponse.model_validate(r) for r in records],
                "total": total,
                "page": page,
                "page_size": page_size,
            },
        )

    async def get(self, record_id: UUID) -> Any:
        record = await self.repo.get_by_id(record_id)
        if not record:
            raise ValueError("合同记录不存在")
        return ContractManagementResponse.model_validate(record)

    async def create(self, data: ContractManagementCreate) -> Any:
        record = await self.repo.create(data.model_dump())
        response = ContractManagementResponse.model_validate(record)
        # 方向 A：新增 → 飞书多维表格（响应返回后异步同步）
        await self._sync_push_create(record)
        return response

    async def update(self, record_id: UUID, data: ContractManagementUpdate) -> Any:
        record = await self.repo.get_by_id(record_id)
        if not record:
            raise ValueError("合同记录不存在")
        record = await self.repo.update(record, data.model_dump(exclude_unset=True))
        # 台账编辑回写员工档案（合同字段，保证两边一致）
        await self._sync_back_to_employee(record)
        response = ContractManagementResponse.model_validate(record)
        # 方向 A：修改 → 飞书多维表格
        await self._sync_push_update(record)
        return response

    async def delete(self, record_id: UUID) -> Any:
        record = await self.repo.get_by_id(record_id)
        if not record:
            raise ValueError("合同记录不存在")
        # 方向 A：删除 → 飞书多维表格（先同步后软删除）
        try:
            await self._sync_push_delete(record)
        except Exception:
            logger.exception("同步删除到飞书失败")
        await self.repo.soft_delete(record)

    # ─── 台账编辑回写员工档案 ───

    async def _sync_back_to_employee(self, record: Any) -> None:
        """台账编辑后回写员工档案合同字段（意见/负责人/合同日期），保证两边一致。"""
        from datetime import date as date_type
        from datetime import datetime as dt

        from sqlalchemy import select

        from app.modules.hr.models import Employee

        emp_result = await self.session.execute(
            select(Employee)
            .where(
                Employee.employee_number == record.employee_number,
                Employee.is_deleted.is_(False),
            )
            .limit(1)
        )
        emp = emp_result.scalars().first()
        if not emp:
            return

        def _to_date(v: Any) -> Any:
            """台账 String 日期 → date（解析失败返回 None）"""
            if v is None or v == "":
                return None
            if isinstance(v, date_type):
                return v
            s = str(v).strip()
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
                try:
                    return dt.strptime(s, fmt).date()
                except ValueError:
                    continue
            return None

        # 直接映射（同类型）
        direct_map = {
            "dept_leader_name": "dept_leader_name",
            "contract_opinion": "contract_opinion",
            "contract_start_1": "contract_start_date",
            "contract_end_1": "contract_end_date",
            "contract_start_2": "contract_start_2",
            "contract_start_3": "contract_start_3",
            "contract_start_4": "contract_start_4",
            "contract_start_5": "contract_start_5",
            "contract_start_6": "contract_start_6",
            "contract_end_5": "contract_end_5",
            "contract_end_6": "contract_end_6",
        }
        changed = False
        for cm_field, emp_field in direct_map.items():
            val = getattr(record, cm_field, None)
            if val is not None and getattr(emp, emp_field, None) != val:
                setattr(emp, emp_field, val)
                changed = True
        # 台账 String → 员工档案 Date 字段（contract_end_2..4）
        for cm_field, emp_field in [
            ("contract_end_2", "contract_end_2"),
            ("contract_end_3", "contract_end_3"),
            ("contract_end_4", "contract_end_4"),
        ]:
            raw = getattr(record, cm_field, None)
            parsed = _to_date(raw)
            if parsed is not None and getattr(emp, emp_field, None) != parsed:
                setattr(emp, emp_field, parsed)
                changed = True
        if changed:
            await self.session.flush()

    # ─── 飞书同步内部方法 ───

    async def _sync_push_create(self, record: Any) -> Any:
        """异步同步新增到飞书多维表格（不阻塞响应）"""
        try:
            from app.modules.hr.contract_sync_service import ContractSyncService

            sync_svc = ContractSyncService(self.session)
            await sync_svc.push_create(record)
        except Exception:
            logger.warning("ContractSync push_create failed", exc_info=True)

    async def _sync_push_update(self, record: Any) -> Any:
        """异步同步修改到飞书多维表格"""
        try:
            from app.modules.hr.contract_sync_service import ContractSyncService

            sync_svc = ContractSyncService(self.session)
            await sync_svc.push_update(record)
        except Exception:
            logger.warning("ContractSync push_update failed", exc_info=True)

    async def _sync_push_delete(self, record: Any) -> Any:
        """异步同步删除到飞书多维表格"""
        try:
            from app.modules.hr.contract_sync_service import ContractSyncService

            sync_svc = ContractSyncService(self.session)
            await sync_svc.push_delete(record)
        except Exception:
            logger.warning("ContractSync push_delete failed", exc_info=True)

    async def sync_from_feishu(self) -> Any:
        """方向 B：从飞书多维表格拉取数据"""
        from app.modules.hr.contract_sync_service import ContractSyncService

        sync_svc = ContractSyncService(self.session)
        return await sync_svc.pull_from_feishu()

    # ─── 数据归档方法 ───

    async def sync_from_contract_expiry(self, employee_data: dict[str, Any]) -> Any:
        """合同到期提醒归档 - 按真实续签次数写入对应字段"""
        from datetime import date as date_type
        from datetime import datetime as dt

        from sqlalchemy import select

        from app.modules.hr.models import ContractManagement as ContractRecord

        def _to_date(v: Any) -> Any:
            "repository 返回的 sign_date/end_d"
            "ate 是 isoformat 字符串，需转 date 写入"
            " DATE 列"
            if v is None:
                return None
            if isinstance(v, date_type):
                return v
            s = str(v).strip()
            for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
                try:
                    return dt.strptime(s, fmt).date()
                except ValueError:
                    continue
            return None

        name = employee_data.get("name", "")
        emp_no = employee_data.get("employee_number", "")
        existing = await self.repo.session.execute(
            select(ContractRecord)
            .where(
                ContractRecord.employee_number == emp_no,
                ContractRecord.name == name,
                ContractRecord.is_deleted.is_(False),
            )
            .limit(1)
        )
        existing_record = existing.scalars().first()

        seq = employee_data.get("contract_sequence")
        sign_date = employee_data.get("contract_sign_date")
        end_date = employee_data.get("contract_end_date")

        data = {
            "employee_number": emp_no,
            "name": name,
            "dept_level1": employee_data.get("department"),
            "dept_level2": employee_data.get("sub_department"),
            "position": employee_data.get("position"),
            "contract_sequence": self._seq_label(seq),
        }

        # 按真实续签次数写入对应的合同字段
        # contract_start_1..5 与 contract_end_1 为
        # DATE 列需转 date；其余为 VARCHAR 直接存字符串
        date_start_fields = {
            "contract_start_1",
            "contract_start_2",
            "contract_start_3",
            "contract_start_4",
            "contract_start_5",
        }
        seq_field_map = {
            1: ("contract_start_1", "contract_end_1"),
            2: ("contract_start_2", "contract_end_2"),
            3: ("contract_start_3", "contract_end_3"),
            4: ("contract_start_4", "contract_end_4"),
            5: ("contract_start_5", "contract_end_5"),
            6: ("contract_start_6", "contract_end_6"),
        }
        if seq in seq_field_map:
            start_field, end_field = seq_field_map[seq]
            if sign_date:
                data[start_field] = (
                    _to_date(sign_date)
                    if start_field in date_start_fields
                    else str(sign_date)
                )
            if end_date:
                data[end_field] = (
                    _to_date(end_date)
                    if end_field == "contract_end_1"
                    else str(end_date)
                )

        data = {k: v for k, v in data.items() if v}
        if existing_record:
            return await self.repo.update(existing_record, data)
        else:
            return await self.repo.create(data)

    async def sync_from_onboarding(self, onboarding_data: dict[str, Any]) -> Any:
        """入职完成时同步合同信息（自动设置首次合同，回写员工档案，同步到飞书）

        参考续签逻辑（contract_api.py renew_contract）：
        1. 创建合同管理记录
        2. 回写员工档案表的合同日期字段
        3. 同步合同管理到飞书
        4. 同步员工档案到飞书
        """
        from sqlalchemy import select

        from app.modules.hr.models import ContractManagement as ContractRecord
        from app.modules.hr.models import Employee

        name = onboarding_data.get("name", "")
        emp_no = onboarding_data.get("employee_number", "")
        # 去重：有工号时按工号+姓名去重；无工号时按姓名去重
        if emp_no:
            existing = await self.repo.session.execute(
                select(ContractRecord)
                .where(
                    ContractRecord.employee_number == emp_no,
                    ContractRecord.name == name,
                    ContractRecord.is_deleted.is_(False),
                )
                .limit(1)
            )
        else:
            existing = await self.repo.session.execute(
                select(ContractRecord)
                .where(
                    ContractRecord.name == name,
                    ContractRecord.employee_number == "",
                    ContractRecord.is_deleted.is_(False),
                )
                .limit(1)
            )
        if existing.scalars().first():
            return None
        data = {
            "employee_number": emp_no,
            "name": name,
            "gender": onboarding_data.get("gender"),
            "dept_level1": onboarding_data.get("department"),
            "dept_level2": onboarding_data.get("sub_department"),
            "position": onboarding_data.get("position"),
            "job_level": onboarding_data.get("level"),
            "id_card": onboarding_data.get("id_card"),
            "archive_number": onboarding_data.get("archive_number"),
            "contract_start_1": onboarding_data.get("contract_start_date"),
            "contract_end_1": onboarding_data.get("contract_end_date"),
            "contract_sequence": "首次",  # 入职首次合同
        }
        data = {k: v for k, v in data.items() if v}
        record = await self.repo.create(data)

        # 回写员工档案表（参考续签逻辑 contract_api.py:382-408）
        emp_result = await self.repo.session.execute(
            select(Employee)
            .where(
                Employee.employee_number == emp_no,
                Employee.is_deleted.is_(False),
            )
            .limit(1)
        )
        emp = emp_result.scalars().first()
        if emp:
            contract_start = onboarding_data.get("contract_start_date")
            contract_end = onboarding_data.get("contract_end_date")
            if contract_start:
                emp.contract_start_date = contract_start
            if contract_end:
                emp.contract_end_date = contract_end
            await self.repo.session.flush()

        # 同步到飞书多维表格
        try:
            from app.modules.hr.contract_sync_service import ContractSyncService

            sync_svc = ContractSyncService(self.repo.session)
            await sync_svc.push_create(record)
        except Exception:
            logger.warning("合同管理飞书同步失败", exc_info=True)

        # 同步员工档案到飞书（参考续签逻辑 contract_api.py:426-437）
        if emp:
            try:
                from app.modules.hr.service import EmployeeService

                emp_service = EmployeeService(self.repo.session)
                await emp_service._sync_single_to_feishu(emp)
            except Exception:
                logger.warning("员工档案飞书同步失败", exc_info=True)

        return record

    @staticmethod
    def _seq_label(seq: Any) -> Any:
        return _SEQ_LABELS.get(seq)
