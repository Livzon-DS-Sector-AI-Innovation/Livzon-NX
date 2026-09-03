"""HR business ORM models live here."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base_model import BaseModel


class HrDepartment(BaseModel):
    __tablename__ = "departments"
    __table_args__ = (
        Index("ix_departments_parent_id", "parent_id"),
        Index("ix_departments_feishu_open_id", "feishu_open_department_id"),
        {"schema": "hr"},
    )

    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="部门名称")
    code: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, comment="部门编码"
    )
    description: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="部门描述"
    )
    leader_name: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="部门负责人"
    )
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("hr.departments.id"), nullable=True, comment="父部门ID"
    )
    feishu_open_department_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="飞书 open_department_id"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="排序顺序"
    )
    headcount: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="编制人数（人事手动填写）"
    )
    current_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="在职人数（飞书同步的member_count）"
    )
    responsibilities: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="部门职责描述"
    )
    category: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="部门分类"
    )

    teams: Mapped[list["Team"]] = relationship(
        "Team", back_populates="department", lazy="select"
    )
    children: Mapped[list["HrDepartment"]] = relationship(
        "HrDepartment", back_populates="parent", lazy="select"
    )
    parent: Mapped["HrDepartment | None"] = relationship(
        "HrDepartment",
        back_populates="children",
        remote_side="HrDepartment.id",
        lazy="select",
    )


class Team(BaseModel):
    __tablename__ = "teams"
    __table_args__ = (
        Index("ix_teams_department_id", "department_id"),
        Index("ix_teams_name", "name"),
        {"schema": "hr"},
    )

    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="班组名称")
    code: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="班组编码"
    )
    description: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="班组描述"
    )
    department_id: Mapped[UUID] = mapped_column(
        ForeignKey("hr.departments.id"), nullable=False, comment="所属部门ID"
    )

    department: Mapped["HrDepartment"] = relationship(
        "HrDepartment", back_populates="teams", lazy="select"
    )


class Employee(BaseModel):
    __tablename__ = "employees"
    __table_args__ = (
        Index("ix_employees_department", "department"),
        Index("ix_employees_status", "status"),
        Index("ix_employees_feishu_record_id", "feishu_record_id"),
        # 软删除员工不再占用工号：仅未删除行要求工号唯一（离职同工号再入职）
        Index(
            "uq_employees_employee_number_active",
            "employee_number",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "hr"},
    )

    # ─── Core identifiers ──
    employee_number: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="工号"
    )
    seq_number: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="序号（飞书自动编号）"
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="姓名")
    domain_account: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="域账号"
    )

    # ─── Department & job ───
    department: Mapped[str] = mapped_column(String(64), nullable=False, comment="部门")
    sub_department: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="二级部门"
    )
    team: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="班组")
    position: Mapped[str] = mapped_column(String(64), nullable=False, comment="职位")
    job_category: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="职类"
    )
    level: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="级别")
    employment_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="人员就业方式"
    )

    # ─── Qualifications ───
    qualifications: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True, comment="职称／职业资格（多选）"
    )
    qualification_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="职称类型"
    )
    certificate_number: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="证书编号"
    )
    certificate_review_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="技能证书复审时间"
    )

    # ─── Personal info ───
    gender: Mapped[str | None] = mapped_column(String(8), nullable=True, comment="性别")
    ethnic_group: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="民族"
    )
    native_place: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="籍贯"
    )
    political_status: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="政治面貌"
    )
    marital_status: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="婚姻状况"
    )
    health_status: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="健康状况"
    )
    household_type: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="户籍类型"
    )
    status_category: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="统计类别"
    )

    # ─── Birth date (split as in Feishu) ───
    birth_year: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="出生年份"
    )
    birth_month: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="出生月份"
    )
    birth_day: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="出生日期"
    )
    age: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="年龄（飞书公式）"
    )

    # ─── Dates ───
    work_start_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="参加工作时间"
    )
    factory_entry_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="进厂时间"
    )
    livo_entry_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="入丽珠时间"
    )
    hire_date: Mapped[date] = mapped_column(Date, nullable=False, comment="入职日期")
    graduation_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="毕业时间"
    )

    # ─── Computed tenure (read-only mirrors of Feishu formulas) ───
    work_years: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="工作年限（飞书公式）"
    )
    factory_tenure: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="厂龄（飞书公式）"
    )
    company_tenure: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="司龄（飞书公式）"
    )

    # ─── Education ───
    education: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="学历"
    )
    degree: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="学位"
    )
    classification: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="分类：全日制/非全日制"
    )
    school: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="毕业学校"
    )
    major: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="专业")

    # ─── ID & address ───
    id_card: Mapped[str | None] = mapped_column(
        String(18), nullable=True, comment="身份证号"
    )
    id_card_expiry: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="身份证到期日"
    )
    id_card_address: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="身份证地址|家庭地址"
    )
    current_address: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="现住址"
    )

    # ─── Contract ───
    contract_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="合同期限"
    )
    contract_start_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="合同开始日期（第一次）"
    )
    contract_end_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="合同结束日期（第一次）"
    )
    contract_start_2: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="第二次合同起点"
    )
    contract_end_2: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="第二次合同终止"
    )
    contract_start_3: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="第三次合同起点"
    )
    contract_end_3: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="第三次合同终止"
    )
    contract_start_4: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="第四次合同起点"
    )
    contract_end_4: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="第四次合同终止"
    )
    contract_start_5: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="第五次续签合同日期"
    )
    contract_end_5: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="合同截止日期5"
    )
    contract_start_6: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="第六次续签合同日期"
    )
    contract_end_6: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="合同截止日期6"
    )
    contract_opinion: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="合同审批意见: 同意续签/不同意续签"
    )
    dept_leader_name: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="合同审批负责人"
    )

    # ─── Contact ───
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="手机")
    email: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="邮箱"
    )
    emergency_contact_name: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="紧急联系人姓名"
    )
    emergency_contact_phone: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="紧急联系人电话"
    )
    emergency_contact_relation: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="紧急联系人关系"
    )

    # ─── Banking & training ───
    bank_account: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="银行卡号"
    )
    training_id: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="培训档案编号"
    )
    archive_number: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="档案编号"
    )

    # ─── Work experience ───
    work_experience_1: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="工作经验一"
    )
    work_experience_2: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="工作经验二"
    )
    work_experience_3: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="工作经验三"
    )
    work_experience_4: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="工作经验四"
    )

    # ─── Work history & remarks ───
    transfer_history: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="异动（含曾经工作部门、岗位)"
    )
    remarks: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True, comment="备注（多选）"
    )

    # ─── Status ───
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="待审批",
        server_default="待审批",
        comment="状态: 在职, 离职, 试用期, 待审批",
    )
    probation_status: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="转正状态"
    )
    planned_probation_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="拟转正日期"
    )
    probation_effective_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="转正生效日期"
    )
    last_working_day: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="最后工作日"
    )
    offboarding_type: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="离职类型"
    )
    offboarding_reason: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="离职原因"
    )

    # ─── Feishu sync metadata ───
    feishu_open_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="飞书 open_id"
    )
    feishu_record_id: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="飞书多维表格 record_id"
    )
    feishu_synced_at: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="上次飞书同步时间"
    )


class OffboardingRecord(BaseModel):
    """离职管理记录 - 离职人员完整档案快照"""

    __tablename__ = "offboarding_records"
    __table_args__ = (
        Index("ix_offboarding_employee_id", "employee_id"),
        Index("ix_offboarding_date", "offboarding_date"),
        Index("ix_offboarding_feishu_record_id", "feishu_record_id"),
        {"schema": "hr"},
    )

    # ─── Employee relationship ───
    employee_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("hr.employees.id"),
        nullable=True,
        comment="员工ID",
    )

    # ─── Core identifiers ───
    seq_number: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="序号（飞书自动编号）"
    )
    employee_number: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="工号"
    )
    name: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="姓名")
    domain_account: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="域账号"
    )

    # ─── Personal info ───
    gender: Mapped[str | None] = mapped_column(String(8), nullable=True, comment="性别")
    ethnic_group: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="民族"
    )
    native_place: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="籍贯"
    )
    political_status: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="政治面貌"
    )
    marital_status: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="婚姻状况"
    )
    health_status: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="健康状况"
    )
    household_type: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="户籍类型"
    )
    status_category: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="统计类别"
    )

    # ─── Birth date ───
    birth_year: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="出生年份"
    )
    birth_month: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="出生月份"
    )
    birth_day: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="出生日期"
    )
    age: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="年龄")

    # ─── ID & address ───
    id_card: Mapped[str | None] = mapped_column(
        String(18), nullable=True, comment="身份证号"
    )
    id_card_expiry: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="身份证有效期截止日期"
    )
    current_address: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="现居住地址"
    )

    # ─── Contact ───
    phone: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="联系电话"
    )
    email: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="电子邮箱"
    )
    emergency_contact_name: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="紧急联系人"
    )
    emergency_contact_phone: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="紧急联系人电话"
    )
    emergency_contact_relation: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="与本人关系"
    )

    # ─── Department & job ───
    department: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="一级部门"
    )
    sub_department: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="二级部门"
    )
    position: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="职位/岗位"
    )
    level: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="职级")
    employment_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="人员就业方式"
    )
    probation_status: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="转正状态"
    )
    probation_effective_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="转正生效日期"
    )

    # ─── Career dates ───
    hire_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="入职日期"
    )
    work_start_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="参加工作时间"
    )
    factory_entry_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="进本公司时间"
    )
    livo_entry_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="入丽珠时间"
    )
    work_years: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="工龄"
    )
    offboarding_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="最后工作日"
    )

    # ─── Offboarding specific ───
    offboarding_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="辞职",
        server_default="辞职",
        comment="离职类型: 辞职, 辞退, 合同到期, 退休, 其他",
    )
    reason: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="离职原因"
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="在职",
        server_default="在职",
        comment="在职状态: 在职, 离职",
    )

    # ─── Education ───
    education: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="学历"
    )
    degree: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="学位"
    )
    major: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="专业")
    school: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="毕业院校"
    )
    graduation_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="毕业时间"
    )

    # ─── Qualifications ───
    qualification_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="职称"
    )
    qualifications: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True, comment="技能证书"
    )
    certificate_number: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="证书编号"
    )
    certificate_review_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="技能证书复审时间"
    )

    # ─── Contract ───
    contract_start_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="首次签订合同日期"
    )
    contract_end_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="首次签订合同截止日期"
    )
    contract_end_2: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="合同截止日期2"
    )
    contract_end_3: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="合同截止日期3"
    )
    contract_end_4: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="合同截止日期4"
    )
    contract_end_5: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="合同截止日期5"
    )
    contract_start_2: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="第二次续签合同日期"
    )
    contract_start_3: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="第三次续签合同日期"
    )
    contract_start_4: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="第四次续签合同日期"
    )
    contract_start_5: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="第五次续签合同日期"
    )
    contract_start_6: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="第六次续签合同日期"
    )

    # ─── Work experience ───
    work_experience_1: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="工作经验一"
    )
    work_experience_2: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="工作经验二"
    )
    work_experience_3: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="工作经验三"
    )
    work_experience_4: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="工作经验四"
    )

    # ─── Archive ───
    archive_number: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="档案编号"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")

    # 新增：离职流程字段
    materials_sent: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        default=False,
        comment="离职材料是否已发送",
    )
    materials_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="离职材料发送时间"
    )
    reminder_sent: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        default=False,
        comment="超时提醒是否已发送",
    )
    reminder_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="超时提醒发送时间"
    )
    completed_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="办结日期"
    )

    # ─── Feishu sync metadata ───
    feishu_record_id: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="飞书多维表格 record_id"
    )
    feishu_synced_at: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="上次飞书同步时间"
    )

    employee: Mapped["Employee"] = relationship("Employee", lazy="select")


class PositionTransferRecord(BaseModel):
    """岗位调动管理记录 - 飞书多维表格为主源，本地 DB 做缓存"""

    __tablename__ = "position_transfer_records"
    __table_args__ = (
        Index("ix_position_transfer_employee_id", "employee_id"),
        Index("ix_position_transfer_effective_date", "effective_date"),
        Index("ix_position_transfer_feishu_record_id", "feishu_record_id"),
        {"schema": "hr"},
    )

    # ─── Employee relationship ───
    employee_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("hr.employees.id"),
        nullable=True,
        comment="员工ID",
    )

    # ─── Core identifiers ───
    seq_number: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="序号（飞书自动编号）"
    )
    employee_number: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="工号"
    )
    employee_name: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="申请人"
    )

    # ─── Before transfer ───
    department_before: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="原部门"
    )
    sub_department_before: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="二级部门"
    )
    original_position: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="原职位"
    )

    # ─── After transfer (apply) ───
    apply_department: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="申请部门"
    )
    sub_department_after: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="二级部门（变动后）"
    )
    apply_position: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="申请职位"
    )

    # ─── Transfer info ───
    effective_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="生效日期"
    )
    transfer_reason: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="调动原因"
    )
    contact_phone: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="联系电话"
    )
    applicant_confirmation_text: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="申请人确认说明"
    )
    applicant_signature: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="申请人签名"
    )
    applicant_confirmation_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="申请人确认日期"
    )
    approval_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="草稿",
        server_default="草稿",
        comment="审批状态: 草稿, 待审批, 已通过, 已拒绝",
    )
    approver: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="审批人"
    )
    approval_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="审批日期"
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")

    # ─── Multi-step approval flow ───
    approval_flow: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="审批流程状态"
    )
    # 示例结构:
    # {
    #   "current_step": 3,
    #   "applicant_name": "张三",
    #   "applicant_date": "2026.07.22",
    #   "is_supervisor_level": true,
    #   "steps": [
    # {"node": "applicant", "label": "申请人确认",
    # "status": "approved", "signer": "张三",
    # "date": "2026.07.22", "opinion": ""},
    # {"node": "origin_direct_leader", "label": "原部门直属领导", "status": "approved",
    # "signer": null, "date": null, "opinion": null},
    #     ...
    #   ]
    # }
    feishu_approval_message_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="飞书审批通知消息ID"
    )

    # ─── Feishu sync metadata ───
    feishu_record_id: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="飞书多维表格 record_id"
    )
    feishu_synced_at: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="上次飞书同步时间"
    )

    employee: Mapped["Employee | None"] = relationship("Employee", lazy="select")


class TrainingLedger(BaseModel):
    __tablename__ = "training_ledgers"
    __table_args__ = (
        Index("ix_training_ledgers_employee_number", "employee_number"),
        Index("ix_training_ledgers_training_date", "training_date"),
        {"schema": "hr"},
    )

    employee_number: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="工号（培训级台账记录可为空）"
    )
    training_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="培训日期"
    )
    training_subject: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="培训课程/主题"
    )
    training_method: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="培训方式"
    )
    duration_hours: Mapped[float | None] = mapped_column(nullable=True, comment="课时")
    location: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="培训地点"
    )
    trainer: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="培训单位/培训师"
    )
    assessment_result: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="考核成绩"
    )
    source_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="manual",
        server_default="manual",
        comment="来源: manual手动, notification培训通知关联",
    )
    source_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="来源ID"
    )
    remarks: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="备注"
    )
    # ── 新增字段（年度培训统计表 SMP-HR-002-14）──
    training_datetime: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="培训时间（日期+时间）"
    )
    training_content: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="培训内容（含文件编号）"
    )
    teaching_dept: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="授课部门"
    )
    instructor: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="授课人"
    )
    level_category: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="一级/二级"
    )
    involved_depts: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="涉及部门"
    )
    trainees: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="培训对象（人员名单）"
    )
    training_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="培训类型（管理类/EHS培训/质量类）"
    )
    ledger_assessment_method: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="考核方式（口试/笔试）"
    )
    plan_source: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="部门/公司计划"
    )
    drug_category: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="人药/兽药"
    )
    score_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="成绩汇总"
    )
    session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("hr.training_sessions.id"),
        nullable=True,
        comment="关联培训会话（回看签到/评估/通知/口试/实操资料）",
    )
    # ── 台账多部门管理字段（每部门一条副本，授课部门一致）──
    ledger_department: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="记录归属部门（部门Tab筛选依据）"
    )
    owner_deleted: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        server_default="false",
        comment="主办方已删除标记（其他部门副本变红提示）",
    )
    second_level_status: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
        comment="二级培训确认: pending待确认/done已完成二级/not_needed不需二级",
    )
    is_presented: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="是否呈现（默认显示，不呈现则不进入员工培训清单）",
    )


class TrainingLedgerPage(BaseModel):
    """培训台账专属页面配置（动态菜单持久化）"""

    __tablename__ = "training_ledger_pages"
    __table_args__ = ({"schema": "hr"},)

    employee_number: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, comment="工号"
    )
    employee_name: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="员工姓名"
    )


class AnnualTrainingPlan(BaseModel):
    __tablename__ = "annual_training_plans"
    __table_args__ = (
        Index("ix_annual_training_plans_year", "year"),
        Index("ix_annual_training_plans_department", "department"),
        {"schema": "hr"},
    )

    year: Mapped[int] = mapped_column(Integer, nullable=False, comment="年度")
    department: Mapped[str] = mapped_column(String(64), nullable=False, comment="部门")
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="草稿",
        server_default="草稿",
        comment="状态: 草稿, 已确认",
    )
    plan_level: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="公司级",
        server_default="公司级",
        comment="计划级别: 公司级, 部门级",
    )
    version: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="版本号（如 01）"
    )
    remarks: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="备注（表格底部整行备注内容）"
    )

    items: Mapped[list["AnnualTrainingPlanItem"]] = relationship(
        "AnnualTrainingPlanItem",
        back_populates="plan",
        lazy="select",
    )


class AnnualTrainingPlanItem(BaseModel):
    __tablename__ = "annual_training_plan_items"
    __table_args__ = (
        Index("ix_annual_training_plan_items_plan_id", "plan_id"),
        {"schema": "hr"},
    )

    plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("hr.annual_training_plans.id"),
        nullable=False,
        comment="年度计划ID",
    )
    month: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="月份")
    trainee_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="培训人数"
    )
    duration_hours: Mapped[float | None] = mapped_column(nullable=True, comment="课时")
    content_and_textbook: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="培训内容及使用教材"
    )
    target_audience: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="培训对象"
    )
    position_and_count: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="参加岗位/参加人数"
    )
    training_method: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="培训方式"
    )
    training_hours: Mapped[float | None] = mapped_column(
        nullable=True, comment="培训学时"
    )
    confirmer: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="确认者"
    )
    confirm_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="确认日期"
    )
    remarks: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="备注"
    )
    tracking_status: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="培训跟踪: 完成, 未完成"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="排序",
    )
    # ── 新增字段（SMP-HR-002-14 二次开发）──
    training_type: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="培训类型: 内训, 外训"
    )
    training_month: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="培训时间（月度）"
    )
    content_textbook: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="培训内容或使用教材"
    )
    target_audience_new: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="培训对象"
    )
    instructor: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="授课单位或人员"
    )
    assessment_method: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="考核方式"
    )

    plan: Mapped["AnnualTrainingPlan"] = relationship(
        "AnnualTrainingPlan", back_populates="items", lazy="select"
    )


class HrFeishuAppSettings(BaseModel):
    __tablename__ = "hr_feishu_app_settings"
    __table_args__ = {"schema": "hr"}

    app_id: Mapped[str] = mapped_column(String(100), nullable=False)
    app_secret: Mapped[str] = mapped_column(Text, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    last_test_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_test_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_tested_at: Mapped[date | None] = mapped_column(Date, nullable=True)


class HrFeishuEntitySetting(BaseModel):
    __tablename__ = "hr_feishu_entity_settings"
    __table_args__ = {"schema": "hr"}

    entity_code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    entity_name: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_group: Mapped[str] = mapped_column(String(100), nullable=False)
    app_token: Mapped[str | None] = mapped_column(String(100), nullable=True)
    base_table_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    base_table_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    enable_push_to_feishu: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    enable_pull_from_feishu: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    field_mappings: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, default=list
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_sync_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[date | None] = mapped_column(Date, nullable=True)


class HrDeptApprovalConfig(BaseModel):
    """部门级审批人配置（岗位调动审批用）"""

    __tablename__ = "hr_dept_approval_configs"
    __table_args__ = (
        Index("ix_hr_dept_approval_dept", "department_id"),
        {"schema": "hr"},
    )

    department_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("hr.departments.id"),
        nullable=True,
        comment="部门ID（部门表为空时为空，按 department_name 展示）",
    )
    department_name: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="部门名称（冗余，方便展示）"
    )
    direct_leader_name: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="部门直属领导"
    )
    direct_leader_open_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="部门直属领导飞书open_id"
    )
    manager_name: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="部门经理"
    )
    manager_open_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="部门经理飞书open_id"
    )
    director_name: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="部门总监"
    )
    director_open_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="部门总监飞书open_id"
    )
    vp_name: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="主管领导"
    )
    vp_open_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="主管领导飞书open_id"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    department: Mapped["HrDepartment | None"] = relationship(
        "HrDepartment", lazy="select"
    )


class HrReminderConfig(BaseModel):
    """HR通用提醒配置（按模块+实体分组，每个提醒项一行）"""

    __tablename__ = "hr_reminder_configs"
    __table_args__ = (
        Index("ix_hr_reminder_configs_entity", "entity_code", "reminder_type"),
        {"schema": "hr"},
    )

    entity_code: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment=(
            "业务实体: contract_renewal/offboarding/onboa"
            "rding/recruitment/position_transfer"
        ),
    )
    entity_label: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="实体显示名: 合同续签/离职管理/入职管理/招聘管理/岗位调动",
    )
    module_group: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="模块分组: 合同管理/离职管理/招聘入职/岗位调动",
    )
    reminder_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="提醒类型: 如 contract_expiry/offboarding_due/onboarding_training",
    )
    reminder_label: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="提醒显示名: 如 合同到期提醒"
    )
    reminder_days: Mapped[list[Any]] = mapped_column(
        JSON, default=[90, 60, 30], comment="提醒天数列表"
    )
    notify_channels: Mapped[list[Any]] = mapped_column(
        JSON, default=["feishu"], comment="通知渠道: feishu/system"
    )
    recipient_open_ids: Mapped[list[Any]] = mapped_column(
        JSON, default=[], comment="接收人open_id列表"
    )
    dept_notify_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否通知部门负责人"
    )
    message_template: Mapped[str] = mapped_column(
        Text, default="", comment="提醒消息模板，支持变量"
    )
    auto_action: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否自动触发动作（如自动创建审批）"
    )
    auto_action_target: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="自动动作目标: 如 草稿/部门负责人"
    )
    trigger_frequency: Mapped[str] = mapped_column(
        String(16), default="monthly", comment="触发频率: monthly/quarterly/daily"
    )
    trigger_day: Mapped[int] = mapped_column(
        Integer, default=1, comment="触发日期: 每月几号(1-28)"
    )
    trigger_hour: Mapped[int] = mapped_column(
        Integer, default=9, comment="触发时间点: 几点(0-23)"
    )
    notify_hours: Mapped[int] = mapped_column(
        Integer, default=24, comment="离职记录创建后多少小时提醒(最大72)"
    )
    # 合同签署通知配置（contract_renewal 实体用）
    sign_clerk_open_ids: Mapped[list[Any]] = mapped_column(
        JSON,
        default=[],
        comment="签署办事员open_id列表（审批通过后通知，为空回退recipient_open_ids）",
    )
    sign_clerk_names: Mapped[list[Any]] = mapped_column(
        JSON, default=[], comment="签署办事员姓名列表"
    )
    sign_reminder_days: Mapped[int] = mapped_column(
        Integer, default=7, comment="合同签署催签间隔天数（默认7天）"
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序")


class HrApprovalConfig(BaseModel):
    """HR通用审批流程配置（每个模块每个角色一行）"""

    __tablename__ = "hr_approval_configs"
    __table_args__ = (
        Index("ix_hr_approval_configs_entity_role", "entity_code", "role"),
        {"schema": "hr"},
    )

    entity_code: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment=(
            "业务实体: contract_renewal/offboarding/onboa"
            "rding/recruitment/position_transfer"
        ),
    )
    entity_label: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="实体显示名"
    )
    module_group: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="模块分组"
    )
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="审批角色: dept/supervisor/hr/gm"
    )
    role_label: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="角色显示名: 部门负责人/分管领导/HR负责人/总经理",
    )
    approver_open_ids: Mapped[list[Any]] = mapped_column(
        JSON, default=[], comment="审批人open_id列表"
    )
    approver_names: Mapped[list[Any]] = mapped_column(
        JSON, default=[], comment="审批人姓名列表"
    )
    deadline_days: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="审批时限（天）"
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序")


class HrReminderDeptRecipient(BaseModel):
    """提醒接收人-部门级覆盖配置（每个提醒项+部门一行）"""

    __tablename__ = "hr_reminder_dept_recipients"
    __table_args__ = (
        Index("ix_hr_reminder_dept_recipients", "reminder_config_id", "department"),
        {"schema": "hr"},
    )

    reminder_config_id: Mapped[UUID] = mapped_column(
        ForeignKey("hr.hr_reminder_configs.id"),
        nullable=False,
        comment="关联hr_reminder_configs的id",
    )
    department: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="部门名称"
    )
    recipient_open_ids: Mapped[list[Any]] = mapped_column(
        JSON, default=[], comment="接收人open_id列表"
    )
    recipient_names: Mapped[list[Any]] = mapped_column(
        JSON, default=[], comment="接收人姓名列表"
    )
    use_dept_leader: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="是否使用部门负责人作为默认接收人"
    )


class HrPushTemplate(BaseModel):
    """HR推送消息模板（邮件 + 飞书通用）"""

    __tablename__ = "hr_push_templates"
    __table_args__ = (
        Index("ix_hr_push_templates_scene", "entity_code", "scene_code", "channel"),
        {"schema": "hr"},
    )

    entity_code: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="业务实体: recruitment"
    )
    scene_code: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="场景编码: interview_notice/offer_notice"
    )
    scene_label: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="场景显示名"
    )
    channel: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="推送渠道: email/feishu"
    )
    title_template: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="标题模板，支持变量 {name} {position} 等"
    )
    body_template: Mapped[str] = mapped_column(
        Text, nullable=False, comment="正文模板（邮件为HTML，飞书为纯文本或卡片JSON）"
    )
    available_variables: Mapped[list[Any]] = mapped_column(
        JSON, default=[], comment="可用变量列表"
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", comment="是否启用"
    )


class HrPushLog(BaseModel):
    """HR推送记录日志"""

    __tablename__ = "hr_push_logs"
    __table_args__ = (
        Index("ix_hr_push_logs_entity_scene", "entity_code", "scene_code"),
        Index("ix_hr_push_logs_status", "status"),
        {"schema": "hr"},
    )

    entity_code: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="业务实体: recruitment"
    )
    scene_code: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="场景编码"
    )
    channel: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="推送渠道: email/feishu"
    )
    recipient: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="接收人（邮箱地址或飞书open_id）"
    )
    recipient_name: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="接收人姓名"
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False, comment="推送标题")
    content_snippet: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="内容摘要（前500字符）"
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        server_default="pending",
        comment="状态: pending/success/failed",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="失败原因"
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="发送时间"
    )
    candidate_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="关联候选人ID（飞书record_id）"
    )
    candidate_name: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="候选人姓名"
    )
    triggered_by: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="触发人"
    )


class HrPushRecipient(BaseModel):
    """HR推送接收人配置（按场景+渠道配置接收人）"""

    __tablename__ = "hr_push_recipients"
    __table_args__ = (
        Index("ix_hr_push_recipients_scene", "entity_code", "scene_code", "channel"),
        {"schema": "hr"},
    )

    entity_code: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="业务实体: recruitment"
    )
    scene_code: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="场景编码: interview_notice/offer_notice"
    )
    channel: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="推送渠道: feishu"
    )
    department: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="关联部门（为空表示全局默认）"
    )
    recipient_open_ids: Mapped[list[Any]] = mapped_column(
        JSON, default=[], comment="接收人飞书open_id列表"
    )
    recipient_names: Mapped[list[Any]] = mapped_column(
        JSON, default=[], comment="接收人姓名列表"
    )
    use_dept_leader: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        comment="是否默认使用部门负责人（仅面试通知场景有效）",
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", comment="是否启用"
    )


class ContractManagement(BaseModel):
    """合同管理（对应飞书多维表格"合同管理"表）"""

    __tablename__ = "contract_management"
    __table_args__ = (
        Index("ix_contract_management_employee_number", "employee_number"),
        Index("ix_contract_management_dept_level1", "dept_level1"),
        {"schema": "hr"},
    )

    seq_number: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="序号"
    )
    employee_number: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="工号"
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="姓名")
    gender: Mapped[str | None] = mapped_column(String(4), nullable=True, comment="性别")
    dept_level1: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="一级部门"
    )
    dept_level2: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="二级部门"
    )
    position: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="职务|岗位"
    )
    job_level: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="职级"
    )
    domain_account: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="域账户"
    )
    id_card: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="身份证号"
    )
    id_card_expiry: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="身份证有效期截止日期"
    )
    archive_number: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="档案编号"
    )
    contract_sequence: Mapped[str | None] = mapped_column(
        String(8), nullable=True, comment="第几次合同"
    )
    contract_start_1: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="首次签订合同日期"
    )
    contract_end_1: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="首次签订合同截止日期"
    )
    contract_start_2: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="第二次续签合同日期"
    )
    contract_end_2: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="合同截止日期（2）"
    )
    contract_start_3: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="第三次续签合同日期"
    )
    contract_end_3: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="合同截止日期（3）"
    )
    contract_start_4: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="第四次续签合同日期"
    )
    contract_end_4: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="合同截止日期4"
    )
    contract_start_5: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="第五次续签合同日期"
    )
    contract_end_5: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="合同截止日期5"
    )
    contract_start_6: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="第六次续签合同日期"
    )
    contract_end_6: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="合同截止日期6"
    )
    # 审批字段（线上审批流程）
    dept_leader_name: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="部门负责人"
    )
    contract_opinion: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="合同意见: 同意续签/不同意续签"
    )
    # 两级审批流程字段（本地流程状态，不同步飞书多维表格）
    approval_status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="dept_pending",
        server_default="dept_pending",
        comment="审批状态: dept_pending/supervisor_pending/approved/rejected",
    )
    supervisor_name: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="分管领导（第二级审批人）"
    )
    supervisor_open_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="分管领导飞书open_id"
    )
    dept_approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="部门负责人审批时间"
    )
    supervisor_approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="分管领导审批时间"
    )
    # 签署流程字段（本地流程状态，不同步飞书多维表格）
    signed_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="待签署",
        server_default="待签署",
        comment="签署状态: 待签署/已签署/拒签",
    )
    signed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="签署时间"
    )
    sign_reminded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="上次催签时间"
    )
    # 飞书多维表格同步元数据
    feishu_record_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="飞书多维表格 record_id"
    )
    feishu_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="上次飞书同步时间"
    )


class HrFeishuMember(BaseModel):
    """飞书人员缓存表（完整通讯录快照；一人多部门时每个部门一行）"""

    __tablename__ = "hr_feishu_members"
    __table_args__ = (
        UniqueConstraint(
            "open_id", "department", name="uq_hr_feishu_members_open_id_dept"
        ),
        {"schema": "hr"},
    )

    open_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="飞书open_id"
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="姓名")
    department: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="部门名称（取第一个部门）"
    )
    mobile: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="手机号"
    )
    email: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="邮箱"
    )
    enterprise_email: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="企业邮箱"
    )
    employee_no: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="工号"
    )
    job_title: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="职位"
    )
    gender: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="性别: 1男 2女"
    )
    avatar_url: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="头像URL"
    )
    status: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="状态: 1在职 2离职 3未激活 4暂停使用"
    )
    status_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="状态变化时间(冻结/离职日期)"
    )
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="最后同步时间",
    )


# ═══════════════════════════════════════════════════════════════
# 培训管理二次开发新增模型（SMP-HR-002-14）
# ═══════════════════════════════════════════════════════════════


class Trainer(BaseModel):
    """培训师清单"""

    __tablename__ = "trainers"
    __table_args__ = {"schema": "hr"}

    employee_id: Mapped[UUID | None] = mapped_column(
        nullable=True, comment="关联员工ID"
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="培训师姓名")
    department: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="部门"
    )
    position: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="岗位"
    )
    approval_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="批准时间"
    )
    approver: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="批准人"
    )
    remarks: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="备注"
    )


class TrainingEvaluation(BaseModel):
    """培训评估表"""

    __tablename__ = "training_evaluations"
    __table_args__ = {"schema": "hr"}

    training_content: Mapped[str | None] = mapped_column(
        String(4096), nullable=True, comment="培训内容"
    )
    training_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="培训日期"
    )
    duration_hours: Mapped[float | None] = mapped_column(nullable=True, comment="课时")
    training_method: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="培训方式"
    )
    other_method: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="其他方式说明"
    )
    instructor: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="授课人"
    )
    target_dept_person: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="培训对象（部门/班组/人员）"
    )
    expected_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="应到人数"
    )
    actual_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="实到人数"
    )
    absent_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="缺席人数"
    )
    textbook: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="培训教材"
    )
    absent_handling: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="缺席人员处理方式"
    )
    need_retraining: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, server_default="false", comment="是否需要再培训"
    )
    retraining_info: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="再培训信息"
    )
    assessment_method: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="考核方式"
    )
    excellent_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="优"
    )
    good_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="良好"
    )
    pass_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="合格"
    )
    fail_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="不合格"
    )
    absent_exam_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="缺考"
    )
    fail_handling: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="缺考及不合格人员处理方式"
    )
    makeup_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="补考人数"
    )
    makeup_pass_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="补考合格人数"
    )
    makeup_fail_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="补考不合格人数"
    )
    makeup_fail_handling: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="缺考及补考不合格人员处理方式"
    )
    evaluation_result: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="培训效果评估结果"
    )
    evaluation_comment: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="培训效果评估及其他"
    )
    evaluator: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="培训评估人"
    )
    evaluate_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="评估日期"
    )
    has_notification: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, server_default="false", comment="附件：培训通知"
    )
    has_signin_sheet: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, server_default="false", comment="附件：培训签到表"
    )
    has_textbook: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, server_default="false", comment="附件：培训教材"
    )
    has_exam_paper: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, server_default="false", comment="附件：考核试题试卷"
    )
    has_score_summary: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, server_default="false", comment="附件：成绩汇总表"
    )
    other_attachment: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="其他附件"
    )


class PositionTrainingList(BaseModel):
    """岗位培训清单（头表）"""

    __tablename__ = "position_training_lists"
    __table_args__ = (
        Index("ix_position_training_lists_dept", "department"),
        {"schema": "hr"},
    )

    department: Mapped[str] = mapped_column(String(128), nullable=False, comment="部门")
    position: Mapped[str] = mapped_column(String(128), nullable=False, comment="岗位")
    creator: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="制定人"
    )
    create_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="制定日期"
    )
    reviewer: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="审核人（部门负责人）"
    )
    review_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="审核日期"
    )
    approver: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="批准人（QA负责人）"
    )
    approve_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="批准日期"
    )

    items: Mapped[list["PositionTrainingListItem"]] = relationship(
        "PositionTrainingListItem",
        back_populates="list",
        lazy="select",
    )


class PositionTrainingListItem(BaseModel):
    """岗位培训清单明细"""

    __tablename__ = "position_training_list_items"
    __table_args__ = (
        Index("ix_position_training_list_items_list_id", "list_id"),
        {"schema": "hr"},
    )

    list_id: Mapped[UUID] = mapped_column(
        ForeignKey("hr.position_training_lists.id"),
        nullable=False,
        comment="清单ID",
    )
    level: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="级别: 部门级, 岗位级"
    )
    sort_order: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="排序"
    )
    textbook_name: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="培训教材名称"
    )
    textbook_code: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="编号"
    )
    assessment_method: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="考核方式"
    )
    remarks: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="备注"
    )

    list: Mapped["PositionTrainingList"] = relationship(
        "PositionTrainingList", back_populates="items", lazy="select"
    )


class PositionTrainingMapping(BaseModel):
    """员工档案岗位 → 岗位培训清单岗位 映射"""

    __tablename__ = "position_training_mappings"
    __table_args__ = (
        Index("ix_ptm_department", "department"),
        Index("ix_ptm_employee_position", "employee_position"),
        UniqueConstraint("department", "employee_position", name="uq_ptm_dept_pos"),
        {"schema": "hr"},
    )

    department: Mapped[str] = mapped_column(String(128), nullable=False, comment="部门")
    employee_position: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="员工档案岗位"
    )
    training_position: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="岗位培训清单岗位"
    )


class NewEmployeeTrainingPlan(BaseModel):
    """新员工培训计划（按岗位培训清单生成部门级培训计划，进度实时从培训台账计算）"""

    __tablename__ = "new_employee_training_plans"
    __table_args__ = (
        Index("ix_netp_employee_id", "employee_id"),
        Index("ix_netp_status", "status"),
        Index("ix_netp_deadline", "deadline_date"),
        {"schema": "hr"},
    )

    employee_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, comment="员工ID"
    )
    employee_name: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="员工姓名"
    )
    employee_number: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="工号"
    )
    department: Mapped[str] = mapped_column(String(128), nullable=False, comment="部门")
    sub_department: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="二级部门"
    )
    position: Mapped[str] = mapped_column(String(128), nullable=False, comment="岗位")
    training_position: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="岗位培训清单岗位（每人独立配置，调岗时更新并重算教材）",
    )
    hire_date: Mapped[date] = mapped_column(Date, nullable=False, comment="入职日期")
    mentor_name: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="导师"
    )
    deadline_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="培训截止日期（入职+1个月）"
    )
    items: Mapped[list[Any] | None] = mapped_column(
        JSONB, nullable=True, comment="部门级培训计划项快照"
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="待安排",
        server_default="待安排",
        comment="状态: 待安排, 培训中, 已完成, 逾期",
    )


class PlanTrackingRecord(BaseModel):
    """培训计划跟踪"""

    __tablename__ = "plan_tracking_records"
    __table_args__ = {"schema": "hr"}

    plan_id: Mapped[UUID | None] = mapped_column(
        nullable=True, comment="关联年度计划ID"
    )
    plan_item_id: Mapped[UUID | None] = mapped_column(
        nullable=True, comment="来源年度计划明细ID（自动录入溯源）"
    )
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="年度")
    month: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="跟踪月份"
    )
    plan_level: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="计划级别: 公司级, 部门级"
    )
    department: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="部门（部门级计划）"
    )
    sort_order: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="排序"
    )
    training_content: Mapped[str | None] = mapped_column(
        String(4096), nullable=True, comment="培训内容"
    )
    actual_time: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="实际培训时间"
    )
    target_audience: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="培训对象"
    )
    training_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="培训类型"
    )
    tracking_assessment_method: Mapped[str | None] = mapped_column(
        "assessment_method", String(32), nullable=True, comment="考核方式"
    )
    is_completed: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, server_default="false", comment="是否按计划完成"
    )
    tracker: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="跟踪人"
    )
    track_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="跟踪日期"
    )
    remarks: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="备注"
    )
    sessions_snapshot: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="上次自动汇总的培训会话时间（判断是否被手工修改）"
    )


class EsgTrainingRecord(BaseModel):
    """ESG 培训报表 — 16 列，每人每次培训一行"""

    __tablename__ = "esg_training_records"
    __table_args__ = (
        Index("ix_esg_training_department", "department"),
        Index("ix_esg_training_date", "training_date"),
        {"schema": "hr"},
    )

    training_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="培训日期"
    )
    training_name: Mapped[str] = mapped_column(
        String(4096), nullable=False, comment="培训名称"
    )
    training_method: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="培训方式"
    )
    caliber: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="口径"
    )
    training_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="培训类型"
    )
    employee_name: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="姓名"
    )
    employee_account: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="员工账号"
    )
    location_address: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="身份所属地"
    )
    department: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="部门"
    )
    employee_level: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="层级"
    )
    gender: Mapped[str | None] = mapped_column(String(8), nullable=True, comment="性别")
    age: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="年龄")
    duration: Mapped[float | None] = mapped_column(nullable=True, comment="培训时长")
    remarks: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="备注"
    )
    apply_company: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="单位名称"
    )
    apply_company_no: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="单位编码"
    )


class TrainingImportMapping(BaseModel):
    """部门培训统计导入格式记忆（AI 识别 + 人工确认后的列映射）"""

    __tablename__ = "training_import_mappings"
    __table_args__ = (
        Index(
            "ix_training_import_mappings_dept_fp",
            "department",
            "header_fingerprint",
            unique=True,
        ),
        {"schema": "hr"},
    )

    department: Mapped[str] = mapped_column(String(128), nullable=False, comment="部门")
    header_fingerprint: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="表头指纹（表头文本排序后的md5）"
    )
    header_row: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1", comment="表头行号"
    )
    mapping_json: Mapped[str] = mapped_column(
        Text, nullable=False, comment='列映射JSON，如 {"0":"training_datetime"}'
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="人工确认时间"
    )
    used_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="命中次数"
    )


class TrainingPersonnelConfig(BaseModel):
    """培训人员配置（按 培训级别+部门+配置名 维护参训人员名单）
    每个部门可有多个配置（如201车间→A班/B班/C班，QC→仪器组/综合组/理化组）。
    """

    __tablename__ = "training_personnel_configs"
    __table_args__ = (
        # 不同用户可各自建同名配置：唯一性按 (level, department, config_name,
        # created_by) 且仅未软删记录唯一（部分唯一索引，避免 is_deleted 进约束）
        Index(
            "ix_training_personnel_configs_level_dept_name_owner",
            "level",
            "department",
            "config_name",
            "created_by",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "hr"},
    )

    level: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="培训级别: 公司级/部门级"
    )
    department: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="部门(公司级为空)"
    )
    config_name: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="配置名称(用户自定义，如A班/仪器组)"
    )
    personnel: Mapped[list[Any]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="参训人员名单 [{name, employee_number, department}]",
    )
    remarks: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="备注"
    )


class HrCustomTrainingDepartment(BaseModel):
    """手动添加的培训部门（补充数据驱动部门）"""

    __tablename__ = "hr_custom_training_departments"
    __table_args__ = (
        Index("ix_hr_custom_training_depts_name", "name", unique=True),
        {"schema": "hr"},
    )

    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="部门名称")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="创建时间"
    )


class TrainingDeptMapping(BaseModel):
    """培训部门映射配置表（HR 设置维护，替代前后端硬编码字典）.

    覆盖：特殊映射/别名归并/201二级归一/仓储部家族/候选人来源/台账拆分/
    打印统一/弹窗专属规则/部门列表排除与强制补入。
    """

    __tablename__ = "training_dept_mappings"
    __table_args__ = (
        UniqueConstraint(
            "source_name",
            "match_level",
            "mapping_type",
            "target_name",
            name="uq_training_dept_mappings_source_level_type_target",
        ),
        Index("ix_training_dept_mappings_source", "source_name"),
        {"schema": "hr"},
    )

    source_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="源部门名（飞书/员工档案/手输名）"
    )
    target_name: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="目标培训部门名（modal_drop/exclude 类型为空）",
    )
    match_level: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default="first",
        server_default="first",
        comment="匹配层级: first仅一级/second仅二级/both两者（201家族用both）",
    )
    mapping_type: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="alias",
        server_default="alias",
        comment="类型: special/alias/candidate_source/split/print_unify/"
        "modal_drop/modal_extra/modal_no_expand/exclude/force_show",
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        server_default="100",
        comment="解析优先级（越小越优先）",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true", comment="是否启用"
    )
    remark: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="备注"
    )


class HrDocumentTemplate(BaseModel):
    """HR 文档模板存储 - 部署时预置，导出 Word 时从数据库读取"""

    __tablename__ = "hr_document_templates"
    __table_args__ = (
        Index("ix_hr_document_templates_code", "template_code", unique=True),
        {"schema": "hr"},
    )

    template_code: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="模板编码"
    )
    template_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="模板名称"
    )
    template_data: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False, comment="模板文件二进制数据"
    )
    content_type: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        server_default="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        comment="MIME 类型",
    )
    file_name: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="原始文件名"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="模板描述"
    )


class PlanAttachment(BaseModel):
    """年度培训计划附件 - 计划级附件清单（附件一/附件二…），明细行按"详见附件X"引用."""

    __tablename__ = "plan_attachments"
    __table_args__ = (
        Index("ix_plan_attachments_plan_id", "plan_id"),
        {"schema": "hr"},
    )

    plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("hr.annual_training_plans.id"),
        nullable=False,
        comment="所属年度培训计划",
    )
    annex_no: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="附件编号（附件一/附件二…，归一化存储）"
    )
    file_name: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="原始文件名"
    )
    file_data: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True, comment="附件二进制数据（MinIO 未启用时存库）"
    )
    storage_key: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="MinIO 对象键（启用对象存储时使用）"
    )
    file_size: Mapped[int | None] = mapped_column(
        nullable=True, comment="文件大小（字节）"
    )
    ledger_imported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="已导入培训台账时间（置灰不可再选）",
    )


class PlanAttachmentSection(BaseModel):
    """计划附件条目 - 从附件文件拆分的"附件X"条目，供跨模块（签到表等）索引."""

    __tablename__ = "plan_attachment_sections"
    __table_args__ = (
        Index("ix_plan_attachment_sections_plan_id", "plan_id"),
        Index("ix_plan_attachment_sections_attachment_id", "attachment_id"),
        {"schema": "hr"},
    )

    attachment_id: Mapped[UUID] = mapped_column(
        ForeignKey("hr.plan_attachments.id"),
        nullable=False,
        comment="所属附件文件",
    )
    plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("hr.annual_training_plans.id"),
        nullable=False,
        comment="所属年度培训计划（冗余，便于跨模块按 计划+附件号 索引）",
    )
    annex_no: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="附件编号（归一化为附件N）"
    )
    title: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="条目标题（sheet名/标题段原文）"
    )
    source_kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="来源类型: xlsx_sheet/docx_section/whole_file/ai",
    )
    source_ref: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="来源位置（sheet名/起始段落下标）"
    )


class TrainingContentUsed(BaseModel):
    """已巩固培训/已导入台账的附件文件清单条目（按文件名去重，置灰不可再选）."""

    __tablename__ = "training_content_used"
    __table_args__ = (
        Index("ix_training_content_used_name", "entry_name"),
        {"schema": "hr"},
    )

    entry_name: Mapped[str] = mapped_column(
        String(500), nullable=False, unique=True, comment="文件名称（去空白归一化）"
    )
    entry_code: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="录入时的最新文件编号"
    )
    attachment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("hr.plan_attachments.id"), nullable=True, comment="来源附件"
    )
    used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="导入培训台账时间"
    )


class TrainingSession(BaseModel):
    """培训会话 - 一次培训一行，聚合五类资料（签到/评估/通知/口试/实操）."""

    __tablename__ = "training_sessions"
    __table_args__ = (
        Index("ix_training_sessions_date", "training_date"),
        Index("ix_training_sessions_topic", "topic"),
        {"schema": "hr"},
    )

    training_level: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="公司级/部门级"
    )
    plan_year: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="计划年度"
    )
    department: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="主办部门"
    )
    trainee_departments: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, comment="受训部门列表"
    )
    topic: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="培训题目/内容概要"
    )
    training_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="培训日期"
    )
    time_start: Mapped[str | None] = mapped_column(
        String(8), nullable=True, comment="开始时间 HH:mm"
    )
    time_end: Mapped[str | None] = mapped_column(
        String(8), nullable=True, comment="结束时间 HH:mm"
    )
    training_method: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="培训方式"
    )
    instructor: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="授课人/评估人"
    )
    actual_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="实际受训人数"
    )
    employee_names: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, comment="受训人员名单"
    )
    employee_dept_map: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="人员→部门映射"
    )
    plan_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("hr.annual_training_plans.id"), nullable=True, comment="关联年度计划"
    )
    plan_item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("hr.annual_training_plan_items.id"),
        nullable=True,
        comment="关联计划项目",
    )
    parent_session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("hr.training_sessions.id"),
        nullable=True,
        comment="上级培训会话（二级培训来源，从台账一键创建时记录）",
    )
    checked_content: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, comment="已选附件培训内容（《名称》（编号）条目）"
    )


class TrainingDocument(BaseModel):
    """培训会话资料 - 五类表单 payload，保存历史+导出共用."""

    __tablename__ = "training_documents"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "doc_type", name="uq_training_documents_session_type"
        ),
        Index("ix_training_documents_session", "session_id"),
        {"schema": "hr"},
    )

    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("hr.training_sessions.id"), nullable=False, comment="所属培训会话"
    )
    doc_type: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        comment=(
            "资料类型: sign_in/evaluation/notification/or"
            "al_exam/practical_exam/attachment"
        ),
    )
    title: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="资料标题"
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, comment="表单全量数据（导出 Word 的输入）"
    )


class EmployeeTrainingListMember(BaseModel):
    """员工培训清单人员配置（部门→人员；一键导入飞书/手动添加/新员工自动合并）."""

    __tablename__ = "employee_training_list_members"
    __table_args__ = (
        UniqueConstraint(
            "department", "name", name="uq_employee_training_list_dept_name"
        ),
        Index("ix_employee_training_list_department", "department"),
        {"schema": "hr"},
    )

    department: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="培训部门（台账口径，含 201 归一化）"
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="姓名")
    employee_number: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="工号"
    )
    source: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="manual",
        server_default="manual",
        comment="来源: feishu一键导入/manual手动添加/auto新员工自动合并",
    )


class HrUserDeptScope(BaseModel):
    """用户可见部门配置（人事/培训模块部门级数据隔离）。

    visible_depts 存培训规范部门名数组；过滤时经 training_dept_aliases_of
    展开为档案口径别名集合，一套配置覆盖档案口径与培训规范口径。
    无配置时回退自动规则（用户只看自己部门）；管理员（hr:write）忽略本表。
    """

    __tablename__ = "hr_user_dept_scopes"
    __table_args__ = (
        Index("ix_hr_user_dept_scopes_user_id", "user_id", unique=True),
        {"schema": "hr"},
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity.users.id"),
        nullable=False,
        comment="用户ID（每个用户一条配置）",
    )
    visible_depts: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True, comment="管理员指定的可见培训部门（规范名数组）"
    )


# Preserve the former turnover snapshot tables for analysis and old reports.
from app.modules.hr.legacy_models import (  # noqa: E402,F401
    DepartureRecord,
    OnboardingRecord,
)
