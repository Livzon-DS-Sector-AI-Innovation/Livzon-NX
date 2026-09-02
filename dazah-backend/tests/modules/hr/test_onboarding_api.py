"""入职台账（飞书多维 tblK1IWXATe2Nn2q）接口测试。

覆盖重做后的核心能力（全部 mock 飞书，不连真实外部服务）：
- 列表返回附件字段结构（file_token/name）
- 删除记录（DELETE /onboarding/{id}）
- 附件上传（POST /onboarding/attachments）
- 附件预览代理（GET /onboarding/{id}/attachments/{token}/content）：
  归属校验通过返回内容，非归属 token 返回 403
- 更新附件字段（PUT /onboarding/{id}）
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.modules.hr import recruitment_repository as repo_mod

# 最小合法 PNG：8 字节签名 + 16 字节占位（upload_security 校验魔数）
PNG_SAMPLE_BYTES = bytes.fromhex("89504e470d0a1a0a") + b"0" * 16

RECORDS = [
    {
        "record_id": "rec_x",
        "fields": {
            "姓名": [{"text": "张三", "type": "text"}],
            "入职日期": 1700000000000,
            "入职部门": "行政部",
            "岗位": "专员",
            "离职证明附件": [{"file_token": "tok_a", "name": "a.png", "type": "png"}],
            "身份信息附件": [{"file_token": "tok_b", "name": "b.pdf", "type": "pdf"}],
            "学历证书附件": [],
            "其他": [],
        },
    },
]


class _FakeFeishuClient:
    async def download_file(self, file_token: str) -> bytes:
        return b"FAKE-BYTES"


class _FakeBitable:
    def __init__(self) -> None:
        self.deleted: str | None = None
        self.updated: tuple[str, dict] | None = None
        self.client = _FakeFeishuClient()

    async def search_records(self, table_id: str, **kwargs):
        return RECORDS

    async def delete_record(self, table_id: str, record_id: str) -> None:
        self.deleted = record_id

    async def update_record(self, table_id: str, record_id: str, fields: dict) -> dict:
        self.updated = (record_id, fields)
        return {"record": {"record_id": record_id}}

    async def create_record(self, table_id: str, fields: dict) -> dict:
        return {"record": {"record_id": "rec_new"}}

    async def upload_attachment(self, file_name: str, file_bytes: bytes) -> str:
        return "fake_token_upload"


@pytest.fixture
def mock_bitable(monkeypatch: pytest.MonkeyPatch) -> _FakeBitable:
    fake = _FakeBitable()

    async def _fake_get_client(self):
        return fake

    monkeypatch.setattr(
        repo_mod.RecruitmentBitableRepo, "_get_client", _fake_get_client
    )
    return fake


async def test_list_onboarding_returns_attachment_fields(
    client: AsyncClient, mock_bitable: _FakeBitable,
) -> None:
    resp = await client.get("/api/v1/hr/onboarding")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data[0]["name"] == "张三"
    assert data[0]["department"] == "行政部"
    assert data[0]["resignation_attachment"][0]["file_token"] == "tok_a"
    assert data[0]["resignation_attachment"][0]["name"] == "a.png"
    assert data[0]["id_attachment"][0]["file_token"] == "tok_b"


async def test_delete_onboarding(
    client: AsyncClient, mock_bitable: _FakeBitable,
) -> None:
    resp = await client.delete("/api/v1/hr/onboarding/rec_x")
    assert resp.status_code == 200
    assert mock_bitable.deleted == "rec_x"


async def test_upload_onboarding_attachment(
    client: AsyncClient, mock_bitable: _FakeBitable,
) -> None:
    resp = await client.post(
        "/api/v1/hr/onboarding/attachments",
        # 真实 PNG 魔数头（upload_security 会校验文件实际格式）
        files={"file": ("photo.png", PNG_SAMPLE_BYTES, "image/png")},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["file_token"] == "fake_token_upload"
    assert data["name"] == "photo.png"


async def test_attachment_content_ok(
    client: AsyncClient, mock_bitable: _FakeBitable,
) -> None:
    resp = await client.get("/api/v1/hr/onboarding/rec_x/attachments/tok_a/content")
    assert resp.status_code == 200
    assert resp.content == b"FAKE-BYTES"
    assert "image/png" in (resp.headers.get("content-type") or "")


async def test_attachment_content_rejects_unowned_token(
    client: AsyncClient, mock_bitable: _FakeBitable,
) -> None:
    resp = await client.get("/api/v1/hr/onboarding/rec_x/attachments/tok_evil/content")
    assert resp.status_code == 403


async def test_update_onboarding_with_attachment_field(
    client: AsyncClient, mock_bitable: _FakeBitable,
) -> None:
    resp = await client.put(
        "/api/v1/hr/onboarding/rec_x",
        json={
            "name": "张三",
            "department": "质量部",
            "resignation_attachment": [{"file_token": "tok_c", "name": "c.png"}],
        },
    )
    assert resp.status_code == 200
    assert mock_bitable.updated is not None
    rid, fields = mock_bitable.updated
    assert rid == "rec_x"
    assert fields["入职部门"] == "质量部"
    assert fields["离职证明附件"] == [{"file_token": "tok_c", "name": "c.png"}]
