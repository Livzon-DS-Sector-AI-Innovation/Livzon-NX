"""页面镜像接口的平台权限登记断言（页面绑定、敏感操作与生命周期账本）。"""

import pytest

from app.modules.safety.page_tables import PAGE_TABLE_DEFINITIONS, get_page_table
from app.platform.identity.page_lifecycle import load_ledger
from app.platform.identity.page_policy import (
    PAGES_BY_KEY,
    SAFETY_PAGE_TABLE_PAGES,
    _sensitive_actions,
    api_binding_for_route,
    page_lifecycle_errors,
)

_PAGE = "safety:risk-hazard:hazard-inspection:hazard-duty"
_SETTINGS_PAGE = "safety:system-config:safety-feishu-settings"


def test_page_table_registry_matches_registered_page_definition() -> None:
    """注册表里的页面标识必须与菜单派生的页面定义一致，否则权限绑定无从生效。"""
    assert len(PAGE_TABLE_DEFINITIONS) == 11
    definition = get_page_table(_PAGE)
    assert definition is not None
    assert definition.page_name == "24小时值班隐患"
    assert definition.route_path == "/safety/hazard-duty"

    page = PAGES_BY_KEY[_PAGE]
    assert page.module_code == "safety"
    assert page.route_path == definition.route_path
    assert page_lifecycle_errors(page) == []


def test_registry_keys_match_policy_page_tuple() -> None:
    """镜像页注册表与平台绑定元组必须一致，避免出现未授权或失效的页面键。"""
    assert tuple(item.page_key for item in PAGE_TABLE_DEFINITIONS) == (
        SAFETY_PAGE_TABLE_PAGES
    )


@pytest.mark.parametrize(
    ("page_key", "page_name", "route_path"),
    [
        (
            "safety:ops-safety:daily-risk-report",
            "关键风险作业报备",
            "/safety/risk-reporting",
        ),
        (
            "safety:ops-safety:special-danger-work",
            "次日特殊危险作业审批",
            "/safety/special-danger-work",
        ),
        (
            "safety:ops-safety:risk-work-registration",
            "关键风险作业报备表",
            "/safety/risk-work-registration",
        ),
        (
            "safety:ops-safety:feeding-inspection",
            "投料巡查表",
            "/safety/feeding-inspection",
        ),
        (
            "safety:ops-safety:hazchem-unloading-inspection",
            "危险化学品卸车巡查表",
            "/safety/hazchem-unloading-inspection",
        ),
        (
            "safety:ops-safety:centrifuge-discharge-inspection",
            "离心出料风险巡查表",
            "/safety/centrifuge-discharge-inspection",
        ),
    ],
)
def test_ops_safety_mirror_pages_registered(
    page_key: str, page_name: str, route_path: str
) -> None:
    definition = get_page_table(page_key)
    assert definition is not None
    assert definition.page_name == page_name
    assert definition.route_path == route_path

    page = PAGES_BY_KEY[page_key]
    assert page.module_code == "safety"
    assert page.page_name == page_name
    assert page.route_path == route_path
    # 页面键与路径不含台账/审批/设置等关键词，推导不出额外敏感动作
    assert _sensitive_actions(page_key, route_path, page_name) == ()
    assert page_lifecycle_errors(page) == []


def test_registry_lookup_returns_none_for_unknown_page() -> None:
    assert get_page_table("safety:not:registered") is None


_EHS_CHANGE_REVIEW_PAGE = "safety:risk-hazard:ehs-change:ehs-change-review"
_EHS_CHANGE_ACCEPTANCE_PAGE = (
    "safety:risk-hazard:ehs-change:ehs-change-acceptance"
)


@pytest.mark.parametrize(
    ("page_key", "page_name", "route_path"),
    [
        (
            _EHS_CHANGE_REVIEW_PAGE,
            "EHS变更审批",
            "/safety/ehs-change",
        ),
        (
            _EHS_CHANGE_ACCEPTANCE_PAGE,
            "变更验收审批",
            "/safety/ehs-change/acceptance",
        ),
    ],
)
def test_ehs_change_mirror_pages_registered(
    page_key: str, page_name: str, route_path: str
) -> None:
    """「EHS变更审批/变更验收审批」镜像页登记、生命周期账本与数据路由一致。"""
    definition = get_page_table(page_key)
    assert definition is not None
    assert definition.page_name == page_name
    assert definition.route_path == route_path

    page = PAGES_BY_KEY[page_key]
    assert page.module_code == "safety"
    assert page.page_name == page_name
    assert page.route_path == route_path
    # 页面键与路径不含审批/台账/记录等关键词：推导不出额外敏感动作，
    # 因此镜像数据路由（绑定动作为空集）才能通过校验
    assert _sensitive_actions(page_key, route_path, page_name) == ()
    assert page_lifecycle_errors(page) == []

    ledger = load_ledger()
    entry = ledger["pages"][page_key]
    assert entry["status"] == "active"
    assert entry["module_code"] == "safety"
    assert entry["route_path"] == route_path
    assert entry["actions"] == {}


def test_config_routes_bound_to_feishu_settings_page() -> None:
    """绑定维护归飞书设置页，且作为 sync_config 敏感操作登记。"""
    routes = [
        ("GET", "/api/v1/safety/page-feishu-configs"),
        ("PUT", "/api/v1/safety/page-feishu-configs/{page_key}"),
        ("POST", "/api/v1/safety/page-feishu-configs/{page_key}/test"),
        ("POST", "/api/v1/safety/page-feishu-configs/resolve"),
    ]
    for method, path in routes:
        binding = api_binding_for_route(method, path)
        assert binding is not None, f"{method} {path} 未登记页面绑定"
        assert binding.page_keys == (_SETTINGS_PAGE,)
        assert binding.scope_adapter == "not_applicable"
        if method == "GET":
            assert binding.permission == "query"
            assert binding.sensitive_action is None
        else:
            assert binding.permission == "operate"
            assert binding.sensitive_action == "sync_config"


def test_data_routes_bound_to_duty_hazard_page() -> None:
    routes = [
        ("GET", "/api/v1/safety/page-tables/{page_key}/tabs", "query"),
        ("GET", "/api/v1/safety/page-tables/{page_key}/records", "query"),
        ("GET", "/api/v1/safety/page-tables/{page_key}/stats", "query"),
        ("GET", "/api/v1/safety/page-tables/{page_key}/values", "query"),
        ("POST", "/api/v1/safety/page-tables/{page_key}/records", "operate"),
        ("PUT", "/api/v1/safety/page-tables/{page_key}/records/{record_id}", "operate"),
        (
            "POST",
            "/api/v1/safety/page-tables/{page_key}/records/{record_id}/attachments/{field_name}",
            "operate",
        ),
        (
            "GET",
            "/api/v1/safety/page-tables/{page_key}/records/{record_id}/attachments/{field_name}/{file_token}/content",
            "query",
        ),
        (
            "GET",
            "/api/v1/safety/page-tables/{page_key}/records/{record_id}/attachments/{field_name}/{file_token}/thumbnail",
            "query",
        ),
    ]
    for method, path, permission in routes:
        binding = api_binding_for_route(method, path)
        assert binding is not None, f"{method} {path} 未登记页面绑定"
        assert binding.page_keys == SAFETY_PAGE_TABLE_PAGES
        assert binding.permission == permission
        assert binding.scope_adapter == "not_applicable"
        # 镜像页敏感动作为空集：绑定的动作必须也为空，否则 _api_binding_errors 会拒绝
        assert binding.sensitive_action is None


def test_duty_hazard_page_has_no_sensitive_actions() -> None:
    """页面名与路径不含台账/设置/导入等关键词，推导出的敏感动作为空。"""
    actions = _sensitive_actions(_PAGE, "/safety/hazard-duty", "24小时值班隐患")
    assert actions == ()


def test_duty_hazard_page_registered_in_lifecycle_ledger() -> None:
    ledger = load_ledger()
    entry = ledger["pages"][_PAGE]
    assert entry["status"] == "active"
    assert entry["module_code"] == "safety"
    assert entry["route_path"] == "/safety/hazard-duty"
    assert entry["actions"] == {}


_QUICK_REPORT_PAGE = "safety:risk-hazard:hazard-inspection:hazard-quick-report"

_FIRE_EQUIPMENT_PAGE = "safety:emergency-accident:fire-equipment-inspection"


def test_fire_equipment_inspection_page_registered() -> None:
    """「灭火器及消防栓点检」镜像页登记、生命周期账本与端点绑定一致。"""
    definition = get_page_table(_FIRE_EQUIPMENT_PAGE)
    assert definition is not None
    assert definition.page_name == "灭火器及消防栓点检"
    assert definition.route_path == "/safety/fire-inspection"

    page = PAGES_BY_KEY[_FIRE_EQUIPMENT_PAGE]
    assert page.module_code == "safety"
    assert page.page_name == "灭火器及消防栓点检"
    assert page.route_path == "/safety/fire-inspection"
    # 键与路径不含台账/记录/设置等英文关键词：推导不出敏感动作，
    # 因此该页的写入绑定也必须为空动作（见 _api_binding_errors）。
    assert _sensitive_actions(
        _FIRE_EQUIPMENT_PAGE, "/safety/fire-inspection", "灭火器及消防栓点检"
    ) == ()
    assert page_lifecycle_errors(page) == []

    ledger = load_ledger()
    entry = ledger["pages"][_FIRE_EQUIPMENT_PAGE]
    assert entry["status"] == "active"
    assert entry["module_code"] == "safety"
    assert entry["route_path"] == "/safety/fire-inspection"
    assert entry["actions"] == {}


def test_fire_equipment_routes_bound_to_fire_inspection_page() -> None:
    routes = [
        ("GET", "/api/v1/safety/fire-equipment", "query"),
        ("GET", "/api/v1/safety/fire-equipment/stats", "query"),
        ("GET", "/api/v1/safety/fire-equipment/checklist", "query"),
        ("GET", "/api/v1/safety/fire-equipment/{equipment_id}", "query"),
        ("GET", "/api/v1/safety/fire-inspection-records", "query"),
        (
            "POST",
            "/api/v1/safety/fire-equipment/{equipment_id}/inspections",
            "operate",
        ),
        ("POST", "/api/v1/safety/fire-equipment/writeback-table/init", "operate"),
        ("POST", "/api/v1/safety/fire-equipment/sync", "operate"),
    ]
    for method, path, permission in routes:
        binding = api_binding_for_route(method, path)
        assert binding is not None, f"{method} {path} 未登记页面绑定"
        assert binding.page_keys == (_FIRE_EQUIPMENT_PAGE,)
        assert binding.permission == permission
        assert binding.scope_adapter == "not_applicable"
        # 页面敏感动作为空集，绑定动作必须为空
        assert binding.sensitive_action is None


def test_every_fire_equipment_api_route_has_a_binding() -> None:
    """消防点检端点↔绑定对等，防止新端点漏登记（403 而非 404 的隐形故障）。"""
    from app.main import app

    route_paths = {
        (method, route.path)
        for route in app.routes
        if getattr(route, "path", "").startswith(
            ("/api/v1/safety/fire-equipment", "/api/v1/safety/fire-inspection")
        )
        for method in (getattr(route, "methods", None) or ())
    }
    assert route_paths, "未收集到消防点检路由"
    missing = [
        f"{method} {path}"
        for method, path in sorted(route_paths)
        if api_binding_for_route(method, path) is None
    ]
    assert missing == []


def test_hazard_quick_report_page_registered() -> None:
    """「隐患台账」（公司总台账镜像页，wiki 表）登记与生命周期账本一致。"""
    definition = get_page_table(_QUICK_REPORT_PAGE)
    assert definition is not None
    assert definition.page_name == "隐患台账"
    assert definition.route_path == "/safety/hazard-quick-report"

    page = PAGES_BY_KEY[_QUICK_REPORT_PAGE]
    assert page.module_code == "safety"
    assert page.page_name == "隐患台账"
    assert page.route_path == "/safety/hazard-quick-report"
    # 键与路径不含台账/记录/设置等关键词：推导不出敏感动作
    assert _sensitive_actions(
        _QUICK_REPORT_PAGE, "/safety/hazard-quick-report", "隐患台账"
    ) == ()
    assert page_lifecycle_errors(page) == []

    ledger = load_ledger()
    entry = ledger["pages"][_QUICK_REPORT_PAGE]
    assert entry["status"] == "active"
    assert entry["module_code"] == "safety"
    assert entry["route_path"] == "/safety/hazard-quick-report"
    assert entry["actions"] == {}


def test_every_page_table_api_route_has_a_binding() -> None:
    """路由↔绑定对等：镜像页新增端点必须同步登记权限绑定。

    未登记的端点对管理员和普通用户都会被 403（页面上下文无法建立），
    服务层与 API 层的测试都发现不了，只有对等校验能拦住。
    """
    from app.main import app

    route_paths = {
        (method, route.path)
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/v1/safety/page-tables/")
        for method in (getattr(route, "methods", None) or ())
    }
    assert route_paths, "未收集到 page-tables 路由"
    missing = [
        f"{method} {path}"
        for method, path in sorted(route_paths)
        if api_binding_for_route(method, path) is None
    ]
    assert missing == []


def test_governance_pages_registered_in_policy_and_lifecycle() -> None:
    """安全治理批次新页：page_policy 与生命周期目录都已登记。"""
    from app.platform.identity.page_lifecycle import load_ledger

    pages = load_ledger()["pages"]
    for page_key in (
        "safety:emergency-accident:emergency-card",
        "safety:emergency-accident:emergency-mgmt",
        "safety:site-mgmt:safety-facilities",
        "safety:site-mgmt:hazchem-msds",
        "safety:governance:target-performance",
    ):
        assert pages[page_key]["status"] == "active", page_key
