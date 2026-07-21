"""Schemas for quality Feishu settings."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class QualityFeishuAppSettingsDetail(BaseModel):
    app_id: str = ""
    app_secret_masked: str | None = None
    is_enabled: bool = False
    last_test_status: str | None = None
    last_test_error: str | None = None
    last_tested_at: datetime | None = None


class UpdateQualityFeishuAppSettingsRequest(BaseModel):
    app_id: str = ""
    app_secret: str = ""
    is_enabled: bool = True


class QualityFeishuEntitySettingItem(BaseModel):
    entity_code: str
    entity_name: str
    entity_group: str
    source_note: str | None = None
    app_token: str | None = None
    base_table_name: str | None = None
    base_table_id: str | None = None
    is_enabled: bool = False
    enable_push_to_feishu: bool = False
    enable_pull_from_feishu: bool = False
    field_mappings: list["QualityFeishuFieldMappingItem"] = Field(default_factory=list)
    sort_order: int = 0
    last_sync_status: str | None = None
    last_sync_error: str | None = None
    last_synced_at: datetime | None = None

    @field_validator("field_mappings", mode="before")
    @classmethod
    def _normalize_field_mappings(
        cls,
        value: object,
    ) -> list[object]:
        if value is None:
            return []
        return value  # type: ignore[return-value]


class QualityFeishuTableOption(BaseModel):
    table_id: str
    table_name: str


class QualityFeishuFieldOption(BaseModel):
    field_id: str
    field_name: str
    field_type: str | int | None = None


class QualityFeishuSystemFieldOption(BaseModel):
    field_key: str
    field_label: str
    direction: str = "both"


class QualityFeishuFieldMappingItem(BaseModel):
    system_field: str
    feishu_field: str | None = None


class QualityFeishuEntityFieldMappingBundle(BaseModel):
    entity_code: str
    entity_name: str
    system_fields: list[QualityFeishuSystemFieldOption] = []
    feishu_fields: list[QualityFeishuFieldOption] = []
    field_mappings: list[QualityFeishuFieldMappingItem] = []


class UpdateQualityFeishuEntitySettingRequest(BaseModel):
    app_token: str | None = None
    base_table_name: str | None = None
    base_table_id: str | None = None
    is_enabled: bool = True
    enable_push_to_feishu: bool = True
    enable_pull_from_feishu: bool = True
    field_mappings: list[QualityFeishuFieldMappingItem] | None = None


class QualityFeishuSettingsTestResult(BaseModel):
    success: bool
    message: str
    checked_at: datetime
    entity_code: str | None = None
    table_id: str | None = None
