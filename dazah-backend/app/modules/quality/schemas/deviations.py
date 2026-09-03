"""Deviation Pydantic schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DeviationBatchDeleteRequest(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=100)

    @field_validator("ids")
    @classmethod
    def unique_ids(cls, values: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(values)) != len(values):
            raise ValueError("不能重复选择同一偏差记录")
        return values


class DeviationBatchDeleteResult(BaseModel):
    deleted: int
    failed: list[uuid.UUID] = Field(default_factory=list)


class DeviationCreateResult(BaseModel):
    id: uuid.UUID
    code: str


class DeviationReporterOption(BaseModel):
    open_id: str
    name: str
    department: str


class DeviationReporterPage(BaseModel):
    items: list[DeviationReporterOption]
    total: int
    page: int
    page_size: int


class AiAnalysis(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    description: str | None = None
    reason: str | None = None
    risk_assessment: str | None = Field(default=None, alias="riskAssessment")
    capa_suggestion: str | None = Field(default=None, alias="capaSuggestion")


class InvestigationRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    nonconformity_description: str | None = Field(
        default=None, alias="nonconformityDescription"
    )
    root_cause_analysis: str | None = Field(default=None, alias="rootCauseAnalysis")
    risk_assessment: str | None = Field(default=None, alias="riskAssessment")
    urgent_measures: str | None = Field(default=None, alias="urgentMeasures")
    content: str | None = None
    author: str = ""
    department: str | None = None
    create_time: str = Field(default="", alias="createTime")
    attachments: list[str] | None = None
    is_modified: bool = Field(default=False, alias="isModified")
    modify_time: str | None = Field(default=None, alias="modifyTime")
    capa_proposals: list[dict[str, Any]] | None = Field(
        default=None, alias="capaProposals"
    )


class ReviewOpinion(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    content: str = ""
    author: str = ""
    step: str = ""
    result: str = "approved"
    create_time: str = Field(default="", alias="createTime")


class CrossDeptReviewer(BaseModel):
    department: str = ""
    investigators: list[str] = []


class RelatedCapaRef(BaseModel):
    id: uuid.UUID
    capa_code: str


class DeviationListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deviation_code: str
    final_code: str | None = None
    title: str
    department: str | None = None
    discovery_date: datetime | None = None
    discovery_time: str | None = None
    status: str
    level: str | None = None
    root_cause_category: str | None = None
    reporter_id: uuid.UUID | None = None
    handler: str | None = None
    batch_number: str | None = None
    affected_items: str | None = None
    description: str | None = None
    has_occurred_before: bool | None = None
    previous_occurrence_code: str | None = None
    material_disposition: str | None = None
    corrective_actions: str | None = None
    root_cause_analysis: str | None = None
    investigation_completed_at: datetime | None = None
    close_time: datetime | None = None
    related_capa_codes: list[str] | None = None
    related_capas: list[RelatedCapaRef] | None = None
    feishu_base_table_id: str | None = None
    feishu_base_record_id: str | None = None
    feishu_sync_status: str | None = "pending"
    feishu_last_sync_error: str | None = None
    feishu_last_sync_direction: str | None = None
    feishu_synced_at: datetime | None = None
    feishu_source_updated_at: datetime | None = None
    created_at: datetime
    status_updated_at: datetime | None = None
    returned_step: str | None = None


class DeviationReportRecordListItem(BaseModel):
    id: str
    deviation_id: uuid.UUID | None = None
    deviation_code: str | None = None
    report_time: datetime | None = None
    description: str | None = None
    report_document: str | None = None
    product_batch: str | None = None
    department: str | None = None
    reporter_name: str | None = None
    department_head: str | None = None
    department_head_result: str | None = None
    department_head_reviewed_at: datetime | None = None
    qa_name: str | None = None
    qa_result: str | None = None
    qa_reviewed_at: datetime | None = None
    qa_head_name: str | None = None
    qa_head_result: str | None = None
    qa_head_reviewed_at: datetime | None = None
    report_status: str | None = None
    attachments: list[dict[str, Any]] | None = None
    reporters: list[dict[str, Any]] | None = None
    department_heads: list[dict[str, Any]] | None = None
    qas: list[dict[str, Any]] | None = None
    qa_heads: list[dict[str, Any]] | None = None
    feishu_base_table_id: str | None = None
    feishu_base_record_id: str | None = None
    feishu_sync_status: str | None = None
    feishu_last_sync_error: str | None = None
    feishu_last_sync_direction: str | None = None
    feishu_synced_at: datetime | None = None
    feishu_source_updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class DeviationDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deviation_code: str
    final_code: str | None = None
    title: str
    department: str | None = None
    discovery_date: datetime | None = None
    discovery_time: str | None = None
    discovery_location: str | None = None
    status: str
    level: str | None = None
    root_cause_category: str | None = None
    description: str | None = None
    immediate_actions: str | None = None
    reporter_id: uuid.UUID | None = None
    handler: str | None = None
    discoverer: str | None = None
    ai_analysis: dict[str, Any] | None = None
    investigation_records: list[Any] | None = None
    review_opinions: list[Any] | None = None
    attachments: list[str] | None = None
    needs_cross_dept_review: bool | None = True
    cross_dept_reviewers: list[Any] | None = None
    affected_items: str | None = None
    batch_number: str | None = None
    has_occurred_before: bool | None = None
    previous_occurrence_code: str | None = None
    material_disposition: str | None = None
    corrective_actions: str | None = None
    root_cause_analysis: str | None = None
    investigation_completed_at: datetime | None = None
    returned_step: str | None = None
    status_updated_at: datetime | None = None
    report_content: str | None = None
    report_versions: list[Any] | None = None
    feishu_base_table_id: str | None = None
    feishu_base_record_id: str | None = None
    feishu_sync_status: str | None = "pending"
    feishu_last_sync_error: str | None = None
    feishu_last_sync_direction: str | None = None
    feishu_synced_at: datetime | None = None
    feishu_source_updated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CreateDeviationRequest(BaseModel):
    title: str | None = None
    department: str | None = None
    reporter_open_id: str | None = None
    discovery_date: str | None = None
    discovery_time: str | None = None
    discovery_location: str | None = None
    level: str | None = None
    root_cause_category: str | None = None
    description: str | None = None
    immediate_actions: str | None = None
    attachments: list[str] | None = None
    affected_items: str | None = None
    batch_number: str | None = None
    handler: str | None = None
    needs_cross_dept_review: bool | None = True
    cross_dept_reviewers: list[CrossDeptReviewer] | None = None
    has_occurred_before: bool | None = None
    previous_occurrence_code: str | None = None
    material_disposition: str | None = None
    corrective_actions: str | None = None
    root_cause_analysis: str | None = None
    investigation_completed_at: str | None = None
    is_closed: bool | None = None
    close_time: str | None = None


class UpdateDeviationRequest(BaseModel):
    title: str | None = None
    status: str | None = None
    level: str | None = None
    department: str | None = None
    discovery_date: str | None = None
    discovery_time: str | None = None
    discovery_location: str | None = None
    root_cause_category: str | None = None
    description: str | None = None
    immediate_actions: str | None = None
    ai_analysis: dict[str, Any] | None = None
    investigation_records: list[Any] | None = None
    review_opinions: list[Any] | None = None
    attachments: list[str] | None = None
    final_code: str | None = None
    handler: str | None = None
    discoverer: str | None = None
    needs_cross_dept_review: bool | None = None
    cross_dept_reviewers: list[CrossDeptReviewer] | None = None
    affected_items: str | None = None
    batch_number: str | None = None
    has_occurred_before: bool | None = None
    previous_occurrence_code: str | None = None
    material_disposition: str | None = None
    corrective_actions: str | None = None
    root_cause_analysis: str | None = None
    investigation_completed_at: str | None = None
    is_closed: bool | None = None
    close_time: str | None = None
    returned_step: str | None = None
    report_content: str | None = None
    report_versions: list[Any] | None = None


class SubmitReviewRequest(BaseModel):
    step: str
    result: str = "approved"
    content: str = ""
    reason_category: str | None = None
    deviation_level: str | None = None


class SubmitInvestigationRequest(BaseModel):
    description: str | None = None
    investigation_records: list[Any] | None = None
    nonconformity_description: str | None = None
    root_cause_analysis: str | None = None
    risk_assessment: str | None = None
    urgent_measures: str | None = None
    capa_proposals: list[dict[str, Any]] | None = None


class CompleteAiAnalysisRequest(BaseModel):
    ai_analysis: dict[str, Any] | None = None


class BatchUpdateStatusRequest(BaseModel):
    deviation_ids: list[uuid.UUID]
    target_status: str


class BatchUpdateStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    updated_count: int
    failed_count: int
    failures: list[dict[str, Any]]
