"""投诉台账拉取方向的回归测试。

投诉台账页面（list_complaint_ledger_records）直连飞书实时读取，依赖
direction="pull" 的实体解析。历史上 complaint_ledger 被误归入
PUSH_ONLY 集合后，ensure_quality_feishu_entity_settings 会把手动开启的
拉取开关钉死为 false，导致页面在所有环境必报 400「飞书 Base 未启用」。
"""

from app.modules.quality.service.quality_feishu_settings import (
    PUSH_ONLY_QUALITY_FEISHU_ENTITIES,
    _get_default_sync_directions,
)


def test_complaint_ledger_not_push_only():
    assert "complaint_ledger" not in PUSH_ONLY_QUALITY_FEISHU_ENTITIES


def test_complaint_ledger_default_directions_allow_pull():
    push, pull = _get_default_sync_directions("complaint_ledger")
    assert pull is True
    assert push is True


def test_push_only_members_still_default_pull_off():
    # 其余 push-only 成员保持原默认（本地为主，仅推送）。
    for code in ("oos_ledger", "oot_ledger", "return_recall_ledger"):
        push, pull = _get_default_sync_directions(code)
        assert push is True
        assert pull is False
