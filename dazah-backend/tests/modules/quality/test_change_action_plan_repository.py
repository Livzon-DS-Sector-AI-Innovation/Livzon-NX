from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.change_control import ChangeControl
from app.modules.quality.repository.quality_management import (
    create_change_action_plan,
    get_change_action_plans,
    update_change_action_plan,
)


@pytest.fixture(autouse=True)
async def _prepare_change_action_plan_tables(db_session: AsyncSession):
    await db_session.execute(text("CREATE SCHEMA IF NOT EXISTS quality"))
    await db_session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS quality.quality_change_controls (
                serial_number VARCHAR(50),
                change_code VARCHAR(100) NOT NULL UNIQUE,
                applicant_department VARCHAR(100),
                change_object VARCHAR(255),
                change_content TEXT,
                impact_assessment TEXT,
                change_level VARCHAR(50),
                application_date DATE,
                planned_approval_date DATE,
                execution_date DATE,
                closure_date DATE,
                id UUID PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                created_by UUID NULL,
                updated_by UUID NULL,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE
            )
            """
        )
    )
    await db_session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS quality.quality_change_action_plans (
                id UUID PRIMARY KEY,
                change_id UUID NULL,
                change_code VARCHAR(100) NOT NULL,
                project_name VARCHAR(255) NOT NULL,
                related_work TEXT NULL,
                owner_name VARCHAR(100) NULL,
                owner_user_id VARCHAR(100) NULL,
                director_name VARCHAR(100) NULL,
                director_user_id VARCHAR(100) NULL,
                deadline_date DATE NULL,
                status VARCHAR(100) NULL,
                delay_flag VARCHAR(100) NULL,
                delayed_deadline_date DATE NULL,
                feishu_record_id VARCHAR(100) NULL,
                sync_status VARCHAR(20) NOT NULL DEFAULT 'pending',
                sync_error TEXT NULL,
                last_synced_at TIMESTAMPTZ NULL,
                reminder_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                reminder_status VARCHAR(20) NOT NULL DEFAULT 'pending',
                last_reminded_at TIMESTAMPTZ NULL,
                reminder_confirmed_at TIMESTAMPTZ NULL,
                reminder_confirmed_by VARCHAR(100) NULL,
                reminder_message_id VARCHAR(100) NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                created_by UUID NULL,
                updated_by UUID NULL,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE
            )
            """
        )
    )
    await db_session.execute(
        text(
            """
            ALTER TABLE quality.quality_change_action_plans
            ADD COLUMN IF NOT EXISTS reminder_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            ADD COLUMN IF NOT EXISTS reminder_status VARCHAR(20) NOT NULL DEFAULT 'pending',
            ADD COLUMN IF NOT EXISTS last_reminded_at TIMESTAMPTZ NULL,
            ADD COLUMN IF NOT EXISTS reminder_confirmed_at TIMESTAMPTZ NULL,
            ADD COLUMN IF NOT EXISTS reminder_confirmed_by VARCHAR(100) NULL,
            ADD COLUMN IF NOT EXISTS reminder_message_id VARCHAR(100) NULL
            """
        )
    )
    await db_session.execute(text("DELETE FROM quality.quality_change_action_plans"))
    await db_session.execute(text("DELETE FROM quality.quality_change_controls"))
    await db_session.commit()

    yield

    await db_session.execute(text("DELETE FROM quality.quality_change_action_plans"))
    await db_session.execute(text("DELETE FROM quality.quality_change_controls"))
    await db_session.commit()


@pytest.mark.anyio
async def test_change_action_plan_repository_roundtrip(
    db_session: AsyncSession,
) -> None:
    change = ChangeControl(
        id=uuid.uuid4(),
        change_code="BG-PLAN-001",
        applicant_department="质量部",
    )
    db_session.add(change)
    await db_session.commit()

    plan = await create_change_action_plan(
        db_session,
        {
            "change_id": change.id,
            "change_code": "BG-PLAN-001",
            "project_name": "灭菌柜验证",
            "related_work": "补充验证方案和培训",
            "owner_name": "张三",
            "status": "推进中",
            "sync_status": "pending",
        },
    )
    await db_session.commit()

    items, total = await get_change_action_plans(
        db_session,
        change_code="BG-PLAN-001",
        project_name="灭菌柜验证",
        page=1,
        page_size=20,
    )

    assert total == 1
    assert items[0].project_name == "灭菌柜验证"
    assert items[0].reminder_enabled is True
    assert items[0].reminder_status == "pending"

    updated = await update_change_action_plan(
        db_session,
        plan,
        {"status": "已完成", "deadline_date": date(2026, 7, 15)},
    )
    await db_session.commit()

    assert updated.status == "已完成"
    assert updated.deadline_date == date(2026, 7, 15)
