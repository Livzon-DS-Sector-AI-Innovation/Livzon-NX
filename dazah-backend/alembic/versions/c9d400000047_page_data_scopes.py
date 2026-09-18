"""Replace legacy inapplicable scopes with each page's actual full range."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d400000047"
down_revision: str | None = "c9d400000046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tables() -> list[sa.Table]:
    return [
        sa.table(
            table_name,
            sa.column("page_key", sa.String),
            sa.column("scope_type", sa.String),
            schema="identity",
        )
        for table_name in ("role_page_grants", "user_page_grants")
    ]


def _legacy_global_page(page_key: sa.Column) -> sa.ColumnElement[bool]:
    prefixes = (
        "production:", "registration:", "quality:product-quality:",
        "warehouse:materials:", "warehouse:product-inventory:",
        "purchasing:contract-generation:",
    )
    exact = (
        "quality:suppliers:supplier-qualification",
        "quality:quality-settings",
        "warehouse:hardware:hardware-hardware-summary",
        "warehouse:hardware:hardware-hardware-electrical",
        "warehouse:hardware:hardware-hardware-inbound-ledger",
        "warehouse:hardware:hardware-hardware-outbound-ledger",
        "purchasing:material-library", "purchasing:supplier",
        "purchasing:invoice-recognition", "purchasing:contract-summary",
        "purchasing:settings",
    )
    return sa.or_(
        page_key.in_(exact),
        *(page_key.like(f"{prefix}%") for prefix in prefixes),
    )


def _global_resource_page(page_key: sa.Column) -> sa.ColumnElement[bool]:
    # These pages have no consistent department owner across their bound APIs;
    # old department grants could not represent all returned data.
    return sa.or_(
        page_key.like("quality:inspection:%"),
        page_key.like("quality:validation:%"),
        page_key.in_((
        "warehouse:ai-analysis",
        "warehouse:warehouse-settings",
        "hr:employee-management:feishu-contacts",
        "hr:hr-settings:hr-settings-feishu",
        "hr:hr-settings:hr-settings-reminder",
        "hr:hr-settings:hr-settings-approval",
        "hr:hr-settings:hr-settings-dept-mapping",
        "hr:hr-settings:hr-settings-dept-scopes",
        "quality:complaints:complaint-ledger",
        "quality:deviations:deviation-records",
        "quality:deviations:deviation-investigations",
        "quality:deviations:deviation-history",
        "quality:deviations:deviation-workbench",
        "quality:oos-oot:oot-limits",
        "quality:oos-oot:product-departments",
        "quality:oos-oot:oos-ledger",
        "quality:oos-oot:oot-ledger",
        "quality:oos-oot:oos-oot-report-records",
        "quality:oos-oot:oos-oot-investigation-push",
        "quality:anomaly-report:anomaly-report-ledger",
        "quality:return-recalls:return-application",
        "quality:return-recalls:return-ledger",
        "quality:inspection:inspection-solid",
        "quality:inspection:inspection-liquid",
        )),
    )


def _convert(old: str, new: str, *, legacy_global_only: bool = False) -> None:
    for table in _tables():
        criterion = (
            _legacy_global_page(table.c.page_key)
            if legacy_global_only else sa.true()
        )
        op.execute(
            table.update()
            .where(table.c.scope_type == old, criterion)
            .values(scope_type=new)
        )


def upgrade() -> None:
    _convert("not_applicable", "all", legacy_global_only=True)
    for table in _tables():
        op.execute(
            table.update()
            .where(
                _global_resource_page(table.c.page_key),
                table.c.scope_type.in_((
                    "not_applicable", "department_tree", "departments"
                )),
            )
            .values(scope_type="all")
        )


def downgrade() -> None:
    _convert("all", "not_applicable", legacy_global_only=True)
    _convert("production_fermentation", "not_applicable", legacy_global_only=True)
    _convert("production_extraction", "not_applicable", legacy_global_only=True)
    # Keep normalized global-resource grants: their former department choice
    # cannot be recovered, and "all" remains valid in the previous catalog.
