"""应急预案 AI 工作台的请求 / 响应模型。

预案正文以结构化文档保存：封面、引言、组织机构、车间应急组与 12 章正文
（每章为纯文本，支持 ``**加粗**``）。AI 生成、审核修正与对话修改的结果
都先经过这里的 Pydantic 校验，再写入正文与修订快照。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

ContentStatus = Literal["empty", "draft", "reviewed", "finalized"]
RevisionSource = Literal[
    "ai_generate", "ai_fix", "ai_chat", "user_edit", "import", "restore"
]
PlanLevel = Literal["company", "workshop"]
JobKind = Literal["generate", "review", "import"]
JobState = Literal["running", "completed", "failed", "interrupted"]

CHAPTER_KEY_PATTERN = r"^[a-z0-9_]{1,40}$"


# ---------- 结构化正文 ----------


class PlanCover(BaseModel):
    company: str = Field(default="", max_length=120, description="公司名称")
    title: str = Field(default="", max_length=200, description="预案标题")
    level: str = Field(default="", max_length=30, description="级别，如 公司级")
    drill_date: str = Field(default="", max_length=60, description="演练/实施时间")
    archive_date: str = Field(default="", max_length=60, description="建档时间")
    archive_department: str = Field(default="", max_length=100, description="建档部门")


class OrgGroup(BaseModel):
    name: str = Field(min_length=1, max_length=60, description="小组名称")
    leader: str = Field(default="", max_length=200, description="组长")
    members: str = Field(default="", max_length=1000, description="成员")
    duties: str = Field(default="", max_length=3000, description="小组职责")


class PlanOrganization(BaseModel):
    commander: str = Field(default="", max_length=100, description="总指挥")
    commander_duties: str = Field(default="", max_length=3000)
    deputy_commanders: list[str] = Field(default_factory=list, max_length=5)
    deputy_duties: str = Field(default="", max_length=3000)
    groups: list[OrgGroup] = Field(default_factory=list, max_length=20)


class WorkshopOrganization(BaseModel):
    department: str = Field(default="", max_length=100, description="车间/部门")
    commander: str = Field(default="", max_length=100, description="总指挥")
    deputy_commander: str = Field(default="", max_length=100, description="副指挥")
    groups: list[OrgGroup] = Field(default_factory=list, max_length=20)


class PlanChapter(BaseModel):
    key: str = Field(pattern=CHAPTER_KEY_PATTERN, description="章节标识")
    title: str = Field(min_length=1, max_length=100, description="章节标题")
    content: str = Field(default="", max_length=40000, description="章节正文")


class EmergencyPlanDocument(BaseModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    cover: PlanCover = Field(default_factory=PlanCover)
    preface: str = Field(default="", max_length=6000, description="引言")
    organization: PlanOrganization = Field(default_factory=PlanOrganization)
    workshop_organization: WorkshopOrganization | None = None
    chapters: list[PlanChapter] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def _unique_chapter_keys(self) -> EmergencyPlanDocument:
        keys = [chapter.key for chapter in self.chapters]
        if len(keys) != len(set(keys)):
            raise ValueError("章节标识不能重复")
        return self

    def chapter(self, key: str) -> PlanChapter | None:
        return next((item for item in self.chapters if item.key == key), None)


# ---------- 生成参数 ----------


class GenerateSubstance(BaseModel):
    chemical_id: UUID | None = Field(default=None, description="危化品档案 ID")
    name: str = Field(min_length=1, max_length=100, description="物质名称")


class EmergencyPlanGenerateRequest(BaseModel):
    level: PlanLevel = Field(default="company", description="预案级别")
    accident_type: str = Field(min_length=1, max_length=30, description="事故类型")
    location: str = Field(min_length=1, max_length=100, description="事故场所")
    location_detail: str = Field(default="", max_length=300, description="具体位置")
    substances: list[GenerateSubstance] = Field(default_factory=list, max_length=5)
    company: str = Field(default="", max_length=120, description="公司名称")
    drill_date: date | None = Field(default=None, description="演练日期")
    start_time: str = Field(
        default="14:00",
        pattern=r"^([01]?\d|2[0-3]):[0-5]\d$",
        description="情景起始时刻 HH:MM",
    )
    archive_department: str = Field(default="", max_length=100)
    participating_departments: list[str] = Field(default_factory=list, max_length=20)
    scenario_requirements: str = Field(default="", max_length=2000)
    organization: PlanOrganization = Field(default_factory=PlanOrganization)
    workshop_organization: WorkshopOrganization | None = None


# ---------- 审核与校验 ----------


class CheckIssue(BaseModel):
    code: str = Field(description="规则编码")
    severity: Literal["high", "medium", "low"]
    section: str = Field(description="所在章节标识或 cover/organization")
    quote: str = Field(default="", description="原文片段")
    message: str = Field(description="问题说明")
    replacement: str | None = Field(default=None, description="可确定修正的替换文本")


class ReviewDimension(BaseModel):
    name: str = Field(min_length=1, max_length=20)
    status: Literal["ok", "warn", "error"]
    note: str = Field(default="", max_length=500)


class ReviewIssue(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    source: Literal["rule", "ai"]
    severity: Literal["high", "medium", "low"]
    category: Literal[
        "contradiction", "technical", "compliance", "completeness", "typo", "format"
    ]
    section: str = Field(default="", max_length=60)
    quote: str = Field(default="", max_length=1000)
    problem: str = Field(min_length=1, max_length=1000)
    status: Literal["fixed", "needs_human", "unresolved", "info"]
    before: str = Field(default="", max_length=4000)
    after: str = Field(default="", max_length=4000)


class EmergencyPlanReviewReport(BaseModel):
    summary: str = Field(default="", max_length=2000)
    score: int = Field(default=0, ge=0, le=100)
    dimensions: list[ReviewDimension] = Field(default_factory=list)
    issues: list[ReviewIssue] = Field(default_factory=list)
    fixed_count: int = Field(default=0, ge=0)
    needs_human_count: int = Field(default=0, ge=0)
    rounds: int = Field(default=0, ge=0)
    reviewed_at: datetime | None = None


class EmergencyPlanChecksResponse(BaseModel):
    issues: list[CheckIssue]


# ---------- 内容与修订 ----------


class EmergencyPlanJobStatus(BaseModel):
    job_id: str
    kind: JobKind | None = None
    state: JobState
    progress: str = ""
    message: str = ""


class EmergencyPlanContentResponse(BaseModel):
    plan_id: UUID
    plan_name: str
    content_status: ContentStatus
    revision_no: int
    ai_generated: bool
    content: EmergencyPlanDocument | None = None
    last_review: EmergencyPlanReviewReport | None = None
    last_reviewed_at: datetime | None = None
    content_updated_at: datetime | None = None
    job: EmergencyPlanJobStatus | None = None


class EmergencyPlanContentUpdate(BaseModel):
    content: EmergencyPlanDocument
    base_revision_no: int = Field(ge=0, description="编辑所基于的修订号")
    summary: str = Field(default="人工编辑", max_length=200)


class RevisionChange(BaseModel):
    section: str = Field(default="", max_length=60)
    reason: str = Field(default="", max_length=1000)
    before: str = Field(default="", max_length=4000)
    after: str = Field(default="", max_length=4000)


class EmergencyPlanRevisionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    revision_no: int
    source: RevisionSource
    summary: str
    changed_sections: list[str] = Field(default_factory=list)
    created_at: datetime


class EmergencyPlanRevisionDetail(EmergencyPlanRevisionSummary):
    content: EmergencyPlanDocument
    changes: list[RevisionChange] = Field(default_factory=list)


class EmergencyPlanRevisionListResponse(BaseModel):
    items: list[EmergencyPlanRevisionSummary]


class EmergencyPlanJobSubmitted(BaseModel):
    job_id: str
    kind: JobKind


class EmergencyPlanImportResponse(BaseModel):
    content: EmergencyPlanContentResponse
    job_id: str | None = None


# ---------- 对话 ----------


class EmergencyPlanChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000, description="用户指令")
    section: str | None = Field(default=None, max_length=60, description="聚焦章节")


class OrgGroupPatch(BaseModel):
    """按组名合并的组织机构小组补丁（name 必填，其余缺省不改）。"""

    name: str = Field(min_length=1, max_length=60)
    leader: str | None = Field(default=None, max_length=200)
    members: str | None = Field(default=None, max_length=1000)
    duties: str | None = Field(default=None, max_length=3000)


class OrganizationPatch(BaseModel):
    commander: str | None = Field(default=None, max_length=100)
    commander_duties: str | None = Field(default=None, max_length=3000)
    deputy_commanders: list[str] | None = None
    deputy_duties: str | None = Field(default=None, max_length=3000)
    groups: list[OrgGroupPatch] | None = None


class WorkshopPatch(BaseModel):
    department: str | None = Field(default=None, max_length=100)
    commander: str | None = Field(default=None, max_length=100)
    deputy_commander: str | None = Field(default=None, max_length=100)
    groups: list[OrgGroupPatch] | None = None


class ChatEdit(BaseModel):
    target: Literal["chapter", "preface", "organization", "workshop_organization"]
    chapter_key: str | None = Field(default=None, pattern=CHAPTER_KEY_PATTERN)
    content: str | None = Field(default=None, max_length=40000)
    organization_patch: OrganizationPatch | None = None
    workshop_patch: WorkshopPatch | None = None
    summary: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def _payload_matches_target(self) -> ChatEdit:
        if self.target == "chapter" and (not self.chapter_key or self.content is None):
            raise ValueError("章节修改必须包含章节标识和正文")
        if self.target == "preface" and self.content is None:
            raise ValueError("引言修改必须包含正文")
        if self.target == "organization" and self.organization_patch is None:
            raise ValueError("组织机构修改必须包含组织机构补丁")
        if self.target == "workshop_organization" and self.workshop_patch is None:
            raise ValueError("车间应急组修改必须包含车间应急组补丁")
        return self


class EmergencyPlanChatMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: Literal["user", "assistant"]
    content: str
    revision_no: int | None = None
    created_at: datetime


class EmergencyPlanChatMessageListResponse(BaseModel):
    items: list[EmergencyPlanChatMessage]


# ---------- 向导选项 ----------


class OptionChemical(BaseModel):
    id: UUID
    name: str
    cas_no: str
    category: str
    has_msds: bool


class OptionBuilding(BaseModel):
    code: str
    name: str
    category: str


class OptionValue(BaseModel):
    value: str
    label: str


class EmergencyPlanAiOptions(BaseModel):
    chemicals: list[OptionChemical]
    buildings: list[OptionBuilding]
    accident_types: list[OptionValue]
    levels: list[OptionValue]
    default_company: str
    default_organization: PlanOrganization
    default_workshop_organization: WorkshopOrganization
    recent_organization: PlanOrganization | None = None
    recent_workshop_organization: WorkshopOrganization | None = None
