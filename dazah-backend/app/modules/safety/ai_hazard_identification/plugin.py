"""AI隐患识别插件 — 核心引擎。

将设计方案中的四阶段流程实现为可独立运行、可测试的插件：
  阶段一：输入采集与预处理
  阶段二：多模态AI分析
  阶段三：规则匹配与推理
  阶段四：输出生成

用法:
    from app.modules.safety.ai_hazard_identification import AIHazardIdentifier

    plugin = AIHazardIdentifier()

    input_data = HazardIdentificationInput(
        description="防爆电箱堵头缺失",
        department="生产部",
        location="合成车间一楼",
        defect_photos=["https://..."],
    )

    output = await plugin.identify(input_data)
    print(output.key_defect)
    print(output.hazard_level)
"""

from __future__ import annotations

import json as _json
import logging
import time
from typing import Any

from app.core.llm import llm_client
from app.modules.safety.ai_hazard_identification.prompts import (
    SYSTEM_ROLE,
    build_context_text,
    build_full_prompt,
    build_vision_context_text,
    get_expected_keys,
)
from app.modules.safety.ai_hazard_identification.rules import (
    RuleEngine,
    auto_correct,
)
from app.modules.safety.ai_hazard_identification.schemas import (
    HazardIdentificationInput,
    HazardIdentificationOutput,
    PluginConfig,
    RectificationSuggestion,
)

logger = logging.getLogger(__name__)


class IdentificationError(Exception):
    """AI 识别失败异常。"""

    pass


class AIHazardIdentifier:
    """AI隐患识别插件 — 稳定、可复现、可独立测试。

    设计原则：
    - 低温度（0.05）保证输出可复现
    - 统一使用系统 LLM 配置
    - 规则引擎后处理确保质量
    - 完整的日志记录用于审计

    Args:
        config: 插件运行时配置（可选，使用默认值）

    Example:
        >>> plugin = AIHazardIdentifier()
        >>> output = await plugin.identify(HazardIdentificationInput(
        ...     description="防爆电箱堵头缺失",
        ...     department="生产部",
        ... ))
    """

    def __init__(
        self,
        config: Any | None = None,
    ) -> None:
        if isinstance(config, PluginConfig) or config is None:
            self.config = config or PluginConfig()
            self._llm: Any = llm_client
        else:
            self.config = PluginConfig()
            self._llm = config
        self.rule_engine = RuleEngine()

    # ── 公共 API ──

    async def identify(
        self,
        input_data: HazardIdentificationInput,
    ) -> HazardIdentificationOutput:
        """执行完整的 AI 隐患识别流程。

        Args:
            input_data: 标准化输入（含描述、图片、部门等上下文）

        Returns:
            经过规则验证和自动修正的识别结果

        Raises:
            IdentificationError: 识别失败（AI 调用失败或输出不合法）
        """
        start_time = time.monotonic()

        # ── 阶段一：输入预处理 ──
        logger.info("阶段一：输入预处理 — hazard_no=%s", input_data.hazard_no)
        has_photos = bool(input_data.defect_photos)

        # ── 阶段二：AI 分析 ──
        logger.info("阶段二：AI 分析 — has_photos=%s", has_photos)

        if has_photos and self.config.enable_vision:
            raw_output = await self._call_vision_ai(input_data)
        else:
            raw_output = await self._call_text_ai(input_data)

        # ── 阶段三：解析 & 验证 ──
        logger.info("阶段三：解析输出并规则验证")
        output = self._parse_output(raw_output)

        # 自动修正
        output = auto_correct(output)

        # 规则验证
        validation = self.rule_engine.validate(input_data, output)
        if not validation.is_valid:
            error_detail = "; ".join(validation.errors)
            if self.config.strict_mode:
                raise IdentificationError(
                    f"AI 输出验证失败: {error_detail}\n"
                    "原始输出: "
                    f"{_json.dumps(raw_output, ensure_ascii=False, default=str)[:500]}"
                )
            else:
                logger.warning(
                    "AI 输出验证失败（非严格模式，继续返回）: %s", error_detail
                )

        # ── 阶段四：返回结果 ──
        elapsed = time.monotonic() - start_time
        logger.info(
            "识别完成 — hazard_no=%s type=%s category=%s level=%s elapsed=%.2fs",
            input_data.hazard_no,
            output.hazard_type.value,
            output.hazard_category.value,
            output.hazard_level.value,
            elapsed,
        )

        return output

    async def identify_batch(
        self,
        inputs: list[HazardIdentificationInput],
    ) -> list[HazardIdentificationOutput]:
        """批量识别（顺序执行，不并发以避免 API 限流）。

        Args:
            inputs: 多条隐患记录的输入

        Returns:
            与输入顺序对应的识别结果列表
        """
        results: list[HazardIdentificationOutput] = []
        for i, input_data in enumerate(inputs):
            logger.info(
                "批量识别 [%d/%d]: %s", i + 1, len(inputs), input_data.hazard_no
            )
            try:
                result = await self.identify(input_data)
                results.append(result)
            except IdentificationError as e:
                logger.error("批量识别 [%d/%d] 失败: %s", i + 1, len(inputs), e)
                raise
        return results

    # ── 内部方法 ──

    async def _call_text_ai(
        self, input_data: HazardIdentificationInput
    ) -> dict[str, Any]:
        """纯文本模式 AI 调用。"""
        context = build_context_text(
            hazard_no=input_data.hazard_no,
            description=input_data.description,
            department=input_data.department,
            location=input_data.location,
            discovered_by_name=input_data.discovered_by_name,
            discovered_at=(
                input_data.discovered_at.strftime("%Y-%m-%d %H:%M")
                if input_data.discovered_at
                else None
            ),
        )

        prompt = build_full_prompt(context, vision_mode=False, include_fewshot=True)
        expected_keys = get_expected_keys()

        messages = [
            {"role": "system", "content": SYSTEM_ROLE},
            {"role": "user", "content": prompt},
        ]

        try:
            if hasattr(self._llm, "chat_json"):
                result = await self._llm.chat_json(
                    messages=messages,
                    expected_keys=expected_keys,
                    temperature=self.config.temperature,
                )
            else:
                result = await self._llm.chat_parsed(
                    messages,
                    expected_keys=expected_keys,
                    temperature=self.config.temperature,
                )
            if not isinstance(result, dict):
                raise IdentificationError("AI 文本分析返回的不是 JSON 对象")
            return result
        except Exception as e:
            logger.error("文本 AI 调用失败: %s", e)
            raise IdentificationError(f"AI 文本分析失败: {e}") from e

    async def _call_vision_ai(
        self, input_data: HazardIdentificationInput
    ) -> dict[str, Any]:
        """多模态 AI 调用（带图片）。"""
        context = build_vision_context_text(
            hazard_no=input_data.hazard_no,
            description=input_data.description,
            department=input_data.department,
            location=input_data.location,
        )

        expected_keys = get_expected_keys()

        try:
            prompt = build_full_prompt(context, vision_mode=True, include_fewshot=True)
            if hasattr(self._llm, "chat_vision_json"):
                result = await self._llm.chat_vision_json(
                    text_prompt=prompt,
                    image_urls=input_data.defect_photos,
                    expected_keys=expected_keys,
                    temperature=self.config.temperature,
                )
            else:
                result = await self._llm.chat_vision_parsed(
                    prompt,
                    input_data.defect_photos,
                    expected_keys=expected_keys,
                    temperature=self.config.temperature,
                )
            if not isinstance(result, dict):
                raise IdentificationError("AI 视觉分析返回的不是 JSON 对象")
            return result

        except Exception as e:
            logger.error("多模态 AI 调用失败: %s", e)
            raise IdentificationError(f"AI 视觉分析失败: {e}") from e

    def _parse_output(self, raw: dict[str, Any]) -> HazardIdentificationOutput:
        """将 AI 返回的字典解析为强类型输出。"""
        try:
            # 解析枚举
            from app.modules.safety.ai_hazard_identification.schemas import (
                HazardCategoryEnum,
                HazardLevelEnum,
                HazardTypeEnum,
            )

            # 如果 rectification_suggestion 是字符串（某些模型可能这样返回），做兼容处理
            rs = raw.get("rectification_suggestion", {})
            if isinstance(rs, str):
                # 尝试 JSON 解析
                try:
                    rs = _json.loads(rs)
                except (_json.JSONDecodeError, TypeError):
                    rs = {"immediate": rs, "short_term": "", "long_term": ""}

            return HazardIdentificationOutput(
                key_defect=raw.get("key_defect", ""),
                hazard_type=HazardTypeEnum(raw.get("hazard_type", "")),
                hazard_category=HazardCategoryEnum(raw.get("hazard_category", "")),
                hazard_level=HazardLevelEnum(raw.get("hazard_level", "")),
                rectification_suggestion=RectificationSuggestion(
                    immediate=rs.get("immediate", ""),
                    short_term=rs.get("short_term", ""),
                    long_term=rs.get("long_term", ""),
                ),
                major_hazard_basis=raw.get("major_hazard_basis", ""),
                confidence=raw.get("confidence")
                if self.config.enable_reasoning
                else None,
                reasoning=raw.get("reasoning")
                if self.config.enable_reasoning
                else None,
            )
        except (ValueError, KeyError, TypeError) as e:
            raise IdentificationError(
                f"AI 输出解析失败: {e}\n"
                f"原始输出: {_json.dumps(raw, ensure_ascii=False, default=str)[:500]}"
            ) from e
