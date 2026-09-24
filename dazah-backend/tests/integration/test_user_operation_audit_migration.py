from typing import Any

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_operation_audit_partial_index_exists(db_session: Any) -> None:
    definition = await db_session.scalar(
        text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE schemaname = 'audit' "
            "AND indexname = 'idx_audit_logs_operations_module_time'"
        )
    )
    assert definition is not None
    assert "resource_type" in definition
    assert "created_at" in definition
    assert "platform_api_request" in definition
