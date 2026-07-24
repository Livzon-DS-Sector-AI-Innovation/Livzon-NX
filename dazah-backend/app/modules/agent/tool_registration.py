_registered = False


def ensure_agent_tools_registered() -> None:
    global _registered
    if _registered:
        return

    import app.modules.agent.agent_tools  # noqa: F401
    import app.modules.agent.analytics  # noqa: F401
    import app.modules.energy.agent_tools  # noqa: F401
    import app.modules.procurement.agent_tools  # noqa: F401
    import app.modules.quality.agent_tools  # noqa: F401
    import app.modules.warehouse.agent_tools  # noqa: F401
    import app.platform.identity.agent_tools  # noqa: F401

    _registered = True
