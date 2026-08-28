"""新员工培训 Service.

业务规则：
- 新员工入职后，按部门+岗位匹配岗位培训清单，复制教材为部门级培训计划
- 公司级培训完成状态：培训台账 trainees 含员工姓名 且
(level_category='一级' 或
plan_source='公司计划')
- 计划项完成状态：培训台账 trainees 含员工姓名 且 training_content 含教材名
- 状态流转：全部完成→已完成；超过截止日期→逾期；已指定导师→培训中；否则待安排
"""

import logging
import re
from datetime import date, timedelta
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.modules.hr.models import (
    NewEmployeeTrainingPlan,
    TrainingLedger,
    TrainingSession,
)
from app.modules.hr.new_employee_training_repository import (
    NewEmployeeTrainingRepository,
)
from app.modules.hr.position_training_mapping_repository import (
    PositionTrainingMappingRepository,
)
from app.modules.hr.schemas import (
    NewEmployeeTrainingPlanUpdate,
    NewEmployeeTrainingStartResponse,
    NewEmployeeTrainingStats,
)

logger = logging.getLogger(__name__)

# 新员工部门级培训周期（入职 + 30 天）
TRAINING_DEADLINE_DAYS = 30


def _normalize_text(text: str | None) -> str:
    """归一化文本：去所有空白，用于教材名匹配。"""
    if not text:
        return ""
    return re.sub(r"\s+", "", text)


class NewEmployeeTrainingService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = NewEmployeeTrainingRepository(session)
        self.mapping_repo = PositionTrainingMappingRepository(session)
        self.session = session

    async def _resolve_training_position(
        self, department: str, sub_department: str | None, position: str
    ) -> str | None:
        """从映射表解析培训岗位。

        先按归一后的培训部门（如 201二车间→201二车间（MC）、动力科→动力部）查询，
        未命中再回退原档案部门（兼容历史映射）。同部门不同子部门（201一车间/201二车间）映射互不干扰。
        """
        from app.modules.hr.training_dept_resolver import resolve_training_department

        resolved = await resolve_training_department(
            self.session, department, sub_department
        )
        mapping = await self.mapping_repo.get_mapping(resolved or department, position)
        if not mapping:
            mapping = await self.mapping_repo.get_mapping(department, position)
        return mapping.training_position if mapping else None

    # ─── 进度计算（培训台账是唯一事实来源）───

    def _is_item_done(self, ledger: TrainingLedger, textbook_name: str) -> bool:
        """计划项完成：台账 training_content 含教材名（去空白归一化匹配）。"""
        if not ledger.trainees or not textbook_name:
            return False
        content = _normalize_text(ledger.training_content)
        name = _normalize_text(textbook_name)
        if not content or not name:
            return False
        return name in content

    def _compute_item_done_map(
        self, ledgers: list[TrainingLedger], items: list[dict[str, Any]]
    ) -> dict[str, date]:
        """返回 {item_id: 完成日期}，按台账培训日期升序取最早完成日期。"""
        done_map: dict[str, date] = {}
        for item in items:
            item_id = item.get("id")
            if not item_id:
                continue
            name = item.get("textbook_name") or ""
            for ledger in ledgers:
                if self._is_item_done(ledger, name):
                    done_map[item_id] = ledger.training_date
                    break
        return done_map

    def _compute_plan_status(
        self,
        *,
        completed_count: int,
        total_count: int,
        deadline_date: date | None,
        today: date | None = None,
    ) -> str:
        today = today or date.today()
        if total_count == 0:
            return "待安排"
        if completed_count >= total_count:
            return "已完成"
        if deadline_date and today > deadline_date:
            return "逾期"
        return "待安排"

    def _build_item_dicts(self, plan: NewEmployeeTrainingPlan) -> list[dict[str, Any]]:
        items = plan.items or []
        result: list[dict[str, Any]] = []
        for idx, raw in enumerate(items):
            if isinstance(raw, dict):
                result.append(
                    {
                        "id": raw.get("id") or str(uuid4()),
                        "level": raw.get("level") or "部门级",
                        "textbook_name": raw.get("textbook_name") or "",
                        "textbook_code": raw.get("textbook_code"),
                        "assessment_method": raw.get("assessment_method"),
                        "remark": raw.get("remark"),
                        "manual": bool(raw.get("manual")),
                        "sort_order": raw.get("sort_order")
                        if raw.get("sort_order") is not None
                        else idx,
                    }
                )
        result.sort(key=lambda x: int(x["sort_order"] or 0))
        return result

    async def _build_response(self, plan: NewEmployeeTrainingPlan) -> dict[str, Any]:
        items = self._build_item_dicts(plan)
        ledgers = await self.repo.list_ledgers_by_employee_name(plan.employee_name)
        done_map = self._compute_item_done_map(ledgers, items)
        for item in items:
            item["completed_date"] = done_map.get(item["id"])
        completed_count = len(done_map)
        total_count = len(items)
        status = self._compute_plan_status(
            completed_count=completed_count,
            total_count=total_count,
            deadline_date=plan.deadline_date,
        )
        progress = round(completed_count / total_count * 100) if total_count else 0
        # 培训岗位：优先读计划自身（每人独立配置），无则回退映射默认（兼容旧计划）
        training_position: str | None
        if plan.training_position:
            training_position = plan.training_position
        else:
            training_position = await self._resolve_training_position(
                plan.department, plan.sub_department, plan.position
            )
        return {
            "id": plan.id,
            "employee_id": plan.employee_id,
            "employee_name": plan.employee_name,
            "employee_number": plan.employee_number,
            "department": plan.department,
            "sub_department": plan.sub_department,
            "position": plan.position,
            "hire_date": plan.hire_date.isoformat(),
            "deadline_date": plan.deadline_date.isoformat(),
            "items": items,
            "status": status,
            "total_count": total_count,
            "completed_count": completed_count,
            "progress": progress,
            "training_position": training_position,
            "created_at": plan.created_at.isoformat() if plan.created_at else None,
            "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
        }

    async def _build_plan_items(
        self,
        *,
        training_position: str | None,
        department: str,
        sub_department: str | None,
        employee_name: str,
    ) -> list[dict[str, Any]]:
        """按培训岗位从岗位培训清单生成教材明细（已培训内容去重，以台账为准）。

        供 generate_plan（初始生成）与 update_plan（调岗重算）共用。
        """
        if training_position:
            lists = await self.repo.list_position_training_lists_by_dept_and_position(
                departments=[department, sub_department or ""],
                position=training_position,
            )
        else:
            # 回退：按部门匹配
            lists = await self.repo.list_position_training_lists_by_dept(
                [department, sub_department or ""]
            )
        # 已培训教材去重：以台账为准（调岗重新生成计划时不重复安排已培训内容）
        ledgers = await self.repo.list_ledgers_by_employee_name(employee_name)
        items: list[dict[str, Any]] = []
        for lst in lists:
            for item in lst.items or []:
                if not item.textbook_name:
                    continue
                if any(
                    self._is_item_done(ledger, item.textbook_name) for ledger in ledgers
                ):
                    continue
                items.append(
                    {
                        "id": str(uuid4()),
                        "level": item.level,
                        "textbook_name": item.textbook_name,
                        "textbook_code": item.textbook_code,
                        "assessment_method": item.assessment_method,
                        "remark": item.remarks,
                        "manual": False,
                        "sort_order": len(items),
                    }
                )
        return items

    # ─── 生成计划 ───

    async def generate_plan(
        self,
        employee_id: UUID,
        user_id: UUID | None,
        training_position: str | None = None,
    ) -> NewEmployeeTrainingPlan:
        employee = await self.repo.get_employee_by_id(employee_id)
        if not employee:
            raise NotFoundException(resource="员工", resource_id=str(employee_id))

        existing = await self.repo.get_by_employee_id(employee_id)
        if existing:
            return existing

        # 培训岗位：显式传入优先；未传入时从映射表解析初始默认（保存后
        # 以计划自身为准，每人
        # 独立）
        if not training_position:
            training_position = await self._resolve_training_position(
                employee.department, employee.sub_department, employee.position or ""
            )

        items = await self._build_plan_items(
            training_position=training_position,
            department=employee.department,
            sub_department=employee.sub_department,
            employee_name=employee.name,
        )

        deadline = employee.hire_date + timedelta(days=TRAINING_DEADLINE_DAYS)
        # department 存员工档案一级部门，sub_department 存二级部门，
        # 匹配时按页面部门对两者任一命中即可
        plan = NewEmployeeTrainingPlan(
            employee_id=employee.id,
            employee_name=employee.name,
            employee_number=employee.employee_number,
            department=employee.department,
            sub_department=employee.sub_department,
            position=employee.position or "",
            training_position=training_position,
            hire_date=employee.hire_date,
            deadline_date=deadline,
            items=items,
            status="待安排",
            created_by=user_id,
            updated_by=user_id,
        )
        await self.repo.create(plan)
        logger.info(
            "new employee training plan generated",
            extra={
                "employee_id": str(employee.id),
                "employee_name": employee.name,
                "item_count": len(items),
                "training_position": training_position,
                "module_name": "hr",
            },
        )
        return plan

    async def create_manual_plan(
        self,
        name: str,
        department: str,
        position: str,
        hire_date: date,
        user_id: UUID | None,
        *,
        sub_department: str | None = None,
        training_position: str | None = None,
        employee_id: UUID | None = None,
    ) -> NewEmployeeTrainingPlan:
        """手动新增新员工培训计划（离岗复训等场景）。

        规则：
        - 员工在档案中（请求携带 employee_id 或按姓名唯一匹配）：
          入职日期/部门/岗位强制以档案为准（减少重复录入并保证一致性）；
          employee_id 使用档案 ID。
        - 不在档案（无匹配或多个匹配）：按前端传入值创建；
          employee_id 用 uuid5 派生稳定虚拟 ID（满足 NOT NULL 且可查重，
          该列无外键约束，纯逻辑引用）。
        - 查重：同名 + 同部门已有未删除计划 → 返回现有计划（不重复创建）。
        - 培训截止日期 = 入职日期 + TRAINING_DEADLINE_DAYS（与自动拉取一致）。
        """
        # 1) 档案匹配：请求未携带 employee_id 时按姓名查询员工档案
        from app.modules.hr.repository import EmployeeRepository
        from app.modules.hr.training_dept_resolver import resolve_training_department

        emp_repo = EmployeeRepository(self.session)
        if employee_id is None:
            matched, _ = await emp_repo.list_employees(
                keyword=name, page=1, page_size=100
            )
            exact = [e for e in matched if e.name == name]
            if len(exact) == 1:
                employee = exact[0]
                employee_id = employee.id
                department = employee.department
                sub_department = employee.sub_department
                position = employee.position or position
                hire_date = employee.hire_date

        # 1.5) 落库前归一：档案带出的一级部门（201车间/动力科）或手输别名写法
        #      → 培训规范名（201一车间/201二车间（MC）/动力部），与列表页 Tab 一致；
        #      保证手动新增与自动拉取两种存储格式查重与候选中一致命中
        if department:
            department = (
                await resolve_training_department(
                    self.session, department, sub_department
                )
            ) or department

        # 2) 培训岗位：显式传入优先；档案唯一命中且未传时解析映射默认
        if not training_position and employee_id is not None:
            employee_by_id = await emp_repo.get_by_id(employee_id)
            if employee_by_id:
                training_position = await self._resolve_training_position(
                    employee_by_id.department,
                    employee_by_id.sub_department,
                    employee_by_id.position or "",
                )

        # 3) 查重：同名 + 同部门已有未删除计划 → 直接返回现有计划
        existing = await self.repo.get_by_name_and_department(name, department)
        if existing:
            return existing

        # 4) employee_id 兜底：不在档案员工生成稳定虚拟 UUID
        if employee_id is None:
            employee_id = uuid5(NAMESPACE_URL, f"manual:{name}:{department}")

        items = await self._build_plan_items(
            training_position=training_position,
            department=department,
            sub_department=sub_department,
            employee_name=name,
        )
        deadline = hire_date + timedelta(days=TRAINING_DEADLINE_DAYS)
        plan = NewEmployeeTrainingPlan(
            employee_id=employee_id,
            employee_name=name,
            employee_number=None,
            department=department,
            sub_department=sub_department,
            position=position,
            training_position=training_position,
            hire_date=hire_date,
            deadline_date=deadline,
            items=items,
            status="待安排",
            created_by=user_id,
            updated_by=user_id,
        )
        await self.repo.create(plan)
        logger.info(
            "new employee training plan created manually",
            extra={
                "employee_id": str(employee_id),
                "employee_name": name,
                "department": department,
                "item_count": len(items),
                "training_position": training_position,
                "module_name": "hr",
            },
        )
        return plan

    # ─── 列表 ───

    async def list_plans(
        self,
        page: int = 1,
        page_size: int = 20,
        department: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
        dept_alias_set: set[str] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        plans, total = await self.repo.list_plans(
            page=page,
            page_size=page_size,
            department=department,
            status=status,
            keyword=keyword,
            dept_alias_set=dept_alias_set,
        )
        result: list[dict[str, Any]] = []
        for plan in plans:
            resp = await self._build_response(plan)
            result.append(
                {
                    "plan_id": resp["id"],
                    "employee_id": resp["employee_id"],
                    "employee_name": resp["employee_name"],
                    "employee_number": resp["employee_number"],
                    "department": resp["department"],
                    "sub_department": resp["sub_department"],
                    "position": resp["position"],
                    "hire_date": resp["hire_date"],
                    "deadline_date": resp["deadline_date"],
                    "status": resp["status"],
                    "total_count": resp["total_count"],
                    "completed_count": resp["completed_count"],
                    "progress": resp["progress"],
                    "training_position": resp["training_position"],
                }
            )
        return result, total

    async def list_pending_employees(
        self,
        hire_date_from: date,
        department: str | None = None,
        page: int = 1,
        page_size: int = 100,
        visible_norms: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """入职3个月内、尚未生成培训计划的员工（用于列表合并展示）。

        部门匹配：员工档案部门（飞书叫法，如
        201二车间）先归一为培训部门名再与选中部门比较；
        归一后不在培训规范部门列表中的员工不展示（如 财务部/冻结用户等培训体系外部门）。
        """
        from app.modules.hr.repository import TrainingLedgerRepository
        from app.modules.hr.training_dept_resolver import resolve_training_department

        employees, _ = await self.repo.list_recent_employees(
            hire_date_from=hire_date_from, page=page, page_size=page_size
        )
        training_depts = await TrainingLedgerRepository(
            self.session
        ).list_all_training_departments()
        result: list[dict[str, Any]] = []
        for emp in employees:
            existing = await self.repo.get_by_employee_id(emp.id)
            if existing:
                continue
            # 员工档案部门归一（201二车间→201二车间（MC）、动力科→动力部 等）
            emp_dept = emp.department
            emp_sub = emp.sub_department
            resolved = await resolve_training_department(
                self.session, emp_dept, emp_sub
            )
            if department:
                if resolved != department:
                    continue
            elif visible_norms is not None:
                # 部门级数据隔离：仅展示可见规范部门内的待培训员工
                if resolved not in visible_norms:
                    continue
            elif resolved not in training_depts:
                # 无部门筛选时也剔除培训体系外部门（不显示）
                continue
            # 查询映射获取培训岗位
            training_position = await self._resolve_training_position(
                emp.department, emp.sub_department, emp.position or ""
            )
            result.append(
                {
                    "employee_id": emp.id,
                    "employee_name": emp.name,
                    "employee_number": emp.employee_number,
                    "department": emp_dept,
                    "sub_department": emp_sub,
                    "position": emp.position or "",
                    "hire_date": emp.hire_date.isoformat(),
                    "training_position": training_position,
                }
            )
        return result

    # ─── 详情 / 更新 / 删除 ───

    async def get_plan(self, plan_id: UUID) -> dict[str, Any] | None:
        plan = await self.repo.get_by_id(plan_id)
        if not plan:
            return None
        return await self._build_response(plan)

    async def update_plan(
        self, plan_id: UUID, data: NewEmployeeTrainingPlanUpdate, user_id: UUID | None
    ) -> dict[str, Any] | None:
        plan = await self.repo.get_by_id(plan_id)
        if not plan:
            return None
        update: dict[str, Any] = {}
        if data.deadline_date is not None:
            update["deadline_date"] = data.deadline_date
        if data.training_position is not None:
            # 调岗：更新培训岗位并按新岗位重算教材明细（已培训内容去重，以台账为准）
            update["training_position"] = data.training_position
            update["items"] = await self._build_plan_items(
                training_position=data.training_position,
                department=plan.department,
                sub_department=plan.sub_department,
                employee_name=plan.employee_name,
            )
        if data.items is not None:
            items = []
            for idx, item in enumerate(data.items):
                items.append(
                    {
                        "id": item.id or str(uuid4()),
                        "level": item.level,
                        "textbook_name": item.textbook_name,
                        "textbook_code": item.textbook_code,
                        "assessment_method": item.assessment_method,
                        "remark": item.remark,
                        "manual": item.manual,
                        "sort_order": idx,
                    }
                )
            update["items"] = items
        if not update:
            return await self._build_response(plan)
        update["updated_by"] = user_id
        await self.repo.update(plan, update)
        return await self._build_response(plan)

    async def add_item(
        self, plan_id: UUID, item: dict[str, Any], user_id: UUID | None
    ) -> dict[str, Any] | None:
        plan = await self.repo.get_by_id(plan_id)
        if not plan:
            return None
        items = self._build_item_dicts(plan)
        items.append(
            {
                "id": str(uuid4()),
                "level": item.get("level") or "部门级",
                "textbook_name": item.get("textbook_name") or "",
                "textbook_code": item.get("textbook_code"),
                "assessment_method": item.get("assessment_method"),
                "remark": item.get("remark"),
                "manual": True,
                "sort_order": len(items),
            }
        )
        await self.repo.update(plan, {"items": items, "updated_by": user_id})
        return await self._build_response(plan)

    async def delete_plan(self, plan_id: UUID, user_id: UUID | None) -> bool:
        plan = await self.repo.get_by_id(plan_id)
        if not plan:
            return False
        plan.updated_by = user_id
        await self.repo.delete(plan)
        return True

    # ─── 开始培训（创建培训会话，跳转培训资料页面预填）───

    async def start_training(
        self,
        plan_id: UUID,
        item_ids: list[str],
        user_id: UUID | None,
        additional_trainees: list[dict[str, Any]] | None = None,
    ) -> NewEmployeeTrainingStartResponse:
        plan = await self.repo.get_by_id(plan_id)
        if not plan:
            raise NotFoundException(resource="新员工培训计划", resource_id=str(plan_id))
        if not item_ids:
            raise AppException(status_code=400, message="请先勾选培训教材")

        items = self._build_item_dicts(plan)
        item_map = {item["id"]: item for item in items}
        selected = []
        for item_id in item_ids:
            item = item_map.get(item_id)
            if item:
                selected.append(item)
        if not selected:
            raise AppException(status_code=400, message="勾选的培训教材不存在")

        # topic 格式：《教材名》（编号）、《教材名》……
        topic_parts = []
        for item in selected:
            name = item.get("textbook_name") or ""
            code = item.get("textbook_code")
            topic_parts.append(f"《{name}》（{code}）" if code else f"《{name}》")
        topic = "、".join(topic_parts)

        # 解析培训部门：一级部门不在培训部门列表时回退二级部门（质量管理部→QA
        # 等特殊映射）
        from app.modules.hr.training_dept_resolver import resolve_training_department

        resolved_dept = (
            await resolve_training_department(
                self.session, plan.department, plan.sub_department
            )
            or plan.department
        )

        # 构建参训人员名单：发起人 + 额外参训人员
        employee_names = [plan.employee_name]
        employee_dept_map = {plan.employee_name: resolved_dept}
        if additional_trainees:
            for t in additional_trainees:
                name = t.get("name") or ""
                dept = t.get("department") or resolved_dept
                if name and name not in employee_names:
                    employee_names.append(name)
                    employee_dept_map[name] = dept

        # 收集所有受训部门
        trainee_departments = list(
            set(
                [resolved_dept]
                + [
                    t.get("department", resolved_dept)
                    for t in (additional_trainees or [])
                    if t.get("department")
                ]
            )
        )

        session = TrainingSession(
            training_level="部门级",
            plan_year=date.today().year,
            department=resolved_dept,
            trainee_departments=trainee_departments,
            topic=topic,
            employee_names=employee_names,
            employee_dept_map=employee_dept_map,
            checked_content=[
                {"name": (i.get("textbook_name") or ""), "code": i.get("textbook_code")}
                for i in selected
            ],
            created_by=user_id,
            updated_by=user_id,
        )
        self.session.add(session)
        await self.session.flush()
        logger.info(
            "new employee training session created",
            extra={
                "plan_id": str(plan.id),
                "session_id": str(session.id),
                "item_count": len(selected),
                "trainee_count": len(employee_names),
                "module_name": "hr",
            },
        )
        return NewEmployeeTrainingStartResponse(
            session_id=session.id,
            topic=topic,
            employee_names=employee_names,
            employee_dept_map=employee_dept_map,
            department=resolved_dept,
            training_level="部门级",
            plan_year=date.today().year,
        )

    # ─── 统计 ───

    async def get_stats(
        self, dept_alias_set: set[str] | None = None
    ) -> NewEmployeeTrainingStats:
        plans, total = await self.repo.list_plans(
            page=1, page_size=1000, dept_alias_set=dept_alias_set
        )
        stats = NewEmployeeTrainingStats()
        for plan in plans:
            resp = await self._build_response(plan)
            status = resp["status"]
            if status == "已完成":
                stats.completed += 1
            elif status == "逾期":
                stats.overdue += 1
            elif status == "培训中":
                stats.training += 1
            else:
                stats.pending += 1
        return stats

    async def list_available_trainees(
        self,
        department: str | None = None,
        exclude_plan_id: UUID | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> list[dict[str, str]]:
        """获取可一起培训的新员工列表（部门按培训规则解析）。"""
        from app.modules.hr.training_dept_resolver import resolve_training_department

        rows = await self.repo.list_available_trainees(
            department=department,
            exclude_plan_id=exclude_plan_id,
            page=page,
            page_size=page_size,
        )
        result: list[dict[str, str]] = []
        for row in rows:
            resolved = await resolve_training_department(
                self.session, row.get("department"), row.get("sub_department")
            )
            result.append({"name": row["name"], "department": resolved or ""})
        return result
