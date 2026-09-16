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
            "liquid-raw-inbound",
            "liquid-sugar-inbound",
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
            "product-inbound-detail",
            "product-inbound-ledger",
            "product-outbound-ledger",
            "product-shipping",
        )
    },
    **{
        f"warehouse:product-inventory:product-details:{alias}": alias
        for alias in (
            "product-detail-l-phenylalanine",
            "product-detail-fumaric-acid",
            "product-detail-l-tryptophan",
            "product-detail-mevastatin",
            "product-detail-kitasamycin-hcl",
            "product-detail-doramectin",
            "product-detail-lovastatin",
            "product-detail-florfenicol-premix",
            "product-detail-demeclocycline-hcl",
            "product-detail-fenbendazole-powder",
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
    # These pages expose migrated business workflows whose high-risk actions
    # cannot be inferred from the short menu label alone. Keep the reviewed
    # action set explicit so a new API binding cannot silently widen a page.
    explicit_actions = {
        "warehouse:warehouse-settings": ("delete",),
        "hr:departments": ("delete", "sync_config"),
        "hr:recruitment": ("delete", "sensitive_export", "sync_config"),
        "hr:onboarding": ("delete", "sensitive_export", "sync_config"),
        "hr:offboarding": ("delete", "sensitive_export", "sync_config"),
        "hr:position-transfer": (
            "approve",
            "reject",
            "delete",
            "sensitive_export",
            "sync_config",
        ),
        "hr:contracts:contracts-ledger": ("sync_config",),
        "hr:training:training-ledger": ("delete", "sync_config"),
        "hr:training:annual-plan": ("delete", "sensitive_export"),
        "hr:training:sign-in-sheet": ("delete", "sensitive_export"),
        "hr:training:trainer": ("delete", "sensitive_export", "sync_config"),
        "hr:training:position-training": ("delete", "sensitive_export"),
        "hr:training:plan-tracking": ("delete", "sensitive_export"),
        "hr:hr-settings:hr-settings-reminder": ("delete",),
        "hr:hr-settings:hr-settings-approval": ("delete",),
        "hr:hr-settings:hr-settings-dept-mapping": ("delete",),
        "hr:hr-settings:hr-settings-dept-scopes": ("delete",),
        "registration:authorization-letter": ("delete", "sensitive_export"),
        "registration:fees:inspection-contacts": ("delete",),
        "registration:knowledge": ("delete", "sensitive_export"),
        "registration:registration-settings": ("delete",),
        "production:overview": ("delete",),
        "production:plan:sales-plan": ("delete", "sync_config"),
        "production:plan:scheduling": (
            "delete",
            "bulk_import",
            "sensitive_export",
            "sync_config",
        ),
        "production:process": ("delete",),
        "production:records": ("delete", "sensitive_export"),
        "production:balance": ("delete",),
        "production:shift-log:shift-log-deviation": ("delete",),
        "production:shift-log:shift-log-summary": ("delete",),
        "production:shift-log:shift-log-handover": ("approve", "delete"),
        "production:label-verification": ("delete",),
        "production:pressure": (
            "approve",
            "delete",
            "bulk_import",
            "sensitive_export",
        ),
    }
    keys.extend(explicit_actions.get(page_key, ()))
    if page_key.startswith("registration:project:declaration-progress:"):
        keys.extend(["delete", "sensitive_export", "bulk_import"])
    if page_key.startswith("registration:certificate-management:"):
        keys.extend(["delete", "sensitive_export", "bulk_import"])
    if page_key.startswith("production:batches:"):
        # Workshop pages expose record deletion and the reviewed Feishu sync
        # settings button.  Internal stage routes resolve to the workshop
        # leaf, so both actions belong to that stable page identity.
        keys.extend(["delete", "sync_config"])
        if page_key == "production:batches:workshop-201-3":
            keys.extend(["approve", "reject", "bulk_import"])
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

# Existing warehouse menu rows created before the qualified child-key fix use
# ``warehouse:hardware:hardware-<suffix>``.  Keep the current qualified keys
# as the permission identity and accept only this reviewed, exact alias set;
# do not infer permission identities from arbitrary URL segments.
PAGE_KEY_ALIASES = {
    **{
        page_key.replace(
            "warehouse:hardware:hardware-hardware-",
            "warehouse:hardware:hardware-",
            1,
        ): page_key
        for page_key in WAREHOUSE_MATERIAL_PAGE_ALIASES
        if page_key.startswith("warehouse:hardware:hardware-hardware-")
    },
    **{
        page_key.replace(
            "warehouse:product-inventory:",
            "warehouse:product:",
            1,
        ): page_key
        for page_key in WAREHOUSE_MATERIAL_PAGE_ALIASES
        if page_key.startswith("warehouse:product-inventory:")
    },
}


def canonical_page_key(page_key: str) -> str:
    return PAGE_KEY_ALIASES.get(page_key, page_key)


# Explicit compatibility routes for module landing pages and migrated pages
# that are not leaf entries in the permission menu. These are reviewed
# aliases, not URL-segment inference; child leaf routes still resolve through
# the normal longest-route match below.
PAGE_ROUTE_ALIASES = {
    "/hr/employee-management": "hr:employee-management:profile",
    "/hr/training": "hr:training:annual-plan",
    "/hr/settings/feishu": "hr:hr-settings:hr-settings-feishu",
    "/hr/new/profile": "hr:employee-management:profile",
    "/hr/new/onboarding": "hr:onboarding",
    "/hr/new/offboarding": "hr:offboarding",
    "/hr/new/departure": "hr:offboarding",
    "/hr/new/departments": "hr:departments",
    "/warehouse/materials/dashboard": "warehouse:materials:raw-summary",
    "/warehouse/hardware/dashboard": "warehouse:hardware:hardware-hardware-summary",
    "/warehouse/product/dashboard": "warehouse:product-inventory:product-summary",
    "/registration/project": (
        "registration:project:project-ledger:international-associated-review"
    ),
    "/registration/project-ledger": (
        "registration:project:project-ledger:international-associated-review"
    ),
    "/registration/declaration-progress": (
        "registration:project:declaration-progress:international-planned-in-progress"
    ),
    "/registration/certificate-management": (
        "registration:certificate-management:international-registration"
    ),
    "/registration/fees": "registration:fees:fee-ledger",
}
PAGE_ROUTE_PREFIX_ALIASES = {
    "/registration/reference-standard": (
        "registration:project:declaration-progress:international-planned-in-progress"
    ),
    "/registration/supplementary-reply": (
        "registration:project:declaration-progress:international-planned-in-progress"
    ),
    "/registration/validation-audit": (
        "registration:project:declaration-progress:international-planned-in-progress"
    ),
    "/registration/review": (
        "registration:project:declaration-progress:international-planned-in-progress"
    ),
    "/registration/dossier-writer": (
        "registration:project:declaration-progress:international-planned-in-progress"
    ),
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


def _module_api_bindings(
    module_code: str,
    rules: Sequence[tuple[str, str, tuple[str, ...], str, str | None, str]],
) -> tuple[PageApiBinding, ...]:
    """Build bindings from an explicitly reviewed method/path matrix.

    The route path and page set are intentionally supplied together by each
    module below. This helper only applies the common API prefix; it does not
    infer page ownership from a URL segment or an HTTP verb.
    """

    return tuple(
        PageApiBinding(
            route_path=f"/api/v1/{module_code}{path}",
            method=method,
            page_keys=page_keys,
            permission=permission,
            sensitive_action=sensitive_action,
            scope_adapter=scope_adapter,
        )
        for (
            method,
            path,
            page_keys,
            permission,
            sensitive_action,
            scope_adapter,
        ) in rules
    )


def _production_api_bindings() -> tuple[PageApiBinding, ...]:
    """Register the reviewed production page-to-API contract.

    Production has several workshop-specific sub-systems behind one module
    prefix.  The page sets below are intentionally explicit: a route may be
    reused by a few reviewed pages, but ownership is never inferred from a
    resource name or from the HTTP verb.
    """

    all_pages = tuple(page.page_key for page in PAGES_BY_MODULE["production"])
    overview = ("production:overview",)
    workshop_pages = tuple(
        page.page_key
        for page in PAGES_BY_MODULE["production"]
        if page.page_key.startswith("production:batches:workshop-")
    )
    batch_context = workshop_pages + overview
    records_context = ("production:records",) + batch_context
    balance_context = ("production:balance",) + batch_context
    process_context = ("production:process",) + overview
    sales_plan_page = ("production:plan:sales-plan",)
    scheduling_page = ("production:plan:scheduling",)
    deviation_page = ("production:shift-log:shift-log-deviation",)
    summary_page = ("production:shift-log:shift-log-summary",)
    handover_page = ("production:shift-log:shift-log-handover",)
    label_page = ("production:label-verification",)
    pressure_page = ("production:pressure",)
    mc_page = ("production:batches:workshop-201-2",)
    dr_page = ("production:batches:workshop-201-3",)
    fa_page = ("production:batches:workshop-203",)
    sync_config_pages = workshop_pages + sales_plan_page + scheduling_page

    rules: list[tuple[str, str, tuple[str, ...], str, str | None, str]] = []

    def add(
        method: str,
        path: str,
        pages: tuple[str, ...],
        permission: str = "query",
        sensitive_action: str | None = None,
        scope_adapter: str = "production.module",
    ) -> None:
        rules.append((method, path, pages, permission, sensitive_action, scope_adapter))

    def add_many(
        method: str,
        paths: Sequence[str],
        pages: tuple[str, ...],
        permission: str = "query",
        sensitive_action: str | None = None,
        scope_adapter: str = "production.module",
    ) -> None:
        for path in paths:
            add(
                method,
                path,
                pages,
                permission,
                sensitive_action,
                scope_adapter,
            )

    add("GET", "/", all_pages)

    # Shared batch and dashboard APIs.
    add_many(
        "GET",
        ("/batch-profile/{batch_no}",),
        batch_context,
        scope_adapter="production.batch",
    )
    add("GET", "/batch-progress", overview, scope_adapter="production.dashboard")
    add_many(
        "GET",
        ("/batches", "/batches/{batch_id}"),
        batch_context,
        scope_adapter="production.batch",
    )
    add("POST", "/batches", batch_context, "operate", scope_adapter="production.batch")
    add(
        "PUT",
        "/batches/{batch_id}",
        batch_context,
        "operate",
        scope_adapter="production.batch",
    )
    add(
        "DELETE",
        "/batches/{batch_id}",
        batch_context,
        "operate",
        "delete",
        "production.batch",
    )
    add_many(
        "GET",
        ("/batches/{batch_id}/balance",),
        balance_context,
        scope_adapter="production.balance",
    )
    add(
        "POST",
        "/batches/{batch_id}/balance/calculate",
        balance_context,
        "operate",
        scope_adapter="production.balance",
    )
    add(
        "PUT",
        "/batches/{batch_id}/balance",
        balance_context,
        "operate",
        scope_adapter="production.balance",
    )
    add(
        "DELETE",
        "/batches/{batch_id}/balance",
        balance_context,
        "operate",
        "delete",
        "production.balance",
    )
    add_many(
        "GET",
        ("/batches/{batch_id}/materials", "/seed-cultures/{record_id}"),
        batch_context,
        scope_adapter="production.batch",
    )
    add(
        "POST",
        "/batches/{batch_id}/materials",
        batch_context,
        "operate",
        scope_adapter="production.batch",
    )
    add(
        "PUT",
        "/batches/{batch_id}/status",
        batch_context,
        "operate",
        scope_adapter="production.batch",
    )
    add(
        "PUT",
        "/materials/{material_id}",
        batch_context,
        "operate",
        scope_adapter="production.batch",
    )
    add(
        "DELETE",
        "/materials/{material_id}",
        batch_context,
        "operate",
        "delete",
        "production.batch",
    )
    add(
        "GET",
        "/batches/{batch_id}/records",
        records_context,
        scope_adapter="production.records",
    )
    add(
        "POST",
        "/records",
        records_context,
        "operate",
        scope_adapter="production.records",
    )
    add(
        "PUT",
        "/records/{record_id}",
        records_context,
        "operate",
        scope_adapter="production.records",
    )
    add(
        "DELETE",
        "/records/{record_id}",
        records_context,
        "operate",
        "delete",
        "production.records",
    )

    # Production plan, process specifications, records and Excel archives.
    add_many(
        "GET",
        ("/plans", "/plans/{plan_id}", "/sales-plan-details"),
        sales_plan_page,
        scope_adapter="production.plan",
    )
    add(
        "GET",
        "/plans/monthly-summary",
        sales_plan_page,
        scope_adapter="production.plan",
    )
    add("POST", "/plans", sales_plan_page, "operate", scope_adapter="production.plan")
    add(
        "PUT",
        "/plans/{plan_id}",
        sales_plan_page,
        "operate",
        scope_adapter="production.plan",
    )
    add(
        "DELETE",
        "/plans/{plan_id}",
        sales_plan_page,
        "operate",
        "delete",
        "production.plan",
    )
    add(
        "POST",
        "/sales-plan-details",
        sales_plan_page,
        "operate",
        scope_adapter="production.plan",
    )
    add(
        "PUT",
        "/sales-plan-details/{detail_id}",
        sales_plan_page,
        "operate",
        scope_adapter="production.plan",
    )
    add(
        "DELETE",
        "/sales-plan-details/{detail_id}",
        sales_plan_page,
        "operate",
        "delete",
        "production.plan",
    )
    add_many(
        "GET",
        ("/schedule-excel", "/schedule-excel/{archive_id}"),
        scheduling_page,
        scope_adapter="production.plan",
    )
    add(
        "POST",
        "/schedule-excel",
        scheduling_page,
        "operate",
        "bulk_import",
        "production.plan",
    )
    add(
        "DELETE",
        "/schedule-excel/{archive_id}",
        scheduling_page,
        "operate",
        "delete",
        "production.plan",
    )
    add(
        "GET",
        "/schedule-excel/{archive_id}/file",
        scheduling_page,
        "operate",
        "sensitive_export",
        "production.plan",
    )
    add_many(
        "GET",
        (
            "/process-specs",
            "/process-specs/{spec_id}",
            "/process-specs/{spec_id}/steps",
        ),
        process_context,
        scope_adapter="production.process",
    )
    add(
        "POST",
        "/process-specs",
        process_context,
        "operate",
        scope_adapter="production.process",
    )
    add(
        "PUT",
        "/process-specs/{spec_id}",
        process_context,
        "operate",
        scope_adapter="production.process",
    )
    add(
        "DELETE",
        "/process-specs/{spec_id}",
        process_context,
        "operate",
        "delete",
        "production.process",
    )
    add(
        "POST", "/steps", process_context, "operate", scope_adapter="production.process"
    )
    add(
        "PUT",
        "/steps/{step_id}",
        process_context,
        "operate",
        scope_adapter="production.process",
    )
    add(
        "DELETE",
        "/steps/{step_id}",
        process_context,
        "operate",
        "delete",
        "production.process",
    )
    add(
        "GET",
        "/steps/{step_id}/parameters",
        process_context,
        scope_adapter="production.process",
    )
    add(
        "POST",
        "/parameters",
        process_context,
        "operate",
        scope_adapter="production.process",
    )
    add(
        "PUT",
        "/parameters/{param_id}",
        process_context,
        "operate",
        scope_adapter="production.process",
    )
    add(
        "DELETE",
        "/parameters/{param_id}",
        process_context,
        "operate",
        "delete",
        "production.process",
    )

    # Shared workshop process records.  The endpoint set is common to the
    # workshop leaves because the old standalone production pages resolve to
    # the reviewed overview/batch context.
    simple_bases = (
        "/broth-receives",
        "/centrifuge1",
        "/centrifuge2",
        "/ceramic-equipment-logs",
        "/ceramic-feeds",
        "/ceramic-material-separations",
        "/ceramic-membrane-cleans",
        "/ceramic-membrane-ops",
        "/conc1",
        "/conc2",
        "/decolor1",
        "/dry",
        "/filter1",
        "/filter2",
        "/fermentation",
        "/pack",
        "/pretreatments",
        "/recrystallize",
        "/seed-cultures",
    )
    simple_ids = (
        "/broth-receives/{record_id}",
        "/centrifuge1/{rid}",
        "/centrifuge2/{rid}",
        "/ceramic-equipment-logs/{rid}",
        "/ceramic-feeds/{rid}",
        "/ceramic-material-separations/{rid}",
        "/ceramic-membrane-cleans/{rid}",
        "/ceramic-membrane-ops/{rid}",
        "/conc1/{rid}",
        "/conc2/{rid}",
        "/decolor1/{rid}",
        "/dry/{rid}",
        "/filter1/{rid}",
        "/filter2/{rid}",
        "/fermentation/{record_id}",
        "/pack/{rid}",
        "/pretreatments/{record_id}",
        "/recrystallize/{rid}",
        "/seed-cultures/{record_id}",
    )
    add_many("GET", simple_bases, batch_context, scope_adapter="production.workshop")
    add_many(
        "POST",
        simple_bases,
        batch_context,
        "operate",
        scope_adapter="production.workshop",
    )
    add_many(
        "PUT",
        simple_ids,
        batch_context,
        "operate",
        scope_adapter="production.workshop",
    )
    add_many(
        "DELETE",
        simple_ids,
        batch_context,
        "operate",
        "delete",
        "production.workshop",
    )
    add(
        "GET",
        "/fermentation/{record_id}",
        batch_context,
        scope_adapter="production.workshop",
    )
    add(
        "GET",
        "/fermentation/{record_id}/related-events",
        batch_context,
        scope_adapter="production.workshop",
    )
    add(
        "PUT",
        "/fermentation/{record_id}/status",
        batch_context,
        "operate",
        scope_adapter="production.workshop",
    )
    add_many(
        "GET",
        ("/fermentation-board",),
        overview,
        scope_adapter="production.dashboard",
    )
    # The extraction daily report is edited from the production dashboard and
    # keeps its finer-grained extraction-yield check inside the module API.
    add(
        "GET",
        "/extraction-daily-reports",
        overview,
        scope_adapter="production.dashboard",
    )
    add(
        "POST",
        "/extraction-daily-reports",
        overview,
        "operate",
        scope_adapter="production.dashboard",
    )
    add(
        "POST",
        "/fermentation-month-capacity",
        overview,
        "operate",
        scope_adapter="production.dashboard",
    )
    add_many(
        "GET",
        ("/fermentation-batch-actuals", "/tank-maintenance"),
        overview,
        scope_adapter="production.dashboard",
    )
    add_many(
        "POST",
        ("/fermentation-batch-actuals", "/tank-maintenance"),
        overview,
        "operate",
        scope_adapter="production.dashboard",
    )
    add(
        "DELETE",
        "/fermentation-batch-actuals/{item_id}",
        overview,
        "operate",
        "delete",
        "production.dashboard",
    )
    add(
        "DELETE",
        "/tank-maintenance/{item_id}",
        overview,
        "operate",
        "delete",
        "production.dashboard",
    )

    # Shift logs and handover workflows.
    add_many(
        "GET",
        (
            "/non-conforming-events",
            "/non-conforming-events/{event_id}/affected-batches",
        ),
        deviation_page,
        scope_adapter="production.shift_log",
    )
    add(
        "POST",
        "/non-conforming-events",
        deviation_page,
        "operate",
        scope_adapter="production.shift_log",
    )
    add(
        "PUT",
        "/non-conforming-events/{record_id}",
        deviation_page,
        "operate",
        scope_adapter="production.shift_log",
    )
    add(
        "DELETE",
        "/non-conforming-events/{record_id}",
        deviation_page,
        "operate",
        "delete",
        "production.shift_log",
    )
    add_many(
        "GET",
        ("/shift-logs", "/shift-logs/{record_id}"),
        summary_page,
        scope_adapter="production.shift_log",
    )
    add(
        "POST",
        "/shift-logs",
        summary_page,
        "operate",
        scope_adapter="production.shift_log",
    )
    add(
        "PUT",
        "/shift-logs/{record_id}",
        summary_page,
        "operate",
        scope_adapter="production.shift_log",
    )
    add(
        "DELETE",
        "/shift-logs/{record_id}",
        summary_page,
        "operate",
        "delete",
        "production.shift_log",
    )
    add_many(
        "GET",
        (
            "/shift-handovers",
            "/shift-handovers/positions",
            "/shift-handovers/search-users",
            "/shift-handovers/{record_id}",
        ),
        handover_page,
        scope_adapter="production.handover",
    )
    add(
        "POST",
        "/shift-handovers",
        handover_page,
        "operate",
        scope_adapter="production.handover",
    )
    add(
        "PUT",
        "/shift-handovers/{record_id}",
        handover_page,
        "operate",
        scope_adapter="production.handover",
    )
    add(
        "DELETE",
        "/shift-handovers/{record_id}",
        handover_page,
        "operate",
        "delete",
        "production.handover",
    )
    add(
        "POST",
        "/shift-handovers/{record_id}/confirm",
        handover_page,
        "operate",
        "approve",
        "production.handover",
    )

    # Production's Feishu configuration and table-sync controls are exposed
    # only from reviewed workshop/plan pages.
    add_many(
        "GET",
        (
            "/feishu-configs",
            "/feishu/tables",
            "/feishu/tables/{table_id}/data",
            "/feishu/tables/{table_id}/fields",
            "/feishu/ws/status",
        ),
        sync_config_pages,
        scope_adapter="production.feishu",
    )
    add_many(
        "PUT",
        ("/feishu-configs",),
        sync_config_pages,
        "operate",
        "sync_config",
        "production.feishu",
    )
    add_many(
        "POST",
        (
            "/feishu-configs/test",
            "/feishu/tables/refresh",
            "/feishu/tables/{table_id}/sync",
            "/feishu/ws/restart",
        ),
        sync_config_pages,
        "operate",
        "sync_config",
        "production.feishu",
    )
    add(
        "PATCH",
        "/feishu/tables/{table_id}/enabled",
        sync_config_pages,
        "operate",
        "sync_config",
        "production.feishu",
    )

    # 201-2 MC production chain.
    add_many(
        "GET",
        (
            "/mc/anomaly/status",
            "/mc/ba-records",
            "/mc/blending-records/full-list",
            "/mc/blending-records/{batch_no}/inputs",
            "/mc/chat/history",
            "/mc/crude-extract/full-list",
            "/mc/dashboard/summary",
            "/mc/extraction-records/full-list",
            "/mc/extraction-records/{batch_no}/inputs",
            "/mc/qc-inputs/{qc_batch}",
            "/mc/qc-inspections/full-list",
            "/mc/qc-inspections/{qc_id}/items",
            "/mc/refinement-records/full-list",
            "/mc/refinement-records/{batch_no}/inputs",
            "/mc/lineage/ai-analysis",
            "/mc/lineage/ai-analysis-stream",
            "/mc/lineage/ai-history",
            "/mc/lineage/coverage",
            "/mc/lineage/material-reuse",
            "/mc/lineage/trace",
            "/mc/lineage/yield-distribution",
            "/mc/sync/status",
        ),
        mc_page,
        scope_adapter="production.mc",
    )
    add_many(
        "GET",
        (
            "/mc/blending-records",
            "/mc/crude-extract/fermentation-liquids",
            "/mc/extraction-records",
            "/mc/qc-inspections",
            "/mc/refinement-records",
        ),
        mc_page,
        scope_adapter="production.mc",
    )
    add_many(
        "POST",
        (
            "/mc/anomaly/run",
            "/mc/blending-inputs",
            "/mc/blending-records",
            "/mc/chat/send",
            "/mc/crude-extract/acid-steps",
            "/mc/crude-extract/fermentation-liquids",
            "/mc/crude-extract/refining-batches",
            "/mc/crude-extract/sodium-steps",
            "/mc/extraction-inputs",
            "/mc/extraction-records",
            "/mc/qc-inputs",
            "/mc/qc-inspection-items",
            "/mc/qc-inspections",
            "/mc/refinement-inputs",
            "/mc/refinement-records",
        ),
        mc_page,
        "operate",
        scope_adapter="production.mc",
    )
    add(
        "POST",
        "/mc/blending-records/{batch_no}/calculate",
        mc_page,
        "operate",
        scope_adapter="production.mc",
    )
    add_many(
        "PUT",
        (
            "/mc/blending-records/{record_id}",
            "/mc/crude-extract/acid-steps/{record_id}",
            "/mc/crude-extract/sodium-steps/{record_id}",
            "/mc/crude-extract/sub-tank-records/{record_id}",
            "/mc/extraction-inputs/{record_id}",
            "/mc/extraction-records/{record_id}",
            "/mc/qc-inputs/{record_id}",
            "/mc/qc-inspections/{record_id}",
            "/mc/refinement-inputs/{record_id}",
            "/mc/refinement-records/{record_id}",
        ),
        mc_page,
        "operate",
        scope_adapter="production.mc",
    )
    add_many(
        "DELETE",
        (
            "/mc/blending-inputs/{record_id}",
            "/mc/blending-records/{record_id}",
            "/mc/crude-extract/refining-batches/{record_id}",
            "/mc/extraction-inputs/{record_id}",
            "/mc/extraction-records/{record_id}",
            "/mc/qc-inputs/{record_id}",
            "/mc/refinement-inputs/{record_id}",
            "/mc/refinement-records/{record_id}",
        ),
        mc_page,
        "operate",
        "delete",
        "production.mc",
    )
    add(
        "POST",
        "/mc/sync/trigger",
        mc_page,
        "operate",
        "sync_config",
        "production.mc",
    )

    # 201-3 DR production chain and its responsible decisions.
    add_many(
        "GET",
        (
            "/dr/dashboard/summary",
            "/dr/extraction/full",
            "/dr/extraction/years",
            "/dr/extractions/{extraction_id}/filtrates",
            "/dr/fermentation-batches",
            "/dr/fermentation-batches/{batch_id}/tanks",
            "/dr/lineage/coverage",
            "/dr/lineage/loss-funnel",
            "/dr/lineage/loss-stats",
            "/dr/lineage/material-reuse",
            "/dr/lineage/trace",
            "/dr/lineage/yield-distribution",
            "/dr/records",
            "/dr/records/years",
            "/dr/schedule/dump-plans",
            "/dr/schedule/tasks",
            "/dr/tanks/{tank_id}/extractions",
        ),
        dr_page,
        scope_adapter="production.dr",
    )
    add_many(
        "POST",
        (
            "/dr/extractions",
            "/dr/fermentation-batches",
            "/dr/fermentation-tanks",
            "/dr/filtrates",
        ),
        dr_page,
        "operate",
        scope_adapter="production.dr",
    )
    add_many(
        "PUT",
        (
            "/dr/extractions/{record_id}",
            "/dr/fermentation-batches/{record_id}",
            "/dr/fermentation-tanks/{record_id}",
            "/dr/filtrates/{record_id}",
        ),
        dr_page,
        "operate",
        scope_adapter="production.dr",
    )
    add_many(
        "DELETE",
        (
            "/dr/extractions/{record_id}",
            "/dr/fermentation-batches/{record_id}",
            "/dr/fermentation-tanks/{record_id}",
            "/dr/filtrates/{record_id}",
        ),
        dr_page,
        "operate",
        "delete",
        "production.dr",
    )
    add_many(
        "POST",
        (
            "/dr/schedule/tasks/{batch_no}/approve",
            "/dr/schedule/tasks/{batch_no}/confirm",
        ),
        dr_page,
        "operate",
        "approve",
        "production.dr",
    )
    add(
        "POST",
        "/dr/schedule/tasks/{batch_no}/delay",
        dr_page,
        "operate",
        "reject",
        "production.dr",
    )
    add(
        "POST",
        "/dr/schedule/upload",
        dr_page,
        "operate",
        "bulk_import",
        "production.dr",
    )

    # 203 FA production chain.
    add_many(
        "GET",
        (
            "/fa/acidification/flat-list",
            "/fa/chat/history",
            "/fa/dashboard/batch-params",
            "/fa/dashboard/golden-batches",
            "/fa/dashboard/summary",
            "/fa/dashboard/yield-chain",
            "/fa/decolor-centrifuge/list",
            "/fa/decolor1/list",
            "/fa/fermentation/batches",
            "/fa/fermentation/batches/{tank_no}",
            "/fa/fermentation/flat-list",
            "/fa/intermediate/list",
            "/fa/lineage/ai-analysis",
            "/fa/lineage/ai-analysis-stream",
            "/fa/lineage/trace",
            "/fa/monthly-averages",
            "/fa/mother-liquor/list",
            "/fa/mvr/list",
            "/fa/plate-recovery/list",
        ),
        fa_page,
        scope_adapter="production.fa",
    )
    add_many(
        "POST",
        ("/fa/chat/send",),
        fa_page,
        "operate",
        scope_adapter="production.fa",
    )
    add(
        "PUT",
        "/fa/fermentation/sub-batches/{sub_id}",
        fa_page,
        "operate",
        scope_adapter="production.fa",
    )
    add(
        "POST",
        "/fa/sync/trigger",
        fa_page,
        "operate",
        "sync_config",
        "production.fa",
    )

    # Pressure records have explicit audit, import, export and deletion
    # actions; they must not collapse into the generic workshop contract.
    add_many(
        "GET",
        (
            "/pressure/audit/stats",
            "/pressure/dashboard",
            "/pressure/data-master",
            "/pressure/notifications",
            "/pressure/ocr-tasks",
            "/pressure/ocr-tasks/{task_id}",
            "/pressure/point-mappings",
            "/pressure/point-mappings/check-unique",
            "/pressure/point-mappings/{mapping_id}",
            "/pressure/data-master/{item_id}",
            "/pressure/records",
            "/pressure/records/{record_id}",
            "/pressure/records/merged",
        ),
        pressure_page,
        scope_adapter="production.pressure",
    )
    add(
        "GET",
        "/pressure/records/export/by-area",
        pressure_page,
        "operate",
        "sensitive_export",
        "production.pressure",
    )
    add_many(
        "POST",
        ("/pressure/data-master", "/pressure/ocr-tasks", "/pressure/point-mappings"),
        pressure_page,
        "operate",
        scope_adapter="production.pressure",
    )
    add(
        "POST",
        "/pressure/data-master/batch",
        pressure_page,
        "operate",
        "bulk_import",
        "production.pressure",
    )
    add(
        "POST",
        "/pressure/data-master/batch-delete",
        pressure_page,
        "operate",
        "delete",
        "production.pressure",
    )
    add_many(
        "PUT",
        ("/pressure/data-master/{item_id}", "/pressure/point-mappings/{mapping_id}"),
        pressure_page,
        "operate",
        scope_adapter="production.pressure",
    )
    add_many(
        "DELETE",
        ("/pressure/data-master/{item_id}", "/pressure/point-mappings/{mapping_id}"),
        pressure_page,
        "operate",
        "delete",
        "production.pressure",
    )
    add_many(
        "PATCH",
        (
            "/pressure/notifications/read-all",
            "/pressure/notifications/{notification_id}/read",
        ),
        pressure_page,
        "operate",
        scope_adapter="production.pressure",
    )
    add(
        "POST",
        "/pressure/ocr-tasks/{task_id}/submit",
        pressure_page,
        "operate",
        scope_adapter="production.pressure",
    )
    add(
        "PATCH",
        "/pressure/records/batch-audit",
        pressure_page,
        "operate",
        "approve",
        "production.pressure",
    )
    add(
        "POST",
        "/pressure/records/batch-delete",
        pressure_page,
        "operate",
        "delete",
        "production.pressure",
    )
    add(
        "POST",
        "/pressure/records/manual",
        pressure_page,
        "operate",
        scope_adapter="production.pressure",
    )
    add(
        "POST",
        "/pressure/records/manual/batch",
        pressure_page,
        "operate",
        "bulk_import",
        "production.pressure",
    )
    add(
        "POST",
        "/pressure/records/merged/batch-delete",
        pressure_page,
        "operate",
        "delete",
        "production.pressure",
    )
    add(
        "POST",
        "/pressure/records/merged/delete",
        pressure_page,
        "operate",
        "delete",
        "production.pressure",
    )
    add(
        "POST",
        "/pressure/records/merged/update",
        pressure_page,
        "operate",
        scope_adapter="production.pressure",
    )
    add(
        "POST",
        "/pressure/records/ocr",
        pressure_page,
        "operate",
        "bulk_import",
        "production.pressure",
    )
    add(
        "DELETE",
        "/pressure/records/{record_id}",
        pressure_page,
        "operate",
        "delete",
        "production.pressure",
    )
    add(
        "PATCH",
        "/pressure/records/{record_id}/audit",
        pressure_page,
        "operate",
        "approve",
        "production.pressure",
    )

    # Label verification is a production workflow.  The route is mounted
    # under /production so the page grant and the endpoint module stay aligned.
    add_many(
        "GET",
        (
            "/label-verifications",
            "/label-verifications/statistics",
            "/label-verifications/batch/{batch_number}",
            "/label-verifications/{verification_id}",
        ),
        label_page,
        scope_adapter="production.label_verification",
    )
    add(
        "POST",
        "/label-verifications",
        label_page,
        "operate",
        scope_adapter="production.label_verification",
    )
    add(
        "PUT",
        "/label-verifications/{verification_id}",
        label_page,
        "operate",
        scope_adapter="production.label_verification",
    )
    add(
        "DELETE",
        "/label-verifications/{verification_id}",
        label_page,
        "operate",
        "delete",
        "production.label_verification",
    )
    add_many(
        "POST",
        (
            "/label-verifications/upload-video",
            "/label-verifications/analyze-video",
            "/label-verifications/auto-compare",
        ),
        label_page,
        "operate",
        scope_adapter="production.label_verification",
    )

    return _module_api_bindings("production", rules)


PAGE_API_BINDINGS += _production_api_bindings()


def _warehouse_api_bindings() -> tuple[PageApiBinding, ...]:
    all_pages = tuple(page.page_key for page in PAGES_BY_MODULE["warehouse"])
    material_pages = tuple(WAREHOUSE_MATERIAL_PAGE_ALIASES)
    summary_pages = (
        "warehouse:materials:raw-summary",
        "warehouse:hardware:hardware-hardware-summary",
        "warehouse:product-inventory:product-summary",
    )
    raw_summary = ("warehouse:materials:raw-summary",)
    packaging_summary = ("warehouse:materials:packaging-summary",)
    product_summary = ("warehouse:product-inventory:product-summary",)
    ai_page = ("warehouse:ai-analysis",)
    settings_page = ("warehouse:warehouse-settings",)
    page_data_read_pages = material_pages + settings_page
    rules: list[tuple[str, str, tuple[str, ...], str, str | None, str]] = [
        ("GET", "/", all_pages, "query", None, "warehouse.module"),
        ("GET", "/dashboard", summary_pages, "query", None, "warehouse.dashboard"),
        (
            "GET",
            "/inspection-progress/overview",
            summary_pages,
            "query",
            None,
            "warehouse.inspection_progress",
        ),
        (
            "GET",
            "/inspection-progress/ai-analysis",
            summary_pages,
            "query",
            None,
            "warehouse.inspection_progress",
        ),
        ("GET", "/raw-materials", raw_summary, "query", None, "warehouse.material"),
        (
            "GET",
            "/packaging-materials",
            packaging_summary,
            "query",
            None,
            "warehouse.material",
        ),
        ("GET", "/products", product_summary, "query", None, "warehouse.product"),
        (
            "GET",
            "/person-avatar-map",
            material_pages,
            "query",
            None,
            "warehouse.person_directory",
        ),
        ("GET", "/ai/anomalies", ai_page, "query", None, "warehouse.ai"),
        (
            "GET",
            "/ai/hardware-cost-anomalies",
            ai_page,
            "query",
            None,
            "warehouse.ai",
        ),
        (
            "GET",
            "/ai/hardware-cost-summary",
            ai_page,
            "query",
            None,
            "warehouse.ai",
        ),
        ("GET", "/ai/report", ai_page, "query", None, "warehouse.ai"),
        ("GET", "/ai/summary", ai_page, "query", None, "warehouse.ai"),
        (
            "GET",
            "/ai/trend-anomalies",
            ai_page,
            "query",
            None,
            "warehouse.ai",
        ),
        (
            "GET",
            "/ai/trend-product-lines",
            ai_page,
            "query",
            None,
            "warehouse.ai",
        ),
        ("GET", "/ai/trend-summary", ai_page, "query", None, "warehouse.ai"),
        (
            "GET",
            "/analysis/profiles/{profile_id}",
            ai_page,
            "query",
            None,
            "warehouse.ai",
        ),
        (
            "GET",
            "/analysis/profiles/{profile_id}/prompts",
            ai_page,
            "query",
            None,
            "warehouse.ai",
        ),
        (
            "GET",
            "/analysis/runs/{run_id}",
            ai_page,
            "query",
            None,
            "warehouse.ai",
        ),
        ("POST", "/ai/chat", ai_page, "operate", None, "warehouse.ai"),
        ("POST", "/analytics/query", ai_page, "operate", None, "warehouse.ai"),
        ("POST", "/analysis/profiles", ai_page, "operate", None, "warehouse.ai"),
        (
            "POST",
            "/analysis/profiles/{profile_id}/prompts",
            ai_page,
            "operate",
            None,
            "warehouse.ai",
        ),
        (
            "POST",
            "/analysis/profiles/{profile_id}/prompts/{prompt_id}/publish",
            ai_page,
            "operate",
            None,
            "warehouse.ai",
        ),
        (
            "POST",
            "/analysis/profiles/{profile_id}/run",
            ai_page,
            "operate",
            None,
            "warehouse.ai",
        ),
        ("GET", "/feishu-config", settings_page, "query", None, "warehouse.settings"),
        (
            "PUT",
            "/feishu-config",
            settings_page,
            "operate",
            "sync_config",
            "warehouse.settings",
        ),
        (
            "POST",
            "/feishu-config/test",
            settings_page,
            "operate",
            "sync_config",
            "warehouse.settings",
        ),
        ("GET", "/feishu/roots", settings_page, "query", None, "warehouse.settings"),
        (
            "POST",
            "/feishu/roots",
            settings_page,
            "operate",
            "sync_config",
            "warehouse.settings",
        ),
        (
            "DELETE",
            "/feishu/roots/{root_id}",
            settings_page,
            "operate",
            "delete",
            "warehouse.settings",
        ),
        (
            "POST",
            "/feishu/roots/{root_id}/discover",
            settings_page,
            "operate",
            "sync_config",
            "warehouse.settings",
        ),
        ("GET", "/feishu/tables", settings_page, "query", None, "warehouse.settings"),
        (
            "GET",
            "/feishu/tables/{table_id}/records",
            settings_page,
            "query",
            None,
            "warehouse.settings",
        ),
        (
            "POST",
            "/feishu/tables/{table_id}/sync",
            settings_page,
            "operate",
            "sync_config",
            "warehouse.settings",
        ),
        (
            "GET",
            "/feishu/ws/status",
            settings_page,
            "query",
            None,
            "warehouse.settings",
        ),
        (
            "POST",
            "/feishu/ws/restart",
            settings_page,
            "operate",
            "sync_config",
            "warehouse.settings",
        ),
        (
            "GET",
            "/page-data/{page_key}",
            page_data_read_pages,
            "query",
            None,
            "warehouse.page_mapping",
        ),
        (
            "PUT",
            "/page-data/{page_key}",
            settings_page,
            "operate",
            "sync_config",
            "warehouse.page_mapping",
        ),
        (
            "GET",
            "/page-data/{page_key}/{binding_id}/field-values/{field_id}",
            material_pages,
            "query",
            None,
            "warehouse.material_page_department",
        ),
        (
            "GET",
            "/page-data/{page_key}/{binding_id}/record/{record_id}",
            material_pages,
            "query",
            None,
            "warehouse.material_page_department",
        ),
        (
            "GET",
            "/page-data/{page_key}/{binding_id}/record/{record_id}/attachments/{field_id}/{file_token}",
            material_pages,
            "query",
            None,
            "warehouse.material_page_department",
        ),
        (
            "GET",
            "/page-data/{page_key}/{binding_id}/records",
            material_pages,
            "query",
            None,
            "warehouse.material_page_department",
        ),
        (
            "GET",
            "/page-feishu-configs",
            settings_page,
            "query",
            None,
            "warehouse.page_mapping",
        ),
        (
            "PUT",
            "/page-feishu-configs/{page_key}",
            settings_page,
            "operate",
            "sync_config",
            "warehouse.page_mapping",
        ),
    ]
    return _module_api_bindings("warehouse", rules)


def _registration_api_bindings() -> tuple[PageApiBinding, ...]:
    all_pages = tuple(page.page_key for page in PAGES_BY_MODULE["registration"])
    project_pages = tuple(
        page.page_key
        for page in PAGES_BY_MODULE["registration"]
        if ":project:project-ledger:" in page.page_key
    )
    declaration_pages = tuple(
        page.page_key
        for page in PAGES_BY_MODULE["registration"]
        if ":project:declaration-progress:" in page.page_key
    )
    authorization_page = ("registration:authorization-letter",)
    certificate_pages = tuple(
        page.page_key
        for page in PAGES_BY_MODULE["registration"]
        if page.page_key.startswith("registration:certificate-management:")
    )
    fee_ledger_page = ("registration:fees:fee-ledger",)
    inspection_contacts_page = ("registration:fees:inspection-contacts",)
    knowledge_page = ("registration:knowledge",)
    settings_page = ("registration:registration-settings",)
    rules: list[tuple[str, str, tuple[str, ...], str, str | None, str]] = [
        ("GET", "/", all_pages, "query", None, "registration.module"),
        (
            "GET",
            "/project/overview",
            project_pages,
            "query",
            None,
            "registration.project",
        ),
        (
            "GET",
            "/project-ledger/entries/{record_id}/history",
            project_pages,
            "query",
            None,
            "registration.project",
        ),
        (
            "GET",
            "/project-ledger/overview",
            project_pages,
            "query",
            None,
            "registration.project",
        ),
        (
            "GET",
            "/project-ledger/sheets/{sheet_key}",
            project_pages,
            "query",
            None,
            "registration.project",
        ),
        (
            "GET",
            "/project-ledger/workbook",
            project_pages,
            "query",
            None,
            "registration.project",
        ),
        (
            "GET",
            "/project-ledger/workbook/export",
            project_pages,
            "operate",
            "sensitive_export",
            "registration.project",
        ),
        (
            "POST",
            "/project-ledger/entries",
            project_pages,
            "operate",
            None,
            "registration.project",
        ),
        (
            "POST",
            "/project-ledger/entries/{record_id}/sub-records",
            project_pages,
            "operate",
            None,
            "registration.project",
        ),
        (
            "POST",
            "/project-ledger/workbook/import",
            project_pages,
            "operate",
            "bulk_import",
            "registration.project",
        ),
        (
            "PUT",
            "/project-ledger/entries/{record_id}",
            project_pages,
            "operate",
            None,
            "registration.project",
        ),
        (
            "DELETE",
            "/project-ledger/entries/{record_id}",
            project_pages,
            "operate",
            "delete",
            "registration.project",
        ),
        (
            "GET",
            "/declaration-progress/entries/{record_id}/history",
            declaration_pages,
            "query",
            None,
            "registration.declaration",
        ),
        (
            "GET",
            "/declaration-progress/overview",
            declaration_pages,
            "query",
            None,
            "registration.declaration",
        ),
        (
            "GET",
            "/declaration-progress/sheets/{sheet_key}",
            declaration_pages,
            "query",
            None,
            "registration.declaration",
        ),
        (
            "GET",
            "/declaration-progress/workbook",
            declaration_pages,
            "query",
            None,
            "registration.declaration",
        ),
        (
            "GET",
            "/declaration-progress/workbook/export",
            declaration_pages,
            "operate",
            "sensitive_export",
            "registration.declaration",
        ),
        (
            "POST",
            "/declaration-progress/entries",
            declaration_pages,
            "operate",
            None,
            "registration.declaration",
        ),
        (
            "POST",
            "/declaration-progress/entries/{record_id}/sub-records",
            declaration_pages,
            "operate",
            None,
            "registration.declaration",
        ),
        (
            "POST",
            "/declaration-progress/workbook/import",
            declaration_pages,
            "operate",
            "bulk_import",
            "registration.declaration",
        ),
        (
            "PUT",
            "/declaration-progress/entries/{record_id}",
            declaration_pages,
            "operate",
            None,
            "registration.declaration",
        ),
        (
            "DELETE",
            "/declaration-progress/entries/{record_id}",
            declaration_pages,
            "operate",
            "delete",
            "registration.declaration",
        ),
        (
            "GET",
            "/drugs/",
            declaration_pages,
            "query",
            None,
            "registration.declaration",
        ),
        (
            "GET",
            "/drugs/nodes",
            declaration_pages,
            "query",
            None,
            "registration.declaration",
        ),
        (
            "GET",
            "/drugs/{drug_id}",
            declaration_pages,
            "query",
            None,
            "registration.declaration",
        ),
        (
            "POST",
            "/drugs/",
            declaration_pages,
            "operate",
            None,
            "registration.declaration",
        ),
        (
            "PUT",
            "/drugs/{drug_id}",
            declaration_pages,
            "operate",
            None,
            "registration.declaration",
        ),
        (
            "DELETE",
            "/drugs/{drug_id}",
            declaration_pages,
            "operate",
            "delete",
            "registration.declaration",
        ),
        (
            "GET",
            "/authorization-letters",
            authorization_page,
            "query",
            None,
            "registration.authorization",
        ),
        (
            "GET",
            "/authorization-letters/fda",
            authorization_page,
            "query",
            None,
            "registration.authorization",
        ),
        (
            "GET",
            "/authorization-letters/fda/export",
            authorization_page,
            "operate",
            "sensitive_export",
            "registration.authorization",
        ),
        (
            "GET",
            "/authorization-letters/ledger",
            authorization_page,
            "query",
            None,
            "registration.authorization",
        ),
        (
            "GET",
            "/authorization-letters/ledger/export",
            authorization_page,
            "operate",
            "sensitive_export",
            "registration.authorization",
        ),
        (
            "GET",
            "/authorization-letters/materials",
            authorization_page,
            "query",
            None,
            "registration.authorization",
        ),
        (
            "GET",
            "/authorization-letters/materials/download",
            authorization_page,
            "operate",
            "sensitive_export",
            "registration.authorization",
        ),
        (
            "GET",
            "/authorization-letters/overview",
            authorization_page,
            "query",
            None,
            "registration.authorization",
        ),
        (
            "GET",
            "/authorization-letters/products",
            authorization_page,
            "query",
            None,
            "registration.authorization",
        ),
        (
            "GET",
            "/authorization-letters/products/{product_name}",
            authorization_page,
            "query",
            None,
            "registration.authorization",
        ),
        (
            "GET",
            "/authorization-letters/{letter_id}",
            authorization_page,
            "query",
            None,
            "registration.authorization",
        ),
        (
            "GET",
            "/authorization-letters/{letter_id}/download",
            authorization_page,
            "operate",
            "sensitive_export",
            "registration.authorization",
        ),
        (
            "POST",
            "/authorization-letters/fda",
            authorization_page,
            "operate",
            None,
            "registration.authorization",
        ),
        (
            "POST",
            "/authorization-letters/generate",
            authorization_page,
            "operate",
            None,
            "registration.authorization",
        ),
        (
            "POST",
            "/authorization-letters/ledger/mains",
            authorization_page,
            "operate",
            None,
            "registration.authorization",
        ),
        (
            "POST",
            "/authorization-letters/ledger/mains/{main_id}/updates",
            authorization_page,
            "operate",
            None,
            "registration.authorization",
        ),
        (
            "PATCH",
            "/authorization-letters/ledger/mains/{main_id}",
            authorization_page,
            "operate",
            None,
            "registration.authorization",
        ),
        (
            "PATCH",
            "/authorization-letters/ledger/updates/{update_id}",
            authorization_page,
            "operate",
            None,
            "registration.authorization",
        ),
        (
            "PUT",
            "/authorization-letters/fda/{entry_id}",
            authorization_page,
            "operate",
            None,
            "registration.authorization",
        ),
        (
            "DELETE",
            "/authorization-letters/fda/{entry_id}",
            authorization_page,
            "operate",
            "delete",
            "registration.authorization",
        ),
        (
            "DELETE",
            "/authorization-letters/ledger/mains/{main_id}",
            authorization_page,
            "operate",
            "delete",
            "registration.authorization",
        ),
        (
            "DELETE",
            "/authorization-letters/ledger/updates/{update_id}",
            authorization_page,
            "operate",
            "delete",
            "registration.authorization",
        ),
        (
            "DELETE",
            "/authorization-letters/{letter_id}",
            authorization_page,
            "operate",
            "delete",
            "registration.authorization",
        ),
        (
            "GET",
            "/certificate-management/overview",
            certificate_pages,
            "query",
            None,
            "registration.certificate",
        ),
        (
            "GET",
            "/certificate-management/sheets/{sheet_key}",
            certificate_pages,
            "query",
            None,
            "registration.certificate",
        ),
        (
            "GET",
            "/certificate-management/workbook",
            certificate_pages,
            "query",
            None,
            "registration.certificate",
        ),
        (
            "GET",
            "/certificate-management/workbook/export",
            certificate_pages,
            "operate",
            "sensitive_export",
            "registration.certificate",
        ),
        (
            "POST",
            "/certificate-management/entries",
            certificate_pages,
            "operate",
            None,
            "registration.certificate",
        ),
        (
            "POST",
            "/certificate-management/workbook/import",
            certificate_pages,
            "operate",
            "bulk_import",
            "registration.certificate",
        ),
        (
            "PUT",
            "/certificate-management/entries/{entry_id}",
            certificate_pages,
            "operate",
            None,
            "registration.certificate",
        ),
        (
            "DELETE",
            "/certificate-management/entries/{entry_id}",
            certificate_pages,
            "operate",
            "delete",
            "registration.certificate",
        ),
        (
            "GET",
            "/certificate-management/reminder-recipients",
            settings_page,
            "query",
            None,
            "registration.settings",
        ),
        (
            "GET",
            "/certificate-management/reminder-settings",
            settings_page,
            "query",
            None,
            "registration.settings",
        ),
        (
            "PUT",
            "/certificate-management/reminder-settings",
            settings_page,
            "operate",
            "sync_config",
            "registration.settings",
        ),
        (
            "POST",
            "/certificate-management/reminder-settings/test",
            settings_page,
            "operate",
            "sync_config",
            "registration.settings",
        ),
        (
            "GET",
            "/fees/dashboard",
            fee_ledger_page,
            "query",
            None,
            "registration.fees",
        ),
        ("GET", "/fees/entries", fee_ledger_page, "query", None, "registration.fees"),
        (
            "GET",
            "/fees/entries/{entry_id}",
            fee_ledger_page,
            "query",
            None,
            "registration.fees",
        ),
        ("GET", "/fees/overview", fee_ledger_page, "query", None, "registration.fees"),
        (
            "POST",
            "/fees/entries",
            fee_ledger_page,
            "operate",
            None,
            "registration.fees",
        ),
        (
            "PUT",
            "/fees/entries/{entry_id}",
            fee_ledger_page,
            "operate",
            None,
            "registration.fees",
        ),
        (
            "DELETE",
            "/fees/entries/{entry_id}",
            fee_ledger_page,
            "operate",
            "delete",
            "registration.fees",
        ),
        (
            "GET",
            "/fees/inspection-contacts",
            inspection_contacts_page,
            "query",
            None,
            "registration.fees",
        ),
        (
            "GET",
            "/fees/inspection-contacts/{contact_id}",
            inspection_contacts_page,
            "query",
            None,
            "registration.fees",
        ),
        (
            "POST",
            "/fees/inspection-contacts",
            inspection_contacts_page,
            "operate",
            None,
            "registration.fees",
        ),
        (
            "PUT",
            "/fees/inspection-contacts/{contact_id}",
            inspection_contacts_page,
            "operate",
            None,
            "registration.fees",
        ),
        (
            "DELETE",
            "/fees/inspection-contacts/{contact_id}",
            inspection_contacts_page,
            "operate",
            "delete",
            "registration.fees",
        ),
        (
            "GET",
            "/knowledge/articles",
            knowledge_page,
            "query",
            None,
            "registration.knowledge",
        ),
        (
            "GET",
            "/knowledge/articles/{article_id}",
            knowledge_page,
            "query",
            None,
            "registration.knowledge",
        ),
        (
            "GET",
            "/knowledge/articles/{article_id}/attachments",
            knowledge_page,
            "query",
            None,
            "registration.knowledge",
        ),
        (
            "GET",
            "/knowledge/articles/{article_id}/comments",
            knowledge_page,
            "query",
            None,
            "registration.knowledge",
        ),
        (
            "GET",
            "/knowledge/attachments/{attachment_id}",
            knowledge_page,
            "query",
            None,
            "registration.knowledge",
        ),
        (
            "GET",
            "/knowledge/attachments/{attachment_id}/preview",
            knowledge_page,
            "operate",
            "sensitive_export",
            "registration.knowledge",
        ),
        (
            "GET",
            "/knowledge/categories",
            knowledge_page,
            "query",
            None,
            "registration.knowledge",
        ),
        (
            "GET",
            "/knowledge/overview",
            knowledge_page,
            "query",
            None,
            "registration.knowledge",
        ),
        (
            "GET",
            "/knowledge/tasks/{task_id}",
            knowledge_page,
            "query",
            None,
            "registration.knowledge",
        ),
        (
            "POST",
            "/knowledge/articles",
            knowledge_page,
            "operate",
            None,
            "registration.knowledge",
        ),
        (
            "POST",
            "/knowledge/articles/extract",
            knowledge_page,
            "operate",
            None,
            "registration.knowledge",
        ),
        (
            "POST",
            "/knowledge/articles/{article_id}/attachments",
            knowledge_page,
            "operate",
            None,
            "registration.knowledge",
        ),
        (
            "POST",
            "/knowledge/articles/{article_id}/comments",
            knowledge_page,
            "operate",
            None,
            "registration.knowledge",
        ),
        (
            "POST",
            "/knowledge/attachments/{attachment_id}/summarize",
            knowledge_page,
            "operate",
            None,
            "registration.knowledge",
        ),
        (
            "POST",
            "/knowledge/categories",
            knowledge_page,
            "operate",
            None,
            "registration.knowledge",
        ),
        (
            "PUT",
            "/knowledge/articles/{article_id}",
            knowledge_page,
            "operate",
            None,
            "registration.knowledge",
        ),
        (
            "PUT",
            "/knowledge/categories/{category_id}",
            knowledge_page,
            "operate",
            None,
            "registration.knowledge",
        ),
        (
            "PUT",
            "/knowledge/comments/{comment_id}",
            knowledge_page,
            "operate",
            None,
            "registration.knowledge",
        ),
        (
            "DELETE",
            "/knowledge/articles/{article_id}",
            knowledge_page,
            "operate",
            "delete",
            "registration.knowledge",
        ),
        (
            "DELETE",
            "/knowledge/attachments/{attachment_id}",
            knowledge_page,
            "operate",
            "delete",
            "registration.knowledge",
        ),
        (
            "DELETE",
            "/knowledge/categories/{category_id}",
            knowledge_page,
            "operate",
            "delete",
            "registration.knowledge",
        ),
        (
            "DELETE",
            "/knowledge/comments/{comment_id}",
            knowledge_page,
            "operate",
            "delete",
            "registration.knowledge",
        ),
        ("GET", "/holidays/", settings_page, "query", None, "registration.settings"),
        (
            "POST",
            "/holidays/",
            settings_page,
            "operate",
            "sync_config",
            "registration.settings",
        ),
        (
            "PUT",
            "/holidays/{holiday_id}",
            settings_page,
            "operate",
            "sync_config",
            "registration.settings",
        ),
        (
            "DELETE",
            "/holidays/{holiday_id}",
            settings_page,
            "operate",
            "delete",
            "registration.settings",
        ),
        (
            "GET",
            "/reference-standards",
            declaration_pages,
            "query",
            None,
            "registration.declaration",
        ),
        (
            "GET",
            "/reference-standards/{record_id}",
            declaration_pages,
            "query",
            None,
            "registration.declaration",
        ),
        (
            "GET",
            "/reference-standards/{record_id}/download",
            declaration_pages,
            "operate",
            "sensitive_export",
            "registration.declaration",
        ),
        (
            "POST",
            "/reference-standards/generate",
            declaration_pages,
            "operate",
            None,
            "registration.declaration",
        ),
        (
            "POST",
            "/reference-standards/parse-coa",
            declaration_pages,
            "operate",
            None,
            "registration.declaration",
        ),
        (
            "DELETE",
            "/reference-standards/{record_id}",
            declaration_pages,
            "operate",
            "delete",
            "registration.declaration",
        ),
        (
            "GET",
            "/reference-substances/",
            declaration_pages,
            "query",
            None,
            "registration.declaration",
        ),
        (
            "GET",
            "/reference-substances/{substance_id}",
            declaration_pages,
            "query",
            None,
            "registration.declaration",
        ),
        (
            "POST",
            "/reference-substances/",
            declaration_pages,
            "operate",
            None,
            "registration.declaration",
        ),
        (
            "PUT",
            "/reference-substances/{substance_id}",
            declaration_pages,
            "operate",
            None,
            "registration.declaration",
        ),
        (
            "DELETE",
            "/reference-substances/{substance_id}",
            declaration_pages,
            "operate",
            "delete",
            "registration.declaration",
        ),
        (
            "GET",
            "/supplementary-replies",
            declaration_pages,
            "query",
            None,
            "registration.declaration",
        ),
        (
            "GET",
            "/supplementary-replies/{reply_id}",
            declaration_pages,
            "query",
            None,
            "registration.declaration",
        ),
        (
            "GET",
            "/supplementary-replies/{reply_id}/download",
            declaration_pages,
            "operate",
            "sensitive_export",
            "registration.declaration",
        ),
        (
            "POST",
            "/supplementary-replies/generate",
            declaration_pages,
            "operate",
            None,
            "registration.declaration",
        ),
        (
            "DELETE",
            "/supplementary-replies/{reply_id}",
            declaration_pages,
            "operate",
            "delete",
            "registration.declaration",
        ),
        (
            "GET",
            "/validation-audit/tasks",
            declaration_pages,
            "query",
            None,
            "registration.validation_audit",
        ),
        (
            "GET",
            "/validation-audit/tasks/{task_id}",
            declaration_pages,
            "query",
            None,
            "registration.validation_audit",
        ),
        (
            "GET",
            "/validation-audit/tasks/{task_id}/files",
            declaration_pages,
            "query",
            None,
            "registration.validation_audit",
        ),
        (
            "GET",
            "/validation-audit/tasks/{task_id}/issues",
            declaration_pages,
            "query",
            None,
            "registration.validation_audit",
        ),
        (
            "GET",
            "/validation-audit/tasks/{task_id}/report",
            declaration_pages,
            "query",
            None,
            "registration.validation_audit",
        ),
        (
            "POST",
            "/validation-audit/tasks",
            declaration_pages,
            "operate",
            None,
            "registration.validation_audit",
        ),
        (
            "POST",
            "/validation-audit/tasks/{task_id}/audit",
            declaration_pages,
            "operate",
            None,
            "registration.validation_audit",
        ),
        (
            "POST",
            "/validation-audit/tasks/{task_id}/export",
            declaration_pages,
            "operate",
            "sensitive_export",
            "registration.validation_audit",
        ),
        (
            "POST",
            "/validation-audit/tasks/{task_id}/files",
            declaration_pages,
            "operate",
            None,
            "registration.validation_audit",
        ),
        (
            "POST",
            "/validation-audit/tasks/{task_id}/parse",
            declaration_pages,
            "operate",
            None,
            "registration.validation_audit",
        ),
        (
            "PUT",
            "/validation-audit/tasks/{task_id}",
            declaration_pages,
            "operate",
            None,
            "registration.validation_audit",
        ),
        (
            "DELETE",
            "/validation-audit/tasks/{task_id}",
            declaration_pages,
            "operate",
            "delete",
            "registration.validation_audit",
        ),
    ]
    return _module_api_bindings("registration", rules)


PAGE_API_BINDINGS += _warehouse_api_bindings()
PAGE_API_BINDINGS += _registration_api_bindings()


def _hr_api_bindings() -> tuple[PageApiBinding, ...]:
    all_pages = tuple(page.page_key for page in PAGES_BY_MODULE["hr"])
    departments = ("hr:departments",)
    profile = ("hr:employee-management:profile",)
    recruitment = ("hr:recruitment",)
    onboarding = ("hr:onboarding",)
    offboarding = ("hr:offboarding",)
    position_transfer = ("hr:position-transfer",)
    contracts = ("hr:contracts:contracts-ledger",)
    contract_approval = ("hr:contracts:contract-approval-results",)
    annual_plan = ("hr:training:annual-plan",)
    sign_in = ("hr:training:sign-in-sheet",)
    new_employee_training = ("hr:training:new-employee-training",)
    training_ledger = ("hr:training:training-ledger",)
    training_ledger_pages = training_ledger + sign_in
    employee_training = ("hr:training:employee-training-list",)
    trainer = ("hr:training:trainer",)
    position_training = ("hr:training:position-training",)
    plan_tracking = ("hr:training:plan-tracking",)
    settings_feishu = ("hr:hr-settings:hr-settings-feishu",)
    settings_reminder = ("hr:hr-settings:hr-settings-reminder",)
    settings_approval = ("hr:hr-settings:hr-settings-approval",)
    settings_mapping = ("hr:hr-settings:hr-settings-dept-mapping",)
    settings_scopes = ("hr:hr-settings:hr-settings-dept-scopes",)
    # 培训各页共用的部门目录只读接口（列表/自定义/映射）允许的页面集合；
    # 浏览器经代理会带上来源页路径，缺登记会导致培训页 403。
    training_departments_pages = (
        annual_plan
        + sign_in
        + new_employee_training
        + training_ledger
        + employee_training
        + trainer
        + position_training
        + plan_tracking
        + settings_mapping
        + settings_scopes
        + settings_reminder
    )
    rules: list[tuple[str, str, tuple[str, ...], str, str | None, str]] = []

    def add(
        method: str,
        path: str,
        pages: tuple[str, ...],
        permission: str = "query",
        sensitive_action: str | None = None,
        scope_adapter: str = "hr.not_applicable",
    ) -> None:
        rules.append((method, path, pages, permission, sensitive_action, scope_adapter))

    def add_many(
        method: str,
        paths: tuple[str, ...],
        pages: tuple[str, ...],
        permission: str = "query",
        sensitive_action: str | None = None,
        scope_adapter: str = "hr.not_applicable",
    ) -> None:
        for path in paths:
            add(method, path, pages, permission, sensitive_action, scope_adapter)

    add("GET", "/", all_pages, scope_adapter="hr.module")

    add_many(
        "GET",
        (
            "/departments",
            "/departments/org-tree",
            "/departments/sync-status",
            "/departments/tree",
            "/departments/{department_id}",
            "/new/departments",
            "/teams",
            "/teams/{team_id}",
        ),
        departments,
        scope_adapter="hr.department_tree",
    )
    add_many(
        "POST",
        ("/departments", "/teams"),
        departments,
        permission="operate",
        scope_adapter="hr.department_tree",
    )
    add(
        "POST",
        "/departments/sync-from-feishu",
        departments,
        "operate",
        "sync_config",
        "hr.department_tree",
    )
    add_many(
        "PUT",
        ("/departments/{department_id}", "/teams/{team_id}"),
        departments,
        permission="operate",
        scope_adapter="hr.department_tree",
    )
    add_many(
        "DELETE",
        ("/departments/{department_id}", "/teams/{team_id}"),
        departments,
        permission="operate",
        sensitive_action="delete",
        scope_adapter="hr.department_tree",
    )

    add_many(
        "GET",
        (
            "/employees/contract-expiring",
            "/employees/contract-expiring/push-status",
            "/employees/max-seq",
            "/employees/new-hires",
            "/employees/sync-status",
            "/new/employees",
        ),
        profile,
        scope_adapter="hr.employee_department",
    )
    add(
        "GET",
        "/employees/contract-expiring/export",
        profile,
        permission="operate",
        sensitive_action="sensitive_export",
        scope_adapter="hr.employee_department",
    )
    add_many(
        "POST",
        (
            "/employees/contract-expiring/push-notify",
            "/employees/contract-expiring/template",
            "/employees/public-create",
        ),
        profile,
        permission="operate",
        scope_adapter="hr.employee_department",
    )
    add(
        "POST",
        "/employees/sync-from-feishu",
        profile,
        "operate",
        "sync_config",
        "hr.employee_department",
    )

    add_many(
        "GET",
        ("/candidates", "/candidates/{record_id}", "/jobs", "/jobs/{record_id}"),
        recruitment,
        scope_adapter="hr.recruitment_record",
    )
    add(
        "GET",
        "/candidates/sync-from-feishu",
        recruitment,
        "operate",
        "sync_config",
        "hr.recruitment_record",
    )
    add(
        "GET",
        "/candidates/{record_id}/resume-file",
        recruitment,
        permission="operate",
        sensitive_action="sensitive_export",
        scope_adapter="hr.recruitment_record",
    )
    add_many(
        "GET",
        ("/email/config", "/email/offer-template"),
        recruitment,
        scope_adapter="hr.recruitment_record",
    )
    add_many(
        "POST",
        (
            "/candidates/ai-analyze-batch",
            "/candidates/{candidate_id}/send-notice",
            "/jobs",
            "/email/browse-folder",
            "/email/config/test",
            "/email/fetch-now",
            "/email/send-offer",
            "/email/upload-offer-template",
        ),
        recruitment,
        permission="operate",
        scope_adapter="hr.recruitment_record",
    )
    add(
        "PUT",
        "/candidates/{record_id}",
        recruitment,
        "operate",
        scope_adapter="hr.recruitment_record",
    )
    add(
        "PUT",
        "/jobs/{record_id}",
        recruitment,
        "operate",
        scope_adapter="hr.recruitment_record",
    )
    add(
        "PUT",
        "/email/config",
        recruitment,
        "operate",
        "sync_config",
        "hr.recruitment_record",
    )
    add(
        "DELETE",
        "/candidates/{record_id}",
        recruitment,
        "operate",
        "delete",
        "hr.recruitment_record",
    )

    add_many(
        "GET",
        (
            "/onboarding",
            "/onboarding-records",
            "/onboarding-records/sync-status",
            "/onboarding-records/{record_id}",
            "/onboarding/names",
            "/onboarding/{record_id}",
            "/new/onboarding-records",
            "/employees/{employee_id}/onboarding-evaluation",
            "/employees/{employee_id}/onboarding-training-record",
            "/employees/{employee_id}/prejob-training-plan",
        ),
        onboarding,
        scope_adapter="hr.employee_department",
    )
    add(
        "GET",
        "/onboarding/{record_id}/attachments/{file_token}/content",
        onboarding,
        permission="operate",
        sensitive_action="sensitive_export",
        scope_adapter="hr.employee_department",
    )
    add_many(
        "POST",
        (
            "/onboarding/attachments",
            "/onboarding/from-interview",
            "/onboarding-evaluation",
        ),
        onboarding,
        permission="operate",
        scope_adapter="hr.employee_department",
    )
    add(
        "POST",
        "/onboarding-records/sync-from-feishu",
        onboarding,
        "operate",
        "sync_config",
        "hr.employee_department",
    )
    add(
        "POST",
        "/onboarding/{record_id}/sync-to-employee",
        onboarding,
        "operate",
        "sync_config",
        "hr.employee_department",
    )
    add(
        "PUT",
        "/onboarding/{record_id}",
        onboarding,
        "operate",
        scope_adapter="hr.employee_department",
    )
    add(
        "DELETE",
        "/onboarding/{record_id}",
        onboarding,
        "operate",
        "delete",
        "hr.employee_department",
    )

    add_many(
        "GET",
        (
            "/departure-records",
            "/departure-records/sync-status",
            "/departure-records/{record_id}",
            "/offboarding-records",
            "/offboarding-records/{record_id}",
            "/new/departure-records",
            "/new/offboarding-records",
            "/turnover-analysis",
        ),
        offboarding,
        scope_adapter="hr.employee_department",
    )
    add_many(
        "POST",
        ("/departure-records", "/offboarding-records"),
        offboarding,
        permission="operate",
        scope_adapter="hr.employee_department",
    )
    add_many(
        "POST",
        (
            "/departure-records/sync-from-feishu",
            "/offboarding-records/sync-from-feishu",
        ),
        offboarding,
        permission="operate",
        sensitive_action="sync_config",
        scope_adapter="hr.employee_department",
    )
    add(
        "POST",
        "/offboarding-records/{record_id}/certificate",
        offboarding,
        permission="operate",
        scope_adapter="hr.employee_department",
    )
    add_many(
        "PUT",
        ("/departure-records/{record_id}", "/offboarding-records/{record_id}"),
        offboarding,
        permission="operate",
        scope_adapter="hr.employee_department",
    )
    add_many(
        "DELETE",
        ("/departure-records/{record_id}", "/offboarding-records/{record_id}"),
        offboarding,
        permission="operate",
        sensitive_action="delete",
        scope_adapter="hr.employee_department",
    )

    add_many(
        "GET",
        (
            "/position-transfers",
            "/position-transfers/approvals",
            "/position-transfers/{record_id}",
        ),
        position_transfer,
        scope_adapter="hr.employee_department",
    )
    add(
        "GET",
        "/position-transfers/{record_id}/export",
        position_transfer,
        permission="operate",
        sensitive_action="sensitive_export",
        scope_adapter="hr.employee_department",
    )
    add_many(
        "POST",
        ("/position-transfers", "/position-transfers/{record_id}/submit"),
        position_transfer,
        permission="operate",
        scope_adapter="hr.employee_department",
    )
    add(
        "POST",
        "/position-transfers/sync-from-feishu",
        position_transfer,
        "operate",
        "sync_config",
        "hr.employee_department",
    )
    add(
        "POST",
        "/position-transfers/{record_id}/approve-node",
        position_transfer,
        "operate",
        "approve",
        "hr.employee_department",
    )
    add(
        "POST",
        "/position-transfers/{record_id}/reject-node",
        position_transfer,
        "operate",
        "reject",
        "hr.employee_department",
    )
    add(
        "PUT",
        "/position-transfers/{record_id}",
        position_transfer,
        "operate",
        scope_adapter="hr.employee_department",
    )
    add(
        "DELETE",
        "/position-transfers/{record_id}",
        position_transfer,
        "operate",
        "delete",
        "hr.employee_department",
    )

    add_many(
        "GET",
        ("/contracts", "/contracts/{record_id}"),
        contracts,
        scope_adapter="hr.employee_department",
    )
    add(
        "GET",
        "/contracts/approval-callback",
        contract_approval,
        scope_adapter="hr.contract_approval",
    )
    add(
        "GET",
        "/contracts/approval-results",
        contract_approval,
        scope_adapter="hr.contract_approval",
    )
    add(
        "GET",
        "/contracts/approval-results/export",
        contract_approval,
        permission="operate",
        sensitive_action="sensitive_export",
        scope_adapter="hr.contract_approval",
    )
    add_many(
        "POST",
        ("/contracts", "/contracts/approval-callback", "/contracts/{record_id}/renew"),
        contracts,
        permission="operate",
        scope_adapter="hr.employee_department",
    )
    add_many(
        "POST",
        ("/contracts/sync-from-feishu", "/contracts/sync-from-onboarding"),
        contracts,
        permission="operate",
        sensitive_action="sync_config",
        scope_adapter="hr.employee_department",
    )
    add_many(
        "PUT",
        ("/contracts/{record_id}", "/contracts/{record_id}/sign-status"),
        contracts,
        permission="operate",
        scope_adapter="hr.employee_department",
    )
    add(
        "DELETE",
        "/contracts/{record_id}",
        contracts,
        "operate",
        "delete",
        "hr.employee_department",
    )

    add_many(
        "GET",
        (
            "/annual-training-plans",
            "/annual-training-plans/{plan_id}",
            "/annual-training-plans/{plan_id}/attachment-sections",
            "/annual-training-plans/{plan_id}/attachments",
            "/annual-training-plans/{plan_id}/items",
        ),
        annual_plan,
        scope_adapter="hr.training_department",
    )
    add_many(
        "GET",
        (
            "/annual-training-plans/{plan_id}/export",
            "/annual-training-plan-attachments/{attachment_id}/download",
            "/annual-training-plan-attachments/{attachment_id}/preview",
            "/plan-attachment-sections/{section_id}/preview",
        ),
        annual_plan,
        permission="operate",
        sensitive_action="sensitive_export",
        scope_adapter="hr.training_department",
    )
    add_many(
        "POST",
        ("/annual-training-plans", "/annual-training-plans/{plan_id}/attachments"),
        annual_plan,
        permission="operate",
        scope_adapter="hr.training_department",
    )
    add(
        "POST",
        "/annual-training-plans/import",
        annual_plan,
        "operate",
        "bulk_import",
        "hr.training_department",
    )
    add(
        "POST",
        "/annual-training-plan-attachments/mark-ledger-imported",
        annual_plan,
        "operate",
        "bulk_import",
        "hr.training_department",
    )
    add_many(
        "PUT",
        (
            "/annual-training-plans/{plan_id}",
            "/annual-training-plans/{plan_id}/items/batch",
        ),
        annual_plan,
        permission="operate",
        scope_adapter="hr.training_department",
    )
    add_many(
        "DELETE",
        (
            "/annual-training-plans/{plan_id}",
            "/annual-training-plan-attachments/{attachment_id}",
        ),
        annual_plan,
        permission="operate",
        sensitive_action="delete",
        scope_adapter="hr.training_department",
    )

    add_many(
        "GET",
        (
            "/new-employee-training/available-trainees",
            "/new-employee-training/plans",
            "/new-employee-training/plans/{plan_id}",
            "/new-employee-training/stats",
        ),
        new_employee_training,
        scope_adapter="hr.training_department",
    )
    add(
        "GET",
        "/new-employee-training/plans/{plan_id}/export-confirmation",
        new_employee_training,
        permission="operate",
        sensitive_action="sensitive_export",
        scope_adapter="hr.training_department",
    )
    add_many(
        "POST",
        (
            "/new-employee-training/plans/generate",
            "/new-employee-training/plans/manual-add",
            "/new-employee-training/plans/{plan_id}/items",
            "/new-employee-training/plans/{plan_id}/start-training",
        ),
        new_employee_training,
        permission="operate",
        scope_adapter="hr.training_department",
    )
    add(
        "PUT",
        "/new-employee-training/plans/{plan_id}",
        new_employee_training,
        "operate",
        scope_adapter="hr.training_department",
    )
    add(
        "DELETE",
        "/new-employee-training/plans/{plan_id}",
        new_employee_training,
        "operate",
        "delete",
        "hr.training_department",
    )

    add_many(
        "GET",
        (
            "/esg-training-records",
            "/esg-training-records/filter-options",
            "/esg-training-records/{record_id}",
        ),
        training_ledger,
        scope_adapter="hr.training_department",
    )
    add(
        "GET",
        "/esg-training-records/export",
        training_ledger,
        permission="operate",
        sensitive_action="sensitive_export",
        scope_adapter="hr.training_department",
    )
    add(
        "POST",
        "/esg-training-records",
        training_ledger,
        "operate",
        scope_adapter="hr.training_department",
    )
    add(
        "POST",
        "/esg-training-records/batch-delete",
        training_ledger,
        "operate",
        "delete",
        "hr.training_department",
    )
    add(
        "POST",
        "/esg-training-records/import",
        training_ledger,
        "operate",
        "bulk_import",
        "hr.training_department",
    )
    add(
        "POST",
        "/esg-training-records/sync-from-ledger",
        training_ledger,
        "operate",
        "sync_config",
        "hr.training_department",
    )
    add(
        "PUT",
        "/esg-training-records/{record_id}",
        training_ledger,
        "operate",
        scope_adapter="hr.training_department",
    )
    add(
        "DELETE",
        "/esg-training-records/{record_id}",
        training_ledger,
        "operate",
        "delete",
        "hr.training_department",
    )

    add_many(
        "GET",
        (
            "/training-ledgers",
            "/training-ledgers/pages",
            "/training-ledgers/{record_id}",
        ),
        training_ledger_pages,
        scope_adapter="hr.training_department",
    )
    add_many(
        "GET",
        ("/training-ledgers/export", "/training-ledgers/export-by-dept"),
        training_ledger,
        permission="operate",
        sensitive_action="sensitive_export",
        scope_adapter="hr.training_department",
    )
    add_many(
        "POST",
        (
            "/training-ledgers",
            "/training-ledgers/check-conflict",
            "/training-ledgers/confirm-exam-scores",
            "/training-ledgers/pages",
        ),
        training_ledger,
        permission="operate",
        scope_adapter="hr.training_department",
    )
    add(
        "POST",
        "/training-ledgers/batch-delete",
        training_ledger,
        "operate",
        "delete",
        "hr.training_department",
    )
    add_many(
        "POST",
        (
            "/training-ledgers/import-by-dept",
            "/training-ledgers/import-confirm",
            "/training-ledgers/import-exam-scores",
            "/training-ledgers/import-preview",
        ),
        training_ledger,
        permission="operate",
        sensitive_action="bulk_import",
        scope_adapter="hr.training_department",
    )
    add(
        "PUT",
        "/training-ledgers/{record_id}",
        training_ledger,
        "operate",
        scope_adapter="hr.training_department",
    )
    add_many(
        "DELETE",
        ("/training-ledgers/by-dept", "/training-ledgers/{record_id}"),
        training_ledger,
        permission="operate",
        sensitive_action="delete",
        scope_adapter="hr.training_department",
    )

    add_many(
        "GET",
        (
            "/ai/exam/generate-written/{job_id}",
            "/training-content-used",
            "/training-documents/{doc_id}",
            "/training-evaluations",
            "/training-evaluations/{evaluation_id}",
            "/training-sessions/{session_id}",
        ),
        sign_in,
        scope_adapter="hr.training_department",
    )
    add_many(
        "GET",
        (
            "/training-evaluations/export/{evaluation_id}",
            "/training-sessions/{session_id}/documents",
        ),
        sign_in,
        permission="operate",
        sensitive_action="sensitive_export",
        scope_adapter="hr.training_department",
    )
    add_many(
        "POST",
        (
            "/ai/chat/stream",
            "/ai/exam/extract-text",
            "/ai/exam/generate",
            "/ai/exam/generate-oral",
            "/ai/exam/generate-written",
            "/training-attachment",
            "/training-content-used",
            "/training-documents/upsert",
            "/training-evaluation",
            "/training-evaluations",
            "/training-notification",
            "/training-notifications/send",
            "/training-sessions/from-ledger",
            "/training-sessions/upsert",
            "/training-sign-in-sheet",
        ),
        sign_in,
        permission="operate",
        scope_adapter="hr.training_department",
    )
    add_many(
        "POST",
        (
            "/ai/exam/export",
            "/ai/exam/export-written",
            "/training-oral-exam/export",
            "/training-practical-exam/export",
        ),
        sign_in,
        permission="operate",
        sensitive_action="sensitive_export",
        scope_adapter="hr.training_department",
    )
    add(
        "POST",
        "/training-practical-exam/import",
        sign_in,
        "operate",
        "bulk_import",
        "hr.training_department",
    )
    add_many(
        "PUT",
        ("/training-evaluations/{evaluation_id}",),
        sign_in,
        permission="operate",
        scope_adapter="hr.training_department",
    )
    add(
        "DELETE",
        "/training-evaluations/{evaluation_id}",
        sign_in,
        "operate",
        "delete",
        "hr.training_department",
    )

    add_many(
        "GET",
        (
            "/training/employee-training-list/members",
            "/training/employee-training-list/records",
            "/training/employee-training-lists",
        ),
        employee_training,
        scope_adapter="hr.training_department",
    )
    add(
        "GET",
        "/training/employee-training-list/export",
        employee_training,
        permission="operate",
        sensitive_action="sensitive_export",
        scope_adapter="hr.training_department",
    )
    add(
        "POST",
        "/training/employee-training-list/members",
        employee_training,
        "operate",
        scope_adapter="hr.training_department",
    )
    add(
        "POST",
        "/training/employee-training-list/members/import-feishu",
        employee_training,
        "operate",
        "bulk_import",
        "hr.training_department",
    )
    add(
        "PUT",
        "/training/employee-training-list/members/{member_id}",
        employee_training,
        "operate",
        scope_adapter="hr.training_department",
    )
    add(
        "DELETE",
        "/training/employee-training-list/members/{member_id}",
        employee_training,
        "operate",
        "delete",
        "hr.training_department",
    )

    add_many(
        "GET",
        ("/trainers", "/trainers/{trainer_id}"),
        trainer,
        scope_adapter="hr.training_department",
    )
    add(
        "GET",
        "/trainers/export",
        trainer,
        permission="operate",
        sensitive_action="sensitive_export",
        scope_adapter="hr.training_department",
    )
    add(
        "POST",
        "/trainers",
        trainer,
        "operate",
        scope_adapter="hr.training_department",
    )
    add(
        "POST",
        "/trainers/import",
        trainer,
        "operate",
        "bulk_import",
        "hr.training_department",
    )
    add(
        "PUT",
        "/trainers/{trainer_id}",
        trainer,
        "operate",
        scope_adapter="hr.training_department",
    )
    add(
        "DELETE",
        "/trainers/{trainer_id}",
        trainer,
        "operate",
        "delete",
        "hr.training_department",
    )
    add(
        "GET",
        "/training-personnel-configs",
        trainer,
        scope_adapter="hr.training_department",
    )
    add(
        "POST",
        "/training-personnel-configs",
        trainer,
        "operate",
        "sync_config",
        "hr.training_department",
    )
    add(
        "DELETE",
        "/training-personnel-configs/{config_id}",
        trainer,
        "operate",
        "delete",
        "hr.training_department",
    )

    add_many(
        "GET",
        (
            "/position-training-lists",
            "/position-training-lists/departments",
            "/position-training-lists/departments/{department}/positions",
            "/position-training-lists/{list_id}",
            "/position-training-mappings",
        ),
        position_training,
        scope_adapter="hr.training_department",
    )
    add(
        "GET",
        "/position-training-lists/{list_id}/export",
        position_training,
        permission="operate",
        sensitive_action="sensitive_export",
        scope_adapter="hr.training_department",
    )
    add_many(
        "POST",
        (
            "/position-training-lists",
            "/position-training-lists/import",
            "/position-training-mappings",
        ),
        position_training,
        permission="operate",
        scope_adapter="hr.training_department",
    )
    add(
        "PUT",
        "/position-training-lists/{list_id}",
        position_training,
        "operate",
        scope_adapter="hr.training_department",
    )
    add(
        "PUT",
        "/position-training-lists/{list_id}/items/batch",
        position_training,
        "operate",
        "bulk_import",
        "hr.training_department",
    )
    add(
        "PUT",
        "/training/dept-mappings/{mapping_id}",
        settings_mapping,
        "operate",
        "sync_config",
        "hr.settings",
    )
    add(
        "DELETE",
        "/position-training-lists/by-dept/clear",
        position_training,
        "operate",
        "delete",
        "hr.training_department",
    )
    add_many(
        "DELETE",
        (
            "/position-training-lists/{list_id}",
            "/position-training-mappings/{mapping_id}",
        ),
        position_training,
        permission="operate",
        sensitive_action="delete",
        scope_adapter="hr.training_department",
    )

    add(
        "GET",
        "/plan-tracking",
        plan_tracking,
        scope_adapter="hr.training_department",
    )
    add(
        "GET",
        "/plan-tracking/export",
        plan_tracking,
        permission="operate",
        sensitive_action="sensitive_export",
        scope_adapter="hr.training_department",
    )
    add_many(
        "GET",
        ("/plan-tracking/period", "/plan-tracking/{record_id}"),
        plan_tracking,
        scope_adapter="hr.training_department",
    )
    add(
        "POST",
        "/plan-tracking",
        plan_tracking,
        "operate",
        scope_adapter="hr.training_department",
    )
    add(
        "PUT",
        "/plan-tracking/{record_id}",
        plan_tracking,
        "operate",
        scope_adapter="hr.training_department",
    )
    add(
        "DELETE",
        "/plan-tracking/{record_id}",
        plan_tracking,
        "operate",
        "delete",
        "hr.training_department",
    )

    add_many(
        "GET",
        (
            "/feishu-settings/app",
            "/feishu-settings/entities",
            "/feishu-settings/entities/{entity_code}/field-mapping",
            "/feishu-settings/entities/{entity_code}/tables",
            "/hr-settings/feishu-members",
            "/hr-settings/feishu-members/departments",
            "/hr-settings/hr-members",
            "/hr-settings/hr-members/sync-status",
        ),
        settings_feishu,
        scope_adapter="hr.settings",
    )
    add_many(
        "POST",
        (
            "/feishu-settings/app/test",
            "/feishu-settings/entities/{entity_code}/test",
            "/hr-settings/hr-members/sync",
        ),
        settings_feishu,
        permission="operate",
        sensitive_action="sync_config",
        scope_adapter="hr.settings",
    )
    add_many(
        "PUT",
        ("/feishu-settings/app", "/feishu-settings/entities/{entity_code}"),
        settings_feishu,
        permission="operate",
        sensitive_action="sync_config",
        scope_adapter="hr.settings",
    )

    add_many(
        "GET",
        (
            "/hr-settings/reminders",
            "/hr-settings/reminders/{config_id}/dept-recipients",
            "/hr-settings/offboarding-template",
        ),
        settings_reminder,
        scope_adapter="hr.settings",
    )
    add(
        "PUT",
        "/hr-settings/reminders/{config_id}",
        settings_reminder,
        "operate",
        "sync_config",
        "hr.settings",
    )
    add(
        "PUT",
        "/hr-settings/reminders/{config_id}/dept-recipients",
        settings_reminder,
        "operate",
        "sync_config",
        "hr.settings",
    )
    add_many(
        "POST",
        ("/hr-settings/offboarding-template",),
        settings_reminder,
        permission="operate",
        sensitive_action="sync_config",
        scope_adapter="hr.settings",
    )
    add_many(
        "DELETE",
        (
            "/hr-settings/reminders-by-entity",
            "/hr-settings/dept-recipients/{dept_recipient_id}",
        ),
        settings_reminder,
        permission="operate",
        sensitive_action="delete",
        scope_adapter="hr.settings",
    )

    add(
        "GET",
        "/hr-settings/approvals",
        settings_approval,
        scope_adapter="hr.settings",
    )
    add(
        "PUT",
        "/hr-settings/approvals/{config_id}",
        settings_approval,
        "operate",
        "sync_config",
        "hr.settings",
    )
    add(
        "DELETE",
        "/hr-settings/approvals-by-entity",
        settings_approval,
        "operate",
        "delete",
        "hr.settings",
    )

    add_many(
        "GET",
        ("/dept-approval-configs", "/dept-approval-configs/names"),
        settings_approval,
        scope_adapter="hr.settings",
    )
    add(
        "POST",
        "/dept-approval-configs",
        settings_approval,
        "operate",
        "sync_config",
        "hr.settings",
    )
    add(
        "POST",
        "/dept-approval-configs/init-from-departments",
        settings_approval,
        "operate",
        "sync_config",
        "hr.settings",
    )
    add(
        "PUT",
        "/dept-approval-configs/{config_id}",
        settings_approval,
        "operate",
        "sync_config",
        "hr.settings",
    )
    add(
        "DELETE",
        "/dept-approval-configs/{config_id}",
        settings_approval,
        "operate",
        "delete",
        "hr.settings",
    )

    add_many(
        "GET",
        ("/dept-scopes", "/dept-scopes/{user_id}"),
        settings_scopes,
        scope_adapter="hr.settings",
    )
    add(
        "PUT",
        "/dept-scopes/{user_id}",
        settings_scopes,
        "operate",
        "sync_config",
        "hr.settings",
    )
    add(
        "DELETE",
        "/dept-scopes/{user_id}",
        settings_scopes,
        "operate",
        "delete",
        "hr.settings",
    )

    add_many(
        "GET",
        (
            "/training/departments",
            "/training/departments/custom",
            "/training/dept-mappings",
        ),
        training_departments_pages,
        scope_adapter="hr.settings",
    )
    add(
        "POST",
        "/training/departments",
        settings_mapping + training_ledger,
        "operate",
        "sync_config",
        "hr.settings",
    )
    add(
        "POST",
        "/training/dept-mappings",
        settings_mapping,
        "operate",
        "sync_config",
        "hr.settings",
    )
    add(
        "DELETE",
        "/training/departments/{name}",
        settings_mapping + training_ledger,
        "operate",
        "delete",
        "hr.settings",
    )
    add(
        "DELETE",
        "/training/dept-mappings/{mapping_id}",
        settings_mapping,
        "operate",
        "delete",
        "hr.settings",
    )

    add(
        "POST",
        "/webhook/feishu-approval",
        settings_approval,
        "operate",
        "sync_config",
        "hr.settings",
    )
    return _module_api_bindings("hr", rules)


PAGE_API_BINDINGS += _hr_api_bindings()


def get_page_definition(page_key: str) -> PageDefinition | None:
    page = PAGES_BY_KEY.get(canonical_page_key(page_key))
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
    alias = PAGE_ROUTE_ALIASES.get(normalized)
    if alias is not None:
        return alias
    for prefix, page_key in PAGE_ROUTE_PREFIX_ALIASES.items():
        if normalized == prefix or normalized.startswith(prefix + "/"):
            return page_key
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
