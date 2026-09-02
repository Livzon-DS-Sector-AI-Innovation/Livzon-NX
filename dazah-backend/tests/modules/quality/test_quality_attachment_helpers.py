"""quality_attachment 共享 helper 测试：路径安全、存储读写、编号生成、key 清理。"""

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import AppException
from app.modules.quality.models import HistoricalDeviation
from app.modules.quality.service import quality_attachment as svc


@pytest.fixture
def no_minio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "minio_enabled", lambda: False)


@pytest.fixture
def temp_upload_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> Any:
    settings = MagicMock()
    settings.UPLOAD_DIR = str(tmp_path)
    monkeypatch.setattr(svc, "get_settings", lambda: settings)
    return tmp_path


def test_persisted_user_id() -> None:
    assert svc.persisted_user_id("system") is None
    assert svc.persisted_user_id("not-a-uuid") is None
    assert svc.persisted_user_id(None) is None
    uid = str(uuid.uuid4())
    assert svc.persisted_user_id(uid) == uuid.UUID(uid)


def test_attachment_storage_keys() -> None:
    assert svc.attachment_storage_keys(
        {
            "storage_key": "orig",
            "converted_md_key": "md",
            "asset_keys": ["a1", "a1", "a2", ""],
        }
    ) == ["orig", "md", "a1", "a2"]
    # converted 与 asset 重复 key 去重
    assert svc.attachment_storage_keys(
        {"storage_key": "k", "converted_md_key": "k", "asset_keys": ["k"]}
    ) == ["k"]
    assert svc.attachment_storage_keys({}) == []


def test_read_md_text(no_minio: None, temp_upload_dir: Any) -> None:
    svc.store_file("test", "ok.md", "# 内容".encode(), "text/markdown")
    assert svc.read_md_text("test", "ok.md") == "# 内容"
    assert svc.read_md_text("test", "missing.md") == ""
    # 非 UTF-8 → 空字符串
    svc.store_file("test", "bin.md", b"\xff\xfe", "application/octet-stream")
    assert svc.read_md_text("test", "bin.md") == ""


def test_store_read_delete_file(no_minio: None, temp_upload_dir: Any) -> None:
    key = svc.store_file("t", "a/b.txt", b"hello", "text/plain")
    assert key == "a/b.txt"
    data, _ = svc.read_file("t", "a/b.txt")
    assert data == b"hello"
    assert svc.read_file("t", "nonexistent") is None
    svc.delete_file("t", "a/b.txt")
    assert svc.read_file("t", "a/b.txt") is None
    # 删除不存在的 key 不报错
    svc.delete_file("t", "still-not-there")


def test_safe_path_rejects_traversal(
    no_minio: None, temp_upload_dir: Any
) -> None:
    with pytest.raises(AppException, match="非法文件路径"):
        svc._safe_path("t", "../../etc/passwd")
    with pytest.raises(AppException, match="非法文件路径"):
        svc._safe_path("t", ".")


@pytest.mark.asyncio
async def test_generate_code_sequences() -> None:
    result = MagicMock()
    month = datetime.now(UTC).strftime("%Y%m")
    result.scalars.return_value.all.return_value = [
        f"HD-{month}001", f"HD-{month}005"
    ]
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    code = await svc.generate_code(session, HistoricalDeviation, "HD")
    assert code.startswith("HD-")
    # 编号递增：已有 005 → 006
    assert code.endswith("006")


@pytest.mark.asyncio
async def test_generate_code_empty() -> None:
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    code = await svc.generate_code(session, HistoricalDeviation, "WB")
    assert code.endswith("001")
