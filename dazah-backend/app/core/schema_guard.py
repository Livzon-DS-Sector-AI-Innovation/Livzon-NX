"""Fail fast when the database schema is behind the application code."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession


def expected_alembic_heads() -> set[str]:
    backend_root = Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    return set(ScriptDirectory.from_config(config).get_heads())


async def assert_database_schema_current(session: AsyncSession) -> None:
    try:
        result = await session.execute(text("SELECT version_num FROM alembic_version"))
    except ProgrammingError as exc:
        raise RuntimeError(
            "数据库尚未完成 Alembic 初始化，服务已停止启动。"
            "请在确认目标数据库后执行 `uv run alembic upgrade head`。"
        ) from exc
    current = set(result.scalars().all())
    expected = expected_alembic_heads()
    if current == expected:
        return
    raise RuntimeError(
        "数据库结构版本落后，服务已停止启动以避免运行时 500。"
        f"当前版本：{', '.join(sorted(current)) or '未初始化'}；"
        f"应用版本：{', '.join(sorted(expected))}。"
        "请在确认目标数据库后执行 `uv run alembic upgrade head`。"
    )
