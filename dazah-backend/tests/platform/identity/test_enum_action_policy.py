"""Status decisions must expose separate, valid grantable page actions."""

from dataclasses import replace

import pytest

from app.platform.identity import page_policy
from app.platform.identity.page_lifecycle import page_lifecycle_errors


def pressure_binding():
    return page_policy.api_binding_for_route(
        "PATCH",
        "/api/v1/production/pressure/records/{record_id}/audit",
    )


def test_pressure_status_selector_and_lifecycle_declare_both_decisions():
    binding = pressure_binding()
    assert binding is not None
    assert binding.action_selector == page_policy.EnumActionSelector(
        "status",
        (("approved", "approve"), ("rejected", "reject")),
    )
    assert binding.sensitive_action is None
    page = page_policy.get_page_definition("production:pressure")
    assert page is not None
    assert page_lifecycle_errors(page) == []


@pytest.mark.parametrize(
    "selector",
    [
        page_policy.EnumActionSelector("", (("approved", "approve"),)),
        page_policy.EnumActionSelector("status", ()),
        page_policy.EnumActionSelector(
            "status", (("approved", "approve"), ("approved", "reject"))
        ),
        page_policy.EnumActionSelector("status", (("", "reject"),)),
        page_policy.EnumActionSelector(
            "status", (("approved", "unregistered_action"),)
        ),
    ],
)
def test_invalid_status_selectors_fail_closed(selector):
    binding = pressure_binding()
    assert binding is not None
    assert page_policy._api_binding_errors(replace(binding, action_selector=selector))


def test_status_decisions_cannot_be_query_only_or_use_a_static_action():
    binding = pressure_binding()
    assert binding is not None
    assert page_policy._api_binding_errors(replace(binding, permission="query"))
    assert page_policy._api_binding_errors(replace(binding, sensitive_action="approve"))
