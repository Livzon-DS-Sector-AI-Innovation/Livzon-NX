import uuid

from app.modules.agent.push_delivery_service import _card_action_elements


def test_interaction_artifact_renders_as_native_feishu_form() -> None:
    elements = _card_action_elements(
        [
            {
                "type": "interaction_form",
                "label": "提交",
                "interaction_request_id": "request-1",
                "interaction_version": 2,
                "fields": [
                    {
                        "key": "amount",
                        "label": "数量",
                        "type": "number",
                        "required": True,
                    },
                    {
                        "key": "confirmed",
                        "label": "确认",
                        "type": "boolean",
                    },
                ],
            }
        ],
        run_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
    )

    form = elements[0]
    assert form["tag"] == "form"
    assert form["elements"][0]["input_type"] == "number"
    assert form["elements"][1]["tag"] == "select_static"
    assert form["elements"][-1]["action_type"] == "form_submit"
    assert form["elements"][-1]["value"]["interaction_request_id"] == "request-1"
