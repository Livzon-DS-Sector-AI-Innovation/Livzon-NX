from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.modules.quality.service import quality_ai as service


class _Result:
    def __init__(
        self, row: object | None = None, rows: list[object] | None = None
    ) -> None:
        self.row = row
        self.rows = rows or []

    def scalar_one_or_none(self) -> object | None:
        return self.row

    def scalar_one(self) -> object:
        assert self.row is not None
        return self.row

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[object]:
        return self.rows


def _deviation(deviation_id: object | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=deviation_id or uuid4(),
        is_deleted=False,
        deviation_code="DEV-1",
        title="异常",
        department="质量部",
        discovery_date=date(2026, 8, 26),
        discovery_time="10:00",
        discovery_location="车间",
        level="major",
        description="偏差描述",
        immediate_actions="隔离",
        affected_items="产品",
        batch_number="B-1",
        root_cause_analysis="待分析",
        corrective_actions="待制定",
        status="draft",
        status_updated_at=None,
        updated_by=None,
    )


def _session(deviation_id: object) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        deviation_id=deviation_id,
        supplement_text="补充信息",
        attachment_summary="附件摘要",
        status="idle",
        error_message=None,
        deviation_analysis_payload=None,
        capa_suggestion_payload=None,
        last_generated_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        updated_by=None,
    )


@pytest.mark.asyncio
async def test_resolve_deviation_id_rebinds_or_creates_placeholder() -> None:
    deviation_id = uuid4()
    assert (
        await service._resolve_deviation_id(SimpleNamespace(), str(deviation_id))
        == deviation_id
    )

    existing = _deviation()
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[_Result(), _Result(existing)]),
        flush=AsyncMock(),
    )
    from app.modules.quality.service import tracking_records

    tracking = AsyncMock(return_value={"deviation_code": "DEV-1"})
    original = tracking_records.get_deviation_report_record_from_feishu
    tracking_records.get_deviation_report_record_from_feishu = tracking
    try:
        assert await service._resolve_deviation_id(db, "feishu-r1") == existing.id
        assert existing.feishu_base_record_id == "feishu-r1"
    finally:
        tracking_records.get_deviation_report_record_from_feishu = original

    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[_Result(), _Result()]),
        add=Mock(),
        flush=AsyncMock(),
    )
    db.add.side_effect = lambda item: setattr(item, "id", uuid4())
    tracking = AsyncMock(
        return_value={
            "deviation_code": "DEV-NEW",
            "description": "飞书描述",
            "department": "质量部",
            "feishu_base_table_id": "tbl-1",
        }
    )
    tracking_records.get_deviation_report_record_from_feishu = tracking
    try:
        created_id = await service._resolve_deviation_id(db, "feishu-new")
    finally:
        tracking_records.get_deviation_report_record_from_feishu = original
    assert created_id
    assert db.add.called


@pytest.mark.asyncio
async def test_ai_session_regenerate_and_apply_updates_business_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deviation = _deviation()
    session = _session(deviation.id)
    generated = {
        "deviation_analysis": {
            "summary": "分析",
            "structured_fields": {
                "preliminary_cause_analysis": "根因建议",
                "capa_suggestions": "措施建议",
            },
        },
        "capa_suggestion": {
            "summary": "CAPA",
            "structured_fields": {"capa_suggestions": "措施建议"},
        },
    }
    monkeypatch.setattr(
        service,
        "_require_quality_ai_config",
        AsyncMock(return_value=SimpleNamespace(model_name="m")),
    )
    monkeypatch.setattr(
        type(service.llm_client),
        "chat_json",
        AsyncMock(return_value=generated),
    )
    db = SimpleNamespace(
        get=AsyncMock(return_value=deviation),
        execute=AsyncMock(
            side_effect=[_Result(session), _Result(session), _Result(rows=[])]
        ),
        add=Mock(),
        flush=AsyncMock(),
        commit=AsyncMock(),
    )
    result = await service.regenerate_deviation_ai_session(db, deviation.id, "system")
    assert result.status == "completed"
    assert session.status == "completed"
    assert (
        session.deviation_analysis_payload["structured_fields"]["capa_suggestions"]
        == "措施建议"
    )

    session.deviation_analysis_payload = generated["deviation_analysis"]
    db.get = AsyncMock(return_value=deviation)
    db.execute = AsyncMock(
        side_effect=[_Result(session), _Result(session), _Result(rows=[])]
    )
    result = await service.apply_deviation_ai_session(
        db,
        deviation.id,
        "deviation_analysis",
        ["root_cause_analysis", "corrective_actions"],
        "system",
    )
    assert result.id == session.id
    assert deviation.root_cause_analysis == "根因建议"
    assert deviation.corrective_actions == "措施建议"


@pytest.mark.asyncio
async def test_image_storage_and_attachment_helpers_cover_local_and_vision_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(service.Image, "open", Mock(return_value=object()))
    monkeypatch.setattr(
        service.pytesseract, "image_to_string", lambda *_args, **_kwargs: "OCR文字"
    )
    text, summary = await service._extract_image_text(b"not-used", "image/png")
    assert text == "OCR文字" and summary is None

    monkeypatch.setattr(
        service.Image, "open", Mock(side_effect=RuntimeError("ocr unavailable"))
    )
    monkeypatch.setattr(
        type(service.llm_client),
        "chat_vision_json",
        AsyncMock(return_value={"text": "视觉文字", "summary": "视觉摘要"}),
    )
    text, summary = await service._extract_image_text(b"image", "image/png")
    assert text == "视觉文字" and summary == "视觉摘要"

    monkeypatch.setattr(service, "minio_enabled", lambda: False)
    monkeypatch.setattr(
        service, "get_settings", lambda: SimpleNamespace(UPLOAD_DIR=str(tmp_path))
    )
    with pytest.raises(Exception):
        service._store_deviation_ai_attachment("../附件.png", b"data", "image/png")
    stored = service._store_deviation_ai_attachment("附件.png", b"data", "image/png")
    assert "deviation-ai" not in stored
    assert open(stored, "rb").read() == b"data"
    service._delete_deviation_ai_attachment_file(stored)

    upload = Mock()
    delete = Mock()
    monkeypatch.setattr(service, "minio_enabled", lambda: True)
    monkeypatch.setattr(service, "upload_object", upload)
    monkeypatch.setattr(service, "delete_object", delete)
    remote = service._store_deviation_ai_attachment(
        "a.docx", b"doc", "application/octet-stream"
    )
    service._delete_deviation_ai_attachment_file(remote)
    upload.assert_called_once()
    delete.assert_called_once_with("quality", remote)
