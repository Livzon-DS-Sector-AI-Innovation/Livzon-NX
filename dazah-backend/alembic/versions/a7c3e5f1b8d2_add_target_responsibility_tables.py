"""target responsibility agreements & duty assessments

目标责任与绩效扩展（依据 2026 安全目标责任书 / 2026 责任制考核表文档）：
- ``safety.safety_target_agreements``：安全目标责任书签订台账
  （年度×部门×岗位，含签订状态与目标条款），种子数据来自
  ``app/modules/safety/seeds/target_responsibility_2026.json``
  （按文件夹 50 份责任书文档结构化，全部初始化为未签订）；
- ``safety.safety_duty_assessments`` /
  ``safety.safety_duty_assessment_items``：安全生产责任制季度考核
  记录与评分明细（百分制，>=95 优秀 / >=90 良好 / >=80 合格）。
考核模板不入库，由同一 JSON 的 ``assessment_templates`` 供匹配预填。
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

revision: str = "a7c3e5f1b8d2"
down_revision: str | None = "c5d7e9f1a3b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "modules"
    / "safety"
    / "seeds"
    / "target_responsibility_2026.json"
)

_BASE_COLUMNS = (
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
    ),
    sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column(
        "is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")
    ),
)
_BASE_CONSTRAINTS = (
    sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
    sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
    sa.PrimaryKeyConstraint("id"),
)


def _seed_agreement_rows() -> list[dict]:
    payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    year = int(payload.get("year") or 2026)
    now = datetime.now(UTC)
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in payload.get("agreements", []):
        key = (item["department"], item["position"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "id": uuid4(),
                "year": year,
                "department": item["department"],
                "position": item["position"],
                "category": item.get("category") or "岗位员工",
                "party_a": "",
                "party_b": "",
                "status": "unsigned",
                "signed_date": None,
                "expires_date": None,
                "goals_text": "\n".join(item.get("goals") or []),
                "remark": "",
                "search_text": " ".join(
                    part
                    for part in (
                        item["department"],
                        item["position"],
                        item.get("category") or "",
                    )
                    if part
                ),
                "created_at": now,
                "updated_at": now,
            }
        )
    return rows


def upgrade() -> None:
    # ---------- 安全目标责任书签订台账 ----------
    op.create_table(
        "safety_target_agreements",
        sa.Column("year", sa.Integer(), nullable=False, comment="签订年度"),
        sa.Column(
            "department",
            sa.String(100),
            nullable=False,
            comment="责任部门/单位（公司领导层用 公司领导）",
        ),
        sa.Column(
            "position",
            sa.String(100),
            nullable=False,
            comment="岗位/角色（如 负责人、安全管理科人员）",
        ),
        sa.Column(
            "category",
            sa.String(30),
            nullable=False,
            server_default="岗位员工",
            comment="分类: 公司领导 / 部门/车间负责人 / 岗位员工",
        ),
        sa.Column(
            "party_a",
            sa.String(60),
            nullable=False,
            server_default="",
            comment="甲方（公司/考核方代表）",
        ),
        sa.Column(
            "party_b",
            sa.String(60),
            nullable=False,
            server_default="",
            comment="乙方（责任方签订人）",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="unsigned",
            comment="状态: unsigned=未签订 / signed=已签订",
        ),
        sa.Column("signed_date", sa.Date(), nullable=True, comment="签订日期"),
        sa.Column(
            "expires_date",
            sa.Date(),
            nullable=True,
            comment="有效期至（责任书一年一签）",
        ),
        sa.Column(
            "goals_text",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="安全生产目标条款（每行一条）",
        ),
        sa.Column(
            "remark", sa.Text(), nullable=False, server_default="", comment="备注"
        ),
        sa.Column(
            "search_text",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="关键字搜索文本",
        ),
        *_BASE_COLUMNS,
        *_BASE_CONSTRAINTS,
        sa.Index(
            "uq_safety_target_agreements_key",
            "year",
            "department",
            "position",
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        ),
        sa.Index("ix_safety_target_agreements_year", "year", "is_deleted"),
        sa.Index("ix_safety_target_agreements_status", "status", "is_deleted"),
        schema="safety",
    )

    agreements_table = sa.table(
        "safety_target_agreements",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("year", sa.Integer),
        sa.column("department", sa.String),
        sa.column("position", sa.String),
        sa.column("category", sa.String),
        sa.column("party_a", sa.String),
        sa.column("party_b", sa.String),
        sa.column("status", sa.String),
        sa.column("goals_text", sa.Text),
        sa.column("remark", sa.Text),
        sa.column("search_text", sa.Text),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
        schema="safety",
    )
    op.bulk_insert(agreements_table, _seed_agreement_rows())

    # ---------- 安全生产责任制季度考核 ----------
    op.create_table(
        "safety_duty_assessments",
        sa.Column("year", sa.Integer(), nullable=False, comment="考核年度"),
        sa.Column("quarter", sa.Integer(), nullable=False, comment="考核季度 1-4"),
        sa.Column(
            "department",
            sa.String(100),
            nullable=False,
            comment="被考核部门/单位",
        ),
        sa.Column(
            "person_name",
            sa.String(100),
            nullable=False,
            server_default="",
            comment="被考核人（可空=部门整体）",
        ),
        sa.Column(
            "assessor",
            sa.String(100),
            nullable=False,
            server_default="",
            comment="考核单位（如 安全部）",
        ),
        sa.Column("assessment_date", sa.Date(), nullable=True, comment="考核日期"),
        sa.Column(
            "total_score",
            sa.Float(),
            nullable=False,
            server_default="0",
            comment="考核总得分（百分制）",
        ),
        sa.Column(
            "grade",
            sa.String(10),
            nullable=False,
            server_default="不合格",
            comment="等级: >=95优秀 / >=90良好 / >=80合格 / <80不合格",
        ),
        sa.Column(
            "remark", sa.Text(), nullable=False, server_default="", comment="备注"
        ),
        sa.Column(
            "search_text",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="关键字搜索文本",
        ),
        *_BASE_COLUMNS,
        *_BASE_CONSTRAINTS,
        sa.Index(
            "uq_safety_duty_assessments_key",
            "year",
            "quarter",
            "department",
            "person_name",
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        ),
        sa.Index(
            "ix_safety_duty_assessments_year_quarter",
            "year",
            "quarter",
            "is_deleted",
        ),
        schema="safety",
    )
    op.create_table(
        "safety_duty_assessment_items",
        sa.Column(
            "assessment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("safety.safety_duty_assessments.id"),
            nullable=False,
            comment="所属考核记录",
        ),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="排列序号",
        ),
        sa.Column("content", sa.Text(), nullable=False, comment="考核内容"),
        sa.Column(
            "rule",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="考核标准/扣分规则",
        ),
        sa.Column(
            "standard_score",
            sa.Float(),
            nullable=False,
            server_default="0",
            comment="标准分",
        ),
        sa.Column(
            "deduction_score",
            sa.Float(),
            nullable=False,
            server_default="0",
            comment="扣减分",
        ),
        sa.Column(
            "score", sa.Float(), nullable=False, server_default="0", comment="考核得分"
        ),
        sa.Column(
            "remark",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="考核明细说明",
        ),
        *_BASE_COLUMNS,
        *_BASE_CONSTRAINTS,
        sa.Index(
            "ix_safety_duty_assessment_items_assessment",
            "assessment_id",
            "is_deleted",
        ),
        schema="safety",
    )


def downgrade() -> None:
    op.drop_table("safety_duty_assessment_items", schema="safety")
    op.drop_table("safety_duty_assessments", schema="safety")
    op.drop_table("safety_target_agreements", schema="safety")
