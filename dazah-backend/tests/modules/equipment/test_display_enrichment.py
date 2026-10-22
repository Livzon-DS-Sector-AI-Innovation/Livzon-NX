"""列表展示字段契约测试：计划/校准的设备名称、备件列表库存数量。

这些字段曾被前端手写类型假设存在而后端未返回（运行时列为空），
契约补齐后必须在响应中真实存在。
"""

from typing import Any

from httpx import AsyncClient


async def _create_test_equipment(client: AsyncClient) -> tuple[str, str, str]:
    """创建测试设备，返回 (equipment_id, name, equipment_no)"""
    import uuid

    uid = uuid.uuid4().hex[:8]
    cat_resp = await client.post(
        "/api/v1/equipment/categories",
        json={"name": "展示字段分类", "code": f"DC-{uid}"},
    )
    cat_id = cat_resp.json()["data"]["id"]
    loc_resp = await client.post(
        "/api/v1/equipment/locations",
        json={"name": "展示字段位置", "code": f"DL-{uid}"},
    )
    loc_id = loc_resp.json()["data"]["id"]
    name = f"展示设备-{uid}"
    equipment_no = f"EQ-DC-{uid}"
    eq_resp = await client.post(
        "/api/v1/equipment/equipments",
        json={
            "equipment_no": equipment_no,
            "name": name,
            "category_ids": [cat_id],
            "location_id": loc_id,
        },
    )
    assert eq_resp.status_code == 200
    return eq_resp.json()["data"]["id"], name, equipment_no


async def test_calibration_plan_list_includes_equipment_display(
    client: AsyncClient,
) -> Any:
    """校准计划列表与详情必须带设备名称/编号（前端表格列依赖）"""
    equipment_id, name, equipment_no = await _create_test_equipment(client)
    create_resp = await client.post(
        "/api/v1/equipment/maintenance/calibration/plans",
        json={
            "equipment_id": equipment_id,
            "calibration_type": "内部校准",
            "cycle_months": 6,
        },
    )
    assert create_resp.status_code == 200
    assert create_resp.json()["data"]["equipment_name"] == name
    assert create_resp.json()["data"]["equipment_no"] == equipment_no

    list_resp = await client.get(
        "/api/v1/equipment/maintenance/calibration/plans",
        params={"equipment_id": equipment_id},
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["data"]
    assert len(items) >= 1
    assert items[0]["equipment_name"] == name
    assert items[0]["equipment_no"] == equipment_no

    detail_resp = await client.get(
        f"/api/v1/equipment/maintenance/calibration/plans/"
        f"{create_resp.json()['data']['id']}"
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["data"]["equipment_name"] == name


async def test_maintenance_plan_list_includes_equipment_display(
    client: AsyncClient,
) -> Any:
    """维护计划列表必须带设备名称/编号（前端表格列依赖）"""
    equipment_id, name, equipment_no = await _create_test_equipment(client)
    create_resp = await client.post(
        "/api/v1/equipment/maintenance/plans/",
        json={
            "equipment_id": equipment_id,
            "plan_name": "季度保养",
            "frequency": 3,
            "frequency_unit": "月",
        },
    )
    assert create_resp.status_code == 200
    assert create_resp.json()["data"]["equipment_name"] == name

    list_resp = await client.get(
        "/api/v1/equipment/maintenance/plans/",
        params={"equipment_id": equipment_id},
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["data"]
    assert len(items) >= 1
    assert items[0]["equipment_name"] == name
    assert items[0]["equipment_no"] == equipment_no


async def test_spare_part_list_includes_stock_quantities(
    client: AsyncClient,
) -> Any:
    """备件列表必须带当前库存与安全库存（前端库存列依赖）"""
    import uuid

    uid = uuid.uuid4().hex[:8]
    create_resp = await client.post(
        "/api/v1/equipment/spare-parts/",
        json={
            "code": f"SP-DC-{uid}",
            "name": f"展示备件-{uid}",
            "unit": "个",
            "workshop_code": "201-1",
        },
    )
    assert create_resp.status_code == 200
    part_id = create_resp.json()["data"]["id"]
    # 单条创建响应不带库存（库存属于列表项契约）
    assert "current_qty" not in create_resp.json()["data"]

    inbound_resp = await client.post(
        f"/api/v1/equipment/spare-parts/{part_id}/stock/inbound",
        json={"quantity": 7},
    )
    assert inbound_resp.status_code == 200

    list_resp = await client.get(
        "/api/v1/equipment/spare-parts/",
        params={"workshop": "201-1", "page_size": 50},
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["data"]
    matched = [item for item in items if item["id"] == part_id]
    assert matched, "新建备件应出现在列表中"
    assert matched[0]["current_qty"] == 7
    assert "safety_qty" in matched[0]


async def test_maintainers_and_all_users_options(client: AsyncClient) -> None:
    """维修人/责任人下拉选项端点（分层修复后经 service 返回）"""
    maintainers_resp = await client.get(
        "/api/v1/equipment/maintenance/staff/maintainers"
    )
    assert maintainers_resp.status_code == 200
    items = maintainers_resp.json()["data"]
    for item in items:
        assert set(item) == {"user_id", "name", "employee_no", "department_id"}

    users_resp = await client.get("/api/v1/equipment/maintenance/staff/all-users")
    assert users_resp.status_code == 200
    for item in users_resp.json()["data"]:
        assert set(item) == {"user_id", "name", "employee_no"}
