"""成品异常报告菜单种子（identity 平台）覆盖测试。

menu_seed_data 由前端 menu-config.ts 静态转写、page_menu_catalog.json 覆盖同源
节点；本测试锁定 anomaly-report 目录节点与其台账子节点确实进入 SEED_MENUS，
防止菜单目录再生成或转写漂移时丢失入口。
"""

from __future__ import annotations

from typing import Any

from app.platform.identity.menu_seed_data import SEED_MENUS


def _quality_children() -> list[dict[str, Any]]:
    module = next(m for m in SEED_MENUS if m["key"] == "quality")
    return module["children"] or []


def test_anomaly_report_menu_seeded() -> None:
    node = next(c for c in _quality_children() if c["key"] == "anomaly-report")
    assert node["name"] == "成品异常报告"
    assert node["path"] == "/quality/anomaly-report"
    assert node["disabled"] is False

    children = node["children"] or []
    ledger = next(c for c in children if c["key"] == "anomaly-report-ledger")
    assert ledger["name"] == "异常台账"
    assert ledger["path"] == "/quality/anomaly-report/ledger"
    assert ledger["disabled"] is False


def test_anomaly_report_keys_do_not_collide() -> None:
    # 既有种子允许不同模块复用短 key（seed 时拼 {parent}:{key} 前缀），
    # 新增 key 必须全树唯一，不得与任何既有节点冲突。
    keys: list[str] = []

    def walk(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            keys.append(node["key"])
            if node.get("children"):
                walk(node["children"])

    walk(SEED_MENUS)
    assert keys.count("anomaly-report") == 1
    assert keys.count("anomaly-report-ledger") == 1


def test_department_contacts_menu_removed() -> None:
    """部门联系人功能整体下线：种子树与页面目录都不得再出现该入口。"""
    keys: list[str] = []
    paths: list[str] = []

    def walk(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            keys.append(node["key"])
            paths.append(node.get("path") or "")
            if node.get("children"):
                walk(node["children"])

    walk(SEED_MENUS)
    assert "department-contacts" not in keys
    assert "/quality/department-contacts" not in paths
