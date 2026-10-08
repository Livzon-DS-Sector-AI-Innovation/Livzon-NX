"""安全模块飞书设置 Schema。"""

from datetime import datetime

from pydantic import BaseModel, Field


class SafetyFeishuAppSettingsDetail(BaseModel):
    """飞书应用配置回显（Secret 仅返回掩码）。"""

    app_id: str = ""
    app_secret_masked: str = ""
    bitable_app_token: str | None = None
    bitable_hazard_table_id: str | None = None
    knowledge_app_token: str | None = None
    knowledge_table_id: str | None = None
    is_enabled: bool = True
    knowledge_last_sync_status: str | None = None
    knowledge_last_sync_error: str | None = None
    knowledge_last_synced_at: datetime | None = None
    last_test_status: str | None = None
    last_test_error: str | None = None
    last_tested_at: datetime | None = None


class UpdateSafetyFeishuAppSettingsRequest(BaseModel):
    """保存飞书应用配置。

    app_secret 留空或传回掩码值表示保持当前 Secret 不变；
    首次保存（尚无存量配置）时必须提供明文 Secret。
    """

    app_id: str = Field(min_length=1, max_length=100)
    app_secret: str = Field(default="", max_length=200)
    bitable_app_token: str | None = Field(default=None, max_length=100)
    bitable_hazard_table_id: str | None = Field(default=None, max_length=100)
    knowledge_app_token: str | None = Field(default=None, max_length=100)
    knowledge_table_id: str | None = Field(default=None, max_length=100)
    is_enabled: bool = True


class SafetyFeishuSettingsTestResult(BaseModel):
    """飞书应用连接测试结果。"""

    success: bool
    message: str
    checked_at: datetime
