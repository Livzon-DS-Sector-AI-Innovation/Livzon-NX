"""ESG 培训报表 Service."""

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.hr.esg_repository import EsgTrainingRecordRepository
from app.modules.hr.models import EsgTrainingRecord
from app.modules.hr.schemas import (
    EsgListFilters,
    EsgTrainingRecordCreate,
    EsgTrainingRecordUpdate,
)


class EsgTrainingRecordService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = EsgTrainingRecordRepository(session)

    async def get_record(self, record_id: UUID) -> EsgTrainingRecord:
        record = await self.repo.get_by_id(record_id)
        if not record:
            raise NotFoundException("ESG培训记录", str(record_id))
        return record

    async def create_record(self, data: EsgTrainingRecordCreate) -> EsgTrainingRecord:
        record = EsgTrainingRecord(**data.model_dump())
        return await self.repo.create(record)

    async def update_record(
        self, record_id: UUID, data: EsgTrainingRecordUpdate
    ) -> EsgTrainingRecord:
        record = await self.get_record(record_id)
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(record, field, value)
        return await self.repo.update(record)

    async def delete_record(self, record_id: UUID) -> None:
        record = await self.get_record(record_id)
        await self.repo.soft_delete(record)

    async def batch_delete_records(self, record_ids: list[UUID]) -> dict[str, Any]:
        """批量软删除 ESG 记录，返回 {deleted, failed}；未命中 ID 计入 failed."""
        deleted = 0
        failed: list[str] = []
        for record_id in record_ids:
            record = await self.repo.get_by_id(record_id)
            if record is None:
                failed.append(str(record_id))
                continue
            await self.repo.soft_delete(record)
            deleted += 1
        return {"deleted": deleted, "failed": failed}

    async def list_by_department(
        self,
        department: str,
        page: int = 1,
        page_size: int = 200,
        date_from: date | None = None,
        date_to: date | None = None,
        filters: EsgListFilters | None = None,
    ) -> tuple[list[EsgTrainingRecord], int]:
        return await self.repo.list_by_department(
            department=department,
            page=page,
            page_size=page_size,
            date_from=date_from,
            date_to=date_to,
            filters=filters,
        )

    async def filter_options(
        self,
        department: str,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, list[str]]:
        return await self.repo.filter_options(
            department=department, date_from=date_from, date_to=date_to
        )

    async def sync_from_ledger(self, department: str) -> dict[str, Any]:
        """从培训台账同步生成 ESG 培训报表记录（按选中部门口径）.

        台账口径与培训台账页面列表一致：按归属部门(ledger_department)筛选，
        存量归属部门为空时回退授课部门(teaching_dept)。不再按涉及部门
        (involved_depts)匹配，避免全厂性培训的多部门副本被重复计入选中部门。
        参训人员按姓名匹配员工档案，且仅录入归一后归属部门等于选中部门的人员
        （跨部门参训人员不计入本部门报表，与其他培训页面的人员归属口径一致）。
        ESG 记录的 department 即选中部门。

        集团 ESG 报表填报口径（按桌面《ESG培训报表.xlsx》模板）：
        培训方式=线下、口径=部门组织、身份所属地=中国大陆、层级留空。
        """
        from datetime import date as date_type

        from sqlalchemy import select

        from app.modules.hr.models import Employee

        # 1. 查询选中部门归属的未删除培训台账（口径与台账页面列表完全一致：
        #    ledger_department 命中；空值回退 teaching_dept（201 家族裸名除外）；
        #    201 家族裸名「201二车间」按 trainees 在飞书联系人中的部门归属 MC/DR；
        #    有拆分副本时隐藏裸名总副本）
        from app.modules.hr.repository import TrainingLedgerRepository
        from app.modules.hr.training_dept_resolver import (
            get_person_overrides,
            resolve_training_department,
        )

        ledgers, _ = await TrainingLedgerRepository(self.session).list_by_department(
            department=department, page=1, page_size=100000
        )

        # 选中部门归一（培训规范名幂等），供重名时区分比较
        norm_dept = await resolve_training_department(self.session, department)
        # 人员归属覆写优先：person 映射的人员按覆写部门判定归属
        person_overrides = await get_person_overrides(self.session)

        created = 0
        skipped_existing = 0
        skipped_unmatched = 0
        skipped_other_dept = 0
        current_year = date_type.today().year

        for ledger in ledgers:
            if not ledger.trainees or not ledger.training_date:
                continue

            # 2. 拆分参训人员
            names = [n.strip() for n in ledger.trainees.split("、") if n.strip()]

            for name in names:
                # 3. 查找已存在的 ESG 记录（去重键：培训日期+培训名称+姓名）
                existing = await self.repo.get_by_key(
                    ledger.training_date, ledger.training_subject or "", name
                )

                # 4. 按姓名查找员工档案
                emp_result = await self.session.execute(
                    select(Employee).where(
                        Employee.name == name,
                        Employee.is_deleted.is_(False),
                    )
                )
                emps = list(emp_result.scalars().all())

                # 5. 员工档案匹配：仅录入归一后归属部门等于选中部门的人员
                #    （人员归属覆写优先：person 映射的人员按覆写部门判定，
                #    档案仅提供层级/年龄等字段；resolve_training_department
                #    为 async，需显式循环）
                emp = None
                override = person_overrides.get(name)
                if override is not None:
                    if override != norm_dept:
                        skipped_other_dept += 1
                        continue
                    emp = emps[0] if emps else None
                else:
                    for e in emps:
                        resolved = await resolve_training_department(
                            self.session, e.department, e.sub_department
                        )
                        if resolved == norm_dept:
                            emp = e
                            break
                if emp is None:
                    if override is not None and override != norm_dept:
                        # 覆写指向其他部门：跨部门参训不计入本部门报表
                        skipped_other_dept += 1
                    elif emps:
                        # 档案存在但归属其他部门：跨部门参训不计入本部门报表
                        skipped_other_dept += 1
                    else:
                        skipped_unmatched += 1
                    continue

                # 6. 已存在记录：更新档案相关字段（年龄/层级等随飞书同步保
                # 持最新），不重复创建
                if existing is not None:
                    existing.employee_level = emp.level
                    existing.age = emp.age or (
                        (current_year - emp.birth_year) if emp.birth_year else None
                    )
                    existing.gender = emp.gender
                    existing.employee_account = emp.domain_account
                    skipped_existing += 1
                    continue

                # 7. 构建 ESG 记录（department 即选中部门；按集团报表口径固定：
                # 培训方式=线下、口径=部门组织、身份所属地=中国大陆；层级取自员工档案）
                esg = EsgTrainingRecord(
                    training_date=ledger.training_date,
                    training_name=ledger.training_subject or "",
                    training_method="线下",
                    caliber="部门组织",
                    training_type=ledger.training_type,
                    employee_name=name,
                    employee_account=emp.domain_account,
                    location_address="中国大陆",
                    department=department,
                    employee_level=emp.level,
                    gender=emp.gender,
                    # 年龄优先取员工档案 age 字段（飞书公式），无则按出生年份计算
                    age=emp.age
                    or ((current_year - emp.birth_year) if emp.birth_year else None),
                    duration=ledger.duration_hours,
                    remarks=None,
                    apply_company="丽珠集团（宁夏）制药有限公司",
                    apply_company_no=None,
                )
                await self.repo.create(esg)
                created += 1

        return {
            "created": created,
            "skipped": skipped_existing + skipped_unmatched + skipped_other_dept,
            "skipped_existing": skipped_existing,
            "skipped_unmatched": skipped_unmatched,
            "skipped_other_dept": skipped_other_dept,
        }
