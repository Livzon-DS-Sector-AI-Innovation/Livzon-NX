"""Join the safety page table mirror with board preferences migrations.

上游 #155 的 a3c8e5f7b9d1 与本分支的 c9d400000059 同以 c4e6f8a0b2d1 为
父节点形成分叉，此合并节点将两支汇合为单一 head。

Revision ID: c9d400000060
Revises: a3c8e5f7b9d1, c9d400000059
"""

revision: str = "c9d400000060"
down_revision: tuple[str, str] = ("a3c8e5f7b9d1", "c9d400000059")
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
