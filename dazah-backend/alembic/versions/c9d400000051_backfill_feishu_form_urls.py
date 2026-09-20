"""Backfill warehouse page form URLs and HR onboarding form URL.

收口改造把写死在前端的表单链接改为 DB 配置（为空隐藏入口）。本迁移把
改造前实际在用的链接回填进库，保证存量环境行为不变；只 UPDATE 已存在
的配置行——全新空库尚无这些行（由运行期 ensure 创建），因此全新部署
仍是零绑定零配置，符合收口原则。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d400000051"
down_revision: str | None = "c9d400000050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BASE = "https://j0eukrlohu.feishu.cn/share/base/form/"

# page_key → (入库表单, 出库表单)：与收口前前端写死值一一对应
_WAREHOUSE_FORM_URLS: dict[str, tuple[str | None, str | None]] = {
    "inbound-ledger": (_BASE + "shrcnLl9xrz5e60vRG4P8Cy85FC", None),
    "raw-ledger": (
        _BASE + "shrcnLl9xrz5e60vRG4P8Cy85FC",
        _BASE + "shrcnsJ8U9aoOqqEBS5b1mpG2Zd",
    ),
    "packaging-ledger": (None, _BASE + "shrcnOZBGw46qWth2auB1F09kNd"),
    "liquid-raw-inbound": (_BASE + "shrcnfWaTJinJrjFh0hcqvYG0De", None),
    "liquid-sugar-inbound": (_BASE + "shrcnPdocHXYzag4Uyj0biU9bYc", None),
    "product-inbound-detail": (_BASE + "shrcnDSOkJ2pyfcd3azP25WHJ9f", None),
    "product-inbound-ledger": (_BASE + "shrcnDSOkJ2pyfcd3azP25WHJ9f", None),
    "product-shipping": (None, _BASE + "shrcnUrGx4FJwY9zEDAR8NLkWDL"),
    "product-outbound-ledger": (None, _BASE + "shrcnnZl0PPBDqISGj02c9h2JBh"),
}

_HR_ONBOARDING_FORM_URL = _BASE + "shrcnds8SEIlMXMdB3qS9QzWlth"


def upgrade() -> None:
    bind = op.get_bind()

    for page_key, (inbound, outbound) in _WAREHOUSE_FORM_URLS.items():
        bind.execute(
            sa.text(
                "UPDATE warehouse.warehouse_page_feishu_configs "
                "SET feishu_inbound_form_url = coalesce("
                "  feishu_inbound_form_url, :inbound), "
                "feishu_outbound_form_url = coalesce("
                "  feishu_outbound_form_url, :outbound), "
                "updated_at = now() "
                "WHERE page_key = :page_key AND is_deleted = false"
            ).bindparams(page_key=page_key, inbound=inbound, outbound=outbound)
        )

    bind.execute(
        sa.text(
            "UPDATE hr.hr_feishu_entity_settings "
            "SET feishu_form_url = :form_url, updated_at = now() "
            "WHERE entity_code = 'onboarding' AND is_deleted = false "
            "AND (feishu_form_url IS NULL OR feishu_form_url = '')"
        ).bindparams(form_url=_HR_ONBOARDING_FORM_URL)
    )


def downgrade() -> None:
    """回滚清空本迁移回填的表单链接（不区分是否用户后续改过，统一置空）。"""
    bind = op.get_bind()
    for page_key, (inbound, outbound) in _WAREHOUSE_FORM_URLS.items():
        bind.execute(
            sa.text(
                "UPDATE warehouse.warehouse_page_feishu_configs "
                "SET feishu_inbound_form_url = NULL, feishu_outbound_form_url = NULL, "
                "updated_at = now() "
                "WHERE page_key = :page_key AND is_deleted = false "
                "AND feishu_inbound_form_url = :inbound "
                "AND feishu_outbound_form_url = :outbound"
            ).bindparams(page_key=page_key, inbound=inbound, outbound=outbound)
        )
    bind.execute(
        sa.text(
            "UPDATE hr.hr_feishu_entity_settings "
            "SET feishu_form_url = NULL, updated_at = now() "
            "WHERE entity_code = 'onboarding' AND is_deleted = false "
            "AND feishu_form_url = :form_url"
        ).bindparams(form_url=_HR_ONBOARDING_FORM_URL)
    )
