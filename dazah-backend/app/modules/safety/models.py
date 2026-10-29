"""Safety ORM models."""

import uuid
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base_model import BaseModel

if TYPE_CHECKING:
    from app.platform.identity.models import User

# 业务表均软删除（is_deleted），唯一编号约束使用部分唯一索引
# (WHERE is_deleted = false)，避免「软删→重建同编号」触发约束冲突。
# 见 CLAUDE.md「软删除隐形 bug」注意事项。

# ==================== Enums ====================


class CheckType(StrEnum):
    """检查类型枚举（16种）"""

    DAILY = "daily"  # 日常检查
    SPECIAL = "special"  # 专项检查
    COMPREHENSIVE = "comprehensive"  # 综合检查
    HOLIDAY = "holiday"  # 节假日检查
    MONTHLY = "monthly"  # 月度安全检查
    SEASONAL = "seasonal"  # 季节性安全检查
    PRE_HOLIDAY = "pre_holiday"  # 节前安全检查
    LEADERSHIP_DUTY = "leadership_duty"  # 领导干部值班检查
    DEPT_CROSS = "dept_cross"  # 部门互查
    WEEKLY = "weekly"  # 周检
    RESUMPTION = "resumption"  # 复工复产安全检查
    CHANGE_ACCEPTANCE = "change_acceptance"  # 变更验收
    LIGHTNING = "lightning"  # 防雷检查
    SAFETY_VALVE = "safety_valve"  # 安全阀专项检查
    POST_HOLIDAY = "post_holiday"  # 节后复工检查
    HEATSTROKE_PREVENTION = "heatstroke_prevention"  # 防暑降温专项


class ChangeType(StrEnum):
    """变更类型枚举（三大类）"""

    PROCESS_TECH = "process_tech"  # 工艺技术变更
    EQUIPMENT_FACILITY = "equipment_facility"  # 设备设施变更
    MANAGEMENT = "management"  # 管理变更


class ChangeGrade(StrEnum):
    """变更等级枚举"""

    MAJOR = "major"  # 重大变更
    GENERAL = "general"  # 一般变更


class ChangeDuration(StrEnum):
    """变更期限枚举"""

    PERMANENT = "permanent"  # 永久性
    TEMPORARY = "temporary"  # 临时性
    EMERGENCY = "emergency"  # 紧急


class EhsChangeStatus(StrEnum):
    """EHS变更状态枚举"""

    DRAFT = "draft"  # 草稿
    UNDER_REVIEW = "under_review"  # 审核中
    APPROVED = "approved"  # 已批准
    REJECTED = "rejected"  # 已驳回
    IN_PROGRESS = "in_progress"  # 实施中
    COMMISSIONED = "commissioned"  # 已投用
    CLOSED = "closed"  # 已关闭


class RiskAssessmentMethod(StrEnum):
    """风险评估方法枚举"""

    LEC = "LEC"  # LEC评价法
    LS = "LS"  # LS风险矩阵
    JHA = "JHA"  # 工作危害分析
    HAZOP = "HAZOP"  # 危险与可操作性分析
    FMEA = "FMEA"  # 失效模式与影响分析
    SCL = "SCL"  # 安全检查表
    PHA = "PHA"  # 预先危险性分析
    LOPA = "LOPA"  # 保护层分析
    OTHER = "other"  # 其他


class RiskLevel(StrEnum):
    """风险等级枚举"""

    LEVEL_1 = "level_1"  # 一级/重大风险
    LEVEL_2 = "level_2"  # 二级/较大风险
    LEVEL_3 = "level_3"  # 三级/一般风险
    LEVEL_4 = "level_4"  # 四级/低风险


class ApprovalDecision(StrEnum):
    """审批决定枚举"""

    PENDING = "pending"  # 待审批
    APPROVED = "approved"  # 同意
    REJECTED = "rejected"  # 驳回


class ActionItemStatus(StrEnum):
    """行动项状态枚举"""

    PENDING = "pending"  # 待完成
    IN_PROGRESS = "in_progress"  # 进行中
    COMPLETED = "completed"  # 已完成


class PSSRResult(StrEnum):
    """PSSR检查结果枚举"""

    PASS = "pass"  # 通过
    FAIL = "fail"  # 不通过
    NA = "na"  # 不适用


class HazardType(StrEnum):
    """隐患类型枚举（人/物/环/管）"""

    UNSAFE_CONDITION = "unsafe_condition"  # 物的不安全状态
    UNSAFE_ACTION = "unsafe_action"  # 人的不安全行为
    MANAGEMENT_DEFECT = "management_defect"  # 管理缺陷
    ENVIRONMENTAL = "environmental"  # 环境因素


class HazardLevel(StrEnum):
    """隐患等级枚举（三级）"""

    GENERAL = "general"  # 一般隐患
    SERIOUS = "serious"  # 较大隐患
    MAJOR = "major"  # 重大隐患


class HazardCategory(StrEnum):
    """隐患类别枚举（13种）"""

    EQUIPMENT = "equipment"  # 设备设施
    HAZARDOUS_STORAGE = "hazardous_storage"  # 危化储存
    EMERGENCY_MGMT = "emergency_mgmt"  # 应急管理
    INSTRUMENT_ELECTRICAL = "instrument_electrical"  # 仪表+电气
    LIGHTNING_ANTISTATIC = "lightning_antistatic"  # 防雷防静电
    OCCUPATIONAL_HEALTH = "occupational_health"  # 职业健康+劳保防护
    VIOLATION_OPERATION = "violation_operation"  # 三违作业
    SIX_S = "six_s"  # 6S
    LABEL_SIGNAGE = "label_signage"  # 标签标识
    PROCESS_MGMT = "process_mgmt"  # 工艺管理
    CONTRACTOR_DEFECT = "contractor_defect"  # 承包商缺陷
    DOCUMENTATION = "documentation"  # 内页资料
    SPECIAL_OPERATION = "special_operation"  # 特殊作业


class AccidentType(StrEnum):
    """事故类型枚举"""

    INJURY = "injury"  # 工伤事故
    FIRE = "fire"  # 火灾
    EXPLOSION = "explosion"  # 爆炸
    LEAKAGE = "leakage"  # 泄漏
    EQUIPMENT = "equipment"  # 设备事故
    NEAR_MISS = "near_miss"  # 未遂事件
    ENVIRONMENTAL = "environmental"  # 环境事件
    OCCUPATIONAL_DISEASE = "occupational_disease"  # 职业病
    TRAFFIC = "traffic"  # 交通事故
    OTHER = "other"  # 其他


class AccidentLevel(StrEnum):
    """事故等级枚举"""

    GENERAL = "general"  # 一般事故
    SERIOUS = "serious"  # 较大事故
    MAJOR = "major"  # 重大事故
    CATASTROPHIC = "catastrophic"  # 特别重大事故


class AccidentStatus(StrEnum):
    """事故处理状态枚举"""

    REPORTED = "reported"  # 已报告
    INVESTIGATING = "investigating"  # 调查中
    INVESTIGATED = "investigated"  # 调查完成
    CAPA_IN_PROGRESS = "capa_in_progress"  # CAPA进行中
    CLOSED = "closed"  # 已关闭


class InjurySeverity(StrEnum):
    """伤害程度枚举"""

    DEATH = "death"  # 死亡
    SERIOUS_INJURY = "serious_injury"  # 重伤
    MINOR_INJURY = "minor_injury"  # 轻伤
    NO_INJURY = "no_injury"  # 无伤害


class ContractorStatus(StrEnum):
    """承包商状态枚举"""

    ACTIVE = "active"  # 活跃
    INACTIVE = "inactive"  # 停用
    BLACKLISTED = "blacklisted"  # 黑名单


class QualificationType(StrEnum):
    """承包资质类型枚举"""

    CONSTRUCTION = "construction"  # 建筑施工
    INSTALLATION = "installation"  # 设备安装
    MAINTENANCE = "maintenance"  # 检维修
    CLEANING = "cleaning"  # 保洁
    SECURITY = "security"  # 安保
    OTHER = "other"  # 其他


class QualificationLevel(StrEnum):
    """资质等级枚举"""

    GRADE_A = "grade_a"  # 甲级/一级
    GRADE_B = "grade_b"  # 乙级/二级
    GRADE_C = "grade_c"  # 丙级/三级


class ContractorTrainingStatus(StrEnum):
    """承包商培训状态枚举"""

    UNTRAINED = "untrained"  # 未培训
    IN_PROGRESS = "in_progress"  # 培训中
    PASSED = "passed"  # 已通过
    EXPIRED = "expired"  # 已过期


class WorkRecordStatus(StrEnum):
    """施工记录状态枚举"""

    IN_PROGRESS = "in_progress"  # 施工中
    COMPLETED = "completed"  # 已完成
    EVALUATED = "evaluated"  # 已评价


class TrainingType(StrEnum):
    """培训类型枚举"""

    INDUCTION = "induction"  # 入职培训
    ANNUAL = "annual"  # 年度培训
    SPECIAL = "special"  # 专项培训
    EMERGENCY = "emergency"  # 应急培训
    CONTRACTOR = "contractor"  # 承包商培训
    REFRESHER = "refresher"  # 复训


class TrainingLevel(StrEnum):
    """培训级别枚举"""

    COMPANY = "company"  # 公司级
    DEPT = "dept"  # 部门级
    TEAM = "team"  # 班组级


class CertificateStatus(StrEnum):
    """证书状态枚举"""

    VALID = "valid"  # 有效
    EXPIRING = "expiring"  # 即将到期
    EXPIRED = "expired"  # 已过期


class TrainingMode(StrEnum):
    """培训方式枚举"""

    ONLINE = "online"  # 线上
    OFFLINE = "offline"  # 线下
    BLENDED = "blended"  # 混合


class RevisionType(StrEnum):
    """操规修订类型枚举"""

    MANUAL = "manual"  # 人工修订
    AI = "ai"  # AI修订


class RevisionScope(StrEnum):
    """修订范围枚举"""

    PROCESS = "process"  # 工艺
    SAFETY_REQUIREMENT = "safety_requirement"  # 安全要求


class ReviewOpinion(StrEnum):
    """审核意见枚举"""

    PENDING = "pending"  # 待审核
    APPROVED = "approved"  # 已审核


class OperationType(StrEnum):
    """特殊作业类型枚举（GB 30871-2022 八大特殊作业）"""

    HOT_WORK = "hot_work"  # 动火作业
    CONFINED_SPACE = "confined_space"  # 受限空间作业
    BLIND_PLATE = "blind_plate"  # 盲板抽堵作业
    HEIGHT_WORK = "height_work"  # 高处作业
    LIFTING = "lifting"  # 吊装作业
    TEMPORARY_ELECTRICITY = "temporary_electricity"  # 临时用电作业
    EXCAVATION = "excavation"  # 动土作业
    ROAD_BREAKING = "road_breaking"  # 断路作业


class OperationLevel(StrEnum):
    """特殊作业级别枚举"""

    SPECIAL = "special"  # 特级
    GRADE1 = "grade1"  # 一级
    GRADE2 = "grade2"  # 二级
    NOT_APPLICABLE = "not_applicable"  # 不涉及


class PersonnelStatus(StrEnum):
    """人员资质状态枚举"""

    ACTIVE = "active"  # 有效
    EXPIRED = "expired"  # 已过期
    REVOKED = "revoked"  # 已撤销


class PermitStatus(StrEnum):
    """作业票状态枚举"""

    DRAFT = "draft"  # 草稿
    SUBMITTED = "submitted"  # 已提交
    APPROVED = "approved"  # 已审批
    REJECTED = "rejected"  # 已驳回
    IN_PROGRESS = "in_progress"  # 作业中
    COMPLETED = "completed"  # 已完工
    ARCHIVED = "archived"  # 已归档


class CompletionMethod(StrEnum):
    """完工方式枚举"""

    NORMAL = "normal"  # 正常完工
    EARLY_TERMINATION = "early_termination"  # 提前终止


class KnowledgeCategory(StrEnum):
    """安全知识库分类枚举"""

    LAWS_REGULATIONS = "laws_regulations"  # 法律法规
    STANDARDS = "standards"  # 标准规范
    MANAGEMENT_SYSTEMS = "management_systems"  # 管理制度
    ACCIDENT_CASES = "accident_cases"  # 事故案例
    EMERGENCY_PLANS = "emergency_plans"  # 应急预案
    SDS = "sds"  # 化学品安全技术说明书
    TRAINING_MATERIALS = "training_materials"  # 培训教材
    OTHER = "other"  # 其他


class DetectionType(StrEnum):
    """检测类型枚举"""

    REGULAR = "regular"  # 定期检测
    COMMISSIONED = "commissioned"  # 委托检测
    EVALUATION = "evaluation"  # 评价检测
    ACCIDENT = "accident"  # 事故调查检测


class HazardFactorCategory(StrEnum):
    """危害因素类别枚举"""

    DUST = "dust"  # 粉尘（总尘/呼尘）
    CHEMICAL = "chemical"  # 化学物质（有机溶剂、有毒气体、重金属）
    PHYSICAL = "physical"  # 物理因素（噪声、高温、振动、辐射、照度）


class OELComplianceStatus(StrEnum):
    """OEL合规状态枚举"""

    COMPLIANT = "compliant"  # 符合
    EXCEEDING = "exceeding"  # 超标
    MARGINAL = "marginal"  # 临界（接近限值）


class MonitorStatus(StrEnum):
    """监测状态枚举"""

    DRAFT = "draft"  # 草稿
    IN_PROGRESS = "in_progress"  # 检测中
    COMPLETED = "completed"  # 已完成
    VERIFIED = "verified"  # 已验证


class ExamType(StrEnum):
    """体检类型枚举"""

    PRE_EMPLOYMENT = "pre_employment"  # 上岗前
    PERIODIC = "periodic"  # 在岗期间
    POST_EMPLOYMENT = "post_employment"  # 离岗时
    EMERGENCY = "emergency"  # 应急/事故后


class ExamConclusion(StrEnum):
    """体检结论枚举"""

    NORMAL = "normal"  # 未见异常
    ABNORMAL_OTHER = "abnormal_other"  # 其他异常（非职业病）
    SUSPECTED_OD = "suspected_od"  # 疑似职业病
    OD_DIAGNOSED = "od_diagnosed"  # 职业病确诊
    CONTRAINDICATED = "contraindicated"  # 职业禁忌证
    RE_EXAMINATION = "re_examination"  # 复查


class ExamStatus(StrEnum):
    """体检状态枚举"""

    SCHEDULED = "scheduled"  # 已安排
    IN_PROGRESS = "in_progress"  # 体检中
    COMPLETED = "completed"  # 已完成
    ARCHIVED = "archived"  # 已归档


class AbnormalityStatus(StrEnum):
    """异常处置状态枚举"""

    OPEN = "open"  # 待处理
    INVESTIGATING = "investigating"  # 调查中
    CORRECTED = "corrected"  # 已纠正
    CLOSED = "closed"  # 已关闭


class RegulationStatus(StrEnum):
    """操规标准化生成状态"""

    DRAFT = "draft"  # 初始状态
    GENERATED = "generated"  # 已生成标准化 Markdown
    REVIEWED = "reviewed"  # 人工编辑审核完成
    EXPORTED = "exported"  # 已导出 PDF


class ReportStatus(StrEnum):
    """报备状态枚举"""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


# ==================== 安全检查 ====================


class SafetyCheck(BaseModel):
    """安全检查表"""

    __tablename__ = "safety_checks"
    __table_args__ = (
        Index(
            "uq_safety_checks_check_no",
            "check_no",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "safety"},
    )

    check_no: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="检查编号"
    )
    check_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="daily",
        server_default="daily",
        comment="检查类型",
    )
    check_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="检查日期"
    )
    department: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="检查部门"
    )
    inspector: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity.users.id"),
        nullable=True,
        comment="检查人",
    )
    inspector_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="检查人姓名"
    )
    location: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="检查地点"
    )
    findings: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="检查发现"
    )
    result: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="检查结果: qualified/unqualified/need_rectification",
    )
    rectification_required: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否需要整改"
    )
    rectification_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="整改期限"
    )
    rectification_status: Mapped[str | None] = mapped_column(
        String(32), default="pending", nullable=True, comment="整改进度"
    )
    inspector_confirmed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", comment="检查人员确认"
    )
    safety_officer_confirmed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", comment="安全办确认"
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="draft",
        server_default="draft",
        nullable=False,
        comment="状态",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")

    # 关系
    hazards: Mapped[list["HazardReport"]] = relationship(
        "HazardReport", back_populates="safety_check", lazy="selectin"
    )


# ==================== 隐患排查 ====================


class HazardReport(BaseModel):
    """隐患报告表"""

    __tablename__ = "hazard_reports"
    __table_args__ = (
        Index(
            "uq_hazard_reports_hazard_no",
            "hazard_no",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "safety"},
    )

    hazard_no: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="隐患编号"
    )
    inspection_category: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="检查类别（Bitable 多选，逗号分隔，如「月度安全检查, 周检」）",
    )
    hazard_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="隐患分类（AI）：人的不安全行为/物的不安全状态/环境的不安全因素/管理的缺陷",
    )
    hazard_level: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="general",
        comment="隐患等级（AI）：一般隐患/较大隐患/重大隐患",
    )
    hazard_category: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="隐患类别（AI）：设备设施/危化储存/仪表+电气/…（13种）",
    )
    description: Mapped[str] = mapped_column(Text, nullable=False, comment="隐患描述")
    discovered_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity.users.id"),
        nullable=True,
        comment="发现人",
    )
    discovered_by_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="检查人员姓名"
    )
    inspector_department: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="检查人员部门（Bitable 多选，逗号分隔，如「EHS部, 生产部」）",
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=None, nullable=False, comment="检查日期"
    )
    department: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="责任部门"
    )
    major_hazard_basis: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="隐患判定依据（AI）"
    )
    key_defect: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="隐患描述（AI）"
    )
    defect_photos: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="缺陷图片JSON数组"
    )
    rectification_responsible_person: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity.users.id"),
        nullable=True,
        comment="整改责任人（FK → identity.users）",
    )
    rectification_responsible_person_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="整改责任人姓名（Bitable「责任人」）"
    )
    corrective_preventive_measures: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="AI整改建议"
    )
    rectification_reply: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="整改回复内容"
    )
    deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="整改期限"
    )
    actual_completion_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="整改完成时间"
    )
    rectification_photos: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="整改后图片JSON数组"
    )
    rectification_status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        server_default="pending",
        nullable=False,
        comment="整改进度",
    )
    # ── 三级复核 ──
    verify_level_1_status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        server_default="pending",
        nullable=False,
        comment=(
            "部门负责人复核状态 (Bitable「部门负责人复核」): "
            "pending/approved/rejected"
        ),
    )
    verify_level_2_status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        server_default="pending",
        nullable=False,
        comment="分管领导复核状态 (Bitable「分管领导复核」): pending/approved/rejected",
    )
    verify_level_3_status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        server_default="pending",
        nullable=False,
        comment="检查人员复核状态 (Bitable「检查人员复核」): pending/approved/rejected",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="open",
        server_default="open",
        nullable=False,
        comment="状态",
    )
    check_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("safety.safety_checks.id"),
        nullable=True,
        comment="关联检查ID",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")

    # ── AI 流程状态 ──
    ai_node_progress: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending_input",
        server_default="pending_input",
        comment="AI流程节点进度(pending_input/pending_script1/review_script1/pending_script2/review_script2/completed)",
    )
    overall_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        server_default="draft",
        comment="整体状态(draft/ai_processing/completed/cancelled)",
    )
    ai_error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="AI 脚本执行错误信息"
    )
    script1_review_status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        server_default="pending",
        comment="AI隐患识别审核状态(pending/approved/rejected)",
    )
    script2_review_status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        server_default="pending",
        comment="AI整改建议审核状态(pending/approved/rejected)",
    )
    ai_generated: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        comment="是否AI生成",
    )
    feishu_record_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="飞书多维表格记录 ID，双向同步关联"
    )
    ledger_record_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="公司隐患总台账（隐患随手拍页）飞书记录 ID，汇总写入锚点",
    )

    # 关系
    safety_check: Mapped["SafetyCheck | None"] = relationship(
        "SafetyCheck", back_populates="hazards"
    )


# ==================== 事故管理 ====================


class Accident(BaseModel):
    """事故登记表"""

    __tablename__ = "accidents"
    __table_args__ = (
        Index(
            "uq_accidents_accident_no",
            "accident_no",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "safety"},
    )

    accident_no: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="事故编号"
    )
    accident_type: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="事故类型"
    )
    accident_level: Mapped[str] = mapped_column(
        String(32), nullable=False, default="general", comment="事故等级"
    )
    happened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="发生时间"
    )
    location: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="发生地点"
    )
    department: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="发生部门"
    )
    description: Mapped[str] = mapped_column(Text, nullable=False, comment="事故描述")
    casualties: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="伤亡情况汇总"
    )
    property_damage: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="财产损失(元)"
    )
    loss_work_days: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="损失工作日"
    )
    # ── 伤员详情 ──
    injury_details: Mapped[list[Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment=(
            '伤员详情 JSON [{"name","position","injury_part","severity",'
            '"hospital"}]'
        ),
    )
    # ── 调查信息 ──
    investigation_team: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, comment='调查组 JSON [{"name","role"}]'
    )
    investigation_method: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="调查方法: 5-Why/FTA/Event Tree/BowTie等"
    )
    investigation_findings: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="调查发现"
    )
    investigation_report_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="调查报告文件路径"
    )
    direct_cause: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="直接原因"
    )
    root_cause: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="根本原因"
    )
    handling_measures: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="处理措施"
    )
    corrective_actions: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="纠正预防措施"
    )
    # ── CAPA 跟踪 ──
    corrective_action_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="CAPA截止日期"
    )
    corrective_action_responsible: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="CAPA责任人"
    )
    corrective_action_status: Mapped[str | None] = mapped_column(
        String(32),
        default="pending",
        nullable=True,
        comment="CAPA状态: pending/in_progress/completed/verified",
    )
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity.users.id"),
        nullable=True,
        comment="CAPA验证人",
    )
    verified_by_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="验证人姓名"
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="验证时间"
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="reported",
        server_default="reported",
        nullable=False,
        comment="状态: reported/investigating/investigated/capa_in_progress/closed",
    )
    reported_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity.users.id"),
        nullable=True,
        comment="报告人",
    )
    reported_by_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="报告人姓名"
    )
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="报告时间"
    )
    investigator: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity.users.id"),
        nullable=True,
        comment="调查人",
    )
    investigator_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="调查人姓名"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


# ==================== 安全培训 ====================


class SafetyTraining(BaseModel):
    """安全培训表"""

    __tablename__ = "safety_trainings"
    __table_args__ = (
        Index(
            "uq_safety_trainings_training_no",
            "training_no",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "safety"},
    )

    training_no: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="培训编号"
    )
    training_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="培训名称"
    )
    training_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="annual", comment="培训类型"
    )
    training_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="offline", comment="培训方式"
    )
    training_level: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="dept",
        server_default="dept",
        comment="培训级别: company/dept/team",
    )
    trainer: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity.users.id"),
        nullable=True,
        comment="培训讲师",
    )
    trainer_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="讲师姓名"
    )
    training_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="培训日期"
    )
    duration_hours: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="培训时长(小时)"
    )
    location: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="培训地点"
    )
    content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="培训内容")
    department: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="培训部门"
    )
    exam_passing_score: Mapped[float | None] = mapped_column(
        Float, default=60, server_default="60", nullable=True, comment="及格分数线"
    )
    course_material_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="课程资料路径"
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="draft",
        server_default="draft",
        nullable=False,
        comment="状态",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")

    # 关系
    records: Mapped[list["TrainingRecord"]] = relationship(
        "TrainingRecord", back_populates="training", lazy="selectin"
    )


class TrainingRecord(BaseModel):
    """培训记录（签到/考核）子表"""

    __tablename__ = "training_records"
    __table_args__ = {"schema": "safety"}

    training_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("safety.safety_trainings.id"),
        nullable=False,
        comment="培训ID",
    )
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity.users.id"),
        nullable=True,
        comment="员工ID",
    )
    employee_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="员工姓名"
    )
    department: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="部门"
    )
    position: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="岗位"
    )
    attendance: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否出席")
    score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="考核成绩"
    )
    passed: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, comment="是否合格"
    )
    certificate_no: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="证书编号"
    )
    certificate_expiry: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="证书有效期至"
    )
    certificate_status: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="证书状态: valid/expiring/expired"
    )
    certificate_file_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="证书文件路径"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")

    # 关系
    training: Mapped["SafetyTraining"] = relationship(
        "SafetyTraining", back_populates="records"
    )


# ==================== 危险源辨识 ====================


class HazardIdentification(BaseModel):
    """危险源辨识与评价表"""

    __tablename__ = "hazard_identifications"
    __table_args__ = (
        Index(
            "uq_hazard_identifications_no",
            "hazard_id_no",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "safety"},
    )

    # ── 基础信息（人工输入） ──
    hazard_id_no: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="危险源编号"
    )
    department: Mapped[str] = mapped_column(String(100), nullable=False, comment="部门")
    position: Mapped[str] = mapped_column(String(100), nullable=False, comment="岗位")
    production_step: Mapped[str] = mapped_column(
        Text, nullable=False, comment="生产步骤"
    )
    attachment_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="岗位资料附件路径"
    )
    attachment_original_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="附件原始文件名"
    )

    # ── 脚本1 输出：附件解析（AI → 人工审核） ──
    specific_activity: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="具体作业活动"
    )
    equipment_facilities: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="设备设施"
    )
    raw_auxiliary_materials: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="原辅料"
    )
    operation_frequency: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="作业频次"
    )
    operator_count: Mapped[int | None] = mapped_column(
        nullable=True, comment="操作人数"
    )

    # ── 脚本2 输出：AI危险源辨识（AI → 人工审核） ──
    hazard_type: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="危险类型（人机料法环）"
    )
    possible_accident: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="可能导致事故"
    )
    unsafe_behavior: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="不规范作业行为表现"
    )

    # ── 脚本3 输出：固有风险 LEC（AI → 人工审核） ──
    l_inherent: Mapped[float | None] = mapped_column(
        nullable=True, comment="可能性L（固有）"
    )
    e_inherent: Mapped[float | None] = mapped_column(
        nullable=True, comment="暴露频率E（固有）"
    )
    c_inherent: Mapped[float | None] = mapped_column(
        nullable=True, comment="严重性C（固有）"
    )
    d_inherent: Mapped[float | None] = mapped_column(
        nullable=True, comment="风险值D（固有）"
    )
    inherent_risk_level: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="固有风险等级"
    )
    inherent_risk_label: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="固有风险等级中文名"
    )

    # ── 脚本4 输出：现有控制措施（AI → 人工审核） ──
    existing_engineering_controls: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="现有工程控制措施"
    )
    existing_management_controls: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="现有管理控制措施"
    )
    existing_ppe: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="现有个人防护措施"
    )
    existing_emergency_measures: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="现有应急措施"
    )

    # ── 脚本5 输出：残余风险（AI → 人工审核） ──
    l_residual: Mapped[float | None] = mapped_column(
        nullable=True, comment="可能性L（残余）"
    )
    e_residual: Mapped[float | None] = mapped_column(
        nullable=True, comment="暴露频率E（残余）"
    )
    c_residual: Mapped[float | None] = mapped_column(
        nullable=True, comment="严重性C（残余）"
    )
    d_residual: Mapped[float | None] = mapped_column(
        nullable=True, comment="风险值D（残余）"
    )
    residual_risk_level: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="残余风险等级"
    )
    residual_risk_label: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="残余风险等级中文名"
    )

    # ── 脚本6 输出：建议措施（AI → 人工审核） ──
    needs_recommendation: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="是否需提出建议措施（是/否/待人工确认）"
    )
    recommendation_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="建议措施类型"
    )
    recommendation_content: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="建议措施内容"
    )
    recommendation_priority: Mapped[str | None] = mapped_column(
        String(10), nullable=True, comment="建议措施优先级（高/中/低）"
    )

    # ── 脚本7 输出：建议措施后风险（AI → 人工审核） ──
    l_post: Mapped[float | None] = mapped_column(
        nullable=True, comment="可能性L（建议措施后）"
    )
    e_post: Mapped[float | None] = mapped_column(
        nullable=True, comment="暴露频率E（建议措施后）"
    )
    c_post: Mapped[float | None] = mapped_column(
        nullable=True, comment="严重性C（建议措施后）"
    )
    d_post: Mapped[float | None] = mapped_column(
        nullable=True, comment="风险值D（建议措施后）"
    )
    post_risk_level: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="建议措施后风险等级"
    )
    post_risk_label: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="建议措施后风险等级中文名"
    )

    # ── 管控层级（根据风险等级自动填充） ──
    control_level: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="管控层级（公司级/部门级/班组级）"
    )
    responsible_person: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="责任人"
    )

    # ── 车间台账专用字段（对齐车间 Excel 表头） ──
    tense: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="时态（过去/现在/将来）"
    )
    state: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="状态（正常/异常/紧急）"
    )
    responsible_unit: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="责任单位"
    )
    check_frequency: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="检查频次"
    )
    check_standard: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="检查标准（设备设施清单）"
    )
    is_major_hazard: Mapped[str | None] = mapped_column(
        String(10), nullable=True, comment="是否重要危险源（是/否）"
    )

    # ── AI 流程状态 ──
    ai_node_progress: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending_input",
        server_default="pending_input",
        comment="AI流程节点进度",
    )
    ai_error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="AI 脚本执行错误信息"
    )
    overall_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        server_default="draft",
        comment="整体状态（draft/in_progress/completed/cancelled）",
    )

    # ── 各脚本人工审核状态 ──
    script1_review_status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", comment="脚本1审核状态"
    )
    script2_review_status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", comment="脚本2审核状态"
    )
    script3_review_status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", comment="脚本3审核状态"
    )
    script4_review_status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", comment="脚本4审核状态"
    )
    script5_review_status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", comment="脚本5审核状态"
    )
    script6_review_status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", comment="脚本6审核状态"
    )
    script7_review_status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", comment="脚本7审核状态"
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


# ==================== 安全操作规程 ====================


class OperationRegulation(BaseModel):
    """安全操作规程表 - 操规文档管理主表"""

    __tablename__ = "operation_regulations"
    __table_args__ = (
        Index(
            "uq_operation_regulations_no",
            "regulation_no",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "safety"},
    )

    regulation_no: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="操规编号（可为空，由文控/车间编号时填写）"
    )
    regulation_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="操规名称"
    )
    document_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="操规文档路径（当前最新版本）"
    )
    document_original_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="文档原始文件名"
    )
    position: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="岗位（达托/达巴，逗号分隔）"
    )
    workshop: Mapped[str | None] = mapped_column(
        String(60),
        nullable=True,
        server_default="",
        comment="车间/部门（如 103车间、201二车间、动力部）",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")

    # ── 标准化生成字段 ──
    content: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="标准化 Markdown 内容（9 章完整操规）"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=RegulationStatus.DRAFT.value,
        server_default="draft",
        nullable=False,
        comment="操规状态: draft/generated/reviewed/exported",
    )
    source_document_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="原始上传的旧版操规文件路径"
    )

    # 关系
    revisions: Mapped[list["RegulationRevision"]] = relationship(
        "RegulationRevision", back_populates="regulation", lazy="selectin"
    )


# ==================== 操规修订记录 ====================


class RegulationRevision(BaseModel):
    """修订记录表 - 修订流程记录"""

    __tablename__ = "regulation_revisions"
    __table_args__ = (
        Index(
            "uq_regulation_revisions_no",
            "revision_no",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "safety"},
    )

    revision_no: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="修订编号"
    )
    regulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("safety.operation_regulations.id"),
        nullable=False,
        comment="关联操规ID",
    )
    regulation_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="安全操规名称"
    )
    old_document_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="旧文档路径"
    )
    reviser: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity.users.id"),
        nullable=True,
        comment="修订人",
    )
    reviser_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="修订人姓名"
    )
    revision_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="修订时间"
    )
    revision_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="manual",
        server_default="manual",
        comment="修订类型: manual/ai",
    )
    revision_opinion: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="修订意见/内容"
    )
    revision_scope: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="修订范围（逗号分隔: process/safety_requirement）",
    )
    review_opinion: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        server_default="pending",
        nullable=False,
        comment="审核意见: pending/approved",
    )
    new_document_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="新文档路径"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")

    # 关系
    regulation: Mapped["OperationRegulation"] = relationship(
        "OperationRegulation", back_populates="revisions"
    )


# ==================== 操规合规审核 ====================


class RegulationReview(BaseModel):
    """操规合规审核记录 —— 按安全法规要求对安全操作规程做 AI 合规审核。

    审核依据为内置法规基线（安全生产法、危化品管理条例、GB 30871 特殊作业、
    个体防护与应急管理等要求拆解为审核要点），审核结论与明细供车间整改参考；
    AI 结论仅作辅助分析，整改与放行仍由人工确认。
    """

    __tablename__ = "regulation_reviews"
    __table_args__ = (
        Index(
            "ix_safety_regulation_reviews_regulation",
            "regulation_id",
            "is_deleted",
        ),
        {"schema": "safety"},
    )

    regulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("safety.operation_regulations.id"),
        nullable=False,
        comment="关联操规ID",
    )
    regulation_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="操规名称（冗余，便于追溯）"
    )
    result: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="fail",
        server_default="fail",
        comment="审核结论: pass/conditional_pass/fail",
    )
    score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="合规评分（0-100）",
    )
    summary: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default="", comment="总体评价"
    )
    missing_items: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="缺失项 [{item, requirement, basis, severity, suggestion}]",
    )
    non_compliant_items: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="不合规项 [{item, requirement, basis, severity, suggestion}]",
    )
    suggestions: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, comment="改进建议列表"
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity.users.id"),
        nullable=True,
        comment="发起审核的用户",
    )


# ==================== AI 工作流配置 ==================


class AIWorkflowConfig(BaseModel):
    """AI 工作流配置 —— 每个安全模块可配置独立的 AI 工作流"""

    __tablename__ = "ai_workflow_configs"
    __table_args__ = (
        Index(
            "uq_ai_workflow_config_module_code",
            "module_code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "safety", "comment": "AI 工作流配置表"},
    )

    module_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="模块代码（hazard-identification / regulation / hazard 等）",
    )
    workflow_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="工作流名称"
    )
    workflow_description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="工作流描述"
    )
    trigger_event: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="触发事件（submit / revision_created 等）"
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False, comment="是否启用"
    )
    script_configs: Mapped[list[Any] | dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="脚本配置 JSON 数组"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False, comment="排序顺序"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


# ==================== 特殊作业人员资质 ====================


class SpecialOperationPersonnel(BaseModel):
    """特殊作业人员资质表"""

    __tablename__ = "special_operation_personnel"
    __table_args__ = (
        Index(
            "uq_special_op_personnel_no",
            "personnel_no",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "safety"},
    )

    personnel_no: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="人员编号"
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="姓名")
    department: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="所属部门"
    )
    certificate_type: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="证书类型（对应8种特殊作业）"
    )
    certificate_number: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="证书编号"
    )
    issuing_authority: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="发证机关"
    )
    issue_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="发证日期"
    )
    expiry_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="有效期至"
    )
    certificate_file_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="证书文件路径"
    )
    qualification_scope: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="资质范围"
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="active",
        server_default="active",
        nullable=False,
        comment="状态: active/expired/revoked",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


# ==================== 特殊作业票 ====================


class SpecialOperationPermit(BaseModel):
    """特殊作业票表"""

    __tablename__ = "special_operation_permits"
    __table_args__ = (
        Index(
            "uq_special_op_permits_permit_no",
            "permit_no",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "safety"},
    )

    permit_no: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="作业票编号"
    )
    operation_type: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="作业类型（8种）"
    )
    operation_level: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="grade2",
        server_default="grade2",
        comment="作业级别: special/grade1/grade2",
    )
    location: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="作业地点"
    )
    equipment_tag: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="设备位号"
    )
    work_description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="作业内容描述"
    )
    planned_start_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="计划开始时间"
    )
    planned_end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="计划结束时间"
    )
    actual_start_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="实际开始时间"
    )
    actual_end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="实际结束时间"
    )
    applicant_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="申请人姓名"
    )
    work_leader_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="作业负责人姓名"
    )
    operator_names: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="作业人员姓名（逗号分隔）"
    )
    guardian_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="监护人姓名"
    )
    approver_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="审批人姓名"
    )
    safety_measures: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="安全措施"
    )
    emergency_equipment: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="应急消防器材"
    )
    gas_analysis: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="气体分析结果"
    )
    risk_assessment: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="风险评估"
    )
    safety_briefing_confirmed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", comment="安全交底确认"
    )
    safety_briefing_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="安全交底时间"
    )
    rejection_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="驳回原因"
    )
    completion_method: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="完工方式: normal/early_termination"
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="draft",
        server_default="draft",
        nullable=False,
        comment="状态",
    )
    check_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("safety.safety_checks.id"),
        nullable=True,
        comment="关联安全检查ID",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


# ==================== 安全知识库 ====================


class SafetyKnowledgeArticle(BaseModel):
    """安全知识库文章表（含 EHS 法规库多维表格镜像字段）"""

    __tablename__ = "knowledge_articles"
    __table_args__ = (
        Index(
            "uq_knowledge_articles_feishu_record_active",
            "feishu_record_id",
            unique=True,
            postgresql_where=text(
                "is_deleted = false AND feishu_record_id IS NOT NULL"
            ),
        ),
        {"schema": "safety"},
    )

    title: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="文章标题"
    )
    article_no: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="法规编号"
    )
    regulation_category: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="法规类别（飞书原始值）"
    )
    source: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="颁布机关"
    )
    promulgation_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="颁布修订日期"
    )
    implement_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="实施日期"
    )
    regulation_status: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="法规状态（如 现行有效）"
    )
    regulation_link: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="法规链接"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="摘要")
    content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="正文内容")
    tags: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="标签（逗号分隔）"
    )
    category: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="other",
        server_default="other",
        comment="分类",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="draft",
        server_default="draft",
        nullable=False,
        comment="状态: draft/published/archived",
    )
    view_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False, comment="浏览次数"
    )
    attachment_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="附件路径"
    )
    attachment_original_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="附件原始文件名"
    )
    feishu_record_id: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="飞书多维表格 record_id（镜像唯一键）"
    )
    feishu_attachments: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="飞书附件快照 [{file_token,name,size}]",
    )
    local_attachments: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="本地附件快照 [{token,name,size}]（镜像行附件在飞书维护）",
    )
    source_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="feishu",
        server_default="feishu",
        comment="来源: feishu=飞书镜像 / manual=本地录入 / ai_radar=AI雷达发现",
    )
    standard_no: Mapped[str | None] = mapped_column(
        String(80), nullable=True, comment="标准号（如 GB 30871-2022，用于标准库检索）"
    )
    version_status: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="标准版本状态: current=现行 / obsolete=已废止 / revised=已修订",
    )
    version_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近版本核查时间"
    )
    ai_analysis: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="AI 分析结果（相关性评分/判定理由/分析时间）"
    )


# ==================== 风险作业报备 ====================


class SpecialOperationReport(BaseModel):
    """八大特殊作业报备表"""

    __tablename__ = "special_operation_reports"
    __table_args__ = (
        Index(
            "uq_special_operation_reports_no",
            "report_no",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "safety"},
    )

    report_no: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="报备编号"
    )
    permit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("safety.special_operation_permits.id"),
        nullable=True,
        comment="关联作业票ID",
    )
    operation_type: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="作业类型（8种）"
    )
    operation_level: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="grade2",
        server_default="grade2",
        comment="作业级别: special/grade1/grade2",
    )
    department: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="报备部门"
    )
    location: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="作业地点"
    )
    equipment_tag: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="设备位号"
    )
    work_description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="作业内容描述"
    )
    planned_start_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="计划开始时间"
    )
    planned_end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="计划结束时间"
    )
    work_leader_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="作业负责人姓名"
    )
    operator_names: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="作业人员姓名（逗号分隔）"
    )
    guardian_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="监护人姓名"
    )
    risk_level: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="风险等级: level_1/level_2/level_3/level_4"
    )
    safety_measures: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="安全措施"
    )
    emergency_equipment: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="应急消防器材"
    )
    gas_analysis: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="气体分析结果"
    )
    risk_assessment: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="风险评估描述"
    )
    applicant_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="报备申请人姓名"
    )
    approver_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="审批人姓名"
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="审批时间"
    )
    rejection_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="驳回原因"
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="draft",
        server_default="draft",
        nullable=False,
        comment="状态: draft/submitted/approved/rejected",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
    is_critical: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
        comment="是否关键作业（AI自动判定+可手动修改）",
    )
    is_critical_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="关键作业判定理由"
    )
    is_critical_updated_by: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="手动修改关键作业标记的操作人"
    )

    # 关系
    permit: Mapped["SpecialOperationPermit | None"] = relationship(
        "SpecialOperationPermit", foreign_keys=[permit_id]
    )


class DailyRiskReport(BaseModel):
    """每日风险作业报备表"""

    __tablename__ = "daily_risk_reports"
    __table_args__ = (
        Index(
            "uq_daily_risk_reports_no",
            "report_no",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "safety"},
    )

    report_no: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="报备编号"
    )
    report_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="报备作业日期"
    )
    report_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="regular",
        server_default="regular",
        comment="报备类型: regular(常规作业) / non_regular(非常规作业)",
    )
    department: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="报备部门"
    )
    hazard_identification_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("safety.hazard_identifications.id"),
        nullable=True,
        comment="关联危险源辨识ID",
    )
    operation_description: Mapped[str] = mapped_column(
        Text, nullable=False, comment="风险作业描述"
    )
    operation_steps: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="作业步骤"
    )
    hazard_factors: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="危险因素"
    )
    risk_level: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="风险等级: level_1/level_2/level_3/level_4"
    )
    control_measures: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="控制措施"
    )
    responsible_person: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="作业负责人"
    )
    operator_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="作业人数"
    )
    location: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="作业地点"
    )
    planned_start_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="计划开始时间"
    )
    planned_end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="计划结束时间"
    )
    applicant_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="报备申请人姓名"
    )
    approver_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="审批人姓名"
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="审批时间"
    )
    rejection_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="驳回原因"
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="draft",
        server_default="draft",
        nullable=False,
        comment="状态: draft/submitted/approved/rejected",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")

    # 关系
    hazard_identification: Mapped["HazardIdentification | None"] = relationship(
        "HazardIdentification", foreign_keys=[hazard_identification_id]
    )


# ==================== EHS变更管理 (MOC) ====================


class EhsChange(BaseModel):
    """EHS变更管理 / Management of Change（基于 T/CCSAS 007-2020）"""

    __tablename__ = "ehs_changes"
    __table_args__ = (
        Index(
            "uq_ehs_changes_change_no",
            "change_no",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "safety", "comment": "EHS变更管理表"},
    )

    # ── 核心标识 ──
    change_no: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="变更编号"
    )

    # ── 基础信息 ──
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="变更标题")
    change_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="变更类型: process_tech/equipment_facility/management",
    )
    change_grade: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="general",
        server_default="general",
        comment="变更等级: major/general",
    )
    change_duration: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="permanent",
        server_default="permanent",
        comment="变更期限: permanent/temporary/emergency",
    )
    department: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="申请部门"
    )
    location_unit: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="所在单元/装置"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="变更描述（变更前/变更后对比）"
    )
    technical_basis: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="变更技术依据"
    )
    expected_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="预期开始日期"
    )
    expected_completion: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="预期完成日期"
    )
    actual_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="实际开始日期"
    )
    actual_completion: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="实际完成日期"
    )
    expected_effect: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="预期效果"
    )

    # ── 状态与申请人 ──
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="draft",
        server_default="draft",
        comment="状态",
    )
    applicant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity.users.id"),
        nullable=True,
        comment="申请人ID",
    )
    applicant_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="申请人姓名"
    )

    # ── JSON 辅助字段 ──
    equipment_tags: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, comment="关联设备位号 JSON数组"
    )
    documents_to_update: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, comment="需更新的文件清单 JSON数组 [{name, number}]"
    )
    attachments: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, comment="附件列表 JSON数组 [{name, path}]"
    )

    # ── JSON 子记录 ──
    risk_assessments: Mapped[list[Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment=(
            "风险评估 JSON数组 [{method, severity, likelihood, risk_level, "
            "description, control_measures, assessed_by, assessed_date, participants}]"
        ),
    )
    approval_chain: Mapped[list[Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment=(
            "审批链 JSON数组 [{level, approver_role, approver, decision, "
            "comments, decided_at}]"
        ),
    )
    action_items: Mapped[list[Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="行动项 JSON数组 [{task, owner, due_date, status, completed_at}]",
    )
    pssr_checklist: Mapped[list[Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="PSSR清单 JSON数组 [{item, result, checked_by, checked_at, remarks}]",
    )
    verification: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment=(
            "变更验证 {expected_effect_achieved, comments, psi_updated, "
            "documents_updated, accepted_by, accepted_date}"
        ),
    )
    closure: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="变更关闭 {closed_by, closed_date, temp_expiry_date, restored_date}",
    )

    # ── 关联 ──
    linked_safety_check_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("safety.safety_checks.id"),
        nullable=True,
        comment="关联安全检查ID（变更验收）",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")

    # ── 关系 ──
    applicant: Mapped["User | None"] = relationship(
        "app.platform.identity.models.User", foreign_keys=[applicant_id]
    )
    linked_safety_check: Mapped["SafetyCheck | None"] = relationship(
        "SafetyCheck", foreign_keys=[linked_safety_check_id]
    )


# ==================== 职业危害因素监测 ====================


class OhHazardMonitor(BaseModel):
    """职业危害因素监测 / Occupational Hazard Factor Monitoring。

    基于 GBZ 159, GBZ 2.1/2.2。
    """

    __tablename__ = "oh_hazard_monitors"
    __table_args__ = (
        Index(
            "uq_oh_hazard_monitors_monitor_no",
            "monitor_no",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "safety", "comment": "职业危害因素监测表"},
    )

    # ── 核心标识 ──
    monitor_no: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="监测编号"
    )

    # ── 监测点信息 ──
    workplace: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="监测场所/车间"
    )
    location: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="具体监测点位"
    )
    equipment_info: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="关联设备/岗位"
    )

    # ── 检测信息 ──
    detection_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="检测类型: regular/commissioned/evaluation/accident",
    )
    detection_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="检测日期"
    )
    detection_agency: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="检测机构"
    )

    # ── 状态 ──
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="draft",
        server_default="draft",
        comment="状态",
    )

    # ── 责任人 ──
    inspector_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="检测人员"
    )
    verifier_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="验证人员"
    )

    # ── JSON 子记录：检测结果数组 ──
    detection_results: Mapped[list[Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment=(
            "检测结果 JSON数组 [{factor_name, factor_category, detection_value, "
            "unit, oel_limit, compliance_status, sampling_method, standard_ref}]"
        ),
    )

    # ── JSON：异常处置记录 ──
    abnormality_records: Mapped[list[Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment=(
            "异常处置记录 [{abnormality_desc, corrective_action, responsible_person, "
            "deadline, status, completed_at, remarks}]"
        ),
    )

    # ── JSON：附件 ──
    attachments: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, comment="附件列表 JSON数组 [{name, path}]"
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


# ==================== 职业健康体检 ====================


class OhHealthExam(BaseModel):
    """职业健康体检管理 / Occupational Health Examination Management（基于 GBZ 188）"""

    __tablename__ = "oh_health_exams"
    __table_args__ = (
        Index(
            "uq_oh_health_exams_exam_no",
            "exam_no",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "safety", "comment": "职业健康体检表"},
    )

    # ── 核心标识 ──
    exam_no: Mapped[str] = mapped_column(String(64), nullable=False, comment="体检编号")

    # ── 人员信息 ──
    employee_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="员工姓名"
    )
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity.users.id"),
        nullable=True,
        comment="关联用户ID",
    )
    department: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="部门"
    )
    job_position: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="岗位"
    )

    # ── 体检类型与状态 ──
    exam_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="体检类型: pre_employment/periodic/post_employment/emergency",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="scheduled",
        server_default="scheduled",
        comment="状态",
    )

    # ── 体检信息 ──
    exam_agency: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="体检机构"
    )
    scheduled_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="计划体检日期"
    )
    exam_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="实际体检日期"
    )
    report_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="报告日期"
    )

    # ── 暴露因素关联 ──
    hazard_factors: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, comment="关联的危害因素列表 [string]"
    )

    # ── 个人体检结论 ──
    overall_conclusion: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="综合体检结论"
    )

    # ── JSON 子记录：体检项目结果 ──
    exam_items: Mapped[list[Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment=(
            "体检项目结果 JSON数组 [{item_name, category, result, reference_range, "
            "is_abnormal, remarks}]"
        ),
    )

    # ── JSON：异常处置记录 ──
    abnormality_records: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, comment="异常处置记录 JSON数组"
    )

    # ── JSON：附件 ──
    attachments: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, comment="附件列表"
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


# ==================== 承包商管理 ====================


class Contractor(BaseModel):
    """承包商管理表"""

    __tablename__ = "contractors"
    __table_args__ = (
        Index(
            "uq_contractors_contractor_no",
            "contractor_no",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "safety"},
    )

    contractor_no: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="承包商编号"
    )
    company_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="公司名称"
    )
    legal_representative: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="法定代表人"
    )
    contact_person: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="联系人"
    )
    contact_phone: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="联系电话"
    )
    business_scope: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="经营范围"
    )
    qualification_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="other",
        server_default="other",
        comment="资质类型",
    )
    qualification_level: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="资质等级: grade_a/grade_b/grade_c"
    )
    qualification_cert_no: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="资质证书编号"
    )
    qualification_expiry: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="资质有效期至"
    )
    safety_license_no: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="安全生产许可证编号"
    )
    safety_license_expiry: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="安全生产许可证有效期"
    )
    insurance_info: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="保险信息"
    )
    insurance_expiry: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="保险有效期至"
    )
    safety_officer_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="安全负责人"
    )
    safety_officer_phone: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="安全负责人电话"
    )
    special_op_personnel: Mapped[list[Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment='特种作业人员列表 [{"name","cert_type","cert_no","expiry"}]',
    )
    training_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="untrained",
        server_default="untrained",
        comment="培训状态: untrained/in_progress/passed/expired",
    )
    training_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近培训日期"
    )
    safety_performance_score: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="安全绩效评分（0-100）"
    )
    blacklisted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
        comment="是否黑名单",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        server_default="active",
        comment="状态: active/inactive/blacklisted",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")

    # 关系
    work_records: Mapped[list["ContractorWorkRecord"]] = relationship(
        "ContractorWorkRecord", back_populates="contractor", lazy="selectin"
    )


class ContractorWorkRecord(BaseModel):
    """施工记录表（承包商子表）"""

    __tablename__ = "contractor_work_records"
    __table_args__ = {"schema": "safety"}

    contractor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("safety.contractors.id"),
        nullable=False,
        comment="关联承包商ID",
    )
    work_content: Mapped[str] = mapped_column(Text, nullable=False, comment="施工内容")
    work_location: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="施工地点"
    )
    planned_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="计划开始时间"
    )
    planned_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="计划结束时间"
    )
    actual_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="实际开始时间"
    )
    actual_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="实际结束时间"
    )
    permit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("safety.special_operation_permits.id"),
        nullable=True,
        comment="关联特殊作业票ID",
    )
    leading_person: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="带班负责人"
    )
    worker_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="施工人数"
    )
    safety_briefing_done: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", comment="安全交底确认"
    )
    violations: Mapped[list[Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment='违章记录 [{"date","description","severity","handler","result"}]',
    )
    evaluation: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment='评价 {"score","comments","evaluator","date"}'
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="in_progress",
        server_default="in_progress",
        comment="状态: in_progress/completed/evaluated",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")

    # 关系
    contractor: Mapped["Contractor"] = relationship(
        "Contractor", back_populates="work_records"
    )
    permit: Mapped["SpecialOperationPermit | None"] = relationship(
        "SpecialOperationPermit", foreign_keys=[permit_id]
    )


# ==================== 定时任务（Scheduled Task） ====================


class ScheduledTask(BaseModel):
    """定时任务配置 — 按 cron 表达式聚合安全数据，推送到飞书群聊"""

    __tablename__ = "scheduled_tasks"
    __table_args__ = (
        Index(
            "uq_scheduled_tasks_name",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "safety"},
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="任务名称")
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="任务描述"
    )
    cron_expression: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Cron 表达式，如 0 9 * * *"
    )
    cron_desc: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="Cron 可读描述，如「每天上午9点」"
    )
    feishu_chat_id: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="目标飞书群聊 chat_id"
    )
    feishu_chat_name: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="飞书群聊名称快照"
    )
    header_color: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="blue",
        server_default="blue",
        comment="卡片头部颜色: blue/orange/green/red/purple",
    )
    data_sources: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, default=list, comment="数据来源配置"
    )
    card_template: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="消息卡片 Markdown 模板"
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true", comment="是否启用"
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="上次执行时间"
    )
    last_run_status: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="上次执行状态: success/failure"
    )
    last_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="上次错误信息"
    )
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="下次执行时间"
    )


class ScheduledTaskLog(BaseModel):
    """定时任务执行日志"""

    __tablename__ = "scheduled_task_logs"
    __table_args__ = ({"schema": "safety"},)

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, comment="关联 scheduled_tasks.id"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="开始执行时间"
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="完成时间"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="running",
        server_default="running",
        comment="执行状态: running/success/failure",
    )
    data_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="聚合数据快照"
    )
    card_content: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="发送的卡片 JSON 内容"
    )
    feishu_msg_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="飞书返回的消息 ID"
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="错误信息"
    )
    duration_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="执行耗时（毫秒）"
    )


class ApiCallConfig(BaseModel):
    """API调用配置表"""

    __tablename__ = "api_call_configs"
    __table_args__ = {"schema": "safety"}

    config_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="配置名称"
    )
    api_base_url: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="API基础URL"
    )
    api_key: Mapped[str] = mapped_column(String(500), nullable=False, comment="API密钥")
    model_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="模型名称"
    )
    temperature: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0.1", comment="温度参数"
    )
    timeout_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="120", comment="超时秒数"
    )
    max_tokens: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="最大Token数"
    )
    extra_config: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="额外配置JSON"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", comment="是否激活"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


class HazardRevisionArchive(BaseModel):
    """危害修订归档表"""

    __tablename__ = "hazard_revision_archives"
    __table_args__ = {"schema": "safety"}

    regulation_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="法规名称"
    )
    hazard_document_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="危害文档路径"
    )
    hazard_document_original_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="危害文档原始名称"
    )
    identification_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="识别日期"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="active", comment="状态"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


class HazardRevisionRecord(BaseModel):
    """危害修订记录表"""

    __tablename__ = "hazard_revision_records"
    __table_args__ = {"schema": "safety"}

    hazard_revision_no: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="危害修订编号"
    )
    regulation_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="法规修订ID"
    )
    regulation_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="法规名称"
    )
    identifier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="识别器ID"
    )
    identifier_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="识别器名称"
    )
    identification_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="识别时间"
    )
    identification_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="auto_trigger", comment="识别类型"
    )
    process_change_content: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="工艺变更内容"
    )
    identification_scope: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="识别范围"
    )
    review_opinion: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="pending", comment="审查意见"
    )
    hazard_document_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="危害文档路径"
    )
    hazard_document_original_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="危害文档原始名称"
    )
    linked_hazard_archive_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="关联的危害归档ID"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


class SafetyFeishuAppSettings(BaseModel):
    """安全模块飞书应用配置（单一事实源存数据库，Web 设置页维护）。

    app_secret 使用 app.core.llm.encryption 加密存储；回显仅返回掩码。
    """

    __tablename__ = "feishu_app_settings"
    __table_args__ = {"schema": "safety"}

    app_id: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="飞书应用 App ID"
    )
    app_secret: Mapped[str] = mapped_column(
        Text, nullable=False, comment="飞书应用 App Secret（加密存储）"
    )
    bitable_app_token: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="隐患多维表格 app_token"
    )
    bitable_hazard_table_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="隐患多维表格 table_id"
    )
    knowledge_app_token: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="EHS 法规库多维表格 app_token"
    )
    knowledge_table_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="EHS 法规库多维表格 table_id"
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="是否启用安全模块飞书集成",
    )
    knowledge_last_sync_status: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="知识库最近同步状态: success/failed"
    )
    knowledge_last_sync_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="知识库最近同步错误信息"
    )
    knowledge_last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="知识库最近同步时间"
    )
    last_test_status: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="最近连接测试状态: success/failed"
    )
    last_test_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="最近连接测试错误信息"
    )
    last_tested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近连接测试时间"
    )
    radar_scan_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="是否启用法规雷达自动扫描（每周一 08:00）",
    )
    radar_notify_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="法规雷达扫描后是否推送飞书通知",
    )
    radar_notify_chat_ids: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, default=list, comment="通知群 chat_id 列表"
    )
    radar_notify_user_ids: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, default=list, comment="通知个人 open_id 列表"
    )
    hazard_due_notify_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="是否启用隐患到期提醒推送（每天检查，进入提醒节点才推送）",
    )
    hazard_due_notify_milestones: Mapped[list[Any] | None] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="提醒节点天数列表（如 [30,15,7]：到期前一个月/半个月/一周各提醒一次）",
    )
    hazard_due_notify_chat_ids: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, default=list, comment="到期提醒群 chat_id 列表"
    )
    hazard_due_notify_user_ids: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, default=list, comment="到期提醒个人 open_id 列表"
    )
    fire_expiry_notify_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="是否启用消防器材有效期到期提醒（每天检查，进入提醒节点才推送）",
    )
    fire_expiry_notify_milestones: Mapped[list[Any] | None] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="有效期提醒节点天数列表（如 [30,15,7]；0 = 已过期节点）",
    )
    fire_expiry_notify_chat_ids: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, default=list, comment="有效期提醒群 chat_id 列表"
    )
    fire_expiry_notify_user_ids: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, default=list, comment="有效期提醒个人 open_id 列表"
    )


class HazardDueNotificationLog(BaseModel):
    """到期提醒推送记录：每条隐患每个提醒节点只推一次（0 = 已逾期节点）。"""

    __tablename__ = "hazard_due_notification_log"
    __table_args__ = (
        UniqueConstraint(
            "table_id",
            "record_id",
            "milestone_days",
            name="uq_hazard_due_notify_once_per_milestone",
        ),
        {"schema": "safety"},
    )

    table_id: Mapped[str] = mapped_column(String(64), nullable=False)
    record_id: Mapped[str] = mapped_column(String(64), nullable=False)
    milestone_days: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="触发的提醒节点天数；0 表示已逾期节点"
    )
    notified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


# ==================== EHS 法规雷达 ====================


class RegulationRadarSite(BaseModel):
    """法规雷达来源站点（从表格链接派生 + 人工维护栏目地址）。"""

    __tablename__ = "regulation_radar_sites"
    __table_args__ = (
        Index(
            "uq_regulation_radar_sites_domain_active",
            "domain",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "safety"},
    )

    site_code: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="站点代码（如 mee_gzk）"
    )
    site_name: Mapped[str] = mapped_column(
        String(120), nullable=False, comment="站点名称（如 生态环境部·规章库）"
    )
    domain: Mapped[str] = mapped_column(
        String(120), nullable=False, comment="域名（从表格链接派生）"
    )
    channel: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="column",
        server_default="column",
        comment="通道类型: column=栏目页抓取 / standard_search=标准号检索",
    )
    list_url: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="栏目页地址（column 通道必填）"
    )
    parser: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="解析器标识（如 generic_list / openstd_gb）"
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true", comment="是否启用"
    )
    last_crawled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近抓取时间"
    )
    last_status: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="最近抓取状态: success/failed"
    )
    last_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="最近抓取错误信息"
    )
    last_item_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="最近抓取条目数"
    )


class RegulationRadarRun(BaseModel):
    """法规雷达扫描批次（页面提示与追溯的数据源）。"""

    __tablename__ = "regulation_radar_runs"
    __table_args__ = {"schema": "safety"}

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="开始时间"
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="结束时间"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="running",
        server_default="running",
        comment="状态: running/success/partial/failed",
    )
    trigger: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual", server_default="manual",
        comment="触发方式: manual=手动 / schedule=定时",
    )
    dry_run: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="是否干跑",
    )
    sites_total: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="参与站点数",
    )
    sites_failed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="抓取失败站点数",
    )
    found_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="抓取条目总数",
    )
    new_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="判定为新法规数",
    )
    revised_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="判定为已修订/已废止数",
    )
    link_fixed_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="修复链接数",
    )
    skipped_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="跳过数（不相关/重复）",
    )
    failed_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="处理失败数",
    )
    items: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True, default=list, comment="本批明细 [{action,name,url,...}]"
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="错误信息"
    )
    is_acknowledged: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="页面提示是否已确认",
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="确认时间"
    )
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="确认人"
    )


# ==================== 页面飞书多维表格镜像 ====================


class SafetyPageFeishuConfig(BaseModel):
    """页面 ↔ 飞书多维表格绑定（每个镜像页一行）。

    页面本身是代码（见 ``safety/page_tables.py`` 注册表），这里只存「这个页面
    绑定哪张飞书表」，由「安全管理 → 系统配置 → 飞书设置」页维护，不写死在
    代码里。使用安全模块飞书应用凭证读取，凭据仍在 ``feishu_app_settings``。
    """

    __tablename__ = "page_feishu_configs"
    __table_args__ = (
        Index(
            "uq_safety_page_feishu_configs_page_key",
            "page_key",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "safety"},
    )

    page_key: Mapped[str] = mapped_column(
        String(160), nullable=False, comment="页面标识（安全模块菜单页面 key）"
    )
    app_token: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="多维表格 app_token"
    )
    table_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="多维表格 table_id"
    )
    view_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="多维表格 view_id（仅记录，不做服务端视图过滤）",
    )
    hidden_field_names: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, default=list, comment="页面隐藏的字段名列表"
    )
    workshop_aliases: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
        comment="车间别名归一映射（{别名: 规范车间名}），供仪表盘按车间聚合使用",
    )
    sub_tables: Mapped[list[Any] | None] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment=(
            "附加子表页签 [{table_id, tab_name, hidden_field_names}]；"
            "主绑定（table_id 列）是第一个页签，本列表是其余页签"
        ),
    )
    writeback_table_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="点检记录回写子表 table_id（灭火器/消防栓点检页专用，同一 Base）",
    )
    over_limit_quantity_field: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        comment="超储计算-存量列字段名（危化品统计表页专用，空=不启用超储计算）",
    )
    over_limit_limit_field: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        comment="超储计算-上限列字段名（与存量列一起配置才生效）",
    )
    over_limit_name_field: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        comment="超储计算-品名列字段名（空=取表格第一个文本列）",
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="是否启用该页面的表格绑定",
    )
    last_test_status: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="最近绑定测试状态: success/failed"
    )
    last_test_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="最近绑定测试错误信息"
    )
    last_tested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近绑定测试时间"
    )
    last_test_field_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="最近绑定测试读到的字段数"
    )
    last_test_record_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="最近绑定测试读到的记录数"
    )
    is_mirrored: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="是否使用本地镜像数据源（关闭则实时拉取飞书）",
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近镜像同步完成时间"
    )
    last_sync_status: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="最近镜像同步状态: success/failed"
    )
    last_sync_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="最近镜像同步错误信息"
    )
    last_sync_record_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="最近镜像同步记录数"
    )


class SafetyPageTableMirrorRecord(BaseModel):
    """页面镜像记录（飞书多维表格 → 本地全量副本）。

    ``fields`` 存按当前飞书字段 schema 解码后的值（与页面 API 返回同构），
    同一时点重写；列结构仍实时来自飞书（Redis 缓存），镜像只存数据行。
    编辑写回飞书成功后单条写透更新本表。
    """

    __tablename__ = "page_table_mirror_records"
    __table_args__ = (
        Index(
            "uq_safety_page_table_mirror_records_page_table_record",
            "page_key",
            "table_id",
            "record_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "ix_safety_page_table_mirror_records_page",
            "page_key",
            "is_deleted",
        ),
        {"schema": "safety"},
    )

    page_key: Mapped[str] = mapped_column(
        String(160), nullable=False, comment="页面标识（对齐 page_feishu_configs）"
    )
    table_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="",
        server_default="",
        comment="所属飞书子表 table_id（多页签页面区分数据来源）",
    )
    record_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="飞书记录 record_id"
    )
    fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, comment="解码后的字段值（中文列名为键）"
    )
    search_text: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default="", comment="关键字搜索文本"
    )
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.now(UTC),
        server_default=text("now()"),
        comment="该行最近同步/写透时间",
    )


class WorkshopClassification(BaseModel):
    """AI 兜底车间分类缓存。

    车间/位置 的自由文本写法未命中别名和车间号规则时，由 LLM 按规范车间清单
    归类；结果按原始写法缓存（唯一），后续统计与下钻直接读缓存。别名映射
    （``workshop_aliases``）优先于本表。
    """

    __tablename__ = "workshop_classifications"
    __table_args__ = (
        Index(
            "uq_safety_workshop_classifications_raw_value",
            "raw_value",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "safety"},
    )

    raw_value: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="原始位置写法"
    )
    canonical: Mapped[str] = mapped_column(
        String(120), nullable=False, comment="归类后的规范车间/部门名"
    )
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ai",
        server_default="ai",
        comment="来源: ai=LLM 自动归类",
    )


# ==================== 灭火器 / 消防栓点检 ====================


class FireEquipment(BaseModel):
    """消防器材台账（「灭火器及消防栓点检」镜像页的结构化投影）。

    数据来源是飞书多维表格的各车间子表（经 ``page_table_mirror_records``
    镜像），投影时按字段名启发式抽取 编号 / 归属部门 / 存放位置，器材类型
    优先取记录字段、其次按子表名判断。二维码与扫码点检都基于本表 id。
    """

    __tablename__ = "fire_equipment"
    __table_args__ = (
        Index(
            "uq_safety_fire_equipment_source_record",
            "table_id",
            "record_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "ix_safety_fire_equipment_page",
            "page_key",
            "is_deleted",
        ),
        {"schema": "safety"},
    )

    page_key: Mapped[str] = mapped_column(
        String(160), nullable=False, comment="来源镜像页标识"
    )
    table_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="来源飞书子表 table_id"
    )
    record_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="来源飞书记录 record_id"
    )
    tab_name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="",
        server_default="",
        comment="来源子表页签名（车间）",
    )
    equipment_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="extinguisher",
        server_default="extinguisher",
        comment="器材类型: extinguisher=灭火器 / hydrant=消防栓",
    )
    equipment_no: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        server_default="",
        comment="器材编号（如 灭火器编号/消防栓编号 列值）",
    )
    department: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="",
        server_default="",
        comment="归属部门/车间",
    )
    location: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="",
        server_default="",
        comment="存放位置",
    )
    fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, comment="镜像解码后的全部字段值"
    )
    search_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="关键字搜索文本（编号/部门/位置/子表名）",
    )
    last_inspected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近一次点检时间"
    )
    last_inspection_result: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="最近一次点检结论: pass=合格 / fail=不合格",
    )
    expiry_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="有效日期（投影自飞书 有效日期/有效期 等字段）",
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.now(UTC),
        server_default=text("now()"),
        comment="该行最近投影同步时间",
    )


class FireExpiryNotificationLog(BaseModel):
    """有效期提醒推送记录：每台器材每个提醒节点只推一次（0 = 已过期节点）。"""

    __tablename__ = "fire_expiry_notification_log"
    __table_args__ = (
        UniqueConstraint(
            "equipment_id",
            "milestone_days",
            name="uq_fire_expiry_notify_once_per_milestone",
        ),
        {"schema": "safety"},
    )

    equipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("safety.fire_equipment.id"),
        nullable=False,
        comment="器材 id（safety.fire_equipment）",
    )
    milestone_days: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="触发的提醒节点天数；0 表示已过期节点"
    )
    notified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class FireInspectionRecord(BaseModel):
    """消防器材点检记录（扫码或网页提交，一次点检一行）。

    ``items`` 存当次点检的完整检查项快照（含文案），检查卡内容调整后
    历史记录仍按当时口径展示；器材基础信息同样快照，台账删除不影响追溯。
    """

    __tablename__ = "fire_inspection_records"
    __table_args__ = (
        Index(
            "ix_safety_fire_inspections_equipment",
            "equipment_id",
            "inspected_at",
        ),
        Index(
            "ix_safety_fire_inspections_inspected_at",
            "inspected_at",
        ),
        {"schema": "safety"},
    )

    equipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("safety.fire_equipment.id"),
        nullable=False,
        comment="器材 id（safety.fire_equipment）",
    )
    equipment_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="器材类型快照: extinguisher/hydrant"
    )
    equipment_no: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        server_default="",
        comment="器材编号快照",
    )
    department: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="",
        server_default="",
        comment="归属部门快照",
    )
    location: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="",
        server_default="",
        comment="存放位置快照",
    )
    items: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="检查项快照 [{key, label, result: ok/fail, remark}]",
    )
    result: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="点检结论: pass=全部合格 / fail=存在不合格项",
    )
    failed_items: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
        comment="不合格项 [{key, label}]",
    )
    abnormal_action: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="异常处理措施"
    )
    inspector_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="点检人用户 id"
    )
    inspector_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        server_default="",
        comment="点检人姓名",
    )
    inspected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="点检时间"
    )
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="web",
        server_default="web",
        comment="提交来源: scan=扫码页 / web=网页端",
    )
    feishu_record_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="回写飞书点检记录表的 record_id（NULL=待回写）",
    )


# ==================== 应急处置卡 ====================


class EmergencyCard(BaseModel):
    """应急处置卡：车间/岗位级事故现场处置卡。

    初始数据来自各车间应急资料（101-102、103、201 一车间、203 车间、
    动力部及公司级），由种子迁移导入；后续可在「应急处置卡」页面维护。
    """

    __tablename__ = "emergency_cards"
    __table_args__ = (
        Index(
            "uq_safety_emergency_cards_title",
            "workshop",
            "position",
            "title",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_safety_emergency_cards_workshop", "workshop", "is_deleted"),
        {"schema": "safety"},
    )

    workshop: Mapped[str] = mapped_column(
        String(60), nullable=False, comment="车间/部门（如 103车间、公司级、动力部）"
    )
    position: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        default="",
        server_default="",
        comment="岗位（如 配料、化测；车间级/公司级卡为空）",
    )
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="卡片标题（如 103车间液氨泄漏应急处置卡）"
    )
    subject: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="",
        server_default="",
        comment="处置主题（标题去除车间/岗位前缀与「应急处置卡」后缀）",
    )
    accident_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="综合",
        server_default="综合",
        comment="事故类型（泄漏/火灾/中毒/触电等）",
    )
    steps: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="处置步骤 [{order, step, action, person}]",
    )
    extras: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="其他段落 [{label, content}]（如 次生、衍生事故）",
    )
    phones: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default="", comment="应急电话"
    )
    risks: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="主要导致风险及导致的后果",
    )
    precautions: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default="", comment="应急注意事项"
    )
    source_file: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
        comment="来源文件名（种子导入溯源）",
    )
    search_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="关键字搜索文本（标题/主题/类型/步骤/电话拼接）",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="展示排序（同车间内升序）",
    )


# ==================== 厂区建筑底册（总览驾驶舱地图） ====================


class CampusBuilding(BaseModel):
    """厂区建筑/分区底册：平面图落点与地点文本归一的目标清单。

    坐标为平面图底图（public/safety/campus-map.png）上的百分比位置；
    aliases 用于把作业票/报备/隐患等自由文本地点归一到建筑，
    由种子迁移导入，后续可在数据库中维护。
    """

    __tablename__ = "campus_buildings"
    __table_args__ = (
        Index(
            "uq_safety_campus_buildings_name",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_safety_campus_buildings_category", "category", "is_deleted"),
        {"schema": "safety"},
    )

    code: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="",
        server_default="",
        comment="建筑编号（图纸编号，如 101、802）",
    )
    name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        comment="建筑名称（重名建筑带方位/编号后缀）"
    )
    category: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="workshop",
        server_default="workshop",
        comment="类别: workshop/warehouse/utility/env/tank/office/logistics/sports",
    )
    x_pct: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        server_default="0",
        comment="平面图横向百分比坐标（0-100）",
    )
    y_pct: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        server_default="0",
        comment="平面图纵向百分比坐标（0-100）",
    )
    aliases: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, comment="地点别名列表（自由文本归一用）"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="展示排序"
    )


# ==================== 体系治理：目标责任与绩效 ====================


class SafetyTarget(BaseModel):
    """年度安全目标：公司/部门级安全生产目标指标。"""

    __tablename__ = "safety_targets"
    __table_args__ = (
        Index(
            "uq_safety_targets_year_title",
            "year",
            "title",
            "owner_department",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_safety_targets_year", "year", "is_deleted"),
        {"schema": "safety"},
    )

    year: Mapped[int] = mapped_column(Integer, nullable=False, comment="目标年度")
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="目标名称（如 杜绝重伤及以上事故）"
    )
    category: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="事故控制",
        server_default="事故控制",
        comment="目标类别（事故控制/隐患治理/培训教育/职业健康/消防应急等）",
    )
    metric: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="",
        server_default="",
        comment="考核指标说明（如何量化）",
    )
    target_value: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        server_default="",
        comment="目标值（如 0 起、100%、≤3 项）",
    )
    unit: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="",
        server_default="",
        comment="计量单位（起/次/%/项）",
    )
    owner_department: Mapped[str] = mapped_column(
        String(100), nullable=False, default="", server_default="", comment="责任部门"
    )
    owner_name: Mapped[str] = mapped_column(
        String(60), nullable=False, default="", server_default="", comment="责任人"
    )
    deadline: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="完成时限",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="in_progress",
        server_default="in_progress",
        comment="状态: in_progress=进行中 / achieved=已达成 / not_achieved=未达成",
    )
    remark: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="备注"
    )
    search_text: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default="", comment="关键字搜索文本"
    )

    records: Mapped[list["SafetyTargetRecord"]] = relationship(
        primaryjoin="and_(SafetyTarget.id == foreign(SafetyTargetRecord.target_id), "
        "SafetyTargetRecord.is_deleted.is_(False))",
        viewonly=True,
        lazy="selectin",
        order_by="SafetyTargetRecord.period",
    )


class SafetyTargetRecord(BaseModel):
    """安全目标进度记录：按月/季度录入实际完成值。"""

    __tablename__ = "safety_target_records"
    __table_args__ = (
        Index(
            "uq_safety_target_records_target_period",
            "target_id",
            "period",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_safety_target_records_target", "target_id", "is_deleted"),
        {"schema": "safety"},
    )

    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("safety.safety_targets.id"),
        nullable=False,
        comment="所属目标",
    )
    period: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="考核期（如 2026-Q1、2026-03）"
    )
    actual_value: Mapped[str] = mapped_column(
        String(100), nullable=False, default="", server_default="", comment="实际完成值"
    )
    completion_pct: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="完成率（%，可空）"
    )
    note: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="情况说明"
    )


class SafetyTargetAgreement(BaseModel):
    """安全目标责任书：年度×部门×岗位的安全生产目标责任签订台账。"""

    __tablename__ = "safety_target_agreements"
    __table_args__ = (
        Index(
            "uq_safety_target_agreements_key",
            "year",
            "department",
            "position",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_safety_target_agreements_year", "year", "is_deleted"),
        Index("ix_safety_target_agreements_status", "status", "is_deleted"),
        {"schema": "safety"},
    )

    year: Mapped[int] = mapped_column(Integer, nullable=False, comment="签订年度")
    department: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="责任部门/单位（公司领导层用 公司领导）"
    )
    position: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="岗位/角色（如 负责人、安全管理科人员）"
    )
    category: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="岗位员工",
        server_default="岗位员工",
        comment="分类: 公司领导 / 部门/车间负责人 / 岗位员工",
    )
    party_a: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        default="",
        server_default="",
        comment="甲方（公司/考核方代表）",
    )
    party_b: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        default="",
        server_default="",
        comment="乙方（责任方签订人）",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="unsigned",
        server_default="unsigned",
        comment="状态: unsigned=未签订 / signed=已签订",
    )
    signed_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="签订日期"
    )
    expires_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="有效期至（责任书一年一签）",
    )
    goals_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="安全生产目标条款（每行一条）",
    )
    remark: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="备注"
    )
    search_text: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default="", comment="关键字搜索文本"
    )


class SafetyDutyAssessment(BaseModel):
    """安全生产责任制考核：按季度对部门/负责人的责任制考核记录（百分制）。"""

    __tablename__ = "safety_duty_assessments"
    __table_args__ = (
        Index(
            "uq_safety_duty_assessments_key",
            "year",
            "quarter",
            "department",
            "person_name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "ix_safety_duty_assessments_year_quarter",
            "year",
            "quarter",
            "is_deleted",
        ),
        {"schema": "safety"},
    )

    year: Mapped[int] = mapped_column(Integer, nullable=False, comment="考核年度")
    quarter: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="考核季度 1-4"
    )
    department: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="被考核部门/单位"
    )
    person_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        server_default="",
        comment="被考核人（可空=部门整体）",
    )
    assessor: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        server_default="",
        comment="考核单位（如 安全部）",
    )
    assessment_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="考核日期"
    )
    total_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        server_default="0",
        comment="考核总得分（百分制）",
    )
    grade: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="不合格",
        server_default="不合格",
        comment="等级: >=95优秀 / >=90良好 / >=80合格 / <80不合格",
    )
    remark: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="备注"
    )
    search_text: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default="", comment="关键字搜索文本"
    )

    items: Mapped[list["SafetyDutyAssessmentItem"]] = relationship(
        primaryjoin="and_(SafetyDutyAssessment.id == "
        "foreign(SafetyDutyAssessmentItem.assessment_id), "
        "SafetyDutyAssessmentItem.is_deleted.is_(False))",
        viewonly=True,
        lazy="selectin",
        order_by="SafetyDutyAssessmentItem.sort_order",
    )


class SafetyDutyAssessmentItem(BaseModel):
    """责任制考核评分明细：考核内容/标准分/扣减分/得分。"""

    __tablename__ = "safety_duty_assessment_items"
    __table_args__ = (
        Index(
            "ix_safety_duty_assessment_items_assessment",
            "assessment_id",
            "is_deleted",
        ),
        {"schema": "safety"},
    )

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("safety.safety_duty_assessments.id"),
        nullable=False,
        comment="所属考核记录",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="排列序号"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="考核内容")
    rule: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default="", comment="考核标准/扣分规则"
    )
    standard_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0", comment="标准分"
    )
    deduction_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0", comment="扣减分"
    )
    score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0", comment="考核得分"
    )
    remark: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default="", comment="考核明细说明"
    )


# ==================== 现场管理：安全设施台账 ====================


class SafetyFacility(BaseModel):
    """安全设施台账：洗眼器、气体检测仪、防护设施等安全设备设施。"""

    __tablename__ = "safety_facilities"
    __table_args__ = (
        Index(
            "uq_safety_facilities_no",
            "facility_no",
            unique=True,
            postgresql_where=text("is_deleted = false and facility_no <> ''"),
        ),
        Index("ix_safety_facilities_category", "category", "is_deleted"),
        Index("ix_safety_facilities_department", "department", "is_deleted"),
        {"schema": "safety"},
    )

    category: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="other",
        server_default="other",
        comment="类别: eyewash=洗眼器 / gas_detector=气体检测仪 / "
        "protective=防护设施 / other=其他",
    )
    facility_no: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        server_default="",
        comment="设施编号（唯一）",
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="设施名称")
    model_spec: Mapped[str] = mapped_column(
        String(200), nullable=False, default="", server_default="", comment="型号规格"
    )
    department: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        server_default="",
        comment="所属部门/车间",
    )
    location: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default="", comment="安装位置"
    )
    installed_at: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="投用日期"
    )
    expiry_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="校准/检定/报废到期日（气体检测仪为校准有效期）"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="normal",
        server_default="normal",
        comment="状态: normal=完好 / damaged=损坏 / scrapped=报废",
    )
    last_inspected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="最近点检时间"
    )
    last_inspection_result: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="最近点检结论: pass/fail"
    )
    remark: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="备注"
    )
    search_text: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default="", comment="关键字搜索文本"
    )


class SafetyFacilityInspection(BaseModel):
    """安全设施点检记录（快照式，与消防器材点检同构）。"""

    __tablename__ = "safety_facility_inspections"
    __table_args__ = (
        Index("ix_safety_facility_inspections_facility", "facility_id", "inspected_at"),
        Index("ix_safety_facility_inspections_inspected_at", "inspected_at"),
        {"schema": "safety"},
    )

    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("safety.safety_facilities.id"),
        nullable=False,
        comment="设施",
    )
    facility_category: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="",
        server_default="",
        comment="设施类别快照",
    )
    facility_no: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        server_default="",
        comment="设施编号快照",
    )
    facility_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="",
        server_default="",
        comment="设施名称快照",
    )
    items: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="点检项 [{key, label, result: ok/fail, remark}]",
    )
    result: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="结论: pass/fail"
    )
    abnormal_action: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="异常处理措施"
    )
    inspector_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="点检人用户ID"
    )
    inspector_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="", server_default="", comment="点检人姓名"
    )
    inspected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="点检时间"
    )
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="web",
        server_default="web",
        comment="提交来源: web=网页端",
    )


# ==================== 现场管理：危化品与 MSDS ====================


class HazardousChemical(BaseModel):
    """危化品档案：品名/CAS/类别 + MSDS 附件。"""

    __tablename__ = "hazardous_chemicals"
    __table_args__ = (
        Index(
            "uq_safety_hazardous_chemicals_name",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_safety_hazardous_chemicals_category", "category", "is_deleted"),
        {"schema": "safety"},
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="化学品名称")
    alias: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="",
        server_default="",
        comment="别名/商品名",
    )
    cas_no: Mapped[str] = mapped_column(
        String(60), nullable=False, default="", server_default="", comment="CAS 号"
    )
    category: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="other",
        server_default="other",
        comment="危险性类别: explosive/flammable_gas/oxidizing_gas/flammable_liquid/"
        "flammable_solid/self_reactive/oxidizing_liquid/organic_peroxide/toxic/corrosive/other",
    )
    hazard_statements: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="危险性概述（理化/健康/环境危害）",
    )
    storage_requirements: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="储存要求（温度/禁配/防爆等）",
    )
    msds_file_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default="",
        server_default="",
        comment="MSDS 文件路径（uploads/safety/hazchem/）",
    )
    msds_file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
        comment="MSDS 原始文件名",
    )
    remark: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="备注"
    )
    search_text: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default="", comment="关键字搜索文本"
    )


class ChemicalInventory(BaseModel):
    """危化品车间存量：当前存量与上限，超储预警数据源。"""

    __tablename__ = "chemical_inventories"
    __table_args__ = (
        Index(
            "uq_safety_chemical_inventories_chem_ws",
            "chemical_id",
            "workshop",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_safety_chemical_inventories_workshop", "workshop", "is_deleted"),
        {"schema": "safety"},
    )

    chemical_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("safety.hazardous_chemicals.id"),
        nullable=False,
        comment="危化品",
    )
    workshop: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="车间/库房",
    )
    quantity: Mapped[float] = mapped_column(
        Numeric(14, 4),
        nullable=False,
        default=0.0,
        server_default="0",
        comment="当前存量",
    )
    upper_limit: Mapped[float | None] = mapped_column(
        Numeric(14, 4),
        nullable=True,
        comment="存量上限（空=不设限）"
    )
    unit: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="kg",
        server_default="kg",
        comment="单位"
    )
    remark: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="备注"
    )


class ChemicalMsdsAttachment(BaseModel):
    """危化品 MSDS 附件（一个档案可挂多个文件，pdf/docx/图片等）。

    存储走「MinIO 优先、本地 uploads/safety/hazchem 回退」（service 层负责），
    这里只记录元数据；``hazardous_chemicals.msds_file_path/msds_file_name``
    旧单文件两列由迁移搬迁为本表记录后不再写入（保留列便于回滚）。
    """

    __tablename__ = "chemical_msds_attachments"
    __table_args__ = (
        Index(
            "ix_safety_chemical_msds_attachments_chemical",
            "chemical_id",
            "is_deleted",
        ),
        {"schema": "safety"},
    )

    chemical_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("safety.hazardous_chemicals.id"),
        nullable=False,
        comment="危化品档案",
    )
    file_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="原始文件名"
    )
    storage_key: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="存储 key（MinIO 对象名或本地相对路径）"
    )
    content_type: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="",
        server_default="",
        comment="文件 MIME 类型",
    )
    size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="文件大小（字节）",
    )


# ==================== 应急处置：应急管理 ====================


class EmergencyPlan(BaseModel):
    """应急预案台账：综合预案/专项预案/现场处置方案。"""

    __tablename__ = "emergency_plans"
    __table_args__ = (
        Index(
            "uq_safety_emergency_plans_name_version",
            "name",
            "version",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_safety_emergency_plans_status", "status", "is_deleted"),
        {"schema": "safety"},
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="预案名称")
    plan_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="onsite",
        server_default="onsite",
        comment="类型: comprehensive=综合预案 / special=专项预案 / onsite=现场处置方案",
    )
    version: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        default="V1.0",
        server_default="V1.0",
        comment="版本号",
    )
    issued_at: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="发布日期",
    )
    review_due_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="下次评审/修订到期日"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
        comment="状态: active=现行 / revising=修订中 / obsolete=废止",
    )
    department: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        server_default="",
        comment="编制/归口部门",
    )
    file_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default="",
        server_default="",
        comment="预案文件路径（uploads/safety/emergency/）",
    )
    file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
        comment="预案原始文件名",
    )
    remark: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="备注"
    )
    search_text: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default="", comment="关键字搜索文本"
    )


class EmergencyDrill(BaseModel):
    """应急演练计划与记录。"""

    __tablename__ = "emergency_drills"
    __table_args__ = (
        Index("ix_safety_emergency_drills_planned_date", "planned_date", "is_deleted"),
        Index("ix_safety_emergency_drills_status", "status", "is_deleted"),
        {"schema": "safety"},
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="演练名称")
    drill_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="practical",
        server_default="practical",
        comment="类型: tabletop=桌面推演 / practical=实战演练 / comprehensive=综合演练",
    )
    scenario: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
        comment="演练情景（如 液氨泄漏、火灾疏散）",
    )
    plan_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
        comment="对应预案名称",
    )
    planned_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="计划日期"
    )
    actual_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="实际执行日期"
    )
    location: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default="", comment="演练地点"
    )
    departments: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default="",
        server_default="",
        comment="参演部门（顿号分隔）",
    )
    participants_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="参演人数"
    )
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="演练过程与评估总结"
    )
    issues: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="发现问题与改进措施"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="planned",
        server_default="planned",
        comment="状态: planned=计划 / done=完成 / cancelled=取消",
    )
    search_text: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default="", comment="关键字搜索文本"
    )


class EmergencySupply(BaseModel):
    """应急物资台账。"""

    __tablename__ = "emergency_supplies"
    __table_args__ = (
        Index("ix_safety_emergency_supplies_category", "category", "is_deleted"),
        Index("ix_safety_emergency_supplies_department", "department", "is_deleted"),
        {"schema": "safety"},
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="物资名称")
    category: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="other",
        server_default="other",
        comment="类别: firefighting=消防 / protective=防护 / medical=医疗 / "
        "communication=通讯 / leak_sealing=堵漏 / other=其他",
    )
    spec: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="",
        server_default="",
        comment="规格型号"
    )
    location: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default="", comment="存放位置"
    )
    department: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        server_default="",
        comment="管理部门/车间",
    )
    quantity: Mapped[float] = mapped_column(
        Numeric(14, 2), nullable=False, default=0.0, server_default="0", comment="数量"
    )
    unit: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="件",
        server_default="件",
        comment="单位"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="good",
        server_default="good",
        comment="状态: good=完好 / repair=待修 / scrapped=报废",
    )
    expiry_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="有效期至（如药剂/呼吸器）"
    )
    last_checked_at: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="最近检查日期"
    )
    last_check_result: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
        comment="最近检查结论（完好/异常描述）",
    )
    remark: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="备注"
    )
    search_text: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default="", comment="关键字搜索文本"
    )


# ==================== 职业健康：检测报告导入 ====================


class OhDetectionReport(BaseModel):
    """职业病危害因素检测报告（第三方检测机构报告批次）。

    一份 PDF 报告一行；明细见 ``OhDetectionResult``。
    同 report_no 重复导入按覆盖更新处理（更新本行 + 重建明细）。
    """

    __tablename__ = "oh_detection_reports"
    __table_args__ = (
        Index(
            "uq_safety_oh_detection_reports_no",
            "report_no",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_safety_oh_detection_reports_date", "detection_date", "is_deleted"),
        {"schema": "safety", "comment": "职业病危害因素检测报告"},
    )

    report_no: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="报告编号（如 NZXZW-J-2026-141）"
    )
    report_name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default="", comment="报告名称"
    )
    company_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
        comment="受检企业",
    )
    detection_agency: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
        comment="检测机构",
    )
    detection_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="检测日期"
    )
    table_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="识别表格数"
    )
    total_points: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="检测点数合计"
    )
    exceed_points: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="超标点数"
    )
    noise_post_points: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="噪声作业岗位数",
    )
    source_file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
        comment="原始报告文件名",
    )
    source_file_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default="",
        server_default="",
        comment="原始报告存储路径（uploads/safety/oh-detection/）",
    )
    source_file_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default="", comment="文件 SHA256"
    )
    parse_mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="rules",
        server_default="rules",
        comment="解析模式: rules=规则 / llm=AI兜底 / mixed=混合",
    )
    parse_warnings: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, comment="解析警告 [{table, reason}]"
    )
    remark: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default="", comment="备注"
    )
    search_text: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default="", comment="关键字搜索文本"
    )


class OhDetectionResult(BaseModel):
    """检测报告结果明细：一个检测点/岗位接触记录一行。

    ``record_type``：post=岗位接触（C_TWA / L_EX,40h / WBGT 岗位级），
    point=采样点·测量地点单点（C_PE / C_STE / C_ME / 测量值）。
    检出限表达（如 ``＜0.44``）保留原文，``measured_value_num`` 置空。
    """

    __tablename__ = "oh_detection_results"
    __table_args__ = (
        Index("ix_safety_oh_detection_results_report", "report_id", "seq"),
        Index(
            "ix_safety_oh_detection_results_category",
            "report_id",
            "factor_category",
        ),
        Index(
            "ix_safety_oh_detection_results_verdict",
            "verdict",
            "is_deleted",
        ),
        {"schema": "safety", "comment": "职业病危害因素检测结果明细"},
    )

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("safety.oh_detection_reports.id"),
        nullable=False,
        comment="所属检测报告",
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="序号")
    table_ref: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="",
        server_default="",
        comment="表号（表5-18）",
    )
    table_title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
        comment="表标题",
    )
    factor_category: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="危害因素类别: dust_total/dust_respirable/free_silica/chemical/"
        "noise/power_frequency_field/heat",
    )
    factor_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="危害因素名称（谷物粉尘/噪声…）"
    )
    record_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="point", comment="记录类型: post/point"
    )
    workshop: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default="", comment="车间"
    )
    post: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default="", comment="岗位"
    )
    sample_point: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
        comment="采样点/测量地点",
    )
    measured_value: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="",
        server_default="",
        comment="检测值原文(＜0.44)",
    )
    measured_value_num: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="检测值数值（检出限表达为空）"
    )
    unit: Mapped[str] = mapped_column(
        String(32), nullable=False, default="", server_default="", comment="单位"
    )
    limit_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="none",
        server_default="none",
        comment="限值类型: PC-TWA/PC-STEL/MAC/PE/LEX-40h/E8/WBGT/none",
    )
    limit_value_num: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="限值数值"
    )
    verdict: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="unknown",
        server_default="unknown",
        comment="判定: compliant=未超标 / exceed=超标 / unknown=未识别",
    )
    is_noise_post: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="是否噪声作业岗位（80≤LEX,8h＜85dB 场景）",
    )
    verdict_raw: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="",
        server_default="",
        comment="判定原文",
    )
    extra: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="类别特有字段（噪声LEX、高温接触时间率等）"
    )
