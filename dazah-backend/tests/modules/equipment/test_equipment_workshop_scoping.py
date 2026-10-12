"""设备模块按车间隔离的回归测试（台账/维护/备件/人员）。

巡检飞书子系统的车间隔离见 test_inspection_feishu_mirror.py；
本文件覆盖其余四个子系统的 workshop 维度：
- 台账：equipments.workshop_code 直接过滤，Excel 导入记录车间
- 维护：工单经 equipment_id 派生车间过滤
- 备件：spare_parts.workshop_code 直接过滤
- 人员：equipment_personnel.workshop_code 直接过滤，同一人可入多个车间
"""

from __future__ import annotations

import io
import uuid
from typing import Any

from openpyxl import Workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.equipment.models.equipment import EquipmentCategory, Location
from app.modules.equipment.schemas.equipment import EquipmentCreate
from app.modules.equipment.schemas.personnel import PersonnelAddRequest
from app.modules.equipment.schemas.spare_part import SparePartCreate
from app.modules.equipment.schemas.work_order import WorkOrderCreate
from app.modules.equipment.service import equipment as equipment_service
from app.modules.equipment.service import equipment_import
from app.modules.equipment.service import personnel as personnel_service
from app.modules.equipment.service import spare_part as spare_part_service
from app.modules.equipment.service import work_order as work_order_service
from app.platform.identity.models import User


def _uid() -> str:
    return uuid.uuid4().hex[:8].upper()


async def _seed_category_and_location(
    db: AsyncSession,
) -> tuple[uuid.UUID, uuid.UUID]:
    category = EquipmentCategory(name="车间隔离分类", code=f"WS-C-{_uid()}")
    location = Location(name="车间隔离位置", code=f"WS-L-{_uid()}")
    db.add_all([category, location])
    await db.flush()
    return category.id, location.id


async def _create_equipment(
    db: AsyncSession,
    category_id: uuid.UUID,
    location_id: uuid.UUID,
    workshop_code: str,
) -> Any:
    return await equipment_service.create_equipment(
        db,
        EquipmentCreate(
            name=f"车间隔离设备{_uid()}",
            equipment_no=f"XT-WS-{_uid()}",
            workshop_code=workshop_code,
            category_ids=[category_id],
            location_id=location_id,
        ),
    )


# ---------- 台账 ----------


async def test_equipments_scoped_by_workshop(db_session: AsyncSession) -> None:
    """台账按车间过滤：列表与统计互不串台。"""
    category_id, location_id = await _seed_category_and_location(db_session)
    await _create_equipment(db_session, category_id, location_id, "101-2")
    await _create_equipment(db_session, category_id, location_id, "201-1")

    items, total = await equipment_service.get_equipments(
        db_session, workshop_code="101-2"
    )
    assert total == 1
    assert items[0].workshop_code == "101-2"

    stats = await equipment_service.get_equipment_statistics(
        db_session, workshop_code="101-2"
    )
    assert stats["total"] == 1

    # 缺省跨车间查询
    _, total_all = await equipment_service.get_equipments(db_session)
    assert total_all >= 2


async def test_import_assigns_workshop(db_session: AsyncSession) -> None:
    """Excel 导入的设备归属导入时指定的车间。"""
    category_id, location_id = await _seed_category_and_location(db_session)
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["设备编号", "设备名称", "安装地点"])
    no = f"XT-IMP-{_uid()}"
    sheet.append([no, "导入车间测试设备", "不存在的地点"])
    buffer = io.BytesIO()
    workbook.save(buffer)

    summary = await equipment_import.import_equipment_ledger(
        db_session,
        buffer.getvalue(),
        default_category_id=category_id,
        default_location_id=location_id,
        workshop_code="101-2",
    )
    assert summary["created"] == 1
    equipment = await equipment_service.repo.get_equipment_by_no(db_session, no)
    assert equipment is not None
    assert equipment.workshop_code == "101-2"


# ---------- 维护（工单经设备派生车间） ----------


async def test_work_orders_scoped_by_workshop(db_session: AsyncSession) -> None:
    """工单列表按所属设备的车间过滤。"""
    category_id, location_id = await _seed_category_and_location(db_session)
    equipment_101 = await _create_equipment(
        db_session, category_id, location_id, "101-2"
    )
    equipment_201 = await _create_equipment(
        db_session, category_id, location_id, "201-1"
    )
    reporter = User(
        name="车间隔离报修人",
        employee_no=f"EMP-WS-{_uid()}",
        role="admin",
        status="active",
    )
    db_session.add(reporter)
    await db_session.flush()

    order_101 = await work_order_service.create_work_order(
        db_session,
        WorkOrderCreate(equipment_id=equipment_101.id, fault_description="101车间故障"),
        reporter.id,
    )
    await work_order_service.create_work_order(
        db_session,
        WorkOrderCreate(equipment_id=equipment_201.id, fault_description="201车间故障"),
        reporter.id,
    )

    orders, total = await work_order_service.get_work_orders(
        db_session, workshop_code="101-2"
    )
    assert total == 1
    assert orders[0].id == order_101.id

    stats = await work_order_service.get_work_order_statistics(
        db_session, workshop_code="101-2"
    )
    assert stats["total"] == 1


# ---------- 备件 ----------


async def test_spare_parts_scoped_by_workshop(db_session: AsyncSession) -> None:
    """备件按车间过滤，创建记录归属车间。"""
    await spare_part_service.create_spare_part(
        db_session,
        SparePartCreate(
            code=f"SP-WS-{_uid()}",
            name="101车间备件",
            workshop_code="101-2",
            unit="个",
        ),
    )
    await spare_part_service.create_spare_part(
        db_session,
        SparePartCreate(
            code=f"SP-WS-{_uid()}",
            name="201车间备件",
            workshop_code="201-1",
            unit="个",
        ),
    )

    parts, total = await spare_part_service.get_spare_parts(
        db_session, workshop_code="101-2"
    )
    assert total == 1
    assert parts[0].workshop_code == "101-2"
    assert parts[0].name == "101车间备件"


# ---------- 人员 ----------


async def test_personnel_scoped_by_workshop(db_session: AsyncSession) -> None:
    """人员按车间过滤；同一人可加入多个车间人员池。"""
    user = User(
        name="车间隔离人员",
        employee_no=f"EMP-P-{_uid()}",
        role="admin",
        status="active",
    )
    db_session.add(user)
    await db_session.flush()

    result_101 = await personnel_service.add_personnel(
        db_session, PersonnelAddRequest(user_ids=[user.id], workshop_code="101-2")
    )
    assert result_101.added and not result_101.skipped
    # 同一人加入另一车间：不视为重复
    result_201 = await personnel_service.add_personnel(
        db_session, PersonnelAddRequest(user_ids=[user.id], workshop_code="201-1")
    )
    assert result_201.added and not result_201.skipped
    # 同车间重复添加：跳过
    result_dup = await personnel_service.add_personnel(
        db_session, PersonnelAddRequest(user_ids=[user.id], workshop_code="101-2")
    )
    assert not result_dup.added and result_dup.skipped == [user.id]

    listing_101 = await personnel_service.list_personnel(
        db_session, workshop_code="101-2"
    )
    assert listing_101.total == 1
    assert listing_101.items[0].workshop_code == "101-2"
