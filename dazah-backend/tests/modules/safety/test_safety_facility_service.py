"""安全设施台账服务层测试（真实服务 + 独立测试库）。

覆盖：台账创建/编号冲突、点检整卡校验（缺项/未知项）、点检失败联动
状态、统计聚合与类别检查卡。
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.safety.models import SafetyFacility, SafetyFacilityInspection
from app.modules.safety.schemas.facilities import (
    CreateSafetyFacilityInspectionRequest,
    SafetyFacilityCreate,
    SafetyFacilityItemInput,
)
from app.modules.safety.service.facility import (
    SafetyFacilityService,
    get_checklist,
)


@pytest.fixture(autouse=True)
async def _cleanup_facilities(db_session: AsyncSession) -> AsyncIterator[None]:
    yield
    await db_session.execute(
        delete(SafetyFacilityInspection).where(
            SafetyFacilityInspection.facility_id.in_(
                select(SafetyFacility.id).where(
                    SafetyFacility.facility_no.like("T-FAC-%")
                )
            )
        )
    )
    await db_session.execute(
        delete(SafetyFacility).where(SafetyFacility.facility_no.like("T-FAC-%"))
    )
    await db_session.commit()


async def _create_facility(
    db: AsyncSession,
    *,
    category: str = "eyewash",
    no: str = "T-FAC-001",
    name: str = "测试洗眼器",
) -> SafetyFacility:
    service = SafetyFacilityService(db)
    return await service.create_facility(
        SafetyFacilityCreate(
            category=category,
            facility_no=no,
            name=name,
            department="测试车间",
            location="一层东侧",
        )
    )


async def test_create_facility_and_duplicate_no(db_session: AsyncSession) -> None:
    facility = await _create_facility(db_session)
    assert facility.category == "eyewash"
    assert "测试洗眼器" in facility.search_text

    service = SafetyFacilityService(db_session)
    with pytest.raises(AppException) as exc:
        await service.create_facility(
            SafetyFacilityCreate(
                category="eyewash", facility_no="T-FAC-001", name="重复编号"
            )
        )
    assert exc.value.status_code == 409

    with pytest.raises(AppException) as exc:
        await service.create_facility(
            SafetyFacilityCreate(category="invalid", name="非法类别")
        )
    assert exc.value.status_code == 422


async def test_checklist_covers_category() -> None:
    eyewash = get_checklist("eyewash")
    assert eyewash.category == "eyewash"
    assert any(item.key == "water_flow" for item in eyewash.items)
    detector = get_checklist("gas_detector")
    assert any(item.key == "calibration" for item in detector.items)
    unknown = get_checklist("not-exists")
    assert len(unknown.items) > 0  # 兜底为 other 卡


async def test_inspection_validation_and_fail_linkage(
    db_session: AsyncSession,
) -> None:
    facility = await _create_facility(db_session, no="T-FAC-002")
    service = SafetyFacilityService(db_session)
    checklist = get_checklist("eyewash")

    def _items(
        skip: str | None = None, unknown: str | None = None
    ) -> list[SafetyFacilityItemInput]:
        return [
            SafetyFacilityItemInput(
                key=item.key,
                label=item.label,
                result="fail" if item.key == unknown else "ok",
            )
            for item in checklist.items
            if item.key != skip
        ]

    # 缺项 → 400
    with pytest.raises(AppException) as exc:
        await service.create_inspection(
            facility.id,
            CreateSafetyFacilityInspectionRequest(
                items=_items(skip="valve"),
                inspected_at=datetime.now(UTC),
            ),
        )
    assert exc.value.status_code == 400
    assert "valve" in (exc.value.message or "")

    # 未知检查项 → 400
    with pytest.raises(AppException) as exc:
        await service.create_inspection(
            facility.id,
            CreateSafetyFacilityInspectionRequest(
                items=[
                    *_items(),
                    SafetyFacilityItemInput(key="ghost", label="幽灵项", result="ok"),
                ],
                inspected_at=datetime.now(UTC),
            ),
        )
    assert exc.value.status_code == 400

    # 全 pass → 正常，设施状态保持 normal
    record = await service.create_inspection(
        facility.id,
        CreateSafetyFacilityInspectionRequest(
            items=_items(),
            inspector_name="李四",
            inspected_at=datetime.now(UTC),
        ),
    )
    assert record.result == "pass"
    await db_session.commit()
    refreshed = await service.get_facility(facility.id)
    assert refreshed is not None
    assert refreshed.last_inspection_result == "pass"
    assert refreshed.status == "normal"

    # 有 fail → 结论 fail，设施转 damaged
    record = await service.create_inspection(
        facility.id,
        CreateSafetyFacilityInspectionRequest(
            items=_items(unknown="water_flow"),
            abnormal_action="已报修",
            inspected_at=datetime.now(UTC),
        ),
    )
    assert record.result == "fail"
    await db_session.commit()
    refreshed = await service.get_facility(facility.id)
    assert refreshed is not None
    assert refreshed.status == "damaged"


async def test_stats_and_listing(db_session: AsyncSession) -> None:
    await _create_facility(
        db_session, no="T-FAC-003", category="gas_detector", name="测试检测仪"
    )
    service = SafetyFacilityService(db_session)

    items, total = await service.list_facilities(
        category="gas_detector", keyword="T-FAC-003"
    )
    assert total == 1
    assert items[0].facility_no == "T-FAC-003"

    stats = await service.get_stats()
    assert stats.by_category.get("gas_detector", 0) >= 1
    assert stats.total >= 1

    records, record_total = await service.list_inspections(facility_id=None)
    assert record_total >= 0
    assert isinstance(records, list)


async def test_delete_facility_soft(db_session: AsyncSession) -> None:
    facility = await _create_facility(db_session, no="T-FAC-004", name="待删除设施")
    service = SafetyFacilityService(db_session)
    assert await service.delete_facility(facility.id) is True
    await db_session.commit()
    assert await service.get_facility(facility.id) is None
    # 无 FK 引用时的孤儿记录不应存在
    leftovers = await db_session.execute(
        select(SafetyFacilityInspection).where(
            SafetyFacilityInspection.facility_id == facility.id
        )
    )
    assert leftovers.scalars().all() == []
