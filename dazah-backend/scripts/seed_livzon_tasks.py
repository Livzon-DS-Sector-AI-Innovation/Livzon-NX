"""为指定开发用户幂等创建 Livzon Task 演示数据。"""

import argparse
import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.agent.models import (
    AgentAutomation,
    AgentAutomationTrigger,
    AgentAutomationVersion,
    AgentWorkflow,
)
from app.platform.identity.models import User

AUTOMATIONS = (
    ("【测试自动化】质量数据摘要", "汇总质量模块关键记录，生成只读摘要。", "enabled"),
    ("【测试自动化】库存阈值检查", "检查原辅料库存阈值并整理异常项。", "paused"),
    ("【测试自动化】采购进度汇总", "汇总采购申请和合同处理进度。", "draft"),
)

SCHEDULED_TASKS = (
    (
        "【测试定时】工作日质量简报",
        "每个工作日上午生成质量简报。",
        "enabled",
        "0 9 * * 1-5",
    ),
    (
        "【测试定时】每四小时库存巡检",
        "每四小时检查一次原辅料库存。",
        "paused",
        "0 */4 * * *",
    ),
    (
        "【测试定时】周五采购汇总",
        "每周五汇总采购执行进度。",
        "enabled",
        "30 17 * * 5",
    ),
)

WORKFLOWS = (
    (
        "【测试工作流】质量偏差查询",
        "查询最近的质量偏差报告记录。",
        "enabled",
        "quality.list_deviation_report_records",
        ["查询质量偏差", "查看偏差记录"],
    ),
    (
        "【测试工作流】原辅料库存查询",
        "查询原辅料库存并返回分页摘要。",
        "disabled",
        "warehouse.list_raw_materials",
        ["查询原辅料库存", "查看库存"],
    ),
    (
        "【测试工作流】采购申请查询",
        "查询采购申请及当前处理状态。",
        "enabled",
        "procurement.list_purchase_requests",
        ["查询采购申请", "查看采购进度"],
    ),
)


def automation_definition(name: str, description: str) -> dict[Any, Any]:
    return {
        "schema_version": "1.0",
        "name": name,
        "description": description,
        "timezone": "Asia/Shanghai",
        "concurrency_policy": "forbid",
        "missed_trigger_policy": "run_once",
        "steps": [
            {
                "key": "finish",
                "type": "end",
                "status": "succeeded",
                "message": "Livzon Task 测试流程执行完成。",
            }
        ],
    }


async def seed(user_id: uuid.UUID, database_url: str) -> tuple[int, int, int]:
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    created_automations = 0
    created_workflows = 0
    created_scheduled = 0
    try:
        async with session_factory() as db:
            user = await db.get(User, user_id)
            if user is None or user.is_deleted:
                raise ValueError("指定用户不存在或已停用")

            for name, description, status in AUTOMATIONS:
                if await automation_exists(db, user_id, name):
                    continue
                await add_automation(
                    db,
                    user_id=user_id,
                    name=name,
                    description=description,
                    status=status,
                    trigger_type="manual",
                )
                created_automations += 1

            for name, description, status, cron in SCHEDULED_TASKS:
                if await automation_exists(db, user_id, name):
                    continue
                await add_automation(
                    db,
                    user_id=user_id,
                    name=name,
                    description=description,
                    status=status,
                    trigger_type="schedule",
                    cron=cron,
                )
                created_scheduled += 1

            for name, description, status, operation, phrases in WORKFLOWS:
                exists = await db.scalar(
                    select(AgentWorkflow.id).where(
                        AgentWorkflow.user_id == user_id,
                        AgentWorkflow.name == name,
                        AgentWorkflow.is_deleted.is_(False),
                    )
                )
                if exists:
                    continue
                workflow = AgentWorkflow(
                    user_id=user_id,
                    name=name,
                    description=description,
                    status=status,
                    trigger_phrases=phrases,
                    steps=[
                        {
                            "order": 1,
                            "title": description.rstrip("。"),
                            "operation": operation,
                            "params": {"page": 1, "page_size": 5},
                            "body": None,
                            "description": "Livzon Task 测试步骤",
                        }
                    ],
                    source_skill="livzon-workflow-builder",
                    source_request="Livzon Task 页面演示数据",
                    created_by=user_id,
                    updated_by=user_id,
                )
                db.add(workflow)
                created_workflows += 1

            await db.commit()
    finally:
        await engine.dispose()
    return created_automations, created_workflows, created_scheduled


async def automation_exists(db: Any, user_id: uuid.UUID, name: str) -> bool:
    return bool(
        await db.scalar(
            select(AgentAutomation.id).where(
                AgentAutomation.owner_user_id == user_id,
                AgentAutomation.name == name,
                AgentAutomation.is_deleted.is_(False),
            )
        )
    )


async def add_automation(
    db: Any,
    *,
    user_id: uuid.UUID,
    name: str,
    description: str,
    status: str,
    trigger_type: str,
    cron: str | None = None,
) -> None:
    automation = AgentAutomation(
        owner_user_id=user_id,
        name=name,
        description=description,
        scope_type="mine",
        scope_ref={},
        status=status,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(automation)
    await db.flush()

    version = AgentAutomationVersion(
        automation_id=automation.id,
        version=1,
        schema_version="1.0",
        definition=automation_definition(name, description),
        policy_snapshot={"source": "livzon_task_test_seed"},
        capability_versions={},
        change_summary="创建 Livzon Task 测试数据",
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(version)
    await db.flush()
    automation.active_version_id = version.id

    trigger = AgentAutomationTrigger(
        automation_id=automation.id,
        trigger_type=trigger_type,
        status="enabled" if status == "enabled" else "disabled",
        schedule={"cron": cron} if cron else {},
        event_filter={},
        timezone="Asia/Shanghai",
        next_fire_at=(datetime.now(UTC) + timedelta(days=1)) if cron else None,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(trigger)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", required=True, type=uuid.UUID)
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("必须通过 DATABASE_URL 指定开发数据库")
    created = asyncio.run(seed(args.user_id, database_url))
    print(
        "Livzon Task 测试数据完成："
        f"自动化新增 {created[0]}，工作流新增 {created[1]}，定时任务新增 {created[2]}"
    )


if __name__ == "__main__":
    main()
