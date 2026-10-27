"""emergency cards table and seed data

应急处置卡：
- 新表 ``safety.emergency_cards``：车间/岗位级事故现场处置卡
  （步骤、应急电话、风险后果、注意事项等结构化字段）；
- 种子数据：从 ``app/modules/safety/seeds/emergency_cards.json`` 导入
  各车间应急资料整理出的 98 张卡（101-102、103、201 一车间、203 车间、
  动力部及公司级），可重复执行判断（仅空表时导入）。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b5d8f2a6c1e9"
down_revision: str | None = "c797740130e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "modules"
    / "safety"
    / "seeds"
    / "emergency_cards.json"
)


def _build_search_text(card: dict) -> str:
    parts = [
        card.get("title") or "",
        card.get("subject") or "",
        card.get("accident_type") or "",
        card.get("workshop") or "",
        card.get("position") or "",
        card.get("phones") or "",
    ]
    for step in card.get("steps") or []:
        parts.extend(
            str(step.get(key) or "") for key in ("step", "action", "person")
        )
    return " ".join(part for part in parts if part)


def _seed_rows() -> list[dict]:
    cards: list[dict] = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    counters: dict[str, int] = {}
    rows: list[dict] = []
    for card in cards:
        workshop = card["workshop"]
        counters[workshop] = counters.get(workshop, 0)
        rows.append(
            {
                "id": uuid4(),
                "workshop": workshop,
                "position": card.get("position") or "",
                "title": card["title"],
                "subject": card.get("subject") or card["title"],
                "accident_type": card.get("accident_type") or "综合",
                "steps": card.get("steps") or [],
                "extras": card.get("extras") or [],
                "phones": card.get("phones") or "",
                "risks": card.get("risks") or "",
                "precautions": card.get("precautions") or "",
                "source_file": card.get("source_file") or "",
                "search_text": _build_search_text(card),
                "sort_order": counters[workshop],
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        )
        counters[workshop] += 1
    return rows


def upgrade() -> None:
    op.create_table(
        "emergency_cards",
        sa.Column(
            "workshop",
            sa.String(60),
            nullable=False,
            comment="车间/部门（如 103车间、公司级、动力部）",
        ),
        sa.Column(
            "position",
            sa.String(60),
            nullable=False,
            server_default="",
            comment="岗位（如 配料、化测；车间级/公司级卡为空）",
        ),
        sa.Column(
            "title",
            sa.String(200),
            nullable=False,
            comment="卡片标题（如 103车间液氨泄漏应急处置卡）",
        ),
        sa.Column(
            "subject",
            sa.String(120),
            nullable=False,
            server_default="",
            comment="处置主题（标题去除车间/岗位前缀与「应急处置卡」后缀）",
        ),
        sa.Column(
            "accident_type",
            sa.String(40),
            nullable=False,
            server_default="综合",
            comment="事故类型（泄漏/火灾/中毒/触电等）",
        ),
        sa.Column(
            "steps",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="处置步骤 [{order, step, action, person}]",
        ),
        sa.Column(
            "extras",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="其他段落 [{label, content}]（如 次生、衍生事故）",
        ),
        sa.Column(
            "phones",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="应急电话",
        ),
        sa.Column(
            "risks",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="主要导致风险及导致的后果",
        ),
        sa.Column(
            "precautions",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="应急注意事项",
        ),
        sa.Column(
            "source_file",
            sa.String(255),
            nullable=False,
            server_default="",
            comment="来源文件名（种子导入溯源）",
        ),
        sa.Column(
            "search_text",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="关键字搜索文本（标题/主题/类型/步骤/电话拼接）",
        ),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="展示排序（同车间内升序）",
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.Index(
            "uq_safety_emergency_cards_title",
            "workshop",
            "position",
            "title",
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        ),
        sa.Index(
            "ix_safety_emergency_cards_workshop",
            "workshop",
            "is_deleted",
        ),
        schema="safety",
    )

    bind = op.get_bind()
    existing = bind.execute(
        sa.text("SELECT count(*) FROM safety.emergency_cards")
    ).scalar_one()
    if existing == 0:
        target = sa.Table(
            "emergency_cards",
            sa.MetaData(),
            sa.Column("id", postgresql.UUID(as_uuid=True)),
            sa.Column("workshop", sa.String(60)),
            sa.Column("position", sa.String(60)),
            sa.Column("title", sa.String(200)),
            sa.Column("subject", sa.String(120)),
            sa.Column("accident_type", sa.String(40)),
            sa.Column("steps", postgresql.JSONB(astext_type=sa.Text())),
            sa.Column("extras", postgresql.JSONB(astext_type=sa.Text())),
            sa.Column("phones", sa.Text()),
            sa.Column("risks", sa.Text()),
            sa.Column("precautions", sa.Text()),
            sa.Column("source_file", sa.String(255)),
            sa.Column("search_text", sa.Text()),
            sa.Column("sort_order", sa.Integer()),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
            schema="safety",
        )
        op.bulk_insert(target, _seed_rows())


def downgrade() -> None:
    op.drop_table("emergency_cards", schema="safety")
