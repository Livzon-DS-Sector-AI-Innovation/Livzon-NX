"""安全知识库本地附件管理测试（上传/删除/下载/预览与安全校验）。"""

import io

import pytest
from fastapi import FastAPI, UploadFile
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.database import get_db
from app.core.exceptions import AppException
from app.modules.safety.api import knowledge as api
from app.modules.safety.models import SafetyKnowledgeArticle
from app.modules.safety.service.knowledge import KnowledgeService


def _file(name: str, content: bytes) -> UploadFile:
    return UploadFile(filename=name, file=io.BytesIO(content))


async def _seed_article(db_session, *, feishu: bool = False, attachments=None):
    row = SafetyKnowledgeArticle(
        title="本地手册",
        status="published",
        feishu_record_id="recX" if feishu else None,
        local_attachments=list(attachments or []),
    )
    db_session.add(row)
    await db_session.commit()
    return row


@pytest.fixture(autouse=True)
async def _clean(db_session):
    yield
    await db_session.execute(delete(SafetyKnowledgeArticle))
    await db_session.commit()


# ── Service ──


async def test_add_and_remove_local_attachment(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.modules.safety.service.knowledge.KNOWLEDGE_UPLOAD_DIR",
        str(tmp_path / "up"),
    )
    row = await _seed_article(db_session)
    service = KnowledgeService(db_session)

    item = await service.add_local_attachments(
        row.id, [_file("手册.pdf", b"%PDF-1.4 fake")]
    )
    assert item.local_attachments and item.local_attachments[0]["name"] == "手册.pdf"
    token = item.local_attachments[0]["token"]

    # 磁盘文件存在且可解析
    path, _ = service.resolve_local_attachment(row.id, token)
    assert path.is_file() and path.read_bytes() == b"%PDF-1.4 fake"

    item = await service.remove_local_attachment(row.id, token)
    assert not (item.local_attachments or [])
    assert not path.exists()


async def test_add_attachment_rejects_mirrored_article(db_session):
    row = await _seed_article(db_session, feishu=True)
    service = KnowledgeService(db_session)
    with pytest.raises(AppException) as exc_info:
        await service.add_local_attachments(row.id, [_file("a.pdf", b"x")])
    assert "飞书" in str(exc_info.value.message)


async def test_add_attachment_rejects_bad_type_and_oversize(
    db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "app.modules.safety.service.knowledge.KNOWLEDGE_UPLOAD_DIR",
        str(tmp_path / "up"),
    )
    row = await _seed_article(db_session)
    service = KnowledgeService(db_session)

    with pytest.raises(AppException):
        await service.add_local_attachments(row.id, [_file("恶意.exe", b"MZ")])

    from app.modules.safety.service import knowledge as svc_mod

    monkeypatch.setattr(svc_mod, "LOCAL_ATTACHMENT_MAX_BYTES", 10)
    with pytest.raises(AppException):
        await service.add_local_attachments(row.id, [_file("大文件.pdf", b"x" * 20)])


async def test_resolve_attachment_rejects_forged_token(
    db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "app.modules.safety.service.knowledge.KNOWLEDGE_UPLOAD_DIR",
        str(tmp_path / "up"),
    )
    row = await _seed_article(db_session)
    service = KnowledgeService(db_session)
    await service.add_local_attachments(row.id, [_file("a.pdf", b"x")])

    with pytest.raises(AppException):
        service.resolve_local_attachment(row.id, "../../etc/passwd")
    with pytest.raises(AppException):
        service.resolve_local_attachment(row.id, "ZZZZnot-a-token")
    with pytest.raises(AppException):
        service.resolve_local_attachment(row.id, "deadbeef" * 4)


# ── API ──


@pytest.fixture
def sub_app(monkeypatch, tmp_path):
    application = FastAPI()
    application.include_router(api.knowledge_router, prefix="/api/v1/safety")
    application.dependency_overrides[get_db] = lambda: None
    # 上传目录指向临时目录，测试互不污染
    monkeypatch.setattr(
        "app.modules.safety.service.knowledge.KNOWLEDGE_UPLOAD_DIR",
        str(tmp_path / "up"),
    )
    return application


@pytest.fixture
def client(sub_app):
    return AsyncClient(transport=ASGITransport(app=sub_app), base_url="http://test")


async def test_upload_endpoint_persists_attachment(db_session, client, sub_app):
    row = await _seed_article(db_session)
    sub_app.dependency_overrides[get_db] = lambda: db_session

    resp = await client.post(
        f"/api/v1/safety/knowledge-articles/{row.id}/attachments",
        files=[("files", ("指南.pdf", b"%PDF-1.4 test", "application/pdf"))],
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["local_attachments"][0]["name"] == "指南.pdf"


async def test_delete_endpoint_removes_attachment(db_session, client, sub_app):
    row = await _seed_article(
        db_session, attachments=[{"token": "t" * 32, "name": "旧.pdf", "size": 3}]
    )
    sub_app.dependency_overrides[get_db] = lambda: db_session

    resp = await client.delete(
        f"/api/v1/safety/knowledge-articles/{row.id}/attachments/{'t' * 32}"
    )
    assert resp.status_code == 200
    await db_session.refresh(row)
    assert not (row.local_attachments or [])


async def test_download_and_preview_endpoints(db_session, client, sub_app, tmp_path):
    token = "a" * 32
    row = await _seed_article(
        db_session, attachments=[{"token": token, "name": "文件.pdf", "size": 5}]
    )
    up_dir = tmp_path / "up" / str(row.id)
    up_dir.mkdir(parents=True)
    (up_dir / f"{token}.pdf").write_bytes(b"%PDF-x")

    sub_app.dependency_overrides[get_db] = lambda: db_session
    resp = await client.get(
        f"/api/v1/safety/knowledge-articles/{row.id}/attachments/{token}/preview"
    )
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].startswith("inline")
    assert resp.headers["content-type"] == "application/pdf"

    resp = await client.get(
        f"/api/v1/safety/knowledge-articles/{row.id}/attachments/{token}/content"
    )
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].startswith("attachment")


async def test_attachment_of_missing_article_returns_404(client, sub_app, db_session):
    import uuid as uuid_mod

    sub_app.dependency_overrides[get_db] = lambda: db_session
    random_id = uuid_mod.uuid4()
    resp = await client.get(
        f"/api/v1/safety/knowledge-articles/{random_id}"
        f"/attachments/{'a' * 32}/content"
    )
    assert resp.status_code == 404
