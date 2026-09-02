from copy import deepcopy
from dataclasses import replace

import pytest

from app.platform.identity import page_lifecycle, page_policy
from app.platform.identity.page_lifecycle import (
    ledger_history_errors,
    lifecycle_catalog_errors,
    load_ledger,
    page_lifecycle_errors,
)

PAGE = "quality:deviations:deviation-ledger"


def test_current_catalog_has_complete_lifecycle_registration():
    assert lifecycle_catalog_errors(page_policy.PAGE_DEFINITIONS, load_ledger()) == []


def test_duplicate_page_action_and_ledger_keys_are_rejected():
    page = page_policy.PAGES_BY_KEY[PAGE]
    assert lifecycle_catalog_errors([page, page], load_ledger())
    assert page_lifecycle_errors(
        replace(
            page, sensitive_actions=(*page.sensitive_actions, page.sensitive_actions[0])
        )
    )
    with pytest.raises(ValueError, match="重复标识"):
        page_lifecycle._unique_object([("page", {}), ("page", {})])


@pytest.mark.parametrize(
    "change",
    [
        "delete_page",
        "reuse_page",
        "move_page",
        "delete_action",
        "reuse_action",
        "change_category",
    ],
)
def test_history_cannot_be_erased_or_reused(change):
    before = deepcopy(load_ledger())
    after = deepcopy(before)
    entry = after["pages"][PAGE]
    if change == "delete_page":
        del after["pages"][PAGE]
    elif change == "reuse_page":
        before["pages"][PAGE]["status"] = "retired"
    elif change == "move_page":
        entry["route_path"] += "-rewritten"
    elif change == "delete_action":
        del entry["actions"]["delete"]
    elif change == "reuse_action":
        before["pages"][PAGE]["actions"]["delete"]["status"] = "retired"
    else:
        entry["actions"]["delete"]["category"] = "approval"
    assert ledger_history_errors(before, after)


def test_removal_requires_tombstone_but_cosmetic_labels_do_not_change_identity():
    page = page_policy.PAGES_BY_KEY[PAGE]
    ledger = deepcopy(load_ledger())
    assert not page_lifecycle_errors(
        replace(page, page_name="新的中文显示名称"), ledger
    )
    actions = tuple(
        action for action in page.sensitive_actions if action.key != "delete"
    )
    removed = replace(page, sensitive_actions=actions)
    assert page_lifecycle_errors(removed, ledger)
    ledger["pages"][PAGE]["actions"]["delete"]["status"] = "retired"
    assert not page_lifecycle_errors(removed, ledger)
    assert not ledger_history_errors(load_ledger(), ledger)
    assert page_lifecycle_errors(page, ledger)


def test_new_pages_and_actions_are_not_silently_registered():
    page = page_policy.PAGES_BY_KEY[PAGE]
    assert page_lifecycle_errors(replace(page, page_key=PAGE + ":v2"))
    action = replace(page.sensitive_actions[0], key="new_action")
    assert page_lifecycle_errors(
        replace(page, sensitive_actions=(*page.sensitive_actions, action))
    )


def test_retired_page_is_unavailable_at_runtime_and_blocks_publish(monkeypatch):
    ledger = deepcopy(load_ledger())
    ledger["pages"][PAGE]["status"] = "retired"
    monkeypatch.setattr(page_lifecycle, "load_ledger", lambda: ledger)
    assert page_policy.get_page_definition(PAGE) is None
    assert any("已退役" in gap for gap in page_policy.page_api_catalog_gaps("quality"))
