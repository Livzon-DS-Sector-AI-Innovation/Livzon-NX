"""HR AI 聊天流式 SSE 端点。

集成了 Function Calling 代理循环：LLM 自主调用 HR 数据查询工具，获取真实数据后流式回复。
"""

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.llm import LLMConfigError, LLMProviderError, LLMRateLimitError
from app.modules.hr.ai_agent_service import run_agent_loop
from app.modules.hr.ai_chat_service import build_hr_system_prompt

logger = logging.getLogger(__name__)

router = APIRouter()


# ── 请求模型 ──────────────────────────────────────


class ChatRequest(BaseModel):
    """聊天请求"""

    messages: list[dict[str, Any]] = Field(
        ..., description="对话消息列表，每条消息含 role 和 content"
    )
    page_context: dict[str, Any] | None = Field(
        default=None,
        description="前端页面上下文，如 { page: 'profile', ... }",
    )


# ── SSE 工具 ──────────────────────────────────────


def _sse(data: dict[str, Any]) -> str:
    """将 dict 序列化为 SSE data 行。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── 端点 ──────────────────────────────────────────


@router.post("/ai/chat/stream", summary="HR AI 流式聊天（含数据查询）")
async def chat_stream(
    request: Request,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    """HR AI 智能聊天端点。

    流程：
    1. LLM 分析用户问题，判断是否需要调用工具查询 HR 数据
    2. 如需数据 → 自动调用对应工具（查员工/统计/合同/培训等）
    3. 拿到真实数据后 → LLM 分析并流式回复

    SSE 事件类型：
    - {"status": "正在查询..."}  — 工具执行状态
    - {"content": "..."}         — 回复文本
    - {"reasoning_content": "..."} — 思考过程
    - {"done": true}             — 流结束
    """
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    # 构建系统提示词（含工具使用指引 + 页面上下文）
    system_prompt = build_hr_system_prompt(body.page_context)

    logger.info(
        "HR AI agent chat started",
        extra={
            "msg_count": len(body.messages),
            "page": body.page_context.get("page") if body.page_context else None,
        },
    )

    async def event_stream() -> Any:
        try:
            async for chunk in run_agent_loop(
                session=db,
                messages=body.messages,
                system_prompt=system_prompt,
            ):
                if chunk["type"] == "status":
                    # 状态提示
                    yield _sse({"status": chunk["text"]})
                elif chunk["type"] == "reasoning":
                    yield _sse({"reasoning_content": chunk["text"]})
                elif chunk["type"] == "content":
                    yield _sse({"content": chunk["text"]})
                elif chunk.get("type") == "done":
                    yield _sse({"done": True})
                    break

            logger.info("HR AI agent chat completed")

        except LLMRateLimitError:
            logger.warning("LLM rate limit exceeded")
            yield _sse({"content": "抱歉，AI 服务当前请求过于频繁，请稍后再试。"})
            yield _sse({"done": True})

        except (LLMProviderError, LLMConfigError):
            logger.error("LLM provider error", exc_info=True)
            yield _sse({"content": "AI 服务暂时不可用，请检查 LLM 配置或稍后重试。"})
            yield _sse({"done": True})

        except Exception:
            logger.exception("Unexpected error in HR AI agent chat")
            yield _sse({"content": "AI 服务出现未知错误，请联系管理员。"})
            yield _sse({"done": True})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
