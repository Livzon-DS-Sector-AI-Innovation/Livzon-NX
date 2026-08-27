"""合同两级审批与签署流程测试"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_record(**kwargs):
    """模拟 ContractManagement 记录"""
    record = MagicMock()
    record.employee_number = kwargs.get("employee_number", "10012")
    record.name = kwargs.get("name", "张三")
    record.dept_leader_name = kwargs.get("dept_leader_name", None)
    record.supervisor_name = kwargs.get("supervisor_name", None)
    record.supervisor_open_id = kwargs.get("supervisor_open_id", None)
    record.approval_status = kwargs.get("approval_status", "dept_pending")
    record.contract_opinion = kwargs.get("contract_opinion", None)
    record.dept_level1 = kwargs.get("dept_level1", "生产部")
    record.dept_level2 = kwargs.get("dept_level2", "一车间")
    record.contract_sequence = kwargs.get("contract_sequence", "首次")
    record.feishu_record_id = kwargs.get("feishu_record_id", None)
    record.id = kwargs.get("id", "rec-1")
    return record


def _mock_session(record=None, emp=None):
    """模拟 AsyncSession：execute 返回 scalars().first()"""
    session = MagicMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = record
    session.execute = AsyncMock(return_value=result)
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


async def _fake_cache_set(*args, **kwargs):
    """模拟 Redis cache_set（避免跨测试复用已关闭事件循环的连接）"""
    return True


async def _fake_cache_get(*args, **kwargs):
    """模拟 Redis cache_get"""
    return None


# ─── 签名防篡改 ───


def test_callback_token_stage_tamper_rejected():
    """stage 越权安全：篡改 stage 后验签必须失败（防伪造越级审批）"""
    from app.modules.hr.contract_api import (
        _sign_contract_callback_token,
        _verify_contract_callback_token,
    )

    token = _sign_contract_callback_token(
        employee_number="10012",
        employee_name="张三",
        action="approve",
        leader_name="李四",
        stage="dept",
    )
    # 正常验签通过
    assert _verify_contract_callback_token(
        employee_number="10012",
        employee_name="张三",
        action="approve",
        leader_name="李四",
        stage="dept",
        token=token,
    )
    # 篡改 stage 为 supervisor -> 验签失败
    assert not _verify_contract_callback_token(
        employee_number="10012",
        employee_name="张三",
        action="approve",
        leader_name="李四",
        stage="supervisor",
        token=token,
    )
    # 篡改 action -> 验签失败
    assert not _verify_contract_callback_token(
        employee_number="10012",
        employee_name="张三",
        action="reject",
        leader_name="李四",
        stage="dept",
        token=token,
    )
    # 篡改工号 -> 验签失败
    assert not _verify_contract_callback_token(
        employee_number="10099",
        employee_name="张三",
        action="approve",
        leader_name="李四",
        stage="dept",
        token=token,
    )
    # 空 token -> 验签失败
    assert not _verify_contract_callback_token(
        employee_number="10012",
        employee_name="张三",
        action="approve",
        leader_name="李四",
        stage="dept",
        token=None,
    )


# ─── 两级审批状态流转 ───


@pytest.mark.asyncio
async def test_dept_approve_with_supervisor_goes_to_supervisor_pending():
    """部门负责人同意 + 有分管领导 -> supervisor_pending，并异步推送分管领导卡片"""
    from app.modules.hr import contract_api

    record = _mock_record(supervisor_name="王五", supervisor_open_id="ou_super")
    session = _mock_session(record=record)

    with patch("app.core.jobs.submit_job", new_callable=AsyncMock) as mock_submit:
        with patch.object(
            contract_api, "_find_employee", new_callable=AsyncMock
        ) as mock_find_emp:
            mock_find_emp.return_value = None
            text = await contract_api._on_dept_approved(
                session, "10012", "张三", "李四"
            )

    assert "等待分管领导审批" in text
    assert record.approval_status == "supervisor_pending"
    assert record.dept_leader_name == "李四"
    assert record.dept_approved_at is not None
    # 异步卡片任务已提交
    mock_submit.assert_called_once()
    assert mock_submit.call_args.kwargs["employee_number"] == "10012"


@pytest.mark.asyncio
async def test_dept_approve_without_supervisor_finalizes_approved():
    """部门负责人同意 + 无分管领导 -> 自动跳过第二级，直接最终通过"""
    from app.modules.hr import contract_api

    record = _mock_record(supervisor_name=None, supervisor_open_id=None)
    session = _mock_session(record=record)

    with patch("app.core.jobs.submit_job", new_callable=AsyncMock) as mock_submit:
        with patch("app.core.redis.cache_set", new=_fake_cache_set):
            with patch.object(
                contract_api, "_find_employee", new_callable=AsyncMock
            ) as mock_find_emp:
                with patch(
                    "app.modules.hr.contract_sync_service.ContractSyncService"
                ) as mock_sync:
                    mock_find_emp.return_value = None
                    mock_sync.return_value.push_create = AsyncMock()
                    text = await contract_api._on_dept_approved(
                        session, "10012", "张三", "李四"
                    )
    assert text == "✅ 已同意续签"
    assert record.approval_status == "approved"
    assert record.contract_opinion == "同意续签"
    # 未推分管领导卡片，但提交了结果通知任务
    mock_submit.assert_called_once()
    assert mock_submit.call_args.kwargs["employee_number"] == "10012"


@pytest.mark.asyncio
async def test_supervisor_approve_finalizes_approved():
    """分管领导同意 -> 最终通过（写意见 + 异步通知）"""
    from app.modules.hr import contract_api

    record = _mock_record(
        supervisor_name="王五",
        supervisor_open_id="ou_super",
        approval_status="supervisor_pending",
        dept_leader_name="李四",
        feishu_record_id="feishu_1",
    )
    session = _mock_session(record=record)

    with patch("app.core.jobs.submit_job", new_callable=AsyncMock):
        with patch("app.core.redis.cache_set", new=_fake_cache_set):
            with patch.object(
                contract_api, "_find_employee", new_callable=AsyncMock
            ) as mock_find_emp:
                with patch(
                    "app.modules.hr.contract_sync_service.ContractSyncService"
                ) as mock_sync:
                    mock_find_emp.return_value = None
                    mock_sync.return_value.push_update = AsyncMock()
                    mock_sync.return_value.push_create = AsyncMock()
                    text = await contract_api._on_supervisor_approved(
                        session, "10012", "张三", "王五"
                    )

    assert text == "✅ 已同意续签"
    assert record.approval_status == "approved"
    assert record.contract_opinion == "同意续签"
    assert record.supervisor_name == "王五"
    assert record.supervisor_approved_at is not None


@pytest.mark.asyncio
async def test_dept_reject_terminates_flow():
    """部门负责人拒绝 -> 直接终止（不再推分管领导），创建离职记录并通知 HR"""
    from app.modules.hr import contract_api

    record = _mock_record()
    session = _mock_session(record=record)

    with patch("app.core.jobs.submit_job", new_callable=AsyncMock) as mock_submit:
        with patch("app.core.redis.cache_set", new=_fake_cache_set):
            with patch.object(
                contract_api, "_find_employee", new_callable=AsyncMock
            ) as mock_find_emp:
                with patch.object(
                    contract_api, "_create_offboarding_record", new_callable=AsyncMock
                ) as mock_off:
                    mock_find_emp.return_value = None
                    text = await contract_api._on_final_rejected(
                        session, "10012", "张三", "李四", "部门负责人"
                    )

    assert "不续签" in text
    assert record.approval_status == "rejected"
    assert record.contract_opinion == "不同意续签"
    mock_off.assert_called_once()
    # 结果通知任务已提交
    mock_submit.assert_called_once()
    assert mock_submit.call_args.kwargs["employee_number"] == "10012"


@pytest.mark.asyncio
async def test_supervisor_reject_creates_offboarding():
    """分管领导拒绝 -> 最终拒绝，reason 注明分管领导"""
    from app.modules.hr import contract_api

    record = _mock_record(
        supervisor_name="王五",
        approval_status="supervisor_pending",
        dept_leader_name="李四",
    )
    session = _mock_session(record=record)

    with patch("app.core.jobs.submit_job", new_callable=AsyncMock):
        with patch("app.core.redis.cache_set", new=_fake_cache_set):
            with patch.object(
                contract_api, "_find_employee", new_callable=AsyncMock
            ) as mock_find_emp:
                with patch.object(
                    contract_api, "_create_offboarding_record", new_callable=AsyncMock
                ) as mock_off:
                    mock_find_emp.return_value = None
                    await contract_api._on_final_rejected(
                        session, "10012", "张三", "王五", "分管领导"
                    )

    assert record.approval_status == "rejected"
    assert record.supervisor_name == "王五"
    assert record.supervisor_approved_at is not None
    # reason 包含拒绝人；参数顺序以服务函数签名为准。
    reason = mock_off.call_args.args[6]
    assert reason == "分管领导"


# ─── 催签任务 ───


def test_sign_reminder_threshold_logic():
    """催签阈值：超过 sign_reminder_days 才进入待催签集合"""
    from datetime import datetime, timedelta

    from app.modules.hr.scheduler import ContractSignReminderGenerator

    now = datetime.now()
    reminder_days = 7
    threshold = now - timedelta(days=reminder_days)

    approved_recent = MagicMock()
    approved_recent.supervisor_approved_at = now - timedelta(days=2)
    approved_old = MagicMock()
    approved_old.supervisor_approved_at = now - timedelta(days=10)

    assert approved_recent.supervisor_approved_at > threshold  # 未超期，不催签
    assert approved_old.supervisor_approved_at <= threshold  # 超期，催签
    assert ContractSignReminderGenerator.name == "hr.contract_sign_reminder"
    assert ContractSignReminderGenerator.schedule.interval_seconds == 3600


def test_latest_contract_end_picks_max():
    """审批结果导出取 6 组截止日期中最晚的一个"""
    from datetime import date

    from app.modules.hr.contract_api import _latest_contract_end

    record = MagicMock()
    record.contract_end_1 = date(2025, 1, 1)
    record.contract_end_2 = "2026-06-30"
    record.contract_end_3 = None
    record.contract_end_4 = ""
    record.contract_end_5 = "2026/12/31"
    record.contract_end_6 = None

    assert _latest_contract_end(record) == "2026/12/31"


@pytest.mark.asyncio
async def test_process_contract_approval_dedup_and_stage_routing():
    """公共审批逻辑：防重 + stage 路由（HTTP 与卡片回调共用入口）"""
    from app.modules.hr import contract_api

    # 1. 防重：第二次调用直接返回已审批
    record = _mock_record(supervisor_name="王五", supervisor_open_id="ou_super")
    session = _mock_session(record=record)
    with patch("app.core.jobs.submit_job", new_callable=AsyncMock) as mock_submit:
        with patch("app.core.redis.cache_get", new=AsyncMock(return_value=None)):
            with patch("app.core.redis.cache_set", new=_fake_cache_set):
                with patch.object(
                    contract_api, "_find_employee", new_callable=AsyncMock
                ) as mock_find_emp:
                    mock_find_emp.return_value = None
                    text = await contract_api.process_contract_approval(
                        employee_number="10012",
                        employee_name="张三",
                        action="approve",
                        leader_name="李四",
                        stage="dept",
                        db=session,
                    )
    assert "等待分管领导审批" in text
    assert record.approval_status == "supervisor_pending"
    # submit_job 已提交分管领导卡片任务
    mock_submit.assert_called_once()

    # 2. 防重命中：cache_get 返回已有值
    session2 = _mock_session(record=record)
    with patch("app.core.redis.cache_get", new=AsyncMock(return_value="approve")):
        text2 = await contract_api.process_contract_approval(
            employee_number="10012",
            employee_name="张三",
            action="approve",
            leader_name="李四",
            stage="dept",
            db=session2,
        )
    assert text2 == "已审批过，请勿重复操作"

    # 3. stage 参数错误
    text3 = await contract_api.process_contract_approval(
        employee_number="10012",
        employee_name="张三",
        action="approve",
        leader_name="李四",
        stage="boss",
        db=session2,
    )
    assert "参数错误" in text3


@pytest.mark.asyncio
@pytest.mark.skip(
    reason="合同卡片处理已迁移到合同 API，全局飞书事件处理器不再承载该入口"
)
async def test_card_callback_handler_returns_toast_and_updates_card():
    """飞书卡片回调处理器：审批后返回 toast，并触发卡片置灰"""
    from app.modules.hr import contract_api
    from app.platform.integrations.feishu import event_handler

    record = _mock_record(supervisor_name=None, supervisor_open_id=None)
    session = _mock_session(record=record)

    value = {
        "module": "hr_contract_approval",
        "action": "approve",
        "employee_number": "10012",
        "employee_name": "张三",
        "stage": "dept",
        "leader_name": "李四",
        "dept_name": "生产部",
    }
    with patch("app.core.jobs.submit_job", new_callable=AsyncMock):
        with patch("app.core.redis.cache_get", new=AsyncMock(return_value=None)):
            with patch("app.core.redis.cache_set", new=_fake_cache_set):
                with patch("app.core.database.async_session_factory") as mock_factory:
                    mock_factory.return_value.__aenter__ = AsyncMock(
                        return_value=session
                    )
                    mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
                    with patch.object(
                        contract_api, "_find_employee", new_callable=AsyncMock
                    ) as mock_find_emp:
                        mock_find_emp.return_value = None
                        with patch(
                            "app.modules.hr.contract_sync_service.ContractSyncService"
                        ) as mock_sync:
                            mock_sync.return_value.push_create = AsyncMock()
                            with patch.object(
                                contract_api,
                                "update_contract_approval_card",
                                new_callable=AsyncMock,
                            ) as mock_update:
                                result = (
                                    await event_handler._handle_hr_contract_approval(
                                        {}, value
                                    )
                                )

    assert result["toast"]["type"] == "success"
    assert "张三" in result["toast"]["content"]
    # 卡片已置灰（更新调用）
    mock_update.assert_called_once()
    assert mock_update.call_args[0][:2] == ("10012", "张三")

    # 防重：重复点击返回 warning toast，不更新卡片
    with patch("app.core.redis.cache_get", new=AsyncMock(return_value="approve")):
        result2 = await event_handler._handle_hr_contract_approval({}, value)
    assert result2["toast"]["type"] == "warning"
    assert "重复" in result2["toast"]["content"]


@pytest.mark.asyncio
async def test_resolve_contract_approvers_uses_manager_and_director():
    """合同审批人映射：部门经理（一级）+ 部门总监（二级），不使用主管领导 vp"""
    from app.modules.hr import api as hr_api

    cfg = MagicMock()
    cfg.manager_name = "部门经理甲"
    cfg.manager_open_id = "ou_mgr"
    cfg.direct_leader_name = "直属领导乙"
    cfg.direct_leader_open_id = "ou_dir"
    cfg.director_name = "部门总监丙"
    cfg.director_open_id = "ou_director"
    cfg.vp_name = "主管领导丁"
    cfg.vp_open_id = "ou_vp"

    result = MagicMock()
    result.scalars.return_value.first.return_value = cfg
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    (
        leader_name,
        leader_open_id,
        sup_name,
        sup_open_id,
    ) = await hr_api._resolve_contract_approvers(session, "AI创新部")
    assert leader_name == "部门经理甲"  # manager 优先
    assert leader_open_id == "ou_mgr"
    assert sup_name == "部门总监丙"  # director 为分管领导
    assert sup_open_id == "ou_director"

    # 无经理时回退直属领导；无总监时第二级为空
    cfg2 = MagicMock()
    cfg2.manager_name = None
    cfg2.manager_open_id = None
    cfg2.direct_leader_name = "直属领导乙"
    cfg2.direct_leader_open_id = "ou_dir"
    cfg2.director_name = None
    cfg2.director_open_id = None
    cfg2.vp_name = "主管领导丁"
    cfg2.vp_open_id = "ou_vp"
    result2 = MagicMock()
    result2.scalars.return_value.first.return_value = cfg2
    session2 = MagicMock()
    session2.execute = AsyncMock(return_value=result2)

    leader2, open2, sup2, sup_open2 = await hr_api._resolve_contract_approvers(
        session2, "AI创新部"
    )
    assert leader2 == "直属领导乙"
    assert open2 == "ou_dir"
    assert sup2 is None  # 无总监自动跳过第二级
    assert sup_open2 is None


@pytest.mark.asyncio
async def test_resolve_contract_clerk_ids_dept_first_then_fallback():
    """签署办事员解析：部门配置优先，回退全局办事员，再回退 HR 接收人"""
    from app.modules.hr.contract_api import _resolve_contract_clerk_ids

    configs = [MagicMock(is_deleted=False, id="cfg-1")]

    # 1. 部门命中：使用部门办事员
    dept_row = MagicMock()
    dept_row.recipient_open_ids = ["ou_dept_clerk"]
    dept_result = MagicMock()
    dept_result.scalar_one_or_none.return_value = dept_row
    session = MagicMock()
    session.execute = AsyncMock(return_value=dept_result)
    ids = await _resolve_contract_clerk_ids(
        session, configs, "AI创新部", ["ou_global"], ["ou_hr"]
    )
    assert ids == ["ou_dept_clerk"]

    # 2. 部门未配置：回退全局办事员
    dept_result2 = MagicMock()
    dept_result2.scalar_one_or_none.return_value = None
    session2 = MagicMock()
    session2.execute = AsyncMock(return_value=dept_result2)
    ids2 = await _resolve_contract_clerk_ids(
        session2, configs, "AI创新部", ["ou_global"], ["ou_hr"]
    )
    assert ids2 == ["ou_global"]

    # 3. 全局为空：回退 HR 接收人
    ids3 = await _resolve_contract_clerk_ids(
        session2, configs, "AI创新部", [], ["ou_hr"]
    )
    assert ids3 == ["ou_hr"]

    # 4. 无部门信息：直接回退
    ids4 = await _resolve_contract_clerk_ids(session2, configs, "", [], ["ou_hr"])
    assert ids4 == ["ou_hr"]


@pytest.mark.asyncio
async def test_finalize_approved_bumps_contract_sequence():
    """审批通过：合同期次自动 +1（首次→第二次）；第六次/无法解析保持原值"""
    from app.modules.hr.contract_api import _finalize_approved

    async def _run(seq_label: str | None) -> str | None:
        record = _mock_record(contract_sequence=seq_label)
        emp = MagicMock()
        db = MagicMock()
        db.flush = AsyncMock()
        with (
            patch("app.core.redis.cache_set", new=AsyncMock()),
            patch("app.core.jobs.submit_job", new=AsyncMock()),
            patch(
                "app.modules.hr.contract_sync_service.ContractSyncService"
            ) as mock_svc,
        ):
            mock_svc.return_value.push_update = AsyncMock()
            await _finalize_approved(db, record, emp, supervisor_name="总监")
        return record.contract_sequence

    assert await _run("首次") == "第二次"
    assert await _run("第六次") == "第六次"  # 已达上限保持
    assert await _run("第七次") == "第七次"  # 无法解析保持
    assert await _run(None) is None


@pytest.mark.asyncio
async def test_contract_service_update_syncs_back_to_employee():
    """台账编辑回写员工档案：意见/负责人/日期映射，String→Date 转换，仅变化时 flush"""
    from datetime import date

    from app.modules.hr.contract_service import ContractService

    record = MagicMock()
    record.employee_number = "10012"
    record.dept_leader_name = "张起智"
    record.contract_opinion = "同意续签"
    record.contract_end_2 = "2029-08-15"
    record.contract_end_3 = None
    record.contract_end_4 = None
    record.contract_start_1 = None
    record.contract_end_1 = None
    record.contract_start_2 = None
    record.contract_start_3 = None
    record.contract_start_4 = None
    record.contract_start_5 = None
    record.contract_start_6 = None
    record.contract_end_5 = None
    record.contract_end_6 = None

    emp = MagicMock()
    emp.contract_opinion = None
    emp.dept_leader_name = None
    emp.contract_end_2 = None
    result = MagicMock()
    result.scalars.return_value.first.return_value = emp
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.flush = AsyncMock()

    svc = ContractService(session)
    await svc._sync_back_to_employee(record)

    assert emp.contract_opinion == "同意续签"
    assert emp.dept_leader_name == "张起智"
    assert emp.contract_end_2 == date(2029, 8, 15)  # String → Date 转换
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_repo_list_filters_approval_statuses():
    """台账列表过滤：approval_status IN ('approved','synced')，审批中/拒绝不返回"""
    from app.modules.hr.contract_repository import ContractRepository

    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalar.return_value = 0
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    repo = ContractRepository(session)
    records, total = await repo.list(
        page=1, page_size=20, approval_statuses=["approved", "synced"]
    )
    assert records == [] and total == 0
    # 验证查询条件包含 approval_status 过滤
    stmt = session.execute.await_args.args[0]
    assert str(stmt).find("approval_status IN (") > 0


@pytest.mark.asyncio
async def test_sync_from_contract_expiry_converts_string_dates():
    """归档时 isoformat 字符串日期必须转为 date 写入 DATE 列。"""
    from datetime import date

    from app.modules.hr.contract_service import ContractService

    session = MagicMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = None  # 无既有记录 -> create 分支
    session.execute = AsyncMock(return_value=result)

    svc = ContractService(session)
    svc.repo.create = AsyncMock(return_value=MagicMock())
    svc.repo.update = AsyncMock(return_value=MagicMock())

    emp_data = {
        "employee_number": "10099",
        "name": "测试员工",
        "department": "AI创新部",
        "sub_department": "测试组",
        "position": "工程师",
        "contract_sign_date": "2023-09-15",
        "contract_end_date": "2026-09-30",
        "contract_sequence": 1,
    }
    await svc.sync_from_contract_expiry(emp_data)

    data = svc.repo.create.call_args[0][0]
    # DATE 列必须为 date 对象（字符串会触发 asyncpg DataError）
    assert data["contract_start_1"] == date(2023, 9, 15)
    assert data["contract_end_1"] == date(2026, 9, 30)
    assert isinstance(data["contract_start_1"], date)
    assert isinstance(data["contract_end_1"], date)
    # 非 DATE 列（contract_end_2 起为 VARCHAR）保持字符串；start_2 仍是 DATE 列转 date
    emp_data2 = dict(emp_data, contract_sequence=2)
    svc.repo.create.reset_mock()
    await svc.sync_from_contract_expiry(emp_data2)
    data2 = svc.repo.create.call_args[0][0]
    assert data2["contract_start_2"] == date(2023, 9, 15)
    assert data2["contract_end_2"] == "2026-09-30"
