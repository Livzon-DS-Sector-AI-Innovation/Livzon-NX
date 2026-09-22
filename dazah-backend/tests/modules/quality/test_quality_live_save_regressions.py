"""Regression cases found by saving isolated records to the real Feishu tables."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.quality.service import person_directory
from app.modules.quality.service import quality_feishu_pages_oos_oot as oos
from app.modules.quality.service import quality_feishu_sync as sync

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    "path,person_key,field",
    [
        ("oos-ledger", "registrant", "登记人"),
        ("oot-ledger", "registrant", "登记人"),
        ("product-departments", "fermentation_head", "涉及发酵部门负责人"),
    ],
)
async def test_selected_people_are_translated_without_rewriting_untouched_fields(
    client, monkeypatch, path, person_key, field
):
    monkeypatch.setattr(
        person_directory, "resolve_person_write_id", AsyncMock(return_value="on_new")
    )
    write = AsyncMock(return_value={"record_id": "rec_one"})
    monkeypatch.setattr(oos, "_update_entity_record", write)
    for name in (
        "get_oos_ledger_record",
        "get_oot_ledger_record",
        "get_product_department_record",
    ):
        monkeypatch.setattr(
            oos,
            name,
            AsyncMock(return_value={"record_id": "rec_one", "remark": "keep"}),
        )
    response = await client.put(
        f"/api/v1/quality/oos-oot/{path}/rec_one",
        json={person_key: "ou_selected"},
    )
    assert response.status_code == 200, response.text
    fields = write.await_args.args[3]
    assert fields[field] == [{"id": "on_new"}]
    assert "备注" not in fields
    assert write.await_args.kwargs["user_id_type"] == "union_id"


async def test_capa_qa_member_and_plan_choices_use_feishu_field_types(monkeypatch):
    capa = SimpleNamespace(
        id="capa",
        capa_code="CA-1",
        created_at=None,
        closure_date=None,
        qa_confirm_date=None,
        department="QC",
        affected_product="A",
        capa_content="措施",
        title="标题",
        evaluation_result=None,
        qa_confirmer="质保人员",
        status="draft",
        feishu_base_record_id="rec_capa",
    )
    monkeypatch.setattr(sync.repository, "get_capa_by_id", AsyncMock(return_value=capa))
    monkeypatch.setattr(
        sync.repository, "get_capa_plan_tracks_by_capa_ids", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        sync,
        "_resolve_contact_bitable_user_value",
        AsyncMock(return_value=[{"id": "on_qa"}]),
    )
    monkeypatch.setattr(sync, "_mark_sync_success", AsyncMock())
    write = AsyncMock(return_value=("rec_capa", "table"))
    monkeypatch.setattr(sync.feishu_sync, "_upsert_record", write)
    await sync.sync_capa_to_feishu(SimpleNamespace(), "capa")
    assert write.await_args.args[4]["QA质量员"] == [{"id": "on_qa"}]

    track = SimpleNamespace(
        capa_id="capa",
        capa_code="CA-1",
        plan_content="计划",
        due_date=None,
        owner_name="责任人",
        department="QA",
        owner_confirmed=False,
        department_head=None,
        department_head_confirmed=False,
        progress="in_progress",
        reminder_status="reminded",
        feishu_base_record_id="rec_plan",
    )
    monkeypatch.setattr(
        sync.repository, "get_capa_plan_track_by_id", AsyncMock(return_value=track)
    )
    monkeypatch.setattr(sync, "_refresh_capa_plan_derived_fields", AsyncMock())
    await sync.sync_capa_plan_track_to_feishu(SimpleNamespace(), "plan")
    assert write.await_args.args[4]["进度"] == "正在进行"
    assert write.await_args.args[4]["提醒状态"] == "已提醒"
    assert write.await_args.args[4]["部门"] == "QA"
    assert (
        not {"部门负责人", "责任人确认", "部门负责人确认"}
        & write.await_args.args[4].keys()
    )
