"""报修台账配置：默认停用，配置齐全后才启用镜像同步。"""

import pytest

from app.core.config import Settings
from app.modules.equipment.feishu import repair_ledger


def test_repair_ledger_settings_default_to_disabled() -> None:
    fields = Settings.model_fields

    assert fields["REPAIR_LEDGER_APP_TOKEN"].default == ""
    assert fields["REPAIR_LEDGER_TABLE_ID"].default == ""
    assert fields["REPAIR_LEDGER_SUMMARY_TABLE_ID"].default == ""


def test_ledger_enabled_requires_app_token_and_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        repair_ledger.settings, "REPAIR_LEDGER_APP_TOKEN", "", raising=False
    )
    monkeypatch.setattr(
        repair_ledger.settings, "REPAIR_LEDGER_TABLE_ID", "", raising=False
    )
    assert repair_ledger.ledger_enabled() is False

    monkeypatch.setattr(
        repair_ledger.settings, "REPAIR_LEDGER_APP_TOKEN", "bapp", raising=False
    )
    assert repair_ledger.ledger_enabled() is False

    monkeypatch.setattr(
        repair_ledger.settings, "REPAIR_LEDGER_TABLE_ID", "tbl1", raising=False
    )
    assert repair_ledger.ledger_enabled() is True
