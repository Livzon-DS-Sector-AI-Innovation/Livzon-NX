"""Real route/service regressions; mock only directory and external writes."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.exceptions import AppException
from app.modules.quality.service import person_directory
from app.modules.quality.service import quality_feishu_pages as pages
from app.modules.quality.service import quality_feishu_pages_oos_oot as oos
from app.modules.quality.service import quality_feishu_sync as sync
from app.modules.quality.service import tracking_records as tracking

pytestmark = pytest.mark.anyio


async def test_investigation_route_accepts_feishu_id_and_selected_person(
    client, monkeypatch
):
    monkeypatch.setattr(
        person_directory, "resolve_person_write_id", AsyncMock(return_value="on_new")
    )
    monkeypatch.setattr(
        tracking,
        "_resolve_selected_submitter_contact",
        AsyncMock(return_value={"name": "新提交人", "department": "QC"}),
    )
    update = AsyncMock()
    monkeypatch.setattr(pages, "_update_entity_record", update)
    response = await client.put(
        "/api/v1/quality/deviation-investigation-push-records/rec_remote",
        json={
            "deviation_code": "PC-1",
            "push_round": "第1次推送",
            "submitter_open_id": "ou_new",
        },
    )
    assert response.status_code == 200, response.text
    fields = update.await_args.args[3]
    assert fields["提交人"] == [{"id": "on_new"}]
    assert fields["部门"] == "QC"
    assert "偏差调查报告" not in fields
    assert "QA审核结果" not in fields
    assert "部门负责人" not in fields  # Lookup is owned by Feishu.
    assert update.await_args.kwargs["user_id_type"] == "union_id"
    assert response.json()["data"]["submitter"] == "新提交人"


@pytest.mark.parametrize(
    "kind,person_field,feishu_field",
    [("report", "reporter", "报告人"), ("investigation_push", "submitter", "提交人")],
)
async def test_oos_update_translates_member_and_preserves_untouched_fields(
    monkeypatch, kind, person_field, feishu_field
):
    resolve = AsyncMock(return_value="on_cross_app")
    monkeypatch.setattr(person_directory, "resolve_person_write_id", resolve)
    update = AsyncMock()
    monkeypatch.setattr(oos, "_update_entity_record", update)
    await getattr(oos, f"update_oos_oot_{kind}_record")(
        SimpleNamespace(), "rec_one", {person_field: "ou_hr", "department": "QC"}
    )
    resolve.assert_awaited_once_with(SimpleNamespace(), "ou_hr", department="QC")
    fields = update.await_args.args[3]
    assert fields[feishu_field] == [{"id": "on_cross_app"}]
    assert update.await_args.kwargs["user_id_type"] == "union_id"
    assert not (
        {"附件", "调查报告", "QA", "部门负责人审核结果", "QA审核结果"} & fields.keys()
    )


@pytest.mark.parametrize("kind", ["report", "investigation_push"])
async def test_oos_update_does_not_reread_whole_table_after_write(monkeypatch, kind):
    read = AsyncMock(side_effect=AssertionError("must not scan the table during save"))
    monkeypatch.setattr(oos, "_search_entity_records", read)
    monkeypatch.setattr(oos, "_update_entity_record", AsyncMock())
    await getattr(oos, f"update_oos_oot_{kind}_record")(
        SimpleNamespace(), "rec", {"content": "仅改文字"}
    )
    read.assert_not_awaited()


@pytest.mark.parametrize(
    "failure,status",
    [(httpx.ConnectError("offline"), 503), (RuntimeError("upstream rejected"), 502)],
)
async def test_oos_upstream_failure_has_useful_status(monkeypatch, failure, status):
    monkeypatch.setattr(oos, "_update_entity_record", AsyncMock(side_effect=failure))
    with pytest.raises(AppException) as error:
        await oos.update_oos_oot_report_record(
            SimpleNamespace(), "rec", {"content": "测试"}
        )
    assert error.value.status_code == status


async def test_oos_unknown_person_is_not_silently_ignored(monkeypatch):
    monkeypatch.setattr(
        person_directory, "resolve_person_write_id", AsyncMock(return_value=None)
    )
    write = AsyncMock()
    monkeypatch.setattr(oos, "_update_entity_record", write)
    with pytest.raises(AppException):
        await oos.update_oos_oot_report_record(
            SimpleNamespace(), "rec", {"reporter": "同名人员"}
        )
    write.assert_not_awaited()


async def test_capa_owner_is_written_as_member_not_name(monkeypatch):
    track = SimpleNamespace(
        capa_id="capa",
        capa_code="CA-1",
        plan_content="计划",
        due_date=date(2026, 9, 30),
        owner_name="责任人",
        department="QC",
        owner_confirmed=False,
        department_head="部门负责人",
        department_head_confirmed=False,
        progress="未开始",
        reminder_status="pending",
        feishu_base_record_id="rec",
    )
    monkeypatch.setattr(
        sync.repository, "get_capa_plan_track_by_id", AsyncMock(return_value=track)
    )
    monkeypatch.setattr(
        sync.repository,
        "get_capa_by_id",
        AsyncMock(return_value=SimpleNamespace(department="QC")),
    )
    resolve = AsyncMock(return_value=[{"id": "on_owner"}])
    monkeypatch.setattr(sync, "_resolve_contact_bitable_user_value", resolve)
    write = AsyncMock(return_value=("rec", "table"))
    monkeypatch.setattr(sync.feishu_sync, "_upsert_record", write)
    monkeypatch.setattr(sync, "_mark_sync_success", AsyncMock())
    monkeypatch.setattr(sync, "_refresh_capa_plan_derived_fields", AsyncMock())
    await sync.sync_capa_plan_track_to_feishu(SimpleNamespace(), "track")
    fields = write.await_args.args[4]
    assert fields["责任人"] == [{"id": "on_owner"}]
    assert fields["预计完成时间"]
    assert "完成时间" not in fields  # 台账表无此列，旧双写会被静默过滤


@pytest.mark.parametrize(
    "kind,mime,disposition",
    [
        ("content", "application/octet-stream", "attachment"),
        ("preview", "application/pdf", "inline"),
        ("thumbnail", "image/jpeg", "inline"),
    ],
)
async def test_oos_attachment_routes_use_owned_record_service(
    client, monkeypatch, kind, mime, disposition
):
    from app.modules.quality.api import oos_oot_feishu as api

    service_name = (
        "get_attachment_thumbnail"
        if kind == "thumbnail"
        else f"get_inspection_feishu_attachment_{kind}"
    )
    service = AsyncMock(return_value=(b"file-content", mime, "报告.doc"))
    monkeypatch.setattr(api, service_name, service)
    response = await client.get(
        f"/api/v1/quality/oos-oot/report-records/rec/attachments/file/{kind}"
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"].startswith(disposition)
    assert response.headers["content-type"].startswith(mime)
    assert service.await_args.args[1:4] == ("oos_oot_report_record", "rec", "file")
