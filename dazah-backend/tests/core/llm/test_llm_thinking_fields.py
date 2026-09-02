"""LLM 配置思考字段（enable_thinking / custom_context / 窗口参数）契约测试。

覆盖 core/llm 本次变更：新增字段默认值、ORM 行 → LLMConfigData 透传，
避免激活配置读取路径丢失思考参数。
"""

from typing import Any
from uuid import uuid4

from app.core.llm.config import LLMConfigData, LLMConfigModel


def _row(**overrides: Any) -> LLMConfigModel:
    values: dict[str, Any] = {
        "id": uuid4(),
        "config_name": "默认文本模型",
        "config_type": "text",
        "api_base_url": "https://example.invalid/v1",
        "encrypted_api_key": "",
        "model_name": "test-model",
        "temperature": 0.2,
        "timeout_seconds": 60,
        "is_active": True,
    }
    values.update(overrides)
    return LLMConfigModel(**values)


def test_llm_config_data_thinking_field_defaults() -> None:
    data = LLMConfigData(
        id="c1",
        config_name="n",
        config_type="text",
        api_base_url="https://example.invalid/v1",
        api_key="k",
        model_name="m",
        temperature=0.2,
        timeout_seconds=60,
        is_active=True,
    )
    assert data.enable_thinking is False
    assert data.custom_context is None
    assert data.context_window_tokens == 200000
    assert data.compress_threshold == 0.8
    assert data.stream_output is True


def test_to_config_data_passes_through_thinking_fields(monkeypatch: Any) -> None:
    monkeypatch.setattr("app.core.llm.config.decrypt_api_key", lambda _: "plain-key")
    row = _row(
        enable_thinking=True,
        custom_context="工厂 GMP 语境",
        context_window_tokens=131072,
        compress_threshold=0.75,
        stream_output=False,
    )
    data = row.to_config_data()
    assert data.enable_thinking is True
    assert data.custom_context == "工厂 GMP 语境"
    assert data.context_window_tokens == 131072
    assert data.compress_threshold == 0.75
    assert data.stream_output is False


def test_to_config_data_is_transparent_for_unset_columns(monkeypatch: Any) -> None:
    monkeypatch.setattr("app.core.llm.config.decrypt_api_key", lambda _: "plain-key")
    row = _row()
    # 内存行（未 flush）Python 端列默认值不生效，to_config_data 如实透传
    # None——落库后读取的行必然携带 server_default 值。
    data = row.to_config_data()
    assert data.enable_thinking is None
    assert data.context_window_tokens is None
    assert data.api_key == "plain-key"
