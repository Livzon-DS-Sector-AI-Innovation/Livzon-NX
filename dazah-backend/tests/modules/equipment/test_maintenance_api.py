"""Maintenance API integration tests."""

import uuid

from httpx import AsyncClient

from app.platform.identity.models import User  # noqa: F401


def _uid() -> str:
    return uuid.uuid4().hex[:6].upper()


async def test_create_failure_symptom(client: AsyncClient):
    """测试创建故障现象"""
    code = f"NOISE-{_uid()}"
    response = await client.post(
        "/api/v1/equipment/maintenance/failure-codes/symptoms",
        json={"code": code, "name": "异响", "sort_order": 1},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert data["data"]["code"] == code
    assert data["data"]["name"] == "异响"


async def test_list_failure_symptoms(client: AsyncClient):
    """测试查询故障现象列表"""
    uid = _uid()
    await client.post(
        "/api/v1/equipment/maintenance/failure-codes/symptoms",
        json={"code": f"NOISE-{uid}", "name": "异响"},
    )
    await client.post(
        "/api/v1/equipment/maintenance/failure-codes/symptoms",
        json={"code": f"LEAK-{uid}", "name": "泄漏"},
    )
    response = await client.get(
        "/api/v1/equipment/maintenance/failure-codes/symptoms"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) >= 2


async def test_update_failure_symptom(client: AsyncClient):
    """测试修改故障现象"""
    code = f"NOISE-{_uid()}"
    create_resp = await client.post(
        "/api/v1/equipment/maintenance/failure-codes/symptoms",
        json={"code": code, "name": "异响"},
    )
    code_id = create_resp.json()["data"]["id"]

    response = await client.put(
        f"/api/v1/equipment/maintenance/failure-codes/symptoms/{code_id}",
        json={"name": "异常噪音"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "异常噪音"


async def test_delete_failure_symptom(client: AsyncClient):
    """测试删除故障现象"""
    code = f"NOISE-{_uid()}"
    create_resp = await client.post(
        "/api/v1/equipment/maintenance/failure-codes/symptoms",
        json={"code": code, "name": "异响"},
    )
    code_id = create_resp.json()["data"]["id"]

    response = await client.delete(
        f"/api/v1/equipment/maintenance/failure-codes/symptoms/{code_id}"
    )
    assert response.status_code == 200


async def test_create_failure_cause(client: AsyncClient):
    """测试创建故障原因"""
    code = f"WEAR-{_uid()}"
    response = await client.post(
        "/api/v1/equipment/maintenance/failure-codes/causes",
        json={"code": code, "name": "轴承磨损"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "轴承磨损"


async def test_create_failure_action(client: AsyncClient):
    """测试创建维修措施"""
    code = f"REPLACE-{_uid()}"
    response = await client.post(
        "/api/v1/equipment/maintenance/failure-codes/actions",
        json={"code": code, "name": "更换部件"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "更换部件"


async def _create_test_equipment(client: AsyncClient) -> str:
    """创建测试设备并返回 equipment_id"""
    uid = _uid()
    cat_resp = await client.post(
        "/api/v1/equipment/categories",
        json={"name": "测试分类", "code": f"TC-{uid}"},
    )
    cat_id = cat_resp.json()["data"]["id"]
    loc_resp = await client.post(
        "/api/v1/equipment/locations",
        json={"name": "测试位置", "code": f"TL-{uid}"},
    )
    loc_id = loc_resp.json()["data"]["id"]
    eq_resp = await client.post(
        "/api/v1/equipment/equipments",
        json={
            "name": f"测试设备-{uid}",
            "category_id": cat_id,
            "location_id": loc_id,
        },
    )
    return eq_resp.json()["data"]["id"]


async def test_create_work_order(client: AsyncClient):
    """测试创建工单"""
    equipment_id = await _create_test_equipment(client)
    response = await client.post(
        "/api/v1/equipment/maintenance/work-orders/",
        json={
            "equipment_id": equipment_id,
            "order_type": "故障维修",
            "priority": "高",
            "fault_description": "设备发出异响",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["status"] == "待处理"
    assert data["data"]["work_order_no"].startswith("WO-")


async def test_work_order_full_lifecycle(
    client: AsyncClient, test_assignee: User
):
    """测试工单完整生命周期"""
    equipment_id = await _create_test_equipment(client)

    # 创建
    create_resp = await client.post(
        "/api/v1/equipment/maintenance/work-orders/",
        json={"equipment_id": equipment_id, "fault_description": "异响"},
    )
    wo_id = create_resp.json()["data"]["id"]
    assert create_resp.json()["data"]["status"] == "待处理"

    # 指派
    assign_resp = await client.put(
        f"/api/v1/equipment/maintenance/work-orders/{wo_id}/assign",
        json={"assignee_id": str(test_assignee.id)},
    )
    assert assign_resp.json()["data"]["status"] == "待处理"

    # 开始
    start_resp = await client.put(
        f"/api/v1/equipment/maintenance/work-orders/{wo_id}/start",
    )
    assert start_resp.json()["data"]["status"] == "执行中"

    # 完成
    complete_resp = await client.put(
        f"/api/v1/equipment/maintenance/work-orders/{wo_id}/complete",
        json={"repair_detail": "更换了轴承"},
    )
    assert complete_resp.json()["data"]["status"] == "待验收"

    # 验收通过
    verify_resp = await client.put(
        f"/api/v1/equipment/maintenance/work-orders/{wo_id}/verify",
        json={"result": "合格"},
    )
    assert verify_resp.json()["data"]["status"] == "已完成"

    # 关闭
    close_resp = await client.put(
        f"/api/v1/equipment/maintenance/work-orders/{wo_id}/close",
    )
    assert close_resp.json()["data"]["status"] == "已关闭"


async def test_work_order_list(client: AsyncClient):
    """测试工单列表"""
    equipment_id = await _create_test_equipment(client)
    await client.post(
        "/api/v1/equipment/maintenance/work-orders/",
        json={"equipment_id": equipment_id},
    )
    response = await client.get("/api/v1/equipment/maintenance/work-orders/")
    assert response.status_code == 200
    assert len(response.json()["data"]) >= 1


async def test_work_order_statistics(client: AsyncClient):
    """测试工单统计"""
    response = await client.get(
        "/api/v1/equipment/maintenance/work-orders/statistics"
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert "total" in data
    assert "by_status" in data


# ==================== Calibration API Tests ====================


async def test_create_calibration_plan(client: AsyncClient):
    """测试创建校准计划"""
    equipment_id = await _create_test_equipment(client)
    response = await client.post(
        "/api/v1/equipment/maintenance/calibration/plans",
        json={
            "equipment_id": equipment_id,
            "calibration_type": "内部校准",
            "cycle_months": 6,
            "last_calibration_date": "2026-01-01",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["calibration_type"] == "内部校准"
    assert data["data"]["next_calibration_date"] == "2026-07-01"


async def test_calibration_plan_crud(client: AsyncClient):
    """测试校准计划 CRUD"""
    equipment_id = await _create_test_equipment(client)

    # 创建
    create_resp = await client.post(
        "/api/v1/equipment/maintenance/calibration/plans",
        json={
            "equipment_id": equipment_id,
            "calibration_type": "外部检定",
            "cycle_months": 12,
        },
    )
    plan_id = create_resp.json()["data"]["id"]

    # 查询
    get_resp = await client.get(
        f"/api/v1/equipment/maintenance/calibration/plans/{plan_id}"
    )
    assert get_resp.status_code == 200

    # 修改
    update_resp = await client.put(
        f"/api/v1/equipment/maintenance/calibration/plans/{plan_id}",
        json={"cycle_months": 3},
    )
    assert update_resp.json()["data"]["cycle_months"] == 3

    # 列表
    list_resp = await client.get("/api/v1/equipment/maintenance/calibration/plans")
    assert list_resp.status_code == 200

    # 删除
    del_resp = await client.delete(
        f"/api/v1/equipment/maintenance/calibration/plans/{plan_id}"
    )
    assert del_resp.status_code == 200


async def test_create_calibration_record(client: AsyncClient):
    """测试创建校准记录"""
    equipment_id = await _create_test_equipment(client)

    # 先创建计划
    plan_resp = await client.post(
        "/api/v1/equipment/maintenance/calibration/plans",
        json={
            "equipment_id": equipment_id,
            "calibration_type": "内部校准",
            "cycle_months": 6,
            "last_calibration_date": "2026-01-01",
        },
    )
    plan_id = plan_resp.json()["data"]["id"]

    # 创建记录
    record_resp = await client.post(
        "/api/v1/equipment/maintenance/calibration/records",
        json={
            "calibration_plan_id": plan_id,
            "calibration_date": "2026-07-01",
            "calibration_type": "内部校准",
            "result": "合格",
            "certificate_no": "CERT-2026-001",
        },
    )
    assert record_resp.status_code == 200
    data = record_resp.json()
    assert data["data"]["result"] == "合格"
    assert data["data"]["next_due_date"] == "2027-01-01"


async def test_calibration_records_list(client: AsyncClient):
    """测试校准记录列表"""
    response = await client.get(
        "/api/v1/equipment/maintenance/calibration/records"
    )
    assert response.status_code == 200


async def test_calibration_plan_overdue(client: AsyncClient):
    """测试查询到期/逾期的校准计划"""
    equipment_id = await _create_test_equipment(client)

    # 创建一个即将到期的计划
    await client.post(
        "/api/v1/equipment/maintenance/calibration/plans",
        json={
            "equipment_id": equipment_id,
            "calibration_type": "内部校准",
            "cycle_months": 6,
            "last_calibration_date": "2025-01-01",
        },
    )

    response = await client.get(
        "/api/v1/equipment/maintenance/calibration/plans/overdue",
        params={"days": 365},
    )
    assert response.status_code == 200
