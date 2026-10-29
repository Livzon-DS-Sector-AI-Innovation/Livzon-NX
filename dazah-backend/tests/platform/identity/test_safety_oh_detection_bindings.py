"""职业健康页（检测报告导入 + 存量监测/体检）权限的平台登记断言。"""

from app.platform.identity.page_policy import (
    PAGE_API_BINDINGS,
    _sensitive_actions,
    api_binding_for_route,
)

_OH_PAGE = "safety:occupational-health-group:oh-monitor"


def test_oh_detection_report_routes_bound_to_monitor_page() -> None:
    """检测报告导入端点全部绑定到职业健康页。"""
    expected = [
        ("GET", "/api/v1/safety/oh-detection-reports", "query", None),
        ("GET", "/api/v1/safety/oh-detection-reports/{report_id}", "query", None),
        (
            "GET",
            "/api/v1/safety/oh-detection-reports/{report_id}/results",
            "query",
            None,
        ),
        ("GET", "/api/v1/safety/oh-detection-reports/{report_id}/file", "query", None),
        (
            "POST",
            "/api/v1/safety/oh-detection-reports/parse",
            "operate",
            "bulk_import",
        ),
        (
            "POST",
            "/api/v1/safety/oh-detection-reports/import",
            "operate",
            "bulk_import",
        ),
        (
            "DELETE",
            "/api/v1/safety/oh-detection-reports/{report_id}",
            "operate",
            "delete",
        ),
    ]
    for method, path, permission, sensitive in expected:
        binding = api_binding_for_route(method, path)
        assert binding is not None, f"{method} {path} 未登记页面绑定"
        assert _OH_PAGE in binding.page_keys, f"{method} {path} 页面 key 错误"
        assert binding.permission == permission, f"{method} {path} 权限档错误"
        assert binding.sensitive_action == sensitive, f"{method} {path} 敏感动作错误"


def test_existing_oh_monitor_and_exam_routes_bound() -> None:
    """存量危害因素监测 / 体检端点补登到同一页面（防兼容模式收紧后 403）。"""
    sample = [
        ("GET", "/api/v1/safety/oh-hazard-monitors"),
        ("POST", "/api/v1/safety/oh-hazard-monitors"),
        ("DELETE", "/api/v1/safety/oh-hazard-monitors/{monitor_id}"),
        ("POST", "/api/v1/safety/oh-hazard-monitors/{monitor_id}/detection-results"),
        ("GET", "/api/v1/safety/oh-health-exams"),
        ("PUT", "/api/v1/safety/oh-health-exams/{exam_id}"),
        ("DELETE", "/api/v1/safety/oh-health-exams/{exam_id}"),
        ("PUT", "/api/v1/safety/oh-health-exams/{exam_id}/conclusion"),
    ]
    for method, path in sample:
        binding = api_binding_for_route(method, path)
        assert binding is not None, f"{method} {path} 未登记页面绑定"
        assert _OH_PAGE in binding.page_keys


def test_oh_page_sensitive_actions_registered() -> None:
    """职业健康页登记批量导入与删除敏感动作。"""
    actions = _sensitive_actions(_OH_PAGE, "/safety/occupational-health", "职业健康")
    keys = {action.key for action in actions}
    assert {"bulk_import", "delete"} <= keys


def test_oh_bindings_are_the_only_oh_routes_in_safety_module() -> None:
    """登记的 oh-* 绑定与模块路由保持一一对应（抽查数量防漂移）。"""
    oh_routes = {
        (b.method, b.route_path)
        for b in PAGE_API_BINDINGS
        if isinstance(b.route_path, str)
        and b.route_path.startswith("/api/v1/safety/oh-")
    }
    assert len(oh_routes) == 34  # 监测 13 + 体检 14 + 检测报告 7
