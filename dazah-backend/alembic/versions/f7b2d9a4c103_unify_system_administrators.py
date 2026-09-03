"""Unify administrator identities without migrating ordinary page grants.

The historical role code is retained for compatibility. Downgrade deliberately
does not demote accounts: their authority may have been explicitly changed after
upgrade, and an automatic reversal could lock out the last administrator.
"""

import sqlalchemy as sa

from alembic import op

revision: str = "f7b2d9a4c103"
down_revision: str | None = "d2f8a4c6e1b3"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        sa.text("""
        UPDATE identity.users AS u
        SET role = 'admin', grant_version = grant_version + 1, updated_at = now()
        WHERE NOT u.is_deleted AND (
            u.role = 'admin' OR EXISTS (
                SELECT 1 FROM identity.user_roles ur
                JOIN identity.roles r ON r.id = ur.role_id
                WHERE ur.user_id = u.id AND ur.source = 'manual'
                    AND NOT ur.is_deleted AND NOT r.is_deleted
                    AND r.code = 'super_admin'
            )
        )
    """)
    )
    op.execute(
        sa.text("""
        UPDATE identity.roles SET name = '系统管理员',
            description = '拥有全部系统及业务权限', updated_at = now()
        WHERE code = 'super_admin'
    """)
    )


def downgrade() -> None:
    # Preserve identities, grant versions and administrator decisions on rollback.
    pass
