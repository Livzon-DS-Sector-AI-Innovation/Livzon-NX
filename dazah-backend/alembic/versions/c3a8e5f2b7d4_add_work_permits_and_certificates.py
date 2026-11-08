"""8大特殊作业票与人员特种作业证件

依据《新版作业票（2026.7.7更新）》在 safety schema 新增：
- ``work_permits``：8 大作业票主表（票种/级别/状态/人员/措施/票面差异字段）；
- ``work_permit_nodes``：逐级审批节点实例（保留驳回重签轮次）；
- ``work_permit_gas_analyses``：气体分析（作业前 + 作业期间周期复检）；
- ``work_permit_relations``：关联作业票互链；
- ``work_permit_attachments``：作业票附件（盲板位置图/简图/示意图等）；
- ``special_work_certificates``：人员特殊作业证件（证件号/类别/有效期）；
- ``special_work_certificate_files``：证件附件（扫描件，供 AI 识别）；
- ``work_permit_approver_configs``：节点默认审批人配置；
- ``work_permit_settings``：复检间隔/有效期等运行参数；
- ``special_work_certificate_reminder_log``：证件到期提醒去重记录。

Revision ID: c3a8e5f2b7d4
Revises: 9af3c6bb8778
Create Date: 2026-11-06 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c3a8e5f2b7d4"
down_revision: str | None = "9af3c6bb8778"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

jsonb = postgresql.JSONB(astext_type=sa.Text())


def _base_columns() -> list[sa.Column]:
    """每张表独立生成基础列（Column 对象不可跨表复用）。"""
    return [
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
            "is_deleted", sa.Boolean(), nullable=False, server_default="false"
        ),
    ]


def _base_constraints() -> tuple[sa.Constraint, ...]:
    return (
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def upgrade() -> None:
    # ── 作业票主表 ──
    op.create_table(
        "work_permits",
        *_base_columns(),
        sa.Column(
            "permit_no", sa.String(64), nullable=False, comment="作业票编号"
        ),
        sa.Column(
            "permit_type",
            sa.String(32),
            nullable=False,
            comment=(
                "票种: hot_work/confined_space/blind_plate/height_work/"
                "lifting/temporary_electricity/excavation/road_breaking"
            ),
        ),
        sa.Column(
            "permit_level",
            sa.String(16),
            nullable=False,
            server_default="none",
            comment="作业级别: special/grade1/grade2/grade3/none",
        ),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="draft",
            comment=(
                "状态: draft/pending_approval/approved/active/completed/"
                "rejected/cancelled"
            ),
        ),
        sa.Column(
            "apply_department", sa.String(100), nullable=True, comment="申请单位"
        ),
        sa.Column(
            "apply_time",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="作业申请时间",
        ),
        sa.Column(
            "work_description", sa.Text(), nullable=True, comment="作业内容"
        ),
        sa.Column(
            "work_location", sa.String(255), nullable=True, comment="作业地点"
        ),
        sa.Column(
            "work_unit", sa.String(100), nullable=True, comment="作业单位"
        ),
        sa.Column(
            "planned_start_time",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="实施开始时间",
        ),
        sa.Column(
            "planned_end_time",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="实施结束时间",
        ),
        sa.Column(
            "actual_start_time",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="实际开始时间（验票时写入）",
        ),
        sa.Column(
            "actual_end_time",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="实际结束时间（完工验收时写入）",
        ),
        sa.Column("persons", jsonb, comment="作业相关人员（含证件快照）"),
        sa.Column(
            "risk_identifications", jsonb, comment="风险辨识结果勾选"
        ),
        sa.Column("safety_measures", jsonb, comment="安全措施勾选"),
        sa.Column(
            "type_data", jsonb, comment="票种差异字段（按模板校验）"
        ),
        sa.Column(
            "related_legacy_no_text",
            sa.String(500),
            nullable=True,
            comment="关联的其他特殊作业及安全作业票编号（自由文本）",
        ),
        sa.Column(
            "current_node_seq",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="当前轮次待处理节点 seq（0=未提交/已完结）",
        ),
        sa.Column(
            "approval_round",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="当前审批轮次（驳回重签递增）",
        ),
        sa.Column(
            "reject_opinion", sa.Text(), nullable=True, comment="最近一次驳回意见"
        ),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        *_base_constraints(),
        schema="safety",
    )
    op.create_index(
        "uq_work_permits_permit_no",
        "work_permits",
        ["permit_no"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        schema="safety",
    )
    op.create_index(
        "ix_work_permits_type_status",
        "work_permits",
        ["permit_type", "status"],
        schema="safety",
    )
    op.create_index(
        "ix_work_permits_apply_time",
        "work_permits",
        ["apply_time"],
        schema="safety",
    )

    # ── 审批节点实例 ──
    op.create_table(
        "work_permit_nodes",
        *_base_columns(),
        sa.Column(
            "permit_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="所属作业票",
        ),
        sa.Column(
            "round",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="审批轮次（驳回重签 +1）",
        ),
        sa.Column(
            "seq",
            sa.Integer(),
            nullable=False,
            comment="节点顺序（同轮次内从 1 递增）",
        ),
        sa.Column(
            "node_key", sa.String(64), nullable=False, comment="节点标识"
        ),
        sa.Column(
            "node_name",
            sa.String(100),
            nullable=False,
            comment="节点名称（票面签字行原文）",
        ),
        sa.Column(
            "node_kind",
            sa.String(16),
            nullable=False,
            comment="节点类型: approve/confirm/verify/accept",
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="waiting",
            comment=(
                "状态: waiting/pending/approved/rejected/skipped"
            ),
        ),
        sa.Column(
            "assigned_approver_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("acted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "acted_at", sa.DateTime(timezone=True), nullable=True, comment="签字时间"
        ),
        sa.Column("opinion", sa.Text(), nullable=True, comment="审批/确认意见"),
        sa.ForeignKeyConstraint(
            ["permit_id"], ["safety.work_permits.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["assigned_approver_id"], ["identity.users.id"]
        ),
        sa.ForeignKeyConstraint(["acted_by"], ["identity.users.id"]),
        *_base_constraints(),
        schema="safety",
    )
    op.create_index(
        "ix_work_permit_nodes_permit_round_seq",
        "work_permit_nodes",
        ["permit_id", "round", "seq"],
        schema="safety",
    )
    op.create_index(
        "ix_work_permit_nodes_approver_pending",
        "work_permit_nodes",
        ["assigned_approver_id", "status"],
        schema="safety",
    )

    # ── 气体分析 ──
    op.create_table(
        "work_permit_gas_analyses",
        *_base_columns(),
        sa.Column(
            "permit_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="所属作业票",
        ),
        sa.Column(
            "phase",
            sa.String(16),
            nullable=False,
            server_default="pre_work",
            comment="阶段: pre_work=作业前分析 / on_duty=作业期间复检",
        ),
        sa.Column(
            "sampled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="取样分析时间",
        ),
        sa.Column(
            "analysis_point",
            sa.String(255),
            nullable=True,
            comment="分析部位/分析点",
        ),
        sa.Column(
            "items", jsonb, comment="分析项目 [{name,standard,value,unit}]"
        ),
        sa.Column(
            "oxygen_value",
            sa.String(32),
            nullable=True,
            comment="氧气含量（体积分数）",
        ),
        sa.Column(
            "analyst_name", sa.String(100), nullable=True, comment="分析人"
        ),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        sa.ForeignKeyConstraint(
            ["permit_id"], ["safety.work_permits.id"], ondelete="CASCADE"
        ),
        *_base_constraints(),
        schema="safety",
    )
    op.create_index(
        "ix_work_permit_gas_permit_phase",
        "work_permit_gas_analyses",
        ["permit_id", "phase"],
        schema="safety",
    )

    # ── 关联作业票 ──
    op.create_table(
        "work_permit_relations",
        *_base_columns(),
        sa.Column(
            "permit_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="本票",
        ),
        sa.Column(
            "related_permit_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="关联票",
        ),
        sa.ForeignKeyConstraint(
            ["permit_id"], ["safety.work_permits.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["related_permit_id"], ["safety.work_permits.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "permit_id",
            "related_permit_id",
            name="uq_work_permit_relations_pair",
        ),
        *_base_constraints(),
        schema="safety",
    )
    op.create_index(
        "ix_work_permit_relations_related",
        "work_permit_relations",
        ["related_permit_id"],
        schema="safety",
    )

    # ── 作业票附件 ──
    op.create_table(
        "work_permit_attachments",
        *_base_columns(),
        sa.Column(
            "permit_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="所属作业票",
        ),
        sa.Column(
            "category",
            sa.String(32),
            nullable=False,
            server_default="other",
            comment="附件类别: blind_map/sketch/photo/other",
        ),
        sa.Column(
            "file_name", sa.String(255), nullable=False, comment="原始文件名"
        ),
        sa.Column(
            "storage_key",
            sa.String(500),
            nullable=False,
            comment="存储 key（MinIO 或本地回退）",
        ),
        sa.Column(
            "content_type", sa.String(100), nullable=True, comment="MIME 类型"
        ),
        sa.Column(
            "size_bytes",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="文件字节数",
        ),
        sa.ForeignKeyConstraint(
            ["permit_id"], ["safety.work_permits.id"], ondelete="CASCADE"
        ),
        *_base_constraints(),
        schema="safety",
    )
    op.create_index(
        "ix_work_permit_attachments_permit",
        "work_permit_attachments",
        ["permit_id", "is_deleted"],
        schema="safety",
    )

    # ── 人员特殊作业证件 ──
    op.create_table(
        "special_work_certificates",
        *_base_columns(),
        sa.Column(
            "person_name",
            sa.String(100),
            nullable=False,
            comment="持证人姓名",
        ),
        sa.Column(
            "identity_user_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column(
            "department", sa.String(100), nullable=True, comment="所属部门"
        ),
        sa.Column(
            "certificate_category",
            sa.String(64),
            nullable=False,
            comment="证件类别（CERTIFICATE_CATEGORIES 字典）",
        ),
        sa.Column(
            "certificate_no", sa.String(100), nullable=True, comment="证件号"
        ),
        sa.Column(
            "issuing_authority",
            sa.String(200),
            nullable=True,
            comment="发证机关",
        ),
        sa.Column("issue_date", sa.Date(), nullable=True, comment="发证日期"),
        sa.Column("expiry_date", sa.Date(), nullable=True, comment="有效期至"),
        sa.Column(
            "qualification_scope",
            sa.Text(),
            nullable=True,
            comment="准操项目/资质范围",
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="valid",
            comment=(
                "状态: valid/expiring/expired/revoked（保存时按有效期计算）"
            ),
        ),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        sa.ForeignKeyConstraint(
            ["identity_user_id"], ["identity.users.id"]
        ),
        *_base_constraints(),
        schema="safety",
    )
    op.create_index(
        "uq_special_work_certificates_no",
        "special_work_certificates",
        ["certificate_no", "certificate_category"],
        unique=True,
        postgresql_where=sa.text(
            "is_deleted = false and certificate_no is not null "
            "and certificate_no <> ''"
        ),
        schema="safety",
    )
    op.create_index(
        "ix_special_work_certificates_category",
        "special_work_certificates",
        ["certificate_category", "status"],
        schema="safety",
    )
    op.create_index(
        "ix_special_work_certificates_expiry",
        "special_work_certificates",
        ["expiry_date"],
        schema="safety",
    )

    # ── 证件附件 ──
    op.create_table(
        "special_work_certificate_files",
        *_base_columns(),
        sa.Column(
            "certificate_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="所属证件",
        ),
        sa.Column(
            "file_name", sa.String(255), nullable=False, comment="原始文件名"
        ),
        sa.Column(
            "storage_key",
            sa.String(500),
            nullable=False,
            comment="存储 key（MinIO 或本地回退）",
        ),
        sa.Column(
            "content_type", sa.String(100), nullable=True, comment="MIME 类型"
        ),
        sa.Column(
            "size_bytes",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="文件字节数",
        ),
        sa.ForeignKeyConstraint(
            ["certificate_id"],
            ["safety.special_work_certificates.id"],
            ondelete="CASCADE",
        ),
        *_base_constraints(),
        schema="safety",
    )
    op.create_index(
        "ix_special_work_cert_files_cert",
        "special_work_certificate_files",
        ["certificate_id", "is_deleted"],
        schema="safety",
    )

    # ── 节点默认审批人配置 ──
    op.create_table(
        "work_permit_approver_configs",
        *_base_columns(),
        sa.Column("permit_type", sa.String(32), nullable=False, comment="票种"),
        sa.Column("node_key", sa.String(64), nullable=False, comment="节点标识"),
        sa.Column(
            "node_name",
            sa.String(100),
            nullable=False,
            comment="节点名称（冗余展示）",
        ),
        sa.Column(
            "approver_user_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        sa.ForeignKeyConstraint(
            ["approver_user_id"], ["identity.users.id"]
        ),
        sa.UniqueConstraint(
            "permit_type",
            "node_key",
            name="uq_work_permit_approver_configs_node",
        ),
        *_base_constraints(),
        schema="safety",
    )

    # ── 运行参数 ──
    op.create_table(
        "work_permit_settings",
        *_base_columns(),
        sa.Column(
            "setting_key",
            sa.String(100),
            nullable=False,
            comment="参数键（如 gas_cycle_minutes.hot_work）",
        ),
        sa.Column("setting_value", jsonb, comment="参数值"),
        sa.Column("description", sa.Text(), nullable=True, comment="参数说明"),
        *_base_constraints(),
        schema="safety",
    )
    op.create_index(
        "uq_work_permit_settings_key",
        "work_permit_settings",
        ["setting_key"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        schema="safety",
    )

    # ── 证件到期提醒去重 ──
    op.create_table(
        "special_work_certificate_reminder_log",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), nullable=False
        ),
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
            "is_deleted", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "certificate_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="证件",
        ),
        sa.Column(
            "milestone_days",
            sa.Integer(),
            nullable=False,
            comment="提醒节点（距到期天数，0=已过期）",
        ),
        sa.Column(
            "notified_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="推送时间",
        ),
        sa.ForeignKeyConstraint(
            ["certificate_id"],
            ["safety.special_work_certificates.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "certificate_id",
            "milestone_days",
            name="uq_special_work_cert_reminder_milestone",
        ),
        schema="safety",
    )

    # ── 安全模块飞书设置：作业票通知 / 证件到期提醒 ──
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "permit_notify_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="是否启用 8 大作业票飞书卡片通知",
        ),
        schema="safety",
    )
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "permit_notify_chat_ids",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
            comment="作业票通知群 chat_id 列表（备用）",
        ),
        schema="safety",
    )
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "permit_notify_user_ids",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
            comment="作业票通知抄送个人 open_id 列表",
        ),
        schema="safety",
    )
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "cert_expiry_notify_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="是否启用特种作业证件到期提醒",
        ),
        schema="safety",
    )
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "cert_expiry_notify_milestones",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
            comment="证件到期提醒节点天数列表（0 = 已过期节点）",
        ),
        schema="safety",
    )
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "cert_expiry_notify_chat_ids",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
            comment="证件到期提醒群 chat_id 列表",
        ),
        schema="safety",
    )
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "cert_expiry_notify_user_ids",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
            comment="证件到期提醒个人 open_id 列表",
        ),
        schema="safety",
    )


def downgrade() -> None:
    op.drop_column(
        "feishu_app_settings",
        "cert_expiry_notify_user_ids",
        schema="safety",
    )
    op.drop_column(
        "feishu_app_settings",
        "cert_expiry_notify_chat_ids",
        schema="safety",
    )
    op.drop_column(
        "feishu_app_settings",
        "cert_expiry_notify_milestones",
        schema="safety",
    )
    op.drop_column(
        "feishu_app_settings",
        "cert_expiry_notify_enabled",
        schema="safety",
    )
    op.drop_column(
        "feishu_app_settings",
        "permit_notify_user_ids",
        schema="safety",
    )
    op.drop_column(
        "feishu_app_settings",
        "permit_notify_chat_ids",
        schema="safety",
    )
    op.drop_column(
        "feishu_app_settings",
        "permit_notify_enabled",
        schema="safety",
    )
    op.drop_table("special_work_certificate_reminder_log", schema="safety")
    op.drop_index(
        "uq_work_permit_settings_key",
        table_name="work_permit_settings",
        schema="safety",
    )
    op.drop_table("work_permit_settings", schema="safety")
    op.drop_table("work_permit_approver_configs", schema="safety")
    op.drop_index(
        "ix_special_work_cert_files_cert",
        table_name="special_work_certificate_files",
        schema="safety",
    )
    op.drop_table("special_work_certificate_files", schema="safety")
    op.drop_index(
        "ix_special_work_certificates_expiry",
        table_name="special_work_certificates",
        schema="safety",
    )
    op.drop_index(
        "ix_special_work_certificates_category",
        table_name="special_work_certificates",
        schema="safety",
    )
    op.drop_index(
        "uq_special_work_certificates_no",
        table_name="special_work_certificates",
        schema="safety",
    )
    op.drop_table("special_work_certificates", schema="safety")
    op.drop_index(
        "ix_work_permit_attachments_permit",
        table_name="work_permit_attachments",
        schema="safety",
    )
    op.drop_table("work_permit_attachments", schema="safety")
    op.drop_index(
        "ix_work_permit_relations_related",
        table_name="work_permit_relations",
        schema="safety",
    )
    op.drop_table("work_permit_relations", schema="safety")
    op.drop_index(
        "ix_work_permit_gas_permit_phase",
        table_name="work_permit_gas_analyses",
        schema="safety",
    )
    op.drop_table("work_permit_gas_analyses", schema="safety")
    op.drop_index(
        "ix_work_permit_nodes_approver_pending",
        table_name="work_permit_nodes",
        schema="safety",
    )
    op.drop_index(
        "ix_work_permit_nodes_permit_round_seq",
        table_name="work_permit_nodes",
        schema="safety",
    )
    op.drop_table("work_permit_nodes", schema="safety")
    op.drop_index(
        "ix_work_permits_apply_time", table_name="work_permits", schema="safety"
    )
    op.drop_index(
        "ix_work_permits_type_status", table_name="work_permits", schema="safety"
    )
    op.drop_index(
        "uq_work_permits_permit_no", table_name="work_permits", schema="safety"
    )
    op.drop_table("work_permits", schema="safety")
