"""培训部门目录接口的页面契约回归测试。

生产曾因 GET /training/departments 系列接口仅登记 hr.settings 页面，培训台账等
页面经代理携带来源页 page key 调用时被拒（403「加载部门列表失败」）。回归锁定：
培训各页与相关设置页都在只读绑定内，台账页可增删自定义部门。
"""

from app.platform.identity.page_policy import api_binding_for_route

_TRAINING_PAGE_KEYS = (
    "hr:training:annual-plan",
    "hr:training:sign-in-sheet",
    "hr:training:new-employee-training",
    "hr:training:training-ledger",
    "hr:training:employee-training-list",
    "hr:training:trainer",
    "hr:training:position-training",
    "hr:training:plan-tracking",
)


def _binding_pages(method: str, path: str) -> tuple[str, ...]:
    binding = api_binding_for_route(method, path)
    assert binding is not None, f"{method} {path} 绑定缺失或契约校验未通过"
    return binding.page_keys


_DEPT_LIST = "/api/v1/hr/training/departments"
_DEPT_CUSTOM = "/api/v1/hr/training/departments/custom"
_DEPT_ONE = "/api/v1/hr/training/departments/{name}"
_DEPT_MAPPINGS = "/api/v1/hr/training/dept-mappings"


def test_departments_get_bindings_cover_training_pages():
    pages = _binding_pages("GET", _DEPT_LIST)
    for key in _TRAINING_PAGE_KEYS:
        assert key in pages, f"只读部门目录缺少培训页登记：{key}"
    assert "hr:hr-settings:hr-settings-dept-mapping" in pages
    assert "hr:hr-settings:hr-settings-dept-scopes" in pages


def test_departments_custom_get_binding_matches_list():
    assert _binding_pages("GET", _DEPT_CUSTOM) == _binding_pages("GET", _DEPT_LIST)


def test_dept_mappings_get_binding_matches_departments():
    assert _binding_pages("GET", _DEPT_MAPPINGS) == _binding_pages("GET", _DEPT_LIST)


def test_departments_mutations_cover_training_ledger():
    for method, path in (
        ("POST", _DEPT_LIST),
        ("DELETE", _DEPT_ONE),
    ):
        pages = _binding_pages(method, path)
        assert "hr:training:training-ledger" in pages
        assert "hr:hr-settings:hr-settings-dept-mapping" in pages
