"""AI隐患识别插件 — 安全模块 AI 工作流核心。

基于《AI隐患识别工作流设计方案》，提供：
- AIHazardIdentifier: 核心识别引擎（独立可测试）
- RuleEngine: 输出规则验证器
- 完整的 Prompt 模板体系 + 数据库配置种子
- 输入/输出数据模型（Pydantic v2）

用法:
    from app.modules.safety.ai_hazard_identification import (
        AIHazardIdentifier,
        HazardIdentificationInput,
        PluginConfig,
    )
"""

from app.modules.safety.ai_hazard_identification.plugin import (
    AIHazardIdentifier,
    IdentificationError,
)
from app.modules.safety.ai_hazard_identification.prompts import (
    get_db_seed_config,
    get_expected_keys,
    build_full_prompt,
    build_context_text,
)
from app.modules.safety.ai_hazard_identification.rules import (
    RuleEngine,
    auto_correct,
)
from app.modules.safety.ai_hazard_identification.schemas import (
    HazardCategoryEnum,
    HazardIdentificationInput,
    HazardIdentificationOutput,
    HazardLevelEnum,
    HazardTypeEnum,
    PluginConfig,
    RectificationSuggestion,
    ValidationResult,
)

__all__ = [
    # 核心引擎
    "AIHazardIdentifier",
    "IdentificationError",
    # 规则
    "RuleEngine",
    "auto_correct",
    # 数据模型
    "HazardIdentificationInput",
    "HazardIdentificationOutput",
    "RectificationSuggestion",
    "ValidationResult",
    "PluginConfig",
    # 枚举
    "HazardTypeEnum",
    "HazardCategoryEnum",
    "HazardLevelEnum",
    # 工具
    "get_db_seed_config",
    "get_expected_keys",
    "build_full_prompt",
    "build_context_text",
]
