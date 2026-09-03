"""Append-only page/action identity ledger; business rewrites need new keys.

The ledger is deliberately separate from generated menus: deleting a menu must
not erase the evidence that its authorization identity has already been used.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.platform.identity.page_policy import PageDefinition

LEDGER_PATH = Path(__file__).with_name("page_permission_lifecycle.json")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("页面权限生命周期目录存在重复标识")
        result[key] = value
    return result


@lru_cache(maxsize=1)
def load_ledger() -> dict[str, Any]:
    value = json.loads(
        LEDGER_PATH.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
    )
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("页面权限生命周期目录格式无效")
    return value


def page_lifecycle_errors(
    page: PageDefinition, ledger: dict[str, Any] | None = None
) -> list[str]:
    entries = (ledger if ledger is not None else load_ledger()).get("pages", {})
    entry = entries.get(page.page_key)
    if not isinstance(entry, dict):
        return ["页面尚未登记授权生命周期"]
    if entry.get("status") != "active":
        return ["页面授权标识已退役，不得重新使用"]
    if (entry.get("module_code"), entry.get("route_path")) != (
        page.module_code,
        page.route_path,
    ):
        return ["页面归属或路由已改变，必须使用新的授权标识"]
    errors = []
    actions = entry.get("actions", {})
    active = {action.key: action for action in page.sensitive_actions}
    if len(active) != len(page.sensitive_actions):
        errors.append("高风险动作标识重复")
    for key, action in active.items():
        fact = actions.get(key, {})
        if fact.get("status") != "active" or fact.get("category") != action.category:
            errors.append("高风险动作未登记、已退役或安全类别已改变")
    if any(
        fact.get("status") == "active" and key not in active
        for key, fact in actions.items()
    ):
        errors.append("已移除的高风险动作必须显式登记退役")
    return errors


def lifecycle_catalog_errors(
    pages: Sequence[PageDefinition], ledger: dict[str, Any]
) -> list[str]:
    errors = [
        f"{page.page_key}: {error}"
        for page in pages
        for error in page_lifecycle_errors(page, ledger)
    ]
    keys = {page.page_key for page in pages}
    if len(keys) != len(pages):
        errors.append("页面授权标识重复")
    for key, entry in ledger.get("pages", {}).items():
        if entry.get("status") not in {"active", "retired"}:
            errors.append(f"{key}: 无效生命周期状态")
        if entry.get("status") == "active" and key not in keys:
            errors.append(f"{key}: 已移除页面必须显式登记退役")
        for action_key, action in entry.get("actions", {}).items():
            if action.get("status") not in {"active", "retired"}:
                errors.append(f"{key}/{action_key}: 无效动作生命周期状态")
    return errors


def ledger_history_errors(
    previous: dict[str, Any], current: dict[str, Any]
) -> list[str]:
    """Reject history deletion, retired-key resurrection and key repurposing."""
    errors = []
    for key, old in previous.get("pages", {}).items():
        new = current.get("pages", {}).get(key)
        if new is None:
            errors.append(f"{key}: 禁止删除历史页面标识")
            continue
        if old.get("status") == "retired" and new.get("status") != "retired":
            errors.append(f"{key}: 禁止恢复已退役页面标识")
        for field in ("module_code", "route_path"):
            if old.get(field) != new.get(field):
                errors.append(f"{key}: 禁止复用页面标识改变{field}")
        for action_key, old_action in old.get("actions", {}).items():
            new_action = new.get("actions", {}).get(action_key)
            if new_action is None:
                errors.append(f"{key}/{action_key}: 禁止删除历史动作标识")
            elif old_action.get("category") != new_action.get("category") or (
                old_action.get("status") == "retired"
                and new_action.get("status") != "retired"
            ):
                errors.append(f"{key}/{action_key}: 禁止复用或恢复退役动作标识")
    return errors
