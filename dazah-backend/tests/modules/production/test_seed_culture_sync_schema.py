"""菌种同步与人员字段：open_id 解析、历史文本兼容、JSONB 落库。"""

import uuid
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import pool as sa_pool
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.modules.production import seed_culture_sync
from app.modules.production.seed_culture_models import SeedCulture
from app.modules.production.seed_culture_schemas import SeedCultureResponse
from app.modules.production.seed_culture_sync import (
    _extract_person_ids,
    sync_seed_culture_to_table,
)
from tests.db_safety import get_pytest_database_url


def test_extract_person_ids_variants() -> None:
    """bitable records 人员字段（[{"id": open_id}]）→ open_id 列表。"""
    assert _extract_person_ids([{"id": "ou_a"}, {"id": "ou_b"}]) == ["ou_a", "ou_b"]
    assert _extract_person_ids({"id": "ou_c"}) == ["ou_c"]
    assert _extract_person_ids([]) == []
    assert _extract_person_ids("张三") == []
    assert _extract_person_ids(None) == []


def test_schema_person_fields_accept_legacy_text() -> None:
    """历史文本（to_jsonb 迁移产生的 JSON 字符串 / 逗号姓名）兼容读取。"""
    now = datetime.now()
    as_json = SeedCultureResponse(
        id=uuid.uuid4(),
        batch_no="SC-1",
        product_name="盐酸林可霉素",
        prepare_operator='[{"name": "张三", "avatar_url": "https://a/1.png"}]',
        created_at=now,
        updated_at=now,
    )
    assert as_json.prepare_operator is not None
    assert as_json.prepare_operator[0].name == "张三"
    assert as_json.prepare_operator[0].avatar_url == "https://a/1.png"

    as_text = SeedCultureResponse(
        id=uuid.uuid4(),
        batch_no="SC-2",
        product_name="盐酸林可霉素",
        sterilization_operator="张三,李四",
        created_at=now,
        updated_at=now,
    )
    assert as_text.sterilization_operator is not None
    assert [p.name for p in as_text.sterilization_operator] == ["张三", "李四"]


async def test_sync_resolves_people_and_writes_jsonb() -> None:
    """同步：人员 open_id 经通讯录解析为姓名+头像，JSONB 落库；非人员列照常。"""
    engine = create_async_engine(
        get_pytest_database_url(get_settings()),
        poolclass=sa_pool.NullPool,
    )
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            config = SimpleNamespace(
                product_name="盐酸林可霉素",
                app_id="cli_test",
                encrypted_app_secret="encrypted",
                bitable_app_token="base_test",
                table_id="tbl_test",
            )
            feishu_record = {
                "fields": {
                    "摇瓶批号": "SC-SYNC-01",
                    "配置日期": 1748736000000,
                    "配制操作人/复核人": [{"id": "ou_zhang"}],
                    "调前PH": 6.5,
                    "备注（罐号）": "A107",
                }
            }
            mock_client = SimpleNamespace(
                list_records=AsyncMock(
                    return_value={
                        "items": [feishu_record],
                        "has_more": False,
                        "page_token": None,
                        "total": 1,
                    }
                ),
                _request=AsyncMock(
                    return_value={
                        "user": {
                            "name": "张三",
                            "avatar": {"avatar_240": "https://avatar/zhang.png"},
                        }
                    }
                ),
            )
            monkeypatch_client = seed_culture_sync.ProductionFeishuClient
            seed_culture_sync.ProductionFeishuClient = lambda **_: mock_client
            seed_culture_sync.decrypt_secret = lambda _: "secret"
            try:
                result = await sync_seed_culture_to_table(config, session)
            finally:
                seed_culture_sync.ProductionFeishuClient = monkeypatch_client

            assert result["created"] == 1
            # 通讯录解析：contact API 被调用，路径带 open_id
            contact_kwargs = mock_client._request.call_args
            assert "ou_zhang" in str(contact_kwargs)

            row = (
                await session.execute(
                    SeedCulture.__table__.select().where(
                        SeedCulture.batch_no == "SC-SYNC-01"
                    )
                )
            ).mappings().first()
            assert row is not None
            people = row["prepare_operator"]
            assert isinstance(people, list)
            assert people[0]["name"] == "张三"
            assert people[0]["avatar_url"] == "https://avatar/zhang.png"
            assert row["ph_before_adjust"] == 6.5
            assert row["tank_remarks"] == "A107"
            assert row["prepare_date"] == date(2025, 6, 1)

            # 清理
            await session.execute(
                SeedCulture.__table__.delete().where(
                    SeedCulture.batch_no == "SC-SYNC-01"
                )
            )
            await session.commit()
    finally:
        await engine.dispose()
