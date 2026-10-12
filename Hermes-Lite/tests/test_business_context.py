import pytest
from pydantic import ValidationError

from services.business_context import AgentPageContext, business_context_instruction
from services.dazah_agent_service import AgentBackendV2Request


def test_generic_knowledge_discovery_is_not_bound_to_a_business_module():
    instruction = business_context_instruction(None)
    assert "不得把知识来源固定为某个模块" in instruction
    assert "knowledge_index" in instruction and "本轮执行" in instruction
    assert "分页或截断内容不能当作全量统计" in instruction


def test_page_context_is_separate_from_identity_and_rejects_authority_fields():
    page = AgentPageContext(
        page_key="production:batches",
        page_name="批次",
        module_code="production",
        route_path="/production/batches",
        filters={"status": "open"},
    )
    payload = AgentBackendV2Request(
        protocol_version="2.0",
        run_id="00000000-0000-0000-0000-000000000001",
        trace_id="00000000-0000-0000-0000-000000000002",
        session_id="test",
        subject={"user_id": "real-user", "tenant_id": "tenant", "source": "web"},
        source={"platform": "web"},
        message="查看这里",
        page_context=page,
    )
    assert payload.context["user_id"] == "real-user"
    assert payload.context["page_context"]["page_key"] == page.page_key
    assert "用户明确指定对象或日期时以用户要求为准" in business_context_instruction(page)
    with pytest.raises(ValidationError):
        AgentPageContext.model_validate({**page.model_dump(), "user_id": "spoof"})
