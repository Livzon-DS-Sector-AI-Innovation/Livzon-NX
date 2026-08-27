"""注册模块输入校验测试：必填字段与最小长度约束。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.modules.registration.schemas.fee import FeeEntryCreate, InspectionContactCreate


def test_fee_entry_create_rejects_empty_fee_type() -> None:
    with pytest.raises(ValidationError):
        FeeEntryCreate(
            fee_type="",
            amount=10,
            payment_status="未付",
        )


def test_fee_entry_create_rejects_whitespace_fee_type() -> None:
    with pytest.raises(ValidationError):
        FeeEntryCreate(
            fee_type="   ",
            amount=10,
            payment_status="未付",
        )


def test_inspection_contact_create_requires_contact_name() -> None:
    with pytest.raises(ValidationError):
        InspectionContactCreate(agency_name="某检测机构")


@pytest.mark.asyncio
async def test_create_fee_entry_api_rejects_empty_fee_type(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/registration/fees/entries",
        json={"fee_type": "", "amount": 10, "payment_status": "未付"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_inspection_contact_api_rejects_empty_body(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/registration/fees/inspection-contacts",
        json={},
    )
    assert response.status_code == 422
