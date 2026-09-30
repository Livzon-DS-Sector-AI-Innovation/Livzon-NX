"""hr qualification_type 放宽迁移（VARCHAR(32)→64）必须精确覆盖两张表且可回退。"""

import importlib.util
from pathlib import Path
from unittest.mock import Mock


def _load_module():
    path = (
        Path(__file__).resolve().parents[3]
        / "alembic/versions/a3f8c2d91e47_widen_hr_qualification_type.py"
    )
    spec = importlib.util.spec_from_file_location("hr_qualification_widen", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_widen_migration_alters_both_hr_tables_and_reverts(monkeypatch):
    module = _load_module()
    execute = Mock()
    monkeypatch.setattr(module.op, "execute", execute)

    module.upgrade()
    upgrade_sql = [call.args[0] for call in execute.call_args_list]
    assert upgrade_sql == [
        "ALTER TABLE hr.employees "
        "ALTER COLUMN qualification_type TYPE VARCHAR(64)",
        "ALTER TABLE hr.offboarding_records "
        "ALTER COLUMN qualification_type TYPE VARCHAR(64)",
    ]

    execute.reset_mock()
    module.downgrade()
    downgrade_sql = [call.args[0] for call in execute.call_args_list]
    assert downgrade_sql == [
        "ALTER TABLE hr.employees "
        "ALTER COLUMN qualification_type TYPE VARCHAR(32)",
        "ALTER TABLE hr.offboarding_records "
        "ALTER COLUMN qualification_type TYPE VARCHAR(32)",
    ]
