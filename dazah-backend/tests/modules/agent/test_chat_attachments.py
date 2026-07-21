import base64
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.modules.agent.schemas import AgentAttachmentIn, AgentChatRequest
from app.modules.agent.service import AgentService


@pytest.mark.asyncio
async def test_prepare_text_attachment_extracts_content_and_redacts_raw_data() -> None:
    raw = "偏差编号,DV-001\n状态,处理中".encode()
    request = AgentChatRequest(
        message="分析附件",
        attachments=[
            AgentAttachmentIn(
                filename="偏差.csv",
                content_type="text/csv",
                size=len(raw),
                data_base64=base64.b64encode(raw).decode(),
            )
        ],
    )

    prepared, metadata = await AgentService(SimpleNamespace())._prepare_attachments(
        request
    )

    assert prepared[0]["kind"] == "document"
    assert "DV-001" in prepared[0]["text"]
    assert metadata == [
        {
            "filename": "偏差.csv",
            "content_type": "text/csv",
            "size": len(raw),
            "kind": "document",
        }
    ]
    assert "data_base64" not in metadata[0]


@pytest.mark.asyncio
async def test_prepare_attachment_rejects_spoofed_image() -> None:
    raw = b"not-a-png"
    request = AgentChatRequest(
        message="分析附件",
        attachments=[
            AgentAttachmentIn(
                filename="现场.png",
                content_type="image/png",
                size=len(raw),
                data_base64=base64.b64encode(raw).decode(),
            )
        ],
    )

    with pytest.raises(HTTPException, match="实际格式"):
        await AgentService(SimpleNamespace())._prepare_attachments(request)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "content_type", "raw"),
    [
        ("现场.png", "image/png", b"\x89PNG\r\n\x1a\ncontent"),
        ("现场.jpg", "image/jpeg", b"\xff\xd8\xffcontent"),
        ("现场.jpeg", "image/jpeg", b"\xff\xd8\xffcontent"),
        ("现场.webp", "image/webp", b"RIFF\x00\x00\x00\x00WEBPcontent"),
        ("现场.gif", "image/gif", b"GIF89acontent"),
    ],
)
async def test_prepare_attachment_accepts_common_image_formats(
    filename: str,
    content_type: str,
    raw: bytes,
) -> None:
    request = AgentChatRequest(
        message="分析图片",
        attachments=[
            AgentAttachmentIn(
                filename=filename,
                content_type=content_type,
                size=len(raw),
                data_base64=base64.b64encode(raw).decode(),
            )
        ],
    )

    prepared, metadata = await AgentService(SimpleNamespace())._prepare_attachments(
        request
    )

    assert prepared[0]["kind"] == "image"
    assert prepared[0]["content_type"] == content_type
    assert metadata[0]["filename"] == filename


@pytest.mark.asyncio
async def test_prepare_attachments_enforces_total_limit() -> None:
    raw = b"a" * (7 * 1024 * 1024)
    encoded = base64.b64encode(raw).decode()
    request = AgentChatRequest(
        message="分析附件",
        attachments=[
            AgentAttachmentIn(
                filename=f"part-{index}.txt",
                content_type="text/plain",
                size=len(raw),
                data_base64=encoded,
            )
            for index in range(3)
        ],
    )

    with pytest.raises(HTTPException, match="总大小"):
        await AgentService(SimpleNamespace())._prepare_attachments(request)


def test_attachment_schema_enforces_per_file_limit() -> None:
    with pytest.raises(ValidationError):
        AgentAttachmentIn(
            filename="large.pdf",
            content_type="application/pdf",
            size=10 * 1024 * 1024 + 1,
            data_base64="YQ==",
        )
