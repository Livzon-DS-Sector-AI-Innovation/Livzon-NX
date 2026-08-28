"""AI 考试相关 Pydantic Schema。

由 exam_generator.py 和 ai_exam_api.py 共用。
"""

from pydantic import BaseModel, Field


class ChoiceOption(BaseModel):
    """选择题选项"""

    label: str = Field(..., description="选项标签，如 A/B/C/D")
    text: str = Field(..., description="选项内容")


class ChoiceQuestion(BaseModel):
    """选择题"""

    number: int = Field(..., description="题号")
    question: str = Field(..., description="题目内容")
    options: list[ChoiceOption] = Field(..., description="选项列表")
    answer: str = Field(..., description="正确答案标签，如 A")


class TrueFalseQuestion(BaseModel):
    """判断题"""

    number: int = Field(..., description="题号")
    question: str = Field(..., description="题目内容")
    answer: str = Field(..., description="正确答案，√ 或 ×")


class ExamGenerateRequest(BaseModel):
    """生成考题请求"""

    file_content: str = Field(..., description="培训材料文本内容", min_length=10)


class ExamGenerateResponse(BaseModel):
    """生成考题响应"""

    choice_questions: list[ChoiceQuestion] = Field(
        default_factory=list, description="选择题列表"
    )
    true_false_questions: list[TrueFalseQuestion] = Field(
        default_factory=list, description="判断题列表"
    )


class ExamExportRequest(BaseModel):
    """导出试卷请求"""

    title: str = Field(..., description="试卷标题")
    examiner: str = Field(..., description="出卷人")
    exam_date: str = Field(..., description="出卷时间")
    assessment_date: str = Field(..., description="考核时间")
    choice_questions: list[ChoiceQuestion] = Field(..., description="选择题列表")
    true_false_questions: list[TrueFalseQuestion] = Field(..., description="判断题列表")


class OralExamFile(BaseModel):
    """口试出题材料文件"""

    name: str = Field(..., max_length=256, description="文件名称")
    code: str | None = Field(default=None, max_length=64, description="文件编码")
    # 单份素材内容上限 20 万字符：与分批上限同量级，防恶意超大文本耗尽内存
    content: str = Field(..., max_length=200_000, description="文件标准 MD 文本内容")


class OralExamGenerateRequest(BaseModel):
    """口试（问答）出题请求"""

    # 不限数量：培训勾选教材份数不设上限（2026-08-13 业务确认）；
    # 单份 content 已限 200k 字符，总量由份数×单份上限兜底
    files: list[OralExamFile] = Field(..., min_length=1, description="培训材料文件列表")
    # 用户可选总题数；为空时按默认逻辑（每份文件 2~3 题，超 5 份文件≤15 题）
    question_count: int | None = Field(None, ge=1, le=100, description="总题数（可选）")


class OralExamQuestion(BaseModel):
    """口试问答题"""

    question: str = Field(..., description="考核问题")
    answer: str = Field(..., description="参考答案要点")


class OralExamGenerateResponse(BaseModel):
    """口试（问答）出题响应"""

    questions: list[OralExamQuestion] = Field(
        default_factory=list, description="问答题列表"
    )


# ─── AI 笔试（选择+填空） ───


class WrittenExamGenerateRequest(BaseModel):
    """AI 笔试出题请求"""

    files: list[OralExamFile] = Field(
        default=[], description="文件内容列表（名称+编码+文本）"
    )
    # 上传/手动内容上限 20 万字符：防恶意超大文本耗尽内存
    uploaded_content: str = Field(
        default="", max_length=200_000, description="上传文件提取的文本"
    )
    manual_content: str = Field(
        default="", max_length=200_000, description="手动粘贴的额外内容"
    )
    single_choice_count: int = Field(default=5, ge=0, le=20, description="单选题数量")
    multiple_choice_count: int = Field(default=0, ge=0, le=20, description="多选题数量")
    true_false_count: int = Field(default=0, ge=0, le=20, description="判断题数量")
    fill_blank_count: int = Field(default=5, ge=0, le=20, description="填空题数量")


class FillBlankQuestion(BaseModel):
    """填空题"""

    number: int = Field(..., description="题号")
    question: str = Field(..., description="题目内容（填空处用______表示）")
    answer: str = Field(default="", description="填空答案")


class WrittenExamGenerateResponse(BaseModel):
    """AI 笔试出题响应"""

    choice_questions: list[ChoiceQuestion] = Field(
        default_factory=list, description="选择题列表"
    )
    true_false_questions: list[TrueFalseQuestion] = Field(
        default_factory=list, description="判断题列表"
    )
    fill_blank_questions: list[FillBlankQuestion] = Field(
        default_factory=list, description="填空题列表"
    )
    shortfall: bool = Field(default=False, description="实际生成题数少于请求数量")


class WrittenExamJobSubmitResponse(BaseModel):
    """AI 笔试出题任务提交响应：立即返回 job_id，结果通过轮询接口获取"""

    job_id: str = Field(..., description="后台任务 ID，用于轮询出题进度与结果")


class WrittenExamJobStatusResponse(BaseModel):
    """AI 笔试出题任务状态查询响应"""

    state: str = Field(..., description="任务状态：running / completed / failed")
    progress: str = Field(default="", description="进度文案（如“正在生成第 3/15 批…”）")
    result: WrittenExamGenerateResponse | None = Field(
        default=None, description="出题结果（completed 时有）"
    )
    error: str | None = Field(default=None, description="错误信息（failed 时有）")


class WrittenExamExportRequest(BaseModel):
    """笔试试卷导出请求"""

    title: str = Field(..., description="试卷标题（自动使用 session.topic）")
    examiner: str = Field(default="", description="出卷人")
    exam_date: str = Field(default="", description="出卷时间")
    assessment_date: str = Field(default="", description="考核时间")
    choice_questions: list[ChoiceQuestion] = Field(
        default_factory=list, description="选择题列表"
    )
    true_false_questions: list[TrueFalseQuestion] = Field(
        default_factory=list, description="判断题列表"
    )
    fill_blank_questions: list[FillBlankQuestion] = Field(
        default_factory=list, description="填空题列表"
    )
