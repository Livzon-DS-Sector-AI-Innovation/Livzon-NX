"""Reference substance schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ReferenceSubstanceCreate(BaseModel):
    drug_name: str = Field(min_length=1, max_length=255, description="药品名称")
    substance_name: str = Field(min_length=1, max_length=255, description="对照物质名称")
    lot_number: str = Field(min_length=1, max_length=100, description="批号")
    manufacturer: str = Field(min_length=1, max_length=500, description="生产厂家")
    english_name: str | None = Field(None, max_length=255, description="英文名")
    expiration_date: str | None = Field(None, max_length=50, description="有效期")
    cas_number: str | None = Field(None, max_length=50, description="CAS号")
    molecular_formula: str | None = Field(None, max_length=100, description="分子式")
    molecular_weight: str | None = Field(None, max_length=50, description="分子量")
    assay: str | None = Field(None, max_length=50, description="含量")
    storage_condition: str | None = Field(None, max_length=255, description="贮存条件")
    coa_file_url: str | None = Field(None, description="COA文件URL")


class ReferenceSubstanceUpdate(BaseModel):
    drug_name: str | None = Field(None, min_length=1, max_length=255)
    substance_name: str | None = Field(None, min_length=1, max_length=255)
    lot_number: str | None = Field(None, min_length=1, max_length=100)
    manufacturer: str | None = Field(None, min_length=1, max_length=500)
    english_name: str | None = Field(None, max_length=255)
    expiration_date: str | None = Field(None, max_length=50)
    cas_number: str | None = Field(None, max_length=50)
    molecular_formula: str | None = Field(None, max_length=100)
    molecular_weight: str | None = Field(None, max_length=50)
    assay: str | None = Field(None, max_length=50)
    storage_condition: str | None = Field(None, max_length=255)
    usage_scope: str | None = Field(None, max_length=255)
    usage_method: str | None = Field(None, max_length=255)
    coa_file_url: str | None = None


class ReferenceSubstanceResponse(BaseModel):
    id: uuid.UUID
    drug_name: str
    substance_name: str
    lot_number: str
    manufacturer: str
    english_name: str | None
    expiration_date: str | None
    cas_number: str | None
    molecular_formula: str | None
    molecular_weight: str | None
    assay: str | None
    storage_condition: str | None
    usage_scope: str | None
    usage_method: str | None
    coa_file_url: str | None
    provider: str
    handler: str
    contact: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
