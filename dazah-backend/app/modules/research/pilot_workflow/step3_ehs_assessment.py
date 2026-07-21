"""步骤3：EHS与工艺安全评估（LLM驱动）"""

import json
import logging

from app.modules.research.llm_service import call_llm
from app.modules.research.models import PilotWorkflow

logger = logging.getLogger(__name__)


def _build_prompt(
    param_result: dict,
    scale_up_result: dict,
    workflow: PilotWorkflow,
) -> str:
    """构建 EHS 评估的 LLM prompt"""
    prompt_start = "你是一个制药工程 EHS（环境、健康、安全）专家。"
    prompt_start += "请基于以下工艺参数和放大评估结果，进行全面的工艺安全评估。"
    return f"""{prompt_start}

## 产品信息
- 产品名称：{workflow.product_name}
- 放大倍数：{workflow.scale_up_ratio}倍
- 设备类型：{workflow.equipment_type}
- 设备容积：{workflow.equipment_volume}L

## 步骤1：工艺参数提取结果
{json.dumps(param_result, ensure_ascii=False, indent=2)}

## 步骤2：工程计算与放大评估结果
{json.dumps(scale_up_result, ensure_ascii=False, indent=2)}

## 评估要求
请从以下维度评估安全风险：

1. **热失控风险**：基于放热反应、散热能力变化、温度控制难度
2. **有毒物质风险**：基于溶剂毒性、气体释放、接触危害
3. **燃爆风险**：基于溶剂闪点、粉尘爆炸可能性、静电风险
4. **压力风险**：基于反应压力、设备承压能力
5. **操作安全**：基于放大后的操作难度、人工干预需求

## 输出格式
返回 JSON：
{{
  "assessments": [
    {{
      "dimension": "评估维度",
      "risk_level": "高/中/低",
      "description": "风险描述",
      "evidence": "判断依据",
      "measures": ["防护措施1", "防护措施2"]
    }}
  ],
  "overall_risk_level": "高/中/低",
  "critical_safety_items": ["关键安全事项1", "关键安全事项2"],
  "ppe_requirements": ["个人防护装备要求"],
  "emergency_measures": ["应急措施建议"],
  "recommendations": ["总体建议"]
}}

请只返回 JSON，不要其他解释。"""


async def execute_ehs_assessment(
    step_input: dict,
    workflow: PilotWorkflow,
) -> dict:
    """执行 EHS 与工艺安全评估"""
    # 从累积的 step_input 中提取前两步的结果
    param_result = step_input.get("param_extraction", {})
    scale_up_result = step_input.get("scale_up_calc", {})

    prompt = _build_prompt(
        param_result=param_result,
        scale_up_result=scale_up_result,
        workflow=workflow,
    )

    result = await call_llm(prompt)

    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            result = {"raw_text": result}

    return {
        "step": "ehs_assessment",
        "assessments": result.get("assessments", []),
        "overall_risk_level": result.get("overall_risk_level", "中"),
        "critical_safety_items": result.get("critical_safety_items", []),
        "ppe_requirements": result.get("ppe_requirements", []),
        "emergency_measures": result.get("emergency_measures", []),
        "recommendations": result.get("recommendations", []),
    }
