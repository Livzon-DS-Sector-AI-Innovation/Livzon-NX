from __future__ import annotations

import io
import json
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import UploadFile

from app.modules.quality.api import document_catalog as api
from app.modules.quality.models.document_catalog import (
    DocumentDepartment,
    DocumentEntry,
)
from app.modules.quality.schemas.document_catalog import (
    CreateDocumentDepartmentRequest,
    CreateDocumentEntryRequest,
    DocumentEntryResolveRequest,
    UpdateDocumentDepartmentRequest,
    UpdateDocumentEntryRequest,
)


class _Result:
    def __init__(
        self,
        value: object | None = None,
        rows: list[object] | None = None,
    ) -> None:
        self.value = value
        self.rows = rows or []

    def scalar_one_or_none(self) -> object | None:
        return self.value

    def scalar_one(self) -> object:
        return self.value

    def scalar(self) -> int:
        return int(self.value or 0)

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[object]:
        return self.rows


class _Db:
    def __init__(self, *results: _Result) -> None:
        self.execute = AsyncMock(side_effect=list(results))
        self.flush = AsyncMock(side_effect=self._set_defaults)
        self.add = Mock()

    async def _set_defaults(self) -> None:
        for call in self.add.call_args_list:
            item = call.args[0]
            if getattr(item, "id", None) is None:
                item.id = uuid4()
            now = datetime.now(UTC)
            if getattr(item, "created_at", None) is None:
                item.created_at = now
            if getattr(item, "updated_at", None) is None:
                item.updated_at = now
            if getattr(item, "is_deleted", None) is None:
                item.is_deleted = False


def _department(name: str = "质量部") -> DocumentDepartment:
    item = DocumentDepartment(name=name, sort_order=1)
    item.id = uuid4()
    item.created_at = datetime(2026, 8, 20, tzinfo=UTC)
    item.updated_at = item.created_at
    item.is_deleted = False
    return item


def _entry(department_id: object, *, code: str = "QA-001/02") -> DocumentEntry:
    item = DocumentEntry(
        department_id=department_id,
        seq_no=1,
        name="偏差处理程序",
        code=code,
        effective_date=date(2026, 8, 20),
        effective_date_text="2026-08-20",
        source_file="目录.xlsx",
        attachments=[],
    )
    item.id = uuid4()
    item.created_at = datetime(2026, 8, 20, tzinfo=UTC)
    item.updated_at = item.created_at
    item.is_deleted = False
    return item


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), department="质量部")


def _response_body(response: object) -> dict[str, object]:
    return json.loads(response.body)  # type: ignore[union-attr]


def _upload(filename: str = "偏差处理程序.pdf") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(b"%PDF-1.7\ncontent"))


def test_escape_like_and_sort_latest_helpers() -> None:
    assert api._escape_like(r"a%_\b") == r"a\%\_\\b"


@pytest.mark.anyio
async def test_department_crud_handles_create_restore_duplicate_update_and_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user()
    monkeypatch.setattr(api, "_require_user", Mock())
    department = _department()
    created = _department("生产部")

    db = _Db(
        _Result(None),
        _Result(created),
    )
    result = await api.create_document_department(
        CreateDocumentDepartmentRequest(name="生产部", sort_order=2), db, user
    )
    assert result.status_code == 200
    assert _response_body(result)["message"] == "创建成功"
    assert db.add.called

    deleted_same = _department("研发部")
    deleted_same.is_deleted = True
    db = _Db(_Result(deleted_same), _Result(deleted_same))
    restored = await api.create_document_department(
        CreateDocumentDepartmentRequest(name="研发部", sort_order=3), db, user
    )
    assert restored.status_code == 200
    assert deleted_same.is_deleted is False

    active = _department()
    db = _Db(_Result(active))
    duplicate = await api.create_document_department(
        CreateDocumentDepartmentRequest(name="质量部"), db, user
    )
    assert duplicate.status_code == 400

    db = _Db(_Result(department), _Result(None), _Result(department))
    updated = await api.update_document_department(
        department.id,
        UpdateDocumentDepartmentRequest(name="质量管理部", sort_order=4),
        db,
        user,
    )
    assert updated.status_code == 200
    assert department.name == "质量管理部"

    db = _Db(_Result(department), _Result(_department("质量管理部")))
    duplicate_update = await api.update_document_department(
        department.id,
        UpdateDocumentDepartmentRequest(name="质量管理部"),
        db,
        user,
    )
    assert duplicate_update.status_code == 400

    db = _Db(_Result(department), _Result(rows=[]))
    deleted = await api.delete_document_department(department.id, db, user)
    assert deleted.status_code == 200
    assert department.is_deleted is True


@pytest.mark.anyio
async def test_document_lookup_and_content_resolution_choose_latest_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user()
    monkeypatch.setattr(api, "_require_user", Mock())
    department_id = uuid4()
    old = _entry(department_id, code="QA-001/01")
    latest = _entry(department_id, code="QA-001/03")
    latest.effective_date = date(2026, 9, 1)

    db = _Db(_Result(rows=[old, latest]))
    result = await api.lookup_latest_document_entry("偏差处理程序", db, user)
    assert result.status_code == 200
    assert _response_body(result)["data"]["code"] == "QA-001/03"

    empty = await api.lookup_latest_document_entry("", _Db(), user)
    assert _response_body(empty)["data"] is None

    monkeypatch.setattr(
        api, "_find_latest_entry_by_name", AsyncMock(side_effect=[latest, None])
    )
    monkeypatch.setattr(
        api,
        "read_entry_md_contents",
        Mock(return_value=[{"file_name": "标准.md", "md_text": "# 内容"}]),
    )
    resolved = await api.resolve_document_entry_content(
        DocumentEntryResolveRequest(names=["偏差处理程序", "不存在", ""]),
        _Db(),
        user,
    )
    body = _response_body(resolved)
    assert body["data"]["results"][0]["matched"] is True
    assert body["data"]["results"][0]["attachments"][0]["md_text"] == "# 内容"
    assert body["data"]["results"][1]["matched"] is False


@pytest.mark.anyio
async def test_document_entry_crud_list_and_export_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user()
    monkeypatch.setattr(api, "_require_user", Mock())
    department = _department()
    entry = _entry(department.id)

    db = _Db(_Result(department), _Result(entry))
    created = await api.create_document_entry(
        CreateDocumentEntryRequest(
            department_id=department.id,
            seq_no=2,
            name="新文件",
            code="QA-002/01",
        ),
        db,
        user,
    )
    assert created.status_code == 200

    db = _Db(_Result(entry), _Result(entry))
    updated = await api.update_document_entry(
        entry.id,
        UpdateDocumentEntryRequest(name="更新文件"),
        db,
        user,
    )
    assert updated.status_code == 200
    assert entry.name == "更新文件"

    from app.platform.identity import data_scope

    monkeypatch.setattr(
        data_scope,
        "resolve_user_department_scope",
        AsyncMock(return_value=SimpleNamespace(is_all=True, department_names=[])),
    )
    db = _Db(_Result(1), _Result(rows=[entry]))
    listed = await api.list_document_entries(
        department_id=department.id,
        keyword="更新",
        page=1,
        page_size=10,
        db=db,
        current_user=user,
    )
    assert listed.status_code == 200
    assert _response_body(listed)["meta"]["total"] == 1

    monkeypatch.setattr(
        api,
        "export_document_catalog_docx",
        Mock(return_value=b"docx"),
    )
    export = await api.export_document_catalog(
        department_id=department.id,
        department_name="质量部",
        db=_Db(_Result(rows=[entry])),
        current_user=user,
    )
    assert export.status_code == 200
    assert export.body == b"docx"

    deleted = await api.delete_document_entry(entry.id, _Db(_Result(entry)), user)
    assert deleted.status_code == 200
    assert entry.is_deleted is True


@pytest.mark.anyio
async def test_attachment_upload_auto_bind_delete_preview_and_import_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user()
    monkeypatch.setattr(api, "_require_user", Mock())
    entry = _entry(uuid4())
    attachment = {
        "file_name": "偏差处理程序.pdf",
        "storage_key": "quality/entry/file.pdf",
        "content_type": "application/pdf",
        "file_size": 16,
        "converted": False,
    }
    monkeypatch.setattr(
        api, "validate_upload_metadata", Mock(return_value="偏差处理程序.pdf")
    )
    monkeypatch.setattr(api, "read_upload_with_limit", AsyncMock(return_value=b"pdf"))
    monkeypatch.setattr(api, "sniff_upload_mime", Mock(return_value="application/pdf"))
    monkeypatch.setattr(
        api, "upload_attachment_to_entry", AsyncMock(return_value=attachment)
    )

    db = _Db(_Result(entry), _Result(entry))
    uploaded = await api.upload_document_entry_attachment(entry.id, _upload(), db, user)
    assert uploaded.status_code == 200
    assert _response_body(uploaded)["data"]["attachment"]["storage_key"]

    monkeypatch.setattr(api, "find_entry_by_file_name", AsyncMock(return_value=None))
    not_bound = await api.auto_bind_document_entry_attachment(_upload(), _Db(), user)
    assert not_bound.status_code == 404

    monkeypatch.setattr(api, "find_entry_by_file_name", AsyncMock(return_value=entry))
    auto = await api.auto_bind_document_entry_attachment(
        _upload(), _Db(_Result(entry)), user
    )
    assert auto.status_code == 200

    monkeypatch.setattr(
        api, "delete_attachment_from_entry", AsyncMock(return_value=True)
    )
    removed = await api.delete_document_entry_attachment(
        entry.id, "quality/entry/file.pdf", _Db(_Result(entry)), user
    )
    assert removed.status_code == 200
    monkeypatch.setattr(
        api, "delete_attachment_from_entry", AsyncMock(return_value=False)
    )
    missing = await api.delete_document_entry_attachment(
        entry.id, "missing", _Db(_Result(entry)), user
    )
    assert missing.status_code == 404

    monkeypatch.setattr(
        api,
        "read_attachment_preview",
        Mock(return_value=(b"pdf", "application/pdf")),
    )
    preview = await api.get_document_entry_attachment_content(
        entry.id, "quality/entry/file.pdf", _Db(_Result(entry)), user
    )
    assert preview.status_code == 200
    assert preview.body == b"pdf"

    from app.modules.quality.service import (
        document_catalog_attachment as attachment_service,
    )

    monkeypatch.setattr(
        attachment_service,
        "match_entry_for_attachment",
        AsyncMock(return_value=(None, "none")),
    )
    monkeypatch.setattr(
        attachment_service,
        "upload_attachment_to_entry",
        AsyncMock(return_value=attachment),
    )
    batch = await api.batch_import_document_attachments([_upload()], _Db(), user)
    assert _response_body(batch)["data"]["failed"] == 1

    monkeypatch.setattr(
        attachment_service,
        "match_entry_for_attachment",
        AsyncMock(return_value=(entry, "exact")),
    )
    bound = await api.batch_import_document_attachments([_upload()], _Db(), user)
    assert _response_body(bound)["data"]["bound"] == 1
