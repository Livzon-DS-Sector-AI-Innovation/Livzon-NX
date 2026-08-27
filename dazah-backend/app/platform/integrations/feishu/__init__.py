"""Feishu SSO, approval, IM, Bitable, notification and WebSocket integrations."""

from app.platform.integrations.feishu.bitable import FeishuBitableSync
from app.platform.integrations.feishu.client import FeishuClient
from app.platform.integrations.feishu.datasource import BitableDataSource
from app.platform.integrations.feishu.employee_datasource import (
    EmployeeBitableDataSource,
    EmployeeRecord,
)
from app.platform.integrations.feishu.im import (
    FeishuMessageSendResult,
    build_callback_card_content,
    build_callback_status_card_content,
    build_markdown_card_content,
    build_simple_card_content,
    build_text_message_content,
    normalize_feishu_card_markdown,
    send_feishu_message,
    update_feishu_message,
)
from app.platform.integrations.feishu.notification import (
    build_card,
    send_user_card,
    send_user_card_with_message_id,
    update_card,
)
from app.platform.integrations.feishu.utils import (
    FEISHU_BITABLE_RECORD_CHANGED_EVENT,
    BitableReference,
    ConnectivityStep,
    build_bitable_client,
    get_tenant_access_token,
    normalize_app_token,
    normalize_table_id,
    parse_bitable_url,
    resolve_bitable_reference,
    test_bitable_table,
)
from app.platform.integrations.feishu.ws_client import (
    start_ws_client,
    stop_ws_client,
)

__all__ = [
    "FeishuClient",
    "FeishuBitableSync",
    "BitableDataSource",
    "EmployeeBitableDataSource",
    "EmployeeRecord",
    "FeishuMessageSendResult",
    "build_callback_card_content",
    "build_callback_status_card_content",
    "build_markdown_card_content",
    "build_simple_card_content",
    "build_text_message_content",
    "normalize_feishu_card_markdown",
    "send_feishu_message",
    "update_feishu_message",
    "build_card",
    "send_user_card",
    "send_user_card_with_message_id",
    "update_card",
    "BitableReference",
    "ConnectivityStep",
    "FEISHU_BITABLE_RECORD_CHANGED_EVENT",
    "build_bitable_client",
    "get_tenant_access_token",
    "normalize_app_token",
    "normalize_table_id",
    "parse_bitable_url",
    "resolve_bitable_reference",
    "test_bitable_table",
    "start_ws_client",
    "stop_ws_client",
]
