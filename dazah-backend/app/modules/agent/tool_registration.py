from importlib import import_module

from app.shared.module_registry import AGENT_TOOL_PROVIDER_MODULES

_registered = False


def ensure_agent_tools_registered() -> None:
    global _registered
    if _registered:
        return

    for provider_module in AGENT_TOOL_PROVIDER_MODULES:
        import_module(provider_module)

    _registered = True
