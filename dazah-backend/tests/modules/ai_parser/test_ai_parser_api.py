import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from app.core.llm import LLMConfigError
from app.modules.ai_parser import api


def test_ai_parser_router_exposes_both_parser_operations() -> None:
    paths = {
        route.path for route in api.router.routes if isinstance(route, APIRoute)
    }

    assert "/parse-experiment" in paths
    assert "/parse-parameters" in paths


@pytest.mark.asyncio
async def test_ai_parser_maps_missing_configuration_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_with_configuration_error(
        *args: object, **kwargs: object
    ) -> dict[str, object]:
        raise LLMConfigError("provider-secret-must-not-leak")

    # Patch the class method so monkeypatch teardown does not leave a bound
    # method on the shared singleton and shadow later module-level patches.
    monkeypatch.setattr(
        type(api.llm_client),
        "chat_json",
        fail_with_configuration_error,
    )

    with pytest.raises(HTTPException) as exc_info:
        await api._call_parser_llm("parse this")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "AI解析服务未配置"
    assert "provider-secret" not in str(exc_info.value.detail)
