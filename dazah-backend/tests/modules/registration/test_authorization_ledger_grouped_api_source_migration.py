from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


def _build_main_payload() -> dict[str, object]:
    suffix = uuid.uuid4().hex[:6].upper()
    return {
        "product_name": f"多拉菌素-{suffix}",
        "market_name": "欧盟",
        "source_sequence": "1",
        "authorization_file_name": "LOA for C&H Generics Limited",
        "quality_standard": "EP",
        "company_name": "C&H Generics Limited",
        "country": "Ireland",
        "customer_code": f"KH-{suffix}",
        "purpose": "注册",
        "status": "已递交",
        "initial_update": {
            "authorization_date": "2026.01.01",
            "handler": "王五",
            "remarks": "首次授权",
        },
    }


async def _create_grouped_main(client: AsyncClient) -> dict[str, object]:
    payload = _build_main_payload()
    response = await client.post(
        "/api/v1/registration/authorization-letters/ledger/mains",
        json=payload,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["code"] == 201
    return body["data"]


@pytest.mark.asyncio
async def test_grouped_ledger_list_returns_updates(client: AsyncClient) -> None:
    created_main = await _create_grouped_main(client)
    main_id = created_main["id"]

    create_update_response = await client.post(
        f"/api/v1/registration/authorization-letters/ledger/mains/{main_id}/updates",
        json={
            "authorization_date": "2026.02.03",
            "handler": "张三",
            "remarks": "补充更新",
        },
    )

    assert create_update_response.status_code == 201

    response = await client.get(
        "/api/v1/registration/authorization-letters/ledger",
        params={
            "product_name": created_main["product_name"],
            "market_name": created_main["market_name"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert len(body["data"]) == 1
    assert body["data"][0]["authorization_file_name"] == "LOA for C&H Generics Limited"
    assert [item["sort_order"] for item in body["data"][0]["updates"]] == [1, 2]
    assert body["data"][0]["updates"][1]["handler"] == "张三"


@pytest.mark.asyncio
async def test_create_ledger_update_only_writes_last_three_columns(
    client: AsyncClient,
) -> None:
    created_main = await _create_grouped_main(client)
    main_id = uuid.UUID(str(created_main["id"]))

    response = await client.post(
        f"/api/v1/registration/authorization-letters/ledger/mains/{main_id}/updates",
        json={
            "authorization_date": "2026.11.22",
            "handler": "刘乐",
            "remarks": "更新博茨瓦纳的 LOA",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["code"] == 201
    assert body["data"]["authorization_date"] == "2026.11.22"
    assert body["data"]["handler"] == "刘乐"
    assert body["data"]["remarks"] == "更新博茨瓦纳的 LOA"

    # 通过同一 client 会话的列表接口验证持久化结果（client 与 db_session 事务隔离）
    list_response = await client.get(
        "/api/v1/registration/authorization-letters/ledger",
        params={
            "product_name": created_main["product_name"],
            "market_name": created_main["market_name"],
        },
    )
    assert list_response.status_code == 200
    groups = list_response.json()["data"]
    assert len(groups) == 1
    persisted_main = groups[0]
    assert persisted_main["authorization_file_name"] == "LOA for C&H Generics Limited"
    assert persisted_main["quality_standard"] == "EP"
    persisted_updates = persisted_main["updates"]
    assert len(persisted_updates) == 2
    assert persisted_updates[-1]["sort_order"] == 2
    assert persisted_updates[-1]["authorization_date"] == "2026.11.22"
    assert persisted_updates[-1]["handler"] == "刘乐"
    assert persisted_updates[-1]["remarks"] == "更新博茨瓦纳的 LOA"


@pytest.mark.asyncio
async def test_delete_ledger_main_soft_deletes_updates(
    client: AsyncClient,
) -> None:
    created_main = await _create_grouped_main(client)
    main_id = uuid.UUID(str(created_main["id"]))

    append_response = await client.post(
        f"/api/v1/registration/authorization-letters/ledger/mains/{main_id}/updates",
        json={
            "authorization_date": "2026.03.03",
            "handler": "李四",
            "remarks": "第二次更新",
        },
    )
    assert append_response.status_code == 201

    response = await client.delete(
        f"/api/v1/registration/authorization-letters/ledger/mains/{main_id}"
    )

    assert response.status_code == 200
    assert response.json()["code"] == 200

    # 软删除后列表接口不再返回该主记录及其子行
    list_response = await client.get(
        "/api/v1/registration/authorization-letters/ledger",
        params={
            "product_name": created_main["product_name"],
            "market_name": created_main["market_name"],
        },
    )
    assert list_response.status_code == 200
    assert list_response.json()["data"] == []
