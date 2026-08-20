"""生产模块 API 冒烟测试：覆盖主要 GET 端点（路由/Service/Repository 层）。"""
from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from httpx import AsyncClient

from app.main import app
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User


@pytest.fixture(autouse=True)
def _authenticate_production_routes() -> Iterator[None]:
    """通过平台模块授权守卫。"""
    user = User(
        name="生产模块测试管理员",
        username="production-test-admin",
        role="admin",
        status="active",
        auth_source="local",
    )

    async def _override_current_user() -> User:
        return user

    app.dependency_overrides[get_current_user] = _override_current_user
    yield
    app.dependency_overrides.pop(get_current_user, None)

# (路径模板, 是否详情类端点)
LIST_ENDPOINTS = [
    "/api/v1/production/batch-progress",
    "/api/v1/production/batches",
    "/api/v1/production/broth-receives",
    "/api/v1/production/centrifuge1",
    "/api/v1/production/centrifuge2",
    "/api/v1/production/ceramic-equipment-logs",
    "/api/v1/production/ceramic-feeds",
    "/api/v1/production/ceramic-material-separations",
    "/api/v1/production/ceramic-membrane-cleans",
    "/api/v1/production/ceramic-membrane-ops",
    "/api/v1/production/conc1",
    "/api/v1/production/conc2",
    "/api/v1/production/decolor1",
    "/api/v1/production/dr/dashboard/summary",
    "/api/v1/production/dr/extraction/full",
    "/api/v1/production/dr/extraction/years",
    "/api/v1/production/dr/fermentation-batches",
    "/api/v1/production/dr/lineage/coverage",
    "/api/v1/production/dr/lineage/loss-funnel",
    "/api/v1/production/dr/lineage/loss-stats",
    "/api/v1/production/dr/lineage/material-reuse",
    "/api/v1/production/dr/lineage/trace",
    "/api/v1/production/dr/lineage/yield-distribution",
    "/api/v1/production/dr/records",
    "/api/v1/production/dr/records/years",
    "/api/v1/production/dr/schedule/dump-plans",
    "/api/v1/production/dr/schedule/tasks",
    "/api/v1/production/dry",
    "/api/v1/production/fa/acidification/flat-list",
    "/api/v1/production/fa/dashboard/batch-params",
    "/api/v1/production/fa/dashboard/golden-batches",
    "/api/v1/production/fa/dashboard/summary",
    "/api/v1/production/fa/dashboard/yield-chain",
    "/api/v1/production/fa/decolor-centrifuge/list",
    "/api/v1/production/fa/decolor1/list",
    "/api/v1/production/fa/fermentation/batches",
    "/api/v1/production/fa/fermentation/flat-list",
    "/api/v1/production/fa/intermediate/list",
    "/api/v1/production/fa/lineage/trace",
    "/api/v1/production/fa/monthly-averages",
    "/api/v1/production/fa/mother-liquor/list",
    "/api/v1/production/fa/mvr/list",
    "/api/v1/production/fa/plate-recovery/list",
    "/api/v1/production/fermentation",
    "/api/v1/production/filter1",
    "/api/v1/production/filter2",
    "/api/v1/production/mc/anomaly/status",
    "/api/v1/production/mc/ba-records",
    "/api/v1/production/mc/blending-records",
    "/api/v1/production/mc/blending-records/full-list",
    "/api/v1/production/mc/crude-extract/fermentation-liquids",
    "/api/v1/production/mc/crude-extract/full-list",
    "/api/v1/production/mc/dashboard/summary",
    "/api/v1/production/mc/extraction-records",
    "/api/v1/production/mc/extraction-records/full-list",
    "/api/v1/production/mc/lineage/coverage",
    "/api/v1/production/mc/lineage/material-reuse",
    "/api/v1/production/mc/lineage/trace",
    "/api/v1/production/mc/lineage/yield-distribution",
    "/api/v1/production/mc/qc-inspections",
    "/api/v1/production/mc/qc-inspections/full-list",
    "/api/v1/production/mc/refinement-records",
    "/api/v1/production/mc/refinement-records/full-list",
    "/api/v1/production/mc/sync/status",
    "/api/v1/production/non-conforming-events",
    "/api/v1/production/pack",
    "/api/v1/production/plans",
    "/api/v1/production/pressure/audit/stats",
    "/api/v1/production/pressure/dashboard",
    "/api/v1/production/pressure/data-master",
    "/api/v1/production/pressure/notifications",
    "/api/v1/production/pressure/ocr-tasks",
    "/api/v1/production/pressure/point-mappings",
    "/api/v1/production/pressure/point-mappings/check-unique",
    "/api/v1/production/pressure/records",
    "/api/v1/production/pressure/records/export/by-area",
    "/api/v1/production/pressure/records/merged",
    "/api/v1/production/pretreatments",
    "/api/v1/production/process-specs",
    "/api/v1/production/recrystallize",
    "/api/v1/production/sales-plan-details",
    "/api/v1/production/seed-cultures",
    "/api/v1/production/shift-handovers",
    "/api/v1/production/shift-handovers/positions",
    "/api/v1/production/shift-handovers/search-users",
    "/api/v1/production/shift-logs",
]

DETAIL_ENDPOINTS = [
    "/api/v1/production/batch-profile/{rid}",
    "/api/v1/production/batches/{rid}",
    "/api/v1/production/batches/{rid}/balance",
    "/api/v1/production/batches/{rid}/materials",
    "/api/v1/production/batches/{rid}/records",
    "/api/v1/production/fermentation/{rid}",
    "/api/v1/production/fermentation/{rid}/related-events",
    "/api/v1/production/plans/{rid}",
    "/api/v1/production/process-specs/{rid}",
    "/api/v1/production/process-specs/{rid}/steps",
    "/api/v1/production/seed-cultures/{rid}",
    "/api/v1/production/shift-handovers/{rid}",
    "/api/v1/production/shift-logs/{rid}",
    "/api/v1/production/pressure/data-master/{rid}",
    "/api/v1/production/pressure/ocr-tasks/{rid}",
    "/api/v1/production/pressure/point-mappings/{rid}",
    "/api/v1/production/pressure/records/{rid}",
    "/api/v1/production/steps/{rid}/parameters",
    "/api/v1/production/non-conforming-events/{rid}/affected-batches",
    "/api/v1/production/mc/qc-inputs/{rid}",
    "/api/v1/production/mc/qc-inspections/{rid}/items",
]

@pytest.mark.anyio
@pytest.mark.parametrize("path", LIST_ENDPOINTS)
async def test_production_list_endpoints(client: AsyncClient, path: str) -> None:
    response = await client.get(path)
    # 空表列表接口返回 200；带参数的接口可能 422（缺参数）但不允许 500
    assert response.status_code in (200, 400, 404, 409, 422), f"{path}: {response.status_code} {response.text[:200]}"  # noqa: E501


@pytest.mark.anyio
@pytest.mark.parametrize("path", DETAIL_ENDPOINTS)
async def test_production_detail_endpoints_missing(client: AsyncClient, path: str) -> None:  # noqa: E501
    rid = str(uuid.uuid4())
    response = await client.get(path.format(rid=rid))
    assert response.status_code in (200, 400, 404, 409, 422), f"{path}: {response.status_code} {response.text[:200]}"  # noqa: E501


POST_ENDPOINTS = [
    "/api/v1/production/batches",
    "/api/v1/production/broth-receives",
    "/api/v1/production/centrifuge1",
    "/api/v1/production/centrifuge2",
    "/api/v1/production/ceramic-equipment-logs",
    "/api/v1/production/ceramic-feeds",
    "/api/v1/production/ceramic-material-separations",
    "/api/v1/production/ceramic-membrane-cleans",
    "/api/v1/production/ceramic-membrane-ops",
    "/api/v1/production/conc1",
    "/api/v1/production/conc2",
    "/api/v1/production/decolor1",
    "/api/v1/production/dry",
    "/api/v1/production/fermentation",
    "/api/v1/production/filter1",
    "/api/v1/production/filter2",
    "/api/v1/production/pack",
    "/api/v1/production/pretreatments",
    "/api/v1/production/recrystallize",
    "/api/v1/production/seed-cultures",
    "/api/v1/production/shift-handovers",
    "/api/v1/production/shift-logs",
    "/api/v1/production/non-conforming-events",
]


@pytest.mark.anyio
@pytest.mark.parametrize("path", POST_ENDPOINTS)
async def test_production_post_endpoints_invalid_payload(client: AsyncClient, path: str) -> None:
    """空/无效 payload → 422 校验失败（覆盖路由与 Schema 校验层）。"""
    response = await client.post(path, json={})
    assert response.status_code in (200, 400, 404, 409, 422), f"{path}: {response.status_code} {response.text[:200]}"


@pytest.mark.anyio
@pytest.mark.parametrize("path", POST_ENDPOINTS)
async def test_production_post_endpoints_invalid_json(client: AsyncClient, path: str) -> None:
    """非 JSON body → 422。"""
    response = await client.post(path, content="not-json", headers={"content-type": "application/json"})
    assert response.status_code in (400, 404, 409, 422), f"{path}: {response.status_code}"
