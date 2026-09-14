"""仪器管理镜像：全量落库、增量水位、镜像读取、按钮列跳过（mock 飞书）。

仪器子表的列结构完全取自飞书字段元数据（含公式结果类型/is_primary），
本文件同时锁定这些元数据进入 snapshot.columns，供前端按类型渲染。
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.quality.repository import inspection_items_mirror as repo
from app.modules.quality.service import inspection_instrument_mirror as mirror

pytestmark = pytest.mark.anyio

ENTITY = "qc_instr_calibration"

_SNAPSHOT_DDL = """
    CREATE TABLE IF NOT EXISTS quality.quality_items_page_snapshots (
        page_key VARCHAR(64) NOT NULL,
        page_title VARCHAR(255) NOT NULL,
        table_name VARCHAR(255) NOT NULL,
        table_id VARCHAR(64) NOT NULL,
        source VARCHAR(64) NOT NULL DEFAULT 'feishu_bitable',
        columns JSONB NOT NULL DEFAULT '[]',
        total_rows INTEGER NOT NULL DEFAULT 0,
        last_error TEXT NULL,
        last_synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        id UUID PRIMARY KEY,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        created_by UUID NULL,
        updated_by UUID NULL,
        is_deleted BOOLEAN NOT NULL DEFAULT FALSE
    )
"""

_ROWS_DDL = """
    CREATE TABLE IF NOT EXISTS quality.quality_items_page_rows (
        page_snapshot_id UUID NOT NULL,
        source_record_id VARCHAR(64) NOT NULL,
        row_order INTEGER NOT NULL DEFAULT 0,
        cells JSONB NOT NULL DEFAULT '{}',
        search_text TEXT NOT NULL DEFAULT '',
        last_synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        id UUID PRIMARY KEY,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        created_by UUID NULL,
        updated_by UUID NULL,
        is_deleted BOOLEAN NOT NULL DEFAULT FALSE
    )
"""


@pytest.fixture(autouse=True)
async def _prepare_tables(db_session: AsyncSession) -> Any:
    from sqlalchemy import text

    await db_session.execute(text("CREATE SCHEMA IF NOT EXISTS quality"))
    await db_session.execute(text(_SNAPSHOT_DDL))
    await db_session.execute(text(_ROWS_DDL))
    await db_session.execute(text("DELETE FROM quality.quality_items_page_rows"))
    await db_session.execute(
        text("DELETE FROM quality.quality_items_page_snapshots")
    )
    await db_session.commit()
    yield
    await db_session.execute(text("DELETE FROM quality.quality_items_page_rows"))
    await db_session.execute(
        text("DELETE FROM quality.quality_items_page_snapshots")
    )
    await db_session.commit()


class _Runtime:
    app_id = "a"
    app_secret = "s"


class _Entity:
    app_token = "tokCalBase"
    table_id = "tblNeiXiao"
    enable_push_to_feishu = True
    enable_pull_from_feishu = True


def _fields() -> list[dict[str, Any]]:
    """内校汇总表字段（含公式日期列、公式单选列、按钮列、附件列）。"""
    return [
        {"field_name": "序号", "ui_type": "Number", "type": 2, "is_primary": True},
        {"field_name": "仪器、设备名称", "ui_type": "Text", "type": 1},
        # 公式返回日期：飞书回读为 Excel 序列号（"46406"），前端换算展示
        {
            "field_name": "校验有效期",
            "ui_type": "Formula",
            "type": 20,
            "property": {
                "formatter": "yyyy/MM/dd",
                "type": {"data_type": 5, "ui_type": "DateTime"},
            },
        },
        # 公式返回单选（设备类型）：值回读为选项 id，需映射回文字
        {
            "field_name": "设备类型",
            "ui_type": "Formula",
            "type": 20,
            "property": {
                "type": {
                    "data_type": 3,
                    "ui_type": "SingleSelect",
                    "ui_property": {
                        "options": [
                            {"id": "optMain", "name": "主要设备"},
                            {"id": "optKey", "name": "重点设备"},
                        ]
                    },
                }
            },
        },
        # 自动化按钮列：无值不可编辑，不应进入镜像列
        {"field_name": "点击按钮", "ui_type": "Button", "type": 3001},
        # 附件列：cells 保留 file_token，页面经后端代理快速预览
        {
            "field_name": "附件",
            "ui_type": "Attachment",
            "type": 17,
        },
    ]


def _records() -> list[dict[str, Any]]:
    return [
        {
            "record_id": "rec1",
            "fields": {
                "序号": 1,
                "仪器、设备名称": "电热恒温水浴锅",
                "校验有效期": "46406",
                "设备类型": "optKey",
                "附件": [
                    {
                        "name": "校准证书.pdf",
                        "url": "https://feishu/example.pdf",
                        "file_token": "file_tok_1",
                        "type": "application/pdf",
                        "size": 1024,
                    }
                ],
            },
            "last_modified_time": 1_700_000_000_000,
        },
        {
            "record_id": "rec2",
            "fields": {
                "序号": 2,
                "仪器、设备名称": "TOC分析仪",
                "校验有效期": "46410",
                "设备类型": "optMain",
            },
            "last_modified_time": 1_700_000_000_100,
        },
    ]


def _install_feishu_mocks(
    monkeypatch: pytest.MonkeyPatch,
    records: list[dict[str, Any]],
    fields: list[dict[str, Any]] | None = None,
) -> None:
    class _ClientObj:
        async def request(self, method, path, params=None, json=None, timeout=None):
            return {"items": records, "has_more": False, "total": len(records)}

    class _Client:
        def __init__(self, *, app_token, app_id, app_secret):
            self.app_token = app_token
            self.client = _ClientObj()

        async def list_fields(self, table_id):
            return fields if fields is not None else _fields()

    async def fake_resolve(_db, entity_code, *, direction):
        return _Runtime(), _Entity()

    monkeypatch.setattr(mirror, "_resolve_runtime_entity", fake_resolve)
    monkeypatch.setattr(mirror, "BitableClient", _Client)
    monkeypatch.setattr(
        "app.modules.quality.service.quality_feishu_sync._require_table_id",
        lambda entity: entity.table_id,
    )


async def test_sync_full_writes_mirror_with_real_fields(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_feishu_mocks(monkeypatch, _records())

    result = await mirror.sync_instrument_page(db_session, ENTITY, incremental=False)
    assert result["synced"] == 2

    read = await mirror.list_instrument_mirror(db_session, ENTITY, page=1, page_size=20)
    assert read["configured"] is True
    assert read["total"] == 2
    # 列 = 飞书真实字段（按表内顺序），按钮列被跳过
    assert read["fields"] == [
        "序号",
        "仪器、设备名称",
        "校验有效期",
        "设备类型",
        "附件",
    ]
    # 按 __last_modified 倒序：rec2 更新更晚在前
    assert read["items"][0]["record_id"] == "rec2"
    by_id = {item["record_id"]: item for item in read["items"]}
    # 公式单选：选项 id 已映射回文字
    assert by_id["rec2"]["设备类型"] == "主要设备"
    assert by_id["rec1"]["设备类型"] == "重点设备"
    # 公式日期序列号原样入库（前端按 result_ui_type 换算成日期展示）
    assert by_id["rec2"]["校验有效期"] == "46410"
    # 附件保留 file_token（页面附件预览走后端代理）
    assert by_id["rec1"]["附件"][0]["file_token"] == "file_tok_1"

    snapshot = await repo.get_snapshot(db_session, ENTITY)
    assert snapshot is not None
    columns = {col["key"]: col for col in (snapshot.columns or [])}
    assert "点击按钮" not in columns
    assert columns["校验有效期"]["result_ui_type"] == "DateTime"
    assert columns["校验有效期"]["editable"] is False
    assert columns["序号"]["is_primary"] is True


async def test_sync_full_reconciles_deleted_remote_rows(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_feishu_mocks(monkeypatch, _records())
    await mirror.sync_instrument_page(db_session, ENTITY, incremental=False)

    # 全量轮：远端只剩 rec2 → rec1 被对账软删
    _install_feishu_mocks(monkeypatch, [_records()[1]])
    await mirror.sync_instrument_page(db_session, ENTITY, incremental=False)

    read = await mirror.list_instrument_mirror(db_session, ENTITY)
    assert read["total"] == 1
    assert read["items"][0]["record_id"] == "rec2"


async def test_sync_incremental_only_writes_newer_rows(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_feishu_mocks(monkeypatch, _records())
    await mirror.sync_instrument_page(db_session, ENTITY, incremental=False)

    # 增量轮：只返回修改时间更新的一条（大于快照水线）
    newer = [
        {
            "record_id": "rec2",
            "fields": {
                "序号": 2,
                "仪器、设备名称": "TOC分析仪（已送检）",
                "校验有效期": "46410",
            },
            "last_modified_time": 1_800_000_000_000,
        }
    ]
    _install_feishu_mocks(monkeypatch, newer)
    await mirror.sync_instrument_page(db_session, ENTITY, incremental=True)

    read = await mirror.list_instrument_mirror(db_session, ENTITY)
    assert read["total"] == 2  # 历史保留
    updated = next(it for it in read["items"] if it["record_id"] == "rec2")
    assert updated["仪器、设备名称"] == "TOC分析仪（已送检）"


async def test_sync_incremental_falls_back_to_full_on_sort_reject(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_feishu_mocks(monkeypatch, _records())
    await mirror.sync_instrument_page(db_session, ENTITY, incremental=False)

    # 业务日期排序路被飞书拒绝（InvalidSort），last_modified 路也异常
    # → 回退全量 + 客户端水位过滤
    class _RejectClientObj:
        def __init__(self) -> None:
            self.search_calls = 0

        async def request(self, method, path, params=None, json=None, timeout=None):
            if method == "POST":
                self.search_calls += 1
                raise RuntimeError("InvalidSort")
            return {
                "items": _records() + [
                    {
                        "record_id": "rec3",
                        "fields": {"序号": 3, "仪器、设备名称": "新购显微镜"},
                        "last_modified_time": 1_900_000_000_000,
                    }
                ],
                "has_more": False,
                "total": 3,
            }

    class _RejectClient:
        def __init__(self, *, app_token, app_id, app_secret):
            self.app_token = app_token
            self.client = _RejectClientObj()

        async def list_fields(self, table_id):
            return _fields()

    async def fake_resolve(_db, entity_code, *, direction):
        return _Runtime(), _Entity()

    monkeypatch.setattr(mirror, "_resolve_runtime_entity", fake_resolve)
    monkeypatch.setattr(mirror, "BitableClient", _RejectClient)

    await mirror.sync_instrument_page(db_session, ENTITY, incremental=True)

    read = await mirror.list_instrument_mirror(db_session, ENTITY)
    ids = {it["record_id"] for it in read["items"]}
    assert ids == {"rec1", "rec2", "rec3"}


async def test_list_filters_placeholder_rows_and_supports_filters(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = _records() + [
        {
            "record_id": "rec_empty",
            "fields": {},
            "last_modified_time": 1_700_000_000_200,
        }
    ]
    _install_feishu_mocks(monkeypatch, records)
    await mirror.sync_instrument_page(db_session, ENTITY, incremental=False)

    read = await mirror.list_instrument_mirror(db_session, ENTITY)
    assert read["total"] == 2

    filtered = await mirror.list_instrument_mirror(
        db_session, ENTITY, filters={"设备类型": "主要设备"}
    )
    assert [it["record_id"] for it in filtered["items"]] == ["rec2"]

    keyword_hit = await mirror.list_instrument_mirror(
        db_session, ENTITY, keyword="水浴锅"
    )
    assert [it["record_id"] for it in keyword_hit["items"]] == ["rec1"]


async def test_sync_unknown_entity_rejected(db_session: AsyncSession) -> None:
    with pytest.raises(AppException):
        await mirror.sync_instrument_page(db_session, "qc_instr_not_exist")


async def test_get_fields_empty_before_sync(db_session: AsyncSession) -> None:
    fields = await mirror.get_instrument_mirror_fields(db_session, ENTITY)
    assert fields == []
    snapshot = await repo.get_snapshot(db_session, ENTITY)
    assert snapshot is None


async def test_all_entities_have_titles_and_date_routes() -> None:
    """8 张子表都有中文标题；日期排序字段必须是表内真实存在的列名。"""
    assert len(mirror.INSTRUMENT_MIRROR_ENTITIES) == 8
    for entity_code in mirror.INSTRUMENT_MIRROR_ENTITIES:
        title = mirror.INSTRUMENT_PAGE_TITLES.get(entity_code)
        assert title, entity_code
    # 有日期列的页必须配置日期排序字段；无日期列的页（维保周期表）不配
    assert "qc_instr_plans" not in mirror.INSTRUMENT_DATE_SORT_FIELDS
    assert mirror.INSTRUMENT_DATE_SORT_FIELDS["qc_instr_cal_external"] == "检定日期"