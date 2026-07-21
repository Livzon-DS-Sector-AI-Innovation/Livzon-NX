"""文献解析服务 - 使用 AI 分析合成路线"""

import json
from typing import Any
from app.modules.research.llm_service import call_llm


async def parse_literature(text: str) -> dict[str, Any]:
    """解析文献内容，提取合成路线
    
    Args:
        text: 文献文本内容
        
    Returns:
        包含候选路线、实验方案等的字典
    """
    prompt = build_literature_analysis_prompt(text)
    result = await call_llm(prompt)
    return result


def build_literature_analysis_prompt(text: str) -> str:
    """构建文献分析 prompt"""
    return f"""你是一个原料药合成工艺专家。请分析以下文献内容，提取合成路线信息。

## 任务
1. 识别文献中描述的所有合成路线
2. 提取每条路线的详细步骤、收率、反应条件
3. 评估每条路线的优缺点
4. 推荐最优路线

## 分析要求

### 路线提取
- 识别所有独立的合成路线（通常标记为 Route 1, Route 2 等）
- 提取每条路线的步骤数、总收率
- 记录关键反应步骤和条件

### 物料识别
- 识别起始物料（Starting Materials）
- 识别关键试剂和催化剂
- 记录溶剂和反应条件

### 评估维度
对每条路线进行以下评估：
1. **反应安全性**：是否涉及高危反应（如叠氮化、高压氢化等）
2. **放大可行性**：是否适合工业化放大
3. **质量可控性**：杂质是否容易控制
4. **成本经济性**：原料成本、步骤数、总收率

## 输出格式

返回 JSON 格式，结构如下：

{{
  "candidate_routes": [
    {{
      "id": "route-1",
      "name": "路线1：[路线名称]",
      "steps": 4,
      "total_yield": 62,
      "starting_materials": ["物料1", "物料2"],
      "key_step": "步骤X：[关键反应描述]",
      "advantages": ["优点1", "优点2"],
      "risks": ["风险1", "风险2"],
      "is_recommended": true,
      "description": "路线简述",
      "文献页码": "P.XX-XX",
      "反应条件": "溶剂，温度，时间，特殊条件"
    }}
  ],
  "experiment_plans": [
    {{
      "route_id": "route-1",
      "route_name": "路线1：[路线名称]",
      "steps": [
        {{
          "step_no": 1,
          "description": "步骤描述",
          "reagents": ["试剂1", "试剂2"],
          "conditions": "反应条件",
          "expected_yield": 85,
          "duration": "Xh",
          "notes": "注意事项"
        }}
      ],
      "analysis_methods": [
        {{
          "name": "HPLC",
          "purpose": "纯度检测",
          "method": "检测方法详情",
          "equipment": "设备名称"
        }}
      ],
      "materials": [
        {{
          "name": "物料名称",
          "cas_number": "CAS号",
          "quantity": "用量",
          "supplier": "推荐供应商",
          "purity": "纯度要求",
          "storage": "储存条件",
          "lead_time": "到货周期"
        }}
      ],
      "equipment": ["设备1", "设备2"],
      "safety_notes": ["安全注意事项1", "安全注意事项2"],
      "estimated_duration": "预计总时长"
    }}
  ]
}}

## 文献内容

{text}

请只返回 JSON，不要其他解释。确保所有字段都完整填写。"""


async def analyze_literature_with_ai(text: str) -> dict[str, Any]:
    """使用 AI 分析文献（对外接口）
    
    Args:
        text: 文献文本内容
        
    Returns:
        解析结果，包含 candidate_routes 和 experiment_plans
    """
    try:
        result = await parse_literature(text)
        
        # 确保返回格式正确
        if "candidate_routes" not in result:
            result["candidate_routes"] = []
        if "experiment_plans" not in result:
            result["experiment_plans"] = []
            
        return result
    except Exception as e:
        # 如果 AI 解析失败，返回空结果
        print(f"AI 文献解析失败: {e}")
        return {
            "candidate_routes": [],
            "experiment_plans": [],
            "error": str(e)
        }
