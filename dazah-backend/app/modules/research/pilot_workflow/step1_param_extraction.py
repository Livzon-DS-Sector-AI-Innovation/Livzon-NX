"""步骤1：工艺参数提取与风险初判（LLM驱动）"""

import json
import logging
from pathlib import Path

from app.modules.research.llm_service import call_llm
from app.modules.research.models import PilotWorkflow

logger = logging.getLogger(__name__)


def _read_document_text(document_path: str | None) -> str:
    """读取上传文档的文本内容"""
    if not document_path:
        return ""

    path = Path(document_path)
    if not path.exists():
        return ""

    suffix = path.suffix.lower()

    if suffix == ".txt":
        return path.read_text(encoding="utf-8")

    if suffix == ".docx":
        try:
            from docx import Document
            doc = Document(str(path))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            logger.warning(f"Failed to read docx: {e}")
            return ""

    if suffix == ".pdf":
        try:
            import pdfplumber
            text_parts = []
            with pdfplumber.open(str(path)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
            return "\n".join(text_parts)
        except Exception as e:
            logger.warning(f"Failed to read pdf: {e}")
            return ""

    return ""


def _build_prompt(document_text: str, extra_context: dict | None) -> str:
    """构建参数提取的 LLM prompt"""
    context_section = ""
    if extra_context:
        ctx_json = json.dumps(extra_context, ensure_ascii=False, indent=2)
        context_section = f"\n## 额外上下文信息\n{ctx_json}\n"

    prompt_start = "你是一个制药工艺放大专家。"
    prompt_start += "请从以下工艺文档中提取关键工艺参数，并进行初步风险评估。"
    return f"""{prompt_start}

## 任务
1. 提取所有关键工艺参数（温度、压力、搅拌速度、反应时间、溶剂用量、加料速度、pH值等）
2. 对每个参数标注数值、单位、范围
3. 标记是否为关键工艺参数(CPP)
4. 进行初步风险评估：
   - 放热反应风险
   - 高压/高温风险
   - 有毒溶剂使用
   - 易燃易爆风险
   - 其他安全隐患

## 工艺文档内容
{document_text}
{context_section}

## 输出格式
返回 JSON，结构如下：
{{
  "parameters": [
    {{
      "name": "参数名称",
      "value": "数值或范围",
      "unit": "单位",
      "is_cpp": true/false,
      "category": "温度/压力/搅拌/时间/溶剂/加料/pH/其他",
      "notes": "备注"
    }}
  ],
  "risk_flags": [
    {{
      "risk_type": "风险类型（放热/高压/有毒/易燃/其他）",
      "severity": "高/中/低",
      "description": "风险描述",
      "affected_parameters": ["相关参数名"]
    }}
  ],
  "solvents": [
    {{
      "name": "溶剂名称",
      "ich_class": "Class 1/2/3/Unlisted",
      "quantity": "用量"
    }}
  ],
  "summary": "工艺概述"
}}

请只返回 JSON，不要其他解释。"""


async def execute_param_extraction(
    step_input: dict,
    workflow: PilotWorkflow,
) -> dict:
    """执行参数提取与风险初判"""
    # 读取文档
    document_text = _read_document_text(workflow.input_document_path)

    if not document_text:
        # 如果没有文档，使用 input_context 作为输入
        document_text = json.dumps(
            workflow.input_context or {},
            ensure_ascii=False,
            indent=2,
        )

    prompt = _build_prompt(document_text, workflow.input_context)

    # 调用 LLM
    result = await call_llm(prompt)

    # 确保结果是 dict
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            result = {"raw_text": result}

    return {
        "step": "param_extraction",
        "parameters": result.get("parameters", []),
        "risk_flags": result.get("risk_flags", []),
        "solvents": result.get("solvents", []),
        "summary": result.get("summary", ""),
    }
