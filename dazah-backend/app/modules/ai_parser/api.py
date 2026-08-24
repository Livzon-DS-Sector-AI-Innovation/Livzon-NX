"""AI解析API路由"""

from typing import Any

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.core.llm import (
    LLMConfigError,
    LLMError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
    llm_client,
)
from app.core.response import success_response

router = APIRouter()


async def _call_parser_llm(prompt: str) -> dict[str, Any]:
    """Call the platform LLM service and map failures to safe HTTP errors."""
    try:
        return await llm_client.chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "你是一个专业的制药工艺数据提取助手，"
                        "擅长从文本中提取关键信息。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            expected_keys=None,
            temperature=0.1,
        )
    except LLMConfigError as exc:
        raise HTTPException(status_code=503, detail="AI解析服务未配置") from exc
    except LLMRateLimitError as exc:
        raise HTTPException(
            status_code=429, detail="AI解析服务繁忙，请稍后重试"
        ) from exc
    except (LLMOutputError, LLMProviderError) as exc:
        raise HTTPException(status_code=502, detail="AI解析服务暂不可用") from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail="AI解析服务调用失败") from exc


@router.post("/parse-experiment", summary="AI解析实验记录文件")
async def parse_experiment_record(
    file: UploadFile = File(...),
    parse_type: str = Body(..., embed=True),
) -> JSONResponse:
    """
    AI解析实验记录文件
    支持解析：实验记录、工艺规程、批记录等
    """
    try:
        # 读取文件内容
        content = await file.read()

        # 根据文件类型提取文本
        text_content = ""
        filename = (file.filename or "").lower()
        if filename.endswith(".txt"):
            text_content = content.decode("utf-8")
        elif filename.endswith((".pdf", ".doc", ".docx")):
            # 对于PDF和Word文件，暂时使用文件名作为提示
            # 实际生产中应该使用pdfplumber、python-docx等库
            text_content = f"[文件: {file.filename}]"
        elif filename.endswith((".jpg", ".jpeg", ".png")):
            # 对于图片文件，应该使用OCR
            # 这里暂时返回提示
            text_content = f"[图片文件: {file.filename}，需要OCR识别]"
        else:
            text_content = content.decode("utf-8", errors="ignore")

        # 构建提示词
        if parse_type == "lab_confirmation":
            prompt = f"""请从以下实验记录中提取小试工艺确认的关键信息，返回JSON格式：

实验记录内容：
{text_content}

请提取以下字段（如果存在）：
- batch_no: 批号
- scale_g: 规模（克）
- date: 日期（YYYY-MM-DD格式）
- operator: 操作人
- equipment: 设备
- temperature: 反应温度（包含单位）
- time: 反应时间（包含单位）
- ratio: 投料比例
- other_parameters: 其他参数
- yield_pct: 收率（百分比数值）
- purity_pct: 纯度（百分比数值）
- impurities_pct: 杂质（百分比数值）
- appearance: 外观描述
- observations: 观察记录
- conclusion: 结论

请只返回JSON，不要包含其他说明文字。"""
        else:  # scale_up
            prompt = f"""请从以下实验记录中提取公斤级放大试验的关键信息，返回JSON格式：

实验记录内容：
{text_content}

请提取以下字段（如果存在）：
- batch_no: 批号
- scale_kg: 规模（千克）
- date: 日期（YYYY-MM-DD格式）
- operator: 操作人
- equipment: 设备
- yield_pct: 收率（百分比数值）
- purity_pct: 纯度（百分比数值）
- impurities_pct: 杂质（百分比数值）
- appearance: 外观描述
- comparison_notes: 与小试对比备注

请只返回JSON，不要包含其他说明文字。"""

        parsed_data = await _call_parser_llm(prompt)
        return success_response(data=parsed_data)

    except HTTPException:
        raise
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="文件编码无法解析") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="解析失败") from exc


@router.post("/parse-parameters", summary="AI解析工艺参数文本")
async def parse_process_parameters(
    content: str = Body(..., embed=True),
    parse_type: str = Body(..., embed=True),
) -> JSONResponse:
    """
    AI解析工艺参数文本
    从文本内容中提取工艺参数
    """
    try:
        # 构建提示词（与文件解析类似）
        if parse_type == "lab_confirmation":
            prompt = f"""请从以下文本中提取小试工艺确认的关键信息，返回JSON格式：

文本内容：
{content}

请提取以下字段（如果存在）：
- batch_no: 批号
- scale_g: 规模（克）
- date: 日期（YYYY-MM-DD格式）
- operator: 操作人
- equipment: 设备
- temperature: 反应温度（包含单位）
- time: 反应时间（包含单位）
- ratio: 投料比例
- other_parameters: 其他参数
- yield_pct: 收率（百分比数值）
- purity_pct: 纯度（百分比数值）
- impurities_pct: 杂质（百分比数值）
- appearance: 外观描述
- observations: 观察记录
- conclusion: 结论

请只返回JSON，不要包含其他说明文字。"""
        else:  # scale_up
            prompt = f"""请从以下文本中提取公斤级放大试验的关键信息，返回JSON格式：

文本内容：
{content}

请提取以下字段（如果存在）：
- batch_no: 批号
- scale_kg: 规模（千克）
- date: 日期（YYYY-MM-DD格式）
- operator: 操作人
- equipment: 设备
- yield_pct: 收率（百分比数值）
- purity_pct: 纯度（百分比数值）
- impurities_pct: 杂质（百分比数值）
- appearance: 外观描述
- comparison_notes: 与小试对比备注

请只返回JSON，不要包含其他说明文字。"""

        parsed_data = await _call_parser_llm(prompt)
        return success_response(data=parsed_data)

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="解析失败") from exc
