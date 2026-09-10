"""hr.public_api.get_avatar_urls_by_emails 单测（跨模块头像关联）。

open_id 是应用维度标识、跨应用不可关联；邮箱在全租户稳定，作为
人员目录 → 其他模块头像回填的桥接键。
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.models import HrFeishuMember
from app.modules.hr.public_api import get_avatar_urls_by_emails


def _member(email: str | None, avatar_url: str | None, name: str = "张三") -> Any:
    return HrFeishuMember(
        open_id=f"ou_{uuid.uuid4().hex[:12]}",
        name=name,
        department="质量部",
        email=email,
        avatar_url=avatar_url,
    )


async def _seed(db: AsyncSession, *members: Any) -> None:
    db.add_all(list(members))
    await db.commit()


@pytest.mark.anyio
async def test_returns_avatar_map_by_normalized_email(db_session: AsyncSession) -> None:
    await _seed(
        db_session,
        _member("Zhang.San@livzon.cn", "https://avatar/z1"),
        _member("li.si@livzon.cn", None),
    )
    result = await get_avatar_urls_by_emails(
        db_session, ["  zhang.san@livzon.cn ", "", "unknown@livzon.cn"]
    )
    assert result == {"zhang.san@livzon.cn": "https://avatar/z1"}


@pytest.mark.anyio
async def test_empty_input_short_circuits_without_query(
    db_session: AsyncSession,
) -> None:
    assert await get_avatar_urls_by_emails(db_session, []) == {}
    assert await get_avatar_urls_by_emails(db_session, ["  ", None]) == {}  # type: ignore[list-item]
