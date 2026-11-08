"""8 大特殊作业票的请求 / 响应模型。

票面差异字段（type_data）按票种以「字段模板 + 动态校验」承接：
创建/更新时由 service.work_permit_templates.type_fields_for(permit_type)
的字段清单校验 key 合法性与必填项，避免为 8 种票各写一套 Pydantic 模型。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.safety.schemas.enums import OperationType


class PermitPersonInput(BaseModel):
    """作业相关人员（可携带证件引用，保存证件快照）。"""

    role: str = Field(max_length=32, description="角色（模板 person_roles）")
    name: str = Field(min_length=1, max_length=100, description="姓名")
    user_id: UUID | None = Field(default=None, description="平台账号")
    certificate_id: UUID | None = Field(
        default=None, description="关联证件（special_work_certificates）"
    )
    certificate_no: str | None = Field(default=None, max_length=100)
    certificate_category: str | None = Field(default=None, max_length=64)


class PermitMeasureInput(BaseModel):
    """安全措施勾选（key 对应票面措施模板）。"""

    key: str = Field(max_length=64)
    status: str = Field(pattern="^(yes|not_applicable)$")
    fills: dict[str, str] = Field(default_factory=dict)


class WorkPermitCreate(BaseModel):
    permit_type: OperationType
    permit_level: str = Field(default="none", max_length=16)
    apply_department: str | None = Field(default=None, max_length=100)
    apply_time: datetime | None = None
    work_description: str | None = Field(default=None, max_length=8000)
    work_location: str | None = Field(default=None, max_length=255)
    work_unit: str | None = Field(default=None, max_length=100)
    planned_start_time: datetime | None = None
    planned_end_time: datetime | None = None
    persons: list[PermitPersonInput] = Field(default_factory=list)
    risk_identifications: list[str] = Field(default_factory=list)
    safety_measures: list[PermitMeasureInput] = Field(default_factory=list)
    type_data: dict[str, object] = Field(default_factory=dict)
    related_legacy_no_text: str | None = Field(default=None, max_length=500)
    remark: str | None = Field(default=None, max_length=2000)


class WorkPermitUpdate(BaseModel):
    """草稿/驳回态编辑（字段全部可空，仅提交的非空项生效）。"""

    permit_level: str | None = Field(default=None, max_length=16)
    apply_department: str | None = Field(default=None, max_length=100)
    apply_time: datetime | None = None
    work_description: str | None = Field(default=None, max_length=8000)
    work_location: str | None = Field(default=None, max_length=255)
    work_unit: str | None = Field(default=None, max_length=100)
    planned_start_time: datetime | None = None
    planned_end_time: datetime | None = None
    persons: list[PermitPersonInput] | None = None
    risk_identifications: list[str] | None = None
    safety_measures: list[PermitMeasureInput] | None = None
    type_data: dict[str, object] | None = None
    related_legacy_no_text: str | None = Field(default=None, max_length=500)
    remark: str | None = Field(default=None, max_length=2000)


class NodeAssignmentInput(BaseModel):
    """提交时为节点改派审批人（缺省用默认配置）。"""

    node_key: str = Field(max_length=64)
    approver_user_id: UUID | None = None


class WorkPermitSubmitInput(BaseModel):
    assignments: list[NodeAssignmentInput] = Field(default_factory=list)


class WorkPermitRejectInput(BaseModel):
    opinion: str = Field(min_length=1, max_length=2000, description="驳回意见")


class PermitNodeActionInput(BaseModel):
    opinion: str | None = Field(default=None, max_length=2000)


class AcceptPermitInput(BaseModel):
    """完工验收（临时用电拆线确认字段随 type_data 提交）。"""

    type_data: dict[str, object] = Field(default_factory=dict)


class GasAnalysisItemInput(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="项目名称")
    standard: str | None = Field(default=None, max_length=100, description="合格标准")
    value: str | None = Field(default=None, max_length=100, description="分析结果")
    unit: str | None = Field(default=None, max_length=32)


class GasAnalysisCreate(BaseModel):
    phase: str = Field(default="pre_work", pattern="^(pre_work|on_duty)$")
    sampled_at: datetime
    analysis_point: str | None = Field(default=None, max_length=255)
    items: list[GasAnalysisItemInput] = Field(default_factory=list)
    oxygen_value: str | None = Field(default=None, max_length=32)
    analyst_name: str | None = Field(default=None, max_length=100)
    remark: str | None = Field(default=None, max_length=2000)


class WorkPermitRelationInput(BaseModel):
    related_permit_id: UUID


# ── 响应模型 ──


class PermitPersonItem(PermitPersonInput):
    """含证件有效性提示（service 计算后附上）。"""

    certificate_valid: bool | None = Field(
        default=None, description="证件有效性（None=未关联证件）"
    )
    certificate_status: str | None = Field(default=None, max_length=16)


class PermitMeasureItem(PermitMeasureInput):
    pass


class WorkPermitNodeItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    round: int
    seq: int
    node_key: str
    node_name: str
    node_kind: str
    status: str
    assigned_approver_id: UUID | None = None
    assigned_approver_name: str | None = None
    acted_by: UUID | None = None
    acted_by_name: str | None = None
    acted_at: datetime | None = None
    opinion: str | None = None


class GasAnalysisItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    phase: str
    sampled_at: datetime
    analysis_point: str | None = None
    items: list[dict[str, object]] = Field(default_factory=list)
    oxygen_value: str | None = None
    analyst_name: str | None = None
    remark: str | None = None


class PermitRelationItem(BaseModel):
    related_permit_id: UUID
    related_permit_no: str
    related_permit_type: str
    related_permit_status: str


class WorkPermitAttachmentItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category: str
    file_name: str
    content_type: str | None = None
    size_bytes: int


class WorkPermitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    permit_no: str
    permit_type: str
    permit_level: str
    status: str
    apply_department: str | None = None
    apply_time: datetime | None = None
    work_description: str | None = None
    work_location: str | None = None
    work_unit: str | None = None
    planned_start_time: datetime | None = None
    planned_end_time: datetime | None = None
    actual_start_time: datetime | None = None
    actual_end_time: datetime | None = None
    persons: list[PermitPersonItem] = Field(default_factory=list)
    risk_identifications: list[str] = Field(default_factory=list)
    safety_measures: list[PermitMeasureItem] = Field(default_factory=list)
    type_data: dict[str, object] = Field(default_factory=dict)
    related_legacy_no_text: str | None = None
    current_node_seq: int
    approval_round: int
    reject_opinion: str | None = None
    remark: str | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class WorkPermitDetailResponse(WorkPermitResponse):
    """详情：附审批节点时间线、气体分析、关联票与附件。"""

    nodes: list[WorkPermitNodeItem] = Field(default_factory=list)
    gas_analyses: list[GasAnalysisItem] = Field(default_factory=list)
    relations: list[PermitRelationItem] = Field(default_factory=list)
    attachments: list[WorkPermitAttachmentItem] = Field(default_factory=list)
    next_gas_due_at: datetime | None = Field(
        default=None,
        description="下次气体复检到期时间（无周期复检要求为 None）",
    )
    gas_overdue: bool = Field(default=False, description="复检是否已超期")


class WorkPermitListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    permit_no: str
    permit_type: str
    permit_level: str
    status: str
    apply_department: str | None = None
    apply_time: datetime | None = None
    work_description: str | None = None
    work_location: str | None = None
    work_unit: str | None = None
    planned_start_time: datetime | None = None
    planned_end_time: datetime | None = None
    approval_round: int
    current_node_seq: int
    created_at: datetime
    updated_at: datetime


class WorkPermitListResponse(BaseModel):
    items: list[WorkPermitListItem]
    total: int
    page: int
    page_size: int


class WorkPermitStatsResponse(BaseModel):
    """列表页统计：按状态计数 + 待我审批数。"""

    total: int = 0
    draft: int = 0
    pending_approval: int = 0
    approved: int = 0
    active: int = 0
    completed: int = 0
    rejected: int = 0
    cancelled: int = 0
    my_pending_approvals: int = Field(
        default=0, description="待当前用户审批的节点数"
    )


class ApproverConfigItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    permit_type: str
    node_key: str
    node_name: str
    approver_user_id: UUID | None = None
    approver_user_name: str | None = None
    remark: str | None = None


class ApproverConfigUpsertInput(BaseModel):
    permit_type: OperationType
    node_key: str = Field(max_length=64)
    approver_user_id: UUID | None = None
    remark: str | None = Field(default=None, max_length=500)


class ApproverConfigListResponse(BaseModel):
    items: list[ApproverConfigItem]


class WorkPermitMetaResponse(BaseModel):
    """前端渲染表单/详情所需的模板元数据。"""

    permit_types: list[dict[str, str]]
    level_options: dict[str, list[dict[str, str]]]
    person_roles: dict[str, list[dict[str, object]]]
    measures: dict[str, list[dict[str, object]]]
    type_fields: dict[str, list[dict[str, object]]]
    nodes: dict[str, list[dict[str, object]]] = Field(
        default_factory=dict,
        description="票种节点目录（key/name/kind/levels），提交审批指派用",
    )
    risk_identification_options: list[str]
    gas_types: list[str] = Field(
        default_factory=list, description="需要气体分析的票种"
    )
    gas_cycle_minutes: dict[str, int] = Field(
        default_factory=dict, description="作业期间复检间隔（分钟）"
    )
    certificate_categories: list[dict[str, str]]


class ActionResponse(BaseModel):
    """通用操作响应（提交/审批/驳回/验票/验收/关联等）。"""

    permit_id: UUID
    permit_no: str
    status: str
    current_node_seq: int = 0
    message: str = ""
    warnings: list[str] = Field(
        default_factory=list,
        description="提交时的人员证件软校验提示（仅提交动作返回）",
    )


class WorkPermitSettingsResponse(BaseModel):
    """作业票运行参数（work_permit_settings 键值子集）。"""

    cert_check_strict: bool = Field(
        default=False,
        description="提交时人员证件校验：False=软提示，True=未通过拦截",
    )


class WorkPermitSettingsUpdate(BaseModel):
    cert_check_strict: bool
