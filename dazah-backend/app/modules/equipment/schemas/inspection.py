"""Inspection schemas."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ── 枚举 ──
InspectionTaskStatus = Literal["待执行", "执行中", "已完成", "已关闭"]
InspectionPlanType = Literal["线路巡检", "设备巡检"]
InspectionOverallResult = Literal["正常", "异常"]
CheckResult = Literal["正常", "异常", "跳过"]


# ═══════════ 巡检任务 ═══════════
class InspectionTaskCreate(BaseModel):
    """创建巡检任务请求"""

    equipment_id: uuid.UUID | None = Field(
        default=None, description="单设备ID（兼容旧版，推荐用 equipment_ids）"
    )
    equipment_ids: list[uuid.UUID] | None = Field(
        default=None, min_length=1, description="设备ID列表（多设备模式）"
    )
    template_ids: list[uuid.UUID] | None = Field(
        default=None,
        min_length=1,
        description="[DEPRECATED] 模板ID列表，推荐用 equipment_templates",
    )
    equipment_templates: dict[str, list[uuid.UUID]] | None = Field(
        default=None,
        description="设备-模板映射（设备巡检用）: {equipment_id: [template_id, ...]}",
    )
    plan_type: InspectionPlanType = Field(default="设备巡检", description="巡检类型")
    assigned_to: uuid.UUID | None = Field(default=None, description="巡检人员ID")
    planned_time: datetime = Field(..., description="计划巡检时间")


class InspectionTaskUpdate(BaseModel):
    """更新巡检任务请求"""

    assigned_to: uuid.UUID | None = Field(default=None)
    planned_time: datetime | None = Field(default=None)


class InspectionTaskClose(BaseModel):
    """关闭任务请求"""

    closure_remark: str | None = Field(default=None, description="关闭备注")


class InspectionTaskResponse(BaseModel):
    """巡检任务响应"""

    id: uuid.UUID
    task_no: str
    equipment_id: uuid.UUID | None
    equipment_ids: list[uuid.UUID] | None = None
    template_ids: list[uuid.UUID] | None = None
    equipment_templates: dict[str, list[uuid.UUID]] | None = None
    plan_type: InspectionPlanType
    assigned_to: uuid.UUID | None
    planned_time: datetime
    status: InspectionTaskStatus
    overall_result: InspectionOverallResult | None
    started_at: datetime | None
    completed_at: datetime | None
    closed_at: datetime | None
    closure_remark: str | None
    created_at: datetime
    updated_at: datetime
    equipment_name: str | None = None
    equipment_no: str | None = None
    assignee_name: str | None = None
    equipment_count: int = 0
    completed_count: int = 0
    completed_equipment_ids: list[uuid.UUID] = []
    photo_count: int = 0

    model_config = {"from_attributes": True}


# ═══════════ 巡检执行 ═══════════
class InspectionRecordItem(BaseModel):
    """单条检查项结果"""

    template_item_id: uuid.UUID = Field(..., description="检查项ID")
    result: CheckResult = Field(..., description="结果：正常/异常/跳过")
    actual_value: str | None = Field(default=None, description="实际值")
    remark: str | None = Field(default=None, description="备注")


class EquipmentCheckResult(BaseModel):
    """单设备检查结果（含多个检查项）"""

    records: list[InspectionRecordItem] = Field(
        ..., min_length=1, description="检查项结果列表"
    )


class InspectionRecordResponse(BaseModel):
    """巡检记录响应"""

    id: uuid.UUID
    task_id: uuid.UUID
    equipment_id: uuid.UUID | None = None
    equipment_name: str | None = None
    template_item_id: uuid.UUID
    result: str
    actual_value: str | None
    remark: str | None
    item_name: str | None = None
    expected_result: str | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


# ═══════════ 巡检照片 ═══════════
class InspectionPhotoResponse(BaseModel):
    """巡检照片响应"""

    id: uuid.UUID
    task_id: uuid.UUID
    equipment_id: uuid.UUID | None = None
    file_name: str
    file_size: int | None
    uploaded_at: datetime

    model_config = {"from_attributes": True}


# ═══════════ AI 分析 ═══════════
class InspectionAIAnalyzeRequest(BaseModel):
    """AI 分析请求"""

    image_base64: str = Field(..., description="图片的 base64 编码")
    image_mime_type: str = Field(default="image/jpeg", description="图片 MIME 类型")


class InspectionAIItemResult(BaseModel):
    """单检查项 AI 分析结果"""

    template_item_id: uuid.UUID = Field(..., description="检查项ID")
    item_name: str = Field(..., description="检查项名称")
    expected_result: str | None = Field(default=None, description="预期结果")
    result: str = Field(..., description="结果：正常/异常/跳过")
    actual_value: str | None = Field(default=None, description="实际值")
    remark: str | None = Field(default=None, description="备注")


class InspectionAIAnalyzeResponse(BaseModel):
    """AI 分析响应"""

    items: list[InspectionAIItemResult] = Field(
        default_factory=list, description="分析结果列表"
    )


# ═══════════ 历史详情 ═══════════
class InspectionTaskDetailResponse(InspectionTaskResponse):
    """巡检任务详情响应（含记录和照片）"""

    records: list[InspectionRecordResponse] = Field(default_factory=list)
    photos: list[InspectionPhotoResponse] = Field(default_factory=list)


# ═══════════ 飞书自建应用 ═══════════
class FeishuAppCreateRequest(BaseModel):
    """登记飞书自建应用请求"""

    name: str = Field(
        ..., min_length=1, max_length=100, description="应用备注名（下拉展示用）"
    )
    app_id: str = Field(
        ..., min_length=1, max_length=100, description="飞书应用 App ID"
    )
    app_secret: str = Field(
        ..., min_length=1, description="飞书应用 App Secret（加密存储，不回显）"
    )


class FeishuAppUpdateRequest(BaseModel):
    """更新飞书自建应用请求（App ID 不可改）"""

    name: str | None = Field(
        default=None, min_length=1, max_length=100, description="应用备注名"
    )
    app_secret: str | None = Field(
        default=None, description="新 App Secret（留空保持已保存值）"
    )


class FeishuAppSummary(BaseModel):
    """飞书自建应用摘要（Secret 掩码返回）"""

    id: uuid.UUID = Field(description="应用 ID")
    name: str = Field(description="应用备注名")
    app_id: str = Field(description="飞书应用 App ID")
    app_secret_masked: str = Field(description="App Secret 掩码")
    app_secret_configured: bool = Field(description="是否已配置 App Secret")
    in_use_workshops: list[str] = Field(
        default_factory=list, description="引用该应用的未删除车间配置"
    )
    created_at: datetime = Field(description="登记时间")


# ═══════════ 飞书镜像配置 ═══════════
class EquipmentInspectionFeishuConfigUpdateRequest(BaseModel):
    """保存设备巡检飞书镜像配置请求

    凭据两选一：``feishu_app_id`` 选择已登记应用（优先）；或手输
    ``app_id`` / ``app_secret``（App ID 已存在则自动关联，不存在则登记新应用）。
    """

    feishu_app_id: uuid.UUID | None = Field(
        default=None, description="已登记的飞书自建应用 ID（下拉选择）"
    )
    app_id: str = Field(
        default="",
        max_length=100,
        description="手输的飞书应用 App ID（未选择已登记应用时使用）",
    )
    app_secret: str | None = Field(
        default=None,
        description="手输的飞书应用 App Secret（关联已登记应用时忽略；新建应用必填）",
    )
    app_name: str = Field(
        default="",
        max_length=100,
        description="手输新建应用时的备注名（缺省取 App ID）",
    )
    app_token: str = Field(
        default="",
        max_length=500,
        description="多维表格 App Token，支持粘贴 /base/ 链接或 /wiki/ 知识库链接",
    )
    base_url: str = Field(
        default="",
        max_length=500,
        description="多维表格完整链接（含租户域名，用于飞书配置页直达，可选）",
    )
    today_table_id: str = Field(default="", max_length=100, description="今日巡检表 ID")
    history_table_id: str = Field(
        default="", max_length=100, description="设备历史巡检记录表 ID"
    )
    device_table_id: str = Field(
        default="", max_length=100, description="设备档案表 ID"
    )
    is_enabled: bool = Field(default=True, description="启用镜像同步")


class EquipmentInspectionFeishuConfigDetail(BaseModel):
    """设备巡检飞书镜像配置详情（Secret 掩码返回）"""

    workshop_code: str = Field(description="车间代码（配置归属车间）")
    feishu_app_id: uuid.UUID | None = Field(
        default=None, description="关联的飞书自建应用 ID（环境变量回退时为空）"
    )
    app_name: str = Field(
        default="", description="关联应用备注名（环境变量回退时为空）"
    )
    app_id: str = Field(description="飞书应用 App ID")
    app_secret_masked: str = Field(description="App Secret 掩码")
    app_secret_configured: bool = Field(description="是否已配置 App Secret")
    app_token: str = Field(description="多维表格 App Token")
    base_url: str = Field(description="多维表格完整链接（未填写为空串）")
    today_table_id: str = Field(description="今日巡检表 ID")
    history_table_id: str = Field(description="设备历史巡检记录表 ID")
    device_table_id: str = Field(description="设备档案表 ID")
    is_enabled: bool = Field(description="启用镜像同步")
    source: Literal["database", "environment"] = Field(
        description="当前生效配置来源：数据库行或环境变量回退"
    )
    enabled: bool = Field(description="当前镜像同步是否实际启用")
    last_test_status: str | None = Field(default=None, description="最近连接测试结果")
    last_test_error: str | None = Field(
        default=None, description="最近连接测试失败原因"
    )
    last_tested_at: datetime | None = Field(
        default=None, description="最近连接测试时间"
    )


class EquipmentInspectionFeishuConfigTestResult(BaseModel):
    """设备巡检飞书镜像连接测试结果"""

    success: bool = Field(description="测试是否通过")
    table_count: int = Field(default=0, description="读取到的多维表格子表数量")
    message: str = Field(default="", description="结果说明（失败时为脱敏原因）")
