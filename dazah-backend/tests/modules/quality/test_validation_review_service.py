"""验证 AI 审核 service 层单元测试。

mock LLM 客户端与目录基准，覆盖：创建/上传解析/审核编排/二次校验/
异常分支（未配置 503、LLM 输出非法、限流耗尽）。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.llm.exceptions import LLMConfigError, LLMRateLimitError
from app.modules.quality.models import ValidationReviewFile, ValidationReviewRecord
from app.modules.quality.service import validation_review as svc
from app.modules.quality.service.validation_basis_resolver import DocumentBasis

_REVIEW_TABLE = """
CREATE TABLE IF NOT EXISTS quality.validation_review_records (
    title VARCHAR(255) NOT NULL DEFAULT '',
    review_mode VARCHAR(20) NOT NULL DEFAULT 'upload',
    status VARCHAR(50) NOT NULL DEFAULT 'draft',
    error_message TEXT NULL,
    model_name VARCHAR(255) NULL,
    input_snapshot JSON NULL,
    output_payload JSON NULL,
    job_id VARCHAR(100) NULL,
    last_generated_at TIMESTAMPTZ NULL,
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by UUID NULL,
    updated_by UUID NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
)
"""
_FILE_TABLE = """
CREATE TABLE IF NOT EXISTS quality.validation_review_files (
    review_id UUID NOT NULL,
    doc_kind VARCHAR(20) NOT NULL DEFAULT 'plan',
    source VARCHAR(20) NOT NULL DEFAULT 'upload',
    file_name VARCHAR(255) NOT NULL,
    file_type VARCHAR(100) NOT NULL,
    file_size INTEGER NOT NULL,
    storage_key TEXT NOT NULL,
    parsed_text TEXT NULL,
    parse_status VARCHAR(50) NOT NULL DEFAULT 'pending',
    parse_error TEXT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by UUID NULL,
    updated_by UUID NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
)
"""


@pytest.fixture(autouse=True)
async def _clean_review_tables(db_session: AsyncSession) -> AsyncIterator[None]:
    await db_session.execute(text("CREATE SCHEMA IF NOT EXISTS quality"))
    await db_session.execute(text(_REVIEW_TABLE))
    await db_session.execute(text(_FILE_TABLE))
    await db_session.execute(text("DELETE FROM quality.validation_review_files"))
    await db_session.execute(text("DELETE FROM quality.validation_review_records"))
    await db_session.commit()
    yield
    await db_session.execute(text("DELETE FROM quality.validation_review_files"))
    await db_session.execute(text("DELETE FROM quality.validation_review_records"))
    await db_session.commit()


async def _seed_record(db_session: AsyncSession) -> ValidationReviewRecord:
    record = ValidationReviewRecord(
        id=uuid.uuid4(),
        title="测试验证审核",
        review_mode="upload",
        status="draft",
        created_by=uuid.uuid4(),
    )
    db_session.add(record)
    await db_session.commit()
    return record


async def _seed_completed_file(
    db_session: AsyncSession, record_id: uuid.UUID, text_value: str
) -> ValidationReviewFile:
    row = ValidationReviewFile(
        id=uuid.uuid4(),
        review_id=record_id,
        doc_kind="plan",
        source="upload",
        file_name="VP-test-01 方案.md",
        file_type="text/markdown",
        file_size=len(text_value.encode("utf-8")),
        storage_key="",
        parsed_text=text_value,
        parse_status="completed",
        sort_order=0,
    )
    db_session.add(row)
    await db_session.commit()
    return row


def _mock_llm(monkeypatch: pytest.MonkeyPatch, findings: list[dict]) -> None:
    monkeypatch.setattr(
        svc, "get_config", AsyncMock(return_value=SimpleNamespace(model_name="m"))
    )
    monkeypatch.setattr(
        type(svc.llm_client),
        "chat_json",
        AsyncMock(return_value={"findings": findings}),
    )


def _mock_basis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        svc, "load_document_basis", AsyncMock(return_value=DocumentBasis())
    )


class TestCreateRecord:
    @pytest.mark.anyio
    async def test_create_upload_record(self, db_session: AsyncSession) -> None:
        record = await svc.create_review_record(
            db_session,
            user_id=uuid.uuid4(),
            title="新建审核",
        )
        assert record.id is not None
        assert record.status == "draft"
        assert record.review_mode == "upload"


class TestParseText:
    @pytest.mark.anyio
    async def test_extract_markdown_text(self) -> None:
        text_value, error = await svc._extract_upload_text(
            "方案.md", "## 目的\n正文".encode()
        )
        assert error is None
        assert "## 目的" in (text_value or "")

    @pytest.mark.anyio
    async def test_extract_unsupported_suffix(self) -> None:
        _text, error = await svc._extract_upload_text("方案.pdf", b"pdf")
        assert error is not None
        assert "不支持" in (error or "")

    @pytest.mark.anyio
    async def test_extract_empty_markdown(self) -> None:
        text_value, error = await svc._extract_upload_text("空.md", b"")
        assert error is None
        assert text_value == ""


class TestExecuteReview:
    @pytest.mark.anyio
    async def test_completed_with_llm_findings(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        record = await _seed_record(db_session)
        text_value = "## 目的\n方案正文内容一致性待核对。"
        await _seed_completed_file(db_session, record.id, text_value)
        _mock_basis(monkeypatch)
        _mock_llm(
            monkeypatch,
            [
                {
                    "category": "content_consistency",
                    "severity": "medium",
                    "location": "目的",
                    "quote": "方案正文内容一致性待核对",
                    "detail": "上下文描述不一致",
                }
            ],
        )

        await svc._execute_review(db_session, record, "job:1", uuid.uuid4())
        await db_session.commit()

        assert record.status == "completed"
        payload = record.output_payload or {}
        findings = payload.get("findings") or []
        assert len(findings) == 1
        assert findings[0]["category"] == "content_consistency"
        assert findings[0]["quote_verified"] is True
        stats = payload.get("stats") or {}
        assert stats["total_findings"] == 1
        assert stats["references_checked"] == 0
        assert record.model_name == "m"

    @pytest.mark.anyio
    async def test_llm_bad_category_dropped(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        record = await _seed_record(db_session)
        await _seed_completed_file(db_session, record.id, "## 目的\n正文")
        _mock_basis(monkeypatch)
        _mock_llm(
            monkeypatch,
            [
                {"category": "not_a_category", "severity": "high", "quote": "x"},
                {"category": "format_issue", "severity": "medium", "quote": "y"},
            ],
        )

        await svc._execute_review(db_session, record, "job:2", uuid.uuid4())
        await db_session.commit()

        payload = record.output_payload or {}
        findings = payload.get("findings") or []
        assert len(findings) == 1
        assert findings[0]["category"] == "format_issue"

    @pytest.mark.anyio
    async def test_llm_rate_limit_exhausted_marks_failed(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        record = await _seed_record(db_session)
        await _seed_completed_file(db_session, record.id, "## 目的\n正文")
        _mock_basis(monkeypatch)
        monkeypatch.setattr(
            svc, "get_config", AsyncMock(return_value=SimpleNamespace(model_name="m"))
        )
        monkeypatch.setattr(
            type(svc.llm_client),
            "chat_json",
            AsyncMock(side_effect=LLMRateLimitError("rate limited")),
        )

        # _execute_review 内部重试耗尽后抛出，job 边界负责落 failed
        with pytest.raises(LLMRateLimitError):
            await svc._execute_review(db_session, record, "job:3", uuid.uuid4())

    @pytest.mark.anyio
    async def test_reference_mismatch_finding_generated(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        record = await _seed_record(db_session)
        text_value = "依据（SMP-QA-105/02）执行"
        await _seed_completed_file(db_session, record.id, text_value)
        from app.modules.quality.service.validation_basis_resolver import BasisEntry

        basis = DocumentBasis(
            entries=[
                BasisEntry(
                    id=uuid.uuid4(),
                    code="SMP-QA-105/03",
                    name="清洁验证管理程序",
                    effective_date=None,
                    updated_at=None,
                )
            ],
            prefixes={"SMP"},
        )
        monkeypatch.setattr(svc, "load_document_basis", AsyncMock(return_value=basis))
        _mock_llm(monkeypatch, [])

        await svc._execute_review(db_session, record, "job:4", uuid.uuid4())
        await db_session.commit()

        payload = record.output_payload or {}
        findings = payload.get("findings") or []
        mismatch = [
            f for f in findings if f["category"] == "version_mismatch"
        ]
        assert len(mismatch) == 1
        assert mismatch[0]["basis_match_type"] == "related"

    @pytest.mark.anyio
    async def test_own_document_number_excluded_from_references(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """文档自身编号（VP-xxx）不计入引用核对，避免自引用误报。"""
        record = await _seed_record(db_session)
        # 文件名为 VP-FT3-CV1902-01，正文引用自身编号 + 一个外部文件编号
        text_value = (
            "本方案编号 VP-FT3-CV1902-01，依据《清洁验证管理程序》"
            "（SMP-QA-105/03）执行。"
        )
        row = ValidationReviewFile(
            id=uuid.uuid4(),
            review_id=record.id,
            doc_kind="plan",
            source="upload",
            file_name="VP-FT3-CV1902-01 方案.md",
            file_type="text/markdown",
            file_size=len(text_value.encode("utf-8")),
            storage_key="",
            parsed_text=text_value,
            parse_status="completed",
            sort_order=0,
        )
        db_session.add(row)
        await db_session.commit()
        _mock_basis(monkeypatch)
        _mock_llm(monkeypatch, [])

        await svc._execute_review(db_session, record, "job:5", uuid.uuid4())
        await db_session.commit()

        basis_used = (record.output_payload or {}).get("basis_used") or []
        codes = [item["code"] for item in basis_used]
        # 自身编号被排除，外部引用 SMP-QA-105/03 保留（空目录 → missing）
        assert "VP-FT3-CV1902-01" not in codes
        assert "SMP-QA-105/03" in codes


class TestRunReviewConfigCheck:
    @pytest.mark.anyio
    async def test_run_without_llm_config_503(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        record = await _seed_record(db_session)
        monkeypatch.setattr(
            svc, "get_config", AsyncMock(side_effect=LLMConfigError("no config"))
        )
        with pytest.raises(AppException) as exc_info:
            await svc.run_review(db_session, record, user_id=uuid.uuid4())
        assert exc_info.value.status_code == 503
        assert record.status == "draft"


class TestQuoteVerified:
    def test_quote_found(self) -> None:
        assert (
            svc._quote_verified("清洁验证管理程序", ["依据《清洁验证管理程序》执行"])
            is True
        )

    def test_quote_not_found(self) -> None:
        assert svc._quote_verified("不存在的原文", ["另一段原文"]) is False

    def test_empty_quote(self) -> None:
        assert svc._quote_verified("", ["原文"]) is False


class TestParseLlmFindings:
    def test_non_list_returns_empty(self) -> None:
        assert svc._parse_llm_findings({"a": 1}, []) == []

    def test_invalid_severity_defaults_medium(self) -> None:
        findings = svc._parse_llm_findings(
            [{"category": "format_issue", "severity": "critical", "quote": "x"}],
            ["x"],
        )
        assert findings[0]["severity"] == "medium"

    def test_non_dict_item_skipped(self) -> None:
        assert svc._parse_llm_findings(["bad"], ["x"]) == []


class TestStatsSummary:
    def test_build_stats(self) -> None:
        findings = [
            {"severity": "high"},
            {"severity": "medium"},
            {"severity": "medium"},
        ]
        stats = svc._build_stats(findings, [], {})
        assert stats["total_findings"] == 3
        assert stats["high"] == 1
        assert stats["medium"] == 2
        assert stats["low"] == 0
        assert stats["plan_report_checked"] is False

    def test_build_summary_contains_counts(self) -> None:
        summary = svc._build_summary(
            {
                "references_checked": 2,
                "references_matched": 1,
                "total_findings": 3,
                "high": 1,
                "medium": 1,
                "low": 1,
                "plan_report_checked": True,
            }
        )
        assert "3" in summary
        assert "方案与报告一致性" in summary


class TestStorageFiles:
    def _use_local_storage(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        monkeypatch.setattr(svc, "minio_enabled", lambda: False)
        from app.core.config import get_settings

        monkeypatch.setattr(
            type(get_settings()), "UPLOAD_DIR", str(tmp_path), raising=False
        )
        monkeypatch.setattr(get_settings(), "UPLOAD_DIR", str(tmp_path))

    def test_store_read_delete_local_roundtrip(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        self._use_local_storage(monkeypatch, tmp_path)
        key = "validation-review/test-roundtrip.md"
        stored = svc._store_review_file(key, "正文".encode(), "text/markdown")
        assert stored == key
        content = svc._read_review_file(key)
        assert content == "正文".encode()
        svc._delete_review_file(key)
        assert svc._read_review_file(key) is None

    def test_read_review_file_empty_key(self) -> None:
        assert svc._read_review_file("") is None

    def test_read_review_file_local_missing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        self._use_local_storage(monkeypatch, tmp_path)
        assert svc._read_review_file("validation-review/missing.md") is None

    def test_minio_branches(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.setattr(svc, "minio_enabled", lambda: True)
        upload_mock = MagicMock(return_value="k")
        delete_mock = MagicMock(side_effect=RuntimeError("boom"))
        monkeypatch.setattr(svc, "upload_object", upload_mock)
        monkeypatch.setattr(svc, "delete_object", delete_mock)
        assert (
            svc._store_review_file("validation-review/x.md", b"x", "text/plain")
            == "validation-review/x.md"
        )
        svc._delete_review_file("validation-review/x.md")
        upload_mock.assert_called_once()
        delete_mock.assert_called_once()

    def test_safe_path_rejects_escape(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        self._use_local_storage(monkeypatch, tmp_path)
        with pytest.raises(AppException):
            svc._safe_path("../escape.md")


class TestAddFiles:
    async def _seed(self, db_session: AsyncSession) -> ValidationReviewRecord:
        return await _seed_record(db_session)

    async def _seed_entry(self, db_session: AsyncSession) -> uuid.UUID:
        from datetime import date

        from app.modules.quality.models import DocumentEntry

        await db_session.run_sync(
            lambda sync_db: DocumentEntry.__table__.create(
                sync_db.connection(), checkfirst=True
            )
        )
        entry_id = uuid.uuid4()
        db_session.add(
            DocumentEntry(
                id=entry_id,
                department_id=uuid.uuid4(),
                name="清洁验证管理程序",
                code="SMP-QA-105/03",
                effective_date=date(2026, 1, 1),
            )
        )
        await db_session.commit()
        return entry_id

    @pytest.mark.anyio
    async def test_add_uploaded_review_file(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        record = await self._seed(db_session)
        monkeypatch.setattr(
            svc, "_store_review_file", lambda key, content, ctype: key
        )
        upload = SimpleNamespace(
            filename="VR-FT3-CV1902-01 报告.docx",
            content_type="application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document",
            read=AsyncMock(return_value=b"docx-bytes"),
        )
        row = await svc.add_uploaded_review_file(
            db_session, record, file=upload, doc_kind=None, user_id=record.created_by
        )
        await db_session.commit()
        assert row.doc_kind == "report"
        assert row.parse_status == "pending"
        assert row.source == "upload"

    @pytest.mark.anyio
    async def test_add_uploaded_empty_content_rejected(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        record = await self._seed(db_session)
        upload = SimpleNamespace(
            filename="a.md",
            content_type="text/markdown",
            read=AsyncMock(return_value=b""),
        )
        with pytest.raises(AppException) as exc_info:
            await svc.add_uploaded_review_file(
                db_session,
                record,
                file=upload,
                doc_kind=None,
                user_id=record.created_by,
            )
        assert exc_info.value.status_code == 422

class TestDeleteAndList:
    @pytest.mark.anyio
    async def test_delete_review_record_soft_deletes(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        record = await _seed_record(db_session)
        monkeypatch.setattr(svc, "record_audit_log", AsyncMock())
        user_id = record.created_by
        await svc.delete_review_record(db_session, record, user_id=user_id)
        await db_session.commit()
        assert record.is_deleted is True
        svc.record_audit_log.assert_awaited_once()

    @pytest.mark.anyio
    async def test_list_review_records_pagination(
        self, db_session: AsyncSession
    ) -> None:
        owner = uuid.uuid4()
        for index in range(3):
            db_session.add(
                ValidationReviewRecord(
                    id=uuid.uuid4(),
                    title=f"列表{index}",
                    review_mode="upload",
                    status="draft",
                    created_by=owner,
                )
            )
        await db_session.commit()
        records, total = await svc.list_review_records(
            db_session, user_id=owner, page=1, page_size=2
        )
        assert total == 3
        assert len(records) == 2
        # 仅本人创建
        _other, other_total = await svc.list_review_records(
            db_session, user_id=uuid.uuid4(), page=1, page_size=10
        )
        assert other_total == 0
        # all_visible 返回全部
        _all, all_total = await svc.list_review_records(
            db_session, user_id=uuid.uuid4(), page=1, page_size=10, all_visible=True
        )
        assert all_total == 3


class TestRunReviewSuccessPath:
    @pytest.mark.anyio
    async def test_run_review_submits_job(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        record = await _seed_record(db_session)
        monkeypatch.setattr(
            svc, "get_config", AsyncMock(return_value=SimpleNamespace(model_name="m"))
        )
        submit_mock = AsyncMock(return_value="job:submitted")
        monkeypatch.setattr(svc, "submit_job", submit_mock)
        monkeypatch.setattr(svc, "record_audit_log", AsyncMock())

        job_id = await svc.run_review(db_session, record, user_id=record.created_by)
        await db_session.commit()

        assert job_id.startswith("quality:validation-review:")
        assert record.status == "processing"
        assert record.job_id == job_id
        submit_mock.assert_awaited_once()


class TestLoadDocumentBasis:
    @pytest.mark.anyio
    async def test_load_document_basis_reads_entries(
        self, db_session: AsyncSession
    ) -> None:
        from datetime import date

        from app.modules.quality.models import DocumentEntry

        await db_session.run_sync(
            lambda sync_db: DocumentEntry.__table__.create(
                sync_db.connection(), checkfirst=True
            )
        )
        await db_session.execute(text("DELETE FROM quality.document_entries"))
        db_session.add(
            DocumentEntry(
                id=uuid.uuid4(),
                department_id=uuid.uuid4(),
                name="清洁验证管理程序",
                code="SMP-QA-105/03",
                effective_date=date(2026, 1, 1),
            )
        )
        db_session.add(
            DocumentEntry(
                id=uuid.uuid4(),
                department_id=uuid.uuid4(),
                name="萃取罐操作规程",
                code="SOP-FT3-004/03",
                effective_date=None,
            )
        )
        await db_session.commit()

        basis = await svc.load_document_basis(db_session)
        assert len(basis.entries) == 2
        assert "SMP" in basis.prefixes
        assert "SOP" in basis.prefixes

    @pytest.mark.anyio
    async def test_resolve_references_with_db_basis(
        self, db_session: AsyncSession
    ) -> None:
        from datetime import date

        from app.modules.quality.models import DocumentEntry
        from app.modules.quality.service.validation_basis_resolver import (
            resolve_references as sync_resolve,
        )

        await db_session.run_sync(
            lambda sync_db: DocumentEntry.__table__.create(
                sync_db.connection(), checkfirst=True
            )
        )
        await db_session.execute(text("DELETE FROM quality.document_entries"))
        db_session.add(
            DocumentEntry(
                id=uuid.uuid4(),
                department_id=uuid.uuid4(),
                name="清洁验证管理程序",
                code="SMP-QA-105/03",
                effective_date=date(2026, 1, 1),
            )
        )
        await db_session.commit()

        basis = await svc.load_document_basis(db_session)
        items = sync_resolve(basis, "依据《清洁验证管理程序》（SMP-QA-105/02）执行")
        assert items[0].issue == "version_mismatch"
        assert items[0].current_revision == "03"


class TestBasisContentPipeline:
    @pytest.mark.anyio
    async def test_select_key_bases_filters_unknown(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:

        monkeypatch.setattr(
            svc,
            "get_config",
            AsyncMock(return_value=SimpleNamespace(model_name="m")),
        )
        monkeypatch.setattr(
            type(svc.llm_client),
            "chat_json",
            AsyncMock(
                return_value={
                    "selected": [
                        {"code": "SOP-FT3-017/04", "reason": "清洁步骤来源"},
                        {"code": "UNKNOWN-001/01", "reason": "不在候选中"},
                    ]
                }
            ),
        )
        entry_id = uuid.uuid4()
        candidates = [
            {
                "entry_id": entry_id,
                "code": "SOP-FT3-017/04",
                "name": "方锥混合机操作规程",
                "length": 100,
                "digest": "混合机参数",
            }
        ]
        key_bases, model_name = await svc._select_key_bases(
            "方案 VP-FT3-CV1902-01", candidates, None
        )
        assert model_name == "m"
        assert len(key_bases) == 1
        assert key_bases[0]["entry_id"] == entry_id
        assert key_bases[0]["reason"] == "清洁步骤来源"

    @pytest.mark.anyio
    async def test_compare_basis_contents_builds_findings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        entry_id = uuid.uuid4()
        basis_text = "主轴转速 2-10rpm，最大装料 2000kg。"
        validation_text = "验证方案规定主轴转速 5-15rpm。"
        monkeypatch.setattr(
            svc,
            "get_config",
            AsyncMock(return_value=SimpleNamespace(model_name="m")),
        )
        monkeypatch.setattr(
            type(svc.llm_client),
            "chat_json",
            AsyncMock(
                return_value={
                    "findings": [
                        {
                            "validation_quote": "主轴转速 5-15rpm",
                            "basis_quote": "主轴转速 2-10rpm",
                            "dimension": "参数",
                            "severity": "high",
                            "detail": "转速范围与规程不一致",
                        }
                    ]
                }
            ),
        )
        key_bases = [
            {
                "entry_id": entry_id,
                "code": "SOP-FT3-017/04",
                "name": "方锥混合机操作规程",
                "reason": "清洁步骤来源",
            }
        ]
        findings = await svc._compare_basis_contents(
            validation_text,
            key_bases,
            {entry_id: basis_text},
            [],
            None,
        )
        assert len(findings) == 1
        row = findings[0]
        assert row["category"] == "basis_content_mismatch"
        assert row["severity"] == "high"
        assert row["quote_verified"] is True
        assert row["basis_quote_verified"] is True
        assert row["validation_quote"] == "主轴转速 5-15rpm"
        assert "方锥混合机操作规程" in row["basis_source"]

    def test_build_basis_comparison_rows(self) -> None:
        entry_id = uuid.uuid4()
        key_bases = [
            {
                "entry_id": entry_id,
                "code": "SOP-FT3-017/04",
                "name": "方锥混合机操作规程",
                "reason": "参数来源",
            }
        ]
        comparison = svc._build_basis_comparison(
            key_bases,
            [
                {
                    "basis_entry_id": str(entry_id),
                    "basis_source": "SOP-FT3-017/04 方锥混合机操作规程",
                    "category": "basis_content_mismatch",
                }
            ],
            {entry_id: "正文"},
        )
        assert len(comparison) == 1
        assert comparison[0]["mismatch_count"] == 1
        assert comparison[0]["status"] == "completed"


class TestQualityDataLinkage:
    @pytest.mark.anyio
    async def test_collect_quality_data_summary(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _fake_deviations(db, *, keyword=None, page=1, page_size=5):
            return (
                [
                    SimpleNamespace(
                        deviation_code="PC-2604001",
                        title="混合转速偏差",
                        status="closed",
                        level="minor",
                        affected_items="霉酚酸",
                    )
                ],
                1,
            )

        async def _fake_changes(db, **kwargs):
            return (
                [
                    SimpleNamespace(
                        change_code="BG-2603001",
                        change_object="混合工艺",
                        change_content="混合时间调整",
                        closure_date=None,
                    )
                ],
                1,
            )

        monkeypatch.setattr(svc, "get_deviations", _fake_deviations)
        monkeypatch.setattr(svc, "get_changes", _fake_changes)
        identities = {
            "plan": {
                "file_name": "VP-FT3-CV1902-01",
                "doc_number": "VP-FT3-CV1902-01",
            }
        }
        summary = await svc._collect_quality_data_summary(
            db_session, identities, {"plan": "FT3 车间清洁验证"}
        )
        assert len(summary) == 2
        assert {row["type"] for row in summary} == {"deviation", "change"}

    @pytest.mark.anyio
    async def test_collect_quality_data_summary_empty_keywords(
        self, db_session: AsyncSession
    ) -> None:
        summary = await svc._collect_quality_data_summary(
            db_session, {}, {"plan": "无关键词文本"}
        )
        assert summary == []


class TestFullPipeline:
    @pytest.mark.anyio
    async def test_execute_review_with_basis_content_compare(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """全管线：引用命中 → 拉依据正文 → 筛选 → 正文比对 → 汇总落库。"""
        from app.modules.quality.service.validation_basis_resolver import (
            BasisEntry,
            DocumentBasis,
        )

        record = await _seed_record(db_session)
        plan_text = (
            "## 清洁步骤\n按《方锥混合机操作规程》（SOP-FT3-017/04）执行，"
            "主轴转速 5-15rpm。"
        )
        row = ValidationReviewFile(
            id=uuid.uuid4(),
            review_id=record.id,
            doc_kind="plan",
            source="upload",
            file_name="VP-FT3-CV1902-01 方案.md",
            file_type="text/markdown",
            file_size=100,
            storage_key="",
            parsed_text=plan_text,
            parse_status="completed",
            sort_order=0,
        )
        db_session.add(row)
        await db_session.commit()

        entry_id = uuid.uuid4()
        basis = DocumentBasis(
            entries=[
                BasisEntry(
                    id=entry_id,
                    code="SOP-FT3-017/04",
                    name="方锥混合机操作规程",
                    effective_date=None,
                    updated_at=None,
                )
            ],
            prefixes={"SOP"},
        )
        monkeypatch.setattr(svc, "load_document_basis", AsyncMock(return_value=basis))
        monkeypatch.setattr(
            svc,
            "load_basis_contents",
            AsyncMock(return_value={entry_id: "主轴转速 2-10rpm，最大装料 2000kg。"}),
        )
        monkeypatch.setattr(
            svc, "get_config", AsyncMock(return_value=SimpleNamespace(model_name="m"))
        )
        # 三次 LLM 调用顺序：P2 筛选 → P3 比对 → P1 总审核
        call_results = [
            {"selected": [{"code": "SOP-FT3-017/04", "reason": "清洁步骤来源"}]},
            {
                "findings": [
                    {
                        "validation_quote": "主轴转速 5-15rpm",
                        "basis_quote": "主轴转速 2-10rpm",
                        "dimension": "参数",
                        "severity": "high",
                        "detail": "转速范围与规程不一致",
                    }
                ]
            },
            {"findings": []},
        ]
        chat_mock = AsyncMock(side_effect=call_results)
        monkeypatch.setattr(type(svc.llm_client), "chat_json", chat_mock)
        monkeypatch.setattr(svc, "get_changes", AsyncMock(return_value=([], 0)))
        monkeypatch.setattr(
            svc, "get_deviations", AsyncMock(return_value=([], 0))
        )

        await svc._execute_review(
            db_session, record, "job:p1", uuid.uuid4(), "重点核转速"
        )
        await db_session.commit()

        payload = record.output_payload or {}
        findings = payload.get("findings") or []
        mismatch = [f for f in findings if f["category"] == "basis_content_mismatch"]
        assert len(mismatch) == 1
        assert mismatch[0]["validation_quote"] == "主轴转速 5-15rpm"
        assert mismatch[0]["basis_quote"] == "主轴转速 2-10rpm"
        assert mismatch[0]["basis_quote_verified"] is True
        comparison = payload.get("basis_comparison") or []
        assert len(comparison) == 1
        assert comparison[0]["reason"] == "清洁步骤来源"
        assert record.input_snapshot.get("focus_points") == "重点核转速"


class TestExtractQualityKeywords:
    def test_extracts_workshop_segment(self) -> None:
        identities = {
            "plan": {
                "file_name": "VP-FT3-CV1902-01 方案",
                "doc_number": "VP-FT3-CV1902-01",
            }
        }
        assert svc._extract_quality_keywords(identities, {}) == ["FT3"]

    def test_extracts_product_segment(self) -> None:
        identities = {
            "plan": {
                "file_name": "VP-MC-PV1902-01 方案",
                "doc_number": "VP-MC-PV1902-01",
            }
        }
        assert svc._extract_quality_keywords(identities, {}) == ["MC"]

    def test_no_keywords(self) -> None:
        assert svc._extract_quality_keywords({}, {"plan": "普通文本"}) == []


class TestBuildSummaryBasisBranch:
    def test_summary_mentions_basis_comparison(self) -> None:
        stats = {
            "references_checked": 1,
            "references_matched": 1,
            "total_findings": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "plan_report_checked": True,
        }
        summary = svc._build_summary(
            stats,
            [
                {
                    "code": "SOP-FT3-017/04",
                    "name": "方锥混合机操作规程",
                    "mismatch_count": 2,
                }
            ],
        )
        assert "依据文件正文比对" in summary
        assert "方锥混合机操作规程" in summary


class TestTimeoutProtection:
    @pytest.mark.anyio
    async def test_parse_timeout_marks_file_failed(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """单文件解析超时 → 该文件 failed+"解析超时"，不阻塞整单。"""
        record = await _seed_record(db_session)
        row = ValidationReviewFile(
            id=uuid.uuid4(),
            review_id=record.id,
            doc_kind="plan",
            source="upload",
            file_name="VP-test.md",
            file_type="text/markdown",
            file_size=3,
            storage_key="validation-review/slow.md",
            parse_status="pending",
            sort_order=0,
        )
        db_session.add(row)
        await db_session.commit()

        async def _slow_extract(file_name, content):
            raise RuntimeError("未实际调用")  # 不应走到

        async def _read_slow(key):
            return b"doc"

        monkeypatch.setattr(svc, "_read_review_file", _read_slow)
        # 让 _extract_upload_text 挂起超时
        monkeypatch.setattr(svc, "_PARSE_FILE_TIMEOUT", 1)
        import asyncio as _asyncio

        async def _hang(file_name, content):
            await _asyncio.sleep(30)

        monkeypatch.setattr(svc, "_extract_upload_text", _hang)
        # 后续步骤无 LLM（texts 空）直接完成
        monkeypatch.setattr(
            svc, "_call_llm_with_retry", AsyncMock(return_value=({}, "m"))
        )

        await svc._execute_review(db_session, record, "job:t1", uuid.uuid4())
        await db_session.commit()
        assert row.parse_status == "failed"
        assert "超时" in (row.parse_error or "")

    @pytest.mark.anyio
    async def test_review_total_timeout_marks_failed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """整单总超时 → _run_review_job 落 failed。"""

        class _FakeSession:
            async def __aenter__(self) -> _FakeSession:
                return self

            async def __aexit__(self, *args: object) -> bool:
                return False

            async def get(self, *args: object):
                record = SimpleNamespace(
                    id=uuid.uuid4(),
                    title="T",
                    review_mode="upload",
                    status="processing",
                    error_message=None,
                    input_snapshot=None,
                    output_payload=None,
                    job_id=None,
                    last_generated_at=None,
                    model_name=None,
                    created_at=None,
                    updated_at=None,
                )
                return record

            async def commit(self) -> None:
                pass

        fake = _FakeSession()
        monkeypatch.setattr(svc, "async_session_factory", lambda: fake)
        import asyncio as _asyncio

        async def _hang_execute(*args, **kwargs):
            await _asyncio.sleep(60)

        monkeypatch.setattr(svc, "_execute_review", _hang_execute)
        monkeypatch.setattr(svc, "_REVIEW_TOTAL_TIMEOUT", 1)

        result = await svc._run_review_job(
            record_id=uuid.uuid4(), job_id="job:t2", user_id=uuid.uuid4()
        )
        assert result["status"] == "failed"
        assert "超时" in result["error"]


class TestAutoTitle:
    def test_auto_generate_title_plan_priority(self) -> None:
        title = svc._auto_generate_title(
            {
                "plan": {
                    "doc_number": "VP-FT3-CV1902-01",
                    "content_title": "设备清洁验证方案",
                },
                "report": {
                    "doc_number": "VR-FT3-CV1902-01",
                    "content_title": "设备清洁验证报告",
                },
            }
        )
        assert title == "VP-FT3-CV1902-01 设备清洁验证方案"

    def test_auto_generate_title_empty(self) -> None:
        assert svc._auto_generate_title({}) == ""

    def test_auto_generate_title_report_only(self) -> None:
        title = svc._auto_generate_title(
            {
                "report": {
                    "doc_number": "VR-MC-PV1902-01",
                    "content_title": "生产验证报告",
                }
            }
        )
        assert title == "VR-MC-PV1902-01 生产验证报告"


class TestRefineDocKind:
    def test_filename_vp(self) -> None:
        assert svc._refine_doc_kind("VP-FT3-CV1902-01 方案.doc", "正文") == "plan"

    def test_filename_vr(self) -> None:
        assert svc._refine_doc_kind("VR-FT3-CV1902-01 报告.doc", "正文") == "report"

    def test_no_prefix_body_report(self) -> None:
        assert (
            svc._refine_doc_kind("清洁验证.doc", "## 验证报告\n结论符合")
            == "report"
        )

    def test_no_prefix_body_plan(self) -> None:
        assert svc._refine_doc_kind("清洁验证.doc", "## 验证方案\n目的") == "plan"

    def test_no_prefix_body_unknown(self) -> None:
        assert svc._refine_doc_kind("无名.doc", "普通内容") == "plan"


class TestListFilters:
    @pytest.mark.anyio
    async def test_list_review_records_filters(
        self, db_session: AsyncSession
    ) -> None:
        owner = uuid.uuid4()
        for index, status_value in enumerate(["draft", "completed", "failed"]):
            db_session.add(
                ValidationReviewRecord(
                    id=uuid.uuid4(),
                    title=f"清洁验证{index}",
                    review_mode="upload",
                    status=status_value,
                    created_by=owner,
                )
            )
        await db_session.commit()
        # keyword
        records, total = await svc.list_review_records(
            db_session, user_id=owner, page=1, page_size=10, keyword="清洁验证0"
        )
        assert total == 1
        assert records[0].title == "清洁验证0"
        # status
        records, total = await svc.list_review_records(
            db_session, user_id=owner, page=1, page_size=10, status="completed"
        )
        assert total == 1
        assert records[0].status == "completed"
        # review_mode
        records, total = await svc.list_review_records(
            db_session, user_id=owner, page=1, page_size=10, review_mode="upload"
        )
        assert total == 3


class TestP2Degrade:
    @pytest.mark.anyio
    async def test_select_key_bases_llm_failure_degrade(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.core.llm.exceptions import LLMProviderError

        monkeypatch.setattr(
            type(svc.llm_client),
            "chat_json",
            AsyncMock(side_effect=LLMProviderError("boom")),
        )
        candidates = [
            {
                "entry_id": uuid.uuid4(),
                "code": f"SOP-FT3-{i:03d}/01",
                "name": f"规程{i}",
                "length": 100,
            }
            for i in range(4)
        ]
        key_bases, model_name = await svc._select_key_bases("文档", candidates, None)
        assert model_name is None
        assert len(key_bases) == 4  # MAX_CONTENT_COMPARE_BASES=5，候选 4 → 全取
        assert "AI 筛选不可用" in key_bases[0]["reason"]


class TestBasisFetchRobustness:
    @pytest.mark.anyio
    async def test_load_basis_contents_skips_failed_entry(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """条目读取/超时失败时跳过，不阻塞其他条目。"""
        entry_id = uuid.uuid4()

        async def _db_get(model, id_):
            if str(id_) == str(entry_id):
                raise RuntimeError("db boom")
            return None

        monkeypatch.setattr(db_session, "get", _db_get)
        contents = await svc.load_basis_contents(db_session, [entry_id])
        assert contents == {}

    @pytest.mark.anyio
    async def test_load_basis_contents_entry_fetch_timeout(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.modules.quality.models import DocumentEntry

        entry = DocumentEntry(
            id=uuid.uuid4(),
            department_id=uuid.uuid4(),
            name="规程",
            code="SOP-FT3-017/04",
        )
        async def _db_get(model, id_):
            return entry

        monkeypatch.setattr(db_session, "get", _db_get)
        import asyncio as _asyncio

        from app.modules.quality.service import validation_basis_resolver as _br

        monkeypatch.setattr(_br, "_BASIS_FETCH_TIMEOUT", 1)

        async def _hang(entry):
            await _asyncio.sleep(30)
            return "x"

        monkeypatch.setattr(_br, "_load_entry_content", _hang)
        contents = await svc.load_basis_contents(db_session, [entry.id])
        assert contents == {}


class TestMissingBasis:
    @pytest.mark.anyio
    async def test_execute_review_missing_basis_finding(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """引用命中目录但无可用基准正文 → 补 missing_basis 提示不静默。"""
        from app.modules.quality.service.validation_basis_resolver import (
            BasisEntry,
        )

        record = await _seed_record(db_session)
        plan_text = "依据（SMP-QA-105/03）执行"
        row = ValidationReviewFile(
            id=uuid.uuid4(),
            review_id=record.id,
            doc_kind="plan",
            source="upload",
            file_name="VP-FT3-CV1902-01 方案.md",
            file_type="text/markdown",
            file_size=100,
            storage_key="",
            parsed_text=plan_text,
            parse_status="completed",
            sort_order=0,
        )
        db_session.add(row)
        await db_session.commit()

        entry_id = uuid.uuid4()
        basis = DocumentBasis(
            entries=[
                BasisEntry(
                    id=entry_id,
                    code="SMP-QA-105/03",
                    name="清洁验证管理程序",
                    effective_date=None,
                    updated_at=None,
                )
            ],
            prefixes={"SMP"},
        )
        monkeypatch.setattr(svc, "load_document_basis", AsyncMock(return_value=basis))
        # 命中目录但无基准正文
        monkeypatch.setattr(svc, "load_basis_contents", AsyncMock(return_value={}))
        monkeypatch.setattr(
            svc, "get_config", AsyncMock(return_value=SimpleNamespace(model_name="m"))
        )
        monkeypatch.setattr(
            type(svc.llm_client),
            "chat_json",
            AsyncMock(return_value={"findings": []}),
        )
        monkeypatch.setattr(svc, "get_changes", AsyncMock(return_value=([], 0)))
        monkeypatch.setattr(
            svc, "get_deviations", AsyncMock(return_value=([], 0))
        )

        await svc._execute_review(db_session, record, "job:mb", uuid.uuid4())
        await db_session.commit()

        payload = record.output_payload or {}
        findings = payload.get("findings") or []
        mb = [f for f in findings if f.get("basis_match_type") == "missing_basis"]
        assert len(mb) == 1
        assert "未做正文一致性比对" in mb[0]["detail"]


class TestP2ExpectedKey:
    @pytest.mark.anyio
    async def test_select_key_bases_uses_selected_expected_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """回归：P2 输出契约是 selected；expected_keys 传 findings 会让
        chat_json 校验失败，P2 永远走降级。"""
        monkeypatch.setattr(
            svc,
            "get_config",
            AsyncMock(return_value=SimpleNamespace(model_name="m")),
        )
        chat_mock = AsyncMock(
            return_value={
                "selected": [{"code": "SOP-FT3-017/04", "reason": "参数来源"}]
            }
        )
        monkeypatch.setattr(type(svc.llm_client), "chat_json", chat_mock)
        entry_id = uuid.uuid4()
        candidates = [
            {
                "entry_id": entry_id,
                "code": "SOP-FT3-017/04",
                "name": "方锥混合机操作规程",
                "length": 100,
                "digest": "混合机参数",
            }
        ]
        key_bases, _model = await svc._select_key_bases("方案", candidates, None)
        assert len(key_bases) == 1
        assert key_bases[0]["reason"] == "参数来源"
        # 关键断言：期望键必须是 selected，而不是 findings
        assert chat_mock.await_args.kwargs.get("expected_keys") == ["selected"]

    @pytest.mark.anyio
    async def test_degrade_orders_by_relevance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """降级不再盲取前 N：与文档主题相关的依据排前。"""
        from app.core.llm.exceptions import LLMProviderError

        monkeypatch.setattr(
            type(svc.llm_client),
            "chat_json",
            AsyncMock(side_effect=LLMProviderError("boom")),
        )
        relevant_id = uuid.uuid4()
        irrelevant_id = uuid.uuid4()
        candidates = [
            {
                "entry_id": irrelevant_id,
                "code": "SMP-QA-011/09",
                "name": "偏差处理管理程序",
                "length": 100,
                "digest": "偏差的处理流程与职责划分。",
            },
            {
                "entry_id": relevant_id,
                "code": "SOP-MC-201/02",
                "name": "霉酚酸提炼操作规程",
                "length": 100,
                "digest": "霉酚酸提炼的结晶温度与离心参数。",
            },
        ]
        key_bases, _model = await svc._select_key_bases(
            "方案 VP-MC-PV1902-01《霉酚酸提炼生产工艺验证方案》",
            candidates,
            None,
        )
        assert key_bases[0]["entry_id"] == relevant_id
        assert "相关性" in key_bases[0]["reason"]


class TestAutoTitleDedup:
    def test_title_containing_number_not_duplicated(self) -> None:
        """正文标题已带文档编号时不再重复拼接。"""
        long_title = "VP-MC-PV1902-01霉酚酸提炼生产工艺验证方案(高内合并）"
        title = svc._auto_generate_title(
            {
                "plan": {
                    "doc_number": "VP-MC-PV1902-01",
                    "content_title": long_title,
                }
            }
        )
        assert title == long_title

    def test_title_partial_number_prefix_still_joined(self) -> None:
        """标题只含编号主干（非完整编号）时仍正常拼接。"""
        title = svc._auto_generate_title(
            {
                "plan": {
                    "doc_number": "VP-MC-PV1902-01",
                    "content_title": "霉酚酸提炼生产工艺验证方案",
                }
            }
        )
        assert title == "VP-MC-PV1902-01 霉酚酸提炼生产工艺验证方案"


class TestCompareChunking:
    @pytest.mark.anyio
    async def test_long_validation_text_compared_chunk_by_chunk(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """超长验证文档分块逐段比对，重叠块产生的重复发现去重。"""
        entry_id = uuid.uuid4()
        basis_text = "主轴转速 2-10rpm。"
        validation_text = "验证方案正文。\n" * 3000  # 约 27000 字 → 多块
        chunks = svc.split_chunks(validation_text)
        assert len(chunks) > 1
        chat_mock = AsyncMock(
            return_value={
                "findings": [
                    {
                        "validation_quote": "验证方案正文。",
                        "basis_quote": "主轴转速 2-10rpm。",
                        "dimension": "参数",
                        "severity": "high",
                        "detail": "与规程不一致",
                    }
                ]
            }
        )
        monkeypatch.setattr(
            svc,
            "get_config",
            AsyncMock(return_value=SimpleNamespace(model_name="m")),
        )
        monkeypatch.setattr(type(svc.llm_client), "chat_json", chat_mock)
        key_bases = [
            {
                "entry_id": entry_id,
                "code": "SOP-MC-201/02",
                "name": "霉酚酸提炼操作规程",
                "reason": "工艺来源",
            }
        ]
        findings = await svc._compare_basis_contents(
            validation_text,
            key_bases,
            {entry_id: basis_text},
            [],
            None,
        )
        expected_calls = min(len(chunks), svc._MAX_COMPARE_CHUNKS_PER_BASIS)
        assert chat_mock.await_count == expected_calls
        # 相同发现来自多个重叠块，只保留一条
        assert len(findings) == 1
        assert findings[0]["quote_verified"] is True

    @pytest.mark.anyio
    async def test_short_validation_text_single_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        entry_id = uuid.uuid4()
        chat_mock = AsyncMock(return_value={"findings": []})
        monkeypatch.setattr(
            svc,
            "get_config",
            AsyncMock(return_value=SimpleNamespace(model_name="m")),
        )
        monkeypatch.setattr(type(svc.llm_client), "chat_json", chat_mock)
        findings = await svc._compare_basis_contents(
            "短正文",
            [
                {
                    "entry_id": entry_id,
                    "code": "SOP-MC-201/02",
                    "name": "规程",
                    "reason": "r",
                }
            ],
            {entry_id: "依据正文"},
            [],
            None,
        )
        assert findings == []
        assert chat_mock.await_count == 1


class TestTitleMatchCandidates:
    """正文未写引用编号时，凭文档标题在目录预筛候选依据。"""

    def _make_basis(self, entries: list[tuple[uuid.UUID, str, str]]):
        from app.modules.quality.service.validation_basis_resolver import (
            BasisEntry,
            DocumentBasis,
        )

        return DocumentBasis(
            entries=[
                BasisEntry(
                    id=eid,
                    code=code,
                    name=name,
                    effective_date=None,
                    updated_at=None,
                )
                for eid, code, name in entries
            ],
            prefixes={"SOP"},
        )

    def test_title_match_finds_relevant_entries(self) -> None:
        clean_id = uuid.uuid4()
        dev_id = uuid.uuid4()
        equip_id = uuid.uuid4()
        basis = self._make_basis(
            [
                (clean_id, "SOP-QC-901/02", "纯化水系统清洁操作规程"),
                (dev_id, "SMP-QA-011/09", "偏差处理管理程序"),
                (equip_id, "SOP-EQ-005/01", "设备管理与清洁规程"),
            ]
        )
        matched = svc._find_title_matched_entries(
            basis, "设备清洁验证方案", []
        )
        ids = [entry.id for entry in matched]
        # 清洁/设备相关条目命中；偏差管理程序不命中
        assert clean_id in ids
        assert equip_id in ids
        assert dev_id not in ids
        # 命中数排序：双命中（清洁+设备）在前
        assert matched[0].id == equip_id

    def test_title_match_excludes_hit_entries(self) -> None:
        clean_id = uuid.uuid4()
        basis = self._make_basis(
            [(clean_id, "SOP-QC-901/02", "纯化水系统清洁操作规程")]
        )
        matched = svc._find_title_matched_entries(
            basis, "设备清洁验证方案", [clean_id]
        )
        assert matched == []

    def test_keyword_candidate_bases_skip_missing_content(self) -> None:
        entry_id = uuid.uuid4()
        empty_id = uuid.uuid4()
        from app.modules.quality.service.validation_basis_resolver import (
            BasisEntry,
        )

        entries = [
            BasisEntry(
                id=entry_id,
                code="SOP-QC-901/02",
                name="纯化水系统清洁操作规程",
                effective_date=None,
                updated_at=None,
            ),
            BasisEntry(
                id=empty_id,
                code="SOP-EQ-005/01",
                name="设备清洁规程",
                effective_date=None,
                updated_at=None,
            ),
        ]
        candidates = svc._build_keyword_candidate_bases(
            entries, {entry_id: "清洁后目检无可见残留。"}
        )
        assert len(candidates) == 1
        assert candidates[0]["entry_id"] == entry_id
        assert candidates[0]["digest"] == "清洁后目检无可见残留。"

    @pytest.mark.anyio
    async def test_review_without_reference_codes_still_compares_content(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """《设备清洁验证方案》没写任何 SOP 编号，也能靠标题找到
        《清洁操作规程》做正文比对（候选来源②：标题关键词预筛）。"""
        from app.modules.quality.service.validation_basis_resolver import (
            BasisEntry,
            DocumentBasis,
        )

        record = await _seed_record(db_session)
        # 正文不含任何文件编号形态
        plan_text = (
            "本方案用于设备清洁效果确认。\n"
            "清洁剂为纯化水，清洁后目检无可见残留。"
        )
        row = ValidationReviewFile(
            id=uuid.uuid4(),
            review_id=record.id,
            doc_kind="plan",
            source="upload",
            file_name="设备清洁验证方案.md",
            file_type="text/markdown",
            file_size=100,
            storage_key="",
            parsed_text=plan_text,
            parse_status="completed",
            sort_order=0,
        )
        db_session.add(row)
        await db_session.commit()

        clean_id = uuid.uuid4()
        basis = DocumentBasis(
            entries=[
                BasisEntry(
                    id=clean_id,
                    code="SOP-QC-901/02",
                    name="纯化水系统清洁操作规程",
                    effective_date=None,
                    updated_at=None,
                )
            ],
            prefixes={"SOP"},
        )
        monkeypatch.setattr(svc, "load_document_basis", AsyncMock(return_value=basis))
        basis_contents_spy = AsyncMock(
            return_value={clean_id: "清洁后应目检无可见残留，微生物不超过 10 CFU。"}
        )
        monkeypatch.setattr(svc, "load_basis_contents", basis_contents_spy)
        monkeypatch.setattr(
            svc, "get_config", AsyncMock(return_value=SimpleNamespace(model_name="m"))
        )
        call_results = [
            {"selected": [{"code": "SOP-QC-901/02", "reason": "清洁步骤来源"}]},
            {
                "findings": [
                    {
                        "validation_quote": "目检无可见残留",
                        "basis_quote": "微生物不超过 10 CFU",
                        "dimension": "限度",
                        "severity": "high",
                        "detail": "方案只写目检，规程要求微生物限度",
                    }
                ]
            },
            {"findings": []},
        ]
        monkeypatch.setattr(
            type(svc.llm_client), "chat_json", AsyncMock(side_effect=call_results)
        )
        monkeypatch.setattr(svc, "get_changes", AsyncMock(return_value=([], 0)))
        monkeypatch.setattr(
            svc, "get_deviations", AsyncMock(return_value=([], 0))
        )

        await svc._execute_review(db_session, record, "job:tm", uuid.uuid4())
        await db_session.commit()

        # 标题预筛条目进了正文拉取范围（无引用命中，ids 全来自标题匹配）
        pulled_ids = basis_contents_spy.await_args.args[1]
        assert clean_id in pulled_ids

        payload = record.output_payload or {}
        findings = payload.get("findings") or []
        mismatch = [f for f in findings if f["category"] == "basis_content_mismatch"]
        assert len(mismatch) == 1
        comparison = payload.get("basis_comparison") or []
        assert len(comparison) == 1
        assert comparison[0]["name"] == "纯化水系统清洁操作规程"


class TestReadFileTimeout:
    @pytest.mark.anyio
    async def test_read_file_timeout_marks_file_failed(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """附件读取（同步 MinIO）卡死 → 线程池+超时保护，文件 failed 不挂死 job。"""
        record = await _seed_record(db_session)
        row = ValidationReviewFile(
            id=uuid.uuid4(),
            review_id=record.id,
            doc_kind="plan",
            source="upload",
            file_name="VP-test.md",
            file_type="text/markdown",
            file_size=3,
            storage_key="validation-review/hang.md",
            parse_status="pending",
            sort_order=0,
        )
        db_session.add(row)
        await db_session.commit()

        def _read_hang(key):
            import time as _time

            _time.sleep(5)  # 同步阻塞，模拟 MinIO socket 挂死
            return b"doc"

        monkeypatch.setattr(svc, "_READ_FILE_TIMEOUT", 0.2)
        monkeypatch.setattr(svc, "_read_review_file", _read_hang)
        monkeypatch.setattr(
            svc, "_call_llm_with_retry", AsyncMock(return_value=({}, "m"))
        )
        monkeypatch.setattr(svc, "get_changes", AsyncMock(return_value=([], 0)))
        monkeypatch.setattr(
            svc, "get_deviations", AsyncMock(return_value=([], 0))
        )

        await svc._execute_review(db_session, record, "job:rf", uuid.uuid4())
        await db_session.commit()
        assert row.parse_status == "failed"
        assert "读取附件超时" in (row.parse_error or "")


class TestReconcileOrphanedReviews:
    @pytest.mark.anyio
    async def test_orphan_processing_flipped_to_failed(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """processing 且 job 心跳已消失 → failed；活 job 与其他状态不动。"""
        orphan = await _seed_record(db_session)
        orphan.status = "processing"
        orphan.job_id = "quality:validation-review:deadbeef0001"
        alive = await _seed_record(db_session)
        alive.status = "processing"
        alive.job_id = "quality:validation-review:alivejob0002"
        done = await _seed_record(db_session)
        done.status = "completed"
        await db_session.commit()

        async def _fake_running(job_id: str) -> bool:
            return job_id.endswith("alivejob0002")

        monkeypatch.setattr(svc, "is_job_running", _fake_running)
        flipped = await svc.reconcile_orphaned_reviews(db_session)

        assert flipped == 1
        assert orphan.status == "failed"
        assert "中断" in (orphan.error_message or "")
        assert alive.status == "processing"
        assert done.status == "completed"

    @pytest.mark.anyio
    async def test_processing_without_job_id_flipped(
        self, db_session: AsyncSession
    ) -> None:
        """processing 但没有 job_id（异常残留）也翻 failed。"""
        record = await _seed_record(db_session)
        record.status = "processing"
        record.job_id = None
        await db_session.commit()

        flipped = await svc.reconcile_orphaned_reviews(db_session)
        assert flipped == 1
        assert record.status == "failed"
