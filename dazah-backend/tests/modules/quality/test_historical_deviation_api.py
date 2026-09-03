"""历史偏差 API 接口测试（AsyncClient 真调路由 + mock llm_client）。"""

from __future__ import annotations

import io
from collections.abc import AsyncIterator
from types import SimpleNamespace as _SimpleNamespace
from typing import Any

import pytest
from docx import Document
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import LLMConfigError, LLMOutputError

SimpleNamespace: Any = _SimpleNamespace


@pytest.fixture(autouse=True)
def _disable_minio(monkeypatch: pytest.MonkeyPatch) -> None:
    """本地测试环境无 MinIO 容器，降级为本地存储路径（外部依赖按规范 mock）。"""
    monkeypatch.setattr(
        "app.modules.quality.service.quality_attachment.minio_enabled",
        lambda: False,
    )


@pytest.fixture(autouse=True)
async def _clean_historical_deviations(db_session: AsyncSession) -> AsyncIterator[Any]:
    await db_session.execute(text("CREATE SCHEMA IF NOT EXISTS quality"))
    await db_session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS quality.historical_deviations (
                id UUID PRIMARY KEY,
                code VARCHAR(255) NOT NULL,
                deviation_event TEXT NULL,
                deviation_content TEXT NULL,
                direct_cause TEXT NULL,
                root_cause TEXT NULL,
                investigation_conclusion TEXT NULL,
                attachments JSON NULL,
                ai_extract_payload JSON NULL,
                remark TEXT NULL,
                deleted_by UUID NULL,
                deleted_at TIMESTAMPTZ NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                created_by UUID NULL,
                updated_by UUID NULL,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE
            )
            """
        )
    )
    await db_session.execute(text("DELETE FROM quality.historical_deviations"))
    await db_session.commit()
    yield
    await db_session.execute(text("DELETE FROM quality.historical_deviations"))
    await db_session.commit()


def _build_docx_bytes(text_value: str) -> bytes:
    document = Document()
    document.add_paragraph(text_value)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _async_config_stub() -> SimpleNamespace:
    return SimpleNamespace(model_name="test-model")


async def _create_record(
    client: AsyncClient,
    *,
    deviation_event: str = "灌装压塞压力超上限",
    deviation_content: str = "压塞机压力异常",
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/quality/historical-deviations",
        json={
            "deviation_event": deviation_event,
            "deviation_content": deviation_content,
            "direct_cause": None,
            "root_cause": None,
            "investigation_conclusion": None,
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


@pytest.mark.anyio
async def test_create_and_list_historical_deviation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    created = await _create_record(client)
    assert created["code"].startswith("HD-")
    assert created["deviation_event"] == "灌装压塞压力超上限"
    assert created["attachment_count"] == 0

    response = await client.get(
        "/api/v1/quality/historical-deviations",
        params={"keyword": "压塞"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] >= 1
    assert any(item["code"] == created["code"] for item in body["data"])


@pytest.mark.anyio
async def test_get_update_delete_historical_deviation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    created = await _create_record(client)
    record_id = created["id"]

    detail = await client.get(f"/api/v1/quality/historical-deviations/{record_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["id"] == record_id

    updated = await client.put(
        f"/api/v1/quality/historical-deviations/{record_id}",
        json={
            "deviation_event": "灌装压塞压力超上限（复核）",
            "deviation_content": created["deviation_content"],
            "direct_cause": "传感器漂移",
            "root_cause": "未定期校准",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["root_cause"] == "未定期校准"

    deleted = await client.delete(
        f"/api/v1/quality/historical-deviations/{record_id}"
    )
    assert deleted.status_code == 200
    gone = await client.get(f"/api/v1/quality/historical-deviations/{record_id}")
    assert gone.status_code == 404


@pytest.mark.anyio
async def test_upload_and_delete_attachment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    created = await _create_record(client)
    record_id = created["id"]
    content = _build_docx_bytes(
        "调查补充：压塞压力传感器显示 0.45MPa，超出 0.40 上限。"
    )

    upload = await client.post(
        f"/api/v1/quality/historical-deviations/{record_id}/attachments",
        files={
            "file": (
                "investigation.docx",
                content,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert upload.status_code == 200
    attachment = upload.json()["data"]
    assert attachment["file_name"] == "investigation.docx"
    assert attachment["converted"] is True
    assert attachment["url"]

    # 读取转换后标准 MD 内容
    content_resp = await client.get(attachment["url"])
    assert content_resp.status_code == 200
    assert content_resp.headers["content-type"].startswith("text/markdown")

    detail = await client.get(f"/api/v1/quality/historical-deviations/{record_id}")
    assert detail.json()["data"]["attachment_count"] == 1

    deleted = await client.delete(
        f"/api/v1/quality/historical-deviations/{record_id}/attachments/{attachment['id']}"
    )
    assert deleted.status_code == 200
    detail_after = await client.get(
        f"/api/v1/quality/historical-deviations/{record_id}"
    )
    assert detail_after.json()["data"]["attachment_count"] == 0


@pytest.mark.anyio
async def test_upload_derives_pc_code_from_filename(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    created = await _create_record(client)
    record_id = created["id"]
    # 上传文件名含 PC-YYMMNNN，上传后 code 应回填为 PC 编号
    response = await client.post(
        f"/api/v1/quality/historical-deviations/{record_id}/attachments",
        files={
            "file": (
                "PC-2508001 液状石蜡重复测试.docx",
                _build_docx_bytes("偏差报告正文"),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 200
    detail = await client.get(f"/api/v1/quality/historical-deviations/{record_id}")
    assert detail.json()["data"]["code"] == "PC-2508001"


@pytest.mark.anyio
async def test_batch_import_historical_deviations(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fake_chat_json(
        self: Any,  # noqa: ANN001
        messages: list[dict[Any, Any]],
        expected_keys: Any = None,  # noqa: ANN001
        temperature: Any = None,  # noqa: ANN001
        config_type: Any = "text",  # noqa: ANN001
    ) -> dict[str, Any]:
        return {
            "deviation_event": "灌装压塞压力超上限",
            "deviation_content": "人：操作未复核；机：传感器漂移",
            "direct_cause": "传感器漂移",
            "root_cause": "未建立校准机制",
        }

    async def _async_config(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        return _async_config_stub()

    monkeypatch.setattr("app.core.llm.client.LLMClient.chat_json", _fake_chat_json)
    monkeypatch.setattr(
        "app.modules.quality.service.historical_deviation.get_config", _async_config
    )

    doc_a = _build_docx_bytes("偏差A：压塞压力异常。")
    doc_b = _build_docx_bytes("偏差B：灌装异物。")
    response = await client.post(
        "/api/v1/quality/historical-deviations/batch-import",
        files=[
            (
                "files",
                (
                    "PC-2508002 偏差A.docx",
                    doc_a,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
            ),
            (
                "files",
                (
                    "PC-2508003 偏差B.docx",
                    doc_b,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
            ),
        ],
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 2
    assert data["succeeded"] == 2
    assert data["failed"] == 0
    codes = {r["code"] for r in data["results"]}
    assert codes == {"PC-2508002", "PC-2508003"}


@pytest.mark.anyio
async def test_ai_extract_historical_deviation_success(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = await _create_record(client)
    record_id = created["id"]
    await client.post(
        f"/api/v1/quality/historical-deviations/{record_id}/attachments",
        files={
            "file": (
                "report.docx",
                _build_docx_bytes("灌装线压塞压力超上限，胶塞来料批次差异。"),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    async def _fake_chat_json(
        self: Any,  # noqa: ANN001
        messages: list[dict[Any, Any]],
        expected_keys: Any = None,  # noqa: ANN001
        temperature: Any = None,  # noqa: ANN001
        config_type: Any = "text",  # noqa: ANN001
    ) -> dict[str, Any]:
        return {
            "deviation_event": "灌装压塞压力超上限",
            "deviation_content": "人：操作人员未复核；机：传感器漂移",
            "direct_cause": "压塞压力传感器漂移",
            "root_cause": "未建立传感器定期校准机制",
        }

    monkeypatch.setattr(
        "app.core.llm.client.LLMClient.chat_json", _fake_chat_json
    )

    async def _async_config(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        return _async_config_stub()

    monkeypatch.setattr(
        "app.modules.quality.service.historical_deviation.get_config",
        _async_config,
    )

    response = await client.post(
        f"/api/v1/quality/historical-deviations/{record_id}/ai-extract"
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["direct_cause"] == "压塞压力传感器漂移"
    assert data["root_cause"] == "未建立传感器定期校准机制"
    assert data["ai_extract_payload"]["model_name"] == "test-model"


@pytest.mark.anyio
async def test_ai_extract_not_configured(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = await _create_record(client)
    record_id = created["id"]
    await client.post(
        f"/api/v1/quality/historical-deviations/{record_id}/attachments",
        files={
            "file": (
                "report.docx",
                _build_docx_bytes("灌装压塞压力超上限。"),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    def _raise_config(*_args: Any, **_kwargs: Any) -> Any:
        raise LLMConfigError("未配置")

    monkeypatch.setattr(
        "app.modules.quality.service.historical_deviation.get_config",
        _raise_config,
    )

    response = await client.post(
        f"/api/v1/quality/historical-deviations/{record_id}/ai-extract"
    )
    assert response.status_code == 503


@pytest.mark.anyio
async def test_ai_extract_output_error(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = await _create_record(client)
    record_id = created["id"]
    await client.post(
        f"/api/v1/quality/historical-deviations/{record_id}/attachments",
        files={
            "file": (
                "report.docx",
                _build_docx_bytes("灌装压塞压力超上限。"),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    async def _raise_output(
        self: Any,  # noqa: ANN001
        *args: Any,  # noqa: ANN002
        **kwargs: Any,  # noqa: ANN003
    ) -> dict[str, Any]:
        raise LLMOutputError("输出格式错误")

    monkeypatch.setattr(
        "app.core.llm.client.LLMClient.chat_json", _raise_output
    )

    async def _async_config(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        return _async_config_stub()

    monkeypatch.setattr(
        "app.modules.quality.service.historical_deviation.get_config",
        _async_config,
    )

    response = await client.post(
        f"/api/v1/quality/historical-deviations/{record_id}/ai-extract"
    )
    assert response.status_code == 502
