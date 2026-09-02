"""HR通用提醒配置 + 审批流程配置 API"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import case, delete, func, or_, select, text
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.response import success_response
from app.core.upload_security import read_upload_secure
from app.modules.hr.contract_settings_schemas import (
    ApprovalConfigResponse,
    ApprovalConfigUpdate,
    DeptRecipientCreate,
    DeptRecipientResponse,
    ReminderConfigResponse,
    ReminderConfigUpdate,
)
from app.modules.hr.contract_settings_service import ContractSettingsService
from app.modules.hr.feishu.contact import FeishuContact
from app.modules.hr.models import HrDepartment, HrFeishuMember

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hr-settings", tags=["人事-设置中心"])

# 离职证明模板保存路径
OFFBOARDING_TEMPLATE_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "templates"
    / "offboarding"
    / "解除劳动合同单.docx"
)


def _require_user(current_user: CurrentUser) -> None:
    """规范合规：所有业务API默认需要登录"""
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")


async def get_service(db: AsyncSession = Depends(get_db)) -> ContractSettingsService:
    return ContractSettingsService(db)


@router.get("/reminders", summary="获取所有提醒配置（按模块分组）")
async def list_reminder_configs(
    current_user: CurrentUser = None,
    service: ContractSettingsService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    # 确保离职管理默认配置存在
    await service.ensure_default_offboarding_config()
    configs = await service.list_reminder_configs()
    return success_response(
        data=[ReminderConfigResponse.model_validate(c) for c in configs]
    )


@router.put("/reminders/{config_id}", summary="保存提醒配置")
async def update_reminder_config(
    config_id: UUID,
    data: ReminderConfigUpdate,
    current_user: CurrentUser = None,
    service: ContractSettingsService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    config = await service.update_reminder_config(
        config_id, data.model_dump(exclude_unset=True)
    )
    return success_response(data=ReminderConfigResponse.model_validate(config))


@router.get("/approvals", summary="获取所有审批流程配置（按模块分组）")
async def list_approval_configs(
    current_user: CurrentUser = None,
    service: ContractSettingsService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    configs = await service.list_approval_configs()
    return success_response(
        data=[ApprovalConfigResponse.model_validate(c) for c in configs]
    )


@router.put("/approvals/{config_id}", summary="保存审批流程配置")
async def update_approval_config(
    config_id: UUID,
    data: ApprovalConfigUpdate,
    current_user: CurrentUser = None,
    service: ContractSettingsService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    config = await service.update_approval_config(
        config_id, data.model_dump(exclude_unset=True)
    )
    return success_response(data=ApprovalConfigResponse.model_validate(config))


@router.get(
    "/reminders/{config_id}/dept-recipients", summary="获取某提醒项的所有部门接收人配置"
)
async def list_dept_recipients(
    config_id: UUID,
    current_user: CurrentUser = None,
    service: ContractSettingsService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    recipients = await service.list_dept_recipients(str(config_id))
    return success_response(
        data=[DeptRecipientResponse.model_validate(r) for r in recipients]
    )


@router.put("/reminders/{config_id}/dept-recipients", summary="批量保存部门接收人配置")
async def batch_save_dept_recipients(
    config_id: UUID,
    items: list[DeptRecipientCreate],
    current_user: CurrentUser = None,
    service: ContractSettingsService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    results = []
    for item in items:
        data = item.model_dump()
        data["reminder_config_id"] = str(config_id)
        result = await service.upsert_dept_recipient(data)
        results.append(DeptRecipientResponse.model_validate(result))
    return success_response(data=results)


@router.delete("/dept-recipients/{dept_recipient_id}", summary="删除单个部门接收人配置")
async def delete_dept_recipient(
    dept_recipient_id: UUID,
    current_user: CurrentUser = None,
    service: ContractSettingsService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    await service.delete_dept_recipient(dept_recipient_id)
    return success_response(data=None)


@router.post("/hr-members/sync", summary="同步飞书联系人（后台任务）")
async def sync_hr_members(
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    from app.core.database import async_session_factory
    from app.core.jobs import is_job_running, submit_job

    task_id = "hr:sync:feishu-members"

    # 检查是否已有同步任务在运行（心跳过期的孤儿状态允许重新提交）
    if await is_job_running(task_id):
        return success_response(
            data={"task_id": task_id, "state": "running"},
            message="同步任务正在执行中",
        )

    async def _do_sync() -> Any:
        async with async_session_factory() as session:
            await _sync_feishu_members(session)
            await session.commit()
            return {"synced": True}

    await submit_job(_do_sync, task_id=task_id, ttl=600)
    return success_response(
        data={"task_id": task_id, "state": "running"}, message="同步任务已启动"
    )


@router.get("/hr-members/sync-status", summary="查询飞书联系人同步状态")
async def get_members_sync_status(
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    from app.core.jobs import get_job_status

    status = await get_job_status("hr:sync:feishu-members")
    if not status:
        return success_response(
            data={"state": "idle", "progress": "无同步任务", "result": None}
        )
    return success_response(data=status)


@router.get("/hr-members", summary="获取飞书人员列表（用于下拉选择接收人）")
async def list_hr_members(
    refresh: bool = Query(False, description="强制刷新缓存，从飞书重新拉取"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    from app.modules.hr.api import _resolve_visible_scope

    alias_set = await _resolve_visible_scope(db, current_user)
    dept_scope = None
    if alias_set is not None:
        # 部门级数据隔离：非管理员仅返回可见部门成员
        dept_scope = HrFeishuMember.department.in_(alias_set)
    # 1. 始终先返回数据库缓存（即使过期），避免阻塞页面加载
    cached_result = await db.execute(
        select(HrFeishuMember)
        .where(HrFeishuMember.is_deleted.is_(False))
        .where(dept_scope)
        if dept_scope is not None
        else select(HrFeishuMember).where(HrFeishuMember.is_deleted.is_(False))
    )
    cached_members = cached_result.scalars().all()
    if cached_members:
        cached_data = [
            {"name": m.name, "open_id": m.open_id, "department": m.department}
            for m in cached_members
        ]
        # 2. 如果缓存未过期或不是强制刷新，直接返回
        synced_times = [m.synced_at for m in cached_members if m.synced_at]
        if synced_times:
            latest_sync = max(synced_times)
            now = datetime.now(UTC)
            if latest_sync.tzinfo is None:
                latest_sync = latest_sync.replace(tzinfo=UTC)
            if not refresh and now - latest_sync < timedelta(hours=24):
                return success_response(data=cached_data)
        # 3. 缓存过期时，后台异步同步（不阻塞响应）
        import asyncio

        asyncio.create_task(_sync_feishu_members_background(db))
        return success_response(data=cached_data)

    # 4. 空表时同步拉取
    if refresh or not cached_members:
        try:
            await _sync_feishu_members(db)
        except Exception:
            logger.exception("飞书联系人同步失败")

    final_stmt = select(HrFeishuMember).where(HrFeishuMember.is_deleted.is_(False))
    if dept_scope is not None:
        final_stmt = final_stmt.where(dept_scope)
    final_result = await db.execute(final_stmt)
    members = final_result.scalars().all()
    return success_response(
        data=[
            {"name": m.name, "open_id": m.open_id, "department": m.department}
            for m in members
        ]
    )


# 仅这些部门把下级单位（组/队等）归组到部门级展示，其他部门保持原样展示
ROLLUP_DEPARTMENTS = {"行政部", "仓储部"}


async def _department_display_map(
    db: AsyncSession,
) -> tuple[dict[str, str], dict[str, int]]:
    """返回 (部门名→展示部门名, 部门名→排序值)。

    仅对 ROLLUP_DEPARTMENTS 中的部门，把其下级单位（组/队等）上卷到该部门展示；
    其他部门保持自身名称。排序值取展示部门在部门表中的最小 sort_order，未配置时为 9999。
    """
    result = await db.execute(
        select(HrDepartment).where(HrDepartment.is_deleted.is_(False))
    )
    depts = result.scalars().all()
    by_id = {d.id: d for d in depts}
    sort_by_name: dict[str, int] = {}
    for d in depts:
        current = sort_by_name.get(d.name, 9999)
        sort_by_name[d.name] = min(current, d.sort_order or 9999)

    display: dict[str, str] = {}
    for d in depts:
        target_name = d.name
        cur: HrDepartment | None = d
        while cur is not None:
            if cur.name in ROLLUP_DEPARTMENTS:
                target_name = cur.name
                break
            cur = by_id.get(cur.parent_id) if cur.parent_id else None
        display.setdefault(d.name, target_name)
    return display, sort_by_name


async def _resolve_ningxia_root_dept_id(db: AsyncSession) -> str:
    """确定宁夏丽珠根部门的飞书 open_department_id。

    优先用配置 HR_FEISHU_MEMBER_ROOT_DEPT_ID；
    回退取 hr_departments 根部门（parent_id 为空）的 feishu_open_department_id；
    最终兆底返回 "0"。
    """
    settings = get_settings()
    if settings.HR_FEISHU_MEMBER_ROOT_DEPT_ID:
        return settings.HR_FEISHU_MEMBER_ROOT_DEPT_ID
    result = await db.execute(
        select(HrDepartment)
        .where(HrDepartment.parent_id.is_(None), HrDepartment.is_deleted.is_(False))
        .limit(1)
    )
    root = result.scalar_one_or_none()
    if root and root.feishu_open_department_id:
        return root.feishu_open_department_id
    return "0"


async def _resolve_extra_root_dept_ids(
    db: AsyncSession, contact: FeishuContact, main_root: str
) -> list[str]:
    """解析额外同步根部门（如冻结用户部门）。

    优先用配置 HR_FEISHU_MEMBER_EXTRA_ROOT_DEPT_IDS（逗号分隔）；
    回退自动发现：列出根 "0" 的直接子部门，取名称含「冻结」的部门。
    """
    settings = get_settings()
    if settings.HR_FEISHU_MEMBER_EXTRA_ROOT_DEPT_IDS:
        return [
            x.strip()
            for x in settings.HR_FEISHU_MEMBER_EXTRA_ROOT_DEPT_IDS.split(",")
            if x.strip()
        ]
    ids: list[str] = []
    try:
        for child in await contact.get_department_children("0"):
            name = child.get("name", "")
            cid = child.get("open_department_id", "")
            if cid and cid != main_root and "冻结" in name:
                ids.append(cid)
    except Exception:
        logger.exception("自动发现冻结部门失败")
    return ids


async def _sync_feishu_members(db: AsyncSession) -> None:
    """从飞书通讯录同步成员数据到本地数据库（宁夏丽珠子树 + 冻结用户部门）。

    从宁夏丽珠根部门及冻结用户部门广度优先遍历其子部门，不拉取整个集团，
    避免越南子公司/外地办事处等非宁夏人员混入，同时纳入冻结/暂停使用员工。
    任一部门成员拉取失败时抛异常并放弃本次全表重写，保留现有数据，
    避免失败部门的成员被静默清除。
    """
    from app.modules.hr.feishu_settings_service import get_hr_feishu_app_credentials

    app_id, app_secret = await get_hr_feishu_app_credentials(db)
    contact = FeishuContact(app_id=app_id, app_secret=app_secret)
    root_id = await _resolve_ningxia_root_dept_id(db)
    extra_roots = await _resolve_extra_root_dept_ids(db, contact, root_id)
    roots = [root_id] + [r for r in extra_roots if r and r != root_id]
    logger.info("[FeishuMemberSync] 同步根部门: %s", roots)

    departments: list[tuple[dict[str, Any], bool]] = []  # (dept, is_extra)
    seen_dept_ids: set[str] = set()
    for rid in roots:
        is_extra = rid != root_id
        for d in await contact.get_all_departments(rid):
            did = d.get("open_department_id", "")
            if did and did not in seen_dept_ids:
                seen_dept_ids.add(did)
                departments.append((d, is_extra))

    # 宁夏丽珠工号前缀，用于过滤额外根（冻结）部门中的非宁夏人员
    emp_prefix = get_settings().HR_FEISHU_MEMBER_EMPLOYEE_NO_PREFIX

    # 重写前读取旧表，建立 open_id -> (status, status_changed_at)，用于检测状态变化
    old_status: dict[str, tuple[str | None, datetime | None]] = {}
    existing_rows = await db.execute(select(HrFeishuMember))
    for m in existing_rows.scalars().all():
        old_status.setdefault(m.open_id, (m.status, m.status_changed_at))

    change_now = datetime.now(UTC)
    collected: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []  # 本次由在职转为冻结/离职的成员
    # 一人多部门时每个部门各保留一行（按 open_id+部门 去重），避免人员从兼属部门"消失"
    seen_keys: set[tuple[str, str]] = set()
    failed_depts: list[str] = []
    for dept, is_extra in departments:
        dept_id = dept.get("open_department_id", "")
        dept_name = dept.get("name") or dept_id
        try:
            users = await _fetch_dept_users_with_retry(contact, dept_id)
        except Exception:
            logger.exception("Failed to get users for dept %s", dept_name)
            failed_depts.append(dept_name)
            continue
        for u in users:
            open_id = u.get("open_id", "")
            # 额外根（冻结）部门只保留宁夏工号（前缀匹配），排除其他子公司冻结人员
            if is_extra and emp_prefix:
                emp_no = str(u.get("employee_no") or "")
                if not emp_no.startswith(emp_prefix):
                    continue
            key = (open_id, dept_name)
            if open_id and key not in seen_keys:
                seen_keys.add(key)
                item = _parse_feishu_user(u, dept_name)
                old = old_status.get(open_id)
                new_st = item["status"]
                if old and old[0] == "1" and new_st in ("2", "4"):
                    # 在职 -> 冻结/离职：记录变化时间并触发联动
                    item["status_changed_at"] = change_now
                    transitions.append(item)
                elif old:
                    item["status_changed_at"] = old[1]
                else:
                    item["status_changed_at"] = None
                collected.append(item)

    if failed_depts:
        # 数据不完整时不做全表重写，job 将标记为失败并提示具体部门
        raise AppException(
            status_code=500,
            message=(
                f"以下飞书部门成员拉取失败，已保留现有数据，请稍后重试同步: "
                f"{', '.join(failed_depts)}"
            ),
        )

    if collected:
        # 接口不返回的手机号/性别/邮箱：重写前按 open_id 继承现有值，
        # 防止全表重写把回填过的联系信息清空
        prev_mobile: dict[str, str | None] = {}
        prev_gender: dict[str, str | None] = {}
        prev_email: dict[str, str | None] = {}
        prev_ent_email: dict[str, str | None] = {}
        existing_rows = await db.execute(select(HrFeishuMember))
        for m in existing_rows.scalars().all():
            prev_mobile[m.open_id] = m.mobile
            prev_gender[m.open_id] = m.gender
            prev_email[m.open_id] = m.email
            prev_ent_email[m.open_id] = m.enterprise_email

        await db.execute(delete(HrFeishuMember))
        now = datetime.now(UTC)
        for item in collected:
            oid = item["open_id"]
            db.add(
                HrFeishuMember(
                    open_id=item["open_id"],
                    name=item["name"],
                    department=item["department"],
                    mobile=item["mobile"] or prev_mobile.get(oid),
                    email=item["email"] or prev_email.get(oid),
                    enterprise_email=item["enterprise_email"]
                    or prev_ent_email.get(oid),
                    employee_no=item["employee_no"],
                    job_title=item["job_title"],
                    gender=item["gender"] or prev_gender.get(oid),
                    avatar_url=item["avatar_url"],
                    status=item["status"],
                    status_changed_at=item.get("status_changed_at"),
                    synced_at=now,
                )
            )
        await db.commit()

    # 全表重写成功后，按联系人（排除无工号公用账号）回填部门在职人数。
    # 人事应用的通讯录权限下飞书部门接口不返回 member_count，部门人数
    # 统一以本表真实人员统计为准，与联系人页面口径一致。
    try:
        # 口径：status=1（在职）且有工号（排除公用账号与离职/冻结账号）。
        # 上卷按部门名去重：同名父子部门（如"仓储部"下还有"仓储部"）的
        # 成员在联系人表里是同一个 department 名，去重避免重复计数。
        await db.execute(
            text(
                """
                WITH RECURSIVE subtree AS (
                    SELECT id AS root_id, id AS node_id
                    FROM hr.departments WHERE is_deleted = false
                    UNION ALL
                    SELECT s.root_id, c.id
                    FROM subtree s
                    JOIN hr.departments c ON c.parent_id = s.node_id
                    WHERE c.is_deleted = false
                ),
                name_counts AS (
                    SELECT m.department, count(*) AS cnt
                    FROM hr.hr_feishu_members m
                    WHERE m.is_deleted = false
                      AND m.employee_no IS NOT NULL AND m.employee_no <> ''
                      AND m.status = '1'
                    GROUP BY m.department
                ),
                root_names AS (
                    SELECT DISTINCT s.root_id, n.name
                    FROM subtree s
                    JOIN hr.departments n ON n.id = s.node_id
                )
                UPDATE hr.departments d
                SET current_count = coalesce(ag.cnt, 0)
                FROM (
                    SELECT r.root_id, sum(coalesce(nc.cnt, 0)) AS cnt
                    FROM root_names r
                    LEFT JOIN name_counts nc ON nc.department = r.name
                    GROUP BY r.root_id
                ) ag
                WHERE d.id = ag.root_id
                """
            )
        )
        await db.commit()
    except Exception:
        logger.exception("[FeishuMemberSync] 回填部门在职人数失败")

    # 全表重写成功后，对「在职→冻结/离职」的成员触发自动离职联动（逐个容错）
    for item in transitions:
        try:
            await _auto_offboard(db, item, item.get("status_changed_at"))
        except Exception:
            logger.exception(
                "[FeishuMemberSync] 自动离职联动失败: employee_no=%s",
                item.get("employee_no"),
            )
    if transitions:
        await db.commit()


async def _sync_feishu_members_background(db: AsyncSession) -> None:
    """后台异步同步飞书成员（不阻塞 API 响应）"""
    try:
        await _sync_feishu_members(db)
        logger.info("飞书联系人后台同步完成")
    except Exception:
        logger.exception("飞书联系人后台同步失败")


async def _auto_offboard(
    db: AsyncSession, item: dict[str, Any], change_at: datetime | None
) -> None:
    """检测到「在职→冻结/离职」时自动把员工从员工档案转入离职台账。

    流程：更新员工状态为离职+最后工作日 → 创建离职台账记录（同步飞书离职管理表）
    → 删除飞书员工档案记录 → 软删本地员工档案。逐个容错、幂等。
    """
    from datetime import date as date_type

    from app.modules.hr.repository import EmployeeRepository
    from app.modules.hr.schemas import OffboardingRecordCreate
    from app.modules.hr.service import OffboardingRecordService

    emp_no = str(item.get("employee_no") or "")
    prefix = get_settings().HR_FEISHU_MEMBER_EMPLOYEE_NO_PREFIX
    if not emp_no or (prefix and not emp_no.startswith(prefix)):
        return  # 非宁夏丽珠工号不处理

    emp_repo = EmployeeRepository(db)
    employee = await emp_repo.get_by_employee_number(emp_no)
    if not employee or employee.is_deleted or employee.status == "离职":
        return  # 不存在或已离职，幂等跳过

    change_d = change_at.date() if change_at else date_type.today()

    # 1. 更新员工档案：在职→离职 + 最后工作日
    employee.status = "离职"
    employee.last_working_day = change_d
    await emp_repo.update(employee)

    # 2. 创建离职台账记录（内部同步飞书离职管理表 + 设状态离职）
    svc = OffboardingRecordService(db)
    # 仅「暂停使用/冻结」（status=4）标记为账号冻结；正常离职（status=2）用正常离职原因
    is_frozen = str(item.get("status")) == "4"
    data = OffboardingRecordCreate(
        employee_id=employee.id,
        employee_number=emp_no,
        name=employee.name,
        domain_account=employee.domain_account,
        gender=employee.gender,
        department=employee.department,
        sub_department=employee.sub_department,
        position=employee.position,
        level=employee.level,
        employment_type=employee.employment_type,
        hire_date=employee.hire_date,
        phone=employee.phone,
        email=employee.email,
        offboarding_date=change_d,
        offboarding_type="其他" if is_frozen else "正常离职",
        reason=(
            "飞书账号冻结/暂停使用，自动转离职"
            if is_frozen
            else "飞书账号状态变更离职，自动转离职"
        ),
        status="离职",
    )
    await svc.create_record(data)

    # 3. 删除飞书员工档案多维表格记录（失败不影响本地）
    try:
        from app.modules.hr.feishu.bitable import FeishuBitableSync
        from app.modules.hr.feishu_settings_service import get_hr_feishu_app_credentials

        app_id, app_secret = await get_hr_feishu_app_credentials(db)
        sync = FeishuBitableSync(app_id=app_id or None, app_secret=app_secret or None)
        await sync.sync_employee_deleted(emp_no)
    except Exception:
        logger.exception("[AutoOffboard] 删除飞书员工档案失败: %s", emp_no)

    # 4. 软删本地员工档案
    await emp_repo.soft_delete(employee)
    logger.info("[AutoOffboard] 员工已自动转离职: %s (%s)", employee.name, emp_no)


# 飞书通讯录拉取重试配置：最多 3 次重试，指数退避 (1s, 2s, 4s)
_FEISHU_MEMBER_MAX_RETRIES = 3
_FEISHU_MEMBER_BACKOFF = (1, 2, 4)


async def hr_member_sync_loop() -> None:
    """每 N 小时定期同步飞书联系人（含冻结检测与自动离职联动）。"""
    from app.core.database import async_session_factory

    interval_h = get_settings().HR_FEISHU_MEMBER_SYNC_INTERVAL_HOURS or 12
    logger.info("[FeishuMemberSync] 定期同步任务已启动（每 %s 小时）", interval_h)
    while True:
        try:
            await asyncio.sleep(interval_h * 3600)
            async with async_session_factory() as session:
                await _sync_feishu_members(session)
                await session.commit()
            logger.info("[FeishuMemberSync] 定期同步完成")
        except asyncio.CancelledError:
            logger.info("[FeishuMemberSync] 定期同步任务已取消")
            raise
        except Exception:
            logger.exception("[FeishuMemberSync] 定期同步失败")


async def _fetch_dept_users_with_retry(
    contact: FeishuContact, dept_id: str
) -> list[dict[str, Any]]:
    "调用 FeishuContact.get_department_users，最多 3 次重试，指数退避 (1s, 2s, 4s)。"
    last_error: Exception | None = None
    # 1 次初始调用 + 最多 3 次重试
    for attempt in range(_FEISHU_MEMBER_MAX_RETRIES + 1):
        try:
            return await contact.get_department_users(dept_id)
        except Exception as e:
            last_error = e
            if attempt < _FEISHU_MEMBER_MAX_RETRIES:
                wait = _FEISHU_MEMBER_BACKOFF[attempt]
                logger.warning(
                    "Feishu get_department_users retry %d/%d for dept %s after %ds: %s",
                    attempt + 1,
                    _FEISHU_MEMBER_MAX_RETRIES,
                    dept_id,
                    wait,
                    e,
                )
                await asyncio.sleep(wait)
            else:
                logger.error(
                    "Feishu get_department_users exhausted retries for dept %s: %s",
                    dept_id,
                    e,
                )
    assert last_error is not None
    raise last_error


def _parse_feishu_user(u: dict[str, Any], department: str | None) -> dict[str, Any]:
    """将飞书 /contact/v3/users/find_by_department 返回的 item 解析为数据库字段。

    - gender: 飞书返回 int (1男 2女)，转为字符串 "1"/"2"
    - status: 飞书返回 {"is_activated", "is_frozen", "is_resigned"}，
              转为简化状态 "1"在职 / "2"离职 / "3"未激活 / "4"暂停使用
    - avatar: 取 avatar_240，回退 avatar_origin
    """
    raw_gender = u.get("gender")
    gender = str(raw_gender) if raw_gender in (1, 2) else None

    status_obj = u.get("status") or {}
    if status_obj.get("is_resigned"):
        status = "2"
    elif status_obj.get("is_frozen"):
        status = "4"
    elif not status_obj.get("is_activated"):
        status = "3"
    else:
        status = "1"

    avatar = u.get("avatar") or {}
    avatar_url = avatar.get("avatar_240") or avatar.get("avatar_origin")

    return {
        "name": u.get("name", ""),
        "open_id": u.get("open_id", ""),
        "department": department,
        "mobile": u.get("mobile") or None,
        "email": u.get("email") or None,
        "enterprise_email": u.get("enterprise_email") or None,
        "employee_no": u.get("employee_no") or None,
        "job_title": u.get("job_title") or None,
        "gender": gender,
        "avatar_url": avatar_url,
        "status": status,
    }


@router.get("/feishu-members", summary="获取飞书联系人列表（分页+搜索+筛选）")
async def list_feishu_members(
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    keyword: str | None = Query(None, description="搜索关键词（姓名/部门/工号）"),
    department: str | None = Query(None, description="部门筛选（精确匹配）"),
    status: str | None = Query(
        None, description="状态筛选（1在职/2离职/3未激活/4暂停使用）"
    ),
) -> Any:
    from app.modules.hr.api import _assert_dept_in_scope

    alias_set = await _assert_dept_in_scope(db, current_user, department)

    # 组/队等下级单位上卷到部门级展示
    display_map, sort_by_name = await _department_display_map(db)

    # 构建查询：过滤公用账号（无工号 = 非真实人员）
    query = select(HrFeishuMember).where(
        HrFeishuMember.is_deleted.is_(False),
        HrFeishuMember.employee_no.isnot(None),
    )
    if alias_set is not None:
        # 部门级数据隔离：可见部门别名集合（原始部门名匹配）
        query = query.where(HrFeishuMember.department.in_(alias_set))
    if keyword:
        # 关键词同时匹配原始部门名与上卷后的展示部门名
        kw_raws = [
            raw
            for raw, disp in display_map.items()
            if keyword.lower() in raw.lower() or keyword.lower() in disp.lower()
        ]
        query = query.where(
            or_(
                HrFeishuMember.name.ilike(f"%{keyword}%"),
                HrFeishuMember.department.ilike(f"%{keyword}%"),
                HrFeishuMember.department.in_(kw_raws),
                HrFeishuMember.employee_no.ilike(f"%{keyword}%"),
            )
        )
    if department:
        # 部门筛选按上卷后的展示部门名展开为全部原始部门名
        raw_names = [raw for raw, disp in display_map.items() if disp == department]
        raw_names.append(department)
        query = query.where(HrFeishuMember.department.in_(raw_names))
    if status:
        query = query.where(HrFeishuMember.status == status)

    # 计算总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # 分页查询 - 用 CASE 把原始部门映射为展示部门及其排序值，
    # 不做 join，避免同名部门产生重复行。
    # 部门表为空（如开发环境未同步部门）时映射为空，CASE 无 WHEN 分支
    # 会生成非法 SQL，此时回退按原始部门名排序。
    if display_map:
        display_case = case(
            display_map,
            value=HrFeishuMember.department,
            else_=HrFeishuMember.department,
        )
        sort_case = case(
            {
                raw: sort_by_name.get(disp, 9999)
                for raw, disp in display_map.items()
            },
            value=HrFeishuMember.department,
            else_=9999,
        )
        order_columns = [sort_case.asc(), display_case.asc()]
    else:
        order_columns = [HrFeishuMember.department.asc()]
    result = await db.execute(
        query.order_by(*order_columns, HrFeishuMember.name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    members = result.scalars().all()

    return success_response(
        data=[
            {
                "id": str(m.id),
                "open_id": m.open_id,
                "name": m.name,
                "department": display_map.get(m.department or "", m.department or ""),
                "mobile": m.mobile,
                "email": m.email,
                "enterprise_email": m.enterprise_email,
                "employee_no": m.employee_no,
                "job_title": m.job_title,
                "gender": m.gender,
                "avatar_url": m.avatar_url,
                "status": m.status,
                "status_changed_at": m.status_changed_at.isoformat()
                if m.status_changed_at
                else None,
            }
            for m in members
        ],
        meta={"page": page, "page_size": page_size, "total": total},
    )


@router.get("/feishu-members/departments", summary="获取飞书联系人筛选部门选项")
async def list_feishu_member_departments(
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """返回联系人表中实际存在的部门名（去重），供前端筛选下拉使用。

    与列表端点同源，保证筛选值与存储值一致，避免本地部门表改名导致筛不出人。
    """
    from app.modules.hr.api import _resolve_visible_scope

    alias_set = await _resolve_visible_scope(db, current_user)

    query = (
        select(HrFeishuMember.department)
        .where(
            HrFeishuMember.is_deleted.is_(False),
            HrFeishuMember.department.isnot(None),
            HrFeishuMember.employee_no.isnot(None),
        )
        .distinct()
    )
    result = await db.execute(query)
    raw_names = [row[0] for row in result.all() if row[0]]

    if alias_set is not None:
        # 部门级数据隔离：仅返回可见部门的选项
        raw_names = [n for n in raw_names if n in alias_set]

    # 上卷到部门级展示，去重后按部门排序值排序
    display_map, sort_by_name = await _department_display_map(db)
    display_names = {display_map.get(n, n) for n in raw_names}
    if alias_set is not None:
        display_names = {d for d in display_names if d in alias_set}
    departments = sorted(display_names, key=lambda n: (sort_by_name.get(n, 9999), n))
    return success_response(data=departments)


@router.post("/offboarding-template", summary="上传离职证明模板")
async def upload_offboarding_template(
    file: UploadFile = File(...),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    _, content = await read_upload_secure(
        file,
        max_bytes=get_settings().MAX_UPLOAD_SIZE_MB * 1024 * 1024,
        allowed_extensions={".docx"},
        what="离职证明模板",
    )

    OFFBOARDING_TEMPLATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    OFFBOARDING_TEMPLATE_PATH.write_bytes(content)

    logger.info(
        "离职证明模板已更新: %s, size=%d bytes",
        file.filename,
        len(content),
        extra={"hr_module": "hr"},
    )
    return success_response(
        data={"filename": file.filename, "size": len(content)},
        message="离职证明模板上传成功",
    )


@router.get("/offboarding-template", summary="获取当前离职证明模板信息")
async def get_offboarding_template_info(
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    exists = OFFBOARDING_TEMPLATE_PATH.exists()
    return success_response(
        data={
            "exists": exists,
            "filename": OFFBOARDING_TEMPLATE_PATH.name if exists else None,
            "updated_at": datetime.fromtimestamp(
                OFFBOARDING_TEMPLATE_PATH.stat().st_mtime, tz=UTC
            ).isoformat()
            if exists
            else None,
        }
    )


@router.delete("/reminders-by-entity", summary="按实体代码批量软删除提醒配置")
async def delete_reminders_by_entity(
    entity_codes: str = Query(
        ..., description="逗号分隔的实体代码，如：onboarding,offboarding,recruitment"
    ),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """软删除指定实体的所有提醒配置"""
    _require_user(current_user)
    from sqlalchemy import update

    from app.modules.hr.models import HrReminderConfig, HrReminderDeptRecipient

    codes = [c.strip() for c in entity_codes.split(",") if c.strip()]
    if not codes:
        raise AppException(status_code=400, message="entity_codes 不能为空")

    # 软删除提醒配置
    result = cast(
        CursorResult[Any],
        await db.execute(
            update(HrReminderConfig)
            .where(
                HrReminderConfig.entity_code.in_(codes),
                HrReminderConfig.is_deleted.is_(False),
            )
            .values(is_deleted=True)
        ),
    )

    # 软删除关联的部门接收人配置
    reminder_ids = await db.execute(
        select(HrReminderConfig.id).where(
            HrReminderConfig.entity_code.in_(codes),
            HrReminderConfig.is_deleted.is_(True),
        )
    )
    reminder_id_list = [str(rid) for rid in reminder_ids.scalars().all()]
    if reminder_id_list:
        await db.execute(
            update(HrReminderDeptRecipient)
            .where(HrReminderDeptRecipient.reminder_config_id.in_(reminder_id_list))
            .values(is_deleted=True)
        )

    await db.commit()
    return success_response(
        data={"deleted_count": result.rowcount},
        message=f"已删除 {result.rowcount} 条提醒配置",
    )


@router.delete("/approvals-by-entity", summary="按实体代码批量软删除审批流程配置")
async def delete_approvals_by_entity(
    entity_codes: str = Query(
        ..., description="逗号分隔的实体代码，如：onboarding,offboarding,recruitment"
    ),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """软删除指定实体的所有审批流程配置"""
    _require_user(current_user)
    from sqlalchemy import update

    from app.modules.hr.models import HrApprovalConfig

    codes = [c.strip() for c in entity_codes.split(",") if c.strip()]
    if not codes:
        raise AppException(status_code=400, message="entity_codes 不能为空")

    # 软删除审批配置
    result = cast(
        CursorResult[Any],
        await db.execute(
            update(HrApprovalConfig)
            .where(
                HrApprovalConfig.entity_code.in_(codes),
                HrApprovalConfig.is_deleted.is_(False),
            )
            .values(is_deleted=True)
        ),
    )

    await db.commit()
    return success_response(
        data={"deleted_count": result.rowcount},
        message=f"已删除 {result.rowcount} 条审批配置",
    )
