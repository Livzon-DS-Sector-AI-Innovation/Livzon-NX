"""验证 AI 审核 prompt 构建器单元测试。

覆盖 v2.2 行为修正：P1 注入引用统计概要而非全量清单、文字质量维度、
P3 不重复报告纯版本号差异。
"""

from __future__ import annotations

import pytest

from app.modules.quality.service.validation_review_prompt import (
    build_content_compare_prompt,
    build_review_prompt,
)


class TestReviewPromptReferenceSummary:
    def test_reference_stats_without_full_list(self) -> None:
        """引用核对只注入统计概要：全量清单由编号核对环节确定性输出。"""
        reference_summary = [
            {
                "code": "SMP-QA-100/03",
                "issue": "version_mismatch",
                "entry_code": "SMP-QA-100-12",
            },
            {"code": "SOP-FT3-017/04", "issue": "none", "entry_code": "SOP-FT3-017-04"},
        ]
        prompt = build_review_prompt(
            plan_text="方案正文",
            report_text=None,
            reference_summary=reference_summary,
        )
        assert "版本不一致 1 项" in prompt
        assert "目录未命中 0 项" in prompt
        # 全量清单（含 entry_code 字段的 dict repr）不应再注入
        assert "entry_code" not in prompt
        assert "确实没有问题时才返回空数组" in prompt

    def test_text_quality_dimension_present(self) -> None:
        prompt = build_review_prompt(
            plan_text="方案正文",
            report_text=None,
            reference_summary=[],
        )
        assert "错别字" in prompt

    def test_no_reference_section_when_empty(self) -> None:
        prompt = build_review_prompt(
            plan_text="方案正文",
            report_text=None,
            reference_summary=[],
        )
        assert "引用文件核对说明" not in prompt


class TestContentComparePrompt:
    def test_version_only_diffs_excluded(self) -> None:
        prompt = build_content_compare_prompt(
            validation_text="验证文档正文",
            basis_name="霉酚酸提炼工艺规程",
            basis_code="SOP-MC-201/02",
            basis_text="依据正文",
        )
        assert "不要输出纯版本号差异" in prompt
        assert "validation_quote" in prompt
        assert "basis_quote" in prompt

    def test_focus_points_included(self) -> None:
        prompt = build_content_compare_prompt(
            validation_text="验证文档正文",
            basis_name="工艺规程",
            basis_code="SOP-MC-201/02",
            basis_text="依据正文",
            focus_points="重点核对灭菌温度参数",
        )
        assert "重点核对灭菌温度参数" in prompt

    @pytest.mark.parametrize(
        ("text", "limit_name"),
        [("validation_text", "validation"), ("basis_text", "basis")],
    )
    def test_long_text_truncated(self, text: str, limit_name: str) -> None:
        kwargs = {
            "validation_text": "验证文档正文",
            "basis_name": "工艺规程",
            "basis_code": "SOP-MC-201/02",
            "basis_text": "依据正文",
        }
        kwargs[text] = "字" * 30000
        prompt = build_content_compare_prompt(**kwargs)
        assert "中间内容因长度限制省略" in prompt


class TestFormulaCheckDimension:
    def test_formula_and_calculation_check_present(self) -> None:
        """数值核对维度包含公式与计算正确性（RSD/回收率等）。"""
        prompt = build_review_prompt(
            plan_text="方案正文",
            report_text=None,
            reference_summary=[],
        )
        assert "公式与计算" in prompt
        assert "回收率" in prompt
        assert "RSD" in prompt
