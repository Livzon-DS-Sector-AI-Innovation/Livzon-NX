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
