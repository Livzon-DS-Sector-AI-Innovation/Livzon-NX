"""校准证书 AI 识别结果契约（外部校准检定新增辅助，不直接写飞书）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CertificateExtractedFields(BaseModel):
    """AI 从证书中提取的原始字段（值可能为空，供人工核对）。"""

    instrument_name: str | None = Field(None, description="仪器/器具名称")
    model: str | None = Field(None, description="型号/规格")
    serial_no: str | None = Field(None, description="出厂编号/器具编号")
    calibration_date: str | None = Field(None, description="检定/校准日期 YYYY-MM-DD")
    next_calibration_date_stated: str | None = Field(
        None, description="证书载明的下次检定日期/有效期至（可能缺失）"
    )
    certificate_no: str | None = Field(None, description="证书编号")
    calibration_agency: str | None = Field(None, description="检定/校准机构")
    conclusion: str | None = Field(None, description="检定/校准结论")


class DeviceDirectoryMatch(BaseModel):
    """QC 设备目录实时反查结果。"""

    matched: bool = Field(..., description="是否在设备目录中命中")
    match_by: str | None = Field(None, description="命中的目录列名（如 器具编号）")
    record_id: str | None = Field(None, description="目录记录 ID")
    instrument_name: str | None = Field(None, description="目录中的器具名称")
    location: str | None = Field(None, description="使用地点")
    period_months: int | None = Field(None, description="检定周期（月）")
    period_text: str | None = Field(None, description="目录中的周期原文")


class InstrumentCertificateAnalyzeResult(BaseModel):
    """证书识别端点响应：提取结果 + 目录反查 + 预填字段（人工确认后提交）。"""

    extracted: CertificateExtractedFields
    directory: DeviceDirectoryMatch
    computed_next_calibration_date: str | None = Field(
        None, description="按目录周期推算的下次检定日期 YYYY-MM-DD（检定日期+周期-1天）"
    )
    mapped_fields: dict[str, Any] = Field(
        default_factory=dict, description="可写入外部校准表的字段（键=飞书字段名）"
    )
    warnings: list[str] = Field(
        default_factory=list, description="识别/反查/映射过程中的提示"
    )
    attachment_file_token: str | None = Field(
        None, description="已上传证书的附件 token（重新匹配时透传复用，不重复上传）"
    )


class CertificateRematchRequest(BaseModel):
    """人工修正后的证书字段 → 重新反查设备目录并重建预填字段。"""

    instrument_name: str | None = None
    model: str | None = None
    serial_no: str | None = Field(None, description="修正后的出厂编号")
    calibration_date: str | None = None
    next_calibration_date_stated: str | None = None
    certificate_no: str | None = None
    calibration_agency: str | None = None
    conclusion: str | None = None
    attachment_file_token: str | None = Field(
        None, description="首次识别上传的证书附件 token（复用，不重复上传）"
    )
    attachment_name: str | None = None
