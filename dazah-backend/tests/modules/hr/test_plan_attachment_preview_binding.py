"""培训资料页附件条目预览的页面契约回归.

回归缺陷：/plan-attachment-sections/{section_id}/preview 曾只登记年度计划页，
培训资料页（签到表）"选择培训附件内容"弹窗按条目预览附件清单时被页面契约
403 拒绝，前端静默吞错后误显示"附件未解析出可选的文件清单内容"。
"""

from app.platform.identity.page_policy import (
    PAGES_BY_KEY,
    api_binding_for_route,
)

PREVIEW_ROUTE = "/api/v1/hr/plan-attachment-sections/{section_id}/preview"


def test_attachment_section_preview_allows_both_training_pages():
    binding = api_binding_for_route("GET", PREVIEW_ROUTE)
    assert binding is not None
    assert set(binding.page_keys) == {
        "hr:training:annual-plan",
        "hr:training:sign-in-sheet",
    }
    assert binding.permission == "operate"
    assert binding.sensitive_action == "sensitive_export"


def test_both_bound_pages_declare_the_sensitive_action():
    for page_key in ("hr:training:annual-plan", "hr:training:sign-in-sheet"):
        page = PAGES_BY_KEY[page_key]
        assert "sensitive_export" in {a.key for a in page.sensitive_actions}


def test_whole_file_preview_stays_limited_to_annual_plan_page():
    """整文件预览/下载仅年度计划详情页调用，不随条目预览扩大登记范围."""
    binding = api_binding_for_route(
        "GET", "/api/v1/hr/annual-training-plan-attachments/{attachment_id}/preview"
    )
    assert binding is not None
    assert binding.page_keys == ("hr:training:annual-plan",)
