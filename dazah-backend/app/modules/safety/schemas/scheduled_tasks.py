"""Safety request and response schemas."""

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TaskStatusEnum(str, Enum):
    """任务执行状态枚举"""

    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"


class HeaderColorEnum(str, Enum):
    """卡片头部颜色枚举"""

    BLUE = "blue"
    ORANGE = "orange"
    GREEN = "green"
    RED = "red"
    PURPLE = "purple"


HEADER_COLOR_OPTIONS = [
    {"value": HeaderColorEnum.BLUE, "label": "蓝色"},
    {"value": HeaderColorEnum.ORANGE, "label": "橙色"},
    {"value": HeaderColorEnum.GREEN, "label": "绿色"},
    {"value": HeaderColorEnum.RED, "label": "红色"},
    {"value": HeaderColorEnum.PURPLE, "label": "紫色"},
]


class DataSourceItem(BaseModel):
    """数据来源配置项"""

    key: str = Field(..., description="数据源标识，如 hazard_open_count")
    label: str = Field(..., description="数据源显示名，如「待整改隐患数」")
    enabled: bool = Field(True, description="是否启用")


class ScheduledTaskCreate(BaseModel):
    """创建定时任务请求"""

    name: str = Field(..., min_length=1, max_length=200, description="任务名称")
    description: str | None = Field(None, description="任务描述")
    cron_expression: str = Field(..., min_length=1, max_length=100, description="Cron 表达式")
    cron_desc: str | None = Field(None, max_length=200, description="Cron 可读描述")
    feishu_chat_id: str = Field(..., min_length=1, max_length=100, description="目标飞书群聊 chat_id")
    feishu_chat_name: str | None = Field(None, max_length=200, description="飞书群聊名称")
    header_color: HeaderColorEnum = Field(HeaderColorEnum.BLUE, description="卡片头部颜色")
    data_sources: list[DataSourceItem] = Field(default_factory=list, description="数据来源配置")
    card_template: str | None = Field(None, description="消息卡片模板")
    is_enabled: bool = Field(True, description="是否启用")


class ScheduledTaskUpdate(BaseModel):
    """更新定时任务请求"""

    name: str | None = Field(None, min_length=1, max_length=200, description="任务名称")
    description: str | None = Field(None, description="任务描述")
    cron_expression: str | None = Field(None, min_length=1, max_length=100, description="Cron 表达式")
    cron_desc: str | None = Field(None, max_length=200, description="Cron 可读描述")
    feishu_chat_id: str | None = Field(None, min_length=1, max_length=100, description="目标飞书群聊 chat_id")
    feishu_chat_name: str | None = Field(None, max_length=200, description="飞书群聊名称")
    header_color: HeaderColorEnum | None = Field(None, description="卡片头部颜色")
    data_sources: list[DataSourceItem] | None = Field(None, description="数据来源配置")
    card_template: str | None = Field(None, description="消息卡片模板")
    is_enabled: bool | None = Field(None, description="是否启用")


class ScheduledTaskResponse(BaseModel):
    """定时任务响应"""

    id: uuid.UUID
    name: str
    description: str | None
    cron_expression: str
    cron_desc: str | None
    feishu_chat_id: str
    feishu_chat_name: str | None
    header_color: str
    data_sources: list | None
    card_template: str | None
    is_enabled: bool
    last_run_at: datetime | None
    last_run_status: str | None
    last_error: str | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ScheduledTaskLogResponse(BaseModel):
    """任务执行日志响应"""

    id: uuid.UUID
    task_id: uuid.UUID
    started_at: datetime
    completed_at: datetime | None
    status: str
    data_snapshot: dict | None
    card_content: str | None
    feishu_msg_id: str | None
    error_message: str | None
    duration_ms: int | None
    created_at: datetime

    class Config:
        from_attributes = True


class CardPreviewRequest(BaseModel):
    """卡片预览请求"""

    data_sources: list[DataSourceItem] = Field(..., description="数据来源配置")
    card_template: str = Field(..., description="消息卡片模板")
    header_color: HeaderColorEnum = Field(HeaderColorEnum.BLUE, description="卡片头部颜色")


class CardPreviewResponse(BaseModel):
    """卡片预览响应"""

    card_json: str = Field(..., description="飞书卡片 JSON")
    markdown_preview: str = Field(..., description="渲染后的 Markdown 预览")
    variables: dict[str, str] = Field(default_factory=dict, description="解析后的变量值")


class DataSourceOption(BaseModel):
    """可用数据来源选项"""

    key: str = Field(..., description="数据源标识")
    label: str = Field(..., description="数据源显示名")
    description: str | None = Field(None, description="数据源说明")
    default_enabled: bool = Field(False, description="新建任务时默认是否勾选")
