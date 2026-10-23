"""Safety request and response schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ── 风险等级常量 ──
RISK_LEVELS: list[dict[str, Any]] = [
    {
        "key": "level_1",
        "label": "一级/重大风险",
        "min_d": 320,
        "max_d": 99999,
        "color": "red",
        "control_level": "公司级",
        "responsible_person": "公司主要负责人",
        "requirement": "必须建立管控档案，立即整改，风险降低后方可作业",
    },
    {
        "key": "level_2",
        "label": "二级/较大风险",
        "min_d": 160,
        "max_d": 319,
        "color": "orange",
        "control_level": "部门级",
        "responsible_person": "安全工程中心 + 各部门按职责分工",
        "requirement": "必须建立管控档案，制定措施控制管理",
    },
    {
        "key": "level_3",
        "label": "三级/一般风险",
        "min_d": 70,
        "max_d": 159,
        "color": "yellow",
        "control_level": "班组/岗位级",
        "responsible_person": "所在部门负责管控",
        "requirement": "安全工程中心监督落实",
    },
    {
        "key": "level_4",
        "label": "四级/低风险",
        "min_d": 0,
        "max_d": 69,
        "color": "blue",
        "control_level": "班组/岗位级",
        "responsible_person": "所在班组/岗位负责管控",
        "requirement": "部门安全员监督落实",
    },
]


def get_risk_level(d_value: float) -> dict[str, Any]:
    """根据 D 值获取风险等级"""
    for level in RISK_LEVELS:
        if level["min_d"] <= d_value <= level["max_d"]:
            return level
    return RISK_LEVELS[-1]


AI_NODE_PROGRESS_OPTIONS = [
    {"value": "pending_input", "label": "待填写基础信息"},
    {"value": "pending_script1", "label": "待AI解析附件"},
    {"value": "pending_script2", "label": "待AI危险源辨识"},
    {"value": "pending_script3", "label": "待AI固有风险评价"},
    {"value": "pending_script4", "label": "待AI输入现有控制措施"},
    {"value": "pending_script5", "label": "待AI评价残余风险"},
    {"value": "pending_script6", "label": "待AI提出建议措施"},
    {"value": "pending_script7", "label": "待AI评价建议措施后风险"},
    {"value": "completed", "label": "AI流程结束"},
]

REVIEW_STATUS_OPTIONS = [
    {"value": "pending", "label": "待审核"},
    {"value": "approved", "label": "已审核"},
    {"value": "rejected", "label": "已驳回"},
]

OVERALL_STATUS_OPTIONS = [
    {"value": "draft", "label": "草稿"},
    {"value": "in_progress", "label": "进行中"},
    {"value": "completed", "label": "已完成"},
    {"value": "cancelled", "label": "已取消"},
]


class HazardIdentificationBase(BaseModel):
    """危险源辨识基础模式"""

    hazard_id_no: str = Field(..., max_length=64, description="危险源编号")
    department: str = Field(..., max_length=100, description="部门")
    position: str = Field(..., max_length=100, description="岗位")
    production_step: str = Field(..., description="生产步骤")
    notes: str | None = Field(None, description="备注")


class HazardIdentificationCreate(HazardIdentificationBase):
    """创建危险源辨识记录"""

    pass


class HazardIdentificationUpdate(BaseModel):
    """更新危险源辨识记录（人工编辑字段）"""

    hazard_id_no: str | None = Field(None, max_length=64)
    department: str | None = Field(None, max_length=100)
    position: str | None = Field(None, max_length=100)
    production_step: str | None = None
    notes: str | None = None
    specific_activity: str | None = None
    equipment_facilities: str | None = None
    raw_auxiliary_materials: str | None = None
    operation_frequency: str | None = None
    operator_count: int | None = None
    hazard_type: str | None = None
    possible_accident: str | None = None
    unsafe_behavior: str | None = None
    l_inherent: float | None = None
    e_inherent: float | None = None
    c_inherent: float | None = None
    d_inherent: float | None = None
    inherent_risk_level: str | None = None
    inherent_risk_label: str | None = None
    existing_engineering_controls: str | None = None
    existing_management_controls: str | None = None
    existing_ppe: str | None = None
    existing_emergency_measures: str | None = None
    l_residual: float | None = None
    e_residual: float | None = None
    c_residual: float | None = None
    d_residual: float | None = None
    residual_risk_level: str | None = None
    residual_risk_label: str | None = None
    needs_recommendation: str | None = None
    recommendation_type: str | None = None
    recommendation_content: str | None = None
    recommendation_priority: str | None = None
    l_post: float | None = None
    e_post: float | None = None
    c_post: float | None = None
    d_post: float | None = None
    post_risk_level: str | None = None
    post_risk_label: str | None = None
    control_level: str | None = Field(None, max_length=50)
    responsible_person: str | None = Field(None, max_length=100)
    tense: str | None = Field(None, max_length=50)
    state: str | None = Field(None, max_length=50)
    responsible_unit: str | None = Field(None, max_length=100)
    check_frequency: str | None = Field(None, max_length=100)
    check_standard: str | None = None
    is_major_hazard: str | None = Field(None, max_length=10)


class HazardIdentificationReview(BaseModel):
    """审核请求"""

    script_number: int = Field(..., ge=1, le=7, description="脚本编号(1-7)")
    action: str = Field(..., description="审核动作: approved/rejected")


class HazardIdentificationRunScript(BaseModel):
    """触发脚本执行请求"""

    script_number: int = Field(..., ge=1, le=7, description="脚本编号(1-7)")
    ai_output: dict[str, Any] | None = Field(None, description="AI 输出内容")


class HazardIdentificationResponse(HazardIdentificationBase):
    """危险源辨识完整响应"""

    id: uuid.UUID
    attachment_path: str | None = None
    attachment_original_name: str | None = None
    specific_activity: str | None = None
    equipment_facilities: str | None = None
    raw_auxiliary_materials: str | None = None
    operation_frequency: str | None = None
    operator_count: int | None = None
    hazard_type: str | None = None
    possible_accident: str | None = None
    unsafe_behavior: str | None = None
    l_inherent: float | None = None
    e_inherent: float | None = None
    c_inherent: float | None = None
    d_inherent: float | None = None
    inherent_risk_level: str | None = None
    inherent_risk_label: str | None = None
    existing_engineering_controls: str | None = None
    existing_management_controls: str | None = None
    existing_ppe: str | None = None
    existing_emergency_measures: str | None = None
    l_residual: float | None = None
    e_residual: float | None = None
    c_residual: float | None = None
    d_residual: float | None = None
    residual_risk_level: str | None = None
    residual_risk_label: str | None = None
    needs_recommendation: str | None = None
    recommendation_type: str | None = None
    recommendation_content: str | None = None
    recommendation_priority: str | None = None
    l_post: float | None = None
    e_post: float | None = None
    c_post: float | None = None
    d_post: float | None = None
    post_risk_level: str | None = None
    post_risk_label: str | None = None
    control_level: str | None = None
    responsible_person: str | None = None
    tense: str | None = None
    state: str | None = None
    responsible_unit: str | None = None
    check_frequency: str | None = None
    check_standard: str | None = None
    is_major_hazard: str | None = None
    ai_node_progress: str
    ai_error_message: str | None = None
    overall_status: str
    script1_review_status: str
    script2_review_status: str
    script3_review_status: str
    script4_review_status: str
    script5_review_status: str
    script6_review_status: str
    script7_review_status: str
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── 危险源辨识台账 Excel 导入 ──


class HazardPositionOption(BaseModel):
    """部门-岗位组合选项。"""

    department: str
    position: str


class HazardFilterOptions(BaseModel):
    """台账筛选下拉选项。"""

    departments: list[str] = Field(default_factory=list)
    positions: list[HazardPositionOption] = Field(default_factory=list)


class HazardImportSampleRow(BaseModel):
    """导入预览中的样例行。"""

    name: str | None = None
    step: str | None = None
    hazard_desc: str | None = None
    accident: str | None = None
    l_value: float | None = Field(None, alias="l")
    e: float | None = None
    c: float | None = None
    d: float | None = None
    level: str | None = None
    engineering: str | None = None


class HazardImportSheetInfo(BaseModel):
    """导入预览中的子表（sheet）解析结果。"""

    name: str
    format: str | None = None
    format_label: str | None = None
    row_count: int = 0
    skipped: bool = False
    skip_reason: str | None = None
    sample_rows: list[HazardImportSampleRow] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)


class HazardImportPreview(BaseModel):
    """工作簿解析预览。"""

    filename: str
    department_guess: str = ""
    sheets: list[HazardImportSheetInfo] = Field(default_factory=list)
    total_valid_rows: int = 0


class HazardImportResult(BaseModel):
    """导入落库结果。"""

    imported: int = 0
    skipped_existing: int = 0
    duplicate_in_file: int = 0
    failed_sheets: list[dict[str, Any]] = Field(default_factory=list)
    row_errors: list[dict[str, Any]] = Field(default_factory=list)
    archive_path: str | None = None
