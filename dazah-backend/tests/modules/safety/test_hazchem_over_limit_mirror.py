"""危化品统计表镜像超储计算测试：数值解析、行标注、绑定配置校验与镜像口径。

沿用 test_page_table_service 的 _FakeSession 模式：不触真实数据库/Redis/飞书。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import AppException
from app.modules.safety.models import SafetyPageFeishuConfig
from app.modules.safety.page_tables import (
    HAZCHEM_PAGE_KEY,
    PAGE_TABLE_DEFINITIONS,
    get_page_table,
)
from app.modules.safety.schemas.page_table import (
    PageTableRecord,
    UpdatePageFeishuConfigRequest,
)
from app.modules.safety.service import page_table
from app.modules.safety.service.page_table import (
    OverLimitFieldConfig as _OverLimitFieldConfig,
)
from app.modules.safety.service.page_table import (
    _annotate_over_limit,
    _over_limit_config,
    _parse_field_number,
    collect_mirror_over_limit_rows,
)


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
        if isinstance(self._value, list):
            return _FakeScalars(self._value)
        return _FakeScalars([self._value])


class _FakeSession:
    def __init__(self, config: SafetyPageFeishuConfig | None = None) -> None:
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


def _patch_service_mocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(page_table, "cache_get", AsyncMock(return_value=None))
    monkeypatch.setattr(page_table, "cache_set", AsyncMock(return_value=None))
    monkeypatch.setattr(page_table, "cache_delete", AsyncMock(return_value=None))
    monkeypatch.setattr(page_table, "record_audit_log", AsyncMock(return_value=None))


def test_hazchem_page_registered() -> None:
    definition = get_page_table(HAZCHEM_PAGE_KEY)
    assert definition is not None
    assert definition.route_path == "/safety/hazchem"
    assert any(item.page_key == HAZCHEM_PAGE_KEY for item in PAGE_TABLE_DEFINITIONS)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (500, 500.0),
        ("500", 500.0),
        ("500kg", 500.0),
        ("1,200.5L", 1200.5),
        ("＜5", 5.0),
        ("１２３", 123.0),
        ("abc", None),
        (None, None),
        ([1, 2], None),
        ({"v": 1}, None),
    ],
)
def test_parse_field_number(value: object, expected: float | None) -> None:
    assert _parse_field_number(value) == expected


def test_over_limit_config_requires_pair() -> None:
    assert _over_limit_config(SafetyPageFeishuConfig(page_key="k")) is None
    only_quantity = SafetyPageFeishuConfig(
        page_key="k", over_limit_quantity_field="存量"
    )
    assert _over_limit_config(only_quantity) is None
    both = SafetyPageFeishuConfig(
        page_key="k",
        over_limit_quantity_field="现有存量",
        over_limit_limit_field="上限",
        over_limit_name_field="品名",
    )
    config = _over_limit_config(both)
    assert config is not None
    assert config.quantity_field == "现有存量"
    assert config.limit_field == "上限"
    assert config.name_field == "品名"


def test_annotate_over_limit_marks_rows() -> None:
    config = _OverLimitFieldConfig(
        quantity_field="存量", limit_field="上限", name_field=None
    )
    records = [
        PageTableRecord(record_id="r1", fields={}),
        PageTableRecord(record_id="r2", fields={}),
        PageTableRecord(record_id="r3", fields={}),
    ]
    source = {
        "r1": {"存量": 120, "上限": 100},
        "r2": {"存量": "80kg", "上限": "100kg"},
        "r3": {"存量": 50, "上限": "未填写"},
    }
    _annotate_over_limit(records, config, source)
    assert records[0].over_limit is True
    assert records[0].over_pct == 20.0
    assert records[1].over_limit is False
    assert records[1].over_pct is None
    assert records[2].over_limit is None


async def test_save_config_over_limit_pair_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_service_mocks(monkeypatch)
    session = _FakeSession(
        SafetyPageFeishuConfig(
            page_key=HAZCHEM_PAGE_KEY,
            app_token="app",
            table_id="tbl",
            is_enabled=True,
            is_mirrored=True,
        )
    )
    with pytest.raises(AppException) as only_quantity:
        await page_table.save_page_feishu_config(
            session,
            HAZCHEM_PAGE_KEY,
            UpdatePageFeishuConfigRequest(over_limit_quantity_field="存量"),
        )
    assert "同时配置" in str(only_quantity.value.message)

    saved = await page_table.save_page_feishu_config(
        session,
        HAZCHEM_PAGE_KEY,
        UpdatePageFeishuConfigRequest(
            over_limit_quantity_field="现有存量",
            over_limit_limit_field="上限",
            over_limit_name_field="品名",
        ),
    )
    assert saved.over_limit_quantity_field == "现有存量"
    assert saved.over_limit_limit_field == "上限"
    assert saved.over_limit_name_field == "品名"

    cleared = await page_table.save_page_feishu_config(
        session,
        HAZCHEM_PAGE_KEY,
        UpdatePageFeishuConfigRequest(
            over_limit_quantity_field=None, over_limit_limit_field=None
        ),
    )
    assert cleared.over_limit_quantity_field is None
    assert cleared.over_limit_limit_field is None


async def test_collect_mirror_rows_unconfigured_returns_none() -> None:
    """未绑定/未配置超储列返回 None（调用方回退本地库存口径）。"""
    assert (
        await collect_mirror_over_limit_rows(_FakeSession(), HAZCHEM_PAGE_KEY) is None
    )
    unbound = _FakeSession(
        SafetyPageFeishuConfig(
            page_key=HAZCHEM_PAGE_KEY,
            app_token="app",
            table_id="tbl",
            over_limit_quantity_field="现有存量",
            over_limit_limit_field="上限",
        )
    )
    unbound.config.is_enabled = False
    assert await collect_mirror_over_limit_rows(unbound, HAZCHEM_PAGE_KEY) is None


async def test_collect_mirror_rows_parses_live_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """配置齐全但未同步镜像时走实时拉取路径并按列解析超储。"""
    session = _FakeSession(
        SafetyPageFeishuConfig(
            page_key=HAZCHEM_PAGE_KEY,
            app_token="app",
            table_id="tbl",
            is_enabled=True,
            is_mirrored=True,
            over_limit_quantity_field="现有存量",
            over_limit_limit_field="上限",
            over_limit_name_field="品名",
        )
    )
    fields = [
        SimpleNamespace(name="品名", kind="text"),
        SimpleNamespace(name="现有存量", kind="number"),
        SimpleNamespace(name="上限", kind="number"),
        SimpleNamespace(name="存放车间", kind="text"),
    ]
    monkeypatch.setattr(
        page_table, "_load_field_schema", AsyncMock(return_value=fields)
    )
    monkeypatch.setattr(
        page_table,
        "_fetch_raw_records",
        AsyncMock(
            return_value=[
                {
                    "record_id": "r1",
                    "fields": {
                        "品名": "丙酮",
                        "现有存量": 120,
                        "上限": 100,
                        "存放车间": "201一车间",
                    },
                },
                {
                    "record_id": "r2",
                    "fields": {
                        "品名": "甲醇",
                        "现有存量": "30kg",
                        "上限": "100kg",
                        "存放车间": "102车间",
                    },
                },
            ]
        ),
    )
    rows = await collect_mirror_over_limit_rows(session, HAZCHEM_PAGE_KEY)
    assert rows is not None
    assert len(rows) == 2
    over = next(row for row in rows if row.record_id == "r1")
    assert over.over_limit is True
    assert over.over_pct == 20.0
    assert over.name == "丙酮"
    assert over.workshop == "201一车间"
    normal = next(row for row in rows if row.record_id == "r2")
    assert normal.over_limit is False
    assert normal.quantity == 30.0


async def test_collect_mirror_rows_feishu_failure_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession(
        SafetyPageFeishuConfig(
            page_key=HAZCHEM_PAGE_KEY,
            app_token="app",
            table_id="tbl",
            is_enabled=True,
            over_limit_quantity_field="现有存量",
            over_limit_limit_field="上限",
        )
    )

    async def _boom(*args: object, **kwargs: object) -> list[object]:
        raise RuntimeError("feishu down")

    monkeypatch.setattr(page_table, "_load_field_schema", _boom)
    assert await collect_mirror_over_limit_rows(session, HAZCHEM_PAGE_KEY) is None
