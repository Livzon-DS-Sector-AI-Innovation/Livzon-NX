from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.modules.regulatory_tracker.services.notification_service import (
    RegulatoryTrackerNotificationService,
)


@pytest.mark.anyio
async def test_list_notification_recipient_options_only_returns_qa_contacts(
    db_session,
) -> None:
    service = RegulatoryTrackerNotificationService(db_session)

    with patch(
        "app.modules.quality.service.department_contacts.get_department_contact_list_from_feishu",
        new=AsyncMock(
            return_value={
                "items": [
                    {
                        "open_id": "ou_qa_1",
                        "name": "武巧玲",
                        "department": "QA",
                        "enterprise_email": "wuqiaoling@example.com",
                    },
                    {
                        "open_id": "ou_qa_2",
                        "name": "李四",
                        "department": "质量保证部",
                        "enterprise_email": "lisi@example.com",
                    },
                    {
                        "open_id": "ou_non_qa",
                        "name": "王五",
                        "department": "注册管理",
                        "enterprise_email": "wangwu@example.com",
                    },
                ]
            }
        ),
    ):
        result = await service.list_notification_recipient_options()

    assert [item.open_id for item in result] == ["ou_qa_1", "ou_qa_2"]
    assert [item.name for item in result] == ["武巧玲", "李四"]
