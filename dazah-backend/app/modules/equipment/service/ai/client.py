"""AI 客户端 — 使用 core.llm 统一客户端。"""

from app.core.llm import llm_client, LLMProviderError


class AIAnalysisError(Exception):
    """AI 分析异常。"""

    def __init__(self, message: str, raw_response: str | None = None):
        self.message = message
        self.raw_response = raw_response
        super().__init__(message)

    def __str__(self) -> str:
        if self.raw_response:
            return f"{self.message} (raw: {self.raw_response[:200]})"
        return self.message


async def analyze_image(
    image_base64: str,
    image_mime_type: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.1,
) -> str:
    """发送多模态请求，返回 AI 响应文本。

    Args:
        image_base64: 图片的 base64 编码（不含 data:xxx;base64, 前缀）
        image_mime_type: 图片 MIME 类型，如 image/jpeg
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        temperature: 温度参数
    """
    # Combine system and user prompts for vision API
    combined_prompt = f"{system_prompt}\n\n{user_prompt}"
    
    try:
        return await llm_client.chat_vision(
            text_prompt=combined_prompt,
            image_urls=[f"data:{image_mime_type};base64,{image_base64}"],
            temperature=temperature,
        )
    except LLMProviderError as e:
        raise AIAnalysisError(f"AI API 返回错误 (HTTP {e.status_code}): {e.raw_response or ''}") from e


async def parse_correction(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.1,
) -> str:
    """发送纯文本修正请求，返回 AI 响应文本。

    Args:
        system_prompt: 系统提示词
        user_prompt: 用户提示词（含当前结果和修改说明）
        temperature: 温度参数
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    
    try:
        return await llm_client.chat(
            messages=messages,
            response_format="json_object",
            temperature=temperature,
        )
    except LLMProviderError as e:
        raise AIAnalysisError(f"AI API 返回错误 (HTTP {e.status_code}): {e.raw_response or ''}") from e
