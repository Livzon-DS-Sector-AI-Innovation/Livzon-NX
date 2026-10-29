"""中试文档上传必须避免路径穿越并限制落盘位置。"""

from __future__ import annotations

import json
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from starlette.datastructures import UploadFile

from app.core.exceptions import AppException
from app.modules.research import api


class _FakeResult:
    def __init__(self, workflow: Any) -> None:
        self._workflow = workflow

    def scalar_one_or_none(self) -> Any:
        return self._workflow


class _FakeDB:
    def __init__(self, workflow: Any) -> None:
        self.workflow = workflow
        self.committed = False

    async def execute(self, _statement: Any) -> _FakeResult:
        return _FakeResult(self.workflow)

    async def commit(self) -> None:
        self.committed = True


def _workflow() -> Any:
    return type(
        "Workflow",
        (),
        {"input_document_path": None, "is_deleted": False},
    )()


def _upload(filename: str, content: bytes = b"document") -> UploadFile:
    return UploadFile(file=BytesIO(content), filename=filename)


@pytest.mark.anyio
async def test_upload_rejects_traversal_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    workflow = _workflow()
    db = _FakeDB(workflow)

    with pytest.raises(AppException) as exc_info:
        await api.upload_pilot_workflow_document(
            workflow_id=str(uuid.uuid4()),
            file=_upload("../../app/main.py"),
            db=db,  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 400
    assert list(tmp_path.rglob("*.py")) == []


@pytest.mark.anyio
async def test_upload_stores_under_isolated_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    workflow = _workflow()
    db = _FakeDB(workflow)
    workflow_id = uuid.uuid4()

    response = await api.upload_pilot_workflow_document(
        workflow_id=str(workflow_id),
        file=_upload("中试记录.docx", b"docx-bytes"),
        db=db,  # type: ignore[arg-type]
    )

    stored = Path(str(workflow.input_document_path))
    assert stored.is_file()
    assert stored.read_bytes() == b"docx-bytes"
    assert stored.parent == tmp_path / "pilot_uploads"
    assert "中试记录" not in stored.name
    body: dict[str, Any] = json.loads(bytes(response.body))
    assert body["data"] == {"path": stored.name, "filename": "中试记录.docx"}
    assert db.committed is True


@pytest.mark.anyio
async def test_upload_rejects_invalid_workflow_id(tmp_path: Path) -> None:
    db = _FakeDB(None)

    with pytest.raises(Exception) as exc_info:
        await api.upload_pilot_workflow_document(
            workflow_id="not-a-uuid",
            file=_upload("doc.pdf"),
            db=db,  # type: ignore[arg-type]
        )

    assert getattr(exc_info.value, "status_code", None) == 404
