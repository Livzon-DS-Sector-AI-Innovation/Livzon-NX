from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import tool_registry
from app.platform.identity.page_policy import PAGES_BY_KEY


def test_system_admin_approval_uses_authenticated_identity():
    from app.modules.procurement.page_access import assert_approval_responsibility
    from app.platform.identity.data_scope import current_page_actor, current_page_key
    from app.platform.identity.models import User

    actor_token = current_page_actor.set(User(name="系统管理员", role="admin"))
    page_token = current_page_key.set(None)
    try:
        assert (
            assert_approval_responsibility("department", "伪造审批人") == "系统管理员"
        )
    finally:
        current_page_actor.reset(actor_token)
        current_page_key.reset(page_token)


def test_procurement_tool_page_bindings_are_valid_and_decisions_stay_human():
    ensure_agent_tools_registered()
    tools = [spec for spec in tool_registry.list() if spec.module == "procurement"]
    assert tools
    for spec in tools:
        assert spec.page_keys, spec.name
        for key in spec.page_keys:
            assert PAGES_BY_KEY[key].module_code == "procurement"
            if spec.sensitive_action:
                assert spec.sensitive_action in {
                    action.key for action in PAGES_BY_KEY[key].sensitive_actions
                }
        if spec.sensitive_action in {"approve", "reject"}:
            assert spec.human_decision_required
            assert not spec.workflow_allowed
