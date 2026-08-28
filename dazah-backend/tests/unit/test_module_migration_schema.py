import re
from pathlib import Path

MIGRATION = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "4772bce4935d_migrate_quality_registration_hr_.py"
)


def test_migration_is_the_additive_migration_head() -> None:
    text = MIGRATION.read_text(encoding="utf-8")

    assert re.search(r"revision: str = ['\"]4772bce4935d['\"]", text)
    assert re.search(r"down_revision: str \| None = ['\"]a1b2c3d4e5f6['\"]", text)
    assert "op.drop_" not in text
    assert "op.alter_" not in text


def test_source_uploads_are_not_part_of_the_migration() -> None:
    migration_text = MIGRATION.read_text(encoding="utf-8")

    # Source attachments are intentionally excluded from the repository and
    # must not be required by a migration test running in CI.
    assert "dazah-Migration" not in migration_text
    assert "uploads" not in migration_text.lower()
