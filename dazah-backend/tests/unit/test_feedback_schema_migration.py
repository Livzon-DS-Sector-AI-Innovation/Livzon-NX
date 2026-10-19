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


def test_feedback_merge_preserves_both_existing_revision_histories() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    # 单一 head 随链尾演进（不再硬编码链尾版本），反馈分支经
    # merge 版本 807ad84a1158 并入主链；本批在其上追加镜像迁移
    heads = scripts.get_heads()
    assert len(heads) == 1
    merge = scripts.get_revision("807ad84a1158")
    assert merge is not None
    assert set(merge.down_revision) == {"b4e9f3d7a2c0", "b8d4f2a6c9e1"}
    feedback = scripts.get_revision("b4e9f3d7a2c0")
    assert feedback is not None and feedback.down_revision == "a3d8f2c6e1b9"
    assert {item.revision for item in scripts.iterate_revisions("heads", "base")} >= {
        "b4e9f3d7a2c0",
        "b8d4f2a6c9e1",
        "b4e2f8a1c7d3",
    }
