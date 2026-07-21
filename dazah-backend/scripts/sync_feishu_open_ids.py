"""Batch sync Feishu open_id for all employees with mobile numbers."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update, text

from app.platform.integrations.feishu.im import FeishuIM
from app.core.config import get_settings


async def main():
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 1. 查询 employees_old 表中有手机号的员工
        result = await session.execute(
            text("SELECT id, employee_number, name, phone FROM hr.employees_old WHERE phone IS NOT NULL AND is_deleted = false")
        )
        employees_old = result.mappings().all()

        # 2. 查询 employees_new 表中有手机号的员工
        result = await session.execute(
            text("SELECT id, employee_number, name, phone FROM hr.employees_new WHERE phone IS NOT NULL AND is_deleted = false")
        )
        employees_new = result.mappings().all()

        all_employees = list(employees_old) + list(employees_new)
        print(f"Total employees: {len(all_employees)} (old: {len(employees_old)}, new: {len(employees_new)})")

        # 3. 分批获取 open_id（每批 50 个）
        im = FeishuIM()
        batch_size = 50
        updated = 0
        failed = 0

        for i in range(0, len(all_employees), batch_size):
            batch = all_employees[i : i + batch_size]
            mobiles = [e.phone for e in batch if e.phone]

            print(f"\nBatch {i+1}-{min(i+batch_size, len(all_employees))}...")
            try:
                mapping = await im.batch_get_open_ids_by_mobile(mobiles)
            except Exception as e:
                print(f"  Query failed: {e}")
                failed += len(batch)
                continue

            # 4. 更新数据库（逐条 UPDATE）
            for emp in batch:
                open_id = mapping.get(emp.phone) if emp.phone else None
                # 判断是 old 还是 new 表
                table = "hr.employees_old" if emp in employees_old else "hr.employees_new"
                if open_id:
                    await session.execute(
                        text(f"UPDATE {table} SET feishu_open_id = :open_id WHERE id = :id"),
                        {"open_id": open_id, "id": str(emp.id)}
                    )
                    updated += 1
                    print(f"  [OK] {emp.employee_number} ({emp.phone}) -> {open_id}")
                else:
                    failed += 1
                    print(f"  [FAIL] {emp.employee_number} ({emp.phone}): not found")

            # 每批提交一次
            await session.commit()

        print(f"\n=== Done ===")
        print(f"Success: {updated}")
        print(f"Failed: {failed}")


if __name__ == "__main__":
    asyncio.run(main())
