import pytest
from pydantic import ValidationError

from app.platform.identity.agent_tools import FeishuUnifiedMessageInput


def test_feishu_message_input_rejects_generic_recipient_placeholder() -> None:
    with pytest.raises(ValidationError, match="不能使用占位词"):
        FeishuUnifiedMessageInput.model_validate(
            {
                "user_ids": ["user"],
                "text": "请发送这条消息",
            }
        )


def test_feishu_message_input_accepts_explicit_recipient_identifier() -> None:
    message = FeishuUnifiedMessageInput.model_validate(
        {
            "user_ids": ["ou_explicit_recipient"],
            "text": "请发送这条消息",
        }
    )

    assert message.user_ids == ["ou_explicit_recipient"]
