from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.capa import CAPA
from app.modules.quality.models.deviations import Deviation


@pytest.fixture(autouse=True)
async def _clean_tables(db_session: AsyncSession) -> Any:
    await db_session.execute(CAPA.__table__.delete())  # type: ignore[attr-defined]
    await db_session.execute(Deviation.__table__.delete())  # type: ignore[attr-defined]
    await db_session.commit()
    yield
    await db_session.execute(CAPA.__table__.delete())  # type: ignore[attr-defined]
    await db_session.execute(Deviation.__table__.delete())  # type: ignore[attr-defined]
    await db_session.commit()


@pytest.mark.anyio
async def test_related_capas_api_matches_deviation_by_three_rules(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    deviation = Deviation(
        id=uuid.uuid4(),
        deviation_code="PC2505001",
        title="甩干异常",
    )
    db_session.add(deviation)
    await db_session.flush()  # Ensure deviation.id exists in DB before adding CAPAs
    db_session.add_all(
        [
            CAPA(
                id=uuid.uuid4(),
                capa_code="CAPA-001",
                title="显式关联",
                deviation_id=deviation.id,
            ),
            CAPA(
                id=uuid.uuid4(),
                capa_code="CAPA-002",
                title="来源编号关联",
                source="deviation",
                source_code="PC2505001",
            ),
            CAPA(
                id=uuid.uuid4(),
                capa_code="CAPA-PC2505001",
                title="编号规则关联",
            ),
        ]
    )
    await db_session.commit()

    response = await client.get(
        f"/api/v1/quality/deviations/{deviation.id}/related-capas"
    )

    assert response.status_code == 200
    items = response.json()["data"]
    assert [item["capa_code"] for item in items] == [
        "CAPA-001",
        "CAPA-002",
        "CAPA-PC2505001",
    ]


@pytest.mark.anyio
async def test_related_capas_api_deduplicates_when_multiple_rules_match_same_capa(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    deviation = Deviation(
        id=uuid.uuid4(),
        deviation_code="PC2505002",
        title="重复命中测试",
    )
    db_session.add(deviation)
    await db_session.flush()  # Ensure deviation.id exists in DB before adding CAPA
    db_session.add(
        CAPA(
            id=uuid.uuid4(),
            capa_code="CAPA-PC2505002",
            title="同时命中编号规则与显式关联",
            deviation_id=deviation.id,
        )
    )
    await db_session.commit()

    response = await client.get(
        f"/api/v1/quality/deviations/{deviation.id}/related-capas"
    )

    assert response.status_code == 200
    items = response.json()["data"]
    assert len(items) == 1
    assert items[0]["capa_code"] == "CAPA-PC2505002"


@pytest.mark.anyio
async def test_related_capas_api_returns_empty_when_no_match(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    deviation = Deviation(
        id=uuid.uuid4(),
        deviation_code="PC2505003",
        title="无关联CAPA",
    )
    db_session.add(deviation)
    await db_session.commit()

    response = await client.get(
        f"/api/v1/quality/deviations/{deviation.id}/related-capas"
    )

    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.anyio
async def test_related_capas_api_returns_404_for_nonexistent_deviation(
    client: AsyncClient,
) -> None:
    fake_id = uuid.uuid4()
    response = await client.get(f"/api/v1/quality/deviations/{fake_id}/related-capas")
    assert response.status_code == 404
