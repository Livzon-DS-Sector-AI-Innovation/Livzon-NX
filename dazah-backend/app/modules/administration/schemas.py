"""Administration request and response schemas.

当前覆盖「烟酒礼品管理」：飞书应用配置、只读镜像入口/数据表/页面绑定，
以及仪表台统计契约。镜像页的 ``page-data`` 载荷由平台层
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
