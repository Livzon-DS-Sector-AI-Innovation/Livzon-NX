"""设备检修台账（飞书镜像）Schema。"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class RepairPerson(BaseModel):
    """维修人员（同步时经通讯录解析；解析不到时整列为空）"""

    name: str = Field(description="姓名（解析失败时回退 open_id）")
    open_id: str | None = Field(default=None, description="飞书 open_id")
    avatar_url: str | None = Field(
        default=None, description="头像（通讯录无权限时为空）"
    )


class RepairRecordResponse(BaseModel):
    """检修记录（飞书镜像，原文展示，不关联设备台账）"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workshop_code: str = Field(description="车间代码")
    record_id: str = Field(description="飞书记录ID")
    workshop_text: str | None = Field(default=None, description="车间及地点（原文）")
    equipment_text: str | None = Field(
        default=None, description="设备名称/型号（原文）"
    )
    repaired_at: date | None = Field(default=None, description="维修日期")
    person_text: str | None = Field(default=None, description="维修人员（原文）")
    persons: list[RepairPerson] | None = Field(
        default=None, description="维修人员（头像解析成功时才有值，展示优先于原文）"
    )
    fault_desc: str | None = Field(default=None, description="故障描述/原因")
    spare_parts: str | None = Field(default=None, description="更换备件")
    result: str | None = Field(default=None, description="维修后状态（原文）")
    remark: str | None = Field(default=None, description="备注")
    last_modified_at: datetime | None = Field(
        default=None, description="飞书最后修改时间"
    )


class RepairFrequencyItem(BaseModel):
    """设备维修频次排行项（按设备名称原文聚合）"""

    equipment_text: str = Field(description="设备名称/型号（原文）")
    times: int = Field(description="维修次数")
    last_repaired_at: date | None = Field(default=None, description="最近维修日期")


class RepairFilterOptions(BaseModel):
    """筛选下拉的去重选项（按出现次数降序）"""

    persons: list[str] = Field(default_factory=list, description="维修人员姓名")
    faults: list[str] = Field(default_factory=list, description="故障描述/原因")
    equipments: list[str] = Field(default_factory=list, description="设备名称/型号")


class RepairSyncStateResponse(BaseModel):
    """检修镜像同步状态"""

    workshop_code: str
    total_rows: int = Field(description="镜像行数")
    last_synced_at: datetime | None = Field(default=None, description="同步水位")
    last_run_at: datetime | None = Field(default=None, description="最近同步执行时间")
    last_status: str | None = Field(default=None, description="success / failed")
    last_message: str | None = Field(default=None, description="最近同步说明")
    enabled: bool = Field(default=False, description="同步是否已启用并配置完整")


class RepairConfigDetail(BaseModel):
    """检修飞书镜像配置详情"""

    workshop_code: str
    feishu_app_id: uuid.UUID | None = None
    app_name: str = ""
    app_id: str = ""
    app_secret_masked: str = ""
    app_secret_configured: bool = False
    app_token: str = ""
    table_id: str = ""
    base_url: str = ""
    is_enabled: bool = False
    enabled: bool = Field(default=False, description="配置完整且启用")
    last_test_status: str | None = None
    last_test_error: str | None = None
    last_tested_at: datetime | None = None


class RepairConfigUpdateRequest(BaseModel):
    """保存检修飞书镜像配置请求。

    凭据两选一：``feishu_app_id`` 选择已登记应用（优先）；或手输
    ``app_id`` / ``app_secret``（App ID 已存在则自动关联，不存在则登记新应用）。
    """

    feishu_app_id: uuid.UUID | None = Field(
        default=None, description="已登记的飞书自建应用 ID（下拉选择）"
    )
    app_id: str = Field(default="", max_length=100, description="手输的飞书应用 App ID")
    app_secret: str | None = Field(
        default=None, max_length=200, description="手输的飞书应用 App Secret"
    )
    app_name: str = Field(default="", max_length=100, description="手输新应用时的名称")
    app_token: str = Field(
        default="", max_length=500, description="多维表格链接或 App Token"
    )
    table_id: str = Field(
        default="", max_length=200, description="维修记录数据表 ID 或子表链接"
    )
    base_url: str = Field(
        default="", max_length=500, description="多维表格完整链接（直达用）"
    )
    is_enabled: bool = Field(default=True, description="启用镜像同步")


class RepairConfigTestResult(BaseModel):
    """检修配置连接测试结果"""

    success: bool
    message: str = ""


class RepairSummaryKpi(BaseModel):
    """检修汇总 KPI"""

    total_count: int = Field(description="维修次数")
    equipment_count: int = Field(description="涉及设备数（车间+设备名去重）")
    workshop_count: int = Field(description="有数据的车间数")
    total_workshops: int = Field(description="车间总数")
    person_count: int = Field(description="维修人数")
    abnormal_count: int = Field(description="异常/待处理记录数")
    daily_average: float = Field(description="日均维修次数")
    previous_total_count: int | None = Field(
        default=None, description="上一周期维修次数（无日期范围时为空）"
    )
    change_rate: float | None = Field(default=None, description="环比变化百分比")


class RepairSummaryWorkshopRow(BaseModel):
    """检修汇总的车间对比行"""

    workshop_code: str
    workshop_name: str
    repair_count: int
    equipment_count: int
    person_count: int
    abnormal_count: int
    last_repaired_at: date | None = None
    last_synced_at: datetime | None = None
    last_sync_status: str | None = None
    configured: bool = Field(default=False, description="是否已配置飞书检修表")
    enabled: bool = Field(default=False, description="是否启用同步")
    status: str = Field(
        description="normal / sync_failed / disabled / not_configured / no_records"
    )


class RepairSummaryEquipmentItem(BaseModel):
    """高频设备（按车间+设备名称原文分组，不跨车间合并）"""

    workshop_code: str
    workshop_name: str
    equipment_text: str
    times: int
    last_repaired_at: date | None = None


class RepairSummaryFaultWorkshop(BaseModel):
    """某条故障在某个车间出现的次数"""

    workshop_code: str
    workshop_name: str
    times: int


class RepairSummaryFaultItem(BaseModel):
    """高频故障（故障描述原文去空白后分组）"""

    fault_desc: str
    times: int
    equipment_count: int = Field(description="涉及设备数（车间+设备名去重）")
    workshops: list[RepairSummaryFaultWorkshop] = Field(
        default_factory=list, description="涉及车间及各自次数（按次数降序）"
    )
    last_repaired_at: date | None = None


class RepairSummaryPersonWorkshop(BaseModel):
    """某个维修人员在某个车间参与的次数"""

    workshop_code: str
    workshop_name: str
    times: int


class RepairSummaryPersonItem(BaseModel):
    """人员工作量（按姓名聚合，优先结构化人员信息）"""

    name: str
    open_id: str | None = None
    avatar_url: str | None = None
    times: int = Field(description="参与维修的记录数")
    workshop_count: int
    workshops: list[RepairSummaryPersonWorkshop] = Field(
        default_factory=list, description="参与车间及各自次数（按次数降序）"
    )
    last_repaired_at: date | None = None


class RepairSummaryTrendPoint(BaseModel):
    """检修趋势点（按周或按月，按车间拆分）"""

    period: str = Field(description="周起始日期（YYYY-MM-DD）或月份（YYYY-MM）")
    workshop_code: str
    workshop_name: str
    count: int
    equipment_count: int


class RepairSummaryResponse(BaseModel):
    """跨车间检修汇总"""

    kpi: RepairSummaryKpi
    workshops: list[RepairSummaryWorkshopRow] = Field(default_factory=list)
    top_equipment: list[RepairSummaryEquipmentItem] = Field(default_factory=list)
    top_faults: list[RepairSummaryFaultItem] = Field(default_factory=list)
    top_persons: list[RepairSummaryPersonItem] = Field(default_factory=list)
    trend: list[RepairSummaryTrendPoint] = Field(default_factory=list)
    trend_granularity: str = Field(description="week / month")


RepairSummarySortField = Literal[
    "workshop",
    "repair_count",
    "equipment_count",
    "abnormal_count",
    "person_count",
    "last_repaired_at",
]
RepairSummaryRangeKey = Literal["30d", "90d", "year", "last-year", "all"]

WORKSHOP_CODE_PATTERN = r"^[a-z0-9][a-z0-9-]{0,8}[a-z0-9]$"


class RepairSummarySettingsResponse(BaseModel):
    """检修汇总全厂默认设置"""

    sort_field: str
    sort_order: str
    range_key: str
    workshops: list[str] | None = Field(
        default=None, description="默认车间筛选；null = 全部"
    )
    updated_by_name: str | None = Field(default=None, description="最近修改人")
    updated_at: datetime | None = Field(default=None, description="最近修改时间")
    can_edit: bool = Field(default=False, description="当前用户是否可保存默认设置")


class RepairSummarySettingsUpdate(BaseModel):
    """保存检修汇总全厂默认设置"""

    sort_field: RepairSummarySortField = "workshop"
    sort_order: Literal["ascend", "descend"] = "ascend"
    range_key: RepairSummaryRangeKey = "30d"
    workshops: list[Annotated[str, Field(pattern=WORKSHOP_CODE_PATTERN)]] | None = (
        Field(default=None, description="默认车间筛选；null/空 = 全部")
    )
