import pytest
from fastapi import HTTPException

from app.platform.identity.page_lifecycle import page_lifecycle_errors
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.page_policy import get_page_definition
from app.platform.identity.schemas import PageDataScopeInput, PageGrantInput


def test_schedule_history_fix_is_an_independent_registered_action() -> None:
    page = get_page_definition("production:plan:scheduling")
    assert page is not None
    action = next(a for a in page.sensitive_actions if a.key == "schedule-archive")
    assert action.name == "排产历史修正"
    assert action.category == "bulk_change"
    assert page_lifecycle_errors(page) == []


@pytest.mark.parametrize("actions", [[], ["bulk_import"], ["schedule-archive"]])
def test_schedule_history_fix_can_be_granted_and_revoked_independently(
    actions: list[str],
) -> None:
    grant = PageGrantInput(
        page_key="production:plan:scheduling",
        permissions=["operate"],
        sensitive_actions=actions,
        data_scope=PageDataScopeInput(scope_type="all"),
    )
    normalized = PagePermissionService().normalize_inputs([grant], allow_inherit=True)
    assert normalized[0]["sensitive_actions"] == actions
    assert normalized[0]["permissions"] == ["access", "query", "operate"]
    with pytest.raises(HTTPException):
        PagePermissionService().normalize_inputs(
            [grant.model_copy(update={
                "page_key": "production:plan:sales-plan",
                "sensitive_actions": ["schedule-archive"],
            })],
            allow_inherit=True,
        )
