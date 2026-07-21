from __future__ import annotations

import logging
import uuid

from app.core.llm import llm_client
from app.modules.quality.models import Deviation

logger = logging.getLogger(__name__)

async def analyze_deviation_async(deviation_id: uuid.UUID, user_id: str):
    """Backward-compatible wrapper around unified quality AI service."""
    from app.modules.quality.service.quality_ai import analyze_deviation_async as _run

    await _run(deviation_id, user_id)


async def analyze_deviation_sync(deviation: Deviation) -> dict | None:
    """Backward-compatible sync wrapper using unified prompt/output structure."""
    from app.modules.quality.service.quality_ai import (
        _build_deviation_snapshot,
        _deviation_prompt,
        _normalize_result,
        QUALITY_AI_RESPONSE_KEYS,
    )

    try:
        raw = await llm_client.chat_json(
            [{"role": "user", "content": _deviation_prompt(_build_deviation_snapshot(deviation), "deviation_analysis")}],
            expected_keys=QUALITY_AI_RESPONSE_KEYS,
            temperature=0.2,
        )
        return _normalize_result(raw)
    except Exception:
        logger.exception("AI analysis failed")
        return None
