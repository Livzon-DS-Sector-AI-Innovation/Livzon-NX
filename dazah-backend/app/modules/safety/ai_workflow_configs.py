"""安全模块独立 AI 工作流配置（fallback 硬编码）。

从 app/platform/integrations/ai/prompts.py 的 STANDALONE_WORKFLOW_CONFIG
中迁移安全模块专属配置到此文件，避免跨边界修改平台层代码。

使用方式：
    from app.modules.safety.ai_workflow_configs import SAFETY_WORKFLOW_CONFIGS
    config = SAFETY_WORKFLOW_CONFIGS.get("hazard-identification-export", {})
"""

from typing import Any

SAFETY_WORKFLOW_CONFIGS: dict[str, dict[str, Any]] = {
    "hazard-identification-export": {
        "name": "AI危险源辨识台账智能导出",
        "input_info": (
            "## 用户输入（第一阶段：解析筛选条件）\n"
            "用户通过自然语言描述要导出哪些危险源辨识记录，例如：\n"
            '- "上月所有重大风险记录"\n'
            '- "生产部的设备相关危险源"\n'
            '- "合成岗位最近三个月的数据"\n'
            '- "一级和二级风险的记录"\n\n'
            "## 查询数据（第二阶段：生成分析报告）\n"
            "系统根据解析结果查询数据库，返回结构化的台账数据摘要：\n"
            "- 记录总数、风险等级分布、部门/岗位分布\n"
            "- 高风险记录详情（一级/二级风险）\n"
            "- 全部记录列表（含编号、部门、岗位、作业活动、危险类型、"
            "固有/残余LEC值及风险等级、现有控制措施、管控层级、责任人等）"
        ),
        "work_rules": (
            "## 第一阶段：解析筛选条件\n"
            "将用户的自然语言查询转换为结构化的危险源辨识台账筛选条件。\n\n"
            "可用筛选字段：\n"
            "- department: 部门名称\n"
            "- position: 岗位名称\n"
            "- risk_level: level_1(重大)/level_2(较大)/level_3(一般)/level_4(低)\n"
            "- date_from / date_to: YYYY-MM-DD\n"
            "- keyword: 模糊搜索关键词\n\n"
            "约束：无法识别的字段设为 null；正确计算时间表达"
            "（今天、本周、上月等）；只返回 JSON。\n\n"
            "## 第二阶段：生成分析报告\n"
            "根据查询结果生成一份专业的危险源辨识台账分析报告。\n\n"
            "报告结构：\n"
            "1. **报告概述**：筛选条件、时间范围、记录总数\n"
            "2. **风险分布分析**：按部门/岗位/风险等级统计\n"
            "3. **重点风险项**：逐条列出高风险（一级/二级）记录，评估控制措施充分性\n"
            "4. **管控措施现状**：工程/管理/PPE/应急措施的覆盖情况\n"
            "5. **改进建议**：基于数据的安全管理建议\n\n"
            "约束：中文撰写、数据准确不编造、表格使用 HTML table、标题 h2/h3"
        ),
        "output_format": (
            "## 第一阶段输出（JSON筛选条件 — 仅 parse 阶段使用）\n"
            '{"department":null,"position":null,"risk_level":null,'
            '"date_from":null,"date_to":null,"keyword":null,'
            '"explanation":"用中文简述你理解的筛选条件"}\n\n'
            "## 第二阶段输出（完整 HTML 文档 — 仅 format 阶段使用）\n"
            "当前阶段请忽略第一阶段 JSON，直接输出 HTML。\n"
            "样式：A3横向(420mm×297mm)、正文9pt/h2:13pt/h3:11pt、"
            "文字#333、表头背景#5645D4白色文字加粗、表格边框0.4pt solid #ddd、"
            "斑马纹#f7f6fb(奇数行#f7f6fb, 偶数行#fff)、"
            "风险标签色(一级红/二级橙/三级蓝/四级绿)、"
            "font-family: 'SimHei','SimSun','Microsoft YaHei',sans-serif; "
            "@page{size:A3 landscape;margin:10mm}。"
            "**重要**：表格列数较多时（>10列），使用 font-size:7.5pt + padding:2px 3px "
            "确保所有列能在一页内显示。使用 style 属性内联样式控制表格紧凑排版。"
        ),
        "reference_docs": {
            "text": "",
            "attachments": [],
        },
    },
}
