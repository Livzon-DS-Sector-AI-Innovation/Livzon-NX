"""Administration request and response schemas.

当前覆盖「烟酒礼品管理」的飞书应用配置、只读镜像入口/数据表/页面绑定、
仪表台统计契约，以及「公告通知」原生台账契约（AI 识别建议值/导入表单/
台账分页/公告内容）。镜像页的 ``page-data`` 载荷由平台层
``ModuleFeishuReadMirrorService`` 生成，前端按 ``WarehouseFeishuPageData``
契约消费，这里不重复定义。
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ── 飞书应用配置 ───────────────────────────────────────────────


class AdministrationFeishuConfigInput(BaseModel):
    """保存飞书应用配置；``app_secret`` 留空表示保持当前 Secret 不变。"""

    id: uuid.UUID | None = None
    config_name: str = Field(default="行政管理飞书配置", min_length=1, max_length=255)
    app_id: str = Field(min_length=1, max_length=100)
    app_secret: str = Field(default="", max_length=200)
    is_active: bool = True
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)
    daily_sync_time: str = Field(default="02:00", pattern=r"^\d{2}:\d{2}$")
    remark: str | None = Field(default=None, max_length=2000)


class AdministrationFeishuConfigResponse(BaseModel):
    """飞书应用配置回显，绝不返回 Secret 明文。"""

    id: uuid.UUID | None = None
    config_name: str
    app_id: str
    timezone: str
    daily_sync_time: str
    is_active: bool
    remark: str | None = None
    app_secret_configured: bool
    app_secret_masked: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AdministrationFeishuConnectivityStep(BaseModel):
    name: str
    status: str
    message: str


class AdministrationFeishuConnectivityResult(BaseModel):
    ok: bool
    steps: list[AdministrationFeishuConnectivityStep]


# ── 只读镜像：入口、数据表、页面绑定 ─────────────────────────────


class AdministrationFeishuSourceRootInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source_type: str = Field(pattern="^(wiki|base)$")
    source_url: str = Field(min_length=1, max_length=2000)


class AdministrationFeishuSourceRoot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    config_id: uuid.UUID
    name: str
    source_type: str
    source_url: str
    root_token: str
    is_active: bool
    discovery_status: str
    last_discovered_at: datetime | None = None
    discovery_error: str | None = None


class AdministrationFeishuResource(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_root_id: uuid.UUID
    app_token: str
    table_id: str
    title: str
    source_path: list[dict[str, str]] = Field(default_factory=list)
    sync_status: str
    sync_error: str | None = None
    last_complete_sync_at: datetime | None = None


class AdministrationFeishuSyncResult(BaseModel):
    resource_id: str
    record_count: int


class AdministrationFeishuBindingItem(BaseModel):
    resource_id: uuid.UUID
    tab_name: str = Field(min_length=1, max_length=255)
    sort_order: int = 0
    is_default: bool = False
    is_enabled: bool = True
    visible_field_ids: list[str] = Field(default_factory=list)


class AdministrationFeishuBindingReplace(BaseModel):
    bindings: list[AdministrationFeishuBindingItem]


# ── 烟酒礼品仪表台 ─────────────────────────────────────────────


class TobaccoGiftChartItem(BaseModel):
    """柱状图单根柱子：维度名称 + 数值（数量或金额）。"""

    name: str
    value: float


class TobaccoGiftDashboardStats(BaseModel):
    """烟酒礼品仪表台统计（数据来自本地飞书镜像，未绑定或未同步时为 0/空）。

    口径与行政侧飞书仪表盘一致（2026-11-09 用真实数据核对）：
    物品品类/总价/总数取自物品清单全表；已领用物品总数只计状态为
    「已领用」的领用单；领取分析/员工统计计入全部未作废领用单。
    """

    item_categories: int = Field(description="物品品类：物品清单记录数")
    item_total_value: float = Field(description="物品总价：Σ总金额（元）")
    item_total_count: float = Field(description="物品总数：Σ物品总数")
    requisitioned_total: float = Field(
        description="已领用物品总数：已领用单的领用数量合计"
    )
    inventory_by_item: list[TobaccoGiftChartItem] = Field(
        description="物品库存情况：按物品的物品总数"
    )
    requisition_by_item: list[TobaccoGiftChartItem] = Field(
        description="物品领取分析：未作废领用单按物品的领用数量"
    )
    value_by_item: list[TobaccoGiftChartItem] = Field(
        description="领用物品总价分布：按物品的总金额（元）"
    )
    requisition_by_employee: list[TobaccoGiftChartItem] = Field(
        description="员工领用统计：未作废领用单按申请人的领用数量"
    )
    inventory_synced_at: datetime | None = Field(
        default=None, description="物品清单最近一次完整同步时间"
    )
    requisition_synced_at: datetime | None = Field(
        default=None, description="领用记录最近一次完整同步时间"
    )


# ── 宿舍管理：入住率仪表盘 + AI 推荐入住 ───────────────────────


class DormitoryRoomSummary(BaseModel):
    """单间宿舍的床位概览（数据来自宿舍清单镜像，公式字段取计算值）。"""

    room_no: str = Field(description="宿舍编号")
    building: str = Field(default="", description="楼号")
    unit: str = Field(default="", description="单元")
    room_type: str = Field(default="", description="房间类型")
    dorm_type: str = Field(default="", description="宿舍类型（男生宿舍/女生宿舍）")
    bed_count: int = Field(default=0, description="床位数量")
    occupied: int = Field(default=0, description="已住人数")
    vacant: int = Field(default=0, description="剩余床位")


class DormitoryOccupancyStats(BaseModel):
    """宿舍入住率仪表盘统计（未绑定或未同步时为 0/空，不报错）。"""

    total_rooms: int = Field(default=0, description="宿舍总数（宿舍清单记录数）")
    empty_rooms: int = Field(default=0, description="空房间数（已住人数为 0）")
    full_rooms: int = Field(default=0, description="满人房间数（剩余床位为 0）")
    partial_rooms: int = Field(default=0, description="未住满房间数")
    total_beds: int = Field(default=0, description="总床位数")
    occupied_beds: int = Field(default=0, description="已住床位合计")
    occupancy_rate: float = Field(default=0.0, description="床位入住率（0-1）")
    empty_room_list: list[DormitoryRoomSummary] = Field(
        default_factory=list, description="空房间列表（按宿舍编号排序）"
    )
    full_room_list: list[DormitoryRoomSummary] = Field(
        default_factory=list, description="满人房间列表（按宿舍编号排序）"
    )
    synced_at: datetime | None = Field(
        default=None, description="宿舍清单最近一次完整同步时间"
    )


class DormitoryRecommendationItem(BaseModel):
    """单条房间推荐（LLM 输出已校验房间号必须来自真实空床位候选）。"""

    room_no: str = Field(description="宿舍编号（候选房间原样取值）")
    room_type: str = Field(default="", description="房间类型")
    dorm_type: str = Field(default="", description="宿舍类型")
    vacant_beds: int = Field(default=0, description="剩余床位")
    reason: str = Field(default="", description="推荐理由（LLM 生成或规则说明）")
    source: str = Field(description="推荐来源：ai=模型推荐 / rule=规则兜底")


class DormitoryRoomRecommendation(BaseModel):
    """AI 推荐结果（最多 3 条；无候选时 recommendations 为空并给出原因）。"""

    recommendations: list[DormitoryRecommendationItem] = Field(default_factory=list)
    source: str = Field(description="整体推荐来源：ai / rule")
    message: str = Field(default="", description="给用户的补充说明（如无可用房间）")


class DormitoryCheckinInput(BaseModel):
    """新员工入住登记（确认后回写飞书员工住宿退宿清单）。"""

    room_no: str = Field(default="", description="宿舍编号（推荐结果或手填）")
    employee_id: str = Field(default="", max_length=100, description="员工ID")
    name: str = Field(min_length=1, max_length=100, description="姓名")
    gender: str = Field(min_length=1, max_length=20, description="性别（男/女）")
    department: str = Field(default="", max_length=100, description="部门")
    job_title: str = Field(default="", max_length=100, description="岗位")
    phone: str = Field(default="", max_length=100, description="联系方式")
    shift_type: str = Field(default="", max_length=50, description="倒班类型")
    address: str = Field(default="", max_length=255, description="居住地址")
    deposit_paid: str = Field(
        default="", max_length=20, description="押金是否缴纳（是/否）"
    )
    agreement_signed: str = Field(
        default="", max_length=20, description="是否签订协议（是/否）"
    )
    remark: str = Field(default="", max_length=255, description="备注")


class DormitoryCheckinResult(BaseModel):
    """办理入住结果（记录已写入飞书；synced 表示镜像是否已即时同步）。"""

    record_id: str = Field(description="飞书记录 ID")
    room_no: str = Field(description="分配的宿舍编号")
    synced: bool = Field(description="写入后是否已即时触发镜像同步")


class TobaccoGiftAiAnalysis(BaseModel):
    """烟酒礼品仪表台 AI 分析结果（LLM 辅助结论，仅供参考，不替代人工核对）。"""

    summary: str = Field(description="总体态势概述（≤120字）")
    insights: list[str] = Field(description="关键发现（2~5条）")
    anomalies: list[str] = Field(description="异常提示（低于预警库存、作废单等）")
    suggestions: list[str] = Field(description="管理建议（2~4条）")
    generated_at: datetime = Field(description="生成时间（UTC）")


# ── 公告通知台账（平台原生，非飞书镜像） ────────────────────────


class NoticeParseSuggestion(BaseModel):
    """AI 识别的公告元数据建议值（不含公告内容，由人工确认后随导入落库）。"""

    notice_no: str | None = Field(default=None, max_length=100, description="公告编号")
    title: str | None = Field(default=None, max_length=255, description="公告标题")
    publisher: str | None = Field(default=None, max_length=255, description="发布单位")
    published_at: str | None = Field(
        default=None, description="发布日期（YYYY-MM-DD，无法识别为 null）"
    )
    category: str | None = Field(default=None, max_length=50, description="公告类别")
    remark: str | None = Field(default=None, description="备注")


class NoticeParsePreview(BaseModel):
    """解析预览（不落库、不存原文、不返回公告内容）。"""

    file_name: str = Field(description="上传文件名")
    suggestion: NoticeParseSuggestion = Field(description="AI 识别建议值")


class NoticeUpdateInput(BaseModel):
    """编辑公告元数据与内容（v1 不支持更换原文存档）。"""

    notice_no: str = Field(default="", max_length=100)
    title: str = Field(default="", max_length=255)
    publisher: str = Field(default="", max_length=255)
    published_at: str | None = Field(default=None, description="YYYY-MM-DD")
    category: str = Field(default="", max_length=50)
    remark: str = Field(default="", max_length=2000)
    content: str = Field(default="", max_length=20000, description="公告内容")


class NoticeItem(BaseModel):
    """台账条目元数据（列表/详情响应永不包含公告内容字段）。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    notice_no: str
    title: str
    publisher: str
    published_at: str | None = None
    category: str
    remark: str | None = None
    source_file_name: str
    source_size_bytes: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class NoticeListResponse(BaseModel):
    """台账分页结果（categories 供筛选下拉，取自现存非空类别）。"""

    items: list[NoticeItem]
    total: int
    page: int
    page_size: int
    categories: list[str] = Field(default_factory=list)


class NoticeContentResponse(BaseModel):
    """公告内容（仅 operate 绑定的专用端点返回）。"""

    id: uuid.UUID
    notice_no: str
    title: str
    content: str
