from __future__ import annotations

import logging
import uuid
from typing import Any

from app.core.llm import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
    llm_client,
)
from app.modules.quality.models import Deviation

logger = logging.getLogger(__name__)


async def analyze_deviation_async(deviation_id: uuid.UUID, user_id: str) -> Any:
    """Backward-compatible wrapper around unified quality AI service."""
    from app.modules.quality.service.quality_ai import analyze_deviation_async as _run

    await _run(deviation_id, user_id)


async def analyze_deviation_sync(deviation: Deviation) -> dict[str, Any] | None:
    """Backward-compatible sync wrapper using unified prompt/output structure."""
    from app.modules.quality.service.quality_ai import (
        QUALITY_AI_RESPONSE_KEYS,
        _build_deviation_snapshot,
        _deviation_prompt,
        _normalize_result,
    )

    try:
        raw = await llm_client.chat_json(
            [
                {
                    "role": "user",
                    "content": _deviation_prompt(
                        _build_deviation_snapshot(deviation), "deviation_analysis"
                    ),
                }
            ],
            expected_keys=QUALITY_AI_RESPONSE_KEYS,
            temperature=0.2,
        )
        return _normalize_result(raw)
    except LLMConfigError:
        logger.warning("AI 服务尚未配置，偏差 AI 分析跳过")
        return None
    except LLMRateLimitError:
        logger.warning("LLM 速率限制，AI 分析跳过")
        return None
    except LLMOutputError:
        logger.exception("LLM 输出格式错误，AI 分析失败")
        return None
    except LLMProviderError:
        logger.exception("LLM 服务调用失败，AI 分析不可用")
        return None
