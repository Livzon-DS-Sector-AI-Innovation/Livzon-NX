"""目标责任与绩效的请求 / 响应模型。"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SafetyTargetCreate(BaseModel):
    year: int = Field(ge=2000, le=2100, description="目标年度")
    title: str = Field(min_length=1, max_length=200, description="目标名称")
    category: str = Field(default="事故控制", max_length=40, description="目标类别")
    metric: str = Field(default="", max_length=200, description="考核指标说明")
    target_value: str = Field(default="", max_length=100, description="目标值")
    unit: str = Field(default="", max_length=30, description="计量单位")
    owner_department: str = Field(default="", max_length=100, description="责任部门")
    owner_name: str = Field(default="", max_length=60, description="责任人")
    deadline: date | None = Field(default=None, description="完成时限")
    status: str = Field(
        default="in_progress",
        max_length=20,
        description="状态: in_progress/achieved/not_achieved",
    )
    remark: str = Field(default="", max_length=8000, description="备注")


class SafetyTargetUpdate(BaseModel):
    year: int | None = Field(default=None, ge=2000, le=2100)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=40)
    metric: str | None = Field(default=None, max_length=200)
    target_value: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, max_length=30)
    owner_department: str | None = Field(default=None, max_length=100)
    owner_name: str | None = Field(default=None, max_length=60)
    deadline: date | None = None
    status: str | None = Field(default=None, max_length=20)
    remark: str | None = Field(default=None, max_length=8000)


class SafetyTargetRecordCreate(BaseModel):
    period: str = Field(
        min_length=1, max_length=20, description="考核期（如 2026-Q1、2026-03）"
    )
    actual_value: str = Field(default="", max_length=100, description="实际完成值")
    completion_pct: float | None = Field(
        default=None, ge=0, le=1000, description="完成率（%）"
    )
    note: str = Field(default="", max_length=8000, description="情况说明")


class SafetyTargetRecordUpdate(BaseModel):
    actual_value: str | None = Field(default=None, max_length=100)
    completion_pct: float | None = Field(default=None, ge=0, le=1000)
    note: str | None = Field(default=None, max_length=8000)


class SafetyTargetRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    target_id: UUID
    period: str
    actual_value: str
    completion_pct: float | None = None
    note: str
    created_at: datetime
    updated_at: datetime


class SafetyTargetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    year: int
    title: str
    category: str
    metric: str
    target_value: str
    unit: str
    owner_department: str
    owner_name: str
    deadline: date | None = None
    status: str
    remark: str
    records: list[SafetyTargetRecordResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class SafetyTargetListResponse(BaseModel):
    items: list[SafetyTargetResponse]
    total: int
    page: int
    page_size: int


class SafetyTargetDepartmentStat(BaseModel):
    department: str
    total: int
    achieved: int
    not_achieved: int
    in_progress: int


class SafetyTargetStatsResponse(BaseModel):
    total: int
    achieved: int
    in_progress: int
    not_achieved: int
    categories: list[str] = Field(default_factory=list)
    departments: list[SafetyTargetDepartmentStat] = Field(default_factory=list)


# ==================== 安全目标责任书 ====================

AGREEMENT_STATUS_VALUES = ("unsigned", "signed")
AGREEMENT_CATEGORY_VALUES = ("公司领导", "部门/车间负责人", "岗位员工")


class SafetyTargetAgreementCreate(BaseModel):
    year: int = Field(ge=2000, le=2100, description="签订年度")
    department: str = Field(min_length=1, max_length=100, description="责任部门/单位")
    position: str = Field(min_length=1, max_length=100, description="岗位/角色")
    category: str = Field(default="岗位员工", max_length=30, description="分类")
    party_a: str = Field(default="", max_length=60, description="甲方（考核方代表）")
    party_b: str = Field(default="", max_length=60, description="乙方（责任方签订人）")
    status: str = Field(
        default="unsigned", max_length=20, description="状态: unsigned/signed"
    )
    signed_date: date | None = Field(default=None, description="签订日期")
    expires_date: date | None = Field(default=None, description="有效期至")
    goals_text: str = Field(
        default="", max_length=20000, description="目标条款（每行一条）"
    )
    remark: str = Field(default="", max_length=8000, description="备注")


class SafetyTargetAgreementUpdate(BaseModel):
    year: int | None = Field(default=None, ge=2000, le=2100)
    department: str | None = Field(default=None, min_length=1, max_length=100)
    position: str | None = Field(default=None, min_length=1, max_length=100)
    category: str | None = Field(default=None, max_length=30)
    party_a: str | None = Field(default=None, max_length=60)
    party_b: str | None = Field(default=None, max_length=60)
    status: str | None = Field(default=None, max_length=20)
    signed_date: date | None = None
    expires_date: date | None = None
    goals_text: str | None = Field(default=None, max_length=20000)
    remark: str | None = Field(default=None, max_length=8000)


class SafetyTargetAgreementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    year: int
    department: str
    position: str
    category: str
    party_a: str
    party_b: str
    status: str
    signed_date: date | None = None
    expires_date: date | None = None
    goals_text: str
    remark: str
    created_at: datetime
    updated_at: datetime


class SafetyTargetAgreementListResponse(BaseModel):
    items: list[SafetyTargetAgreementResponse]
    total: int
    page: int
    page_size: int


class SafetyTargetAgreementDepartmentStat(BaseModel):
    department: str
    total: int
    signed: int


class SafetyTargetAgreementStatsResponse(BaseModel):
    total: int
    signed: int
    unsigned: int
    sign_rate: float = Field(description="签订率（%）")
    departments: list[SafetyTargetAgreementDepartmentStat] = Field(default_factory=list)


# ==================== 安全生产责任制考核 ====================

DUTY_GRADE_EXCELLENT = "优秀"
DUTY_GRADE_GOOD = "良好"
DUTY_GRADE_QUALIFIED = "合格"
DUTY_GRADE_UNQUALIFIED = "不合格"


class SafetyDutyAssessmentItemInput(BaseModel):
    content: str = Field(min_length=1, max_length=2000, description="考核内容")
    rule: str = Field(default="", max_length=2000, description="考核标准/扣分规则")
    standard_score: float = Field(default=0, ge=0, le=1000, description="标准分")
    deduction_score: float = Field(default=0, ge=0, le=1000, description="扣减分")
    score: float | None = Field(
        default=None, ge=0, le=1000, description="考核得分（缺省=标准分-扣减分）"
    )
    remark: str = Field(default="", max_length=2000, description="考核明细说明")


class SafetyDutyAssessmentCreate(BaseModel):
    year: int = Field(ge=2000, le=2100, description="考核年度")
    quarter: int = Field(ge=1, le=4, description="考核季度 1-4")
    department: str = Field(min_length=1, max_length=100, description="被考核部门/单位")
    person_name: str = Field(default="", max_length=100, description="被考核人")
    assessor: str = Field(default="", max_length=100, description="考核单位")
    assessment_date: date | None = Field(default=None, description="考核日期")
    items: list[SafetyDutyAssessmentItemInput] = Field(
        default_factory=list, max_length=100, description="评分明细"
    )
    remark: str = Field(default="", max_length=8000, description="备注")


class SafetyDutyAssessmentUpdate(BaseModel):
    year: int | None = Field(default=None, ge=2000, le=2100)
    quarter: int | None = Field(default=None, ge=1, le=4)
    department: str | None = Field(default=None, min_length=1, max_length=100)
    person_name: str | None = Field(default=None, max_length=100)
    assessor: str | None = Field(default=None, max_length=100)
    assessment_date: date | None = None
    items: list[SafetyDutyAssessmentItemInput] | None = Field(
        default=None, max_length=100, description="提供时整体替换评分明细"
    )
    remark: str | None = Field(default=None, max_length=8000)


class SafetyDutyAssessmentItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    assessment_id: UUID
    sort_order: int
    content: str
    rule: str
    standard_score: float
    deduction_score: float
    score: float
    remark: str


class SafetyDutyAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    year: int
    quarter: int
    department: str
    person_name: str
    assessor: str
    assessment_date: date | None = None
    total_score: float
    grade: str
    remark: str
    items: list[SafetyDutyAssessmentItemResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class SafetyDutyAssessmentListResponse(BaseModel):
    items: list[SafetyDutyAssessmentResponse]
    total: int
    page: int
    page_size: int


class SafetyDutyAssessmentQuarterStat(BaseModel):
    quarter: int
    count: int
    avg_score: float


class SafetyDutyAssessmentDepartmentStat(BaseModel):
    department: str
    count: int
    avg_score: float


class SafetyDutyAssessmentStatsResponse(BaseModel):
    total: int
    avg_score: float
    excellent: int = Field(description="优秀数（>=95）")
    good: int = Field(description="良好数（>=90）")
    qualified: int = Field(description="合格数（>=80）")
    unqualified: int = Field(description="不合格数（<80）")
    quarters: list[SafetyDutyAssessmentQuarterStat] = Field(default_factory=list)
    departments: list[SafetyDutyAssessmentDepartmentStat] = Field(default_factory=list)


class SafetyDutyTemplateItem(BaseModel):
    content: str
    rule: str = ""
    standard_score: float


class SafetyDutyTemplateResponse(BaseModel):
    name: str
    category: str
    assessed: str = ""
    items: list[SafetyDutyTemplateItem] = Field(default_factory=list)
    matched: bool = Field(
        default=False, description="是否按部门匹配到模板（未匹配返回通用空模板）"
    )


# ==================== Excel 批量导入 ====================


class SafetyImportErrorItem(BaseModel):
    row: int | str = Field(description="出错行号（责任书）或 sheet 名（考核）")
    target: str = Field(default="", description="出错对象（部门/岗位）")
    message: str


class SafetyAgreementImportResultResponse(BaseModel):
    updated: int = Field(description="更新（登记签订）条数")
    created: int = Field(description="新建条数")
    errors: list[SafetyImportErrorItem] = Field(default_factory=list)


class SafetyDutyAssessmentImportResultResponse(BaseModel):
    imported: int = Field(description="新建考核条数")
    updated: int = Field(description="覆盖更新考核条数")
    skipped_sheets: list[str] = Field(
        default_factory=list, description="未导入的 sheet（未填扣减分或无法识别）"
    )
    errors: list[SafetyImportErrorItem] = Field(default_factory=list)
