import asyncio
from typing import Any

from sqlalchemy import text

from app.core.database import engine


async def check() -> Any:
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT COUNT(*) FROM hr.employees WHERE feishu_open_id IS NOT NULL")
        )
        print("employees with open_id:", result.scalar())
        result = await conn.execute(
            text(
                "SELECT COUNT(*) FROM hr.employees_old WHERE feishu_open_id IS NOT NULL"
            )
        )
        print("employees_old with open_id:", result.scalar())
        result = await conn.execute(
            text(
                "SELECT COUNT(*) FROM hr.employees_new WHERE feishu_open_id IS NOT NULL"
            )
        )
        print("employees_new with open_id:", result.scalar())


asyncio.run(check())
