"""混粉投入明细 schema 回归：blend_batch 容纳源表多批号连写。

迁移 b4f2c8d1e3a5 将 production.blending_inputs.blend_batch 从
varchar(32) 加宽到 varchar(255)；此前源表「混合批号」列多批号连写
（44 字符）导致插入截断报错、混粉工段同步整段失败。
"""

from sqlalchemy import pool as sa_pool
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.modules.production.mc_blend_models import BlendingInput
from tests.db_safety import get_pytest_database_url

LONG_BLEND_BATCH = "MC-260714    USMC-M-2607007 USMC-M-2607008"


async def test_blend_batch_accepts_multi_batch_cell() -> None:
    """多批号连写（44 字符）可正常写入并读回——同步不再截断报错。"""
    engine = create_async_engine(
        get_pytest_database_url(get_settings()),
        poolclass=sa_pool.NullPool,
    )
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            item = BlendingInput(
                blend_batch=LONG_BLEND_BATCH,
                input_batch_no="MC-F2-260719",
                source_type="mc_f2",
                batch_level=0,
                seq_no=1,
                input_weight=461.0,
            )
            session.add(item)
            await session.commit()
            try:
                assert item.blend_batch == LONG_BLEND_BATCH
            finally:
                await session.delete(item)
                await session.commit()
    finally:
        await engine.dispose()
