"""Production ORM models live here."""

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base_model import BaseModel


class BatchStatus(StrEnum):
    """批次状态枚举"""

    DRAFT = "draft"  # 草稿
    RELEASED = "released"  # 已下达
    IN_PROGRESS = "in_progress"  # 执行中
    COMPLETED = "completed"  # 已完成
    CANCELLED = "cancelled"  # 已取消


class PlanStatus(StrEnum):
    """计划状态枚举"""

    DRAFT = "draft"  # 草稿
    APPROVED = "approved"  # 已批准
    EXECUTING = "executing"  # 执行中
    COMPLETED = "completed"  # 已完成


class ProcessSpecStatus(StrEnum):
    """工艺规程状态枚举"""

    DRAFT = "draft"  # 草稿
    APPROVED = "approved"  # 已批准
    EFFECTIVE = "effective"  # 已生效
    ARCHIVED = "archived"  # 已归档


class TaskStatus(StrEnum):
    """任务状态枚举"""

    PENDING = "pending"  # 待执行
    ASSIGNED = "assigned"  # 已分配
    IN_PROGRESS = "in_progress"  # 执行中
    COMPLETED = "completed"  # 已完成


class OperationType(StrEnum):
    """操作类型枚举"""

    MATERIAL_ADD = "material_add"  # 投料
    TRANSFER = "transfer"  # 转序
    SAMPLING = "sampling"  # 取样
    EQUIPMENT_CHECK = "equipment_check"  # 设备检查
    PARAMETER_RECORD = "parameter_record"  # 参数记录
    PACKAGING = "packaging"  # 包装


class Batch(BaseModel):
    """批次主表"""

    __tablename__ = "batches"
    __table_args__ = (
        UniqueConstraint("batch_no", name="uq_batches_batch_no"),
        {"schema": "production"},
    )

    batch_no: Mapped[str] = mapped_column(String(64), nullable=False, comment="批次号")
    product_code: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="产品编码"
    )
    product_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="产品名称"
    )
    specification: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="规格"
    )
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="单位")
    status: Mapped[str] = mapped_column(
        String(32),
        default="draft",
        server_default="draft",
        nullable=False,
        comment="状态",
    )
    planned_qty: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="计划数量"
    )
    actual_qty: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="实际产出数量"
    )
    input_qty: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="实际投入数量"
    )
    process_spec_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("production.process_specs.id"),
        nullable=True,
        comment="工艺规程ID",
    )
    production_line: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="生产线"
    )
    start_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="开始时间"
    )
    end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="结束时间"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")

    # 关系
    materials: Mapped[list["BatchMaterial"]] = relationship(
        "BatchMaterial", back_populates="batch", lazy="selectin"
    )
    records: Mapped[list["ProductionRecord"]] = relationship(
        "ProductionRecord", back_populates="batch", lazy="selectin"
    )
    material_balance: Mapped["MaterialBalance | None"] = relationship(
        "MaterialBalance", back_populates="batch", uselist=False, lazy="selectin"
    )


class BatchMaterial(BaseModel):
    """批次物料表"""

    __tablename__ = "batch_materials"
    __table_args__ = {"schema": "production"}

    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("production.batches.id"),
        nullable=False,
        comment="批次ID",
    )
    material_code: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="物料编码"
    )
    material_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="物料名称"
    )
    material_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="物料类型"
    )
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="单位")
    planned_qty: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="计划用量"
    )
    actual_qty: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="实际用量"
    )
    lot_no: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="批号/批次"
    )
    stage: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="工序阶段"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")

    # 关系
    batch: Mapped["Batch"] = relationship("Batch", back_populates="materials")


class ProductionPlan(BaseModel):
    """生产计划表"""

    __tablename__ = "production_plans"
    __table_args__ = (
        UniqueConstraint("plan_no", name="uq_production_plans_plan_no"),
        {"schema": "production"},
    )

    plan_no: Mapped[str] = mapped_column(String(64), nullable=False, comment="计划编号")
    plan_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="计划名称"
    )
    plan_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="计划类型:月计划/周计划"
    )
    plan_month: Mapped[str | None] = mapped_column(
        String(7), nullable=True, comment="计划月份YYYY-MM"
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="draft",
        server_default="draft",
        nullable=False,
        comment="状态",
    )
    total_batches: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="总批次"
    )
    completed_batches: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=0, comment="已完成批次"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")

    # 关系
    tasks: Mapped[list["PlanTask"]] = relationship(
        "PlanTask", back_populates="plan", lazy="selectin"
    )


class ProductionExecutionPlan(BaseModel):
    """交接业务中的车间日生产执行计划台账。"""

    __tablename__ = "production_execution_plans"
    __table_args__ = (
        Index("ix_production_execution_plans_workshop", "workshop"),
        Index("ix_production_execution_plans_product", "product_name"),
        Index("ix_production_execution_plans_date", "plan_date"),
        UniqueConstraint(
            "source",
            "source_record_id",
            name="uq_production_execution_plans_source_record",
        ),
        {"schema": "production"},
    )

    workshop: Mapped[str | None] = mapped_column(String(64), nullable=True)
    product_name: Mapped[str] = mapped_column(String(128), nullable=False)
    plan_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    planned_yield: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_completion: Mapped[float | None] = mapped_column(Float, nullable=True)
    completion_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    safety_status: Mapped[str | None] = mapped_column(String(128), nullable=True)
    quality_status: Mapped[str | None] = mapped_column(String(128), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual", server_default="manual"
    )
    source_record_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class PlanTask(BaseModel):
    """计划任务表"""

    __tablename__ = "plan_tasks"
    __table_args__ = {"schema": "production"}

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("production.production_plans.id"),
        nullable=False,
        comment="计划ID",
    )
    product_code: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="产品编码"
    )
    product_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="产品名称"
    )
    batch_qty: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="批次数量"
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity.users.id"),
        nullable=True,
        comment="负责人",
    )
    assigned_to_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="负责人姓名"
    )
    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="计划完成日期"
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        server_default="pending",
        nullable=False,
        comment="状态",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")

    # 关系
    plan: Mapped["ProductionPlan"] = relationship(
        "ProductionPlan", back_populates="tasks"
    )


class SalesPlanDetail(BaseModel):
    """产销计划中的销售执行明细。"""

    __tablename__ = "sales_plan_details"
    __table_args__ = (
        Index("ix_sales_plan_details_product", "product_name"),
        UniqueConstraint(
            "source",
            "source_record_id",
            name="uq_sales_plan_details_source_record",
        ),
        {"schema": "production"},
    )

    product_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="产品名称"
    )
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="单位")
    last_month_delivered_uninvoiced: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="上月已发货未开票"
    )
    current_year_delivered: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="当年当月发货量"
    )
    month_planned_delivery: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="本月计划发货量"
    )
    month_delivered_qty: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="本月已发货量"
    )
    undelivered_qty: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="未发货量"
    )
    month_planned_invoice: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="本月预计开票量"
    )
    invoiced_qty: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="已开票量"
    )
    delivery_completion_rate: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="本月发货完成率(%)"
    )
    last_month_end_inventory: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="上月底库存"
    )
    month_planned_capacity: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="本月预计产能"
    )
    month_end_inventory: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="本月底库存"
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="manual",
        server_default="manual",
        comment="数据来源",
    )
    source_record_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="来源系统记录标识"
    )


class ProductionFeishuReadSourceRoot(BaseModel):
    """生产模块的只读 Wiki/Base 入口，不参与原业务双向同步。"""

    __tablename__ = "feishu_read_source_roots"
    __table_args__ = (
        UniqueConstraint(
            "config_id",
            "source_type",
            "root_token",
            "is_deleted",
            name="uq_production_feishu_read_source_root",
        ),
        Index("ix_production_feishu_read_roots_config", "config_id", "is_active"),
        {"schema": "production"},
    )

    config_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    root_token: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    discovery_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    last_discovered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    discovery_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProductionFeishuReadResource(BaseModel):
    __tablename__ = "feishu_read_resources"
    __table_args__ = (
        UniqueConstraint(
            "app_token",
            "table_id",
            "is_deleted",
            name="uq_production_feishu_read_resource",
        ),
        Index("ix_production_feishu_read_resources_root", "source_root_id"),
        {"schema": "production"},
    )

    source_root_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    app_token: Mapped[str] = mapped_column(String(256), nullable=False)
    table_id: Mapped[str] = mapped_column(String(256), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_path: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    schema_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    active_mirror_version: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    last_complete_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sync_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProductionFeishuReadField(BaseModel):
    __tablename__ = "feishu_read_fields"
    __table_args__ = (
        UniqueConstraint(
            "resource_id",
            "field_id",
            "is_deleted",
            name="uq_production_feishu_read_field",
        ),
        Index("ix_production_feishu_read_fields_resource", "resource_id", "sort_order"),
        {"schema": "production"},
    )

    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    field_id: Mapped[str] = mapped_column(String(256), nullable=False)
    field_name: Mapped[str] = mapped_column(String(255), nullable=False)
    field_type: Mapped[str] = mapped_column(String(64), nullable=False)
    property: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )


class ProductionFeishuReadRecord(BaseModel):
    __tablename__ = "feishu_read_records"
    __table_args__ = (
        UniqueConstraint(
            "resource_id",
            "record_id",
            "mirror_version",
            name="uq_production_feishu_read_record_version",
        ),
        Index(
            "ix_production_feishu_read_records_page",
            "resource_id",
            "mirror_version",
            "record_id",
        ),
        {"schema": "production"},
    )

    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    record_id: Mapped[str] = mapped_column(String(256), nullable=False)
    mirror_version: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    raw_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    normalized_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    search_text: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    source_created_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_modified_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )


class ProductionFeishuReadPageBinding(BaseModel):
    __tablename__ = "feishu_read_page_bindings"
    __table_args__ = (
        UniqueConstraint(
            "page_key",
            "resource_id",
            "is_deleted",
            name="uq_production_feishu_read_page_binding",
        ),
        Index("ix_production_feishu_read_bindings_page", "page_key", "sort_order"),
        {"schema": "production"},
    )

    page_key: Mapped[str] = mapped_column(String(255), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tab_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    visible_field_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )


class ProductionFeishuReadSyncRun(BaseModel):
    __tablename__ = "feishu_read_sync_runs"
    __table_args__ = (
        Index("ix_production_feishu_read_runs_resource", "resource_id", "started_at"),
        {"schema": "production"},
    )

    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    mirror_version: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="running", server_default="running"
    )
    expected_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ProcessSpec(BaseModel):
    """工艺规程主表"""

    __tablename__ = "process_specs"
    __table_args__ = (
        UniqueConstraint("spec_code", "version", name="uq_process_specs_code_version"),
        {"schema": "production"},
    )

    spec_code: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="规程编号"
    )
    spec_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="规程名称"
    )
    product_code: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="产品编码"
    )
    product_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="产品名称"
    )
    version: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="1.0", comment="版本号"
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="draft",
        server_default="draft",
        nullable=False,
        comment="状态",
    )
    effective_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="生效日期"
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity.users.id"),
        nullable=True,
        comment="批准人",
    )
    approved_by_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="批准人姓名"
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="批准时间"
    )
    supersedes_version: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="替代版本"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")

    # 关系
    steps: Mapped[list["ProcessStep"]] = relationship(
        "ProcessStep", back_populates="spec", lazy="selectin"
    )


class ProcessStep(BaseModel):
    """工艺步骤表"""

    __tablename__ = "process_steps"
    __table_args__ = {"schema": "production"}

    spec_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("production.process_specs.id"),
        nullable=False,
        comment="规程ID",
    )
    step_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="步骤序号")
    step_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="步骤名称"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="步骤描述"
    )
    equipment_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="设备类型"
    )
    equipment_spec: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="设备规格"
    )
    duration_minutes: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="持续时间(分钟)"
    )
    sequence_order: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="排序顺序"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")

    # 关系
    spec: Mapped["ProcessSpec"] = relationship("ProcessSpec", back_populates="steps")
    parameters: Mapped[list["ProcessParameter"]] = relationship(
        "ProcessParameter", back_populates="step", lazy="selectin"
    )


class ProcessParameter(BaseModel):
    """工艺参数表"""

    __tablename__ = "process_parameters"
    __table_args__ = {"schema": "production"}

    step_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("production.process_steps.id"),
        nullable=False,
        comment="步骤ID",
    )
    param_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="参数名称"
    )
    param_code: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="参数编码"
    )
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="单位")
    min_value: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="最小值"
    )
    max_value: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="最大值"
    )
    target_value: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="目标值"
    )
    is_critical: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否关键参数"
    )
    data_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="数据类型:numeric/text/boolean"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")

    # 关系
    step: Mapped["ProcessStep"] = relationship(
        "ProcessStep", back_populates="parameters"
    )


class ProductionRecord(BaseModel):
    """生产记录表"""

    __tablename__ = "production_records"
    __table_args__ = (
        UniqueConstraint(
            "batch_id", "record_no", name="uq_production_records_batch_record"
        ),
        {"schema": "production"},
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("production.batches.id"),
        nullable=False,
        comment="批次ID",
    )
    record_no: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="记录编号"
    )
    step_no: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="步骤序号"
    )
    step_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="步骤名称"
    )
    operator: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity.users.id"),
        nullable=True,
        comment="操作人",
    )
    operator_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="操作人姓名"
    )
    operation_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="操作时间",
    )
    operation_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="操作类型",
    )
    parameters: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="参数JSON"
    )
    result: Mapped[str | None] = mapped_column(Text, nullable=True, comment="操作结果")
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")

    # 关系
    batch: Mapped["Batch"] = relationship("Batch", back_populates="records")


class MaterialBalance(BaseModel):
    """物料平衡表"""

    __tablename__ = "material_balances"
    __table_args__ = {"schema": "production"}

    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("production.batches.id"),
        nullable=False,
        unique=True,
        comment="批次ID",
    )
    input_qty: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="投入总量"
    )
    output_qty: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="产出总量"
    )
    loss_qty: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="损耗总量"
    )
    balance_rate: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="平衡率(%)"
    )
    min_balance_rate: Mapped[float] = mapped_column(
        Float, default=95.0, comment="最低平衡率(%)"
    )
    is_balanced: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否平衡"
    )
    deviation_rate: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="偏差率(%)"
    )
    calculated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="计算时间"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")

    # 关系
    batch: Mapped["Batch"] = relationship("Batch", back_populates="material_balance")


class ProductionFeishuConfig(BaseModel):
    """生产飞书配置"""

    __tablename__ = "feishu_configs"
    __table_args__ = (
        Index("ix_production_feishu_configs_is_active", "is_active"),
        {"schema": "production"},
    )

    config_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="生产飞书配置",
        comment="配置名称",
    )
    app_id: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="飞书应用 App ID"
    )
    encrypted_app_secret: Mapped[str] = mapped_column(
        String(1024), nullable=False, comment="加密后的飞书应用 App Secret"
    )
    bitable_app_token: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="飞书多维表格 app_token"
    )
    table_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="默认飞书多维表格数据表 table_id"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="是否启用",
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Asia/Shanghai",
        server_default="Asia/Shanghai",
    )
    daily_sync_time: Mapped[str] = mapped_column(
        String(5), nullable=False, default="02:00", server_default="02:00"
    )


class ProductionFeishuSyncBinding(BaseModel):
    """生产飞书同步绑定；仅保存经业务确认的同步目标与字段映射。"""

    __tablename__ = "feishu_sync_bindings"
    __table_args__ = (
        UniqueConstraint(
            "config_id",
            "sync_target",
            "table_id",
            name="uq_production_feishu_sync_bindings_target",
        ),
        Index("ix_production_feishu_sync_bindings_config", "config_id"),
        Index("ix_production_feishu_sync_bindings_active", "is_active"),
        {"schema": "production"},
    )

    config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, comment="生产飞书配置 ID（逻辑关联）"
    )
    binding_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="绑定名称"
    )
    sync_target: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="同步业务目标"
    )
    product_name: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="适用产品"
    )
    workshop_code: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="适用车间或生产线编码"
    )
    table_id: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="飞书多维表格数据表 ID"
    )
    field_mapping: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=dict, comment="平台字段到飞书字段的映射"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="是否允许进入同步队列",
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
    last_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="not_run",
        server_default="not_run",
        comment="最近一次同步状态",
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近一次同步时间"
    )
    last_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="最近一次同步错误摘要"
    )


class ProductionFeishuSyncRun(BaseModel):
    """生产飞书同步运行记录。"""

    __tablename__ = "feishu_sync_runs"
    __table_args__ = (
        Index("ix_production_feishu_sync_runs_binding", "binding_id"),
        Index("ix_production_feishu_sync_runs_started_at", "started_at"),
        {"schema": "production"},
    )

    binding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, comment="飞书同步绑定 ID（逻辑关联）"
    )
    run_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="运行模式：preview 或 execute"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="running", comment="运行状态"
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="本次请求幂等标识"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(), comment="开始时间"
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="完成时间"
    )
    created_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="新增数量"
    )
    updated_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="更新数量"
    )
    skipped_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="跳过数量"
    )
    failed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="失败数量"
    )
    error_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="错误摘要（不含凭据）"
    )


class ProcessExecutionRecord(BaseModel):
    """批次工序执行记录；以统一模型承载 203 车间 13 道工序。"""

    __tablename__ = "process_execution_records"
    __table_args__ = (
        Index("ix_process_execution_records_batch", "batch_no"),
        Index("ix_process_execution_records_process", "process_code"),
        Index("ix_process_execution_records_workshop", "workshop_code"),
        UniqueConstraint(
            "source",
            "process_code",
            "source_record_id",
            name="uq_process_execution_records_source",
        ),
        {"schema": "production"},
    )

    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="批次 ID（逻辑关联）"
    )
    batch_no: Mapped[str] = mapped_column(String(128), nullable=False, comment="批次号")
    workshop_code: Mapped[str] = mapped_column(
        String(32), nullable=False, default="203", server_default="203"
    )
    process_code: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="工序编码"
    )
    step_sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="工序顺序"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="draft", server_default="draft"
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, comment="工序业务字段"
    )
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual", server_default="manual"
    )
    source_record_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="来源记录标识"
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)


class FermentationRecord(BaseModel):
    """发酵批次记录。"""

    __tablename__ = "fermentation_records"
    __table_args__ = (
        Index("ix_fermentation_records_batch_no", "batch_no"),
        Index("ix_fermentation_records_product_name", "product_name"),
        UniqueConstraint(
            "source", "source_record_id", name="uq_fermentation_source_record"
        ),
        {"schema": "production"},
    )

    batch_no: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name: Mapped[str] = mapped_column(String(100), nullable=False)
    fermenter: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    discharge_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    cycle_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    tank_yield: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="in_progress", server_default="in_progress"
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachment: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual", server_default="manual"
    )
    source_record_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class SeedCultureRecord(BaseModel):
    """摇瓶种子制备记录；来源字段按业务分组保存在 JSONB 中。"""

    __tablename__ = "seed_culture_records"
    __table_args__ = (
        Index("ix_seed_culture_records_batch_no", "batch_no"),
        Index("ix_seed_culture_records_prepare_date", "prepare_date"),
        UniqueConstraint(
            "source", "source_record_id", name="uq_seed_culture_source_record"
        ),
        {"schema": "production"},
    )

    batch_no: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="", server_default=""
    )
    prepare_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    materials: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    quality_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    operation_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    tank_yield: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="in_progress", server_default="in_progress"
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual", server_default="manual"
    )
    source_record_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class NonConformingEvent(BaseModel):
    """非保密事件与运行偏差。"""

    __tablename__ = "non_conforming_events"
    __table_args__ = (
        Index("ix_nce_event_time", "event_time"),
        Index("ix_nce_workshop", "workshop"),
        Index("ix_nce_event_type", "event_type"),
        {"schema": "production"},
    )

    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    restore_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    impact_duration: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    workshop: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    impact_scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_taken: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="open", server_default="open"
    )
    related_batch_nos: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)


class ShiftLog(BaseModel):
    """生产班次运行摘要。"""

    __tablename__ = "shift_logs"
    __table_args__ = (
        Index("ix_shift_logs_date", "log_date"),
        Index("ix_shift_logs_workshop", "workshop"),
        {"schema": "production"},
    )

    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    shift: Mapped[str] = mapped_column(String(16), nullable=False)
    workshop: Mapped[str] = mapped_column(String(64), nullable=False)
    handover_from: Mapped[str] = mapped_column(String(64), nullable=False)
    handover_to: Mapped[str] = mapped_column(String(64), nullable=False)
    production_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    equipment_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    abnormal_events: Mapped[str | None] = mapped_column(Text, nullable=True)
    pending_tasks: Mapped[str | None] = mapped_column(Text, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)


class ShiftHandover(BaseModel):
    """班组交接及接班确认。"""

    __tablename__ = "shift_handovers"
    __table_args__ = (
        Index("ix_shift_handovers_handover_time", "handover_time"),
        Index("ix_shift_handovers_position", "position"),
        Index("ix_shift_handovers_workshop", "workshop"),
        {"schema": "production"},
    )

    position: Mapped[str] = mapped_column(String(64), nullable=False)
    workshop: Mapped[str] = mapped_column(String(64), nullable=False)
    shift: Mapped[str] = mapped_column(String(16), nullable=False)
    handover_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    handover_from: Mapped[str] = mapped_column(String(64), nullable=False)
    handover_to: Mapped[str] = mapped_column(String(64), nullable=False)
    production_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    equipment_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    equipment_inspection: Mapped[str | None] = mapped_column(Text, nullable=True)
    tools_handover: Mapped[str | None] = mapped_column(Text, nullable=True)
    fire_emergency: Mapped[str | None] = mapped_column(Text, nullable=True)
    ppe_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="确认人逻辑 ID"
    )


class ProductionMigrationRun(BaseModel):
    """生产历史数据导入运行批次。"""

    __tablename__ = "migration_runs"
    __table_args__ = (
        UniqueConstraint("run_key", name="uq_production_migration_runs_key"),
        Index("ix_production_migration_runs_status", "status"),
        {"schema": "production"},
    )

    run_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    input_counts: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    report: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    rollback_of: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )


class ProductionMigrationRecordMap(BaseModel):
    """来源记录到平台记录的稳定映射。"""

    __tablename__ = "migration_record_maps"
    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "entity",
            "source_record_id",
            name="uq_production_migration_record_map",
        ),
        Index(
            "ix_production_migration_record_maps_target", "target_table", "target_id"
        ),
        {"schema": "production"},
    )

    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    entity: Mapped[str] = mapped_column(String(64), nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(128), nullable=False)
    target_table: Mapped[str] = mapped_column(String(128), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    last_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


class ProductionMigrationChange(BaseModel):
    """单次导入的可逆变更日志。"""

    __tablename__ = "migration_changes"
    __table_args__ = (
        Index("ix_production_migration_changes_run", "run_id"),
        {"schema": "production"},
    )

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    map_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    entity: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    before_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    before_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    after_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    rolled_back_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class LabelVerification(BaseModel):
    """标签复核记录表"""

    __tablename__ = "label_verifications"
    __table_args__ = ({"schema": "production"},)

    # 基础信息
    batch_number: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="批号，如 QS32603006"
    )
    product_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="产品名称"
    )
    production_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="生产日期"
    )
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False, comment="有效期至")

    # 桶数与重量信息
    total_barrels: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="总桶数"
    )
    standard_barrels: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="整桶数"
    )
    remainder_barrel: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="零头桶数（0或1）"
    )
    standard_weight: Mapped[float] = mapped_column(
        Float, nullable=False, comment="整桶重量（kg）"
    )
    remainder_weight: Mapped[float] = mapped_column(
        Float, nullable=False, comment="零头重量（kg）"
    )
    total_weight: Mapped[float] = mapped_column(
        Float, nullable=False, comment="总重量（kg）"
    )

    # 8项结论状态（True=一致，False=不一致）
    check_batch_number: Mapped[bool] = mapped_column(
        Boolean, nullable=False, comment="批号对比结果"
    )
    check_production_date: Mapped[bool] = mapped_column(
        Boolean, nullable=False, comment="生产日期对比结果"
    )
    check_expiry_date: Mapped[bool] = mapped_column(
        Boolean, nullable=False, comment="有效期至对比结果"
    )
    check_standard_barrels: Mapped[bool] = mapped_column(
        Boolean, nullable=False, comment="整桶信息对比结果"
    )
    check_remainder_barrel: Mapped[bool] = mapped_column(
        Boolean, nullable=False, comment="零头信息对比结果"
    )
    check_total_weight: Mapped[bool] = mapped_column(
        Boolean, nullable=False, comment="总重量对比结果"
    )
    check_all_barrels_identified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, comment="是否识别到每一桶"
    )
    check_exception_handled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, comment="异常处理结果"
    )

    # 总体结论
    result_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="全部一致",
        server_default="全部一致",
        comment="总体结论：全部一致/存在差异",
    )
    result_summary: Mapped[str] = mapped_column(
        Text, nullable=False, comment="结论摘要，如 ✅✅✅ 全部一致"
    )

    # 视频来源信息
    video_file_key: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="视频文件 key（用于去重）"
    )
    video_file_name: Mapped[str] = mapped_column(
        String(256), nullable=True, comment="视频文件名"
    )
    video_frame_count: Mapped[int] = mapped_column(
        Integer, nullable=True, comment="提取帧数"
    )
    video_fps: Mapped[float] = mapped_column(
        Float, nullable=True, comment="帧率（2.0 或 3.0）"
    )

    # 复核时间
    verification_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="复核日期"
    )
    verification_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="复核时间"
    )

    # 备注
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
