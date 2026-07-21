from app.modules.agent.llm_proxy import (
    body_without_thinking,
    build_provider_body,
    payload_has_images,
    should_retry_without_auto_thinking,
)


def test_payload_has_images_detects_multimodal_message() -> None:
    assert payload_has_images(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "识别图片"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,YQ=="},
                        },
                    ],
                }
            ]
        }
    )
    assert not payload_has_images(
        {"messages": [{"role": "user", "content": "普通文本"}]}
    )


def test_build_provider_body_merges_extra_body_for_raw_http_forwarding():
    body = build_provider_body(
        {
            "model": "dazah-active-text",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
            "extra_body": {
                "thinking": {"type": "disabled"},
                "provider": {"only": ["moonshot"]},
            },
        },
        model_name="kimi-k2.5",
        temperature=0.1,
    )

    assert body["model"] == "kimi-k2.5"
    assert body["messages"] == [{"role": "user", "content": "hello"}]
    assert body["stream"] is True
    assert body["thinking"] == {"type": "disabled"}
    assert body["provider"] == {"only": ["moonshot"]}
    assert "extra_body" not in body


def test_build_provider_body_disables_kimi_thinking_by_default():
    body = build_provider_body(
        {"messages": [{"role": "user", "content": "hello"}]},
        model_name="kimi-k2.5",
        temperature=0.1,
    )

    assert body["thinking"] == {"type": "disabled"}


def test_build_provider_body_preserves_explicit_kimi_thinking():
    body = build_provider_body(
        {
            "messages": [{"role": "user", "content": "hello"}],
            "extra_body": {"thinking": {"type": "enabled"}},
        },
        model_name="kimi-k2.5",
        temperature=0.1,
    )

    assert body["thinking"] == {"type": "enabled"}
    assert not should_retry_without_auto_thinking(
        {"extra_body": {"thinking": {"type": "enabled"}}},
        body,
        "kimi-k2.5",
    )


def test_build_provider_body_preserves_explicit_reasoning_effort():
    body = build_provider_body(
        {
            "messages": [{"role": "user", "content": "hello"}],
            "reasoning_effort": "low",
        },
        model_name="deepseek-chat",
        temperature=0.1,
    )

    assert body["reasoning_effort"] == "low"
    assert "thinking" not in body


def test_build_provider_body_does_not_add_kimi_defaults_to_other_models():
    body = build_provider_body(
        {"messages": [{"role": "user", "content": "hello"}]},
        model_name="deepseek-chat",
        temperature=0.1,
    )

    assert "thinking" not in body


def test_build_provider_body_omits_config_temperature_when_zero():
    body = build_provider_body(
        {"messages": [{"role": "user", "content": "hello"}]},
        model_name="local-model",
        temperature=0,
    )

    assert "temperature" not in body


def test_build_provider_body_preserves_explicit_payload_temperature_when_config_zero():
    body = build_provider_body(
        {
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": 0.7,
        },
        model_name="local-model",
        temperature=0,
    )

    assert body["temperature"] == 0.7


def test_build_provider_body_strips_temperature_for_kimi_models():
    body = build_provider_body(
        {
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": 0.7,
        },
        model_name="moonshotai/Kimi-K2.6",
        temperature=0.1,
    )

    assert "temperature" not in body
    assert body["thinking"] == {"type": "disabled"}


def test_build_provider_body_strips_reasoning_effort_for_default_kimi_non_thinking():
    body = build_provider_body(
        {
            "messages": [{"role": "user", "content": "hello"}],
            "reasoning_effort": "high",
        },
        model_name="kimi-k2.5",
        temperature=0,
    )

    assert "reasoning_effort" not in body
    assert body["thinking"] == {"type": "disabled"}


def test_build_provider_body_preserves_explicit_kimi_thinking_with_reasoning_effort():
    body = build_provider_body(
        {
            "messages": [{"role": "user", "content": "hello"}],
            "reasoning_effort": "high",
            "extra_body": {"thinking": {"type": "enabled"}},
        },
        model_name="kimi-k2.5",
        temperature=0,
    )

    assert body["reasoning_effort"] == "high"
    assert body["thinking"] == {"type": "enabled"}


def test_should_retry_without_auto_thinking_for_auto_kimi_default():
    payload = {"messages": [{"role": "user", "content": "hello"}]}
    body = build_provider_body(payload, model_name="kimi-k2.5", temperature=0.1)

    assert should_retry_without_auto_thinking(payload, body, "kimi-k2.5")
    assert "thinking" not in body_without_thinking(body)
