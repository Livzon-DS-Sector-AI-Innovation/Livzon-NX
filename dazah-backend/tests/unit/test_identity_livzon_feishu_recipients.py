import uuid

import pytest
from pydantic import ValidationError

from app.platform.identity.agent_tools import FeishuDeliveryInput


def test_feishu_delivery_input_rejects_non_uuid_recipient() -> None:
    with pytest.raises(ValidationError, match="UUID"):
        FeishuDeliveryInput.model_validate(
            {
                "recipient_user_ids": ["user"],
                "title": "通知",
                "markdown": "请发送这条消息",
                "idempotency_key": "identity-delivery-invalid",
            }
        )


def test_feishu_delivery_input_accepts_explicit_local_user_id() -> None:
    user_id = uuid.uuid4()
    message = FeishuDeliveryInput.model_validate(
        {
            "recipient_user_ids": [str(user_id)],
            "title": "通知",
            "markdown": "请发送这条消息",
            "idempotency_key": "identity-delivery-explicit",
        }
    )

    assert message.recipient_user_ids == [user_id]


def test_feishu_text_delivery_rejects_card_actions() -> None:
    with pytest.raises(ValidationError, match="text delivery does not support actions"):
        FeishuDeliveryInput.model_validate(
            {
                "recipient_user_ids": [str(uuid.uuid4())],
                "message_form": "text",
                "title": "通知",
                "markdown": "纯文本内容",
                "actions": [{"label": "查看"}],
                "idempotency_key": "identity-text-actions-invalid",
            }
        )
