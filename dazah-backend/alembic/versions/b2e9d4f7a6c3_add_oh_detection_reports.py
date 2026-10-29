"""occupational health detection report tables

职业健康-检测报告导入：
- ``safety.oh_detection_reports``：第三方检测报告批次（报告编号唯一，
  保留原始 PDF，统计快照与解析警告）；
- ``safety.oh_detection_results``：检测报告结果明细（一检测点一行，
  岗位接触/采样点单点、限值类型与判定、类别特有字段 extra JSON）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b2e9d4f7a6c3"
down_revision: str | None = "a7c3e5f1b8d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BASE_COLUMNS = (
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
        "is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")
    ),
)
_BASE_CONSTRAINTS = (
    sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
    sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
    sa.PrimaryKeyConstraint("id"),
)


def upgrade() -> None:
    op.create_table(
        "oh_detection_reports",
        sa.Column(
            "report_no",
            sa.String(64),
            nullable=False,
            comment="报告编号（如 NZXZW-J-2026-141）",
        ),
        sa.Column(
            "report_name",
            sa.String(255),
            nullable=False,
            server_default="",
            comment="报告名称",
        ),
        sa.Column(
            "company_name",
            sa.String(255),
            nullable=False,
            server_default="",
            comment="受检企业",
        ),
        sa.Column(
            "detection_agency",
            sa.String(255),
            nullable=False,
            server_default="",
            comment="检测机构",
        ),
        sa.Column(
            "detection_date", sa.Date(), nullable=True, comment="检测日期"
        ),
        sa.Column(
            "table_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="识别表格数",
        ),
        sa.Column(
            "total_points",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="检测点数合计",
        ),
        sa.Column(
            "exceed_points",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="超标点数",
        ),
        sa.Column(
            "noise_post_points",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="噪声作业岗位数",
        ),
        sa.Column(
            "source_file_name",
            sa.String(255),
            nullable=False,
            server_default="",
            comment="原始报告文件名",
        ),
        sa.Column(
            "source_file_path",
            sa.String(500),
            nullable=False,
            server_default="",
            comment="原始报告存储路径（uploads/safety/oh-detection/）",
        ),
        sa.Column(
            "source_file_sha256",
            sa.String(64),
            nullable=False,
            server_default="",
            comment="文件 SHA256",
        ),
        sa.Column(
            "parse_mode",
            sa.String(16),
            nullable=False,
            server_default="rules",
            comment="解析模式: rules=规则 / llm=AI兜底 / mixed=混合",
        ),
        sa.Column(
            "parse_warnings",
            sa.JSON(),
            nullable=True,
            comment="解析警告 [{table, reason}]",
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
            "uq_safety_oh_detection_reports_no",
            "report_no",
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        ),
        sa.Index(
            "ix_safety_oh_detection_reports_date", "detection_date", "is_deleted"
        ),
        schema="safety",
    )

    op.create_table(
        "oh_detection_results",
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("safety.oh_detection_reports.id"),
            nullable=False,
            comment="所属检测报告",
        ),
        sa.Column(
            "seq", sa.Integer(), nullable=False, server_default="0", comment="序号"
        ),
        sa.Column(
            "table_ref",
            sa.String(32),
            nullable=False,
            server_default="",
            comment="表号（表5-18）",
        ),
        sa.Column(
            "table_title",
            sa.String(255),
            nullable=False,
            server_default="",
            comment="表标题",
        ),
        sa.Column(
            "factor_category",
            sa.String(32),
            nullable=False,
            comment="危害因素类别: dust_total/dust_respirable/free_silica/chemical/"
            "noise/power_frequency_field/heat",
        ),
        sa.Column(
            "factor_name",
            sa.String(128),
            nullable=False,
            comment="危害因素名称（谷物粉尘/噪声…）",
        ),
        sa.Column(
            "record_type",
            sa.String(16),
            nullable=False,
            server_default="point",
            comment="记录类型: post/point",
        ),
        sa.Column(
            "workshop",
            sa.String(255),
            nullable=False,
            server_default="",
            comment="车间",
        ),
        sa.Column(
            "post", sa.String(255), nullable=False, server_default="", comment="岗位"
        ),
        sa.Column(
            "sample_point",
            sa.String(255),
            nullable=False,
            server_default="",
            comment="采样点/测量地点",
        ),
        sa.Column(
            "measured_value",
            sa.String(64),
            nullable=False,
            server_default="",
            comment="检测值原文(＜0.44)",
        ),
        sa.Column(
            "measured_value_num",
            sa.Float(),
            nullable=True,
            comment="检测值数值（检出限表达为空）",
        ),
        sa.Column(
            "unit", sa.String(32), nullable=False, server_default="", comment="单位"
        ),
        sa.Column(
            "limit_type",
            sa.String(16),
            nullable=False,
            server_default="none",
            comment="限值类型: PC-TWA/PC-STEL/MAC/PE/LEX-40h/E8/WBGT/none",
        ),
        sa.Column(
            "limit_value_num", sa.Float(), nullable=True, comment="限值数值"
        ),
        sa.Column(
            "verdict",
            sa.String(16),
            nullable=False,
            server_default="unknown",
            comment="判定: compliant=未超标 / exceed=超标 / unknown=未识别",
        ),
        sa.Column(
            "is_noise_post",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="是否噪声作业岗位（80≤LEX,8h＜85dB 场景）",
        ),
        sa.Column(
            "verdict_raw",
            sa.String(128),
            nullable=False,
            server_default="",
            comment="判定原文",
        ),
        sa.Column(
            "extra",
            sa.JSON(),
            nullable=True,
            comment="类别特有字段（噪声LEX、高温接触时间率等）",
        ),
        *_BASE_COLUMNS,
        *_BASE_CONSTRAINTS,
        sa.Index(
            "ix_safety_oh_detection_results_report", "report_id", "seq"
        ),
        sa.Index(
            "ix_safety_oh_detection_results_category",
            "report_id",
            "factor_category",
        ),
        sa.Index(
            "ix_safety_oh_detection_results_verdict", "verdict", "is_deleted"
        ),
        schema="safety",
    )


def downgrade() -> None:
    op.drop_table("oh_detection_results", schema="safety")
    op.drop_table("oh_detection_reports", schema="safety")
