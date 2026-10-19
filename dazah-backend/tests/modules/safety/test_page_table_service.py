"""页面飞书多维表格镜像服务测试（飞书侧全程 mock，不访问真实多维表格）。"""

from datetime import UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from app.core.exceptions import AppException
from app.modules.safety.models import SafetyPageFeishuConfig
from app.modules.safety.page_tables import PAGE_TABLE_DEFINITIONS
from app.modules.safety.schemas.page_table import PageTableRecordCondition
from app.modules.safety.service import page_table

PAGE_KEY = "safety:risk-hazard:hazard-inspection:hazard-duty"
APP_TOKEN = "bascnTest"
TABLE_ID = "tblTest"

_FIELDS = [
    {"field_id": "fld1", "field_name": "记录编号", "type": 1, "is_primary": True},
    {"field_id": "fld2", "field_name": "照片", "type": 17},
    {"field_id": "fld3", "field_name": "值班日期", "type": 5},
    {
        "field_id": "fld4",
        "field_name": "整改情况",
        "type": 3,
        "property": {"options": [{"name": "未整改"}, {"name": "已整改"}]},
    },
    {"field_id": "fld5", "field_name": "公式列", "type": 20},
    {"field_id": "fld6", "field_name": "车间/位置", "type": 1},
    {"field_id": "fld7", "field_name": "父记录", "type": 18},
]


class _FakeScalars:
    def __init__(self, values: list[object]) -> None:
        self._values = values

    def all(self) -> list[object]:
        return list(self._values)


class _FakeResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object:
        return self._value

    def scalars(self) -> _FakeScalars:
        if self._value is None:
            return _FakeScalars([])
        return _FakeScalars([self._value])


class _FakeSession:
    """只满足服务用到的会话接口。"""

    def __init__(self, config: SafetyPageFeishuConfig | None) -> None:
        self.config = config
        self.commits = 0
        self.added: list[object] = []

    async def execute(self, *args: object, **kwargs: object) -> _FakeResult:
        return _FakeResult(self.config)

    def add(self, obj: object) -> None:
        self.added.append(obj)
        if self.config is None:
            self.config = obj

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, obj: object) -> None:
        return None

    async def rollback(self) -> None:
        return None


class _FakeClient:
    def __init__(
        self,
        *,
        fields: list[dict] | None = None,
        rows: list[dict] | None = None,
        search_error: str | None = None,
        record_fields: dict | None = None,
        update_result: tuple[bool, str | None] = (True, None),
        create_result: tuple[str | None, str | None] = ("rec-new", None),
        upload_token: str | None = "tok-new",
        download: bytes | None = b"file-bytes",
        tmp_download: bytes | None | object = ...,
    ) -> None:
        self.fields = _FIELDS if fields is None else fields
        self.rows = rows or []
        self.search_error = search_error
        self.record_fields = record_fields or {}
        self.update_result = update_result
        self.create_result = create_result
        self.upload_token = upload_token
        self.download = download
        # tmp_url 优先路径：默认与 download 一致；显式传 None/bytes 覆盖
        self.tmp_download = download if tmp_download is ... else tmp_download
        self.tmp_calls: list[str] = []
        self.updates: list[tuple[str, dict]] = []
        self.creates: list[dict] = []
        self.uploads: list[str] = []
        self.search_kwargs: list[dict] = []

    async def list_fields(self, table_id: str | None = None) -> list[dict]:
        return self.fields

    async def search_records_with_result(
        self, **kwargs: object
    ) -> tuple[list[dict], str | None]:
        self.search_kwargs.append(dict(kwargs))
        return self.rows, self.search_error

    async def create_record_with_result(
        self, fields: dict, table_id: str | None = None
    ) -> tuple[str | None, str | None]:
        self.creates.append(dict(fields))
        return self.create_result

    async def update_record_with_result(
        self, record_id: str, fields: dict, table_id: str | None = None
    ) -> tuple[bool, str | None]:
        self.updates.append((record_id, fields))
        return self.update_result

    async def get_record(
        self, record_id: str, table_id: str | None = None, **kwargs: object
    ) -> dict:
        return self.record_fields

    async def upload_media(
        self, file_bytes: bytes, file_name: str, parent_type: str = "bitable_file"
    ) -> str | None:
        self.uploads.append(file_name)
        return self.upload_token

    async def download_attachment_via_tmp_url(self, tmp_url: str) -> bytes | None:
        self.tmp_calls.append(tmp_url)
        return self.tmp_download

    async def download_attachment_from_url(self, download_url: str) -> bytes | None:
        return self.download

    async def download_attachment(
        self, file_token: str, extra: str | None = None
    ) -> bytes | None:
        return self.download


def _config(**overrides: object) -> SafetyPageFeishuConfig:
    values: dict[str, object] = {
        "page_key": PAGE_KEY,
        "app_token": APP_TOKEN,
        "table_id": TABLE_ID,
        "is_enabled": True,
        "hidden_field_names": [],
        # 单测默认走实时路径；镜像用例显式打开
        "is_mirrored": False,
        "last_synced_at": None,
        "last_sync_status": None,
        "last_sync_error": None,
        "last_sync_record_count": None,
    }
    values.update(overrides)
    return SafetyPageFeishuConfig(**values)


class _NullSessionCtx:
    """写透独立会话的空实现：任何查询都返回 None。"""

    def __init__(self) -> None:
        self.added: list[object] = []

    async def __aenter__(self):
        return SimpleNamespace(
            execute=AsyncMock(return_value=_FakeResult(None)),
            add=self.added.append,
            commit=AsyncMock(return_value=None),
        )

    async def __aexit__(self, *args: object) -> None:
        return None


def _null_session_factory() -> _NullSessionCtx:
    return _NullSessionCtx()


def _install_client(monkeypatch, client: _FakeClient) -> _FakeClient:
    monkeypatch.setattr(
        page_table, "SafetyBitableClient", lambda **kwargs: client
    )
    # 字段 schema 缓存命中会让断言依赖 Redis 状态，测试里固定走实时读取
    monkeypatch.setattr(page_table, "cache_get", AsyncMock(return_value=None))
    monkeypatch.setattr(page_table, "cache_set", AsyncMock(return_value=None))
    monkeypatch.setattr(page_table, "cache_delete", AsyncMock(return_value=None))
    monkeypatch.setattr(page_table, "record_audit_log", AsyncMock(return_value=None))
    # 写透路径的独立会话：查不到配置即安静返回 False，不触真实数据库
    monkeypatch.setattr(page_table, "async_session_factory", _null_session_factory)
    # AI 兜底默认关闭（不触发 LLM）；需要时在用例内单独 mock _ai_classify_workshops
    monkeypatch.setattr(
        page_table, "_load_classifications", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        page_table, "_save_classifications", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        page_table, "_ai_classify_workshops", AsyncMock(return_value={})
    )
    return client


async def test_list_records_decodes_columns_and_applies_hidden_keyword_sort_paging(
    monkeypatch,
) -> None:
    rows = [
        {
            "record_id": "rec-1",
            "fields": {"记录编号": [{"text": "YH-1"}], "整改情况": "未整改"},
        },
        {
            "record_id": "rec-2",
            "fields": {"记录编号": [{"text": "YH-2"}], "整改情况": "已整改"},
        },
        {
            "record_id": "rec-3",
            "fields": {"记录编号": [{"text": "YH-3"}], "整改情况": "未整改"},
        },
    ]
    client = _install_client(monkeypatch, _FakeClient(rows=rows))
    db = _FakeSession(_config(hidden_field_names=["公式列"]))

    result = await page_table.list_page_table_records(
        db, PAGE_KEY, page=1, page_size=2, keyword="YH-"
    )

    assert result.page_name == "24小时值班隐患"
    assert "公式列" not in {column.name for column in result.columns}
    assert result.total == 3
    assert [record.record_id for record in result.records] == ["rec-1", "rec-2"]
    assert result.records[0].fields["记录编号"] == "YH-1"
    assert result.page_size == 2

    filtered = await page_table.list_page_table_records(
        db, PAGE_KEY, page=1, page_size=10, keyword="已整改"
    )
    assert [record.record_id for record in filtered.records] == ["rec-2"]

    sorted_result = await page_table.list_page_table_records(
        db, PAGE_KEY, page=1, page_size=10, sort_field="记录编号", sort_direction="desc"
    )
    assert [record.record_id for record in sorted_result.records] == [
        "rec-3",
        "rec-2",
        "rec-1",
    ]
    assert client.rows == rows


async def test_list_records_without_binding_raises_service_unavailable() -> None:
    db = _FakeSession(None)
    with pytest.raises(AppException) as excinfo:
        await page_table.list_page_table_records(db, PAGE_KEY)
    assert excinfo.value.status_code == 503
    assert "飞书设置" in excinfo.value.message


async def test_list_records_disabled_binding_raises_service_unavailable() -> None:
    db = _FakeSession(_config(is_enabled=False))
    with pytest.raises(AppException) as excinfo:
        await page_table.list_page_table_records(db, PAGE_KEY)
    assert excinfo.value.status_code == 503


async def test_list_records_surfaces_feishu_read_error(monkeypatch) -> None:
    _install_client(monkeypatch, _FakeClient(search_error="Permission denied"))
    db = _FakeSession(_config())
    with pytest.raises(AppException) as excinfo:
        await page_table.list_page_table_records(db, PAGE_KEY)
    assert excinfo.value.status_code == 502
    assert "Permission denied" in excinfo.value.message


async def test_list_records_unknown_page_key_raises_not_found() -> None:
    db = _FakeSession(_config())
    with pytest.raises(AppException) as excinfo:
        await page_table.list_page_table_records(db, "safety:not:registered")
    assert excinfo.value.status_code == 404


async def test_update_record_encodes_fields_and_writes_back(monkeypatch) -> None:
    client = _install_client(
        monkeypatch,
        _FakeClient(
            record_fields={
                "记录编号": [{"text": "YH-9"}],
                "整改情况": "已整改",
                "值班日期": 1791561600000,
            }
        ),
    )
    db = _FakeSession(_config())
    user_id = uuid4()

    record = await page_table.update_page_table_record(
        db,
        PAGE_KEY,
        "rec-1",
        {"记录编号": "YH-9", "整改情况": "已整改", "值班日期": "2026-10-10"},
        user_id=user_id,
    )

    assert client.updates == [
        (
            "rec-1",
            {"记录编号": "YH-9", "整改情况": "已整改", "值班日期": 1791561600000},
        )
    ]
    # 回读飞书后的规范值（日期回到 YYYY-MM-DD，供前端直接展示）
    assert record.fields["值班日期"] == "2026-10-10"
    assert record.fields["整改情况"] == "已整改"


async def test_update_record_rejects_unknown_and_attachment_fields(monkeypatch) -> None:
    _install_client(monkeypatch, _FakeClient())
    db = _FakeSession(_config())

    with pytest.raises(AppException) as unknown:
        await page_table.update_page_table_record(
            db, PAGE_KEY, "rec-1", {"不存在": "x"}
        )
    assert unknown.value.status_code == 400

    with pytest.raises(AppException) as attachment:
        await page_table.update_page_table_record(
            db, PAGE_KEY, "rec-1", {"照片": [{"file_token": "tok"}]}
        )
    assert attachment.value.status_code == 400
    assert "附件" in attachment.value.message


async def test_update_record_rejects_invalid_option(monkeypatch) -> None:
    _install_client(monkeypatch, _FakeClient())
    db = _FakeSession(_config())
    with pytest.raises(AppException) as excinfo:
        await page_table.update_page_table_record(
            db, PAGE_KEY, "rec-1", {"整改情况": "随便写的"}
        )
    assert excinfo.value.status_code == 400
    assert "选项" in excinfo.value.message


async def test_update_record_surfaces_feishu_write_error(monkeypatch) -> None:
    _install_client(
        monkeypatch, _FakeClient(update_result=(False, "FieldNameNotFound"))
    )
    db = _FakeSession(_config())
    with pytest.raises(AppException) as excinfo:
        await page_table.update_page_table_record(
            db, PAGE_KEY, "rec-1", {"记录编号": "YH-9"}
        )
    assert excinfo.value.status_code == 502
    assert "FieldNameNotFound" in excinfo.value.message


async def test_update_record_requires_at_least_one_field(monkeypatch) -> None:
    _install_client(monkeypatch, _FakeClient())
    db = _FakeSession(_config())
    with pytest.raises(AppException) as excinfo:
        await page_table.update_page_table_record(db, PAGE_KEY, "rec-1", {})
    assert excinfo.value.status_code == 400


async def test_upload_attachment_appends_and_keeps_existing_tokens(monkeypatch) -> None:
    client = _install_client(
        monkeypatch,
        _FakeClient(
            upload_token="tok-new",
            record_fields={
                "照片": [
                    {"file_token": "tok-old", "name": "old.jpg", "type": "image/jpeg"}
                ]
            },
        ),
    )
    monkeypatch.setattr(
        page_table,
        "read_upload_secure",
        AsyncMock(return_value=("new.jpg", b"content")),
    )
    db = _FakeSession(_config())

    result = await page_table.upload_page_table_attachment(
        db,
        PAGE_KEY,
        "rec-1",
        "照片",
        file=SimpleNamespace(),
        user_id=uuid4(),
    )

    assert client.uploads == ["new.jpg"]
    # 关键：只追加，不覆盖既有附件
    assert client.updates == [
        ("rec-1", {"照片": [{"file_token": "tok-old"}, {"file_token": "tok-new"}]})
    ]
    assert result.field_name == "照片"


async def test_upload_attachment_skips_duplicate_token(monkeypatch) -> None:
    client = _install_client(
        monkeypatch,
        _FakeClient(
            upload_token="tok-old",
            record_fields={"照片": [{"file_token": "tok-old", "name": "old.jpg"}]},
        ),
    )
    monkeypatch.setattr(
        page_table, "read_upload_secure", AsyncMock(return_value=("old.jpg", b"c"))
    )
    db = _FakeSession(_config())

    await page_table.upload_page_table_attachment(
        db, PAGE_KEY, "rec-1", "照片", file=SimpleNamespace()
    )
    assert client.updates == [("rec-1", {"照片": [{"file_token": "tok-old"}]})]


async def test_upload_attachment_rejects_non_attachment_field(monkeypatch) -> None:
    _install_client(monkeypatch, _FakeClient())
    monkeypatch.setattr(
        page_table, "read_upload_secure", AsyncMock(return_value=("a.txt", b"x"))
    )
    db = _FakeSession(_config())
    with pytest.raises(AppException) as excinfo:
        await page_table.upload_page_table_attachment(
            db, PAGE_KEY, "rec-1", "记录编号", file=SimpleNamespace()
        )
    assert excinfo.value.status_code == 400
    assert "不是附件字段" in excinfo.value.message


async def test_upload_attachment_surfaces_upload_failure(monkeypatch) -> None:
    _install_client(monkeypatch, _FakeClient(upload_token=None))
    monkeypatch.setattr(
        page_table, "read_upload_secure", AsyncMock(return_value=("a.jpg", b"x"))
    )
    db = _FakeSession(_config())
    with pytest.raises(AppException) as excinfo:
        await page_table.upload_page_table_attachment(
            db, PAGE_KEY, "rec-1", "照片", file=SimpleNamespace()
        )
    assert excinfo.value.status_code == 502


async def test_fetch_attachment_rejects_token_not_on_record(monkeypatch) -> None:
    _install_client(
        monkeypatch,
        _FakeClient(
            record_fields={"照片": [{"file_token": "tok-owned", "name": "a.jpg"}]}
        ),
    )
    db = _FakeSession(_config())
    with pytest.raises(AppException) as excinfo:
        await page_table.fetch_page_table_attachment(
            db, PAGE_KEY, "rec-1", "照片", "tok-other"
        )
    assert excinfo.value.status_code == 404


async def test_fetch_attachment_returns_bytes_for_owned_token(monkeypatch) -> None:
    client = _install_client(
        monkeypatch,
        _FakeClient(
            record_fields={
                "照片": [
                    {
                        "file_token": "tok-owned",
                        "name": "a.jpg",
                        "type": "image/jpeg",
                        "url": "https://open/x",
                        "tmp_url": "https://open/batch_get_tmp_download_url?file_tokens=tok-owned",
                    }
                ]
            }
        ),
    )
    db = _FakeSession(_config())
    content, content_type, filename = await page_table.fetch_page_table_attachment(
        db, PAGE_KEY, "rec-1", "照片", "tok-owned"
    )
    assert content == b"file-bytes"
    assert content_type == "image/jpeg"
    assert filename == "a.jpg"
    # tmp_url（batch_get_tmp_download_url）是首选下载路径
    assert client.tmp_calls == [
        "https://open/batch_get_tmp_download_url?file_tokens=tok-owned"
    ]


async def test_fetch_attachment_falls_back_when_tmp_url_fails(monkeypatch) -> None:
    """tmp_url 换取失败时回退附件 url / 直接下载，不中断代理。"""
    _install_client(
        monkeypatch,
        _FakeClient(
            record_fields={
                "照片": [
                    {
                        "file_token": "tok-1",
                        "name": "a.jpg",
                        "type": "image/jpeg",
                        "url": "https://open/x",
                        "tmp_url": "https://open/batch_get_tmp_download_url?file_tokens=tok-1",
                    }
                ]
            },
            tmp_download=None,
            download=b"file-bytes",
        ),
    )
    db = _FakeSession(_config())
    content, _, _ = await page_table.fetch_page_table_attachment(
        db, PAGE_KEY, "rec-1", "照片", "tok-1"
    )
    assert content == b"file-bytes"


async def test_test_binding_reports_failure_when_fields_unreadable(monkeypatch) -> None:
    _install_client(monkeypatch, _FakeClient(fields=[]))
    config = _config()
    db = _FakeSession(config)

    result = await page_table.test_page_feishu_config(db, PAGE_KEY)

    assert result.success is False
    assert "协作者" in result.message
    assert config.last_test_status == "failed"
    assert config.last_test_error


async def test_test_binding_reports_success_and_records_counts(monkeypatch) -> None:
    _install_client(monkeypatch, _FakeClient(rows=[{"record_id": "rec-1"}]))
    config = _config()
    db = _FakeSession(config)

    result = await page_table.test_page_feishu_config(db, PAGE_KEY)

    assert result.success is True
    assert result.field_count == len(_FIELDS)
    assert config.last_test_status == "success"
    assert config.last_test_field_count == len(_FIELDS)
    assert [field.name for field in result.fields] == [
        field["field_name"] for field in _FIELDS
    ]


async def test_save_config_persists_binding_and_clears_test_state(monkeypatch) -> None:
    _install_client(monkeypatch, _FakeClient())
    config = _config(last_test_status="success", last_test_error=None)
    db = _FakeSession(config)

    from app.modules.safety.schemas.page_table import UpdatePageFeishuConfigRequest

    item = await page_table.save_page_feishu_config(
        db,
        PAGE_KEY,
        UpdatePageFeishuConfigRequest(
            app_token=" bascnNew ", table_id="tblNew", is_enabled=False
        ),
    )

    assert config.app_token == "bascnNew"
    assert config.table_id == "tblNew"
    assert config.is_enabled is False
    # 绑定变化后旧的测试结论不再适用
    assert config.last_test_status is None
    assert item.is_configured is True
    assert db.commits == 1


async def test_list_configs_includes_unconfigured_pages() -> None:
    db = _FakeSession(None)
    result = await page_table.list_page_feishu_configs(db)
    # 未配置绑定的镜像页也会出现在列表里（设置页据此集中维护）
    assert [item.page_key for item in result.items] == [
        definition.page_key for definition in PAGE_TABLE_DEFINITIONS
    ]
    duty = next(item for item in result.items if item.page_key == PAGE_KEY)
    assert duty.is_configured is False
    assert duty.page_name == "24小时值班隐患"


async def test_list_records_view_id_is_record_only(monkeypatch) -> None:
    """飞书无「视图字段」开放接口：view_id 仅记录，列由隐藏字段配置控制。

    /views/:id/fields 端点在飞书网关层返回 404 page not found，历史上对它
    的调用从未成功过，现在不再发起请求。
    """
    rows = [
        {
            "record_id": "rec-1",
            "fields": {
                "记录编号": [{"text": "YH-1"}],
                "值班日期": 1770652800000,
                "照片": [{"file_token": "tok-1"}],
            },
        }
    ]
    _install_client(monkeypatch, _FakeClient(rows=rows))
    db = _FakeSession(_config(view_id="vewOps"))

    result = await page_table.list_page_table_records(db, PAGE_KEY)

    # 列 = 全量字段 − 隐藏字段（本配置未隐藏任何字段）
    assert [column.name for column in result.columns] == [
        field["field_name"] for field in _FIELDS
    ]


async def test_list_records_hides_fields_from_binding(monkeypatch) -> None:
    """隐藏字段配置承担视图对齐：配置内的字段从列与记录中裁掉。"""
    rows = [
        {
            "record_id": "rec-1",
            "fields": {
                "记录编号": [{"text": "YH-1"}],
                "值班日期": 1770652800000,
                "照片": [{"file_token": "tok-1"}],
            },
        }
    ]
    _install_client(monkeypatch, _FakeClient(rows=rows))
    db = _FakeSession(_config(hidden_field_names=["照片"]))

    result = await page_table.list_page_table_records(db, PAGE_KEY)

    assert "照片" not in {column.name for column in result.columns}
    assert "照片" not in result.records[0].fields


async def test_stats_respects_hidden_columns(monkeypatch) -> None:
    """统计分组同样基于可见列，隐藏字段不能作为分组维度。"""
    _install_client(monkeypatch, _FakeClient())
    db = _FakeSession(_config(hidden_field_names=["照片"]))

    with pytest.raises(AppException) as excinfo:
        await page_table.get_page_table_stats(db, PAGE_KEY, group_by=["照片"])
    assert excinfo.value.status_code == 400
    assert "照片" in excinfo.value.message


async def test_list_records_conditions_combine_with_and(monkeypatch) -> None:
    """多条件筛选：字段间 AND；选项精确匹配，日期按天前缀匹配。"""
    rows = [
        {
            "record_id": "rec-1",
            "fields": {"整改情况": "未整改", "值班日期": 1770595200000},
        },
        {
            "record_id": "rec-2",
            "fields": {"整改情况": "已整改", "值班日期": 1770595200000},
        },
        {
            "record_id": "rec-3",
            "fields": {"整改情况": "未整改", "值班日期": 1770681600000},
        },
    ]
    _install_client(monkeypatch, _FakeClient(rows=rows))
    db = _FakeSession(_config())

    result = await page_table.list_page_table_records(
        db,
        PAGE_KEY,
        conditions=[
            PageTableRecordCondition(field="整改情况", value="未整改"),
            PageTableRecordCondition(field="值班日期", value="2026-02-09"),
        ],
    )

    # 1770595200000 = 2026-02-09；条件组合后只剩 rec-1
    assert [record.record_id for record in result.records] == ["rec-1"]

    month_only = await page_table.list_page_table_records(
        db,
        PAGE_KEY,
        conditions=[PageTableRecordCondition(field="值班日期", value="2026-02")],
    )
    assert [record.record_id for record in month_only.records] == [
        "rec-1",
        "rec-2",
        "rec-3",
    ]


async def test_list_records_conditions_reject_unknown_field(monkeypatch) -> None:
    _install_client(monkeypatch, _FakeClient())
    db = _FakeSession(_config())

    with pytest.raises(AppException) as excinfo:
        await page_table.list_page_table_records(
            db,
            PAGE_KEY,
            conditions=[PageTableRecordCondition(field="不存在的字段", value="x")],
        )
    assert excinfo.value.status_code == 400


async def test_list_records_fetches_newest_first_by_date(monkeypatch) -> None:
    """超过条数上限时按日期倒序拉取，确保最新记录进入加载窗口。"""
    client = _install_client(monkeypatch, _FakeClient())
    db = _FakeSession(_config())

    await page_table.list_page_table_records(db, PAGE_KEY)

    assert client.search_kwargs[0]["sort"] == [
        {"field_name": "值班日期", "desc": True}
    ]


# ── 车间号识别归一 ──


def test_normalize_workshop_name_merges_numbering_variants() -> None:
    """「201-1车间」「201-1」「201一车间」都是同一个车间 201一车间。"""
    normalize = page_table.normalize_workshop_name
    assert normalize("201-1车间") == "201一车间"
    assert normalize("201-1") == "201一车间"
    assert normalize("201一车间") == "201一车间"
    assert normalize(" 201 一 车间 ") == "201一车间"
    assert normalize("102-2") == "102二车间"
    assert normalize("203-3车间") == "203三车间"
    assert normalize("201二车间") == "201二车间"
    assert normalize("11-2车间") == "11二车间"
    assert normalize("203-10车间") == "203十车间"


def test_normalize_workshop_name_keeps_non_workshop_values() -> None:
    normalize = page_table.normalize_workshop_name
    assert normalize("原料罐区") == "原料罐区"
    assert normalize("103车间") == "103车间"  # 无序号不造序号
    assert normalize("202车间") == "202车间"
    assert normalize("") == ""
    assert normalize("仓库东侧走道") == "仓库东侧走道"


def test_normalize_workshop_name_applies_configured_aliases() -> None:
    """页面配置的别名映射：值中包含产线别名即归入规范车间（长别名优先）。"""
    aliases = {
        "DR车间": "201二车间（DR）",
        "DR提炼": "201二车间（DR）",
        "DR": "201二车间（DR）",
        "多拉": "201二车间（DR）",
        "MC车间": "201二车间（MC）",
        "MC": "201二车间（MC）",
        "霉酚酸提炼": "201二车间（MC）",
        "霉酚酸": "201二车间（MC）",
    }
    normalize = page_table.normalize_workshop_name
    assert normalize("DR车间", aliases) == "201二车间（DR）"
    assert normalize("201多拉", aliases) == "201二车间（DR）"
    assert normalize("201-2多拉车间", aliases) == "201二车间（DR）"
    assert normalize("多拉提取", aliases) == "201二车间（DR）"
    assert normalize("201二车间多拉U型弯", aliases) == "201二车间（DR）"
    assert normalize("霉酚酸车间二楼", aliases) == "201二车间（MC）"
    assert normalize("102-2车间MC过滤岗位", aliases) == "201二车间（MC）"
    # 不含别名的值不受影响，仍走车间号规则
    assert normalize("201-1车间", aliases) == "201一车间"
    assert normalize("201二车间", aliases) == "201二车间"
    assert normalize("原料罐区", aliases) == "原料罐区"


def test_normalize_workshop_name_applies_site_rules() -> None:
    """按现场车间结构配置的完整别名集：默认产线、按厂房合并、部门归口。"""
    aliases = {
        # 产线别名
        "DR车间": "201二车间（DR）",
        "DR提炼": "201二车间（DR）",
        "DR": "201二车间（DR）",
        "多拉": "201二车间（DR）",
        "哆啦生产线": "201二车间（DR）",
        "MC车间": "201二车间（MC）",
        "MC": "201二车间（MC）",
        "霉酚酸提炼": "201二车间（MC）",
        "霉酚酸": "201二车间（MC）",
        # 201二车间默认产线为 MC
        "201二车间": "201二车间（MC）",
        "201-2车间": "201二车间（MC）",
        "201-2": "201二车间（MC）",
        # 203 各序号车间合并为 203车间
        "203-1车间": "203车间",
        "203一车间": "203车间",
        "203-1": "203车间",
        "203-2车间": "203车间",
        "203二车间": "203车间",
        "203-2": "203车间",
        "203-3车间": "203车间",
        "203三车间": "203车间",
        "203-3": "203车间",
        # 103 含各序号与液氨罐区
        "103一车间": "103车间",
        "103-1车间": "103车间",
        "103-1": "103车间",
        "103二车间": "103车间",
        "103-2车间": "103车间",
        "103-2": "103车间",
        "液氨罐区": "103车间",
        # 201三车间
        "辅助车间": "201三车间",
        "甲类罐区": "201三车间",
        "RTO": "201三车间",
        # 部门归口
        "仓库": "仓储部门",
        "库房": "仓储部门",
        "道路": "行政部",
        "后勤": "行政部",
        "循环水站": "动力科",
        "东动力": "动力科",
        "西动力": "动力科",
        "动力": "动力科",
        "空压站": "动力科",
        "锅炉": "动力科",
    }
    normalize = page_table.normalize_workshop_name

    # 默认产线：不带线标记的 201二车间 归（MC）
    assert normalize("201二车间", aliases) == "201二车间（MC）"
    assert normalize("201-2车间", aliases) == "201二车间（MC）"
    assert normalize("201-2", aliases) == "201二车间（MC）"
    # 但带产线标记的仍归对应产线（默认线不得抢线）
    assert normalize("201-2车间多拉提炼", aliases) == "201二车间（DR）"
    assert normalize("201二车间多拉U型弯", aliases) == "201二车间（DR）"
    # 203 各序号合并为 203车间（含带楼层/位置后缀的写法）
    assert normalize("203-1车间", aliases) == "203车间"
    assert normalize("203一车间二楼", aliases) == "203车间"
    assert normalize("203-3车间", aliases) == "203车间"
    # 103 合并 + 液氨罐区
    assert normalize("103-2车间", aliases) == "103车间"
    assert normalize("液氨罐区", aliases) == "103车间"
    # 201三车间归口
    assert normalize("辅助车间", aliases) == "201三车间"
    assert normalize("甲类罐区", aliases) == "201三车间"
    assert normalize("201车间甲类罐区", aliases) == "201三车间"
    assert normalize("RTO", aliases) == "201三车间"
    # 部门归口
    assert normalize("303仓库", aliases) == "仓储部门"
    assert normalize("后勤行政", aliases) == "行政部"
    assert normalize("循环水站", aliases) == "动力科"
    assert normalize("东动力", aliases) == "动力科"
    assert normalize("空压站", aliases) == "动力科"
    assert normalize("锅炉房", aliases) == "动力科"
    # 楼层后缀剥离（不含别名的普通车间）
    assert normalize("201一车间二楼", aliases) == "201一车间"
    assert normalize("102二车间陶瓷膜区域", aliases) == "102二车间"
    # 哆啦 是 多拉 的另一种写法（产线别名包含匹配兜住）
    assert normalize("哆啦生产线", aliases) == "201二车间（DR）"


# ── 仪表盘聚合 ──


def _stats_rows() -> list[dict]:
    # 1791561600000 是 2026-10-10（东八区零点）；7 月 1 日应为 1782835200000
    july_1 = 1782835200000
    aug_1 = 1785513600000
    return [
        {
            "record_id": "rec-1",
            "fields": {
                "值班日期": july_1,
                "整改情况": "未整改",
                "车间/位置": [{"text": "201-1车间"}],
            },
        },
        {
            "record_id": "rec-2",
            "fields": {
                "值班日期": july_1,
                "整改情况": "已整改",
                "车间/位置": [{"text": "201一车间"}],
            },
        },
        {
            "record_id": "rec-3",
            "fields": {
                "值班日期": aug_1,
                "整改情况": "已整改",
                "车间/位置": [{"text": "201-1"}],
            },
        },
        {
            "record_id": "rec-4",
            "fields": {
                "值班日期": aug_1,
                "整改情况": "已整改",
                "车间/位置": [{"text": "原料罐区"}],
            },
        },
        {
            "record_id": "rec-5",
            "fields": {"值班日期": None, "整改情况": None, "车间/位置": None},
        },
    ]


async def test_stats_aggregates_month_workshop_and_status(monkeypatch) -> None:
    _install_client(monkeypatch, _FakeClient(rows=_stats_rows()))
    db = _FakeSession(_config())

    result = await page_table.get_page_table_stats(db, PAGE_KEY)

    assert result.total == 5
    by_field = {group.field: group for group in result.groups}
    # 缺省维度：日期字段按月、位置类文本按车间号、单选按选项
    assert set(by_field) == {"值班日期", "车间/位置", "整改情况"}

    months = {b.key: b.count for b in by_field["值班日期"].buckets}
    assert months["2026-07"] == 2
    assert months["2026-08"] == 2
    assert by_field["值班日期"].mode == "month"

    # 「201-1车间」「201一车间」「201-1」归一为同一车间
    shops = {b.key: b.count for b in by_field["车间/位置"].buckets}
    assert shops["201一车间"] == 3
    assert shops["原料罐区"] == 1
    assert shops["（未填写）"] == 1

    status = {b.key: b.count for b in by_field["整改情况"].buckets}
    assert status == {"已整改": 3, "未整改": 1, "（未填写）": 1}
    # 计数多的选项排前面
    assert by_field["整改情况"].buckets[0].key == "已整改"


async def test_stats_month_keeps_most_recent_when_over_limit(monkeypatch) -> None:
    rows = []
    # 14 个月，每月 1 条：应只保留最近 12 个月（2025-03 起）
    base_month = (2025, 1)
    for offset in range(14):
        month_index = base_month[1] + offset
        year = base_month[0] + (month_index - 1) // 12
        month = (month_index - 1) % 12 + 1
        from datetime import datetime

        moment = datetime(year, month, 1, tzinfo=UTC)
        rows.append(
            {
                "record_id": f"rec-{offset}",
                "fields": {"值班日期": int(moment.timestamp() * 1000)},
            }
        )
    _install_client(monkeypatch, _FakeClient(rows=rows))
    db = _FakeSession(_config())

    result = await page_table.get_page_table_stats(db, PAGE_KEY)

    months = [b.key for b in result.groups[0].buckets]
    assert len(months) == 12
    assert months[0] == "2025-03"
    assert months[-1] == "2026-02"


async def test_stats_caps_value_buckets_with_overflow(monkeypatch) -> None:
    rows = [
        {
            "record_id": f"rec-{index}",
            "fields": {"车间/位置": [{"text": f"{200 + index}车间"}]},
        }
        for index in range(12)
    ]
    _install_client(monkeypatch, _FakeClient(rows=rows))
    db = _FakeSession(_config())

    result = await page_table.get_page_table_stats(
        db, PAGE_KEY, group_by=["车间/位置"]
    )

    group = result.groups[0]
    assert len(group.buckets) == page_table.STATS_GROUP_LIMIT + 1
    assert group.buckets[-1].key == "其他"
    assert group.buckets[-1].count == 12 - page_table.STATS_GROUP_LIMIT


async def test_stats_rejects_unknown_group_field(monkeypatch) -> None:
    _install_client(monkeypatch, _FakeClient())
    db = _FakeSession(_config())
    with pytest.raises(AppException) as excinfo:
        await page_table.get_page_table_stats(db, PAGE_KEY, group_by=["不存在的列"])
    assert excinfo.value.status_code == 400


async def test_stats_applies_configured_workshop_aliases(monkeypatch) -> None:
    """配置行里的车间别名映射必须参与统计聚合（回归：曾漏传导致别名不生效）。"""
    _install_client(monkeypatch, _FakeClient(rows=_stats_rows()))
    db = _FakeSession(
        _config(workshop_aliases={"原料罐区": "201一车间", "201一车间": "201一车间"})
    )

    result = await page_table.get_page_table_stats(db, PAGE_KEY)

    shops = {
        group.field: {b.key: b.count for b in group.buckets}
        for group in result.groups
    }["车间/位置"]
    # 「原料罐区」按别名并入 201一车间
    assert shops["201一车间"] == 4
    assert "原料罐区" not in shops


async def test_records_filter_matches_by_stat_bucket_key(monkeypatch) -> None:
    """下钻筛选与统计聚合必须用同一套归一规则（含别名），否则数字对不上。"""
    _install_client(
        monkeypatch,
        _FakeClient(
            rows=[
                {
                    "record_id": "rec-1",
                    "fields": {
                        "车间/位置": [{"text": "201-2多拉车间"}],
                        "整改情况": "未整改",
                    },
                },
                {
                    "record_id": "rec-2",
                    "fields": {
                        "车间/位置": [{"text": "201一车间"}],
                        "整改情况": "已整改",
                    },
                },
            ]
        ),
    )
    db = _FakeSession(
        _config(workshop_aliases={"多拉": "201二车间（DR）"})
    )

    result = await page_table.list_page_table_records(
        db,
        PAGE_KEY,
        page=1,
        page_size=10,
        filter_field="车间/位置",
        filter_value="201二车间（DR）",
    )

    assert result.total == 1
    assert result.records[0].record_id == "rec-1"


async def test_records_filter_other_drills_into_overflow(monkeypatch) -> None:
    """「其他」是合成桶：下钻 = 不在展示名单内的记录（与图表口径一致）。"""
    rows = [
        {
            "record_id": f"rec-{index}",
            "fields": {"车间/位置": [{"text": f"{200 + index}车间"}]},
        }
        for index in range(12)
    ]
    _install_client(monkeypatch, _FakeClient(rows=rows))
    db = _FakeSession(_config())

    result = await page_table.list_page_table_records(
        db,
        PAGE_KEY,
        page=1,
        page_size=10,
        filter_field="车间/位置",
        filter_value="其他",
    )

    stats = await page_table.get_page_table_stats(db, PAGE_KEY, group_by=["车间/位置"])
    named_total = sum(
        bucket.count for bucket in stats.groups[0].buckets if bucket.key != "其他"
    )
    assert stats.total == 12
    assert result.total == 12 - named_total


async def test_stats_defers_unknown_values_to_background_ai(monkeypatch) -> None:
    """未识别写法本轮以原值分组，AI 兜底转为后台任务，不阻塞请求。"""
    _install_client(monkeypatch, _FakeClient(rows=_stats_rows()))
    db = _FakeSession(_config())

    result = await page_table.get_page_table_stats(db, PAGE_KEY)

    shops = {
        group.field: {b.key: b.count for b in group.buckets}
        for group in result.groups
    }["车间/位置"]
    # 本轮仍以原值分组（不阻塞等待 LLM），后台任务完成后下次刷新生效
    assert "原料罐区" in shops
    assert shops["原料罐区"] == 1


async def test_classify_pending_workshops_saves_ai_results(monkeypatch) -> None:
    """后台 AI 兜底：LLM 结果写入分类缓存，带分布式锁防并发重复调用。"""
    pending = ["污水车间", "厂区东南角"]
    lock_state = {"acquired": True}

    async def _acquire(key, timeout=10):
        return lock_state["acquired"]

    async def _release(key):
        lock_state["released"] = True

    class _FakeSessionCtx:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *args):
            return None

    ai_mock = AsyncMock(
        side_effect=lambda values, names: {
            value: ("动力科" if value == "污水车间" else "未分类")
            for value in values
        }
    )
    monkeypatch.setattr(page_table, "_ai_classify_workshops", ai_mock)
    monkeypatch.setattr(page_table, "acquire_lock", _acquire)
    monkeypatch.setattr(page_table, "release_lock", _release)
    monkeypatch.setattr(
        page_table, "async_session_factory", lambda: _FakeSessionCtx()
    )
    save_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(page_table, "_save_classifications", save_mock)

    await page_table._classify_pending_workshops(pending, aliases={"动力科": "动力科"})

    # 能归入规范清单的与「未分类」的都落缓存——后者避免同一写法反复调用 LLM；
    # 统计侧只把能归类的用作分组键，「未分类」保持原值展示
    saved = save_mock.await_args.args[1]
    assert saved["污水车间"] == "动力科"
    assert saved["厂区东南角"] == "未分类"
    assert lock_state.get("released") is True

    # 拿不到锁（已有后台任务在跑）时不重复调用 LLM
    lock_state["acquired"] = False
    ai_mock.reset_mock()
    await page_table._classify_pending_workshops(pending, aliases={"动力科": "动力科"})
    ai_mock.assert_not_awaited()


# ── 缩略图 ──


def _png_bytes(color: tuple[int, int, int] = (200, 30, 30), size: int = 400) -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (size, size), color).save(buf, format="PNG")
    return buf.getvalue()


def test_build_thumbnail_resizes_image_to_jpeg() -> None:
    from app.modules.safety.service.attachment_thumbnail import (
        DEFAULT_MAX_HEIGHT,
        DEFAULT_MAX_WIDTH,
        build_thumbnail,
    )

    thumb = build_thumbnail(
        _png_bytes(), "photo.png", DEFAULT_MAX_WIDTH, DEFAULT_MAX_HEIGHT
    )
    assert thumb is not None
    assert thumb[:2] == b"\xff\xd8"  # JPEG 魔数
    with __import__("io").BytesIO(thumb) as opened:
        from PIL import Image

        with Image.open(opened) as image:
            assert max(image.size) <= DEFAULT_MAX_WIDTH


def test_build_thumbnail_rejects_non_image() -> None:
    from app.modules.safety.service.attachment_thumbnail import build_thumbnail

    assert build_thumbnail(b"plain text", "note.txt", 200, 200) is None


async def test_attachment_thumbnail_validates_token_ownership(monkeypatch) -> None:
    from app.modules.safety.service import attachment_thumbnail
    from app.platform.integrations.feishu.attachment_cache import AttachmentCache

    called: list[tuple[str, str]] = []

    async def _fake_fetch(
        _db, page_key, record_id, field_name, file_token, table_id=None
    ):
        called.append((record_id, file_token))
        return _png_bytes(), "image/png", "photo.png"

    monkeypatch.setattr(
        attachment_thumbnail, "fetch_page_table_attachment", _fake_fetch
    )
    # 禁用磁盘/内存缓存：缩略图缓存跨测试持久化，命中会让回源断言落空
    monkeypatch.setattr(
        attachment_thumbnail,
        "get_attachment_cache",
        lambda: AttachmentCache(
            enabled=False,
            cache_dir="",
            max_memory_mb=0,
            max_disk_mb=0,
            ttl_seconds=0,
        ),
    )
    db = _FakeSession(_config())

    result = await attachment_thumbnail.get_page_table_attachment_thumbnail(
        db, PAGE_KEY, "rec-1", "照片", "tok-1"
    )

    # 缩略图回源复用记录附件读取：token 归属校验因此对缩略图同样生效
    assert called == [("rec-1", "tok-1")]
    assert result is not None
    content, content_type, filename = result
    assert content_type == "image/jpeg"
    assert filename == "photo.jpg"
    assert content[:2] == b"\xff\xd8"


# ── 覆盖补强：辅助分支与外部依赖失败路径 ──


def test_ordinal_to_cn_covers_number_shapes() -> None:
    assert page_table._ordinal_to_cn("1") == "一"
    assert page_table._ordinal_to_cn("10") == "十"
    assert page_table._ordinal_to_cn("11") == "十一"
    assert page_table._ordinal_to_cn("21") == "二十一"
    assert page_table._ordinal_to_cn("30") == "三十"
    # 已是中文数字：原样返回
    assert page_table._ordinal_to_cn("二") == "二"
    assert page_table._ordinal_to_cn("十二") == "十二"
    # 非数字 / 非正数：原样返回
    assert page_table._ordinal_to_cn("A3") == "A3"
    assert page_table._ordinal_to_cn("0") == "0"
    assert page_table._ordinal_to_cn("-2") == "-2"


@pytest.mark.anyio
async def test_ai_classify_workshops_branches(monkeypatch) -> None:
    from app.core.llm import llm_client

    # 空输入直接返回空
    assert await page_table._ai_classify_workshops([], ["一车间"]) == {}
    assert await page_table._ai_classify_workshops(["污水车间"], []) == {}

    async def _boom(*args: object, **kwargs: object) -> object:
        raise RuntimeError("LLM 挂了")

    monkeypatch.setattr(llm_client, "chat_json", _boom)
    assert await page_table._ai_classify_workshops(["污水车间"], ["一车间"]) == {}

    async def _bad_structure(*args: object, **kwargs: object) -> object:
        return {"results": "不是列表"}

    monkeypatch.setattr(llm_client, "chat_json", _bad_structure)
    assert await page_table._ai_classify_workshops(["污水车间"], ["一车间"]) == {}

    async def _ok(*args: object, **kwargs: object) -> object:
        return {
            "results": [
                {"序号": 0, "车间": "一车间"},
                {"序号": 1, "车间": "不在清单里的车间"},  # 不在白名单 → 忽略
                {"序号": 1, "车间": "未分类"},  # 明确未分类 → 忽略
                {"序号": 9, "车间": "一车间"},  # 越界序号 → 忽略
                {"序号": "x", "车间": "一车间"},  # 序号类型错 → 忽略
                "非字典项",
            ]
        }

    monkeypatch.setattr(llm_client, "chat_json", _ok)
    mapping = await page_table._ai_classify_workshops(
        ["污水车间", "厂区东南角"], ["一车间", "二车间"]
    )
    assert mapping == {"污水车间": "一车间"}


class _RaisingSession:
    """execute 直接抛配置表缺失的数据库错误。"""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def execute(self, *args: object, **kwargs: object) -> object:
        raise self._exc


@pytest.mark.anyio
async def test_config_table_missing_becomes_actionable_error(monkeypatch) -> None:

    missing = OperationalError(
        "statement",
        {},
        Exception('relation "safety.page_feishu_configs" does not exist'),
    )
    monkeypatch.setattr(
        page_table, "SafetyBitableClient", lambda **kwargs: _FakeClient()
    )
    db = _RaisingSession(missing)

    for call in (
        lambda: page_table.list_page_table_records(db, PAGE_KEY),
        lambda: page_table.test_page_feishu_config(db, PAGE_KEY),
    ):
        with pytest.raises(AppException, match="数据表未创建"):
            await call()

    # 其它数据库错误原样抛出
    other = OperationalError("statement", {}, Exception("connection refused"))
    with pytest.raises(OperationalError):
        await page_table.list_page_table_records(_RaisingSession(other), PAGE_KEY)


def test_is_config_table_missing_requires_table_name_in_message() -> None:
    hit = OperationalError(
        "s", {}, Exception('relation "safety.page_feishu_configs" does not exist')
    )
    assert page_table._is_config_table_missing(hit) is True
    miss = OperationalError("s", {}, Exception("connection refused"))
    assert page_table._is_config_table_missing(miss) is False


@pytest.mark.anyio
async def test_field_schema_cache_invalid_json_falls_back_to_live_read(
    monkeypatch,
) -> None:
    _install_client(monkeypatch, _FakeClient(rows=[]))
    db = _FakeSession(_config())
    # 缓存里是坏 JSON：忽略缓存，改为实时读取字段
    monkeypatch.setattr(page_table, "cache_get", AsyncMock(return_value="not-json"))

    result = await page_table.list_page_table_records(db, PAGE_KEY)

    assert [column.name for column in result.columns]  # 实际读到了字段定义


@pytest.mark.anyio
async def test_fetch_attachment_surfaces_download_failure(monkeypatch) -> None:
    _install_client(
        monkeypatch,
        _FakeClient(
            record_fields={
                "照片": [
                    {
                        "file_token": "tok-1",
                        "name": "a.jpg",
                        "size": 1,
                        "type": "image/jpeg",
                    }
                ]
            },
            tmp_download=None,
            download=None,  # 下载失败
        ),
    )
    db = _FakeSession(_config())

    with pytest.raises(AppException, match="下载飞书附件失败"):
        await page_table.fetch_page_table_attachment(
            db, PAGE_KEY, "rec-1", "照片", "tok-1"
        )


@pytest.mark.anyio
async def test_resolve_page_feishu_url_parses_base_and_wiki_links(monkeypatch) -> None:
    # /base/ 链接：取出 app_token/table/view 并列出子表
    fake = _FakeClient()
    fake.list_tables = AsyncMock(
        return_value=[{"table_id": "tblX", "name": "数据表"}, {"name": "缺 id"}]
    )
    monkeypatch.setattr(page_table, "SafetyBitableClient", lambda **kwargs: fake)

    result = await page_table.resolve_page_feishu_url(
        object(),
        "https://example.feishu.cn/base/bascnABC?table=tblX&view=vew1",
    )
    assert result.app_token == "bascnABC"
    assert result.table_id == "tblX"
    assert result.view_id == "vew1"
    assert result.is_wiki is False
    assert [table.table_id for table in result.tables] == ["tblX"]

    # 空链接 → 400
    with pytest.raises(AppException, match="请填写多维表格链接"):
        await page_table.resolve_page_feishu_url(object(), "   ")

    # 没有 app_token 的链接 → 400
    with pytest.raises(AppException, match="app_token"):
        await page_table.resolve_page_feishu_url(object(), "https://example.feishu.cn/base/")

    # wiki 链接需要先配置应用凭证（运行时配置为 None 时不触库/缓存）
    async def _none_runtime_config():
        return None

    monkeypatch.setattr(
        page_table, "load_safety_feishu_runtime_config", _none_runtime_config
    )
    with pytest.raises(AppException, match="知识库链接"):
        await page_table.resolve_page_feishu_url(
            object(), "https://example.feishu.cn/wiki/wikcnABC?table=tblX"
        )

    # 链接缺 table/view 参数：解析为 None（parse_qs 取值分支）
    no_param = await page_table.resolve_page_feishu_url(
        object(), "https://example.feishu.cn/base/bascnOnly"
    )
    assert no_param.app_token == "bascnOnly"
    assert no_param.table_id is None and no_param.view_id is None

    # wiki 链接 + 凭证：经知识库节点解析出 app_token
    from app.modules.safety.feishu.runtime_config import SafetyFeishuRuntimeConfig

    async def _fake_resolve(**kwargs: object) -> str:
        return "bascnFromWiki"

    async def _fake_runtime_config():
        return SafetyFeishuRuntimeConfig(
            app_id="cli_x",
            app_secret="s",
            bitable_app_token="",
            bitable_hazard_table_id="",
        )

    from app.platform.integrations.feishu import utils as feishu_utils

    monkeypatch.setattr(feishu_utils, "resolve_wiki_bitable_app_token", _fake_resolve)
    monkeypatch.setattr(
        page_table, "load_safety_feishu_runtime_config", _fake_runtime_config
    )
    wiki_result = await page_table.resolve_page_feishu_url(
        object(), "https://example.feishu.cn/wiki/wikcnABC?table=tblW"
    )
    assert wiki_result.is_wiki is True
    assert wiki_result.app_token == "bascnFromWiki"
    assert wiki_result.table_id == "tblW"


# ── 部门继承（父记录值下放，仅展示与统计） ──


def _ledger_rows() -> list[dict]:
    """公司总台账形态：父记录带部门，子记录部门为空。"""
    return [
        {
            "record_id": "parent-1",
            "fields": {"车间/位置": [{"text": "201一车间"}], "父记录": None},
        },
        {
            "record_id": "child-1",
            "fields": {
                "车间/位置": None,
                "父记录": {"link_record_ids": ["parent-1"]},
                "整改情况": "未整改",
            },
        },
        {
            "record_id": "child-2",
            "fields": {
                "车间/位置": [{"text": "203车间"}],  # 自带部门：不覆盖
                "父记录": {"link_record_ids": ["parent-1"]},
            },
        },
        {
            "record_id": "orphan-1",
            "fields": {"车间/位置": None, "父记录": None},
        },
    ]


def test_resolve_dept_inheritance_fills_children_from_parent() -> None:
    schema = page_table.build_field_schema(_FIELDS)
    dept_map = page_table._resolve_dept_inheritance(schema, _ledger_rows())

    assert dept_map["parent-1"] == "201一车间"
    assert dept_map["child-1"] == "201一车间"  # 继承
    assert dept_map["child-2"] == "203车间"  # 自带值优先
    assert "orphan-1" not in dept_map  # 无父也无部门：不造值


def test_resolve_dept_inheritance_two_level_chain() -> None:
    """父记录自身也靠继承（孙记录场景）：两轮迭代收敛。"""
    rows = [
        {"record_id": "top", "fields": {"车间/位置": [{"text": "103车间"}]}},
        {
            "record_id": "mid",
            "fields": {
                "车间/位置": None,
                "父记录": {"link_record_ids": ["top"]},
            },
        },
        {
            "record_id": "leaf",
            "fields": {
                "车间/位置": None,
                "父记录": {"link_record_ids": ["mid"]},
            },
        },
    ]
    schema = page_table.build_field_schema(_FIELDS)
    dept_map = page_table._resolve_dept_inheritance(schema, rows)

    assert dept_map["mid"] == "103车间"
    assert dept_map["leaf"] == "103车间"


def test_resolve_dept_inheritance_without_dept_field() -> None:
    fields = [f for f in _FIELDS if f["field_name"] != "车间/位置"]
    schema = page_table.build_field_schema(fields)
    assert page_table._resolve_dept_inheritance(schema, _ledger_rows()) == {}


async def test_list_records_applies_dept_inheritance(monkeypatch) -> None:
    _install_client(monkeypatch, _FakeClient(rows=_ledger_rows()))
    db = _FakeSession(_config())

    result = await page_table.list_page_table_records(
        db, PAGE_KEY, page=1, page_size=10
    )

    by_id = {record.record_id: record.fields for record in result.records}
    assert by_id["child-1"]["车间/位置"] == "201一车间"
    assert by_id["child-2"]["车间/位置"] == "203车间"
    assert "车间/位置" not in by_id["orphan-1"] or not by_id["orphan-1"]["车间/位置"]


async def test_stats_count_inherited_dept(monkeypatch) -> None:
    _install_client(monkeypatch, _FakeClient(rows=_ledger_rows()))
    db = _FakeSession(_config())

    result = await page_table.get_page_table_stats(
        db, PAGE_KEY, group_by=["车间/位置"]
    )

    buckets = {b.key: b.count for b in result.groups[0].buckets}
    # child-1 继承计入 201一车间；orphan 无部门计入（未填写）
    assert buckets["201一车间"] == 2
    assert buckets["203车间"] == 1
    assert buckets["（未填写）"] == 1


def test_link_field_decodes_to_none_not_dict_garbage() -> None:
    """link 字段（type 18）是结构对象：解码为 None 而不是 str(dict) 垃圾串。"""
    from app.modules.safety.feishu.field_codec import build_field_schema, decode_value

    schema = {f.name: f for f in build_field_schema(_FIELDS)}
    value = decode_value(
        schema["父记录"], {"link_record_ids": ["parent-1"]}
    )
    assert value is None


# ── 多子表页签（一页多 Tab + 跨表聚合） ──

_SUB_FIELDS = [
    {"field_id": "sf1", "field_name": "部门/车间", "type": 1},
    {"field_id": "sf2", "field_name": "隐患内容", "type": 1},
    {
        "field_id": "sf3",
        "field_name": "关闭状态",
        "type": 3,
        "property": {"options": [{"name": "已关闭"}, {"name": "未关闭"}]},
    },
    {"field_id": "sf4", "field_name": "检查内容", "type": 1},  # 文本型检查内容
]


class _FakeMultiClient:
    """按 table_id 返回不同 schema/记录的假客户端。"""

    def __init__(self, schemas: dict[str, list[dict]], rows: dict[str, list[dict]]):
        self.schemas = schemas
        self.rows = rows
        self.updates: list[tuple[str, dict]] = []

    async def list_fields(self, table_id=None):
        return self.schemas.get(table_id, [])

    async def search_records_with_result(self, table_id=None, **kwargs):
        return self.rows.get(table_id, []), None

    async def get_record(self, record_id, table_id=None, **kwargs):
        for row in self.rows.get(table_id or "", []):
            if row.get("record_id") == record_id:
                return row.get("fields") or {}
        return {}

    async def update_record_with_result(self, record_id, fields, table_id=None):
        self.updates.append((record_id, fields))
        return True, None

    async def upload_media(self, file_bytes, file_name, parent_type="bitable_file"):
        return f"tok-{file_name}"


def _multi_install(monkeypatch, client):
    monkeypatch.setattr(
        page_table, "SafetyBitableClient", lambda **kwargs: client
    )
    monkeypatch.setattr(page_table, "cache_get", AsyncMock(return_value=None))
    monkeypatch.setattr(page_table, "cache_set", AsyncMock(return_value=None))
    monkeypatch.setattr(page_table, "cache_delete", AsyncMock(return_value=None))
    monkeypatch.setattr(page_table, "record_audit_log", AsyncMock(return_value=None))
    monkeypatch.setattr(
        page_table, "_load_classifications", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        page_table, "_save_classifications", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        page_table, "_ai_classify_workshops", AsyncMock(return_value={})
    )
    return client


def _multi_binding(**overrides):
    values = dict(
        page_key=PAGE_KEY,
        app_token="bascnMulti",
        table_id="tblMain",
        hidden_field_names=["父记录"],
        is_enabled=True,
        is_mirrored=False,
        sub_tables=[
            {"table_id": "tblSub", "tab_name": "2024年公司级检查"},
        ],
    )
    values.update(overrides)
    return SafetyPageFeishuConfig(**values)


async def test_list_records_selects_sub_table(monkeypatch) -> None:
    """table_id 指定子表时返回该子表的列与记录；未知子表 404。"""
    schemas = {
        "tblMain": _FIELDS,
        "tblSub": _SUB_FIELDS,
    }
    rows = {
        "tblMain": [
            {"record_id": "m1", "fields": {"部门/车间": [{"text": "201一车间"}]}}
        ],
        "tblSub": [
            {"record_id": "s1", "fields": {"部门/车间": [{"text": "103车间"}]}}
        ],
    }
    _multi_install(monkeypatch, _FakeMultiClient(schemas, rows))
    db = _FakeSession(_multi_binding())

    sub = await page_table.list_page_table_records(
        db, PAGE_KEY, page=1, page_size=10, table_id="tblSub"
    )
    assert [record.record_id for record in sub.records] == ["s1"]
    assert "父记录" not in {c.name for c in sub.columns}

    with pytest.raises(AppException) as excinfo:
        await page_table.list_page_table_records(
            db, PAGE_KEY, page=1, page_size=10, table_id="tblUnknown"
        )
    assert excinfo.value.status_code == 404


async def test_aggregate_stats_cross_sub_tables(monkeypatch) -> None:
    """不传 table_id 时跨全部子表聚合：值分组合并计数、日期分组只取日期型子表。"""
    # 主表构造为「检查内容=日期型」，模拟 2026 公司级检查；
    # 子表为「检查内容=文本型」，模拟 2024/2025 年检查（同名字段不同类型）。
    main_fields = [f for f in _FIELDS if f["field_name"] != "值班日期"] + [
        {"field_id": "fldX", "field_name": "检查内容", "type": 5}
    ]
    schemas = {"tblMain": main_fields, "tblSub": _SUB_FIELDS}
    rows = {
        "tblMain": [
            {
                "record_id": "m1",
                "fields": {
                    "车间/位置": [{"text": "201一车间"}],
                    "检查内容": 1791561600000,
                    "整改情况": "未整改",
                },
            }
        ],
        "tblSub": [
            {
                "record_id": "s1",
                "fields": {
                    "部门/车间": [{"text": "103车间"}],
                    "检查内容": [{"text": "2024年10月18日消防安全检查台账"}],
                    "关闭状态": "未关闭",
                },
            }
        ],
    }
    _multi_install(monkeypatch, _FakeMultiClient(schemas, rows))
    db = _FakeSession(_multi_binding())

    result = await page_table.get_page_table_stats(
        db,
        PAGE_KEY,
        group_by=["检查内容", "关闭状态", "部门/车间", "车间/位置", "整改情况"],
    )

    assert result.total == 2  # 两张子表各 1 条
    by_field = {g.field: {b.key: b.count for b in g.buckets} for g in result.groups}
    # 检查内容：主表日期型→月份桶；子表文本型→不参与月份分组
    check_group = next(g for g in result.groups if g.field == "检查内容")
    assert check_group.kind == "date"
    assert by_field["检查内容"] == {"2026-10": 1}
    # 各自的位置字段名独立分组（实际 9 张检查子表同名「部门/车间」会合并）
    assert by_field["车间/位置"] == {"201一车间": 1}
    assert by_field["部门/车间"] == {"103车间": 1}
    assert by_field["整改情况"] == {"未整改": 1}
    assert by_field["关闭状态"] == {"未关闭": 1}


async def test_per_table_stats_isolated(monkeypatch) -> None:
    """传 table_id 时只聚合该子表。"""
    schemas = {"tblMain": _FIELDS, "tblSub": _SUB_FIELDS}
    rows = {
        "tblMain": [
            {"record_id": "m1", "fields": {"车间/位置": [{"text": "201一车间"}]}}
        ],
        "tblSub": [
            {"record_id": "s1", "fields": {"部门/车间": [{"text": "103车间"}]}}
        ],
    }
    _multi_install(monkeypatch, _FakeMultiClient(schemas, rows))
    db = _FakeSession(_multi_binding())

    result = await page_table.get_page_table_stats(
        db, PAGE_KEY, group_by=["部门/车间"], table_id="tblSub"
    )
    assert result.total == 1


async def test_update_record_targets_sub_table(monkeypatch) -> None:
    """回写带 table_id 时按该子表 schema 编码并写回该表。"""
    schemas = {"tblMain": _FIELDS, "tblSub": _SUB_FIELDS}
    rows = {"tblMain": [], "tblSub": []}
    client = _multi_install(monkeypatch, _FakeMultiClient(schemas, rows))
    db = _FakeSession(_multi_binding())

    await page_table.update_page_table_record(
        db,
        PAGE_KEY,
        "s1",
        {"隐患内容": "新内容", "关闭状态": "未关闭"},
        table_id="tblSub",
    )
    assert client.updates == [("s1", {"隐患内容": "新内容", "关闭状态": "未关闭"})]


async def test_list_tabs_returns_bound_tables(monkeypatch) -> None:
    """页签清单：主绑定在前 + sub_tables 顺序，主表标记 is_primary。"""
    class _CountSession(_FakeSession):
        def __init__(self, binding):
            super().__init__(binding)

    _multi_install(monkeypatch, _FakeMultiClient({}, {}))
    db = _CountSession(_multi_binding())

    tabs = await page_table.list_page_table_tabs(db, PAGE_KEY)

    assert [t.table_id for t in tabs] == ["tblMain", "tblSub"]
    assert tabs[0].is_primary is True and tabs[0].tab_name == "24小时值班隐患"
    assert tabs[1].is_primary is False and tabs[1].tab_name == "2024年公司级检查"


# ── 新建记录（写透飞书 + 镜像） ──


async def test_create_record_encodes_writes_and_returns_decoded(monkeypatch) -> None:
    client = _install_client(
        monkeypatch,
        _FakeClient(
            create_result=("rec-new", None),
            record_fields={
                "记录编号": [{"text": "XH-2026-001"}],
                "整改情况": "未整改",
            },
        ),
    )
    db = _FakeSession(_config())

    result = await page_table.create_page_table_record(
        db,
        PAGE_KEY,
        {"记录编号": "XH-2026-001", "整改情况": "未整改", "值班日期": None},
    )

    # 主字段文本按纯字符串编码，空值字段不写入
    assert client.creates == [{"记录编号": "XH-2026-001", "整改情况": "未整改"}]
    assert result.record_id == "rec-new"
    assert result.fields["记录编号"] == "XH-2026-001"


async def test_create_record_surfaces_feishu_error(monkeypatch) -> None:
    client = _install_client(
        monkeypatch,
        _FakeClient(create_result=(None, "字段权限不足")),
    )
    db = _FakeSession(_config())

    with pytest.raises(AppException) as excinfo:
        await page_table.create_page_table_record(
            db, PAGE_KEY, {"整改情况": "未整改"}
        )
    assert excinfo.value.status_code == 502
    assert "字段权限不足" in excinfo.value.message
    assert client.creates


async def test_create_record_rejects_all_empty_values(monkeypatch) -> None:
    client = _install_client(monkeypatch, _FakeClient())
    db = _FakeSession(_config())

    with pytest.raises(AppException) as excinfo:
        await page_table.create_page_table_record(
            db, PAGE_KEY, {"记录编号": None, "整改情况": None}
        )
    assert excinfo.value.status_code == 400
    assert client.creates == []
