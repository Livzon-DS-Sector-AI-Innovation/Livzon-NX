"""Bitable 写接口 user_id_type 透传与 union_id 自动识别。

人事应用目录选人后写其他应用（质量）多维表格成员字段必须用 union_id
命名空间；fields_need_union_user_id 负责按字段值判定，create/update 负责
透传 query 参数。
"""

from __future__ import annotations

from typing import Any

import pytest

from app.platform.integrations.feishu.bitable import (
    BitableClient,
    fields_need_union_user_id,
)


class _FakeFeishuClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"method": method, "path": path, **kwargs})
        return {"record": {"record_id": "rec-1"}}


def _client() -> tuple[BitableClient, _FakeFeishuClient]:
    fake = _FakeFeishuClient()
    client = BitableClient.__new__(BitableClient)
    client.app_token = "app-token"
    client.client = fake  # type: ignore[attr-defined]
    return client, fake


def test_fields_need_union_user_id_detects_on_prefix() -> None:
    assert fields_need_union_user_id(
        {"负责人": [{"id": "on_union_1"}]}
    ) is True
    assert fields_need_union_user_id(
        {"负责人": [{"id": "ou_open_1"}]}
    ) is False
    assert fields_need_union_user_id({"标题": "x", "人数": 3}) is False
    assert fields_need_union_user_id(
        {"混合": [{"id": "ou_a"}, {"id": "on_b"}]}
    ) is True


@pytest.mark.anyio
async def test_create_record_passes_user_id_type_param() -> None:
    client, fake = _client()
    await client.create_record("tbl-1", {"a": 1}, user_id_type="union_id")
    call = fake.calls[0]
    assert call["method"] == "POST"
    assert call["params"] == {"user_id_type": "union_id"}
    assert call["json"] == {"fields": {"a": 1}}


@pytest.mark.anyio
async def test_create_record_default_open_id_param() -> None:
    client, fake = _client()
    await client.create_record("tbl-1", {"a": 1})
    assert fake.calls[0]["params"] == {"user_id_type": "open_id"}
