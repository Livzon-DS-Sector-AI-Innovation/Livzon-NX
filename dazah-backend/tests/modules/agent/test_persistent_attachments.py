import base64
import hashlib
import uuid
from io import BytesIO
from types import SimpleNamespace

import pytest
from openpyxl import Workbook, load_workbook

from app.modules.agent.attachment_service import AgentAttachmentService
from app.modules.agent.service import AgentService


class FakeDb:
    async def flush(self) -> None:
        return None


class FailingDb:
    async def flush(self) -> None:
        raise RuntimeError("database flush failed")


class FakeRepo:
    def __init__(self) -> None:
        self.items: list[SimpleNamespace] = []

    async def create_attachment(self, _db, **values):
        attachment_id = values.pop("attachment_id")
        item = SimpleNamespace(
            id=attachment_id,
            **values,
            version=1,
            is_deleted=False,
            updated_by=values["user_id"],
        )
        self.items.append(item)
        return item

    async def list_session_attachments(self, _db, *, session_id, user_id, limit=50):
        return [
            item
            for item in self.items
            if item.session_id == session_id
            and item.user_id == user_id
            and not item.is_deleted
        ][:limit]

    async def get_session_attachment(self, _db, *, session_id, user_id, attachment_ref):
        for item in reversed(self.items):
            if (
                item.session_id == session_id
                and item.user_id == user_id
                and not item.is_deleted
                and attachment_ref in {str(item.id), item.filename}
            ):
                return item
        return None


def _xlsx_bytes() -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "销售"
    worksheet.append(["产品", "销量"])
    worksheet.append(["A", 10])
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


@pytest.mark.anyio
async def test_persist_cleans_up_object_when_database_flush_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.modules.agent.attachment_service as module

    objects: dict[str, tuple[bytes, str]] = {}

    def upload_object(_module, key, data, _length, content_type):
        objects[key] = (data, content_type)

    monkeypatch.setattr(module, "is_enabled", lambda: True)
    monkeypatch.setattr(module, "upload_object", upload_object)
    monkeypatch.setattr(module, "get_object", lambda _module, key: objects.get(key))
    monkeypatch.setattr(
        module, "delete_object", lambda _module, key: objects.pop(key, None)
    )

    with pytest.raises(RuntimeError, match="database flush failed"):
        await AgentAttachmentService(FakeRepo()).persist(
            FailingDb(),
            session_id=uuid.uuid4(),
            message_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            uploads=[
                {
                    "attachment_id": str(uuid.uuid4()),
                    "filename": "销售数据.xlsx",
                    "content_type": (
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                    "kind": "document",
                    "data": _xlsx_bytes(),
                    "text": "产品\t销量\nA\t10",
                }
            ],
        )

    assert objects == {}


@pytest.mark.anyio
async def test_persisted_attachment_can_be_read_mutated_and_deleted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.modules.agent.attachment_service as module

    objects: dict[str, tuple[bytes, str]] = {}

    def upload_object(_module, key, data, _length, content_type):
        objects[key] = (data, content_type)
        return key

    def get_object(_module, key):
        return objects.get(key)

    def delete_object(_module, key):
        objects.pop(key, None)

    monkeypatch.setattr(module, "is_enabled", lambda: True)
    monkeypatch.setattr(module, "upload_object", upload_object)
    monkeypatch.setattr(module, "get_object", get_object)
    monkeypatch.setattr(module, "delete_object", delete_object)

    repo = FakeRepo()
    service = AgentAttachmentService(repo)
    db = FakeDb()
    session_id = uuid.uuid4()
    user_id = uuid.uuid4()
    attachment_id = uuid.uuid4()
    raw = _xlsx_bytes()
    [attachment] = await service.persist(
        db,
        session_id=session_id,
        message_id=uuid.uuid4(),
        user_id=user_id,
        uploads=[
            {
                "attachment_id": str(attachment_id),
                "filename": "销售数据.xlsx",
                "content_type": (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ),
                "kind": "document",
                "data": raw,
                "text": "[工作表: 销售]\n产品\t销量\nA\t10",
            }
        ],
    )

    read = await service.read(
        db,
        session_id=session_id,
        user_id=user_id,
        attachment_ref="销售数据.xlsx",
        offset=0,
        limit=20_000,
    )
    assert "A\t10" in read["content"]
    assert attachment.sha256 == hashlib.sha256(raw).hexdigest()

    result = await service.mutate_tabular(
        db,
        session_id=session_id,
        user_id=user_id,
        attachment_ref=str(attachment_id),
        action="append_row",
        sheet_name="销售",
        row_number=None,
        values=["B", 20],
    )
    assert result["version"] == 2
    stored = load_workbook(BytesIO(objects[attachment.object_key][0]), read_only=True)
    assert list(stored["销售"].values)[-1] == ("B", 20)
    stored.close()

    await service.mutate_tabular(
        db,
        session_id=session_id,
        user_id=user_id,
        attachment_ref="销售数据.xlsx",
        action="update_row",
        sheet_name="销售",
        row_number=3,
        values=["B", 25],
    )
    await service.mutate_tabular(
        db,
        session_id=session_id,
        user_id=user_id,
        attachment_ref="销售数据.xlsx",
        action="delete_row",
        sheet_name="销售",
        row_number=2,
        values=[],
    )
    assert attachment.version == 4

    deleted = await service.delete(
        db,
        session_id=session_id,
        user_id=user_id,
        attachment_ref="销售数据.xlsx",
    )
    assert deleted["deleted"] is True
    assert attachment.is_deleted is True
    assert attachment.object_key not in objects


@pytest.mark.anyio
async def test_mutation_restores_object_when_database_flush_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.modules.agent.attachment_service as module

    objects: dict[str, tuple[bytes, str]] = {}

    def upload_object(_module, key, data, _length, content_type):
        objects[key] = (data, content_type)

    monkeypatch.setattr(module, "is_enabled", lambda: True)
    monkeypatch.setattr(module, "upload_object", upload_object)
    monkeypatch.setattr(module, "get_object", lambda _module, key: objects.get(key))
    monkeypatch.setattr(
        module, "delete_object", lambda _module, key: objects.pop(key, None)
    )

    repo = FakeRepo()
    service = AgentAttachmentService(repo)
    session_id = uuid.uuid4()
    user_id = uuid.uuid4()
    raw = _xlsx_bytes()
    [attachment] = await service.persist(
        FakeDb(),
        session_id=session_id,
        message_id=uuid.uuid4(),
        user_id=user_id,
        uploads=[
            {
                "attachment_id": str(uuid.uuid4()),
                "filename": "销售数据.xlsx",
                "content_type": (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ),
                "kind": "document",
                "data": raw,
                "text": "产品\t销量\nA\t10",
            }
        ],
    )

    with pytest.raises(RuntimeError, match="database flush failed"):
        await service.mutate_tabular(
            FailingDb(),
            session_id=session_id,
            user_id=user_id,
            attachment_ref=str(attachment.id),
            action="append_row",
            sheet_name="销售",
            row_number=None,
            values=["B", 20],
        )

    assert objects[attachment.object_key][0] == raw
    assert attachment.version == 1
    assert attachment.sha256 == hashlib.sha256(raw).hexdigest()


@pytest.mark.anyio
async def test_delete_restores_object_when_database_flush_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.modules.agent.attachment_service as module

    objects: dict[str, tuple[bytes, str]] = {}

    def upload_object(_module, key, data, _length, content_type):
        objects[key] = (data, content_type)

    monkeypatch.setattr(module, "is_enabled", lambda: True)
    monkeypatch.setattr(module, "upload_object", upload_object)
    monkeypatch.setattr(module, "get_object", lambda _module, key: objects.get(key))
    monkeypatch.setattr(
        module, "delete_object", lambda _module, key: objects.pop(key, None)
    )

    repo = FakeRepo()
    service = AgentAttachmentService(repo)
    session_id = uuid.uuid4()
    user_id = uuid.uuid4()
    raw = _xlsx_bytes()
    [attachment] = await service.persist(
        FakeDb(),
        session_id=session_id,
        message_id=uuid.uuid4(),
        user_id=user_id,
        uploads=[
            {
                "attachment_id": str(uuid.uuid4()),
                "filename": "销售数据.xlsx",
                "content_type": (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ),
                "kind": "document",
                "data": raw,
                "text": "产品\t销量\nA\t10",
            }
        ],
    )

    with pytest.raises(RuntimeError, match="database flush failed"):
        await service.delete(
            FailingDb(),
            session_id=session_id,
            user_id=user_id,
            attachment_ref=str(attachment.id),
        )

    assert objects[attachment.object_key][0] == raw
    assert attachment.is_deleted is False


def test_follow_up_restores_named_or_recent_attachment() -> None:
    attachment = SimpleNamespace(
        id=uuid.uuid4(),
        filename="销售数据.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        size=100,
        kind="document",
        extracted_text="产品\t销量\nA\t10",
    )

    named = AgentService._restored_attachments(
        [attachment], "把销售数据.xlsx写入目标文档"
    )
    recent = AgentService._restored_attachments([attachment], "修改刚才上传的文件")

    assert named[0]["text"] == "产品\t销量\nA\t10"
    assert recent[0]["attachment_id"] == str(attachment.id)


@pytest.mark.anyio
async def test_follow_up_materializes_persisted_image_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.modules.agent.attachment_service as module

    raw = b"\x89PNG\r\n\x1a\nimage"
    attachment = SimpleNamespace(
        id=uuid.uuid4(),
        filename="现场照片.png",
        content_type="image/png",
        size=len(raw),
        kind="image",
        object_key="sessions/user/session/image/source",
        sha256=hashlib.sha256(raw).hexdigest(),
        extracted_text=None,
    )
    monkeypatch.setattr(
        module,
        "get_object",
        lambda _module, _key: (raw, "image/png"),
    )

    restored = await AgentAttachmentService().materialize_for_context(
        [attachment],
        text_limit=50_000,
    )

    assert base64.b64decode(restored[0]["data_base64"]) == raw
    assert restored[0]["attachment_id"] == str(attachment.id)
