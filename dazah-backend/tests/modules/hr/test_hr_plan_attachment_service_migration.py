from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.core.exceptions import NotFoundException
from app.core.llm import LLMOutputError
from app.modules.hr import service
from app.modules.hr.attachment_parser import SectionDraft


def _attachment(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": uuid4(),
        "plan_id": uuid4(),
        "annex_no": "附件1",
        "file_name": "附件1.docx",
        "file_data": b"content",
        "storage_key": None,
        "file_size": 7,
        "ledger_imported_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_plan_attachment_upload_sections_preview_delete_and_mark_imported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_id = uuid4()
    attachment = _attachment(plan_id=plan_id)

    async def create(item: object) -> object:
        if getattr(item, "id", None) is None:
            item.id = attachment.id
        return attachment

    repo = SimpleNamespace(
        session=SimpleNamespace(flush=AsyncMock()),
        create=AsyncMock(side_effect=create),
        get_by_id=AsyncMock(return_value=attachment),
        soft_delete=AsyncMock(),
    )
    section_repo = SimpleNamespace(
        create=AsyncMock(),
        list_by_plan=AsyncMock(return_value=[]),
        soft_delete_by_attachment=AsyncMock(),
        get_by_id=AsyncMock(),
    )
    instance = service.PlanAttachmentService.__new__(service.PlanAttachmentService)
    instance.repo = repo
    instance.section_repo = section_repo
    monkeypatch.setattr(service.storage, "is_enabled", lambda: False)
    monkeypatch.setattr(
        service,
        "parse_sections",
        lambda *_args: [
            SectionDraft("附件1", "第一项", "docx_section", "2"),
            SectionDraft("附件1", "重复项", "docx_section", "3"),
        ],
    )
    uploaded = await instance.upload(plan_id, "附件1.docx", b"content")
    assert uploaded is attachment
    assert section_repo.create.await_count == 1

    assert instance.read_data(attachment) == b"content"
    section = SimpleNamespace(
        id=uuid4(),
        attachment_id=attachment.id,
        source_kind="docx_section",
        source_ref="2",
    )
    section_repo.get_by_id.return_value = section
    monkeypatch.setattr(
        service,
        "build_preview",
        Mock(return_value={"text": "预览"}),
    )
    assert (await instance.preview_section(section.id))["text"] == "预览"
    assert await instance.preview_attachment(attachment.id) == {"text": "预览"}

    await instance.delete(attachment.id)
    section_repo.soft_delete_by_attachment.assert_awaited_once_with(attachment.id)
    repo.soft_delete.assert_awaited_once_with(attachment)

    imported = _attachment(ledger_imported_at=None)
    already = _attachment(ledger_imported_at=datetime(2026, 8, 20, tzinfo=UTC))
    repo.get_by_id.side_effect = [imported, already, None]
    count = await instance.mark_ledger_imported([imported.id, already.id, uuid4()])
    assert count == 1
    repo.session.flush.assert_awaited_once()

    section_repo.get_by_id.return_value = None
    with pytest.raises(NotFoundException):
        await instance.get_section(uuid4())


@pytest.mark.asyncio
async def test_plan_attachment_ai_inference_matching_and_storage_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = service.PlanAttachmentService.__new__(service.PlanAttachmentService)
    item_repo = SimpleNamespace(
        list_items=AsyncMock(
            return_value=[SimpleNamespace(content_textbook="附件1 培训内容")]
        )
    )
    section_repo = SimpleNamespace(
        list_by_plan=AsyncMock(return_value=[]),
        create=AsyncMock(),
    )
    instance.repo = SimpleNamespace(
        session=SimpleNamespace(), get_by_id=AsyncMock(return_value=None)
    )
    instance.section_repo = section_repo
    monkeypatch.setattr(
        service,
        "AnnualTrainingPlanItemRepository",
        lambda _session: item_repo,
    )
    monkeypatch.setattr(service, "strip_punct", lambda value: value.replace(" ", ""))
    monkeypatch.setattr(service, "extract_annex_refs", lambda _value: ["附件1"])
    deterministic = await instance._match_to_plan_refs(
        uuid4(), "培训内容.docx", b"docx"
    )
    assert deterministic[0].annex_no == "附件1"

    monkeypatch.setattr(
        service,
        "build_outline",
        lambda *_args: {"kind": "xlsx", "sheets": [{"name": "Sheet1"}]},
    )
    monkeypatch.setattr(
        service,
        "_llm_chat_json_with_retry",
        AsyncMock(
            return_value={"sections": [{"sheet": "Sheet1", "n": 2, "title": "第二项"}]}
        ),
    )
    inferred = await instance._ai_infer_sections("计划.xlsx", b"xlsx")
    assert inferred[0].annex_no == "附件2"

    monkeypatch.setattr(
        service,
        "build_outline",
        lambda *_args: {"kind": "docx", "lines": [{"index": 1, "text": "附件三"}]},
    )
    monkeypatch.setattr(
        service,
        "_llm_chat_json_with_retry",
        AsyncMock(return_value={"sections": [{"index": 1, "n": 3, "title": "第三项"}]}),
    )
    docx_sections = await instance._ai_infer_sections("计划.docx", b"docx")
    assert docx_sections[0].source_kind == "docx_section"

    monkeypatch.setattr(
        service,
        "_llm_chat_json_with_retry",
        AsyncMock(side_effect=LLMOutputError("invalid")),
    )
    assert await instance._ai_infer_sections("计划.docx", b"docx") == []

    monkeypatch.setattr(service, "extract_annex_refs", lambda _value: ["附件1"])
    monkeypatch.setattr(service, "strip_punct", lambda value: value.replace(" ", ""))
    monkeypatch.setattr(
        service, "build_outline", lambda *_args: {"kind": "xlsx", "sheets": []}
    )
    monkeypatch.setattr(
        service,
        "_llm_chat_json_with_retry",
        AsyncMock(return_value={"ref": "附件1"}),
    )
    semantic = await instance._match_to_plan_refs(uuid4(), "其他.xlsx", b"xlsx")
    assert semantic[0].annex_no == "附件1"

    missing = SimpleNamespace(
        id=uuid4(), storage_key="hr/key", file_data=None, file_name="x.pdf"
    )
    instance.repo.get_by_id.return_value = None
    with pytest.raises(NotFoundException):
        await instance.get(missing.id)
    instance.repo.get_by_id.return_value = missing
    monkeypatch.setattr(service.storage, "is_enabled", lambda: True)
    monkeypatch.setattr(
        service.storage, "get_object", lambda *_args: (b"minio", "application/pdf")
    )
    assert instance.read_data(missing) == b"minio"
