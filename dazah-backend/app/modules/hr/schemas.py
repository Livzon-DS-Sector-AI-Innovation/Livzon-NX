"""HR business request and response schemas live here."""

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ─── Department-level Approval Config Schemas ───


class DeptApprovalConfigCreate(BaseModel):
    """部门级审批人配置 - 创建（部门表为空时 department_id 可空，按名称展示）"""

    department_id: UUID | None = None
    department_name: str = Field(..., max_length=64)
    direct_leader_name: str | None = Field(None, max_length=64)
    direct_leader_open_id: str | None = Field(None, max_length=64)
    manager_name: str | None = Field(None, max_length=64)
    manager_open_id: str | None = Field(None, max_length=64)
    director_name: str | None = Field(None, max_length=64)
    director_open_id: str | None = Field(None, max_length=64)
    vp_name: str | None = Field(None, max_length=64)
    vp_open_id: str | None = Field(None, max_length=64)
    sort_order: int = 0


class DeptApprovalConfigUpdate(BaseModel):
    """部门级审批人配置 - 更新（所有字段可选）"""

    direct_leader_name: str | None = None
    direct_leader_open_id: str | None = None
    manager_name: str | None = None
    manager_open_id: str | None = None
    director_name: str | None = None
    director_open_id: str | None = None
    vp_name: str | None = None
    vp_open_id: str | None = None
    sort_order: int | None = None


# ─── Department Schemas ───


class DepartmentBase(BaseModel):
    name: str = Field(..., max_length=64, description="部门名称")
    code: str = Field("", max_length=32, description="部门编码（可选，留空时使用名称）")
    description: str | None = Field(None, max_length=256, description="部门描述")
    leader_name: str | None = Field(None, max_length=64, description="部门负责人")
    parent_id: UUID | None = Field(None, description="父部门ID")
    sort_order: int = Field(0, description="排序顺序")
    headcount: int | None = Field(None, ge=0, description="编制人数")
    responsibilities: str | None = Field(
        None, max_length=2000, description="部门职责描述"
    )
    category: str | None = Field(None, max_length=32, description="部门分类")


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    name: str | None = Field(None, max_length=64)
    code: str | None = Field(None, max_length=32)
    description: str | None = Field(None, max_length=256)
    leader_name: str | None = Field(None, max_length=64)
    parent_id: UUID | None = Field(None)
    sort_order: int | None = Field(None)
    headcount: int | None = Field(None, ge=0)
    responsibilities: str | None = Field(None, max_length=2000)
    category: str | None = Field(None, max_length=32)


class DepartmentResponse(DepartmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    feishu_open_department_id: str | None = None
    current_count: int | None = 0
    vacancy: int | None = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DepartmentTreeResponse(DepartmentResponse):
    children: list["DepartmentTreeResponse"] = []


# ─── Team Schemas ───


class TeamBase(BaseModel):
    name: str = Field(..., max_length=64, description="班组名称")
    code: str | None = Field(None, max_length=32, description="班组编码")
    description: str | None = Field(None, max_length=256, description="班组描述")
    department_id: UUID = Field(..., description="所属部门ID")


class TeamCreate(TeamBase):
    pass


class TeamUpdate(BaseModel):
    name: str | None = Field(None, max_length=64)
    code: str | None = Field(None, max_length=32)
    description: str | None = Field(None, max_length=256)
    department_id: UUID | None = Field(None)


class TeamResponse(TeamBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    department: DepartmentResponse | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ─── Employee Schemas ───


def _empty_str_to_none(v: Any) -> Any:
    """空字符串转 None，避免 date/int 等类型解析失败"""
    if v == "" or v is None:
        return None
    return v


class EmployeeBase(BaseModel):
    # Core
    employee_number: str | None = Field(None, max_length=32, description="工号")
    seq_number: int | None = Field(None, description="序号（飞书自动编号）")
    name: str = Field(..., max_length=64, description="姓名")
    domain_account: str | None = Field(None, max_length=64, description="域账号")

    # Department & job
    department: str = Field(..., max_length=64, description="部门")
    sub_department: str | None = Field(None, max_length=64, description="二级部门")
    team: str | None = Field(None, max_length=64, description="班组")
    position: str = Field(..., max_length=64, description="职位")
    job_category: str | None = Field(None, max_length=32, description="职类")
    level: str | None = Field(None, max_length=32, description="级别")
    employment_type: str | None = Field(None, max_length=32, description="人员就业方式")

    # Qualifications
    qualifications: list[str] | None = Field(None, description="职称／职业资格")
    qualification_type: str | None = Field(None, max_length=32, description="职称类型")
    certificate_number: str | None = Field(None, max_length=64, description="证书编号")
    certificate_review_date: date | None = Field(None, description="技能证书复审时间")

    # Personal
    gender: str | None = Field(None, max_length=8, description="性别")
    ethnic_group: str | None = Field(None, max_length=32, description="民族")
    native_place: str | None = Field(None, max_length=64, description="籍贯")
    political_status: str | None = Field(None, max_length=32, description="政治面貌")
    marital_status: str | None = Field(None, max_length=16, description="婚姻状况")
    health_status: str | None = Field(None, max_length=32, description="健康状况")
    household_type: str | None = Field(None, max_length=16, description="户籍类型")
    status_category: str | None = Field(None, max_length=32, description="统计类别")

    # Birth
    birth_year: int | None = Field(None, description="出生年份")
    birth_month: int | None = Field(None, description="出生月份")
    birth_day: int | None = Field(None, description="出生日期")
    age: int | None = Field(None, description="年龄")

    # Dates
    work_start_date: date | None = Field(None, description="参加工作时间")
    factory_entry_date: date | None = Field(None, description="进厂时间")
    livo_entry_date: date | None = Field(None, description="入丽珠时间")
    hire_date: date = Field(..., description="入职日期")
    graduation_date: date | None = Field(None, description="毕业时间")

    # Computed
    work_years: int | None = Field(None, description="工作年限")
    factory_tenure: str | None = Field(None, max_length=32, description="厂龄")
    company_tenure: str | None = Field(None, max_length=32, description="司龄")

    # Education
    education: str | None = Field(None, max_length=16, description="学历")
    degree: str | None = Field(None, max_length=32, description="学位")
    classification: str | None = Field(None, max_length=16, description="分类")
    school: str | None = Field(None, max_length=128, description="毕业学校")
    major: str | None = Field(None, max_length=64, description="专业")

    # ID & address
    id_card: str | None = Field(None, max_length=18, description="身份证号")
    id_card_expiry: str | None = Field(None, max_length=32, description="身份证到期日")
    id_card_address: str | None = Field(None, description="身份证地址|家庭地址")
    current_address: str | None = Field(None, description="现住址")

    # Contract
    contract_type: str | None = Field(None, max_length=32, description="合同期限")
    contract_start_date: date | None = Field(None, description="合同开始日期")
    contract_end_date: date | None = Field(None, description="合同结束日期")
    contract_start_2: date | None = Field(None, description="第二次合同起点")
    contract_end_2: date | None = Field(None, description="第二次合同终止")
    contract_start_3: date | None = Field(None, description="第三次合同起点")
    contract_end_3: date | None = Field(None, description="第三次合同终止")
    contract_start_4: date | None = Field(None, description="第四次合同起点")
    contract_end_4: date | None = Field(None, description="第四次合同终止")
    contract_start_5: date | None = Field(None, description="第五次续签合同日期")
    contract_end_5: str | None = Field(None, max_length=32, description="合同截止日期5")
    contract_start_6: str | None = Field(
        None, max_length=32, description="第六次续签合同日期"
    )
    contract_end_6: str | None = Field(None, max_length=32, description="合同截止日期6")
    contract_opinion: str | None = Field(
        None, max_length=32, description="合同审批意见: 同意续签/不同意续签"
    )
    dept_leader_name: str | None = Field(
        None, max_length=64, description="合同审批负责人"
    )

    # Contact
    phone: str | None = Field(None, max_length=32, description="手机")
    email: str | None = Field(None, max_length=128, description="邮箱")
    emergency_contact_name: str | None = Field(
        None, max_length=64, description="紧急联系人姓名"
    )
    emergency_contact_phone: str | None = Field(
        None, max_length=32, description="紧急联系人电话"
    )
    emergency_contact_relation: str | None = Field(
        None, max_length=32, description="紧急联系人关系"
    )

    # Banking & training
    bank_account: str | None = Field(None, max_length=32, description="银行卡号")
    training_id: str | None = Field(None, max_length=32, description="培训档案编号")
    archive_number: str | None = Field(None, max_length=32, description="档案编号")

    # Work experience
    work_experience_1: str | None = Field(None, description="工作经验一")
    work_experience_2: str | None = Field(None, description="工作经验二")
    work_experience_3: str | None = Field(None, description="工作经验三")
    work_experience_4: str | None = Field(None, description="工作经验四")

    # Other
    transfer_history: str | None = Field(None, description="异动记录")
    remarks: list[str] | None = Field(None, description="备注")
    status: str = Field("待审批", max_length=16, description="状态")

    # Probation & offboarding
    probation_status: str | None = Field(None, max_length=32, description="转正状态")
    planned_probation_date: date | None = Field(None, description="拟转正日期")
    probation_effective_date: date | None = Field(None, description="转正生效日期")
    last_working_day: date | None = Field(None, description="最后工作日")
    offboarding_type: str | None = Field(None, max_length=16, description="离职类型")
    offboarding_reason: str | None = Field(None, max_length=512, description="离职原因")

    # 空字符串 -> None，防止前端传空字符串导致 date/int 类型校验失败
    @field_validator(
        "employee_number",
        "domain_account",
        "sub_department",
        "team",
        "job_category",
        "level",
        "employment_type",
        "qualification_type",
        "certificate_number",
        "certificate_review_date",
        "gender",
        "ethnic_group",
        "native_place",
        "political_status",
        "marital_status",
        "health_status",
        "household_type",
        "status_category",
        "education",
        "degree",
        "classification",
        "school",
        "major",
        "id_card",
        "id_card_expiry",
        "id_card_address",
        "current_address",
        "contract_type",
        "work_start_date",
        "factory_entry_date",
        "livo_entry_date",
        "graduation_date",
        "hire_date",
        "contract_start_date",
        "contract_end_date",
        "contract_start_2",
        "contract_end_2",
        "contract_start_3",
        "contract_end_3",
        "contract_start_4",
        "contract_end_4",
        "contract_start_5",
        "contract_end_5",
        "contract_start_6",
        "contract_end_6",
        "contract_opinion",
        "dept_leader_name",
        "phone",
        "email",
        "emergency_contact_name",
        "emergency_contact_phone",
        "emergency_contact_relation",
        "bank_account",
        "training_id",
        "archive_number",
        "transfer_history",
        "probation_status",
        "planned_probation_date",
        "probation_effective_date",
        "last_working_day",
        "offboarding_type",
        "offboarding_reason",
        "work_experience_1",
        "work_experience_2",
        "work_experience_3",
        "work_experience_4",
        "factory_tenure",
        "company_tenure",
        mode="before",
    )
    @classmethod
    def _strip_empty(cls: Any, v: Any) -> Any:
        if v == "":
            return None
        return v

    @field_validator(
        "seq_number",
        "birth_year",
        "birth_month",
        "birth_day",
        "age",
        "work_years",
        mode="before",
    )
    @classmethod
    def _strip_empty_int(cls: Any, v: Any) -> Any:
        if v == "" or v is None:
            return None
        return v


class EmployeeCreate(EmployeeBase):
    pass


class EmployeePublicCreate(BaseModel):
    """扫码公开创建员工的请求体（工号留空，不需要登录）"""

    # 基本信息（必填）
    name: str = Field(..., max_length=64, description="姓名")
    department: str = Field(..., max_length=64, description="部门")
    position: str = Field(..., max_length=64, description="职位")
    hire_date: date = Field(..., description="入职日期")

    # 基本信息（选填）
    domain_account: str | None = Field(None, max_length=64)
    sub_department: str | None = Field(None, max_length=64)
    team: str | None = Field(None, max_length=64)
    job_category: str | None = Field(None, max_length=32)
    level: str | None = Field(None, max_length=32)
    employment_type: str | None = Field(None, max_length=32)
    gender: str | None = Field(None, max_length=8)

    # 个人信息
    native_place: str | None = Field(None, max_length=64)
    ethnic_group: str | None = Field(None, max_length=32)
    political_status: str | None = Field(None, max_length=32)
    marital_status: str | None = Field(None, max_length=16)
    health_status: str | None = Field(None, max_length=32)
    household_type: str | None = Field(None, max_length=16)
    status_category: str | None = Field(None, max_length=32)
    birth_year: int | None = Field(None)
    birth_month: int | None = Field(None)
    birth_day: int | None = Field(None)
    id_card: str | None = Field(None, max_length=18)
    id_card_expiry: str | None = Field(None, max_length=32)

    # 联系信息
    phone: str | None = Field(None, max_length=32)
    email: str | None = Field(None, max_length=128)
    id_card_address: str | None = Field(None)
    current_address: str | None = Field(None)
    emergency_contact_name: str | None = Field(None, max_length=64)
    emergency_contact_phone: str | None = Field(None, max_length=32)
    emergency_contact_relation: str | None = Field(None, max_length=32)

    # 学历职业
    education: str | None = Field(None, max_length=16)
    degree: str | None = Field(None, max_length=32)
    classification: str | None = Field(None, max_length=16)
    school: str | None = Field(None, max_length=128)
    major: str | None = Field(None, max_length=64)
    qualification_type: str | None = Field(None, max_length=32)
    qualifications: list[str] | None = Field(None)
    certificate_number: str | None = Field(None, max_length=64)
    certificate_review_date: date | None = Field(None)
    work_start_date: date | None = Field(None)

    # 其他
    bank_account: str | None = Field(None, max_length=32)
    training_id: str | None = Field(None, max_length=32)
    archive_number: str | None = Field(None, max_length=32)
    work_experience_1: str | None = Field(None)
    work_experience_2: str | None = Field(None)
    work_experience_3: str | None = Field(None)
    work_experience_4: str | None = Field(None)


class EmployeeUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")

    employee_number: str | None = Field(None, max_length=32)
    name: str | None = Field(None, max_length=64)
    domain_account: str | None = Field(None, max_length=64)
    department: str | None = Field(None, max_length=64)
    team: str | None = Field(None, max_length=64)
    position: str | None = Field(None, max_length=64)
    job_category: str | None = Field(None, max_length=32)
    level: str | None = Field(None, max_length=32)
    qualifications: list[str] | None = Field(None)
    qualification_type: str | None = Field(None, max_length=32)
    gender: str | None = Field(None, max_length=8)
    native_place: str | None = Field(None, max_length=64)
    political_status: str | None = Field(None, max_length=32)
    marital_status: str | None = Field(None, max_length=16)
    household_type: str | None = Field(None, max_length=16)
    status_category: str | None = Field(None, max_length=32)
    birth_year: int | None = Field(None)
    birth_month: int | None = Field(None)
    birth_day: int | None = Field(None)
    age: int | None = Field(None)
    work_start_date: date | None = Field(None)
    factory_entry_date: date | None = Field(None)
    livo_entry_date: date | None = Field(None)
    hire_date: date | None = Field(None)
    graduation_date: date | None = Field(None)
    work_years: int | None = Field(None)
    factory_tenure: str | None = Field(None, max_length=32)
    company_tenure: str | None = Field(None, max_length=32)
    education: str | None = Field(None, max_length=16)
    classification: str | None = Field(None, max_length=16)
    school: str | None = Field(None, max_length=128)
    major: str | None = Field(None, max_length=64)
    id_card: str | None = Field(None, max_length=18)
    id_card_expiry: str | None = Field(None, max_length=32)
    id_card_address: str | None = Field(None)
    current_address: str | None = Field(None)
    contract_type: str | None = Field(None, max_length=32)
    contract_start_date: date | None = Field(None)
    contract_end_date: date | None = Field(None)
    contract_start_2: date | None = Field(None)
    contract_end_2: date | None = Field(None)
    contract_start_3: date | None = Field(None)
    contract_end_3: date | None = Field(None)
    contract_start_4: date | None = Field(None)
    contract_end_4: date | None = Field(None)
    phone: str | None = Field(None, max_length=32)
    email: str | None = Field(None, max_length=128)
    emergency_contact_name: str | None = Field(None, max_length=64)
    emergency_contact_phone: str | None = Field(None, max_length=32)
    emergency_contact_relation: str | None = Field(None, max_length=32)
    bank_account: str | None = Field(None, max_length=32)
    training_id: str | None = Field(None, max_length=32)
    transfer_history: str | None = Field(None)
    remarks: list[str] | None = Field(None)
    status: str | None = Field(None, max_length=16)
    contract_opinion: str | None = Field(None, max_length=32)
    dept_leader_name: str | None = Field(None, max_length=64)


class EmployeeResponse(EmployeeBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    feishu_open_id: str | None = None
    feishu_record_id: str | None = None
    feishu_synced_at: date | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SyncStatusResponse(BaseModel):
    local_total: int
    feishu_total: int
    synced_count: int
    unsynced_count: int
    conflict_count: int
    last_sync_at: datetime | None = None


# ─── Legacy turnover compatibility schemas ───
#
# The former factory pages still submit these records.  The actual storage
# remains the historical ``hr.onboarding_records``/``hr.departure_records``
# tables; these schemas deliberately accept additional columns so old clients
# do not lose fields that are not used by the current service layer.


class TrainingNotifyInput(BaseModel):
    """Send a training notification through the legacy Feishu endpoint."""

    employee_numbers: list[str] = Field(..., description="受训人员工号列表")
    department: str | None = Field(None, max_length=64, description="主办部门")
    subject: str = Field(..., max_length=128, description="培训主题")
    training_date: date = Field(..., description="培训日期")
    training_time_start: str | None = Field(None, max_length=32)
    training_time_end: str | None = Field(None, max_length=32)
    location: str | None = Field(None, max_length=128)
    trainer: str | None = Field(None, max_length=64)
    content: str | None = Field(None, max_length=512)
    training_method: str | None = Field(None, max_length=32)
    issuer_department: str | None = Field(None, max_length=64)
    issue_date: date | None = None


class DepartureRecordCreate(BaseModel):
    """Minimum contract for the former departure ledger create endpoint."""

    model_config = ConfigDict(extra="allow")

    name: str = Field(..., max_length=64)
    department: str = Field(..., max_length=64)
    position: str = Field(..., max_length=64)
    offboarding_type: str = Field("辞职", max_length=16)
    team: str | None = None
    job_category: str | None = None
    gender: str | None = None
    status_category: str | None = None
    livo_entry_date: date | None = None
    factory_entry_date: date | None = None
    work_start_date: date | None = None
    offboarding_date: date | None = None
    company_tenure_at_leave: str | None = None
    education: str | None = None
    school: str | None = None
    major: str | None = None
    classification: str | None = None
    id_card: str | None = None
    native_place: str | None = None
    household_type: str | None = None
    marital_status: str | None = None
    political_status: str | None = None
    phone: str | None = None
    emergency_contact_phone: str | None = None
    emergency_contact_relation: str | None = None
    bank_account: str | None = None
    contract_type: str | None = None
    transfer_history: str | None = None
    offboarding_reason: list[str] | None = None
    offboarding_reason_2: list[str] | None = None
    offboarding_remarks: list[str] | None = None
    remarks: str | None = None


class DepartureRecordUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = Field(None, max_length=64)
    department: str | None = Field(None, max_length=64)
    position: str | None = Field(None, max_length=64)
    offboarding_type: str | None = Field(None, max_length=16)
    team: str | None = None
    job_category: str | None = None
    gender: str | None = None
    status_category: str | None = None
    livo_entry_date: date | None = None
    factory_entry_date: date | None = None
    work_start_date: date | None = None
    offboarding_date: date | None = None
    company_tenure_at_leave: str | None = None
    education: str | None = None
    school: str | None = None
    major: str | None = None
    classification: str | None = None
    id_card: str | None = None
    native_place: str | None = None
    household_type: str | None = None
    marital_status: str | None = None
    political_status: str | None = None
    phone: str | None = None
    emergency_contact_phone: str | None = None
    emergency_contact_relation: str | None = None
    bank_account: str | None = None
    contract_type: str | None = None
    transfer_history: str | None = None
    offboarding_reason: list[str] | None = None
    offboarding_reason_2: list[str] | None = None
    offboarding_remarks: list[str] | None = None
    remarks: str | None = None


class OnboardingRecordCreate(BaseModel):
    """Minimum contract for legacy onboarding imports."""

    model_config = ConfigDict(extra="allow")

    employee_number: str = Field(..., max_length=32)
    name: str = Field(..., max_length=64)
    department: str = Field(..., max_length=64)
    position: str = Field(..., max_length=64)
    hire_date: date
    seq_number: int | None = None
    team: str | None = None
    job_category: str | None = None
    status_category: str | None = None
    is_employed: str | None = None
    factory_entry_date: date | None = None
    livo_entry_date: date | None = None
    work_start_date: date | None = None
    graduation_date: date | None = None
    email: str | None = None
    phone: str | None = None
    remarks: list[str] | None = None


class OnboardingRecordUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")

    employee_number: str | None = Field(None, max_length=32)
    name: str | None = Field(None, max_length=64)
    department: str | None = Field(None, max_length=64)
    position: str | None = Field(None, max_length=64)
    hire_date: date | None = None
    seq_number: int | None = None
    team: str | None = None
    job_category: str | None = None
    status_category: str | None = None
    is_employed: str | None = None
    factory_entry_date: date | None = None
    livo_entry_date: date | None = None
    work_start_date: date | None = None
    graduation_date: date | None = None
    email: str | None = None
    phone: str | None = None
    remarks: list[str] | None = None


class TrainingSignInSheetInput(BaseModel):
    training_date: date = Field(..., description="培训日期")
    training_time_start: str | None = Field(
        None, max_length=32, description="培训开始时间"
    )
    training_time_end: str | None = Field(
        None, max_length=32, description="培训结束时间"
    )
    department: str = Field(
        ..., max_length=256, description="受训部门（多部门时用、拼接）"
    )
    training_subject: str | None = Field(None, max_length=128, description="培训主题")
    topic: str = Field(..., max_length=256, description="培训题目或内容概要")
    instructor: str | None = Field(None, max_length=64, description="授课人")
    location: str | None = Field(None, max_length=128, description="培训地点")
    training_method: str | None = Field(None, max_length=32, description="培训方式")
    employee_names: list[str] = Field(
        default_factory=list, description="应出席受训人员姓名列表"
    )
    employee_dept_map: dict[str, str] | None = Field(
        None, description="人员姓名→所属部门（签到表数据行每人显示自己部门）"
    )
    remarks: str | None = Field(None, max_length=512, description="备注")


class TrainingNotificationInput(BaseModel):
    department: str = Field(..., max_length=64, description="主办部门")
    training_date: date = Field(..., description="培训日期")
    subject: str = Field(..., max_length=2048, description="培训主题")
    training_time_start: str | None = Field(
        None, max_length=32, description="培训开始时间"
    )
    training_time_end: str | None = Field(
        None, max_length=32, description="培训结束时间"
    )
    location: str | None = Field(None, max_length=128, description="培训地点")
    trainer: str | None = Field(None, max_length=64, description="培训师")
    content: str | None = Field(None, max_length=512, description="培训内容")
    trainee_names: list[str] = Field(
        default_factory=list, description="培训人员姓名列表"
    )
    issuer_department: str | None = Field(None, max_length=64, description="落款部门")
    issue_date: date | None = Field(None, description="落款日期")
    assessment_method: str | None = Field(
        None, max_length=32, description="六、培训考核方式"
    )
    training_level: str | None = Field(
        None,
        max_length=16,
        description="培训级别：公司级/部门级（五、培训要求第1条插入）",
    )


class TrainingEvaluationInput(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)
    subject: str = Field(..., max_length=2048, description="培训主题/培训内容")
    training_date: date | None = Field(None, description="培训日期")
    training_time_start: str | None = Field(
        None, max_length=32, description="培训开始时间"
    )
    training_time_end: str | None = Field(
        None, max_length=32, description="培训结束时间"
    )
    duration_hours: float | None = Field(None, description="学时")
    training_method: str | None = Field(None, max_length=32, description="培训方式")
    is_exam: bool = Field(False, description="是否考试")
    trainer_type: str | None = Field(None, max_length=64, description="培训人员类型")
    trainer: str | None = Field(None, max_length=64, description="授课人")
    department_personnel: str | None = Field(
        None, max_length=256, description="部门/班组/人员"
    )
    expected_count: int | None = Field(None, description="应出席人数")
    actual_count: int | None = Field(None, description="实际出席人数")
    absent_count: int | None = Field(None, description="缺席人数")
    textbook: str | None = Field(
        None, max_length=2048, description="培训教材（可含多份教材清单）"
    )
    makeup_training: bool | None = Field(None, description="是否补课")
    assessment_method: str | None = Field(None, max_length=32, description="考核方式")
    pass_count: int | None = Field(None, description="合格人数")
    fail_count: int | None = Field(None, description="不合格人数")
    absent_exam_count: int | None = Field(None, description="缺考人数")
    absent_exam_handling: str | None = Field(
        None, max_length=512, description="缺考人员处理方式和原因"
    )
    excellent_count: int | None = Field(None, description="优秀人数")
    qualified_count: int | None = Field(None, description="合格人数")
    unqualified_count: int | None = Field(None, description="不合格人数")
    evaluation_conclusion: str | None = Field(
        None, max_length=1024, description="培训效果评估及结论"
    )
    organizer: str | None = Field(None, max_length=64, description="培训组织人")
    organizer_date: date | None = Field(None, description="组织日期")
    remarks: str | None = Field(None, max_length=512, description="备注")
    # ── APP4 模板扩展字段（培训资料评估表页签导出，与 APP4 表格逐项对应）──
    other_method: str | None = Field(None, max_length=64, description="其他方式说明")
    instructor: str | None = Field(None, max_length=64, description="授课人")
    target_dept_person: str | None = Field(
        None, max_length=256, description="培训对象（部门/班组/人员）"
    )
    absent_handling: str | None = Field(
        None, max_length=512, description="缺席人员处理方式"
    )
    need_retraining: bool | None = Field(None, description="是否再培训")
    retraining_info: str | None = Field(
        None, max_length=512, description="再培训（时间、地点、方式等）"
    )
    good_count: int | None = Field(None, description="良好人数")
    fail_handling: str | None = Field(
        None, max_length=512, description="缺考及不合格人员处理方式"
    )
    makeup_count: int | None = Field(None, description="补考人数")
    makeup_pass_count: int | None = Field(None, description="补考合格人数")
    makeup_fail_count: int | None = Field(None, description="补考不合格人数")
    makeup_fail_handling: str | None = Field(
        None, max_length=512, description="缺考及补考不合格人员处理方式"
    )
    evaluation_result: str | None = Field(
        None, max_length=128, description="培训效果评估结论(勾选项)"
    )
    evaluation_comment: str | None = Field(
        None, max_length=1024, description="培训效果评估及其他(补充文本)"
    )
    evaluator: str | None = Field(None, max_length=64, description="培训评估人")
    evaluate_date: date | None = Field(None, description="评估日期")
    has_notification: bool | None = Field(None, description="附件：培训通知 有")
    has_signin_sheet: bool | None = Field(None, description="附件：培训签到表 有")
    has_textbook: bool | None = Field(None, description="附件：培训使用教材 有")
    has_exam_paper: bool | None = Field(
        None, description="附件：考核试题、试卷、问卷 有"
    )
    has_score_summary: bool | None = Field(None, description="附件：考核成绩汇总表 有")
    has_notification_qty: str | None = Field(
        None, max_length=32, description="附件1数量"
    )
    has_signin_sheet_qty: str | None = Field(
        None, max_length=32, description="附件2数量"
    )
    has_textbook_qty: str | None = Field(None, max_length=32, description="附件3数量")
    has_exam_paper_qty: str | None = Field(None, max_length=32, description="附件4数量")
    has_score_summary_qty: str | None = Field(
        None, max_length=32, description="附件5数量"
    )
    other_attachment: str | None = Field(
        None, max_length=256, description="其他附件说明"
    )


class OnboardingEvaluationInput(BaseModel):
    employee_name: str = Field(..., max_length=64, description="员工姓名")
    employee_number: str | None = Field(None, max_length=32, description="工作卡号")
    gender: str | None = Field(None, max_length=8, description="性别")
    department_position: str | None = Field(
        None, max_length=128, description="所在部门/岗位"
    )
    hire_date: date | None = Field(None, description="入厂时间")
    training_period: str | None = Field(None, max_length=64, description="培训/考核期")
    regularization_date: date | None = Field(None, description="转正时间")
    assessment_contents: list[str] = Field(
        default_factory=list, description="上岗培训期内考核内容"
    )
    comprehensive_comment: str | None = Field(
        None, max_length=1024, description="培训/考核期综合评语"
    )
    is_qualified: bool | None = Field(None, description="是否同意上岗")
    assigned_position: str | None = Field(None, max_length=64, description="担任岗位")
    assessment_method: str | None = Field(None, max_length=32, description="考核方式")
    dept_manager_signature: str | None = Field(
        None, max_length=64, description="部门负责人签名"
    )
    signature_date: date | None = Field(None, description="签名日期")
    remarks: str | None = Field(None, max_length=512, description="备注")
    dept_manager_agree: bool | None = Field(None, description="部门负责人是否同意")
    hr_manager_agree: bool | None = Field(None, description="人事行政部负责人是否同意")
    qa_manager_agree: bool | None = Field(None, description="质量管理负责人是否同意")
    dept_manager: str | None = Field(None, max_length=64, description="部门负责人")
    hr_manager: str | None = Field(None, max_length=64, description="人事行政部负责人")
    qa_manager: str | None = Field(None, max_length=64, description="质量管理负责人")
    approval_date: date | None = Field(None, description="审批日期")


# ─── OffboardingRecord Schemas ───


class OffboardingRecordBase(BaseModel):
    """离职管理记录 - 离职人员完整档案快照"""

    # Employee relationship
    employee_id: UUID | None = Field(None, description="员工ID")

    # Core identifiers
    seq_number: int | None = Field(None, description="序号")
    employee_number: str | None = Field(None, max_length=32, description="工号")
    name: str | None = Field(None, max_length=64, description="姓名")
    domain_account: str | None = Field(None, max_length=64, description="域账号")

    # Personal info
    gender: str | None = Field(None, max_length=8, description="性别")
    ethnic_group: str | None = Field(None, max_length=32, description="民族")
    native_place: str | None = Field(None, max_length=64, description="籍贯")
    political_status: str | None = Field(None, max_length=32, description="政治面貌")
    marital_status: str | None = Field(None, max_length=16, description="婚姻状况")
    health_status: str | None = Field(None, max_length=32, description="健康状况")
    household_type: str | None = Field(None, max_length=16, description="户籍类型")
    status_category: str | None = Field(None, max_length=32, description="统计类别")

    # Birth date
    birth_year: int | None = Field(None, description="出生年份")
    birth_month: int | None = Field(None, description="出生月份")
    birth_day: int | None = Field(None, description="出生日期")
    age: int | None = Field(None, description="年龄")

    # ID & address
    id_card: str | None = Field(None, max_length=18, description="身份证号")
    id_card_expiry: str | None = Field(
        None, max_length=32, description="身份证有效期截止日期"
    )
    current_address: str | None = Field(None, description="现居住地址")

    # Contact
    phone: str | None = Field(None, max_length=32, description="联系电话")
    email: str | None = Field(None, max_length=128, description="电子邮箱")
    emergency_contact_name: str | None = Field(
        None, max_length=64, description="紧急联系人"
    )
    emergency_contact_phone: str | None = Field(
        None, max_length=32, description="紧急联系人电话"
    )
    emergency_contact_relation: str | None = Field(
        None, max_length=32, description="与本人关系"
    )

    # Department & job
    department: str | None = Field(None, max_length=64, description="一级部门")
    sub_department: str | None = Field(None, max_length=64, description="二级部门")
    position: str | None = Field(None, max_length=64, description="职位/岗位")
    level: str | None = Field(None, max_length=32, description="职级")
    employment_type: str | None = Field(None, max_length=32, description="人员就业方式")
    probation_status: str | None = Field(None, max_length=32, description="转正状态")
    probation_effective_date: date | None = Field(None, description="转正生效日期")

    # Career dates
    hire_date: date | None = Field(None, description="入职日期")
    work_start_date: date | None = Field(None, description="参加工作时间")
    factory_entry_date: date | None = Field(None, description="进本公司时间")
    livo_entry_date: date | None = Field(None, description="入丽珠时间")
    work_years: str | None = Field(None, max_length=16, description="工龄")
    offboarding_date: date | None = Field(None, description="最后工作日")

    # Offboarding specific
    offboarding_type: str = Field("辞职", max_length=16, description="离职类型")
    reason: str | None = Field(None, max_length=512, description="离职原因")
    status: str = Field("在职", max_length=16, description="在职状态")

    # Education
    education: str | None = Field(None, max_length=16, description="学历")
    degree: str | None = Field(None, max_length=32, description="学位")
    major: str | None = Field(None, max_length=64, description="专业")
    school: str | None = Field(None, max_length=128, description="毕业院校")
    graduation_date: date | None = Field(None, description="毕业时间")

    # Qualifications
    qualification_type: str | None = Field(None, max_length=32, description="职称")
    qualifications: list[str] | None = Field(None, description="技能证书")
    certificate_number: str | None = Field(None, max_length=64, description="证书编号")
    certificate_review_date: date | None = Field(None, description="技能证书复审时间")

    # Contract
    contract_start_date: date | None = Field(None, description="首次签订合同日期")
    contract_end_date: date | None = Field(None, description="首次签订合同截止日期")
    contract_end_2: str | None = Field(None, max_length=32, description="合同截止日期2")
    contract_end_3: str | None = Field(None, max_length=32, description="合同截止日期3")
    contract_end_4: str | None = Field(None, max_length=32, description="合同截止日期4")
    contract_end_5: str | None = Field(None, max_length=32, description="合同截止日期5")
    contract_start_2: date | None = Field(None, description="第二次续签合同日期")
    contract_start_3: str | None = Field(
        None, max_length=32, description="第三次续签合同日期"
    )
    contract_start_4: str | None = Field(
        None, max_length=32, description="第四次续签合同日期"
    )
    contract_start_5: str | None = Field(
        None, max_length=32, description="第五次续签合同日期"
    )
    contract_start_6: str | None = Field(
        None, max_length=32, description="第六次续签合同日期"
    )

    # Work experience
    work_experience_1: str | None = Field(None, description="工作经验一")
    work_experience_2: str | None = Field(None, description="工作经验二")
    work_experience_3: str | None = Field(None, description="工作经验三")
    work_experience_4: str | None = Field(None, description="工作经验四")

    # Archive & notes
    archive_number: str | None = Field(None, max_length=32, description="档案编号")
    notes: str | None = Field(None, description="备注")

    # Offboarding workflow
    materials_sent: bool = Field(False, description="离职材料是否已发送")
    materials_sent_at: datetime | None = Field(None, description="离职材料发送时间")
    reminder_sent: bool = Field(False, description="超时提醒是否已发送")
    reminder_sent_at: datetime | None = Field(None, description="超时提醒发送时间")
    completed_date: date | None = Field(None, description="办结日期")

    # Feishu sync
    feishu_record_id: str | None = Field(None, max_length=32, description="飞书记录ID")
    feishu_synced_at: date | None = Field(None, description="飞书同步时间")


class OffboardingRecordCreate(OffboardingRecordBase):
    pass


class OffboardingRecordUpdate(BaseModel):
    """离职记录更新 - 所有字段可选"""

    model_config = ConfigDict(extra="allow")

    employee_id: UUID | None = Field(None)
    seq_number: int | None = Field(None)
    employee_number: str | None = Field(None, max_length=32)
    name: str | None = Field(None, max_length=64)
    domain_account: str | None = Field(None, max_length=64)
    gender: str | None = Field(None, max_length=8)
    ethnic_group: str | None = Field(None, max_length=32)
    native_place: str | None = Field(None, max_length=64)
    political_status: str | None = Field(None, max_length=32)
    marital_status: str | None = Field(None, max_length=16)
    health_status: str | None = Field(None, max_length=32)
    household_type: str | None = Field(None, max_length=16)
    status_category: str | None = Field(None, max_length=32)
    birth_year: int | None = Field(None)
    birth_month: int | None = Field(None)
    birth_day: int | None = Field(None)
    age: int | None = Field(None)
    id_card: str | None = Field(None, max_length=18)
    id_card_expiry: str | None = Field(None, max_length=32)
    current_address: str | None = Field(None)
    phone: str | None = Field(None, max_length=32)
    email: str | None = Field(None, max_length=128)
    emergency_contact_name: str | None = Field(None, max_length=64)
    emergency_contact_phone: str | None = Field(None, max_length=32)
    emergency_contact_relation: str | None = Field(None, max_length=32)
    department: str | None = Field(None, max_length=64)
    sub_department: str | None = Field(None, max_length=64)
    position: str | None = Field(None, max_length=64)
    level: str | None = Field(None, max_length=32)
    employment_type: str | None = Field(None, max_length=32)
    probation_status: str | None = Field(None, max_length=32)
    probation_effective_date: date | None = Field(None)
    hire_date: date | None = Field(None)
    work_start_date: date | None = Field(None)
    factory_entry_date: date | None = Field(None)
    livo_entry_date: date | None = Field(None)
    work_years: str | None = Field(None, max_length=16)
    offboarding_date: date | None = Field(None)
    offboarding_type: str | None = Field(None, max_length=16)
    reason: str | None = Field(None, max_length=512)
    status: str | None = Field(None, max_length=16, description="在职状态")
    education: str | None = Field(None, max_length=16)
    degree: str | None = Field(None, max_length=32)
    major: str | None = Field(None, max_length=64)
    school: str | None = Field(None, max_length=128)
    graduation_date: date | None = Field(None)
    qualification_type: str | None = Field(None, max_length=32)
    qualifications: list[str] | None = Field(None)
    certificate_number: str | None = Field(None, max_length=64)
    certificate_review_date: date | None = Field(None)
    contract_start_date: date | None = Field(None)
    contract_end_date: date | None = Field(None)
    contract_end_2: str | None = Field(None, max_length=32)
    contract_end_3: str | None = Field(None, max_length=32)
    contract_end_4: str | None = Field(None, max_length=32)
    contract_end_5: str | None = Field(None, max_length=32)
    contract_start_2: date | None = Field(None)
    contract_start_3: str | None = Field(None, max_length=32)
    contract_start_4: str | None = Field(None, max_length=32)
    contract_start_5: str | None = Field(None, max_length=32)
    contract_start_6: str | None = Field(None, max_length=32)
    work_experience_1: str | None = Field(None)
    work_experience_2: str | None = Field(None)
    work_experience_3: str | None = Field(None)
    work_experience_4: str | None = Field(None)
    archive_number: str | None = Field(None, max_length=32)
    notes: str | None = Field(None)
    feishu_record_id: str | None = Field(None, max_length=32)
    feishu_synced_at: date | None = Field(None)


class OffboardingRecordResponse(OffboardingRecordBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee: EmployeeResponse | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ─── PositionTransferRecord Schemas ───


class PositionTransferRecordBase(BaseModel):
    """岗位调动记录 - 飞书多维表格为主源，本地 DB 做缓存"""

    # Employee relationship
    employee_id: UUID | None = Field(None, description="员工ID")

    # Core identifiers
    seq_number: int | None = Field(None, description="序号")
    employee_number: str | None = Field(None, max_length=32, description="工号")
    employee_name: str = Field(..., max_length=64, description="申请人")

    # Before transfer
    department_before: str | None = Field(None, max_length=64, description="原部门")
    sub_department_before: str | None = Field(
        None, max_length=64, description="二级部门"
    )
    original_position: str | None = Field(None, max_length=64, description="原职位")

    # After transfer (apply)
    apply_department: str | None = Field(None, max_length=64, description="申请部门")
    sub_department_after: str | None = Field(
        None, max_length=64, description="二级部门（变动后）"
    )
    apply_position: str | None = Field(None, max_length=64, description="申请职位")

    # Transfer info
    effective_date: date = Field(..., description="生效日期")
    transfer_reason: str | None = Field(None, max_length=512, description="调动原因")
    contact_phone: str | None = Field(None, max_length=32, description="联系电话")
    applicant_confirmation_text: str | None = Field(None, description="申请人确认说明")
    applicant_signature: str | None = Field(
        None, max_length=64, description="申请人签名"
    )
    applicant_confirmation_date: date | None = Field(None, description="申请人确认日期")
    approval_status: str = Field(
        "草稿", max_length=16, description="审批状态: 草稿/待审批/已通过/已拒绝"
    )
    approver: str | None = Field(None, max_length=64, description="审批人")
    approval_date: date | None = Field(None, description="审批日期")
    remarks: str | None = Field(None, description="备注")

    # Feishu sync
    feishu_record_id: str | None = Field(None, max_length=32, description="飞书记录ID")
    feishu_synced_at: date | None = Field(None, description="飞书同步时间")


class PositionTransferRecordCreate(PositionTransferRecordBase):
    pass


class PositionTransferRecordUpdate(BaseModel):
    """岗位调动记录更新 - 所有字段可选"""

    model_config = ConfigDict(extra="allow")

    employee_id: UUID | None = Field(None)
    seq_number: int | None = Field(None)
    employee_number: str | None = Field(None, max_length=32)
    employee_name: str | None = Field(None, max_length=64)
    department_before: str | None = Field(None, max_length=64)
    sub_department_before: str | None = Field(None, max_length=64)
    original_position: str | None = Field(None, max_length=64)
    apply_department: str | None = Field(None, max_length=64)
    sub_department_after: str | None = Field(None, max_length=64)
    apply_position: str | None = Field(None, max_length=64)
    effective_date: date | None = Field(None)
    transfer_reason: str | None = Field(None, max_length=512)
    contact_phone: str | None = Field(None, max_length=32)
    applicant_confirmation_text: str | None = Field(None)
    applicant_signature: str | None = Field(None, max_length=64)
    applicant_confirmation_date: date | None = Field(None)
    approval_status: str | None = Field(None, max_length=16)
    approver: str | None = Field(None, max_length=64)
    approval_date: date | None = Field(None)
    remarks: str | None = Field(None)
    feishu_record_id: str | None = Field(None, max_length=32)
    feishu_synced_at: date | None = Field(None)
    approval_flow: dict[str, Any] | None = Field(None, description="审批流程状态")
    feishu_approval_message_id: str | None = Field(None, max_length=64)


class PositionTransferRecordResponse(PositionTransferRecordBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee: EmployeeResponse | None = None
    approval_flow: dict[str, Any] | None = Field(None, description="审批流程状态")
    feishu_approval_message_id: str | None = Field(
        None, max_length=64, description="飞书审批通知消息ID"
    )
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ─── Position Transfer Approval Schemas ───


class PositionTransferSubmitRequest(BaseModel):
    """提交审批请求"""

    is_supervisor_level: bool = Field(
        False, description="是否主管级以上（决定是否跳过分管领导）"
    )
    custom_approvers: dict[str, str] | None = Field(
        None, description="手动指定审批人 {node: 姓名}，覆盖自动解析"
    )


class PositionTransferApproveNodeRequest(BaseModel):
    """审批通过当前节点"""

    opinion: str = Field("", max_length=256, description="审批意见")


class PositionTransferRejectNodeRequest(BaseModel):
    """审批拒绝当前节点"""

    opinion: str = Field("", max_length=256, description="拒绝理由")


class ApprovalStepResponse(BaseModel):
    """审批步骤响应"""

    node: str
    label: str
    status: str  # pending / approved / rejected / skipped
    signer: str | None = None
    date: str | None = None
    opinion: str | None = None


class ApprovalFlowResponse(BaseModel):
    """审批流程响应"""

    current_step: int
    applicant_name: str | None = None
    applicant_date: str | None = None
    is_supervisor_level: bool = False
    steps: list[ApprovalStepResponse] = []


class PositionTransferApprovalListRequest(BaseModel):
    """审批列表查询参数"""

    tab: str = Field(
        "my_applications", description="my_applications / pending_approval / approved"
    )
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


# ─── TrainingLedger Schemas ───


class TrainingLedgerBase(BaseModel):
    employee_number: str | None = Field(
        None, max_length=32, description="工号（培训级台账记录可为空）"
    )
    training_date: date | None = Field(None, description="培训日期")
    training_subject: str | None = Field(
        None, max_length=256, description="培训课程/主题"
    )
    training_method: str | None = Field(None, max_length=32, description="培训方式")
    duration_hours: float | None = Field(None, description="培训时长（h）")
    location: str | None = Field(None, max_length=128, description="培训地点")
    trainer: str | None = Field(None, max_length=128, description="培训单位/培训师")
    assessment_result: str | None = Field(None, max_length=16, description="考核成绩")
    source_type: str = Field(
        "manual", max_length=16, description="来源: manual, notification"
    )
    source_id: str | None = Field(None, max_length=64, description="来源ID")
    remarks: str | None = Field(None, max_length=512, description="备注")
    # ── SMP-HR-002-14 年度培训统计表字段 ──
    training_datetime: str | None = Field(
        None, max_length=64, description="培训时间（日期+时间）"
    )
    training_content: str | None = Field(None, description="培训内容")
    teaching_dept: str | None = Field(None, max_length=128, description="授课部门")
    instructor: str | None = Field(None, max_length=128, description="授课人")
    level_category: str | None = Field(None, max_length=16, description="一级/二级")
    involved_depts: str | None = Field(None, description="涉及部门")
    trainees: str | None = Field(None, description="培训对象")
    training_type: str | None = Field(None, max_length=32, description="培训类型")
    ledger_assessment_method: str | None = Field(
        None, max_length=32, description="考核方式"
    )
    plan_source: str | None = Field(None, max_length=32, description="部门/公司计划")
    drug_category: str | None = Field(None, max_length=32, description="人药/兽药")
    score_summary: str | None = Field(None, description="成绩汇总")
    session_id: UUID | None = Field(
        None, description="关联培训会话（回看签到/评估/通知/口试/实操资料）"
    )
    # ── 台账多部门管理字段 ──
    ledger_department: str | None = Field(
        None, max_length=128, description="记录归属部门（部门Tab筛选依据）"
    )
    owner_deleted: bool | None = Field(
        None, description="主办方已删除标记（其他部门副本变红提示）"
    )
    second_level_status: str | None = Field(
        None,
        max_length=16,
        description="二级培训确认: pending待确认/done已完成二级/not_needed不需二级",
    )
    is_presented: bool = Field(
        True, description="是否呈现（默认显示，不呈现则不进入员工培训清单）"
    )


class TrainingLedgerCreate(TrainingLedgerBase):
    pass


class TrainingLedgerUpdate(BaseModel):
    """所有字段可选，移除 extra="allow" hack"""

    employee_number: str | None = Field(None, max_length=32)
    training_date: date | None = Field(None)
    training_subject: str | None = Field(None, max_length=256)
    training_method: str | None = Field(None, max_length=32)
    duration_hours: float | None = Field(None)
    location: str | None = Field(None, max_length=128)
    trainer: str | None = Field(None, max_length=128)
    assessment_result: str | None = Field(None, max_length=16)
    source_type: str | None = Field(None, max_length=16)
    source_id: str | None = Field(None, max_length=64)
    remarks: str | None = Field(None, max_length=512)
    training_datetime: str | None = Field(None, max_length=64)
    training_content: str | None = Field(None)
    teaching_dept: str | None = Field(None, max_length=128)
    instructor: str | None = Field(None, max_length=128)
    level_category: str | None = Field(None, max_length=16)
    involved_depts: str | None = Field(None)
    trainees: str | None = Field(None)
    training_type: str | None = Field(None, max_length=32)
    ledger_assessment_method: str | None = Field(None, max_length=32)
    plan_source: str | None = Field(None, max_length=32)
    drug_category: str | None = Field(None, max_length=32)
    score_summary: str | None = Field(None)
    session_id: UUID | None = None
    ledger_department: str | None = Field(None, max_length=128)
    owner_deleted: bool | None = None
    second_level_status: str | None = Field(None, max_length=16)
    is_presented: bool | None = Field(None, description="是否呈现")


class TrainingLedgerResponse(TrainingLedgerBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None
    attendance_count: int | None = Field(
        None,
        description="参训人员统计：关联培训会话的真实名单数；无名单时按培训对象文本分隔计数",
    )


class TrainingLedgerListResponse(BaseModel):
    code: int
    message: str
    data: list[TrainingLedgerResponse]
    meta: dict[str, Any] | None = None


# ─── Exam Score Import Schemas ───


class ExamScoreItem(BaseModel):
    """单条成绩项."""

    name: str = Field(..., max_length=32, description="姓名")
    score: str = Field(..., max_length=16, description="成绩")


class ExamScoreConfirmRequest(BaseModel):
    """确认导入成绩请求."""

    record_id: UUID = Field(..., description="目标台账记录 ID")
    scores: list[ExamScoreItem] = Field(..., description="成绩列表")


class ExamScoreImportResponse(BaseModel):
    """解析成绩响应."""

    code: int = 0
    message: str = "ok"
    data: list[ExamScoreItem] = []


class ExamScoreConfirmResponse(BaseModel):
    """确认导入响应."""

    code: int = 0
    message: str = "ok"
    data: dict[str, Any] = {}  # {synced_count: int, score_summary: str}


# ─── Training Conflict Check Schemas ───


class TrainingConflictCheckRequest(BaseModel):
    """培训时间冲突检测请求."""

    training_date: date = Field(..., description="培训日期")
    time_start: str = Field(..., max_length=8, description="开始时间 HH:MM")
    time_end: str = Field(..., max_length=8, description="结束时间 HH:MM")
    instructor: str | None = Field(None, description="授课人")
    trainees: list[str] = Field(default_factory=list, description="参训人员姓名列表")
    exclude_session_id: str | None = Field(
        None, description="排除的会话ID（编辑时排除自身）"
    )


class InstructorConflictItem(BaseModel):
    """授课人冲突汇总项."""

    training_name: str = Field("", description="冲突培训名称")
    time_range: str = Field("", description="冲突时间段")
    conflict_depts: list[str] = Field(default_factory=list, description="涉及部门")
    conflict_count: int = Field(0, description="涉及部门数")


class TraineeConflictItem(BaseModel):
    """参训人员冲突汇总项."""

    training_name: str = Field("", description="冲突培训名称")
    time_range: str = Field("", description="冲突时间段")
    names: list[str] = Field(default_factory=list, description="冲突人员")
    conflict_count: int = Field(0, description="冲突人数")


class SuggestedTimeSlot(BaseModel):
    """推荐时间段."""

    start: str = Field("", description="开始 HH:MM")
    end: str = Field("", description="结束 HH:MM")


class TrainingConflictCheckResponse(BaseModel):
    """培训时间冲突检测响应."""

    has_conflict: bool = Field(False, description="是否存在冲突")
    instructor_conflicts: list[InstructorConflictItem] = Field(default_factory=list)
    trainee_conflicts: list[TraineeConflictItem] = Field(default_factory=list)
    suggested_times: list[SuggestedTimeSlot] = Field(default_factory=list)


# ─── TrainingLedgerPage Schemas ───


class TrainingLedgerPageCreate(BaseModel):
    employee_number: str = Field(..., max_length=32, description="工号")
    employee_name: str = Field(..., max_length=64, description="员工姓名")


class TrainingLedgerPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_number: str
    employee_name: str
    department: str | None = Field(None, max_length=64, description="所属部门")
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ─── ESG Training Records Schemas ───


class EsgTrainingRecordBase(BaseModel):
    training_date: date = Field(..., description="培训日期")
    training_name: str = Field(..., max_length=4096, description="培训名称")
    training_method: str | None = Field(None, max_length=32, description="培训方式")
    caliber: str | None = Field(None, max_length=32, description="口径")
    training_type: str | None = Field(None, max_length=32, description="培训类型")
    employee_name: str = Field(..., max_length=64, description="姓名")
    employee_account: str | None = Field(None, max_length=64, description="员工账号")
    location_address: str | None = Field(None, max_length=64, description="身份所属地")
    department: str | None = Field(None, max_length=128, description="部门")
    employee_level: str | None = Field(None, max_length=32, description="层级")
    gender: str | None = Field(None, max_length=8, description="性别")
    age: int | None = Field(None, description="年龄")
    duration: float | None = Field(None, description="培训时长")
    remarks: str | None = Field(None, max_length=512, description="备注")
    apply_company: str | None = Field(None, max_length=128, description="单位名称")
    apply_company_no: str | None = Field(None, max_length=64, description="单位编码")


class EsgTrainingRecordCreate(EsgTrainingRecordBase):
    pass


class EsgListFilters(BaseModel):
    """ESG 培训报表列表各列筛选（query 模型，配合 Depends 使用）.

    文本列按包含匹配（ilike），枚举列按精确匹配，数值列按闭区间。
    """

    training_name: str | None = Field(
        None, max_length=512, description="培训名称（包含）"
    )
    training_method: str | None = Field(None, max_length=32, description="培训方式")
    caliber: str | None = Field(None, max_length=32, description="口径")
    training_type: str | None = Field(None, max_length=32, description="培训类型")
    employee_name: str | None = Field(None, max_length=64, description="姓名（包含）")
    employee_account: str | None = Field(
        None, max_length=64, description="员工账号（包含）"
    )
    location_address: str | None = Field(None, max_length=64, description="身份所属地")
    employee_level: str | None = Field(None, max_length=32, description="层级")
    gender: str | None = Field(None, max_length=8, description="性别")
    apply_company: str | None = Field(
        None, max_length=128, description="单位名称（包含）"
    )
    apply_company_no: str | None = Field(
        None, max_length=64, description="单位编码（包含）"
    )
    remarks: str | None = Field(None, max_length=512, description="备注（包含）")
    age_min: int | None = Field(None, ge=0, description="年龄下限")
    age_max: int | None = Field(None, ge=0, description="年龄上限")
    duration_min: float | None = Field(None, ge=0, description="培训时长下限")
    duration_max: float | None = Field(None, ge=0, description="培训时长上限")

    def has_any(self) -> bool:
        return any(
            value is not None
            for value in self.model_dump().values()
        )


class EsgTrainingRecordUpdate(BaseModel):
    training_date: date | None = Field(None)
    training_name: str | None = Field(None, max_length=4096)
    training_method: str | None = Field(None, max_length=32)
    caliber: str | None = Field(None, max_length=32)
    training_type: str | None = Field(None, max_length=32)
    employee_name: str | None = Field(None, max_length=64)
    employee_account: str | None = Field(None, max_length=64)
    location_address: str | None = Field(None, max_length=64)
    department: str | None = Field(None, max_length=128)
    employee_level: str | None = Field(None, max_length=32)
    gender: str | None = Field(None, max_length=8)
    age: int | None = Field(None)
    duration: float | None = Field(None)
    remarks: str | None = Field(None, max_length=512)
    apply_company: str | None = Field(None, max_length=128)
    apply_company_no: str | None = Field(None, max_length=64)


class EsgTrainingRecordResponse(EsgTrainingRecordBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EsgTrainingRecordListResponse(BaseModel):
    code: int
    message: str
    data: list[EsgTrainingRecordResponse]
    meta: dict[str, Any] | None = None


# ─── Training Import AI Recognition Schemas ───


class ImportSheetPreview(BaseModel):
    """单个工作表的导入预览分析结果"""

    name: str = Field(..., description="工作表名")
    header_row: int = Field(0, description="表头行号（0表示未识别）")
    source: str = Field("none", description="识别来源: memory/rule/ai/none")
    headers: list[str] = Field(default_factory=list, description="原始表头文本")
    mapping: dict[str, str] = Field(
        default_factory=dict, description="列索引->系统字段名"
    )
    sample_rows: list[list[str]] = Field(
        default_factory=list, description="样例数据（最多3行）"
    )
    ai_judgment: str | None = Field(
        None, description="AI对表内容的判断（统计数据/历史数据/建议跳过）"
    )
    data_row_count: int = Field(0, description="可导入数据行数")


class ImportPreviewData(BaseModel):
    sheets: list[ImportSheetPreview] = Field(
        default_factory=list, description="各工作表分析结果"
    )
    field_catalog: list[dict[str, str]] = Field(
        default_factory=list, description="可映射字段目录"
    )


class ImportSheetConfirm(BaseModel):
    """用户确认后的单个工作表导入配置"""

    name: str = Field(..., description="工作表名")
    header_row: int = Field(..., ge=1, description="表头行号")
    mapping: dict[str, str] = Field(..., description="列索引->系统字段名（已人工确认）")


class ImportConfirmRequest(BaseModel):
    department: str = Field(..., max_length=128, description="导入到哪个部门")
    sheets: list[ImportSheetConfirm] = Field(..., description="要导入的工作表配置")


class ImportPreviewResponse(BaseModel):
    code: int
    message: str
    data: ImportPreviewData


class ImportConfirmResponseData(BaseModel):
    created: int = Field(0, description="导入总条数")
    echo_sheets: list[ImportSheetConfirm] = Field(
        default_factory=list, description="已确认的工作表配置"
    )


class ImportConfirmResponse(BaseModel):
    code: int
    message: str
    data: ImportConfirmResponseData


# ─── AnnualTrainingPlan Schemas ───


class AnnualTrainingPlanBase(BaseModel):
    year: int = Field(..., description="年度")
    department: str = Field(..., max_length=64, description="部门")
    plan_level: str = Field(
        "公司级", max_length=16, description="计划级别: 公司级, 部门级"
    )
    version: str | None = Field(None, max_length=16, description="版本号")
    remarks: str | None = Field(None, description="备注")


class AnnualTrainingPlanCreate(AnnualTrainingPlanBase):
    pass


class AnnualTrainingPlanUpdate(BaseModel):
    year: int | None = Field(None, description="年度")
    department: str | None = Field(None, max_length=64, description="部门")
    plan_level: str | None = Field(
        None, max_length=16, description="计划级别: 公司级, 部门级"
    )
    version: str | None = Field(None, max_length=16, description="版本号")
    remarks: str | None = Field(None, description="备注")


class AnnualTrainingPlanResponse(AnnualTrainingPlanBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AnnualTrainingPlanListResponse(BaseModel):
    code: int
    message: str
    data: list[AnnualTrainingPlanResponse]
    meta: dict[str, Any] | None = None


# ─── AnnualTrainingPlanItem Schemas ───


class AnnualTrainingPlanItemBase(BaseModel):
    month: str | None = Field(None, max_length=16, description="月份/季度")
    trainee_count: int | None = Field(None, description="培训人数")
    duration_hours: float | None = Field(None, description="课时")
    content_and_textbook: str | None = Field(
        None, max_length=512, description="培训内容及使用教材"
    )
    target_audience: str | None = Field(None, max_length=256, description="培训对象")
    position_and_count: str | None = Field(
        None, max_length=256, description="参加岗位/参加人数"
    )
    training_method: str | None = Field(None, max_length=64, description="培训方式")
    training_hours: float | None = Field(None, description="培训学时")
    confirmer: str | None = Field(None, max_length=64, description="确认者")
    confirm_date: date | None = Field(None, description="确认日期")
    remarks: str | None = Field(None, max_length=512, description="备注")
    tracking_status: str | None = Field(
        None, max_length=16, description="培训跟踪: 完成, 未完成"
    )
    sort_order: int = Field(0, description="排序")
    # ── 新增字段（SMP-HR-002-14）──
    training_type: str | None = Field(
        None, max_length=16, description="培训类型: 内训, 外训"
    )
    training_month: str | None = Field(
        None, max_length=16, description="培训时间（月度）"
    )
    content_textbook: str | None = Field(
        None, max_length=512, description="培训内容或使用教材"
    )
    target_audience_new: str | None = Field(
        None, max_length=256, description="培训对象"
    )
    instructor: str | None = Field(None, max_length=128, description="授课单位或人员")
    assessment_method: str | None = Field(None, max_length=32, description="考核方式")


class AnnualTrainingPlanItemCreate(AnnualTrainingPlanItemBase):
    pass


class AnnualTrainingPlanItemUpdate(BaseModel):
    month: str | None = Field(None, max_length=16)
    trainee_count: int | None = Field(None)
    duration_hours: float | None = Field(None)
    content_and_textbook: str | None = Field(None, max_length=512)
    target_audience: str | None = Field(None, max_length=256)
    position_and_count: str | None = Field(None, max_length=256)
    training_method: str | None = Field(None, max_length=64)
    training_hours: float | None = Field(None)
    confirmer: str | None = Field(None, max_length=64)
    confirm_date: date | None = Field(None)
    remarks: str | None = Field(None, max_length=512)
    tracking_status: str | None = Field(None, max_length=16)
    sort_order: int | None = Field(None)


class AnnualTrainingPlanItemResponse(AnnualTrainingPlanItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AnnualTrainingPlanItemBatchUpdate(BaseModel):
    items: list[AnnualTrainingPlanItemCreate] = Field(
        default_factory=list, description="明细列表"
    )


class PlanAttachmentResponse(BaseModel):
    """年度培训计划附件（不含二进制数据）."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    annex_no: str | None = None
    file_name: str
    file_size: int | None = None
    created_at: datetime | None = None
    ledger_imported_at: datetime | None = None


class MarkLedgerImportedRequest(BaseModel):
    """标记计划附件已导入培训台账."""

    ids: list[UUID] = Field(default_factory=list, description="附件ID列表")


class TrainingContentUsedOut(BaseModel):
    """已培训/已导入台账的附件文件清单条目."""

    model_config = ConfigDict(from_attributes=True)

    entry_name: str
    entry_code: str | None = None
    used_at: datetime | None = None


class TrainingContentUsedItem(BaseModel):
    """待标记为已培训的文件条目."""

    name: str = Field(description="文件名称")
    code: str | None = Field(default=None, description="录入时的最新文件编号")
    attachment_id: UUID | None = Field(default=None, description="来源附件ID")


class MarkTrainingContentUsedRequest(BaseModel):
    """标记附件文件清单条目已培训（置灰不可再选）."""

    items: list[TrainingContentUsedItem] = Field(default_factory=list)


# ─── TrainingSession / TrainingDocument Schemas ───


class TrainingSessionUpsert(BaseModel):
    """培训会话保存（id 存在则更新，否则新建）."""

    id: UUID | None = None
    training_level: str | None = None
    plan_year: int | None = None
    department: str | None = None
    trainee_departments: list[str] | None = None
    topic: str | None = None
    training_date: date | None = None
    time_start: str | None = None
    time_end: str | None = None
    training_method: str | None = None
    instructor: str | None = None
    actual_count: int | None = None
    employee_names: list[str] | None = None
    employee_dept_map: dict[str, str] | None = None
    plan_id: UUID | None = None
    plan_item_id: UUID | None = None
    checked_content: list[Any] | None = None


class TrainingSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    training_level: str | None = None
    plan_year: int | None = None
    department: str | None = None
    trainee_departments: list[str] | None = None
    topic: str | None = None
    training_date: date | None = None
    time_start: str | None = None
    time_end: str | None = None
    training_method: str | None = None
    instructor: str | None = None
    actual_count: int | None = None
    employee_names: list[str] | None = None
    employee_dept_map: dict[str, str] | None = None
    plan_id: UUID | None = None
    plan_item_id: UUID | None = None
    checked_content: list[Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TrainingDocumentUpsert(BaseModel):
    """会话资料保存（同会话同类覆盖更新）."""

    session_id: UUID
    doc_type: str = Field(
        description="sign_in/evaluation/notification/oral_exam/practical_exam"
    )
    title: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class TrainingDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    doc_type: str
    title: str | None = None
    payload: dict[str, Any]
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TrainingSessionFromLedgerRequest(BaseModel):
    """从培训台账记录一键创建部门级二级培训会话（带入上级试卷草稿）."""

    record_id: UUID = Field(description="台账记录ID（部门副本）")
    copy_doc_types: list[str] | None = Field(
        default=None,
        description="要复制的试卷类型，默认 ai_written_exam/oral_exam/practical_exam",
    )


# ─── 员工培训清单 Schemas ───


class EmployeeTrainingListMemberCreate(BaseModel):
    """手动添加员工培训清单人员."""

    department: str = Field(..., max_length=64, description="培训部门")
    name: str = Field(..., max_length=64, description="姓名")
    employee_number: str | None = Field(None, max_length=32, description="工号")


class EmployeeTrainingListMemberUpdate(BaseModel):
    """编辑员工培训清单人员（改名）."""

    name: str = Field(..., max_length=64, description="新姓名")


class EmployeeTrainingListMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    department: str
    name: str
    employee_number: str | None = None
    source: str


class ImportFeishuMembersRequest(BaseModel):
    """一键导入飞书联系人（department 为空=全部部门一次导入）."""

    department: str | None = Field(None, max_length=64, description="部门（空=全部）")


class ImportFeishuMembersResult(BaseModel):
    """导入结果（按部门统计）."""

    total: int = 0
    per_department: dict[str, int] = Field(default_factory=dict)


class EmployeeTrainingSummaryOut(BaseModel):
    """员工培训清单汇总行."""

    name: str
    employee_number: str | None = None
    source: str
    record_count: int = 0
    first_training_date: date | None = None
    last_training_date: date | None = None


class EmployeeTrainingRecordOut(BaseModel):
    """员工个人培训清单行（导出 Excel 的输入）."""

    training_datetime: str | None = None
    training_date: date | None = None
    training_content: str | None = None
    personal_score: str | None = None
    remarks: str | None = None


# ─── 培训附件导出 ───


class TrainingAttachmentItem(BaseModel):
    """培训附件文件条目."""

    name: str = Field(..., max_length=512, description="文件名称")
    code: str | None = Field(None, max_length=128, description="文件编号")


class TrainingAttachmentExportRequest(BaseModel):
    """培训附件导出请求（附件： + 序号/文件名称/文件编号表格）."""

    items: list[TrainingAttachmentItem] = Field(
        default_factory=list,
        max_length=500,
        description="附件文件清单（防御性上限，防止异常输入生成超大文档）",
    )


# ─── 口试/实操考核结果表导出 ───


class OralExamQuestionItem(BaseModel):
    no: str | None = Field(None, description="题号")
    question: str | None = Field(None, description="考核问题")
    answer: str | None = Field(None, description="参考答案")


class OralExamPersonItem(BaseModel):
    name: str = Field(..., description="姓名")
    department: str | None = Field(None, description="部门/班组")
    question_nos: str | None = Field(None, description="考核题号")
    result: str | None = Field(None, description="合格/不合格")
    remark: str | None = Field(None, description="备注")


class OralExamExportRequest(BaseModel):
    training_content: str | None = Field(None, description="培训内容")
    training_date: str | None = Field(None, description="培训日期")
    questions: list[OralExamQuestionItem] = Field(default_factory=list)
    persons: list[OralExamPersonItem] = Field(default_factory=list)
    assessor: str | None = Field(None, description="评估人")


class PracticalExamPersonItem(BaseModel):
    name: str = Field(..., description="姓名")
    department: str | None = Field(None, description="部门")
    description: str | None = Field(None, description="实操考核情况描述")


class PracticalExamExportRequest(BaseModel):
    training_content: str | None = Field(None, description="培训内容")
    training_date: str | None = Field(None, description="培训日期")
    persons: list[PracticalExamPersonItem] = Field(default_factory=list)
    assessor: str | None = Field(None, description="评估人")


class PlanAttachmentSectionResponse(BaseModel):
    """附件条目（从附件文件拆分的"附件X"，供跨模块索引）."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    attachment_id: UUID
    plan_id: UUID
    annex_no: str
    title: str | None = None
    source_kind: str
    source_ref: str | None = None


class AttachmentPreviewTable(BaseModel):
    """预览用结构化表格."""

    title: str | None = None
    header: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class AttachmentPreviewBlock(BaseModel):
    """预览用文档块：段落或表格."""

    type: str
    text: str | None = None
    rows: list[list[str]] | None = None


class AttachmentPreview(BaseModel):
    """附件预览结构化响应（table/doc/tables 三种形态）."""

    kind: str
    title: str | None = None
    header: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    tables: list[AttachmentPreviewTable] = Field(default_factory=list)
    blocks: list[AttachmentPreviewBlock] = Field(default_factory=list)


class PlanAttachmentListEnvelope(BaseModel):
    """附件清单响应包络（用于 OpenAPI 类型生成）."""

    code: int = 200
    message: str = "success"
    data: list[PlanAttachmentResponse] = Field(default_factory=list)


class PlanAttachmentSectionListEnvelope(BaseModel):
    """附件条目列表响应包络（用于 OpenAPI 类型生成）."""

    code: int = 200
    message: str = "success"
    data: list[PlanAttachmentSectionResponse] = Field(default_factory=list)


class AttachmentPreviewEnvelope(BaseModel):
    """附件预览响应包络（用于 OpenAPI 类型生成）."""

    code: int = 200
    message: str = "success"
    data: AttachmentPreview | None = None


# ─── HR Feishu Settings Schemas ───


class HrFeishuAppSettingsDetail(BaseModel):
    app_id: str = ""
    app_secret_masked: str | None = None
    is_enabled: bool = False
    last_test_status: str | None = None
    last_test_error: str | None = None
    last_tested_at: datetime | None = None


class UpdateHrFeishuAppSettingsRequest(BaseModel):
    app_id: str = ""
    app_secret: str = ""
    is_enabled: bool = True


class HrFeishuFieldMappingItem(BaseModel):
    system_field: str
    feishu_field: str | None = None


class HrFeishuEntitySettingItem(BaseModel):
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
    field_mappings: list[HrFeishuFieldMappingItem] = Field(default_factory=list)
    sort_order: int = 0
    last_sync_status: str | None = None
    last_sync_error: str | None = None
    last_synced_at: datetime | None = None

    @field_validator("field_mappings", mode="before")
    @classmethod
    def _normalize_field_mappings(cls: Any, value: object) -> list[object]:
        if value is None:
            return []
        return value  # type: ignore[return-value]


class UpdateHrFeishuEntitySettingRequest(BaseModel):
    app_token: str | None = None
    base_table_name: str | None = None
    base_table_id: str | None = None
    is_enabled: bool = True
    enable_push_to_feishu: bool = True
    enable_pull_from_feishu: bool = True
    field_mappings: list[HrFeishuFieldMappingItem] | None = None


class HrFeishuSettingsTestResult(BaseModel):
    success: bool
    message: str
    checked_at: datetime
    entity_code: str | None = None
    table_id: str | None = None


class HrFeishuTableOption(BaseModel):
    table_id: str
    table_name: str


class HrFeishuFieldOption(BaseModel):
    field_id: str
    field_name: str
    field_type: str | int | None = None


class HrFeishuSystemFieldOption(BaseModel):
    field_key: str
    field_label: str
    direction: str = "both"


class HrFeishuEntityFieldMappingBundle(BaseModel):
    entity_code: str
    entity_name: str
    system_fields: list[HrFeishuSystemFieldOption] = []
    feishu_fields: list[HrFeishuFieldOption] = []
    field_mappings: list[HrFeishuFieldMappingItem] = []


# ─── JobPosting Schemas ───


class JobPostingBase(BaseModel):
    title: str = Field(..., max_length=64, description="职位名称")
    description: str | None = Field(None, description="岗位描述")
    requirement: str | None = Field(None, description="任职要求")
    salary_range: str | None = Field(None, max_length=32, description="薪资范围")
    location: str | None = Field(None, max_length=64, description="工作地点")
    req_skills: list[str] | None = Field(None, description="要求技能")
    status: str = Field("招聘中", max_length=16, description="招聘状态")

    @field_validator("req_skills", mode="before")
    @classmethod
    def _parse_req_skills(cls: Any, v: Any) -> Any:
        """飞书多维表格可能返回逗号分隔字符串，转换为 list。"""
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v


class JobPostingCreate(JobPostingBase):
    pass


class JobPostingUpdate(BaseModel):
    title: str | None = Field(None, max_length=64, description="职位名称")
    description: str | None = Field(None, description="岗位描述")
    requirement: str | None = Field(None, description="任职要求")
    salary_range: str | None = Field(None, max_length=32, description="薪资范围")
    location: str | None = Field(None, max_length=64, description="工作地点")
    req_skills: list[str] | None = Field(None, description="要求技能")
    status: str | None = Field(None, max_length=16, description="招聘状态")


class JobPostingResponse(JobPostingBase):
    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ─── Candidate Schemas ───


class CandidateBase(BaseModel):
    name: str = Field(..., max_length=64, description="姓名")
    contact: str | None = Field(None, description="联系方式")
    education: str | None = Field(None, description="学历")
    work_years: int | None = Field(None, description="工作经验(年)")
    skills: list[str] | None = Field(None, description="技能标签")
    match_rate: int | None = Field(None, description="技能匹配度")
    resume_score: int | None = Field(None, description="简历评分")
    fit_level: str | None = Field(None, description="招聘符合程度")
    interview_status: str = Field("待安排", description="面试状态")
    interview_time: str | None = Field(None, description="面试时间")
    interviewer: str | None = Field(None, description="面试官")
    remark: str | None = Field(None, description="备注")
    source_channel: str = Field("手动下载", description="来源渠道")

    @field_validator("skills", mode="before")
    @classmethod
    def _parse_skills(cls: Any, v: Any) -> Any:
        """飞书多维表格可能返回逗号分隔字符串，转换为 list。"""
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @field_validator("work_years", "match_rate", "resume_score", mode="before")
    @classmethod
    def _parse_int_fields(cls: Any, v: Any) -> Any:
        """飞书多维表格可能返回字符串数字，转换为 int。"""
        if isinstance(v, str):
            try:
                return int(v)
            except ValueError:
                return v
        return v


class CandidateCreate(CandidateBase):
    pass


class CandidateUpdate(BaseModel):
    name: str | None = Field(None, max_length=64, description="姓名")
    contact: str | None = Field(None, description="联系方式")
    education: str | None = Field(None, description="学历")
    work_years: int | None = Field(None, description="工作经验(年)")
    skills: list[str] | None = Field(None, description="技能标签")
    match_rate: int | None = Field(None, description="技能匹配度")
    resume_score: int | None = Field(None, description="简历评分")
    fit_level: str | None = Field(None, description="招聘符合程度")
    interview_status: str | None = Field(None, description="面试状态")
    interview_time: str | None = Field(None, description="面试时间")
    interviewer: str | None = Field(None, description="面试官")
    remark: str | None = Field(None, description="备注")
    source_channel: str | None = Field(None, description="来源渠道")


class CandidateResponse(CandidateBase):
    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str
    feishu_record_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ─── Onboarding Schemas (recruitment-onboarding flow) ───


class OnboardingBase(BaseModel):
    """入职信息（对应飞书多维表格入职信息表 tblK1IWXATe2Nn2q 字段）"""

    name: str | None = Field(None, description="姓名")
    onboard_date: str | None = Field(None, description="入职日期（YYYY-MM-DD）")
    department: str | None = Field(None, description="入职部门")
    level: str | None = Field(None, description="岗位")
    # 附件字段：元素格式 [{"file_token": "...", "name": "..."}]（飞书多维附件 type=17）
    resignation_attachment: list[dict[str, Any]] | None = Field(
        None, description="离职证明附件"
    )
    id_attachment: list[dict[str, Any]] | None = Field(None, description="身份信息附件")
    education_attachment: list[dict[str, Any]] | None = Field(
        None, description="学历证书附件"
    )
    other_attachment: list[dict[str, Any]] | None = Field(None, description="其他附件")


class OnboardingUpdate(OnboardingBase):
    """更新入职信息（可选字段，未传不更新）"""


class OnboardingResponse(OnboardingBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    candidate_id: str | None = None
    position: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class OnboardingSyncRequest(BaseModel):
    """入职完成同步到合同/员工档案的请求体"""

    employee_number: str | None = Field(
        None, max_length=32, description="工号（可选，按姓名自动匹配）"
    )
    name: str | None = Field(None, max_length=64, description="姓名（来自入职表）")
    department: str | None = Field(
        None, max_length=64, description="入职部门（来自入职表）"
    )
    level: str | None = Field(None, max_length=64, description="岗位（来自入职表）")


# ─── Health Check and Material Schemas ───


class HealthCheckUpdate(BaseModel):
    status: str | None = Field(None, description="体检状态")
    check_date: str | None = Field(None, description="体检日期")
    remark: str | None = Field(None, description="备注")


class MaterialUpdate(BaseModel):
    material_type: str = Field(..., description="材料类型")
    status: str | None = Field(None, description="提交状态")


# ─── Webhook / Email Schemas ───


class FeishuApprovalWebhookPayload(BaseModel):
    """飞书审批完成回调请求体"""

    employee_number: str = Field(..., description="工号")


class EmailConfigUpdate(BaseModel):
    """邮箱配置更新请求体"""

    imap_host: str | None = Field(None, description="IMAP 服务器地址")
    imap_port: int | None = Field(None, description="IMAP 端口")
    imap_user: str | None = Field(None, description="IMAP 用户名")
    imap_pass: str | None = Field(None, description="IMAP 密码")
    smtp_host: str | None = Field(None, description="SMTP 服务器地址")
    smtp_port: int | None = Field(None, description="SMTP 端口")
    smtp_user: str | None = Field(None, description="SMTP 用户名")
    smtp_pass: str | None = Field(None, description="SMTP 密码")
    from_addr: str | None = Field(None, description="发件人地址")
    fetch_enabled: bool | None = Field(None, description="是否启用邮件抓取")
    fetch_interval_hours: int | None = Field(
        None, description="自动抓取间隔（小时），默认1小时，最大48小时"
    )
    fetch_schedule_hours: list[int] | None = Field(
        None,
        description="定时抓取小时列表（0-23），如[9,10,14]表示每天9点、10点、14点抓取",
    )
    watch_dir: str | None = Field(None, description="简历监控目录")
    offer_subject: str | None = Field(None, description="录用通知邮件主题")
    offer_body: str | None = Field(None, description="录用通知邮件正文")
    reject_subject: str | None = Field(None, description="拒绝通知邮件主题")
    reject_body: str | None = Field(None, description="拒绝通知邮件正文")


class SendOfferEmailPayload(BaseModel):
    """发送录用通知邮件请求体"""

    candidate_id: str = Field(..., description="候选人ID")
    to_email: str = Field(..., description="收件人邮箱")
    subject: str = Field(..., description="邮件主题")
    body: str = Field(..., description="邮件正文")


# ═══════════════════════════════════════════════════════════════
# 培训管理二次开发新增 Schemas（SMP-HR-002-14）
# ═══════════════════════════════════════════════════════════════

# ─── 培训师管理 ───


class TrainerBase(BaseModel):
    name: str = Field(..., max_length=64, description="培训师姓名")
    employee_id: UUID | None = Field(None, description="关联员工ID")
    department: str | None = Field(None, max_length=128, description="部门")
    position: str | None = Field(None, max_length=128, description="岗位")
    approval_date: date | None = Field(None, description="批准时间")
    approver: str | None = Field(None, max_length=64, description="批准人")
    remarks: str | None = Field(None, max_length=512, description="备注")


class TrainerCreate(TrainerBase):
    pass


class TrainerUpdate(BaseModel):
    name: str | None = Field(None, max_length=64, description="培训师姓名")
    employee_id: UUID | None = Field(None, description="关联员工ID")
    department: str | None = Field(None, max_length=128, description="部门")
    position: str | None = Field(None, max_length=128, description="岗位")
    approval_date: date | None = Field(None, description="批准时间")
    approver: str | None = Field(None, max_length=64, description="批准人")
    remarks: str | None = Field(None, max_length=512, description="备注")


class TrainerResponse(TrainerBase):
    id: UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class TrainerListResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: list[TrainerResponse]
    meta: dict[str, Any] | None = None


# ─── 培训评估表 ───


class TrainingEvaluationBase(BaseModel):
    training_content: str | None = Field(None, max_length=4096, description="培训内容")
    training_date: date | None = Field(None, description="培训日期")
    duration_hours: float | None = Field(None, description="课时")
    training_method: str | None = Field(None, max_length=32, description="培训方式")
    other_method: str | None = Field(None, max_length=128, description="其他方式说明")
    instructor: str | None = Field(None, max_length=128, description="授课人")
    target_dept_person: str | None = Field(
        None, description="培训对象（部门/班组/人员）"
    )
    expected_count: int | None = Field(None, description="应到人数")
    actual_count: int | None = Field(None, description="实到人数")
    absent_count: int | None = Field(None, description="缺席人数")
    textbook: str | None = Field(None, max_length=512, description="培训教材")
    absent_handling: str | None = Field(None, description="缺席人员处理方式")
    need_retraining: bool | None = Field(False, description="是否需要再培训")
    retraining_info: str | None = Field(None, description="再培训信息")
    assessment_method: str | None = Field(None, max_length=32, description="考核方式")
    excellent_count: int | None = Field(None, description="优")
    good_count: int | None = Field(None, description="良好")
    pass_count: int | None = Field(None, description="合格")
    fail_count: int | None = Field(None, description="不合格")
    absent_exam_count: int | None = Field(None, description="缺考")
    fail_handling: str | None = Field(None, description="缺考及不合格人员处理方式")
    makeup_count: int | None = Field(None, description="补考人数")
    makeup_pass_count: int | None = Field(None, description="补考合格人数")
    makeup_fail_count: int | None = Field(None, description="补考不合格人数")
    makeup_fail_handling: str | None = Field(
        None, description="缺考及补考不合格人员处理方式"
    )
    evaluation_result: str | None = Field(
        None, max_length=32, description="培训效果评估结果"
    )
    evaluation_comment: str | None = Field(None, description="培训效果评估及其他")
    evaluator: str | None = Field(None, max_length=64, description="培训评估人")
    evaluate_date: date | None = Field(None, description="评估日期")
    has_notification: bool | None = Field(False, description="附件：培训通知")
    has_signin_sheet: bool | None = Field(False, description="附件：培训签到表")
    has_textbook: bool | None = Field(False, description="附件：培训教材")
    has_exam_paper: bool | None = Field(False, description="附件：考核试题试卷")
    has_score_summary: bool | None = Field(False, description="附件：成绩汇总表")
    other_attachment: str | None = Field(None, description="其他附件")


class TrainingEvaluationCreate(TrainingEvaluationBase):
    pass


class TrainingEvaluationUpdate(BaseModel):
    training_content: str | None = Field(None, max_length=4096, description="培训内容")
    training_date: date | None = Field(None, description="培训日期")
    duration_hours: float | None = Field(None, description="课时")
    training_method: str | None = Field(None, max_length=32, description="培训方式")
    other_method: str | None = Field(None, max_length=128, description="其他方式说明")
    instructor: str | None = Field(None, max_length=128, description="授课人")
    target_dept_person: str | None = Field(
        None, description="培训对象（部门/班组/人员）"
    )
    expected_count: int | None = Field(None, description="应到人数")
    actual_count: int | None = Field(None, description="实到人数")
    absent_count: int | None = Field(None, description="缺席人数")
    textbook: str | None = Field(None, max_length=512, description="培训教材")
    absent_handling: str | None = Field(None, description="缺席人员处理方式")
    need_retraining: bool | None = Field(None, description="是否需要再培训")
    retraining_info: str | None = Field(None, description="再培训信息")
    assessment_method: str | None = Field(None, max_length=32, description="考核方式")
    excellent_count: int | None = Field(None, description="优")
    good_count: int | None = Field(None, description="良好")
    pass_count: int | None = Field(None, description="合格")
    fail_count: int | None = Field(None, description="不合格")
    absent_exam_count: int | None = Field(None, description="缺考")
    fail_handling: str | None = Field(None, description="缺考及不合格人员处理方式")
    makeup_count: int | None = Field(None, description="补考人数")
    makeup_pass_count: int | None = Field(None, description="补考合格人数")
    makeup_fail_count: int | None = Field(None, description="补考不合格人数")
    makeup_fail_handling: str | None = Field(
        None, description="缺考及补考不合格人员处理方式"
    )
    evaluation_result: str | None = Field(
        None, max_length=32, description="培训效果评估结果"
    )
    evaluation_comment: str | None = Field(None, description="培训效果评估及其他")
    evaluator: str | None = Field(None, max_length=64, description="培训评估人")
    evaluate_date: date | None = Field(None, description="评估日期")
    has_notification: bool | None = Field(None, description="附件：培训通知")
    has_signin_sheet: bool | None = Field(None, description="附件：培训签到表")
    has_textbook: bool | None = Field(None, description="附件：培训教材")
    has_exam_paper: bool | None = Field(None, description="附件：考核试题试卷")
    has_score_summary: bool | None = Field(None, description="附件：成绩汇总表")
    other_attachment: str | None = Field(None, description="其他附件")


class TrainingEvaluationResponse(TrainingEvaluationBase):
    id: UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class TrainingEvaluationListResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: list[TrainingEvaluationResponse]
    meta: dict[str, Any] | None = None


# ─── 岗位培训清单 ───


class PositionTrainingListItemBase(BaseModel):
    level: str = Field(..., max_length=16, description="级别: 部门级, 岗位级")
    sort_order: int | None = Field(None, description="排序")
    textbook_name: str | None = Field(None, max_length=256, description="培训教材名称")
    textbook_code: str | None = Field(None, max_length=128, description="编号")
    assessment_method: str | None = Field(None, max_length=32, description="考核方式")
    remarks: str | None = Field(None, max_length=512, description="备注")


class PositionTrainingListItemResponse(PositionTrainingListItemBase):
    id: UUID
    list_id: UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class PositionTrainingListBase(BaseModel):
    department: str = Field(..., max_length=128, description="部门")
    position: str = Field(..., max_length=128, description="岗位")
    creator: str | None = Field(None, max_length=64, description="制定人")
    create_date: date | None = Field(None, description="制定日期")
    reviewer: str | None = Field(
        None, max_length=64, description="审核人（部门负责人）"
    )
    review_date: date | None = Field(None, description="审核日期")
    approver: str | None = Field(None, max_length=64, description="批准人（QA负责人）")
    approve_date: date | None = Field(None, description="批准日期")


class PositionTrainingListCreate(PositionTrainingListBase):
    items: list[PositionTrainingListItemBase] | None = Field(
        None, description="清单明细"
    )


class PositionTrainingListUpdate(BaseModel):
    department: str | None = Field(None, max_length=128, description="部门")
    position: str | None = Field(None, max_length=128, description="岗位")
    creator: str | None = Field(None, max_length=64, description="制定人")
    create_date: date | None = Field(None, description="制定日期")
    reviewer: str | None = Field(
        None, max_length=64, description="审核人（部门负责人）"
    )
    review_date: date | None = Field(None, description="审核日期")
    approver: str | None = Field(None, max_length=64, description="批准人（QA负责人）")
    approve_date: date | None = Field(None, description="批准日期")


class PositionTrainingListResponse(PositionTrainingListBase):
    id: UUID
    items: list[PositionTrainingListItemResponse] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class PositionTrainingListListResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: list[PositionTrainingListResponse]
    meta: dict[str, Any] | None = None


class PositionTrainingListItemBatchUpdate(BaseModel):
    items: list[PositionTrainingListItemBase] = Field(
        ..., description="清单明细（全量替换）"
    )


# ─── 岗位培训映射 ───


class PositionTrainingMappingCreate(BaseModel):
    """创建岗位映射 - 请求"""

    department: str = Field(..., max_length=128, description="部门")
    employee_position: str = Field(..., max_length=128, description="员工档案岗位")
    training_position: str = Field(..., max_length=128, description="岗位培训清单岗位")


class PositionTrainingMappingResponse(BaseModel):
    """岗位映射 - 响应"""

    id: UUID
    department: str
    employee_position: str
    training_position: str
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ─── 培训计划跟踪 ───


class PlanTrackingRecordBase(BaseModel):
    plan_id: UUID | None = Field(None, description="关联年度计划ID")
    plan_item_id: UUID | None = Field(
        None, description="来源年度计划明细ID（自动录入溯源）"
    )
    year: int | None = Field(None, description="年度")
    month: str | None = Field(None, max_length=16, description="跟踪月份")
    plan_level: str | None = Field(
        None, max_length=16, description="计划级别: 公司级, 部门级"
    )
    department: str | None = Field(
        None, max_length=64, description="部门（部门级计划）"
    )
    sort_order: int | None = Field(None, description="排序")
    training_content: str | None = Field(None, max_length=4096, description="培训内容")
    actual_time: str | None = Field(None, max_length=64, description="实际培训时间")
    target_audience: str | None = Field(None, description="培训对象")
    training_type: str | None = Field(None, max_length=32, description="培训类型")
    tracking_assessment_method: str | None = Field(
        None, max_length=32, description="考核方式"
    )
    is_completed: bool | None = Field(False, description="是否按计划完成")
    tracker: str | None = Field(None, max_length=64, description="跟踪人")
    track_date: date | None = Field(None, description="跟踪日期")
    remarks: str | None = Field(None, max_length=512, description="备注")
    sessions_snapshot: str | None = Field(
        None, description="上次自动汇总的培训会话时间"
    )


class PlanTrackingRecordCreate(PlanTrackingRecordBase):
    pass


class PlanTrackingRecordUpdate(BaseModel):
    plan_id: UUID | None = Field(None, description="关联年度计划ID")
    plan_item_id: UUID | None = Field(
        None, description="来源年度计划明细ID（自动录入溯源）"
    )
    year: int | None = Field(None, description="年度")
    month: str | None = Field(None, max_length=16, description="跟踪月份")
    plan_level: str | None = Field(
        None, max_length=16, description="计划级别: 公司级, 部门级"
    )
    department: str | None = Field(
        None, max_length=64, description="部门（部门级计划）"
    )
    sort_order: int | None = Field(None, description="排序")
    training_content: str | None = Field(None, max_length=4096, description="培训内容")
    actual_time: str | None = Field(None, max_length=64, description="实际培训时间")
    target_audience: str | None = Field(None, description="培训对象")
    training_type: str | None = Field(None, max_length=32, description="培训类型")
    tracking_assessment_method: str | None = Field(
        None, max_length=32, description="考核方式"
    )
    is_completed: bool | None = Field(None, description="是否按计划完成")
    tracker: str | None = Field(None, max_length=64, description="跟踪人")
    track_date: date | None = Field(None, description="跟踪日期")
    remarks: str | None = Field(None, max_length=512, description="备注")
    sessions_snapshot: str | None = Field(
        None, description="上次自动汇总的培训会话时间"
    )


class PlanTrackingRecordResponse(PlanTrackingRecordBase):
    id: UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class PlanTrackingRecordListResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: list[PlanTrackingRecordResponse]
    meta: dict[str, Any] | None = None


# ─── Training Personnel Config Schemas ───


class TrainingPersonnelConfigCreate(BaseModel):
    """培训人员配置 - 创建/更新（按 level+department+config_name upsert）"""

    level: str = Field(..., max_length=16, description="培训级别: 公司级/部门级")
    department: str | None = Field(None, max_length=64, description="部门(公司级为空)")
    config_name: str = Field(
        ..., max_length=64, description="配置名称(用户自定义，如A班/仪器组)"
    )
    personnel: list[dict[str, Any]] = Field(
        default_factory=list,
        description="参训人员名单 [{name, employee_number, department}]",
    )
    remarks: str | None = Field(None, max_length=256, description="备注")


class TrainingPersonnelConfigOut(BaseModel):
    """培训人员配置 - 响应"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    level: str
    department: str | None = None
    config_name: str
    personnel: list[dict[str, Any]] = Field(default_factory=list)
    remarks: str | None = None
    updated_at: datetime | None = None


class CustomTrainingDepartmentCreate(BaseModel):
    """自定义培训部门 - 创建"""

    name: str = Field(..., min_length=1, max_length=64, description="部门名称")


# 映射类型合法枚举值（与 training_dept_resolver.py 配置表驱动一致）
VALID_MAPPING_TYPES: set[str] = {
    "special",
    "alias",
    "candidate_source",
    "split",
    "print_unify",
    "modal_drop",
    "modal_extra",
    "modal_no_expand",
    "exclude",
    "force_show",
}
VALID_MATCH_LEVELS: set[str] = {"first", "second", "both"}


class TrainingDeptMappingCreate(BaseModel):
    """培训部门映射配置 - 创建"""

    source_name: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="源部门名（飞书/员工档案/手输名）",
    )
    target_name: str | None = Field(None, max_length=128, description="目标培训部门名")
    match_level: Literal["first", "second", "both"] = Field(
        "first", description="匹配层级: first/second/both"
    )
    mapping_type: str = Field("alias", max_length=24, description="映射类型")
    priority: int = Field(100, ge=0, le=9999, description="解析优先级（越小越优先）")
    enabled: bool = True
    remark: str | None = Field(None, max_length=256, description="备注")

    @field_validator("mapping_type")
    @classmethod
    def _validate_mapping_type(cls: Any, v: str) -> str:
        if v not in VALID_MAPPING_TYPES:
            raise ValueError(
                f"mapping_type 必须为 {sorted(VALID_MAPPING_TYPES)} 之一，收到: {v!r}"
            )
        return v


class TrainingDeptMappingUpdate(BaseModel):
    """培训部门映射配置 - 更新（所有字段可选）"""

    source_name: str | None = Field(None, min_length=1, max_length=128)
    target_name: str | None = Field(None, max_length=128)
    match_level: Literal["first", "second", "both"] | None = None
    mapping_type: str | None = Field(None, max_length=24)
    priority: int | None = Field(None, ge=0, le=9999)
    enabled: bool | None = None
    remark: str | None = Field(None, max_length=256)

    @field_validator("mapping_type")
    @classmethod
    def _validate_mapping_type(cls: Any, v: str | None) -> str | None:
        if v is not None and v not in VALID_MAPPING_TYPES:
            raise ValueError(
                f"mapping_type 必须为 {sorted(VALID_MAPPING_TYPES)} 之一，收到: {v!r}"
            )
        return v


class TrainingDeptMappingOut(BaseModel):
    """培训部门映射配置 - 响应"""

    id: str
    source_name: str
    target_name: str | None = None
    match_level: str
    mapping_type: str
    priority: int = 100
    enabled: bool = True
    remark: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class NewHireOut(BaseModel):
    """新员工（最近进厂）- 响应"""

    employee_number: str | None = None
    name: str
    department: str | None = None
    factory_entry_date: date | None = None


# ─── 新员工培训（NewEmployeeTrainingPlan）───


class NewEmployeeTrainingPlanItem(BaseModel):
    """新员工培训计划项（从岗位培训清单复制的教材快照）"""

    id: str | None = Field(None, description="计划项ID（稳定标识，用于勾选关联）")
    level: str = Field(..., max_length=16, description="级别: 部门级, 岗位级")
    textbook_name: str = Field(..., max_length=256, description="培训教材名称")
    textbook_code: str | None = Field(None, max_length=128, description="编号")
    assessment_method: str | None = Field(None, max_length=32, description="考核方式")
    remark: str | None = Field(None, max_length=512, description="备注")
    manual: bool = False
    sort_order: int = 0


class NewEmployeeTrainingPlanGenerate(BaseModel):
    """生成新员工培训计划 - 请求"""

    employee_id: UUID = Field(..., description="员工ID")
    training_position: str | None = Field(
        None, max_length=128, description="培训岗位（可选，优先使用映射）"
    )


class NewEmployeeTrainingManualAdd(BaseModel):
    """手动新增新员工培训计划 - 请求（离岗复训等场景）

    员工在档案中时前端携带 employee_id；后端按姓名匹配档案，
    唯一命中时入职日期强制以档案为准（忽略前端传入值）。
    """

    name: str = Field(..., max_length=64, description="员工姓名")
    department: str = Field(..., max_length=128, description="部门")
    sub_department: str | None = Field(None, max_length=128, description="二级部门")
    position: str = Field(..., max_length=128, description="岗位")
    training_position: str | None = Field(
        None, max_length=128, description="培训岗位（为空时尝试映射解析）"
    )
    hire_date: date = Field(..., description="入职日期")
    employee_id: UUID | None = Field(
        None, description="员工档案ID（前端匹配到档案员工时携带）"
    )


class NewEmployeeTrainingPlanUpdate(BaseModel):
    """更新新员工培训计划 - 请求（字段可选）"""

    deadline_date: date | None = Field(None, description="培训截止日期")
    training_position: str | None = Field(
        None, description="岗位培训清单岗位（调岗时更新，将重算教材明细）"
    )
    items: list[NewEmployeeTrainingPlanItem] | None = Field(
        None, description="计划项（全量）"
    )


class NewEmployeeTrainingItemAdd(BaseModel):
    """手动添加计划项 - 请求"""

    level: str = Field("部门级", max_length=16, description="级别: 部门级, 岗位级")
    textbook_name: str = Field(..., max_length=256, description="培训教材名称")
    textbook_code: str | None = Field(None, max_length=128, description="编号")
    assessment_method: str | None = Field(None, max_length=32, description="考核方式")
    remark: str | None = Field(None, max_length=512, description="备注")


class TraineeInfo(BaseModel):
    """参训人员信息"""

    name: str = Field(..., max_length=64, description="姓名")
    department: str = Field(..., max_length=128, description="部门")


class NewEmployeeTrainingStartRequest(BaseModel):
    """开始培训 - 请求（勾选的计划项 + 可选的参训人员）"""

    item_ids: list[str] = Field(..., description="勾选的计划项ID（≤5个）")
    additional_trainees: list[TraineeInfo] | None = Field(
        None, description="额外参训人员（与发起人一起培训）"
    )


class NewEmployeeTrainingStartResponse(BaseModel):
    """开始培训 - 响应（跳转培训资料页面预填用）"""

    session_id: UUID
    topic: str
    employee_names: list[str] = Field(default_factory=list)
    employee_dept_map: dict[str, str] = Field(default_factory=dict)
    department: str
    training_level: str = "部门级"
    plan_year: int | None = None


class NewEmployeeTrainingPlanResponse(BaseModel):
    """新员工培训计划 - 响应（含实时进度）"""

    id: UUID
    employee_id: UUID
    employee_name: str
    employee_number: str | None = None
    department: str
    sub_department: str | None = None
    position: str
    training_position: str | None = None
    hire_date: date
    deadline_date: date
    items: list[NewEmployeeTrainingPlanItem] = Field(default_factory=list)
    status: str
    # 实时进度（service 从培训台账计算）
    total_count: int = 0
    completed_count: int = 0
    progress: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class NewEmployeeTrainingPendingEmployee(BaseModel):
    """入职3个月内、尚未生成培训计划的员工"""

    employee_id: UUID
    employee_name: str
    employee_number: str | None = None
    department: str
    position: str
    hire_date: date


class NewEmployeeTrainingListItem(BaseModel):
    """列表项 - 已有计划或待生成计划的员工"""

    plan_id: UUID | None = None
    employee_id: UUID
    employee_name: str
    employee_number: str | None = None
    department: str
    sub_department: str | None = None
    position: str
    hire_date: date
    deadline_date: date | None = None
    status: str | None = None
    total_count: int = 0
    completed_count: int = 0
    progress: int = 0
    training_position: str | None = Field(None, description="培训岗位（从映射表获取）")


class NewEmployeeTrainingStats(BaseModel):
    """新员工培训统计"""

    pending: int = 0
    training: int = 0
    completed: int = 0
    overdue: int = 0
