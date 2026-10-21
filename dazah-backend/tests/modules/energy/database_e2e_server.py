"""Opt-in real PostgreSQL browser fixture; never starts background integrations.

Run only with DATABASE_URL == TEST_DATABASE_URL targeting a dedicated test DB.
All enabled units/departments below are explicit test fixtures, not business decisions.
The caller supplies a temporary SECRET_KEY and mounts the two source workbooks.
"""

import argparse
import asyncio
import json
import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID, uuid4

import jwt
import openpyxl
import uvicorn
from sqlalchemy import delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def source_expectations(directory: Path) -> None:
    """Independent numeric expectations from the value-only original file."""
    book = openpyxl.load_workbook(directory / "download.xlsx", data_only=True)
    expected: dict[str, dict[str, str]] = {}
    for name in ("饮用水码", "冰水码", "蒸汽码", "循环水码", "空气码", "电量"):
        values = {}
        for row in book[name]:
            stamp = row[0].value
            if not isinstance(stamp, (datetime, date)):
                continue
            day = stamp.date() if isinstance(stamp, datetime) else stamp
            if not date(2026, 7, 1) <= day <= date(2026, 7, 29):
                continue
            for column, cell in enumerate(row[1:], 2):
                if name == "电量" and column in {2, 41, 42, 43}:
                    continue
                if isinstance(cell.value, (int, float, str)):
                    try:
                        number = Decimal(str(cell.value))
                    except InvalidOperation:
                        continue
                    if number.is_finite():
                        values[f"{day}:{column}"] = str(number)
        expected[name] = values
    book.close()
    electric = expected["电量"]
    totals = {}
    for day_number in range(1, 29):
        key = f"2026-07-{day_number:02}"
        totals[key] = str(
            Decimal(electric[f"{key}:44"]) + Decimal(electric[f"{key}:45"])
        )
    (directory / "expected.json").write_text(
        json.dumps(
            {"readings": expected, "electric_totals": totals}, ensure_ascii=False
        ),
        encoding="utf-8",
    )


async def prepare(directory: Path) -> None:
    from app.core.database import engine
    from app.modules.energy.ledger_imports import inspect_xlsx
    from app.modules.energy.ledger_models import EnergyMeterPoint
    from app.modules.energy.ledger_schemas import MeterWrite, RuleWrite
    from app.modules.energy.ledger_service import EnergyLedgerService
    from app.modules.energy.ledger_template import extract_template
    from app.platform.identity.models import User

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    engine.echo = False
    source_expectations(directory)
    async with factory() as session:
        count = await session.scalar(select(func.count()).select_from(EnergyMeterPoint))
        if count:
            # Restart only this server's existing fixture, never adopt other data.
            state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
            claims = jwt.decode(
                state["cookies"][0]["value"],
                os.environ["SECRET_KEY"],
                algorithms=["HS256"],
            )
            existing_actor = await session.get(User, UUID(claims["sub"]))
            owned = await session.scalar(
                select(func.count())
                .select_from(
                    EnergyMeterPoint,
                )
                .where(EnergyMeterPoint.created_by == UUID(claims["sub"]))
            )
            if (
                existing_actor is None
                or not (existing_actor.username or "").startswith("energy-e2e-")
                or owned != count
            ):
                raise RuntimeError(
                    "Browser fixture requires an empty energy test ledger"
                )
            await session.close()
            await engine.dispose()
            return
        actor = User(
            id=uuid4(),
            username="energy-e2e-" + uuid4().hex,
            name="能源独立测试",
            role="admin",
            status="active",
            auth_source="local",
        )
        session.add(actor)
        await session.flush()
        service = EnergyLedgerService(session, actor)
        draft = extract_template(
            inspect_xlsx(
                (directory / "formulas.xlsx").read_bytes(),
                2026,
                date(2026, 6, 27),
                date(2026, 7, 19),
            )
        )
        # Explicit synthetic dimensions allow calculation validation without
        # approving unknown real units, departments, or excluded ownership rules.
        for definition in draft.meters:
            await service.save_meter(
                MeterWrite(
                    definition=definition.model_copy(
                        update={
                            "enabled": True,
                            "unit": "test",
                            "department": "独立测试场景",
                        }
                    )
                )
            )
        for rule in draft.rules:
            await service.save_rule(
                RuleWrite(
                    definition=rule.model_copy(
                        update={
                            "enabled": True,
                            "unit": "test",
                            "department": "独立测试场景",
                        }
                    )
                )
            )
        await session.commit()
        token = jwt.encode(
            {
                "sub": str(actor.id),
                "session_version": actor.session_version,
                "exp": datetime.now(UTC) + timedelta(hours=2),
            },
            os.environ["SECRET_KEY"],
            algorithm="HS256",
        )
        (directory / "state.json").write_text(
            json.dumps(
                {
                    "cookies": [
                        {
                            "name": "auth_token",
                            "value": token,
                            "domain": "127.0.0.1",
                            "path": "/",
                            "expires": -1,
                            "httpOnly": True,
                            "secure": False,
                            "sameSite": "Lax",
                        }
                    ],
                    "origins": [],
                }
            ),
            encoding="utf-8",
        )
        (directory / "fixture.json").write_text(
            json.dumps(
                {
                    "meters": len(draft.meters),
                    "rules": len(draft.rules),
                    "issues": draft.issues,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    await engine.dispose()


async def cleanup(directory: Path) -> None:
    """Remove only records owned by this temporary test fixture."""
    from app.core.database import engine
    from app.modules.energy.ledger_models import (
        EnergyEntryTask,
        EnergyMeterPoint,
        EnergyNotificationRun,
        EnergyReading,
        LedgerBase,
    )
    from app.platform.identity.models import User

    engine.echo = False
    state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
    claims = jwt.decode(
        state["cookies"][0]["value"],
        os.environ["SECRET_KEY"],
        algorithms=["HS256"],
    )
    actor_id = UUID(claims["sub"])
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        actor = await session.get(User, actor_id)
        if actor is None or not (actor.username or "").startswith("energy-e2e-"):
            raise RuntimeError("Not an owned browser test fixture")
        ids = select(EnergyMeterPoint.id).where(EnergyMeterPoint.created_by == actor_id)
        await session.execute(
            delete(EnergyReading).where(EnergyReading.point_id.in_(ids))
        )
        task_ids = select(EnergyEntryTask.id).where(
            EnergyEntryTask.created_by == actor_id
        )
        await session.execute(
            delete(EnergyNotificationRun).where(
                EnergyNotificationRun.task_id.in_(task_ids)
            )
        )
        for mapper in list(LedgerBase.registry.mappers):
            model = mapper.class_
            if issubclass(model, LedgerBase):
                await session.execute(delete(model).where(model.created_by == actor_id))
        actor.status = "inactive"
        await session.commit()
    await engine.dispose()
    (directory / "state.json").unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    target = os.environ.get("TEST_DATABASE_URL")
    if not target or target != os.environ.get("DATABASE_URL"):
        raise RuntimeError("Explicit identical test database URLs are required")
    if "test" not in (make_url(target).database or "").lower():
        raise RuntimeError("Dedicated test database name is required")
    if args.cleanup:
        asyncio.run(cleanup(args.fixtures))
    else:
        asyncio.run(prepare(args.fixtures))
        uvicorn.run(
            "app.main:app", host="0.0.0.0", port=8000, lifespan="off", access_log=False
        )
