from pathlib import Path
import uuid

from services.dazah_agent_service import (
    AgentBackendSource,
    AgentBackendV2Request,
    AgentTrustedSubject,
    DazahAIAgent,
    _user_message_with_attachments,
)


def _payload(**values) -> AgentBackendV2Request:
    return AgentBackendV2Request(
        run_id=uuid.uuid4(),
        trace_id=uuid.uuid4(),
        session_id="web:session-1",
        subject=AgentTrustedSubject(
            tenant_id="test",
            user_id=str(uuid.uuid4()),
            source="web",
        ),
        source=AgentBackendSource(platform="web"),
        **values,
    )


def test_dazah_proxy_keeps_multimodal_message_parts() -> None:
    agent = object.__new__(DazahAIAgent)
    assert agent._model_supports_vision() is True


def test_document_attachment_is_added_as_user_content() -> None:
    payload = _payload(
        message="请总结",
        attachments=[
            {
                "filename": "记录.txt",
                "content_type": "text/plain",
                "size": 12,
                "kind": "document",
                "text": "批次状态正常",
            }
        ],
    )

    content = _user_message_with_attachments(payload)

    assert isinstance(content, str)
    assert "记录.txt" in content
    assert "批次状态正常" in content


def test_image_attachment_builds_multimodal_user_content() -> None:
    payload = _payload(
        message="识别图片",
        attachments=[
            {
                "filename": "现场.png",
                "content_type": "image/png",
                "size": 3,
                "kind": "image",
                "data_base64": "YWJj",
            }
        ],
    )

    content = _user_message_with_attachments(payload)

    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert content[1]["image_url"]["url"] == "data:image/png;base64,YWJj"


def test_gateway_cached_image_is_loaded_only_from_hermes_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    image_path = tmp_path / "cache" / "images" / "现场.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"abc")
    payload = _payload(
        message="识别图片",
        attachments=[
            {
                "filename": "现场.png",
                "content_type": "image/png",
                "kind": "image",
                "local_path": str(image_path),
            }
        ],
    )

    content = _user_message_with_attachments(payload)

    assert isinstance(content, list)
    assert content[1]["image_url"]["url"] == "data:image/png;base64,YWJj"


def test_gateway_attachment_rejects_path_outside_hermes_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    outside = tmp_path / "outside.txt"
    outside.write_text("sensitive", encoding="utf-8")
    payload = _payload(
        message="读取附件",
        attachments=[
            {
                "filename": "outside.txt",
                "content_type": "text/plain",
                "kind": "document",
                "local_path": str(outside),
            }
        ],
    )

    content = _user_message_with_attachments(payload)

    assert isinstance(content, str)
    assert "附件不可读取" in content
    assert "sensitive" not in content
