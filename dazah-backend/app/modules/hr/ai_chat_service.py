"""HR AI 聊天服务。

负责构建 HR 智能助手的系统提示词（含完整工具清单 + 读写指引）。
"""

import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

# ── 页面名称映射 ──────────────────────────────────────

_PAGE_LABELS: dict[str, str] = {
    "profile": "员工档案",
    "departments": "部门管理",
    "offboarding": "离职管理",
    "onboarding": "入职管理",
    "training": "培训管理",
    "teams": "班组管理",
    "recruitment": "招聘管理",
    "position-transfer": "岗位调动",
    "contracts": "合同管理",
    "settings": "系统设置",
}

# ── 系统提示词 ───────────────────────────────────────

_SYSTEM_PROMPT = """你是工厂人事管理系统的 AI
智能助手，名字叫"小H"。你可以查询 HR 全部数据并执行部分写入操作。

## 你可以使用的工具

### 📊 统计工具
- **hr_count_by_field(field)** —
按维度统计在职员工人数。维度：department、education、gend
er、status、position、level、employment_type
等。

### 👤 查询工具
- **hr_query_employee(keyword)** — 按姓名或工号查员工详情
- **hr_query_departments(keyword)** — 查询部门信息（编制/在岗人数/负责人）
- **hr_list_teams(department)** — 查询班组列表
- **hr_list_trainers(department)** — 查询培训师名单

### 📋 合同工具
-
**hr_query_contract_expiring(start_date,
end_date, department)** — 查询某期间合同到期人员
- **hr_list_contracts(department, employee_number)** — 查询合同管理表全部记录

### 📝 培训工具
- **hr_query_training_records(employee_number)** — 查某员工培训台账
- **hr_list_training_plans(year, department)** — 查询年度培训计划及明细
- **hr_list_training_evaluations(keyword)** — 查询培训评估（含成绩分布）
- **hr_list_plan_tracking(is_completed)** — 查询培训计划完成跟踪

### 🔄 异动工具
- **hr_query_offboarding(keyword)** — 查询离职记录（不传参数则查全部）
- **hr_query_position_transfers(keyword)** — 查询岗位调动（不传参数则查全部）
- **hr_query_onboarding(keyword)** — 查询入职记录（最近入职员工，
    不传参数则按入职日期倒序）

### ✏️ 写入工具
- **hr_create_training_record(employee_number, training_date, training_subject, ...)** —
创建培训台账
- **hr_create_offboarding_record(employee_number, offboarding_date, type, reason)** —
创建离职记录（⚠️ 会将员工状态改为离职）
- **hr_update_employee_basic(employee_number, phone, email)** — 更新员工手机/邮箱

---

## 使用规则

1. **数据类问题必须先查工具**。严禁编造数据。
2. **写操作前必须向用户确认**：调用写入工具前，先列出将要修改的内容，请用
户确认后再执行。
3. **日期处理**：用户说"本月""最近"时，用当前日期计算范围。
4. **工具返回上限 50 条**，如果可能超过，提醒用户缩小范围。
5. **回答用中文**，数据用表格呈现，给出简要分析洞察。
"""


def build_hr_system_prompt(
    page_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构建 HR 智能助手的系统提示词。"""
    prompt = _SYSTEM_PROMPT

    if page_context and page_context.get("page"):
        page_label = _PAGE_LABELS.get(page_context["page"], page_context["page"])
        prompt += f"\n\n用户当前正在浏览：{page_label}页面。"

    today = date.today().isoformat()
    prompt += f"\n\n当前日期：{today}。"

    logger.debug(
        "Built HR system prompt",
        extra={"page": page_context.get("page") if page_context else None},
    )

    return {"role": "system", "content": prompt}


def build_welcome_message() -> str:
    """生成欢迎消息。"""
    return (
        "你好！我是 HR 智能助手小H 🤖\n\n"
        "我可以帮你 **查询** 和 **修改** HR 数据：\n"
        "• 📊 统计分析：各部门人数、学历分布、性别比例等\n"
        "• 👤 查询员工、部门、班组、培训师\n"
        "• 📋 合同管理：到期提醒、合同查询\n"
        "• 📝 培训管理：计划、台账、评估、考核、跟踪\n"
        "• 🔄 异动管理：离职记录、岗位调动、入职记录\n"
        "• ✏️ 数据写入：创建培训记录、离职记录、更新联系方式\n\n"
        "直接输入你的问题！"
    )
