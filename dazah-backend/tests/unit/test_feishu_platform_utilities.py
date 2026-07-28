"""Unit tests for shared Feishu field, event, Bitable, and sync helpers."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.platform.integrations.feishu import event_client
from app.platform.integrations.feishu import sync as sync_module
from app.platform.integrations.feishu import utils as feishu_utils
from app.platform.integrations.feishu.bitable import (
    BitableClient,
    FeishuBitableSync,
    _to_ms_timestamp,
)
from app.platform.integrations.feishu.fields import (
    extract_attachments,
    extract_email,
    extract_multi_select,
    extract_number,
    extract_person_name,
    extract_single_select,
    extract_text,
    extract_text_or_none,
    ms_to_date,
    ms_to_datetime,
)
from app.platform.integrations.feishu.sync import (
    _is_newly_created,
    _parse_user_record,
    run_sync,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ([{"text": "A"}], "A"),
        ({"text": "B"}, "B"),
        ({"value": [{"text": "C"}]}, "C"),
        ({"value": [7]}, "7"),
        ("D", "D"),
        (None, ""),
    ],
)
def test_extract_text_variants(value, expected) -> None:
    assert extract_text(value) == expected


def test_extract_field_variants() -> None:
    assert extract_text_or_none(" ") == " "
    assert extract_text_or_none(None) is None
    assert extract_number(3) == 3
    assert extract_number({"value": [4]}) == 4
    assert extract_number([5]) == 5
    assert extract_number({}) is None
    assert extract_single_select(6) == "6"
    assert extract_multi_select(["A", 2]) == ["A", "2"]
    assert extract_multi_select(None) == []
    assert extract_multi_select("A") == ["A"]
    assert extract_attachments([{"name": "a"}, "invalid"]) == [{"name": "a"}]
    assert extract_attachments({}) == []
    assert extract_person_name([{"name": "张三"}, {"name": "李四"}]) == "张三, 李四"
    assert extract_email({"text": "a@example.com"}) == "a@example.com"
    assert extract_email({"link": "mailto:b@example.com"}) == "b@example.com"
    assert extract_email("c@example.com") == "c@example.com"


def test_millisecond_conversions() -> None:
    value = 1_767_225_600_000
    assert ms_to_date(value) == date(2026, 1, 1)
    assert ms_to_datetime(value) == datetime(2026, 1, 1, tzinfo=UTC)
    assert ms_to_date(0) is None
    assert ms_to_datetime("invalid") is None
    assert _to_ms_timestamp(date(2026, 1, 1)) == value
    assert _to_ms_timestamp("2026-01-01") == value
    assert _to_ms_timestamp("not-a-date") == "not-a-date"
    assert _to_ms_timestamp(None) == ""
    assert _to_ms_timestamp(datetime(2026, 1, 1)) == value


@pytest.mark.asyncio
async def test_event_registration_and_dispatch_contain_handler_errors() -> None:
    event_type = "ci.event"
    calls: list[dict] = []

    @event_client.on_event(event_type)
    async def success(payload):
        calls.append(payload)

    @event_client.on_event(event_type)
    async def failure(_payload):
        raise RuntimeError("handler failed")

    await event_client._dispatch_event(
        {"header": {"event_type": event_type}, "event": {"value": 1}}
    )
    await event_client._dispatch_event(
        {"type": "event", "event": {"type": event_type, "value": 2}}
    )
    await event_client._dispatch_event({"unexpected": True})
    assert calls == [{"value": 1}, {"type": event_type, "value": 2}]


@pytest.mark.asyncio
async def test_get_ws_url_handles_success_and_failures(monkeypatch) -> None:
    response = SimpleNamespace(
        status_code=200,
        json=lambda: {"code": 0, "data": {"URL": "wss://example"}},
    )
    client = AsyncMock()
    client.post.return_value = response

    class ClientContext:
        async def __aenter__(self):
            return client

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(
        event_client.httpx,
        "AsyncClient",
        lambda **_kwargs: ClientContext(),
    )
    assert await event_client._get_ws_url("id", "secret") == "wss://example"
    response.json = lambda: {"code": 1, "msg": "denied"}
    assert await event_client._get_ws_url("id", "secret") is None
    response.status_code = 500
    assert await event_client._get_ws_url("id", "secret") is None


@pytest.mark.asyncio
async def test_stop_ws_sets_active_stop_event() -> None:
    event_client._stop = __import__("asyncio").Event()
    await event_client.stop_ws()
    assert event_client._stop.is_set()


@pytest.mark.asyncio
async def test_bitable_client_crud_and_pagination() -> None:
    client = BitableClient(app_token="app-token")
    client.client = AsyncMock()
    client.client.request.side_effect = [
        {"items": [{"table_id": "1"}, "bad"], "has_more": True, "page_token": "next"},
        {"items": [{"table_id": "2"}], "has_more": False},
        {"record": {"record_id": "created"}},
        {"record": {"record_id": "updated"}},
        {},
        {"items": [{"field_id": "1"}], "has_more": False},
        {"items": [{"record_id": "1"}]},
    ]

    assert await client.list_tables() == [{"table_id": "1"}, {"table_id": "2"}]
    assert await client.create_record("table", {"name": "A"}) == {
        "record_id": "created"
    }
    assert await client.update_record("table", "record", {"name": "B"}) == {
        "record_id": "updated"
    }
    await client.delete_record("table", "record")
    assert await client.list_fields("table") == [{"field_id": "1"}]
    assert await client.search_records(
        "table",
        filter_str="filter",
        automatic_fields=True,
    ) == [{"record_id": "1"}]
    assert client._path("table", "/records").endswith("/table/records")


@pytest.mark.asyncio
async def test_bitable_client_requires_configuration() -> None:
    client = BitableClient(app_token="")
    client.app_token = ""
    with pytest.raises(RuntimeError, match="app_token"):
        await client.list_tables()
    with pytest.raises(RuntimeError, match="table_id"):
        await client.create_record("", {})
    with pytest.raises(RuntimeError, match="table_id"):
        await client.update_record("", "record", {})
    with pytest.raises(RuntimeError, match="table_id"):
        await client.delete_record("", "record")
    with pytest.raises(RuntimeError, match="table_id"):
        await client.list_fields("")
    with pytest.raises(RuntimeError, match="table_id"):
        await client.search_records("")


@pytest.mark.asyncio
async def test_bitable_pagination_stops_on_missing_next_token() -> None:
    client = BitableClient(app_token="app-token")
    client.client = AsyncMock()
    client.client.request.side_effect = [
        {
            "items": [{"table_id": "table"}],
            "has_more": True,
            "page_token": "",
        },
        {
            "items": [{"field_id": "field"}],
            "has_more": True,
            "page_token": "",
        },
    ]
    assert await client.list_tables() == [{"table_id": "table"}]
    assert await client.list_fields("table") == [{"field_id": "field"}]


@pytest.mark.asyncio
async def test_feishu_bitable_sync_maps_business_records() -> None:
    sync = FeishuBitableSync.__new__(FeishuBitableSync)
    sync.bitable = AsyncMock()
    sync.bitable.app_token = "token"
    sync.department_table = "departments"
    sync.employee_table = "employees"
    sync.offboarding_table = "offboarding"
    sync.approval_table = "approvals"
    sync.bitable.create_record.return_value = {"record_id": "created"}
    sync.bitable.search_records.return_value = [
        {
            "record_id": "record",
            "created_time": "2",
            "fields": {"审批情况": "已完成"},
        }
    ]

    await sync.sync_department_created({"name": "生产", "code": "P"})
    await sync.sync_department_updated({"name": "质量", "code": "Q"})
    await sync.sync_department_deleted("Q")
    await sync.sync_employee_created(
        {
            "employee_number": "E1",
            "name": "张三",
            "phone": "13800000000",
            "hire_date": "2026-01-01",
        }
    )
    await sync.sync_employee_updated({"employee_number": "E1", "name": "李四"})
    await sync.sync_employee_deleted("E1")
    await sync.sync_offboarding_created(
        {
            "employee": {"name": "张三", "employee_number": "E1"},
            "offboarding_date": "2026-01-01",
        }
    )
    await sync.sync_offboarding_updated(
        {
            "_feishu_record_id": "record",
            "employee": {"name": "张三", "employee_number": "E1"},
        }
    )
    await sync.sync_approval_created({"name": "张三", "employee_number": "E1"})
    assert await sync.check_approval_status("E1") == "已完成"
    assert sync.bitable.create_record.await_count == 4
    assert sync.bitable.update_record.await_count == 3
    assert sync.bitable.delete_record.await_count == 2


@pytest.mark.asyncio
async def test_feishu_bitable_sync_guards_and_failure_paths() -> None:
    sync = FeishuBitableSync.__new__(FeishuBitableSync)
    sync.bitable = AsyncMock()
    sync.bitable.app_token = ""
    sync.department_table = ""
    sync.employee_table = ""
    sync.offboarding_table = ""
    sync.approval_table = ""

    await sync.sync_department_created({})
    await sync.sync_department_updated({})
    await sync.sync_department_deleted("")
    await sync.sync_employee_created({})
    await sync.sync_employee_updated({})
    await sync.sync_employee_deleted("")
    await sync.sync_offboarding_created({})
    await sync.sync_offboarding_updated({})
    await sync.sync_approval_created({})
    assert await sync.check_approval_status("E1") is None

    sync.bitable.app_token = "token"
    sync.department_table = "departments"
    sync.employee_table = "employees"
    sync.offboarding_table = "offboarding"
    sync.approval_table = "approvals"
    sync.bitable.search_records.return_value = []
    assert await sync._find_department_record(None) is None
    assert await sync._find_department_record("D1") is None
    assert await sync._find_employee_record(None) is None
    assert await sync._find_employee_record("E1") is None
    assert await sync.check_approval_status("E1") is None

    sync.bitable.create_record.side_effect = RuntimeError("create failed")
    with pytest.raises(RuntimeError, match="create failed"):
        await sync.sync_department_created({"name": "生产部"})
    with pytest.raises(RuntimeError, match="create failed"):
        await sync.sync_employee_created({"name": "张三"})
    with pytest.raises(RuntimeError, match="create failed"):
        await sync.sync_offboarding_created({})
    with pytest.raises(RuntimeError, match="create failed"):
        await sync.sync_approval_created({"name": "张三"})

    sync.bitable.search_records.return_value = [{"record_id": "record"}]
    sync.bitable.update_record.side_effect = RuntimeError("update failed")
    with pytest.raises(RuntimeError, match="update failed"):
        await sync.sync_department_updated({"code": "D1"})
    with pytest.raises(RuntimeError, match="update failed"):
        await sync.sync_employee_updated({"employee_number": "E1"})
    with pytest.raises(RuntimeError, match="update failed"):
        await sync.sync_offboarding_updated(
            {"_feishu_record_id": "record"}
        )

    sync.bitable.delete_record.side_effect = RuntimeError("delete failed")
    with pytest.raises(RuntimeError, match="delete failed"):
        await sync.sync_department_deleted("D1")
    with pytest.raises(RuntimeError, match="delete failed"):
        await sync.sync_employee_deleted("E1")


def test_employee_field_builder_includes_optional_contact_and_dates() -> None:
    sync = FeishuBitableSync.__new__(FeishuBitableSync)
    fields = sync._build_employee_fields(
        {
            "employee_number": "E1",
            "name": "张三",
            "phone": "masked",
            "emergency_contact_phone": "masked",
            "hire_date": "2026-01-01",
            "contract_start_date": "2026-01-02",
            "contract_end_date": "2026-01-03",
        }
    )
    assert fields["电话"] == "masked"
    assert fields["紧急联系人电话"] == "masked"
    assert fields["入职日期"] == 1_767_225_600_000
    assert fields["合同开始日期"] == 1_767_312_000_000
    assert fields["合同结束日期"] == 1_767_398_400_000


@pytest.mark.asyncio
async def test_run_sync_counts_all_outcomes() -> None:
    records = [
        {"record_id": "created", "id": "created"},
        {"record_id": "updated", "id": "updated"},
        {"record_id": "missing"},
        {"record_id": "error", "id": "error"},
    ]
    post_process = AsyncMock()

    async def upsert(parsed):
        if parsed["id"] == "error":
            raise RuntimeError("write failed")

    async def get_existing(record_id):
        created_at = (
            datetime.now(UTC)
            if record_id == "created"
            else datetime.now(UTC) - timedelta(days=1)
        )
        return SimpleNamespace(created_at=created_at)

    stats = await run_sync(
        fetch_records=AsyncMock(return_value=records),
        parse_record=lambda record: record if record.get("id") else None,
        upsert_record=upsert,
        get_existing=get_existing,
        get_record_id=lambda record: record.get("id"),
        post_process=post_process,
    )
    assert stats == {"created": 1, "updated": 1, "failed": 2, "total": 4}
    assert post_process.await_count == 2


@pytest.mark.asyncio
async def test_run_sync_rejects_missing_identity_and_naive_creation_time() -> None:
    existing = SimpleNamespace(created_at=datetime.now())
    stats = await run_sync(
        fetch_records=AsyncMock(
            return_value=[
                {"record_id": "missing-id", "value": ""},
                {"record_id": "created", "value": "created"},
            ]
        ),
        parse_record=lambda record: record,
        upsert_record=AsyncMock(),
        get_existing=AsyncMock(return_value=existing),
        get_record_id=lambda record: record["value"] or None,
    )
    assert stats == {"created": 1, "updated": 0, "failed": 1, "total": 2}


def test_user_record_parsing_and_creation_heuristic() -> None:
    assert _parse_user_record({}) is None
    parsed = _parse_user_record(
        {
            "open_id": "open",
            "department_ids": ["d1"],
            "employee_no": "",
            "job_title": "工程师",
        }
    )
    assert parsed is not None
    assert parsed["open_id"] == "open"
    assert parsed["feishu_department_ids"] == '["d1"]'
    assert _is_newly_created(SimpleNamespace(created_at=datetime.now(UTC)))
    assert not _is_newly_created(
        SimpleNamespace(created_at=datetime.now(UTC) - timedelta(minutes=2))
    )
    assert not _is_newly_created(SimpleNamespace(created_at=None))


@pytest.mark.asyncio
async def test_user_upsert_updates_existing_and_creates_missing(
    monkeypatch,
) -> None:
    existing = SimpleNamespace(
        name="旧名",
        en_name="",
        employee_no=None,
        email=None,
        mobile=None,
        position=None,
        avatar_url=None,
        department="已有部门",
        feishu_department_ids=None,
        feishu_user_id=None,
    )
    results = [
        SimpleNamespace(scalar_one_or_none=lambda: existing),
        SimpleNamespace(scalar_one_or_none=lambda: None),
        SimpleNamespace(scalar_one_or_none=lambda: existing),
    ]
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=results),
        add=lambda value: added.append(value),
        commit=AsyncMock(),
    )
    added = []

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(sync_module, "async_session_factory", SessionContext)
    parsed = {
        "open_id": "open",
        "user_id": "user",
        "name": "新名",
        "en_name": "New",
        "employee_no": "E1",
        "email": "a@example.com",
        "mobile": "masked",
        "department": "新部门",
        "position": "工程师",
        "avatar_url": "avatar",
        "feishu_department_ids": '["d1"]',
    }

    await sync_module._upsert_user(parsed)
    assert existing.name == "新名"
    assert existing.department == "已有部门"
    assert existing.feishu_user_id == "user"
    await sync_module._upsert_user(parsed)
    assert len(added) == 1
    assert (await sync_module._get_existing_user("open")) is existing


@pytest.mark.asyncio
async def test_sync_departments_updates_and_creates_records(monkeypatch) -> None:
    existing = SimpleNamespace(
        created_at=datetime.now(UTC),
        name="旧部门",
        parent_feishu_department_id="",
        leader_user_id="",
        member_count=0,
        status_is_deleted=False,
        order=0,
    )
    persisted_new = SimpleNamespace(created_at=datetime.now(UTC))
    results = [
        SimpleNamespace(scalar_one_or_none=lambda: existing),
        SimpleNamespace(scalar_one_or_none=lambda: existing),
        SimpleNamespace(scalar_one_or_none=lambda: None),
        SimpleNamespace(scalar_one_or_none=lambda: persisted_new),
    ]
    added = []
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=results),
        add=lambda value: added.append(value),
        commit=AsyncMock(),
    )

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(sync_module, "async_session_factory", SessionContext)
    monkeypatch.setattr(
        "app.platform.integrations.feishu.contact.get_all_departments",
        AsyncMock(
            return_value=[
                {
                    "department_id": "d1",
                    "name": "生产部",
                    "parent_department_id": "root",
                    "leader_user_id": "u1",
                    "member_count": 2,
                    "order": 1,
                },
                {
                    "department_id": "d2",
                    "name": "质量部",
                    "parent_department_id": "root",
                },
            ]
        ),
    )
    result = await sync_module.sync_departments("root")
    assert result["dept_count"] == 2
    assert existing.name == "生产部"
    assert existing.member_count == 2
    assert len(added) == 1


@pytest.mark.asyncio
async def test_sync_members_reports_department_and_user_fetch_failures(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.platform.integrations.feishu.contact.get_all_departments",
        AsyncMock(side_effect=RuntimeError("department timeout")),
    )
    monkeypatch.setattr(
        "app.platform.integrations.feishu.contact.find_users_by_department",
        AsyncMock(side_effect=RuntimeError("user timeout")),
    )

    async def invoke_fetch(**kwargs):
        records = await kwargs["fetch_records"]()
        return {
            "created": 0,
            "updated": 0,
            "failed": 0,
            "total": len(records),
        }

    monkeypatch.setattr(sync_module, "run_sync", invoke_fetch)
    result = await sync_module.sync_members("root")
    assert result["user_count"] == 0
    assert result["dept_count"] == 1
    assert result["errors"] == ["root: user timeout"]


@pytest.mark.asyncio
async def test_sync_members_orchestrates_departments_and_users(monkeypatch) -> None:
    async def get_departments(**_kwargs):
        return [{"department_id": "child", "name": "子部门"}]

    async def get_users(department_id, **_kwargs):
        if department_id == "root":
            return [{"open_id": "root-user"}]
        return [{"open_id": "child-user"}]

    monkeypatch.setattr(
        "app.platform.integrations.feishu.contact.get_all_departments",
        get_departments,
    )
    monkeypatch.setattr(
        "app.platform.integrations.feishu.contact.find_users_by_department",
        get_users,
    )

    async def fake_run_sync(**kwargs):
        raw = await kwargs["fetch_records"]()
        parsed = [kwargs["parse_record"](record) for record in raw]
        return {
            "created": len(parsed),
            "updated": 0,
            "failed": 0,
            "total": len(parsed),
        }

    monkeypatch.setattr(sync_module, "run_sync", fake_run_sync)
    result = await sync_module.sync_members("root")
    assert result["user_count"] == 2
    assert result["dept_count"] == 2
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_sync_users_by_ids_deduplicates_and_ignores_fetch_errors(
    monkeypatch,
) -> None:
    async def get_user(user_id, **_kwargs):
        if user_id == "bad":
            raise RuntimeError("unavailable")
        return {"open_id": user_id}

    monkeypatch.setattr(
        "app.platform.integrations.feishu.contact.get_user_detail",
        get_user,
    )

    async def fake_run_sync(**kwargs):
        records = await kwargs["fetch_records"]()
        return {
            "created": len(records),
            "updated": 0,
            "failed": 0,
            "total": len(records),
        }

    monkeypatch.setattr(sync_module, "run_sync", fake_run_sync)
    result = await sync_module.sync_users_by_ids(["good", "good", "", "bad"])
    assert result["user_count"] == 1


@pytest.mark.asyncio
async def test_sync_departments_builds_expected_mapping(monkeypatch) -> None:
    async def get_departments(**_kwargs):
        return [
            {
                "department_id": "d1",
                "name": "生产部",
                "parent_department_id": "0",
            },
            {"name": "missing-id"},
        ]

    monkeypatch.setattr(
        "app.platform.integrations.feishu.contact.get_all_departments",
        get_departments,
    )
    captured: list[dict | None] = []

    async def fake_run_sync(**kwargs):
        records = await kwargs["fetch_records"]()
        captured.extend(kwargs["parse_record"](record) for record in records)
        return {"created": 1, "updated": 0, "failed": 1, "total": 2}

    monkeypatch.setattr(sync_module, "run_sync", fake_run_sync)
    result = await sync_module.sync_departments("root")
    assert result["dept_count"] == 2
    assert captured[0] == {
        "department_id": "d1",
        "name": "生产部",
        "parent_department_id": "0",
        "leader_user_id": "",
        "member_count": 0,
        "status_is_deleted": False,
        "order": 0,
    }
    assert captured[1] is None


def test_feishu_reference_parsing_and_fallbacks() -> None:
    reference = feishu_utils.parse_bitable_url(
        "https://example.feishu.cn/base/appToken123?table=tblTable&view=vew1"
    )
    assert reference.app_token == "appToken123"
    assert reference.table_id == "tblTable"
    assert reference.view_id == "vew1"
    assert feishu_utils.normalize_app_token("app_token: labelledToken123") == (
        "labelledToken123"
    )
    assert feishu_utils.normalize_table_id("table: tblLabelled") == "tblLabelled"
    assert feishu_utils.normalize_app_token(" ") is None
    assert feishu_utils.normalize_table_id(None) is None
    resolved = feishu_utils.resolve_bitable_reference(
        app_token=None,
        table_id=None,
        fallback_app_token=(
            "https://example.feishu.cn/base/fallbackToken?table=tblFallback"
        ),
    )
    assert resolved.app_token == "fallbackToken"
    assert resolved.table_id == "tblFallback"


@pytest.mark.asyncio
async def test_tenant_access_token_cache_and_http_failures(monkeypatch) -> None:
    with pytest.raises(RuntimeError, match="未配置"):
        await feishu_utils.get_tenant_access_token("", "")

    monkeypatch.setattr(feishu_utils, "cache_get", AsyncMock(return_value="cached"))
    assert await feishu_utils.get_tenant_access_token(
        "app",
        "secret",
        cache_key="key",
    ) == "cached"

    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"code": 0, "tenant_access_token": "fresh"},
    )
    client = SimpleNamespace(post=AsyncMock(return_value=response))

    class ClientContext:
        async def __aenter__(self):
            return client

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(
        feishu_utils,
        "cache_get",
        AsyncMock(side_effect=RuntimeError("Redis unavailable")),
    )
    monkeypatch.setattr(
        feishu_utils,
        "cache_set",
        AsyncMock(side_effect=RuntimeError("Redis unavailable")),
    )
    monkeypatch.setattr(
        feishu_utils.httpx,
        "AsyncClient",
        lambda **_kwargs: ClientContext(),
    )
    assert await feishu_utils.get_tenant_access_token(
        "app",
        "secret",
        cache_key="key",
    ) == "fresh"

    response.json = lambda: {"code": 1, "msg": "denied"}
    with pytest.raises(RuntimeError, match="denied"):
        await feishu_utils.get_tenant_access_token("app", "secret")
    response.json = lambda: {"code": 0}
    with pytest.raises(RuntimeError, match="响应为空"):
        await feishu_utils.get_tenant_access_token("app", "secret")


@pytest.mark.asyncio
async def test_bitable_connectivity_reports_all_failure_modes(monkeypatch) -> None:
    missing_app = await feishu_utils.test_bitable_table_with_token(
        tenant_access_token="token",
        app_token="",
        table_id="table",
    )
    assert missing_app.status == "error"
    missing_table = await feishu_utils.test_bitable_table_with_token(
        tenant_access_token="token",
        app_token="app",
        table_id="",
    )
    assert missing_table.status == "error"

    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"code": 0},
    )
    client = SimpleNamespace(get=AsyncMock(return_value=response))

    class ClientContext:
        async def __aenter__(self):
            return client

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(
        feishu_utils.httpx,
        "AsyncClient",
        lambda **_kwargs: ClientContext(),
    )
    ok = await feishu_utils.test_bitable_table_with_token(
        tenant_access_token="token",
        app_token="app",
        table_id="table",
    )
    assert ok.status == "ok"
    response.json = lambda: {"code": 1, "msg": "no access"}
    denied = await feishu_utils.test_bitable_table_with_token(
        tenant_access_token="token",
        app_token="app",
        table_id="table",
    )
    assert denied.status == "error"

    client.get.side_effect = TimeoutError("timeout")
    timeout = await feishu_utils.test_bitable_table_with_token(
        tenant_access_token="token",
        app_token="app",
        table_id="table",
    )
    assert "timeout" in timeout.message


@pytest.mark.asyncio
async def test_bitable_connectivity_contains_auth_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        feishu_utils,
        "get_tenant_access_token",
        AsyncMock(side_effect=RuntimeError("invalid credentials")),
    )
    result = await feishu_utils.test_bitable_table(
        app_id="app",
        app_secret="secret",
        app_token="token",
        table_id="table",
    )
    assert result.name == "应用凭证"
    assert result.status == "error"
