"""新增检验选料接口 GET /api/v1/quality/inspection/materials 的集成测试。

覆盖：返回全部固体+液体原辅料、字段结构、label/模块/分组正确。
"""

from __future__ import annotations

from httpx import AsyncClient

from app.modules.quality.service.quality_feishu_material_groups import (
    MATERIAL_ENTITY_LABELS,
    MATERIAL_GROUP_ENTITY_MAP,
)


async def test_list_all_materials_returns_solid_and_liquid(
    client: AsyncClient,
) -> None:
    resp = await client.get("/api/v1/quality/inspection/materials")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["data"] is not None
    assert payload["meta"]["configured"] is True

    items = payload["data"]
    expected_total = sum(
        len(entity_codes)
        for group_map in MATERIAL_GROUP_ENTITY_MAP.values()
        for entity_codes in group_map.values()
    )
    assert len(items) == expected_total
    assert len(items) > 0

    solid_items = [item for item in items if item["module"] == "solid"]
    liquid_items = [item for item in items if item["module"] == "liquid"]
    assert solid_items and liquid_items


async def test_list_all_materials_item_structure(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/quality/inspection/materials")
    items = resp.json()["data"]

    ys001 = next(item for item in items if item["entity_code"] == "qc_solid_ys001")
    assert ys001["label"] == "YS001 食用葡萄糖"
    assert ys001["label"] == MATERIAL_ENTITY_LABELS["solid"]["qc_solid_ys001"]
    assert ys001["module"] == "solid"
    assert ys001["group_key"] == "ys-000"
    assert ys001["group_label"] == "YS000"

    for item in items:
        assert set(item.keys()) == {
            "entity_code",
            "label",
            "module",
            "group_key",
            "group_label",
        }
        assert item["module"] in {"solid", "liquid"}
        assert item["entity_code"].startswith(f"qc_{item['module']}_")
        assert item["label"]
        assert item["group_key"]
        assert item["group_label"]


async def test_list_all_materials_has_no_duplicate_entity(
    client: AsyncClient,
) -> None:
    resp = await client.get("/api/v1/quality/inspection/materials")
    items = resp.json()["data"]
    entity_codes = [item["entity_code"] for item in items]
    assert len(entity_codes) == len(set(entity_codes))
