"""safety governance / site management / emergency mgmt tables

安全管理五项功能（目标责任与绩效、安全设施台账、危化品与 MSDS、
应急管理、厂区建筑底册）：
- ``safety.campus_buildings``：厂区建筑/分区底册（驾驶舱平面图落点），
  种子数据来自 ``app/modules/safety/seeds/campus_buildings.json``
  （依据 BM.EP.101-05 厂区平面图 2023.11.12 标定）；
- ``safety.safety_targets`` / ``safety.safety_target_records``：年度安全
  目标与考核期进度；
- ``safety.safety_facilities`` / ``safety.safety_facility_inspections``：
  洗眼器/气体检测仪/防护设施等台账与点检记录；
- ``safety.hazardous_chemicals`` / ``safety.chemical_inventories``：危化品
  档案（MSDS 附件）与车间存量（超储预警）；
- ``safety.emergency_plans`` / ``safety.emergency_drills`` /
  ``safety.emergency_supplies``：应急预案、演练计划记录、应急物资。
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

revision: str = "d7f3b9c1e5a2"
down_revision: str | None = "f2a7c9e4b5d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CAMPUS_SEED_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "modules"
    / "safety"
    / "seeds"
    / "campus_buildings.json"
)

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


def _seed_campus_rows() -> list[dict]:
    buildings: list[dict] = json.loads(CAMPUS_SEED_PATH.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for index, item in enumerate(buildings):
        rows.append(
            {
                "id": uuid4(),
                "code": item.get("code") or "",
                "name": item["name"],
                "category": item.get("category") or "workshop",
                "x_pct": float(item.get("x_pct") or 0.0),
                "y_pct": float(item.get("y_pct") or 0.0),
                "aliases": item.get("aliases") or [],
                "sort_order": index,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        )
    return rows


def upgrade() -> None:
    # ---------- 厂区建筑底册 ----------
    op.create_table(
        "campus_buildings",
        sa.Column(
            "code",
            sa.String(40),
            nullable=False,
            server_default="",
            comment="建筑编号（图纸编号，如 101、802）",
        ),
        sa.Column(
            "name",
            sa.String(120),
            nullable=False,
            comment="建筑名称（重名建筑带方位/编号后缀）",
        ),
        sa.Column(
            "category",
            sa.String(30),
            nullable=False,
            server_default="workshop",
            comment="类别: workshop/warehouse/utility/env/tank/office/logistics/sports",
        ),
        sa.Column(
            "x_pct",
            sa.Float(),
            nullable=False,
            server_default="0",
            comment="平面图横向百分比坐标（0-100）",
        ),
        sa.Column(
            "y_pct",
            sa.Float(),
            nullable=False,
            server_default="0",
            comment="平面图纵向百分比坐标（0-100）",
        ),
        sa.Column(
            "aliases",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="地点别名列表（自由文本归一用）",
        ),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="展示排序",
        ),
        *_BASE_COLUMNS,
        *_BASE_CONSTRAINTS,
        sa.Index(
            "uq_safety_campus_buildings_name",
            "name",
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        ),
        sa.Index("ix_safety_campus_buildings_category", "category", "is_deleted"),
        schema="safety",
    )
    bind = op.get_bind()
    existing = bind.execute(
        sa.text("SELECT count(*) FROM safety.campus_buildings")
    ).scalar_one()
    if existing == 0:
        target = sa.Table(
            "campus_buildings",
            sa.MetaData(),
            sa.Column("id", postgresql.UUID(as_uuid=True)),
            sa.Column("code", sa.String(40)),
            sa.Column("name", sa.String(120)),
            sa.Column("category", sa.String(30)),
            sa.Column("x_pct", sa.Float()),
            sa.Column("y_pct", sa.Float()),
            sa.Column("aliases", postgresql.JSONB(astext_type=sa.Text())),
            sa.Column("sort_order", sa.Integer()),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
            schema="safety",
        )
        op.bulk_insert(target, _seed_campus_rows())

    # ---------- 目标责任与绩效 ----------
    op.create_table(
        "safety_targets",
        sa.Column("year", sa.Integer(), nullable=False, comment="目标年度"),
        sa.Column(
            "title",
            sa.String(200),
            nullable=False,
            comment="目标名称（如 杜绝重伤及以上事故）",
        ),
        sa.Column(
            "category",
            sa.String(40),
            nullable=False,
            server_default="事故控制",
            comment="目标类别（事故控制/隐患治理/培训教育/职业健康/消防应急等）",
        ),
        sa.Column(
            "metric",
            sa.String(200),
            nullable=False,
            server_default="",
            comment="考核指标说明（如何量化）",
        ),
        sa.Column(
            "target_value",
            sa.String(100),
            nullable=False,
            server_default="",
            comment="目标值（如 0 起、100%、≤3 项）",
        ),
        sa.Column(
            "unit",
            sa.String(30),
            nullable=False,
            server_default="",
            comment="计量单位（起/次/%/项）",
        ),
        sa.Column(
            "owner_department",
            sa.String(100),
            nullable=False,
            server_default="",
            comment="责任部门",
        ),
        sa.Column(
            "owner_name",
            sa.String(60),
            nullable=False,
            server_default="",
            comment="责任人",
        ),
        sa.Column("deadline", sa.Date(), nullable=True, comment="完成时限"),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="in_progress",
            comment="状态: in_progress=进行中 / achieved=已达成 / not_achieved=未达成",
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
            "uq_safety_targets_year_title",
            "year",
            "title",
            "owner_department",
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        ),
        sa.Index("ix_safety_targets_year", "year", "is_deleted"),
        schema="safety",
    )
    op.create_table(
        "safety_target_records",
        sa.Column(
            "target_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("safety.safety_targets.id"),
            nullable=False,
            comment="所属目标",
        ),
        sa.Column(
            "period",
            sa.String(20),
            nullable=False,
            comment="考核期（如 2026-Q1、2026-03）",
        ),
        sa.Column(
            "actual_value",
            sa.String(100),
            nullable=False,
            server_default="",
            comment="实际完成值",
        ),
        sa.Column(
            "completion_pct", sa.Float(), nullable=True, comment="完成率（%，可空）"
        ),
        sa.Column(
            "note", sa.Text(), nullable=False, server_default="", comment="情况说明"
        ),
        *_BASE_COLUMNS,
        *_BASE_CONSTRAINTS,
        sa.Index(
            "uq_safety_target_records_target_period",
            "target_id",
            "period",
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        ),
        sa.Index("ix_safety_target_records_target", "target_id", "is_deleted"),
        schema="safety",
    )

    # ---------- 安全设施台账 ----------
    op.create_table(
        "safety_facilities",
        sa.Column(
            "category",
            sa.String(30),
            nullable=False,
            server_default="other",
            comment="类别: eyewash=洗眼器 / gas_detector=气体检测仪 / "
            "protective=防护设施 / other=其他",
        ),
        sa.Column(
            "facility_no",
            sa.String(100),
            nullable=False,
            server_default="",
            comment="设施编号（唯一）",
        ),
        sa.Column("name", sa.String(200), nullable=False, comment="设施名称"),
        sa.Column(
            "model_spec",
            sa.String(200),
            nullable=False,
            server_default="",
            comment="型号规格",
        ),
        sa.Column(
            "department",
            sa.String(100),
            nullable=False,
            server_default="",
            comment="所属部门/车间",
        ),
        sa.Column(
            "location",
            sa.String(255),
            nullable=False,
            server_default="",
            comment="安装位置",
        ),
        sa.Column("installed_at", sa.Date(), nullable=True, comment="投用日期"),
        sa.Column(
            "expiry_date",
            sa.Date(),
            nullable=True,
            comment="校准/检定/报废到期日（气体检测仪为校准有效期）",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="normal",
            comment="状态: normal=完好 / damaged=损坏 / scrapped=报废",
        ),
        sa.Column(
            "last_inspected_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最近点检时间",
        ),
        sa.Column(
            "last_inspection_result",
            sa.String(20),
            nullable=True,
            comment="最近点检结论: pass/fail",
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
            "uq_safety_facilities_no",
            "facility_no",
            unique=True,
            postgresql_where=sa.text("is_deleted = false and facility_no <> ''"),
        ),
        sa.Index("ix_safety_facilities_category", "category", "is_deleted"),
        sa.Index("ix_safety_facilities_department", "department", "is_deleted"),
        schema="safety",
    )
    op.create_table(
        "safety_facility_inspections",
        sa.Column(
            "facility_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("safety.safety_facilities.id"),
            nullable=False,
            comment="设施",
        ),
        sa.Column(
            "facility_category",
            sa.String(30),
            nullable=False,
            server_default="",
            comment="设施类别快照",
        ),
        sa.Column(
            "facility_no",
            sa.String(100),
            nullable=False,
            server_default="",
            comment="设施编号快照",
        ),
        sa.Column(
            "facility_name",
            sa.String(200),
            nullable=False,
            server_default="",
            comment="设施名称快照",
        ),
        sa.Column(
            "items",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="点检项 [{key, label, result: ok/fail, remark}]",
        ),
        sa.Column("result", sa.String(20), nullable=False, comment="结论: pass/fail"),
        sa.Column(
            "abnormal_action",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="异常处理措施",
        ),
        sa.Column(
            "inspector_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="点检人用户ID",
        ),
        sa.Column(
            "inspector_name",
            sa.String(100),
            nullable=False,
            server_default="",
            comment="点检人姓名",
        ),
        sa.Column(
            "inspected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="点检时间",
        ),
        sa.Column(
            "source",
            sa.String(20),
            nullable=False,
            server_default="web",
            comment="提交来源: web=网页端",
        ),
        *_BASE_COLUMNS,
        *_BASE_CONSTRAINTS,
        sa.Index(
            "ix_safety_facility_inspections_facility", "facility_id", "inspected_at"
        ),
        sa.Index("ix_safety_facility_inspections_inspected_at", "inspected_at"),
        schema="safety",
    )

    # ---------- 危化品与 MSDS ----------
    op.create_table(
        "hazardous_chemicals",
        sa.Column("name", sa.String(200), nullable=False, comment="化学品名称"),
        sa.Column(
            "alias",
            sa.String(200),
            nullable=False,
            server_default="",
            comment="别名/商品名",
        ),
        sa.Column(
            "cas_no", sa.String(60), nullable=False, server_default="", comment="CAS 号"
        ),
        sa.Column(
            "category",
            sa.String(40),
            nullable=False,
            server_default="other",
            comment="危险性类别: explosive/flammable_gas/oxidizing_gas/"
            "flammable_liquid/flammable_solid/self_reactive/oxidizing_liquid/"
            "organic_peroxide/toxic/corrosive/other",
        ),
        sa.Column(
            "hazard_statements",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="危险性概述（理化/健康/环境危害）",
        ),
        sa.Column(
            "storage_requirements",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="储存要求（温度/禁配/防爆等）",
        ),
        sa.Column(
            "msds_file_path",
            sa.String(500),
            nullable=False,
            server_default="",
            comment="MSDS 文件路径（uploads/safety/hazchem/）",
        ),
        sa.Column(
            "msds_file_name",
            sa.String(255),
            nullable=False,
            server_default="",
            comment="MSDS 原始文件名",
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
            "uq_safety_hazardous_chemicals_name",
            "name",
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        ),
        sa.Index("ix_safety_hazardous_chemicals_category", "category", "is_deleted"),
        schema="safety",
    )
    op.create_table(
        "chemical_inventories",
        sa.Column(
            "chemical_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("safety.hazardous_chemicals.id"),
            nullable=False,
            comment="危化品",
        ),
        sa.Column("workshop", sa.String(100), nullable=False, comment="车间/库房"),
        sa.Column(
            "quantity",
            sa.Numeric(14, 4),
            nullable=False,
            server_default="0",
            comment="当前存量",
        ),
        sa.Column(
            "upper_limit",
            sa.Numeric(14, 4),
            nullable=True,
            comment="存量上限（空=不设限）",
        ),
        sa.Column(
            "unit", sa.String(30), nullable=False, server_default="kg", comment="单位"
        ),
        sa.Column(
            "remark", sa.Text(), nullable=False, server_default="", comment="备注"
        ),
        *_BASE_COLUMNS,
        *_BASE_CONSTRAINTS,
        sa.Index(
            "uq_safety_chemical_inventories_chem_ws",
            "chemical_id",
            "workshop",
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        ),
        sa.Index("ix_safety_chemical_inventories_workshop", "workshop", "is_deleted"),
        schema="safety",
    )

    # ---------- 应急管理 ----------
    op.create_table(
        "emergency_plans",
        sa.Column("name", sa.String(255), nullable=False, comment="预案名称"),
        sa.Column(
            "plan_type",
            sa.String(30),
            nullable=False,
            server_default="onsite",
            comment="类型: comprehensive=综合预案 / special=专项预案 / "
            "onsite=现场处置方案",
        ),
        sa.Column(
            "version",
            sa.String(60),
            nullable=False,
            server_default="V1.0",
            comment="版本号",
        ),
        sa.Column("issued_at", sa.Date(), nullable=True, comment="发布日期"),
        sa.Column(
            "review_due_date", sa.Date(), nullable=True, comment="下次评审/修订到期日"
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
            comment="状态: active=现行 / revising=修订中 / obsolete=废止",
        ),
        sa.Column(
            "department",
            sa.String(100),
            nullable=False,
            server_default="",
            comment="编制/归口部门",
        ),
        sa.Column(
            "file_path",
            sa.String(500),
            nullable=False,
            server_default="",
            comment="预案文件路径（uploads/safety/emergency/）",
        ),
        sa.Column(
            "file_name",
            sa.String(255),
            nullable=False,
            server_default="",
            comment="预案原始文件名",
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
            "uq_safety_emergency_plans_name_version",
            "name",
            "version",
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        ),
        sa.Index("ix_safety_emergency_plans_status", "status", "is_deleted"),
        schema="safety",
    )
    op.create_table(
        "emergency_drills",
        sa.Column("name", sa.String(255), nullable=False, comment="演练名称"),
        sa.Column(
            "drill_type",
            sa.String(30),
            nullable=False,
            server_default="practical",
            comment="类型: tabletop=桌面推演 / practical=实战演练 / "
            "comprehensive=综合演练",
        ),
        sa.Column(
            "scenario",
            sa.String(255),
            nullable=False,
            server_default="",
            comment="演练情景（如 液氨泄漏、火灾疏散）",
        ),
        sa.Column(
            "plan_name",
            sa.String(255),
            nullable=False,
            server_default="",
            comment="对应预案名称",
        ),
        sa.Column("planned_date", sa.Date(), nullable=True, comment="计划日期"),
        sa.Column("actual_date", sa.Date(), nullable=True, comment="实际执行日期"),
        sa.Column(
            "location",
            sa.String(255),
            nullable=False,
            server_default="",
            comment="演练地点",
        ),
        sa.Column(
            "departments",
            sa.String(500),
            nullable=False,
            server_default="",
            comment="参演部门（顿号分隔）",
        ),
        sa.Column(
            "participants_count", sa.Integer(), nullable=True, comment="参演人数"
        ),
        sa.Column(
            "summary",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="演练过程与评估总结",
        ),
        sa.Column(
            "issues",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="发现问题与改进措施",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="planned",
            comment="状态: planned=计划 / done=完成 / cancelled=取消",
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
            "ix_safety_emergency_drills_planned_date", "planned_date", "is_deleted"
        ),
        sa.Index("ix_safety_emergency_drills_status", "status", "is_deleted"),
        schema="safety",
    )
    op.create_table(
        "emergency_supplies",
        sa.Column("name", sa.String(200), nullable=False, comment="物资名称"),
        sa.Column(
            "category",
            sa.String(30),
            nullable=False,
            server_default="other",
            comment="类别: firefighting=消防 / protective=防护 / medical=医疗 / "
            "communication=通讯 / leak_sealing=堵漏 / other=其他",
        ),
        sa.Column(
            "spec",
            sa.String(200),
            nullable=False,
            server_default="",
            comment="规格型号",
        ),
        sa.Column(
            "location",
            sa.String(255),
            nullable=False,
            server_default="",
            comment="存放位置",
        ),
        sa.Column(
            "department",
            sa.String(100),
            nullable=False,
            server_default="",
            comment="管理部门/车间",
        ),
        sa.Column(
            "quantity",
            sa.Numeric(14, 2),
            nullable=False,
            server_default="0",
            comment="数量",
        ),
        sa.Column(
            "unit", sa.String(30), nullable=False, server_default="件", comment="单位"
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="good",
            comment="状态: good=完好 / repair=待修 / scrapped=报废",
        ),
        sa.Column(
            "expiry_date", sa.Date(), nullable=True, comment="有效期至（如药剂/呼吸器）"
        ),
        sa.Column("last_checked_at", sa.Date(), nullable=True, comment="最近检查日期"),
        sa.Column(
            "last_check_result",
            sa.String(255),
            nullable=False,
            server_default="",
            comment="最近检查结论（完好/异常描述）",
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
        sa.Index("ix_safety_emergency_supplies_category", "category", "is_deleted"),
        sa.Index("ix_safety_emergency_supplies_department", "department", "is_deleted"),
        schema="safety",
    )


def downgrade() -> None:
    for table in (
        "emergency_supplies",
        "emergency_drills",
        "emergency_plans",
        "chemical_inventories",
        "hazardous_chemicals",
        "safety_facility_inspections",
        "safety_facilities",
        "safety_target_records",
        "safety_targets",
        "campus_buildings",
    ):
        op.drop_table(table, schema="safety")
