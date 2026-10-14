from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import patch

from app.platform.system.feedback_models import FeedbackScreenshot, UserFeedback


def test_feedback_migration_matches_model_columns_and_supports_downgrade() -> None:
    spec = spec_from_file_location(
        "feedback_migration",
        Path(__file__).parents[2] / "alembic/versions/b4e9f3d7a2c0_user_feedback.py",
    )
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    with patch.object(migration, "op") as operations:
        migration.upgrade()
        tables = {call.args[0]: call for call in operations.create_table.call_args_list}
        for model in (UserFeedback, FeedbackScreenshot):
            call = tables[model.__tablename__]
            assert call.kwargs["schema"] == "core"
            assert {column.name for column in model.__table__.columns} == {
                column.name for column in call.args[1:] if hasattr(column, "type")
            }
        migration.downgrade()
        assert [call.args[0] for call in operations.drop_table.call_args_list] == [
            "feedback_screenshots",
            "user_feedback",
        ]
