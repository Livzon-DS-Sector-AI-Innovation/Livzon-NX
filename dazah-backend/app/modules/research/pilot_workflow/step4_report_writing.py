"""步骤4：生产数据分析与报告撰写（LLM驱动）"""

import json
import logging

from app.modules.research.llm_service import call_llm
from app.modules.research.models import PilotWorkflow

logger = logging.getLogger(__name__)


def _build_prompt(
    all_results: dict,
    workflow: PilotWorkflow,
) -> str:
    """构建报告撰写的 LLM prompt"""
    prompt_start = "你是一个制药工艺报告撰写专家。"
    prompt_start += (
        "请基于以下中试研究的全部分析结果，"
        "撰写一份完整的中试放大报告。"
    )
    return f"""{prompt_start}

## 产品基本信息
- 产品名称：{workflow.product_name}
- 放大倍数：{workflow.scale_up_ratio}倍
- 设备类型：{workflow.equipment_type}
- 设备容积：{workflow.equipment_volume}L

## 分析结果汇总

### 1. 工艺参数提取与风险初判
{json.dumps(all_results.get("param_extraction", {}), ensure_ascii=False, indent=2)}

### 2. 工程计算与放大评估
{json.dumps(all_results.get("scale_up_calc", {}), ensure_ascii=False, indent=2)}

### 3. EHS与工艺安全评估
{json.dumps(all_results.get("ehs_assessment", {}), ensure_ascii=False, indent=2)}

## 报告要求
请撰写一份符合 GMP 规范的中试放大报告，包含以下章节：

1. **概述**：产品简介、放大目的、放大规模
2. **工艺参数汇总**：所有关键工艺参数列表（含范围和控制要求）
3. **放大评估结论**：传热、混合、设备适配性的评估结论
4. **风险评估**：各类风险等级和应对措施
5. **安全与防护**：EHS 要求、个人防护、应急措施
6. **操作建议**：中试操作的关键注意事项
7. **结论与建议**：总体可行性结论和后续建议

## 输出格式
返回 JSON：
{{
  "report_title": "报告标题",
  "sections": [
    {{
      "title": "章节标题",
      "content": "章节内容（Markdown格式）"
    }}
  ],
  "conclusion": "总体结论",
  "recommendations": ["后续建议"],
  "appendix": {{
    "parameters": "参数汇总表",
    "risk_summary": "风险汇总表",
    "equipment": "设备清单"
  }}
}}

请只返回 JSON，不要其他解释。"""


async def execute_report_writing(
    step_input: dict,
    workflow: PilotWorkflow,
) -> dict:
    """执行报告撰写"""
    prompt = _build_prompt(
        all_results=step_input,
        workflow=workflow,
    )

    result = await call_llm(prompt)

    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            result = {"raw_text": result}

    return {
        "step": "report_writing",
        "report_title": result.get("report_title", "中试放大报告"),
        "sections": result.get("sections", []),
        "conclusion": result.get("conclusion", ""),
        "recommendations": result.get("recommendations", []),
        "appendix": result.get("appendix", {}),
    }
