"""设备检修台账（飞书镜像）Schema。"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


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
