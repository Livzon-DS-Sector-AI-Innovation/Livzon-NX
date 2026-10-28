"""报修意图的 LLM 解析层：口语消息 → 结构化字段。

设计约束：
- LLM 只负责"归一化"（抽取车间/设备/故障/紧急度），不直接决定业务
  动作——抽取结果仍交给既有的确定性匹配与工单状态机执行；
- 解析失败/超时/未配置 LLM 时返回 None，由规则引擎兜底，报修链路
  的可用性不依赖模型在线。
"""

import logging
from typing import Any

from app.core.llm import LLMError, llm_client

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "你是制药厂设备报修信息抽取器。从用户消息中抽取结构化字段，"
    "只输出一个 JSON 对象：\n"
    '{"workshop": "车间名或代码，如 201一车间 / 201-1，消息里没有则留空",\n'
    ' "equipment": "设备名称，尽量还原完整名称（含空格和序号，'
    '如 下卸料离心机 1），没有则留空",\n'
    ' "fault": "故障现象描述，简明扼要，没有则留空",\n'
    ' "urgency": "紧急 或 普通"}\n'
    "判定规则：\n"
    "- urgency：涉及停机、停产、泄漏、安全隐患或催促用语"
    "（赶紧/马上/立即/快来）判「紧急」，否则「普通」\n"
    "- 只抽取消息实际表达的信息，禁止编造；设备名中的数字序号必须保留\n"
    "不要输出 JSON 以外的任何内容。"
)

_EXPECTED_KEYS = ["workshop", "equipment", "fault", "urgency"]
# 公司网关对长提示词首响应可达 10s+，给足余量；失败回落规则引擎
_TIMEOUT_SECONDS = 15
_MAX_MESSAGE_CHARS = 200


def _build_prompt(workshop_names: list[str] | None) -> str:
    prompt = _SYSTEM_PROMPT
    if workshop_names:
        joined = "、".join(workshop_names)
        prompt += (
            f"\n注册车间清单（workshop 必须从中选择语义最匹配的一个，"
            f"原样输出该名称；都不沾边则留空）：{joined}"
        )
    return prompt


async def parse_repair_intent(
    text: str, workshop_names: list[str] | None = None
) -> dict[str, str] | None:
    """口语报修 → {workshop, equipment, fault, urgency}；不可用时返回 None。"""
    cleaned = text.removeprefix("报修").strip()
    if not cleaned:
        return None
    try:
        data: Any = await llm_client.chat_json(
            [
                {"role": "system", "content": _build_prompt(workshop_names)},
                {"role": "user", "content": cleaned[:_MAX_MESSAGE_CHARS]},
            ],
            expected_keys=_EXPECTED_KEYS,
            temperature=0.0,
            timeout=_TIMEOUT_SECONDS,
            enable_thinking=False,
        )
    except LLMError:
        logger.info("报修 LLM 解析未生效（模型输出异常），走规则匹配")
        return None
    except Exception:
        logger.warning("报修 LLM 解析调用失败，走规则匹配", exc_info=True)
        return None

    intent = {
        key: str(data.get(key, "") or "").strip() for key in _EXPECTED_KEYS
    }
    intent["urgency"] = "紧急" if "紧" in intent["urgency"] else "普通"
    if not any(intent[key] for key in ("workshop", "equipment", "fault")):
        return None
    logger.info("报修 LLM 解析: %s", intent)
    return intent
