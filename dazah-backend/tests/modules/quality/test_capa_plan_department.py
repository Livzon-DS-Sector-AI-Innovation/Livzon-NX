from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.quality.models.capa_plan_track import CapaPlanTrack
from app.modules.quality.service import feishu_capa
from app.modules.quality.service import quality_feishu_sync as sync
from app.modules.quality.service import tracking_records as service

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("method", ["post", "put"])
async def test_department_saved_but_derived_fields_preserved(
    client, monkeypatch, method
):
    now = datetime.now(UTC)
    capa_id, track_id = uuid4(), uuid4()
    track = CapaPlanTrack(
        id=track_id,
        capa_id=capa_id,
        capa_code="CA-TEST",
        plan_content="计划",
        department="QC",
        department_head="自动生成负责人",
        owner_confirmed=True,
        department_head_confirmed=True,
        reminder_status="pending",
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(
        service.repository,
        "get_capa_by_id",
        AsyncMock(
            return_value=SimpleNamespace(
                id=capa_id, capa_code="CA-TEST", department="QC"
            )
        ),
    )
    monkeypatch.setattr(
        service.repository, "get_capa_plan_track_by_id", AsyncMock(return_value=track)
    )
    monkeypatch.setattr(service, "assert_quality_record_department", AsyncMock())
    monkeypatch.setattr(sync, "auto_sync_capa_plan_track_after_write", AsyncMock())
    writes = []

    async def write(*args):
        payload = args[-1]
        writes.append(payload)
        for key, value in payload.items():
            setattr(track, key, value)
        return track

    monkeypatch.setattr(service.repository, "create_capa_plan_track", write)
    monkeypatch.setattr(service.repository, "update_capa_plan_track", write)
    path = "/api/v1/quality/capa-plan-tracks" + (
        f"/{track_id}" if method == "put" else ""
    )
    response = await getattr(client, method)(
        path,
        json={
            "capa_id": str(capa_id),
            "plan_content": "修改计划",
            "department": "QA",
            "department_head": "错误手填人",
            "owner_confirmed": False,
            "department_head_confirmed": False,
        },
    )
    assert response.status_code == 200, response.text
    saved = response.json()["data"]
    assert saved["department"] == "QA"
    assert saved["plan_content"] == "修改计划"
    assert saved["department_head"] == "自动生成负责人"
    assert saved["owner_confirmed"] and saved["department_head_confirmed"]
    assert (
        not {"department_head", "owner_confirmed", "department_head_confirmed"}
        & writes[0].keys()
    )


async def test_invalid_plan_request_is_validation_error(client):
    response = await client.post(
        "/api/v1/quality/capa-plan-tracks", json={"due_date": "不是日期"}
    )
    assert response.status_code == 422


async def test_native_plan_writer_also_ignores_automatic_confirmation_fields():
    fields = await feishu_capa._coerce_write_fields(
        SimpleNamespace(),
        {
            "部门": "QA",
            "计划内容": "修订计划",
            "部门负责人": "手填负责人",
            "责任人确认": True,
            "部门负责人确认": True,
        },
        datetime_fields=feishu_capa._CAPA_PLAN_DATETIME_FIELDS,
        user_fields=feishu_capa._CAPA_PLAN_USER_FIELDS,
        checkbox_fields=feishu_capa._CAPA_PLAN_CHECKBOX_FIELDS,
        readonly_fields=feishu_capa._CAPA_PLAN_READONLY_FIELDS,
    )
    assert fields == {"部门": "QA", "计划内容": "修订计划"}


async def test_remote_lookup_and_confirmations_are_read_back(monkeypatch):
    entity = SimpleNamespace(app_token="test", table_id="table", field_mappings={})
    runtime = SimpleNamespace(
        app_id="test",
        app_secret="test",
        get_entity_config=lambda *args, **kwargs: entity,
    )
    monkeypatch.setattr(
        sync.feishu_sync, "_resolve_runtime", AsyncMock(return_value=runtime)
    )
    search = AsyncMock(
        side_effect=[
            {
                "items": [
                    {
                        "record_id": "another_plan",
                        "fields": {
                            "部门负责人": [{"name": "别人的负责人"}],
                        },
                    }
                ],
                "has_more": True,
                "page_token": "page2",
            },
            {
                "items": [
                    {
                        "record_id": "rec_test",
                        "fields": {
                            "部门负责人": {
                                "type": 11,
                                "value": [{"name": "新部门负责人"}],
                            },
                            "责任人确认": True,
                            "部门负责人确认": True,
                        },
                    }
                ],
                "has_more": False,
            },
            {"items": [{"record_id": "rec_test", "fields": {}}], "has_more": False},
        ]
    )
    monkeypatch.setattr(sync.BitableClient, "search_records_page", search)
    track = SimpleNamespace(
        capa_code="CA-TEST",
        department_head="旧负责人",
        owner_confirmed=False,
        department_head_confirmed=False,
    )
    await sync._refresh_capa_plan_derived_fields(SimpleNamespace(), track, "rec_test")
    assert track.department_head == "新部门负责人"
    assert track.owner_confirmed and track.department_head_confirmed
    assert search.await_args_list[0].kwargs["automatic_fields"] is True
    assert search.await_args_list[1].kwargs["page_token"] == "page2"
    # Missing automatic fields must not erase the previously synchronized values.
    await sync._refresh_capa_plan_derived_fields(SimpleNamespace(), track, "rec_test")
    assert track.department_head == "新部门负责人"
    assert track.owner_confirmed and track.department_head_confirmed
