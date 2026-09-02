"""Stable business-page permission catalog.

The existing menu seed remains the source of page identity.  This module adds
security metadata without replacing the menu or RBAC systems.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from starlette.routing import BaseRoute, Mount, Route

from app.platform.identity.menu_seed_data import SEED_MENUS
from app.platform.identity.page_lifecycle import page_lifecycle_errors

PAGE_PERMISSION_ORDER = ("access", "query", "operate")
PAGE_PERMISSION_SET = frozenset(PAGE_PERMISSION_ORDER)
PAGE_SCOPE_TYPES = frozenset(
    {"not_applicable", "department_tree", "departments", "all", "self"}
)
FIRST_BATCH_MODULES = frozenset({"hr", "warehouse", "quality", "procurement"})

# Reviewed aliases used by the warehouse material-page API, not URL inference.
WAREHOUSE_DEPARTMENT_DATA_PAGES = frozenset(
    "hardware-" + suffix
    for suffix in (
        "101-1-workshop",
        "101-2-workshop",
        "102-workshop",
        "103-workshop",
        "201-1-workshop",
        "201-2-workshop",
        "201-3-workshop",
        "202-workshop",
        "203-workshop",
        "203-3-workshop",
        "thermal-station",
        "power-department",
        "wastewater",
        "warehouse",
        "rd-center",
        "others",
    )
)
WAREHOUSE_MATERIAL_PAGE_ALIASES = {
    **{
        f"warehouse:materials:{alias}": alias
        for alias in (
            "raw-summary",
            "raw-detail",
            "raw-ledger",
            "packaging-summary",
            "packaging-detail",
            "packaging-ledger",
            "inbound-ledger",
            "qualified-suppliers",
            "material-name-code-map",
        )
    },
    **{
        f"warehouse:hardware:hardware-{alias}": alias
        for alias in sorted(
            WAREHOUSE_DEPARTMENT_DATA_PAGES
            | {
                "hardware-summary",
                "hardware-electrical",
                "hardware-inbound-ledger",
                "hardware-outbound-ledger",
            }
        )
    },
    **{
        f"warehouse:product-inventory:{alias}": alias
        for alias in (
            "product-summary",
            "product-inbound-ledger",
            "product-outbound-ledger",
            "product-shipping",
        )
    },
}

MENU_MODULE_TO_BUSINESS_MODULE = {
    "purchasing": "procurement",
    "rd": "research",
    "admin": "administration",
}
BUSINESS_MODULE_TO_MENU_MODULE = {
    value: key for key, value in MENU_MODULE_TO_BUSINESS_MODULE.items()
}


@dataclass(frozen=True)
class SensitiveActionDefinition:
    key: str
    name: str
    category: str
    description: str


@dataclass(frozen=True)
class PageDefinition:
    page_key: str
    module_code: str
    page_name: str
    route_path: str
    supported_scope_types: tuple[str, ...]
    sensitive_actions: tuple[SensitiveActionDefinition, ...]


@dataclass(frozen=True)
class PageApiBinding:
    """Reviewed exact route contract; never inferred from resource name or verb."""

    route_path: str
    method: str
    page_keys: tuple[str, ...]
    permission: str
    sensitive_action: str | None = None
    scope_adapter: str | None = None


# Add entries only after the endpoint's list/detail/write scope adapter has
# been verified. Draft configuration is usable before these contracts exist;
# both publication and runtime enforcement fail closed for missing contracts.
PAGE_API_BINDINGS: tuple[PageApiBinding, ...] = ()


@dataclass(frozen=True)
class ToolPageBinding:
    module_code: str | None
    name: str
    summary: str
    page_keys: tuple[str, ...]
    sensitive_action: str | None


_tool_catalog_provider: Callable[[], list[ToolPageBinding]] | None = None
_api_catalog_provider: Callable[[], list[tuple[str, str]]] | None = None


def register_api_catalog_provider(
    provider: Callable[[], list[tuple[str, str]]],
) -> None:
    global _api_catalog_provider
    _api_catalog_provider = provider


def register_tool_catalog_provider(
    provider: Callable[[], list[ToolPageBinding]],
) -> None:
    """Agent registers its projection; platform does not import business code."""
    global _tool_catalog_provider
    _tool_catalog_provider = provider


def tool_page_bindings() -> list[ToolPageBinding] | None:
    return _tool_catalog_provider() if _tool_catalog_provider else None


def collect_http_route_catalog(
    routes: Sequence[BaseRoute], *, prefix: str = ""
) -> list[tuple[str, str]]:
    """Inspect mounted routes, including hidden routes and duplicates, not docs."""
    catalog: list[tuple[str, str]] = []
    for route in routes:
        if isinstance(route, Mount):
            path = prefix + route.path
            if route.routes:
                catalog.extend(collect_http_route_catalog(route.routes, prefix=path))
            else:
                # An opaque ASGI mount cannot be certified as a reviewed HTTP API.
                catalog.append(("MOUNT", path))
        elif isinstance(route, Route):
            catalog.extend(
                (method.upper(), prefix + route.path)
                for method in sorted(route.methods or {"*"})
            )
    return catalog


def api_route_catalog(module_code: str) -> list[tuple[str, str]] | None:
    if _api_catalog_provider is None:
        return None
    prefix = f"/api/v1/{module_code}"
    return sorted(
        (method, path)
        for method, path in _api_catalog_provider()
        if path == prefix or path.startswith(prefix + "/")
    )


def api_bindings_for_module(module_code: str) -> tuple[PageApiBinding, ...]:
    prefix = f"/api/v1/{module_code}"
    return tuple(
        item
        for item in PAGE_API_BINDINGS
        if item.route_path == prefix or item.route_path.startswith(prefix + "/")
    )


def _api_binding_errors(binding: PageApiBinding) -> list[str]:
    errors: list[str] = []
    parts = binding.route_path.split("/")
    module_code = parts[3] if len(parts) >= 4 and parts[1:3] == ["api", "v1"] else None
    if module_code not in PAGES_BY_MODULE:
        errors.append("业务模块未登记")
    if binding.method not in {
        "GET",
        "HEAD",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    }:
        errors.append("请求类型未登记")
    if binding.permission not in PAGE_PERMISSION_SET:
        errors.append("页面主权限无效")
    if not binding.scope_adapter or not binding.scope_adapter.strip():
        errors.append("尚未完成数据范围适配")
    if not binding.page_keys or len(set(binding.page_keys)) != len(binding.page_keys):
        errors.append("关联页面为空或重复")
    if binding.sensitive_action and binding.permission != "operate":
        errors.append("高风险业务动作必须要求操作权限")
    if binding.method in {"PUT", "PATCH", "DELETE"} and binding.permission != "operate":
        errors.append("业务写入必须要求操作权限")
    if binding.method == "DELETE" and binding.sensitive_action != "delete":
        errors.append("删除业务记录必须登记独立删除权限")
    for key in binding.page_keys:
        page = PAGES_BY_KEY.get(key)
        if page is None or page.module_code != module_code:
            errors.append("关联页面无效或不属于目标业务模块")
        elif binding.sensitive_action and binding.sensitive_action not in {
            action.key for action in page.sensitive_actions
        }:
            errors.append(f"高风险业务动作未登记：{page.page_name}")
    return list(dict.fromkeys(errors))


def api_binding_for_route(method: str, route_path: str) -> PageApiBinding | None:
    matches = [
        item
        for item in PAGE_API_BINDINGS
        if item.method == method.upper() and item.route_path == route_path
    ]
    # A duplicate is a broken security contract, not first-match-wins.
    return (
        matches[0]
        if len(matches) == 1 and not _api_binding_errors(matches[0])
        else None
    )


def page_api_catalog_gaps(module_code: str) -> list[str]:
    gaps: list[str] = []
    for page in PAGES_BY_MODULE.get(module_code, ()):
        gaps.extend(
            f"{page.page_name}：{error}" for error in page_lifecycle_errors(page)
        )
        bindings = [
            item
            for item in PAGE_API_BINDINGS
            if page.page_key in item.page_keys and item.permission != "access"
        ]
        if not bindings:
            gaps.append(f"页面尚未完成接口权限登记：{page.page_name}")
        elif any(not item.scope_adapter for item in bindings):
            gaps.append(f"页面尚未完成数据范围适配：{page.page_name}")
    actual_routes = api_route_catalog(module_code)
    if actual_routes is None:
        gaps.append("实际业务接口目录尚未加载，无法完成发布检查")
    else:
        missing = [
            path
            for method, path in actual_routes
            if api_binding_for_route(method, path) is None
        ]
        if missing:
            gaps.append(f"仍有 {len(missing)} 个业务接口未完成页面权限登记")
        duplicates = sum(count > 1 for count in Counter(actual_routes).values())
        if duplicates:
            gaps.append(f"存在 {duplicates} 组重复业务接口，无法确定唯一处理入口")
        actual_route_set = set(actual_routes)
        orphaned = sum(
            (item.method, item.route_path) not in actual_route_set
            for item in api_bindings_for_module(module_code)
        )
        if orphaned:
            gaps.append(f"仍有 {orphaned} 条接口策略对应的业务接口已不存在")
    for binding in api_bindings_for_module(module_code):
        gaps.extend(f"接口策略无效：{error}" for error in _api_binding_errors(binding))
    return list(dict.fromkeys(gaps))


_ACTION_DEFINITIONS = {
    "approve": SensitiveActionDefinition(
        "approve", "批准业务申请", "decision", "执行批准、放行等人工责任判断"
    ),
    "reject": SensitiveActionDefinition(
        "reject", "驳回业务申请", "decision", "执行驳回、退回等人工责任判断"
    ),
    "delete": SensitiveActionDefinition(
        "delete", "删除或作废记录", "destructive", "删除、作废或撤销业务记录"
    ),
    "bulk_import": SensitiveActionDefinition(
        "bulk_import", "批量导入或覆盖", "bulk_change", "批量导入、覆盖或清空数据"
    ),
    "sensitive_export": SensitiveActionDefinition(
        "sensitive_export", "导出敏感数据", "sensitive_export", "下载或批量导出业务数据"
    ),
    "sync_config": SensitiveActionDefinition(
        "sync_config",
        "同步或修改配置",
        "integration_admin",
        "同步外部数据或修改业务配置",
    ),
    "permission_admin": SensitiveActionDefinition(
        "permission_admin",
        "管理用户权限",
        "permission_admin",
        "调整角色、用户权限或数据范围",
    ),
}


def normalize_permissions(values: Sequence[str]) -> tuple[str, ...]:
    selected = set(values)
    unknown = selected - PAGE_PERMISSION_SET
    if unknown:
        raise ValueError(f"未知页面权限: {', '.join(sorted(unknown))}")
    if "operate" in selected:
        selected.update({"query", "access"})
    elif "query" in selected:
        selected.add("access")
    return tuple(item for item in PAGE_PERMISSION_ORDER if item in selected)


def _sensitive_actions(
    page_key: str, route_path: str, page_name: str
) -> tuple[SensitiveActionDefinition, ...]:
    text = f"{page_key} {route_path}".lower()
    keys: list[str] = []
    if page_key in WAREHOUSE_MATERIAL_PAGE_ALIASES:
        keys.extend(["delete", "sync_config"])
    if page_key == "hr:employee-management:profile":
        keys.append("sync_config")
    if "approval" in text or ":approval" in page_key:
        keys.extend(["approve", "reject"])
    if any(
        token in text
        for token in (
            "ledger",
            "record",
            "employee",
            "contract",
            "request",
            "document",
            "order",
        )
    ):
        keys.extend(["delete", "sensitive_export"])
    if any(
        token in text
        for token in ("import", "ledger", "employee", "training", "request")
    ):
        keys.append("bulk_import")
    if any(token in text for token in ("settings", "config", "feishu")):
        keys.append("sync_config")
    if any(
        token in text
        for token in (
            "system:roles",
            "system:user-roles",
            "system:dept-roles",
            "system:menus",
        )
    ):
        keys.append("permission_admin")
    if route_path == "/purchasing/invoice-recognition":
        keys.append("delete")
    if route_path == "/purchasing/supplier":
        keys.extend(["bulk_import", "sensitive_export"])
    action_verbs = {
        "approve": "批准",
        "reject": "驳回",
        "delete": "删除或作废",
        "bulk_import": "批量导入或覆盖",
        "sensitive_export": "导出",
        "sync_config": "同步或配置",
        "permission_admin": "管理权限：",
    }
    employee_action_names = {
        "delete": "删除员工档案",
        "bulk_import": "批量导入员工档案",
        "sensitive_export": "导出员工敏感档案",
        "sync_config": "同步员工档案至飞书",
    }
    deviation_action_names = {
        "delete": "删除偏差记录",
        "bulk_import": "批量导入偏差记录",
        "sensitive_export": "导出偏差台账",
    }
    return tuple(
        SensitiveActionDefinition(
            key=key,
            name=employee_action_names[key]
            if page_key == "hr:employee-management:profile"
            else deviation_action_names[key]
            if page_key == "quality:deviations:deviation-ledger"
            else f"{action_verbs[key]}{page_name}",
            category=_ACTION_DEFINITIONS[key].category,
            description=_ACTION_DEFINITIONS[key].description,
        )
        for key in dict.fromkeys(keys)
    )


def _walk_pages(
    nodes: list[dict[str, object]],
    parent_key: str | None = None,
    ancestor_disabled: bool = False,
) -> list[PageDefinition]:
    definitions: list[PageDefinition] = []
    for node in nodes:
        raw_key = str(node["key"])
        page_key = f"{parent_key}:{raw_key}" if parent_key else raw_key
        route_path = str(node.get("path") or "")
        disabled = ancestor_disabled or bool(node.get("disabled"))
        menu_module = page_key.split(":", 1)[0]
        module_code = MENU_MODULE_TO_BUSINESS_MODULE.get(menu_module, menu_module)
        if route_path and not disabled and not node.get("children"):
            scopes: tuple[str, ...]
            if module_code in FIRST_BATCH_MODULES:
                scopes = ("department_tree", "departments", "all")
            else:
                scopes = ("not_applicable",)
            if (
                module_code == "procurement"
                and route_path != "/purchasing/order"
                and not any(
                    route_path.startswith(prefix)
                    for prefix in ("/purchasing/request/", "/purchasing/approval/")
                )
            ):
                scopes = ("not_applicable",)
            if (
                page_key in WAREHOUSE_MATERIAL_PAGE_ALIASES
                and WAREHOUSE_MATERIAL_PAGE_ALIASES[page_key]
                not in WAREHOUSE_DEPARTMENT_DATA_PAGES
            ):
                scopes = ("not_applicable",)
            definitions.append(
                PageDefinition(
                    page_key=page_key,
                    module_code=module_code,
                    page_name=str(node["name"]),
                    route_path=route_path,
                    supported_scope_types=scopes,
                    sensitive_actions=_sensitive_actions(
                        page_key, route_path, str(node["name"])
                    ),
                )
            )
        children = node.get("children")
        if isinstance(children, list):
            definitions.extend(_walk_pages(children, page_key, disabled))
    return definitions


PAGE_DEFINITIONS = tuple(_walk_pages(SEED_MENUS))
PAGES_BY_KEY = {item.page_key: item for item in PAGE_DEFINITIONS}
PAGES_BY_MODULE: dict[str, tuple[PageDefinition, ...]] = {
    module_code: tuple(
        item for item in PAGE_DEFINITIONS if item.module_code == module_code
    )
    for module_code in {item.module_code for item in PAGE_DEFINITIONS}
}


def _purchase_request_bindings() -> tuple[PageApiBinding, ...]:
    request_pages = tuple(
        page.page_key
        for page in PAGES_BY_MODULE["procurement"]
        if page.route_path.startswith("/purchasing/request/")
    )
    approval_pages = tuple(
        page.page_key
        for page in PAGES_BY_MODULE["procurement"]
        if page.route_path.startswith("/purchasing/approval/")
    )
    base = "/api/v1/procurement/purchase-requests"
    return tuple(
        PageApiBinding(
            route_path=base + suffix,
            method=method,
            page_keys=pages,
            permission=permission,
            sensitive_action=action,
            scope_adapter="procurement.purchase_request_department",
        )
        for method, suffix, pages, permission, action in (
            ("GET", "", request_pages + approval_pages, "query", None),
            ("GET", "/{request_id}", request_pages + approval_pages, "query", None),
            ("POST", "", request_pages, "operate", None),
            ("PUT", "/{request_id}", request_pages, "operate", None),
            ("DELETE", "/{request_id}", request_pages, "operate", "delete"),
            ("POST", "/import", request_pages, "operate", "bulk_import"),
            ("POST", "/{request_id}/submit", request_pages, "operate", None),
            ("POST", "/{request_id}/approve", approval_pages, "operate", "approve"),
            ("POST", "/{request_id}/reject", approval_pages, "operate", "reject"),
        )
    )


PAGE_API_BINDINGS = _purchase_request_bindings() + tuple(
    PageApiBinding(
        route_path="/api/v1/procurement/purchase-orders" + suffix,
        method="GET",
        page_keys=("purchasing:order",),
        permission=permission,
        sensitive_action=action,
        scope_adapter="procurement.purchase_request_department",
    )
    for suffix, permission, action in (
        ("", "query", None),
        ("/export", "operate", "sensitive_export"),
    )
    if "purchasing:order" in PAGES_BY_KEY
)

PAGE_API_BINDINGS += tuple(
    PageApiBinding(
        route_path="/api/v1/warehouse/material-pages/{page_key}" + suffix,
        method=method,
        page_keys=tuple(WAREHOUSE_MATERIAL_PAGE_ALIASES),
        permission=permission,
        sensitive_action=action,
        scope_adapter="warehouse.material_page_department",
    )
    for method, suffix, permission, action in (
        ("GET", "", "query", None),
        ("GET", "/records/{record_id}", "query", None),
        ("PUT", "/records/{record_id}", "operate", None),
        ("DELETE", "/records/{record_id}", "operate", "delete"),
    )
)

PAGE_API_BINDINGS += tuple(
    PageApiBinding(
        route_path="/api/v1/hr/employees" + suffix,
        method=method,
        page_keys=("hr:employee-management:profile",),
        permission=permission,
        sensitive_action=action,
        scope_adapter="hr.employee_department",
    )
    for method, suffix, permission, action in (
        ("GET", "", "query", None),
        ("GET", "/stats", "query", None),
        ("GET", "/by-number/{employee_number}", "query", None),
        ("GET", "/{employee_id}", "query", None),
        ("POST", "", "operate", None),
        ("PUT", "/{employee_id}", "operate", None),
        ("DELETE", "/{employee_id}", "operate", "delete"),
        ("POST", "/{employee_id}/sync-to-feishu", "operate", "sync_config"),
    )
)


def _procurement_resource_bindings() -> tuple[PageApiBinding, ...]:
    requests = tuple(
        page.page_key
        for page in PAGES_BY_MODULE["procurement"]
        if page.route_path.startswith("/purchasing/request/")
    )
    contracts = tuple(
        page.page_key
        for page in PAGES_BY_MODULE["procurement"]
        if page.route_path.startswith("/purchasing/contract-generation/")
    )
    supplier = ("purchasing:supplier",)
    invoice = ("purchasing:invoice-recognition",)
    settings = ("purchasing:settings",)
    summary = ("purchasing:contract-summary",)
    rules = (
        (
            "GET",
            "/",
            tuple(page.page_key for page in PAGES_BY_MODULE["procurement"]),
            "access",
            None,
        ),
        ("GET", "/material-source-config", settings, "query", None),
        ("PUT", "/material-source-config", settings, "operate", "sync_config"),
        ("POST", "/material-source-config/test", settings, "operate", "sync_config"),
        ("POST", "/material-source-config/sync", settings, "operate", "sync_config"),
        ("GET", "/material-catalog", ("purchasing:material-library",), "query", None),
        ("GET", "/material-options", requests, "query", None),
        ("GET", "/suppliers", supplier + contracts, "query", None),
        ("POST", "/suppliers/import", supplier, "operate", "bulk_import"),
        ("POST", "/invoices/recognize", invoice, "operate", None),
        ("GET", "/invoices/recognition-records", invoice, "query", None),
        (
            "DELETE",
            "/invoices/recognition-records/{record_id}",
            invoice,
            "operate",
            "delete",
        ),
        (
            "POST",
            "/invoices/recognition-records/batch-delete",
            invoice,
            "operate",
            "delete",
        ),
        ("GET", "/contracts", contracts + summary, "query", None),
        ("GET", "/contracts/templates/{category}", contracts, "query", None),
        ("POST", "/contracts/generate", contracts, "operate", None),
        ("GET", "/contracts/{contract_id}", contracts + summary, "query", None),
        (
            "GET",
            "/contracts/{contract_id}/file",
            contracts + summary,
            "operate",
            "sensitive_export",
        ),
    )
    return tuple(
        PageApiBinding(
            route_path="/api/v1/procurement" + path,
            method=method,
            page_keys=pages,
            permission=permission,
            sensitive_action=action,
            scope_adapter="procurement.contract_category"
            if path.startswith("/contracts")
            else "not_applicable",
        )
        for method, path, pages, permission, action in rules
    )


PAGE_API_BINDINGS += _procurement_resource_bindings()

PAGE_API_BINDINGS += tuple(
    PageApiBinding(
        route_path="/api/v1/quality/deviations" + suffix,
        method=method,
        page_keys=("quality:deviations:deviation-ledger",),
        permission=permission,
        sensitive_action=action,
        scope_adapter="quality.deviation_department",
    )
    for method, suffix, permission, action in (
        ("GET", "", "query", None),
        ("GET", "/{deviation_id}", "query", None),
        ("GET", "/{deviation_id}/related-capas", "query", None),
        ("GET", "/export", "operate", "sensitive_export"),
        ("POST", "", "operate", None),
        ("PUT", "/{deviation_id}", "operate", None),
        ("DELETE", "/{deviation_id}", "operate", "delete"),
        ("POST", "/batch-delete", "operate", "delete"),
        ("GET", "/reporter-options", "query", None),
    )
)


def get_page_definition(page_key: str) -> PageDefinition | None:
    page = PAGES_BY_KEY.get(page_key)
    return page if page is not None and not page_lifecycle_errors(page) else None


def module_for_page(page_key: str) -> str | None:
    definition = get_page_definition(page_key)
    return definition.module_code if definition else None


def page_key_for_route(route_path: str) -> str | None:
    normalized = route_path.rstrip("/") or "/"
    # Auxiliary forms belong to the ledger, never to its directory or siblings.
    if re.fullmatch(
        r"/quality/deviations/(?:new|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
        normalized,
    ):
        return "quality:deviations:deviation-ledger"
    candidates = [
        item
        for item in PAGE_DEFINITIONS
        if normalized == item.route_path.rstrip("/")
        or normalized.startswith(item.route_path.rstrip("/") + "/")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: len(item.route_path)).page_key


def sensitive_action_for_request(method: str, api_path: str) -> str | None:
    """Map server-observed business requests to high-risk categories."""
    method = method.upper()
    path = api_path.lower()
    if method == "DELETE" or any(token in path for token in ("/void", "/cancel")):
        return "delete"
    if method not in {"GET", "HEAD"}:
        if any(token in path for token in ("/approve", "/approval", "/release")):
            return "approve"
        if any(token in path for token in ("/reject", "/return")):
            return "reject"
        if any(token in path for token in ("/import", "/bulk", "/overwrite")):
            return "bulk_import"
        if any(token in path for token in ("/sync", "/config", "/settings")):
            return "sync_config"
    if any(token in path for token in ("/export", "/download-report")):
        return "sensitive_export"
    return None
