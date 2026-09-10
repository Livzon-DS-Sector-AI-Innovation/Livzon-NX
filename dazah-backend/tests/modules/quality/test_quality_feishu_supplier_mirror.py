"""供应商资质镜像回拉服务单元测试（不触库、不连真实飞书）。"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import AppException
from app.modules.quality.service import quality_feishu_supplier_mirror as mirror
from app.modules.quality.service.quality_feishu_supplier_mirror import (
    _compute_watermark,
    _record_is_newer,
    map_record_to_mirror_fields,
    pull_supplier_qualification_mirror,
)
from app.modules.quality.service.quality_feishu_sync import (
    QualityFeishuEntityRuntimeConfig,
)


def _entity() -> QualityFeishuEntityRuntimeConfig:
    return QualityFeishuEntityRuntimeConfig(
        app_token="app-token",
        table_id="table-id",
        is_enabled=True,
        enable_push_to_feishu=True,
        enable_pull_from_feishu=True,
        field_mappings={},
    )


def _record(fields: dict[str, Any], record_id: str = "rec-1") -> dict[str, Any]:
    return {
        "record_id": record_id,
        "created_time": 1753000000000,
        "last_modified_time": 1753100000000,
        "fields": fields,
    }


def test_map_record_to_mirror_fields_converts_cn_columns() -> None:
    mapped = map_record_to_mirror_fields(
        _record(
            {
                "供应商名称": "供应商A",
                "物料名称": "原料A",
                "物料类型": "原料",
                "资质名称": "营业执照",
                "资质文件": "license.pdf",
                "是否完成": "是",
                "截止日期": 1754006400000,
                "负责人": [{"name": "张三"}, {"name": "李四"}],
                "备注": "重点供应商",
                "到期状态": "正常",
            }
        ),
        _entity(),
    )
    assert mapped["supplier_name"] == "供应商A"
    assert mapped["material_name"] == "原料A"
    assert mapped["is_completed"] is True
    assert mapped["responsible_person"] == "张三、李四"
    assert mapped["expiry_status"] == "正常"
    deadline = datetime.fromisoformat(str(mapped["deadline"]))
    assert deadline.year == 2025
    assert isinstance(mapped["source_updated_at"], datetime)
    assert isinstance(mapped["source_created_at"], datetime)


def test_map_record_handles_checkbox_bool_and_empty_fields() -> None:
    mapped = map_record_to_mirror_fields(
        _record({"供应商名称": "B", "是否完成": True}),
        _entity(),
    )
    assert mapped["is_completed"] is True
    assert mapped["material_name"] is None
    assert mapped["deadline"] is None
    assert mapped["responsible_person"] is None
    assert mapped["responsible_users"] is None
    assert mapped["groups"] is None


def test_map_record_captures_responsible_users_and_groups() -> None:
    mapped = map_record_to_mirror_fields(
        _record(
            {
                "供应商名称": "C",
                "负责人": [
                    {"id": "ou_abc", "name": "甄宁宁", "email": "znn@livzon.cn"},
                    {"id": "ou_def", "name": "陈连平", "email": "clp@livzon.cn"},
                ],
                "群组": [
                    {
                        "id": "oc_chat1",
                        "name": "供应商资质沟通群",
                        "avatar_url": "https://example.com/a.webp",
                    }
                ],
            }
        ),
        _entity(),
    )
    # 负责人：姓名串保持（兼容搜索/导出）+ 成员对象列表供写回（email 用于头像关联）
    assert mapped["responsible_person"] == "甄宁宁、陈连平"
    assert mapped["responsible_users"] == [
        {"id": "ou_abc", "name": "甄宁宁", "email": "znn@livzon.cn"},
        {"id": "ou_def", "name": "陈连平", "email": "clp@livzon.cn"},
    ]
    # 群组：只读展示（id/name/avatar_url）
    assert mapped["groups"] == [
        {"id": "oc_chat1", "name": "供应商资质沟通群", "avatar_url": "https://example.com/a.webp"}
    ]


def test_compute_watermark_and_newer_gate() -> None:
    assert _compute_watermark({}) is None
    ts_a = datetime(2026, 9, 1, tzinfo=UTC)
    ts_b = datetime(2026, 9, 6, tzinfo=UTC)
    assert _compute_watermark({"a": ts_a, "b": ts_b, "c": None}) == ts_b

    newer_ms = int(datetime(2026, 9, 7, tzinfo=UTC).timestamp() * 1000)
    assert _record_is_newer({"last_modified_time": newer_ms}, ts_b) is True
    older_ms = int(datetime(2026, 8, 1, tzinfo=UTC).timestamp() * 1000)
    assert _record_is_newer({"last_modified_time": older_ms}, ts_b) is False
    # 缺自动字段的记录保守放行（宁可多镜像不误漏）
    assert _record_is_newer({}, ts_b) is True
    assert _record_is_newer({"last_modified_time": older_ms}, None) is True


@pytest.mark.parametrize(
    ("value", "expected"),
    [("true", True), ("是", True), ("已确认", True), ("1", True), ("否", False)],
)
def test_map_checkbox_semantics(value: str, expected: bool) -> None:
    mapped = map_record_to_mirror_fields(
        _record({"供应商名称": "X", "是否完成": value}), _entity()
    )
    assert mapped["is_completed"] is expected


# ── 回拉编排（fake 飞书通道与 fake session，不连真实外部服务） ──────────────


class _FakeHTTP:
    """替代 FeishuClient.request：GET 全量与 POST search 都返回同一批记录。"""

    def __init__(self, records: list[dict[str, Any]], *, fail: bool = False) -> None:
        self.records = records
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Any = None,
        timeout: Any = None,
    ) -> dict[str, Any]:
        self.calls.append((method, path))
        if self.fail:
            raise RuntimeError("simulated feishu outage")
        return {"items": self.records, "has_more": False, "total": len(self.records)}


class _Nested:
    async def __aenter__(self) -> _Nested:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False


class _Result:
    def __init__(self, rows: list[Any] | None = None, scalar: Any = None) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def all(self) -> list[Any]:
        return self._rows

    def scalars(self) -> _Result:
        return self

    def scalar_one_or_none(self) -> Any:
        return self._scalar


def _fake_row(record_id: str, updated_at: datetime | None) -> SimpleNamespace:
    return SimpleNamespace(
        feishu_record_id=record_id,
        source_updated_at=updated_at,
        is_deleted=False,
    )


class _FakeDB:
    """满足 pull 编排所需的最小 AsyncSession 接口。"""

    def __init__(
        self,
        *,
        existing: list[Any] | None = None,
        lookup_rows: dict[str, Any] | None = None,
        entity_row: Any = None,
    ) -> None:
        self.existing = existing or []
        self.lookup_rows = lookup_rows or {}
        self.entity_row = entity_row
        self.added: list[Any] = []
        self.commits = 0

    def begin_nested(self) -> _Nested:
        return _Nested()

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def execute(self, stmt: Any) -> _Result:
        sql = str(stmt)
        if "quality_feishu_entity_settings" in sql:
            return _Result(scalar=self.entity_row)
        if "supplier_qualification_records" in sql:
            # 水位探测只 select 两列（前缀精确区分整行 ORM select）
            if sql.startswith(
                "SELECT quality.supplier_qualification_records.feishu_record_id,"
            ):
                return _Result(rows=self.existing)
            if " IN (" in sql:
                return _Result(rows=self.existing)
            params = stmt.compile().params
            for name, value in params.items():
                if isinstance(value, str) and value in self.lookup_rows:
                    return _Result(scalar=self.lookup_rows[value])
            return _Result(scalar=None)
        return _Result()


_MOD_MS = int(datetime(2026, 9, 1, tzinfo=UTC).timestamp() * 1000)


@pytest.mark.anyio
async def test_pull_full_creates_rows_and_marks_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = [
        _record({"供应商名称": "A", "是否完成": False}, "rec-1"),
        _record({"供应商名称": "B", "是否完成": True}, "rec-2"),
    ]
    records[0]["last_modified_time"] = _MOD_MS
    records[1]["last_modified_time"] = _MOD_MS + 1000
    http = _FakeHTTP(records)
    monkeypatch.setattr(
        mirror,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(_runtime(), _entity())),
    )
    monkeypatch.setattr(
        mirror,
        "BitableClient",
        lambda **kw: SimpleNamespace(app_token="app-token", client=http),
    )
    entity_row = SimpleNamespace(
        last_sync_status=None, last_sync_error=None, last_synced_at=None
    )
    db = _FakeDB(entity_row=entity_row)

    result = await pull_supplier_qualification_mirror(db, full=True)

    assert result == {"synced": 2, "failed": 0, "removed": 0, "total": 2}
    assert len(db.added) == 2
    assert {row.feishu_record_id for row in db.added} == {"rec-1", "rec-2"}
    assert entity_row.last_sync_status == "success"
    # 全量轮必须走 GET /records（search 无 filter 翻页失效的实测约束）
    assert http.calls[0][0] == "GET"


@pytest.mark.anyio
async def test_pull_incremental_skips_below_watermark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale = datetime(2026, 9, 5, tzinfo=UTC)
    existing_row = _fake_row("rec-1", stale)
    records = [
        _record({"供应商名称": "A"}, "rec-1"),
        _record({"供应商名称": "C"}, "rec-3"),
    ]
    # rec-1 修改时间恰等于本地水位（upsert 时按 <= 跳过）；rec-3 高于水位
    records[0]["last_modified_time"] = int(stale.timestamp() * 1000)
    records[1]["last_modified_time"] = int(stale.timestamp() * 1000) + 5000
    http = _FakeHTTP(records)
    monkeypatch.setattr(
        mirror,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(_runtime(), _entity())),
    )
    monkeypatch.setattr(
        mirror,
        "BitableClient",
        lambda **kw: SimpleNamespace(app_token="app-token", client=http),
    )
    db = _FakeDB(existing=[existing_row], entity_row=None)

    result = await pull_supplier_qualification_mirror(db, full=False)

    # rec-1 水位以下跳过；rec-3 为新行（缺水位字段保守放行）
    assert result["synced"] == 1
    assert result["removed"] == 0
    assert db.added and db.added[0].feishu_record_id == "rec-3"
    # 增量轮同样走 GET /records（search 的 sort/filter 不支持自动字段，
    # 实测 InvalidSort；靠客户端水位过滤取增量）
    assert http.calls[0][0] == "GET"


@pytest.mark.anyio
async def test_pull_full_soft_deletes_stale_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gone = _fake_row("rec-gone", datetime(2026, 9, 1, tzinfo=UTC))
    http = _FakeHTTP([_record({"供应商名称": "A"}, "rec-1")])
    monkeypatch.setattr(
        mirror,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(_runtime(), _entity())),
    )
    monkeypatch.setattr(
        mirror,
        "BitableClient",
        lambda **kw: SimpleNamespace(app_token="app-token", client=http),
    )
    db = _FakeDB(existing=[gone], entity_row=None)

    result = await pull_supplier_qualification_mirror(db, full=True)

    assert result["removed"] == 1
    assert gone.is_deleted is True


@pytest.mark.anyio
async def test_pull_feishu_outage_maps_to_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = _FakeHTTP([], fail=True)
    entity_row = SimpleNamespace(
        last_sync_status=None, last_sync_error=None, last_synced_at=None
    )
    monkeypatch.setattr(
        mirror,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(_runtime(), _entity())),
    )
    monkeypatch.setattr(
        mirror,
        "BitableClient",
        lambda **kw: SimpleNamespace(app_token="app-token", client=http),
    )
    db = _FakeDB(entity_row=entity_row)

    with pytest.raises(AppException) as excinfo:
        await pull_supplier_qualification_mirror(db, full=True)

    assert excinfo.value.status_code == 503
    assert entity_row.last_sync_status == "failed"
    assert entity_row.last_sync_error


def _runtime() -> SimpleNamespace:
    return SimpleNamespace(app_id="cli-x", app_secret="secret-x")


@pytest.mark.anyio
async def test_mirror_generators_gate_on_pull_switch() -> None:
    """定时回拉仅在实体启用且回拉开关打开时调度。"""
    from app.modules.quality.scheduled import (
        SupplierQualificationMirrorFullSyncGenerator,
        SupplierQualificationMirrorSyncGenerator,
    )

    pull_off = SimpleNamespace(is_enabled=True, enable_pull_from_feishu=False)
    pull_on = SimpleNamespace(is_enabled=True, enable_pull_from_feishu=True)

    assert (
        await SupplierQualificationMirrorSyncGenerator().find_due(
            _FakeDB(entity_row=pull_off)
        )
        == []
    )
    assert (
        await SupplierQualificationMirrorFullSyncGenerator().find_due(
            _FakeDB(entity_row=pull_off)
        )
        == []
    )
    assert (
        await SupplierQualificationMirrorSyncGenerator().find_due(
            _FakeDB(entity_row=pull_on)
        )
        == ["supplier_qualification"]
    )
    # 无配置行同样不调度
    assert (
        await SupplierQualificationMirrorSyncGenerator().find_due(
            _FakeDB(entity_row=None)
        )
        == []
    )
