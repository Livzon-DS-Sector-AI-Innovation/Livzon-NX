"""飞书记录不存在映射为 404 的测试（修复 RecordIdNotFound 返回 500）。

覆盖：
- _is_feishu_record_not_found helper 识别 1254043/RecordIdNotFound；
- get_inspection_feishu_attachment_content 对失效记录抛 NotFoundException（404）
  而非 RuntimeError（500）；
- 缩略图端点继承该行为：失效记录 thumbnail 返回 404（经 service → get_or_fetch）。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import NotFoundException
from app.modules.quality.service import inspection_feishu_crud as svc
from app.modules.quality.service.inspection_feishu_crud import (
    _is_feishu_record_not_found,
    get_inspection_feishu_attachment_content,
)


def test_is_feishu_record_not_found_detects_markers() -> None:
    assert _is_feishu_record_not_found(
        RuntimeError(
            "Feishu API error: code=1254043, msg=RecordIdNotFound, path=/bitable/..."
        )
    )
    assert _is_feishu_record_not_found(
        RuntimeError("Feishu API error: code=91403, msg=RecordIdNotFound")
    )
    assert not _is_feishu_record_not_found(
        RuntimeError("Feishu API error: code=1254302, msg=Forbidden")
    )
    assert not _is_feishu_record_not_found(ValueError("unrelated"))


class _FakeRuntime:
    app_id = "cli_1"
    app_secret = "secret_1"

    def is_enabled(self) -> bool:
        return True


class _FakeEntity:
    app_token = "app_token_1"
    table_id = "tbl_x"
    enable_push_to_feishu = True
    enable_pull_from_feishu = True


@pytest.mark.anyio
async def test_attachment_content_maps_record_not_found_to_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_record 命中已删除记录（飞书 RecordIdNotFound）应抛 404 而非 500。"""

    async def _resolve(db, entity_code, *, direction):
        return _FakeRuntime(), _FakeEntity()

    class _NotFoundBitable:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def get_record(self, table_id, record_id):
            raise RuntimeError(
                "Feishu API error: code=1254043, msg=RecordIdNotFound, "
                f"path=/bitable/v1/apps/x/tables/{table_id}/records/{record_id}"
            )

    monkeypatch.setattr(svc, "_resolve_runtime_entity", _resolve)
    monkeypatch.setattr(svc, "BitableClient", _NotFoundBitable)
    monkeypatch.setattr(svc, "_entity_table_id", lambda entity: "tbl_x")

    db = AsyncMock()
    with pytest.raises(NotFoundException):
        await get_inspection_feishu_attachment_content(
            db, "qc_solid_ys602", "rec_deleted", "ft_x"
        )


@pytest.mark.anyio
async def test_attachment_content_reraises_other_runtime_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非"记录不存在"类飞书 RuntimeError 原样上抛（仍 5xx，不静默降级）。"""

    async def _resolve(db, entity_code, *, direction):
        return _FakeRuntime(), _FakeEntity()

    class _ForbiddenBitable:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def get_record(self, table_id, record_id):
            raise RuntimeError(
                "Feishu API error: code=1254302, msg=Forbidden.NS_TableNotFound"
            )

    monkeypatch.setattr(svc, "_resolve_runtime_entity", _resolve)
    monkeypatch.setattr(svc, "BitableClient", _ForbiddenBitable)
    monkeypatch.setattr(svc, "_entity_table_id", lambda entity: "tbl_x")

    db = AsyncMock()
    with pytest.raises(RuntimeError):
        await get_inspection_feishu_attachment_content(
            db, "qc_solid_ys602", "rec_1", "ft_x"
        )
