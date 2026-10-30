"""职业健康检测报告导入的请求 / 响应模型。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# 危害因素类别（检测报告明细专用，较监测流程的 dust/chemical/physical 更细）
OH_DETECTION_FACTOR_CATEGORY_OPTIONS: list[dict[str, str]] = [
    {"value": "dust_total", "label": "粉尘（总尘）"},
    {"value": "dust_respirable", "label": "粉尘（呼尘）"},
    {"value": "free_silica", "label": "游离二氧化硅"},
    {"value": "chemical", "label": "化学因素"},
    {"value": "noise", "label": "噪声"},
    {"value": "power_frequency_field", "label": "工频电场"},
    {"value": "heat", "label": "高温"},
]

# 判定结果
OH_DETECTION_VERDICT_OPTIONS: list[dict[str, str]] = [
    {"value": "compliant", "label": "未超标"},
    {"value": "exceed", "label": "超标"},
    {"value": "unknown", "label": "未判定"},
]

# 记录类型
OH_DETECTION_RECORD_TYPE_OPTIONS: list[dict[str, str]] = [
    {"value": "post", "label": "岗位接触"},
    {"value": "point", "label": "采样点/测量点"},
]

# 限值类型
OH_DETECTION_LIMIT_TYPE_OPTIONS: list[dict[str, str]] = [
    {"value": "PC-TWA", "label": "PC-TWA（8h时间加权）"},
    {"value": "PC-STEL", "label": "PC-STEL（短时接触）"},
    {"value": "MAC", "label": "MAC（最高容许浓度）"},
    {"value": "PE", "label": "PE（超限倍数限值）"},
    {"value": "LEX-40h", "label": "LEX,40h（40h等效声级）"},
    {"value": "E8", "label": "E8（8h工频电场强度）"},
    {"value": "WBGT", "label": "WBGT指数"},
    {"value": "none", "label": "无限值"},
]

# 解析模式
OH_DETECTION_PARSE_MODE_OPTIONS: list[dict[str, str]] = [
    {"value": "rules", "label": "规则识别"},
    {"value": "llm", "label": "AI 识别"},
    {"value": "mixed", "label": "规则 + AI"},
]


class OhDetectionResultDraft(BaseModel):
    """解析引擎输出的单条检测结果草稿（入库前校验）。"""

    table_ref: str = Field(default="", max_length=32)
    table_title: str = Field(default="", max_length=255)
    factor_category: str = Field(max_length=32)
    factor_name: str = Field(min_length=1, max_length=128)
    record_type: str = Field(default="point", pattern="^(post|point)$")
    workshop: str = Field(default="", max_length=255)
    post: str = Field(default="", max_length=255)
    sample_point: str = Field(default="", max_length=255)
    measured_value: str = Field(default="", max_length=64)
    measured_value_num: float | None = None
    unit: str = Field(default="", max_length=32)
    limit_type: str = Field(default="none", max_length=16)
    limit_value_num: float | None = None
    verdict: str = Field(default="unknown", pattern="^(compliant|exceed|unknown)$")
    is_noise_post: bool = False
    verdict_raw: str = Field(default="", max_length=128)
    extra: dict[str, Any] | None = None


class OhDetectionTableSummary(BaseModel):
    """解析预览中的单表识别汇总。"""

    table_ref: str = Field(default="", description="表号（表5-2）")
    table_title: str = Field(default="", description="表标题")
    layout: str = Field(default="unknown", description="识别版式")
    mode: str = Field(
        default="rules",
        description="识别模式: rules=规则 / llm=AI / skipped=跳过",
    )
    row_count: int = Field(default=0, description="识别结果行数")
    warnings: list[str] = Field(default_factory=list)
    sample_rows: list[OhDetectionResultDraft] = Field(
        default_factory=list, description="前几行样例（预览展示用）"
    )


class OhDetectionParsePreview(BaseModel):
    """检测报告 PDF 解析预览（不落库）。"""

    report_no: str = Field(default="", description="识别的报告编号（可编辑）")
    report_name: str = Field(default="", description="报告名称")
    company_name: str = Field(default="", description="受检企业")
    detection_agency: str = Field(default="", description="检测机构")
    file_name: str = Field(default="", description="上传文件名")
    file_sha256: str = Field(default="", description="文件 SHA256")
    parse_mode: str = Field(default="rules", description="解析模式 rules/llm/mixed")
    table_count: int = Field(default=0, description="识别表格数")
    total_points: int = Field(default=0, description="检测记录数")
    exceed_points: int = Field(default=0, description="超标数")
    noise_post_points: int = Field(default=0, description="噪声作业岗位数")
    warnings: list[str] = Field(default_factory=list, description="全局解析警告")
    tables: list[OhDetectionTableSummary] = Field(default_factory=list)
    existing_report_id: UUID | None = Field(
        default=None, description="同编号已存在的报告 ID（导入将覆盖）"
    )
    existing_total_points: int = Field(
        default=0, description="同编号已存在报告的明细数（覆盖提示）"
    )


class OhDetectionReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    report_no: str
    report_name: str
    company_name: str
    detection_agency: str
    detection_date: date | None = None
    table_count: int
    total_points: int
    exceed_points: int
    noise_post_points: int
    source_file_name: str
    source_file_path: str
    source_file_sha256: str
    parse_mode: str
    parse_warnings: list[dict[str, Any]] | None = None
    remark: str
    created_by_name: str = Field(default="", description="导入人")
    created_at: datetime
    updated_at: datetime


class OhDetectionResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    report_id: UUID
    seq: int
    table_ref: str
    table_title: str
    factor_category: str
    factor_name: str
    record_type: str
    workshop: str
    post: str
    sample_point: str
    measured_value: str
    measured_value_num: float | None = None
    unit: str
    limit_type: str
    limit_value_num: float | None = None
    verdict: str
    is_noise_post: bool
    verdict_raw: str
    extra: dict[str, Any] | None = None


class OhDetectionImportResponse(BaseModel):
    report: OhDetectionReportResponse
    imported_count: int = Field(description="本次导入明细行数")
    replaced: bool = Field(default=False, description="是否覆盖了同编号已有报告")
    monitors_synced: int = Field(
        default=0, description="自动同步生成的危害因素监测记录数（按车间/点位分组）"
    )
    skipped_tables: list[dict[str, str]] = Field(
        default_factory=list, description="跳过的表格 [{table, reason}]"
    )


class OhDetectionListMeta(BaseModel):
    """报告列表聚合统计（全量非删除报告）。"""

    report_count: int = 0
    total_points: int = 0
    exceed_points: int = 0
    noise_post_points: int = 0
