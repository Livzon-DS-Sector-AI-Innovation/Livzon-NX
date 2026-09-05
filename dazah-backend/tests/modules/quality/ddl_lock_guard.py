"""测试内防御性 DDL 的锁保护。

CI 上前序测试可能留下持有表锁的连接，`ALTER TABLE ... ADD COLUMN IF NOT
EXISTS`（需要 ACCESS EXCLUSIVE 锁）会永久等待，导致整个 integration job
超时。这里给 DDL 设置会话级 lock_timeout：等锁超时（SQLSTATE 55P03）时
回滚并跳过——这些列由 alembic 迁移保证存在，补列语句只是防御性的。
"""

from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

LOCK_NOT_AVAILABLE_SQLSTATE = "55P03"


async def execute_ddl_with_lock_timeout(
    db_session: AsyncSession,
    statements: Sequence[str],
    *,
    lock_timeout: str = "10s",
) -> None:
    """逐条执行防御性 DDL；等锁超时（55P03）回滚跳过，其他错误照常抛出。"""
    await db_session.execute(text(f"SET lock_timeout = '{lock_timeout}'"))
    try:
        for statement in statements:
            try:
                await db_session.execute(text(statement))
            except DBAPIError as exc:
                sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
                if sqlstate != LOCK_NOT_AVAILABLE_SQLSTATE:
                    raise
                # 等锁超时：迁移已保证列存在，回滚后放弃本轮补列
                await db_session.rollback()
                return
    finally:
        try:
            await db_session.execute(text("SET lock_timeout = 0"))
        except Exception:  # noqa: BLE001 —— 会话可能已回滚，清理失败不影响流程
            pass