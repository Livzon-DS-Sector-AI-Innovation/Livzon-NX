"""Decision selectors must remain part of the reviewed authorization contract."""

from dataclasses import replace

import pytest

from app.platform.identity import page_policy


def decision_binding():
    return next(
        binding
        for binding in page_policy.PAGE_API_BINDINGS
        if binding.route_path
        == "/api/v1/production/dr/schedule/tasks/{batch_no}/approve"
    )


def test_decision_contract_declares_both_actions():
    binding = decision_binding()
    assert page_policy._api_binding_errors(binding) == []
    assert binding.action_selector == page_policy.BooleanActionSelector(
        "approve", "approve", "reject"
    )
    assert binding.sensitive_action is None


@pytest.mark.parametrize(
    "change", ["missing_field", "unknown_action", "query_only", "static_conflict"]
)
def test_invalid_decision_contract_is_rejected(change):
    binding = decision_binding()
    selector = binding.action_selector
    assert selector is not None
    if change == "missing_field":
        binding = replace(binding, action_selector=replace(selector, field=""))
    elif change == "unknown_action":
        binding = replace(
            binding, action_selector=replace(selector, when_false="unreviewed_action")
        )
    elif change == "query_only":
        binding = replace(binding, permission="query")
    else:
        binding = replace(binding, sensitive_action="approve")
    assert page_policy._api_binding_errors(binding)


def test_contract_url_has_the_grantable_leaf_identity():
    assert (
        page_policy.page_key_for_route("/hr/contracts")
        == "hr:contracts:contracts-ledger"
    )
