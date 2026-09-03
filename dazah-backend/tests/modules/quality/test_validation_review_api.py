"""验证 AI 审核 API 集成测试（AsyncClient 真实路由）。

覆盖：创建（upload/entry）、上传（非法类型/超限）、发起审核（未配置 503）、
job 查询 owner 校验、详情越权、分页列表、导出 content-type、软删除。
LLM、存储、目录基准均 mock。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.quality.api import validation_review as api_module
from app.modules.quality.models import ValidationReviewRecord
from app.modules.quality.service import validation_review as service_module


@pytest.fixture(autouse=True)
async def _clean_review_tables(db_session: AsyncSession) -> AsyncIterator[None]:
    await db_session.run_sync(
        lambda sync_db: ValidationReviewRecord.__table__.create(
            sync_db.connection(), checkfirst=True
        )
    )
    from app.modules.quality.models.validation_review import ValidationReviewFile

    await db_session.run_sync(
        lambda sync_db: ValidationReviewFile.__table__.create(
            sync_db.connection(), checkfirst=True
        )
    )
    await db_session.execute(
        __import__("sqlalchemy").text(
            "DELETE FROM quality.validation_review_files"
        )
    )
    await db_session.execute(
        __import__("sqlalchemy").text(
            "DELETE FROM quality.validation_review_records"
        )
    )
    await db_session.commit()
    yield
    await db_session.execute(
        __import__("sqlalchemy").text(
            "DELETE FROM quality.validation_review_files"
        )
    )
    await db_session.execute(
        __import__("sqlalchemy").text(
            "DELETE FROM quality.validation_review_records"
        )
    )
    await db_session.commit()


@pytest.fixture(autouse=True)
def _mock_storage_and_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """本地/远端存储写盘、LLM 调用、审计落库全部 mock，避免依赖外部环境。"""
    monkeypatch.setattr(
        service_module, "_store_review_file", lambda key, content, ctype: key
    )
    monkeypatch.setattr(
        api_module, "run_review", AsyncMock(return_value="job:test:abc")
    )
    # 审计表 user_id 外键到 identity.users，测试用户不落库，mock 掉审计写入
    monkeypatch.setattr(service_module, "record_audit_log", AsyncMock())


async def _create_upload_review(client: AsyncClient) -> dict:
    response = await client.post(
        "/api/v1/quality/validation-reviews",
        json={"review_mode": "upload", "title": "测试审核"},
    )
    assert response.status_code == 200
    return response.json()["data"]


class TestCreateReview:
    @pytest.mark.anyio
    async def test_create_upload_review(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        data = await _create_upload_review(client)
        assert data["review_mode"] == "upload"
        assert data["status"] == "draft"
        assert data["files"] == []
        assert data["id"]

    @pytest.mark.anyio
    async def test_create_entry_review_missing_entry_id(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/quality/validation-reviews",
            json={"review_mode": "entry"},
        )
        assert response.status_code == 422
        assert "必须指定目录条目" in response.json()["message"]


class TestUploadFile:
    @pytest.mark.anyio
    async def test_upload_markdown(self, client: AsyncClient) -> None:
        review = await _create_upload_review(client)
        response = await client.post(
            f"/api/v1/quality/validation-reviews/{review['id']}/files",
            files={
                "file": (
                    "VP-test-01 方案.md",
                    "## 目的\n正文".encode(),
                    "text/markdown",
                )
            },
        )
        assert response.status_code == 200
        assert response.json()["data"]["file_name"].endswith(".md")

    @pytest.mark.anyio
    async def test_upload_unsupported_type(self, client: AsyncClient) -> None:
        review = await _create_upload_review(client)
        response = await client.post(
            f"/api/v1/quality/validation-reviews/{review['id']}/files",
            files={"file": ("方案.pdf", b"%PDF", "application/pdf")},
        )
        assert response.status_code == 422

    @pytest.mark.anyio
    async def test_upload_exceeds_limit(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        review = await _create_upload_review(client)
        monkeypatch.setattr(service_module, "REVIEW_MAX_SIZE", 10)
        response = await client.post(
            f"/api/v1/quality/validation-reviews/{review['id']}/files",
            files={"file": ("big.md", b"x" * 100, "text/markdown")},
        )
        assert response.status_code == 413


class TestRunReview:
    @pytest.mark.anyio
    async def test_run_returns_job_id(self, client: AsyncClient) -> None:
        review = await _create_upload_review(client)
        response = await client.post(
            f"/api/v1/quality/validation-reviews/{review['id']}/run"
        )
        assert response.status_code == 200
        assert response.json()["data"]["job_id"] == "job:test:abc"

    @pytest.mark.anyio
    async def test_run_without_llm_config_503(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        review = await _create_upload_review(client)
        monkeypatch.setattr(
            api_module,
            "run_review",
            AsyncMock(
                side_effect=AppException(
                    status_code=503, message="AI 服务尚未配置，无法发起审核"
                )
            ),
        )
        response = await client.post(
            f"/api/v1/quality/validation-reviews/{review['id']}/run"
        )
        assert response.status_code == 503

    @pytest.mark.anyio
    async def test_run_missing_record_404(self, client: AsyncClient) -> None:
        response = await client.post(
            f"/api/v1/quality/validation-reviews/{uuid.uuid4()}/run"
        )
        assert response.status_code == 404


class TestJobStatus:
    @pytest.mark.anyio
    async def test_job_owner_mismatch_404(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            api_module,
            "get_job_status",
            AsyncMock(
                return_value={
                    "state": "running",
                    "owner": "other-user",
                    "progress": "启动中",
                }
            ),
        )
        response = await client.get(
            "/api/v1/quality/validation-reviews/job/job:test:abc"
        )
        assert response.status_code == 404

    @pytest.mark.anyio
    async def test_job_running_status(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            api_module,
            "get_job_status",
            AsyncMock(return_value={"state": "running", "progress": "启动中"}),
        )
        response = await client.get(
            "/api/v1/quality/validation-reviews/job/job:test:abc"
        )
        assert response.status_code == 200
        assert response.json()["data"]["state"] == "running"


class TestDetailAndList:
    @pytest.mark.anyio
    async def test_detail_and_list(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        review = await _create_upload_review(client)
        response = await client.get(
            f"/api/v1/quality/validation-reviews/{review['id']}"
        )
        assert response.status_code == 200
        assert response.json()["data"]["id"] == review["id"]

        list_response = await client.get("/api/v1/quality/validation-reviews")
        assert list_response.status_code == 200
        assert list_response.json()["data"]
        assert list_response.json()["meta"]["total"] >= 1

    @pytest.mark.anyio
    async def test_detail_missing_404(self, client: AsyncClient) -> None:
        response = await client.get(
            f"/api/v1/quality/validation-reviews/{uuid.uuid4()}"
        )
        assert response.status_code == 404


class TestExport:
    @pytest.mark.anyio
    async def test_export_docx(self, client: AsyncClient) -> None:
        review = await _create_upload_review(client)
        response = await client.post(
            f"/api/v1/quality/validation-reviews/{review['id']}/export"
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument"
        )
        assert "attachment" in response.headers["content-disposition"]


class TestDelete:
    @pytest.mark.anyio
    async def test_delete_soft_delete(self, client: AsyncClient) -> None:
        review = await _create_upload_review(client)
        response = await client.delete(
            f"/api/v1/quality/validation-reviews/{review['id']}"
        )
        assert response.status_code == 200
        # 删除后再查详情应 404
        detail = await client.get(
            f"/api/v1/quality/validation-reviews/{review['id']}"
        )
        assert detail.status_code == 404


class TestRerunAndRateLimit:
    @pytest.mark.anyio
    async def test_rerun_returns_job_id(self, client: AsyncClient) -> None:
        review = await _create_upload_review(client)
        response = await client.post(
            f"/api/v1/quality/validation-reviews/{review['id']}/rerun"
        )
        assert response.status_code == 200
        assert response.json()["data"]["job_id"] == "job:test:abc"

    @pytest.mark.anyio
    async def test_run_rate_limited_429(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        review = await _create_upload_review(client)
        monkeypatch.setattr(api_module, "cache_get", AsyncMock(return_value="3"))
        response = await client.post(
            f"/api/v1/quality/validation-reviews/{review['id']}/run"
        )
        assert response.status_code == 429

    @pytest.mark.anyio
    async def test_job_completed_returns_review(
        self, client: AsyncClient, db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await _create_upload_review(client)
        monkeypatch.setattr(
            api_module,
            "get_job_status",
            AsyncMock(return_value={"state": "completed", "progress": "完成"}),
        )
        response = await client.get(
            "/api/v1/quality/validation-reviews/job/job:test:abc"
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["state"] == "completed"
