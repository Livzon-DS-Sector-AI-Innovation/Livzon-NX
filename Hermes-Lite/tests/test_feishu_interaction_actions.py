from services.feishu_gateway_worker import _parse_interaction_action


def test_parse_interaction_card_submission() -> None:
    action = _parse_interaction_action(
        '/card {"interaction_request_id":"req-1","interaction_version":2,'
        '"interaction_idempotency_key":"submit-1",'
        '"interaction_values":{"name":"A","count":2}}'
    )

    assert action == {
        "request_id": "req-1",
        "version": 2,
        "idempotency_key": "submit-1",
        "values": {"name": "A", "count": 2},
    }


def test_parse_official_form_callback_shape() -> None:
    action = _parse_interaction_action(
        '/card {"value":{"interaction_request_id":"req-2",'
        '"interaction_version":3,"interaction_idempotency_key":"submit-2"},'
        '"form_value":{"name":"A","count":"2"},"name":"submit"}'
    )

    assert action == {
        "request_id": "req-2",
        "version": 3,
        "idempotency_key": "submit-2",
        "values": {"name": "A", "count": "2"},
    }
