"""Keep platform administration outside Livzon's callable capability surface."""

from app.platform.identity.page_policy import get_page_definition


def tool_exclusion_reason(
    *, name: str, path: str, page_keys: tuple[str, ...], module: str | None = None
) -> str | None:
    route = path.split("?", 1)[0].rstrip("/")
    if route.startswith("/api/v1/"):
        route = route.removeprefix("/api/v1")
    segments = route.split("/")
    if any(
        page_key.startswith("system:")
        or (
            (page := get_page_definition(page_key)) is not None
            and page.route_path.startswith("/settings")
        )
        for page_key in page_keys
    ):
        return "系统设置页面不接入 Livzon"
    if any("settings" in part or "config" in part for part in segments):
        return "配置管理不接入 Livzon"
    if any("settings" in page_key for page_key in page_keys):
        return "配置管理页面不接入 Livzon"
    if route.startswith(("/identity/", "/system/", "/admin/")) or (
        name.startswith("identity.") and name != "identity.deliver_feishu_message"
    ):
        return "身份与组织管理不接入 Livzon"
    if (
        route.startswith(("/agent/operations/", "/energy/feishu/roots"))
        or route
        in {
            "/agent/automation-capability-impacts",
            "/agent/feishu-resource-templates",
        }
        or name == "agent.validate_feishu_resource_template"
    ):
        return "平台运维与资源配置不接入 Livzon"
    if module in {"identity", "system"} or name.startswith("system."):
        return "系统管理不接入 Livzon"
    if module is not None and not page_keys:
        return "业务工具缺少页面授权绑定，暂不开放"
    return None
