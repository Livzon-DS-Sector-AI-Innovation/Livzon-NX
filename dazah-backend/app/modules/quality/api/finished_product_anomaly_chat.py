"""成品异常 AI 聊天端点（SSE 流式，含数据查询工具）。"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.llm import LLMConfigError, LLMProviderError, LLMRateLimitError
from app.modules.quality.service.finished_product_anomaly_chat import (
    build_chat_system_prompt,
    run_anomaly_chat_loop,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class AnomalyChatMessage(BaseModel):
    role: str = Field(description="消息角色：user/assistant")
    content: str = Field(description="消息内容")


class AnomalyChatRequest(BaseModel):
    messages: list[AnomalyChatMessage] = Field(default_factory=list)
    year: int | None = Field(default=None, description="限定分析的年份（可选）")


def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post(
    "/finished-product-anomaly/chat/stream",
    summary="成品异常 AI 流式聊天（查询异常数据 + 不合格项分析）",
)
async def anomaly_chat_stream(
    body: AnomalyChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    """成品异常 AI 助手聊天。

    流程：LLM 判断是否需要查询成品异常数据 → 调用工具（记录明细/聚合统计）
    → 基于真实数据流式回答。SSE 事件：status/content/reasoning_content/done。
    """
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    if not body.messages:
        raise AppException(status_code=400, message="消息不能为空")

    system_prompt = {
        "role": "system",
        "content": build_chat_system_prompt()
        + (f"\n【当前限定年份】{body.year}年（用户从仪表盘筛选）。" if body.year else ""),
    }
    messages = [
        {"role": message.role, "content": message.content}
        for message in body.messages
        if message.role in ("user", "assistant") and message.content
    ]

    logger.info(
        "Finished product anomaly AI chat started",
        extra={"module_name": "quality", "msg_count": len(messages), "year": body.year},
    )

    async def event_stream() -> Any:
        try:
            # 开场心跳：确保响应头与首个事件立即下发（复杂问题整体需 1-3 分钟）
            yield _sse({"status": "已连接，AI 正在理解问题（多步查询约需 1-3 分钟）…"})
            async for chunk in run_anomaly_chat_loop(
                db=db,
                messages=messages,
                system_prompt=system_prompt,
            ):
                if chunk["type"] == "status":
                    yield _sse({"status": chunk["text"]})
                elif chunk["type"] == "reasoning":
                    yield _sse({"reasoning_content": chunk["text"]})
                elif chunk["type"] == "content":
                    yield _sse({"content": chunk["text"]})
                elif chunk["type"] == "done":
                    yield _sse({"done": True})
        except LLMRateLimitError:
            yield _sse({"content": "AI 服务请求过于频繁，请稍后再试。"})
            yield _sse({"done": True})
        except LLMConfigError:
            yield _sse(
                {
                    "content": "AI 服务尚未配置，请先在 系统管理 → AI 模型配置 中配置并启用 text 类型模型。"
                }
            )
            yield _sse({"done": True})
        except LLMProviderError:
            logger.exception("Anomaly AI chat provider error")
            yield _sse({"content": "AI 服务暂时不可用，请检查 LLM 配置或稍后重试。"})
            yield _sse({"done": True})
        except Exception:
            logger.exception("Anomaly AI chat unknown error")
            yield _sse({"content": "AI 服务出现未知错误，请联系管理员。"})
            yield _sse({"done": True})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
    )
