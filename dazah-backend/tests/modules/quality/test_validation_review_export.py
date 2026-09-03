"""验证 AI 审核报告导出（docx）单元测试。

覆盖：完整 findings/basis_used/stats 渲染、空数据最小报告、异常兜底分支。
"""

from __future__ import annotations

import uuid

from app.modules.quality.service.validation_review_export import (
    build_review_docx,
)


def _full_payload() -> dict:
    return {
        "id": uuid.uuid4(),
        "title": "清洁验证审核",
        "review_mode": "upload",
        "status": "completed",
        "last_generated_at": "2026-09-03T10:05:00",
        "summary": "本次 AI 审核共核对引用文件 2 项，发现 3 个问题。",
        "stats": {
            "total_findings": 3,
            "high": 1,
            "medium": 1,
            "low": 1,
            "references_checked": 2,
            "references_matched": 1,
            "plan_report_checked": True,
        },
        "findings": [
            {
                "category": "version_mismatch",
                "severity": "high",
                "location": "引用文件",
                "quote": "SMP-QA-105/02",
                "quote_verified": True,
                "detail": "引用版本与目录现行版不一致",
            },
            {
                "category": "reference_missing",
                "severity": "medium",
                "location": "引用文件",
                "quote": "SOP-QA-999/01",
                "quote_verified": False,
                "detail": "引用文件未在目录中找到",
            },
            {
                "category": "numeric_check",
                "severity": "low",
                "location": "性能确认",
                "quote": "70±5℃",
                "quote_verified": True,
                "detail": "实测温度未落在方案区间",
            },
        ],
        "basis_used": [
            {
                "code": "SMP-QA-105/03",
                "entry_name": "清洁验证管理程序",
                "entry_code": "SMP-QA-105/03",
                "issue": "none",
            },
            {
                "code": "SMP-QA-105/02",
                "entry_name": "清洁验证管理程序",
                "entry_code": "SMP-QA-105/03",
                "issue": "version_mismatch",
            },
            {
                "code": "SOP-QA-999/01",
                "entry_name": None,
                "entry_code": None,
                "issue": "missing",
            },
        ],
    }


class TestBuildReviewDocx:
    def test_full_payload_renders_tables(self) -> None:
        content = build_review_docx(_full_payload())
        assert len(content) > 5000

    def test_minimal_draft_renders(self) -> None:
        content = build_review_docx(
            {
                "id": uuid.uuid4(),
                "title": "空审核",
                "review_mode": "entry",
                "status": "draft",
                "last_generated_at": None,
                "summary": None,
                "stats": None,
                "findings": [],
                "basis_used": [],
            }
        )
        assert len(content) > 1000

    def test_invalid_findings_items_skipped(self) -> None:
        payload = _full_payload()
        payload["findings"] = [
            "not-a-dict",
            {"category": "unknown", "severity": 1},
        ]
        payload["basis_used"] = ["bad-item"]
        content = build_review_docx(payload)
        assert len(content) > 1000

    def test_datetime_object_last_generated(self) -> None:
        from datetime import datetime

        payload = _full_payload()
        payload["last_generated_at"] = datetime(2026, 9, 3, 10, 5)
        content = build_review_docx(payload)
        assert len(content) > 5000
