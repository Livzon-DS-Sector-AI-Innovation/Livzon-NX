"""工作流编排引擎 — 逐步执行，人工确认"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.modules.research.models import PilotWorkflow, PilotWorkflowStep
from app.modules.research.pilot_workflow.step1_param_extraction import (
    execute_param_extraction,
)
from app.modules.research.pilot_workflow.step2_scale_up_calc import (
    execute_scale_up_calc,
)
from app.modules.research.pilot_workflow.step3_ehs_assessment import (
    execute_ehs_assessment,
)
from app.modules.research.pilot_workflow.step4_report_writing import (
    execute_report_writing,
)

logger = logging.getLogger(__name__)

STEP_DEFINITIONS = [
    {
        "step_order": 1,
        "step_code": "param_extraction",
        "step_name": "工艺参数提取与风险初判",
        "executor": execute_param_extraction,
    },
    {
        "step_order": 2,
        "step_code": "scale_up_calc",
        "step_name": "工程计算与放大评估",
        "executor": execute_scale_up_calc,
    },
    {
        "step_order": 3,
        "step_code": "ehs_assessment",
        "step_name": "EHS与工艺安全评估",
        "executor": execute_ehs_assessment,
    },
    {
        "step_order": 4,
        "step_code": "report_writing",
        "step_name": "生产数据分析与报告撰写",
        "executor": execute_report_writing,
    },
]


async def _create_steps(session: AsyncSession, workflow_id: uuid.UUID) -> None:
    """创建工作流的4个步骤记录"""
    for defn in STEP_DEFINITIONS:
        step = PilotWorkflowStep(
            workflow_id=workflow_id,
            step_order=defn["step_order"],
            step_code=defn["step_code"],
            step_name=defn["step_name"],
            status="pending",
        )
        session.add(step)
    await session.flush()


async def _execute_step(
    session: AsyncSession,
    step: PilotWorkflowStep,
    step_defn: dict,
    workflow: PilotWorkflow,
) -> dict:
    """执行单个步骤，返回输出数据"""
    step.status = "running"
    step.started_at = datetime.now(UTC)
    await session.flush()

    try:
        output = await step_defn["executor"](
            step_input=step.input_data or {},
            workflow=workflow,
        )
        step.output_data = output
        step.status = "waiting_approval"
        step.completed_at = datetime.now(UTC)
        await session.flush()
        return output
    except Exception as e:
        logger.exception(f"Step {step.step_code} failed: {e}")
        step.status = "failed"
        step.error_message = str(e)
        step.completed_at = datetime.now(UTC)
        workflow.status = "failed"
        await session.commit()
        raise


async def start_workflow(workflow_id: uuid.UUID) -> None:
    """启动工作流：创建步骤记录，执行第一步后暂停等待确认"""
    async with async_session_factory() as session:
        # 创建步骤记录
        await _create_steps(session, workflow_id)

        # 更新工作流状态为 running
        await session.execute(
            update(PilotWorkflow)
            .where(PilotWorkflow.id == workflow_id)
            .values(status="running")
        )
        await session.flush()

        # 获取工作流和第一个步骤
        result = await session.execute(
            select(PilotWorkflow).where(PilotWorkflow.id == workflow_id)
        )
        workflow = result.scalar_one()

        result = await session.execute(
            select(PilotWorkflowStep)
            .where(
                PilotWorkflowStep.workflow_id == workflow_id,
                PilotWorkflowStep.step_order == 1,
            )
        )
        step = result.scalar_one()
        step.input_data = {}

        # 执行第一步
        try:
            await _execute_step(session, step, STEP_DEFINITIONS[0], workflow)
            # 工作流保持 running 状态，等待人工确认
            await session.commit()
        except Exception:
            await session.rollback()


async def approve_step(workflow_id: uuid.UUID) -> dict:
    """确认当前步骤，异步执行下一步。返回执行结果信息。"""
    import asyncio
    
    async with async_session_factory() as session:
        # 获取工作流
        result = await session.execute(
            select(PilotWorkflow).where(PilotWorkflow.id == workflow_id)
        )
        workflow = result.scalar_one_or_none()
        if not workflow:
            return {"error": "工作流不存在"}

        if workflow.status not in ("running", "waiting_approval"):
            return {"error": f"工作流状态为 {workflow.status}，无法继续"}

        # 获取所有步骤
        result = await session.execute(
            select(PilotWorkflowStep)
            .where(PilotWorkflowStep.workflow_id == workflow_id)
            .order_by(PilotWorkflowStep.step_order)
        )
        steps = list(result.scalars().all())

        # 找到当前等待确认的步骤
        waiting_step = None
        waiting_idx = -1
        for i, s in enumerate(steps):
            if s.status == "waiting_approval":
                waiting_step = s
                waiting_idx = i
                break

        if not waiting_step:
            return {"error": "没有等待确认的步骤"}

        # 标记当前步骤为已完成
        waiting_step.status = "completed"

        # 检查是否还有下一步
        next_idx = waiting_idx + 1
        if next_idx >= len(steps):
            # 所有步骤完成
            workflow.status = "completed"
            workflow.final_report = waiting_step.output_data
            await session.commit()
            return {
                "status": "completed",
                "message": "所有步骤已完成，工作流结束",
            }

        # 准备下一步
        next_step = steps[next_idx]
        next_defn = STEP_DEFINITIONS[next_idx]

        # 累积所有已完成步骤的输出作为下一步的输入
        accumulated_results = {}
        for s in steps[:next_idx]:
            if s.output_data and isinstance(s.output_data, dict):
                step_key = s.step_code
                accumulated_results[step_key] = s.output_data
        next_step.input_data = accumulated_results
        
        # 标记下一步为运行中
        next_step.status = "running"
        next_step.started_at = datetime.now(UTC)
        
        await session.commit()
        
        # 在后台异步执行下一步
        asyncio.create_task(_execute_next_step_async(workflow_id, next_idx))
        
        return {
            "status": "running",
            "step_order": next_step.step_order,
            "step_name": next_step.step_name,
            "message": f"步骤 {waiting_step.step_order} 已确认，步骤 {next_step.step_order} 正在执行",
        }


async def _execute_next_step_async(workflow_id: uuid.UUID, step_idx: int) -> None:
    """异步执行工作流步骤"""
    async with async_session_factory() as session:
        # 获取工作流
        result = await session.execute(
            select(PilotWorkflow).where(PilotWorkflow.id == workflow_id)
        )
        workflow = result.scalar_one()
        
        # 获取步骤
        result = await session.execute(
            select(PilotWorkflowStep)
            .where(PilotWorkflowStep.workflow_id == workflow_id)
            .order_by(PilotWorkflowStep.step_order)
        )
        steps = list(result.scalars().all())
        step = steps[step_idx]
        step_defn = STEP_DEFINITIONS[step_idx]
        
        try:
            await _execute_step(session, step, step_defn, workflow)
            await session.commit()
        except Exception as e:
            logger.exception(f"Step {step.step_code} failed: {e}")
            await session.rollback()
