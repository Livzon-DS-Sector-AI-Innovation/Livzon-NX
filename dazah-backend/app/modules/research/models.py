"""Research ORM models."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class ResearchProject(BaseModel):
    """研发项目主表"""

    __tablename__ = "research_projects"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('立项', '研发中试', '验证', '注册', '商业化')",
            name="ck_research_projects_stage",
        ),
        CheckConstraint(
            "status IN ('进行中', '已暂停', '已完成', '已终止')",
            name="ck_research_projects_status",
        ),
        {"schema": "research"},
    )

    project_no: Mapped[str] = mapped_column(
        String(50), comment="项目编号"
    )
    name: Mapped[str] = mapped_column(
        String(200), comment="项目名称"
    )
    project_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="项目类型"
    )
    stage: Mapped[str] = mapped_column(
        String(20),
        default="立项",
        comment="项目阶段：立项/研发中试/验证/注册/商业化",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="进行中",
        comment="项目状态：进行中/已暂停/已完成/已终止",
    )
    leader: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="项目负责人"
    )
    start_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="开始日期"
    )
    end_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="结束日期"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="项目描述"
    )


class ICHAnalysisRecord(BaseModel):
    """ICH Q3C/Q3D 杂质识别分析记录"""

    __tablename__ = "ich_analysis_records"
    __table_args__ = {"schema": "research"}

    filename: Mapped[str] = mapped_column(
        String(500), comment="上传的文件名"
    )
    route: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="给药途径: oral/parenteral/inhalation/cutaneous (deprecated)"
    )
    q3c_result: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Q3C 溶剂残留分析结果"
    )
    q3d_result: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Q3D 元素杂质分析结果"
    )
    llm_used: Mapped[bool] = mapped_column(
        default=False, comment="是否使用 LLM 增强识别"
    )
    notes: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="备注"
    )


class RouteDevelopment(BaseModel):
    """打通路线开发记录"""

    __tablename__ = "route_developments"
    __table_args__ = {"schema": "research"}

    # Override id from BaseModel to use String (DB column is varchar)
    id: Mapped[str] = mapped_column(
        String(50), primary_key=True, comment="主键ID"
    )

    project_id: Mapped[str] = mapped_column(
        String(50), comment="所属研发项目ID"
    )
    route_no: Mapped[str] = mapped_column(
        String(50), comment="路线编号"
    )
    name: Mapped[str] = mapped_column(
        String(200), comment="路线名称"
    )
    source: Mapped[str] = mapped_column(
        String(50), default="manual", comment="来源: manual/literature/llm"
    )
    source_reference: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="来源引用"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="描述"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="planning",
        comment="状态: planning/in_progress/completed/failed"
    )
    current_module: Mapped[str] = mapped_column(
        String(20), default="research",
        comment="当前工作流阶段: research/trial/assessment/confirmation"
    )
    literature_sources: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="文献来源数据"
    )
    candidate_routes: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="候选路线列表"
    )
    selected_route_ids: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="已选路线ID列表"
    )
    experiment_plans: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="实验方案列表"
    )
    assessment: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="四维度评估结果"
    )
    deliverables: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="交付物列表"
    )
    start_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="开始日期"
    )
    end_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="结束日期"
    )



class RouteExperiment(BaseModel):
    """打通路线实验记录"""

    __tablename__ = "route_experiments"
    __table_args__ = {"schema": "research"}

    # Override id from BaseModel to use String (DB column is varchar)
    id: Mapped[str] = mapped_column(
        String(50), primary_key=True, comment="主键ID"
    )

    route_id: Mapped[str | None] = mapped_column(
        String(50), comment="所属路线ID"
    )
    experiment_no: Mapped[str] = mapped_column(
        String(50), comment="实验编号"
    )
    title: Mapped[str] = mapped_column(
        String(200), comment="实验标题"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="实验描述"
    )
    experiment_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="实验日期"
    )
    operator: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="操作人"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="planned",
        comment="状态: planned/in_progress/completed/failed"
    )
    reaction_temp: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="反应温度"
    )
    reaction_time: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="反应时间"
    )
    yield_pct: Mapped[float | None] = mapped_column(
        nullable=True, comment="收率(%)"
    )
    purity: Mapped[float | None] = mapped_column(
        nullable=True, comment="纯度(%)"
    )
    impurities: Mapped[float | None] = mapped_column(
        nullable=True, comment="杂质(%)"
    )
    result_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="结果摘要"
    )



class ProcessOptimization(BaseModel):
    """工艺优化记录"""

    __tablename__ = "process_optimizations"
    __table_args__ = {"schema": "research"}

    # Override id from BaseModel to use String (DB column is varchar)
    id: Mapped[str] = mapped_column(
        String(50), primary_key=True, comment="主键ID"
    )

    project_id: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="所属研发项目ID"
    )
    route_id: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="来源路线ID"
    )
    name: Mapped[str] = mapped_column(
        String(200), comment="优化任务名称"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="描述"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="planning",
        comment="状态: planning/in_progress/completed/failed"
    )
    current_module: Mapped[str] = mapped_column(
        String(20), default="doe",
        comment="当前工作流阶段: doe/impurity/crystal/quality/scaleup/report"
    )
    doe_design: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="DOE实验设计数据"
    )
    doe_results: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="DOE实验结果数据"
    )
    impurity_study: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="杂质研究数据"
    )
    crystal_form_study: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="晶型研究数据"
    )
    quality_standards: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="质量标准数据"
    )
    scale_up_study: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="公斤级放大数据"
    )
    final_report: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="最终报告数据"
    )
    start_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="开始日期"
    )
    end_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="结束日期"
    )




class PilotWorkflow(BaseModel):
    """中试研究实例"""

    __tablename__ = "pilot_workflows"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'waiting_approval', 'completed', 'failed')",
            name="ck_pilot_workflows_status",
        ),
        {"schema": "research"},
    )

    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="关联研发项目ID"
    )
    product_name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="产品名称"
    )
    scale_up_ratio: Mapped[float] = mapped_column(
        Float, nullable=False, comment="放大倍数"
    )
    equipment_type: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="设备类型"
    )
    equipment_volume: Mapped[float] = mapped_column(
        Float, nullable=False, comment="设备容积(L)"
    )
    input_document_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="上传文档路径"
    )
    input_context: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="额外上下文"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", comment="状态"
    )
    final_report: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="最终报告"
    )


class PilotWorkflowStep(BaseModel):
    """工作流步骤执行记录"""

    __tablename__ = "pilot_workflow_steps"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'waiting_approval', 'completed', 'failed', 'skipped')",
            name="ck_pilot_workflow_steps_status",
        ),
        {"schema": "research"},
    )

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, comment="工作流ID"
    )
    step_order: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="步骤序号"
    )
    step_code: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="步骤标识"
    )
    step_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="步骤名称"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", comment="状态"
    )
    input_data: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="输入数据"
    )
    output_data: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="输出数据"
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="错误信息"
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="开始时间"
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="完成时间"
    )


class BayesianProject(BaseModel):
    """贝叶斯优化项目表"""

    __tablename__ = "bayesian_projects"
    __table_args__ = {"schema": "research"}

    name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="项目名称"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="项目描述"
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="项目状态"
    )


class BayesianExperiment(BaseModel):
    """贝叶斯优化实验表"""

    __tablename__ = "bayesian_experiments"
    __table_args__ = {"schema": "research"}

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, comment="所属项目ID"
    )
    batch_number: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="实验批次号"
    )
    parameters: Mapped[dict] = mapped_column(
        JSON, nullable=False, comment="实验参数"
    )
    results: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="实验结果"
    )
    is_suggested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, comment="是否为建议的实验"
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="实验状态"
    )


class BayesianObjective(BaseModel):
    """贝叶斯优化目标表"""

    __tablename__ = "bayesian_objectives"
    __table_args__ = {"schema": "research"}

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, comment="所属项目ID"
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="目标名称"
    )
    direction: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="优化方向：maximize/minimize"
    )
    weight: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="目标权重"
    )
    threshold: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="目标阈值"
    )


class BayesianComponent(BaseModel):
    """贝叶斯优化组件表"""

    __tablename__ = "bayesian_components"
    __table_args__ = {"schema": "research"}

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, comment="所属项目ID"
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="组件名称"
    )
    lower_bound: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="下界"
    )
    upper_bound: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="上界"
    )
    interval: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="间隔"
    )
    unit: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="单位"
    )
    sort_order: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="排序顺序"
    )
    component_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="组件类型"
    )
    data_points: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="数据点数"
    )
    categorical_values: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="分类值"
    )


class ReactionScope(BaseModel):
    """反应范围表"""

    __tablename__ = "reaction_scopes"
    __table_args__ = {"schema": "research"}

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, comment="所属项目ID"
    )
    name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="范围名称"
    )
    scope_data: Mapped[dict] = mapped_column(
        JSON, nullable=False, comment="范围数据"
    )
    total_combinations: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="总组合数"
    )
