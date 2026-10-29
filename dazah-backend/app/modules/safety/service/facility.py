"""安全设施台账：洗眼器/气体检测仪/防护设施等的台账、点检与统计。

与消防器材点检同构（快照式点检记录 + 整卡校验），但数据为平台内
直接维护，无飞书镜像与回写。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.modules.safety.models import SafetyFacility, SafetyFacilityInspection
from app.modules.safety.schemas.facilities import (
    CreateSafetyFacilityInspectionRequest,
    SafetyFacilityChecklistItem,
    SafetyFacilityChecklistResponse,
    SafetyFacilityCreate,
    SafetyFacilityStatsResponse,
    SafetyFacilityUpdate,
)

FACILITY_CATEGORY_LABELS: dict[str, str] = {
    "eyewash": "洗眼器",
    "gas_detector": "气体检测仪",
    "protective": "防护设施",
    "other": "其他",
}

# 各类别内置点检项（与消防器材 CHECK_ITEMS 同思路，整卡提交校验）
FACILITY_CHECK_ITEMS: dict[str, list[dict[str, str]]] = {
    "eyewash": [
        {"key": "appearance", "label": "外观完好、无锈蚀破损"},
        {"key": "water_flow", "label": "冲水正常、水压充足"},
        {"key": "drain", "label": "排水畅通、无堵塞"},
        {"key": "sign", "label": "标识清晰、周边无遮挡"},
        {"key": "valve", "label": "阀门启闭灵活、无滴漏"},
    ],
    "gas_detector": [
        {"key": "appearance", "label": "外观完好、显示屏正常"},
        {"key": "self_test", "label": "自检/自报功能正常"},
        {"key": "calibration", "label": "校准在有效期内"},
        {"key": "power", "label": "电池/供电正常"},
        {"key": "accessory", "label": "探头/过滤器等附件齐全"},
    ],
    "protective": [
        {"key": "integrity", "label": "设施结构完整、无变形损坏"},
        {"key": "function", "label": "功能有效（联锁/冲洗/通风等）"},
        {"key": "accessibility", "label": "周边畅通、无遮挡占用"},
        {"key": "sign", "label": "标识与警示完好"},
    ],
    "other": [
        {"key": "appearance", "label": "外观完好"},
        {"key": "function", "label": "功能正常"},
        {"key": "sign", "label": "标识完好"},
    ],
}

_VALID_CATEGORIES = set(FACILITY_CATEGORY_LABELS)
_VALID_STATUSES = {"normal", "damaged", "scrapped"}


def build_search_text(
    name: str, facility_no: str, department: str, location: str, model_spec: str
) -> str:
    return " ".join(
        part for part in (name, facility_no, department, location, model_spec) if part
    )


def get_checklist(category: str) -> SafetyFacilityChecklistResponse:
    items = FACILITY_CHECK_ITEMS.get(category) or FACILITY_CHECK_ITEMS["other"]
    return SafetyFacilityChecklistResponse(
        category=category,
        items=[SafetyFacilityChecklistItem.model_validate(item) for item in items],
    )


class SafetyFacilityService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_facilities(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        category: str | None = None,
        department: str | None = None,
        status: str | None = None,
        expiry_status: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[SafetyFacility], int]:
        conditions: list[ColumnElement[bool]] = [SafetyFacility.is_deleted.is_(False)]
        if category:
            conditions.append(SafetyFacility.category == category)
        if department:
            conditions.append(SafetyFacility.department == department)
        if status:
            conditions.append(SafetyFacility.status == status)
        if expiry_status == "expiring":
            horizon = date.today() + timedelta(days=90)
            conditions.append(SafetyFacility.expiry_date.is_not(None))
            conditions.append(SafetyFacility.expiry_date <= horizon)
        if expiry_status == "expired":
            conditions.append(SafetyFacility.expiry_date.is_not(None))
            conditions.append(SafetyFacility.expiry_date < date.today())
        if keyword:
            pattern = f"%{keyword.strip()}%"
            conditions.append(
                or_(
                    SafetyFacility.name.ilike(pattern),
                    SafetyFacility.facility_no.ilike(pattern),
                    SafetyFacility.search_text.ilike(pattern),
                )
            )

        total = (
            await self.db.execute(
                select(func.count()).select_from(SafetyFacility).where(*conditions)
            )
        ).scalar() or 0
        result = await self.db.execute(
            select(SafetyFacility)
            .where(*conditions)
            .order_by(
                SafetyFacility.category.asc(),
                SafetyFacility.department.asc(),
                SafetyFacility.facility_no.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def get_facility(self, facility_id: UUID) -> SafetyFacility | None:
        result = await self.db.execute(
            select(SafetyFacility).where(
                SafetyFacility.id == facility_id,
                SafetyFacility.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_no(self, facility_no: str) -> SafetyFacility | None:
        if not facility_no:
            return None
        result = await self.db.execute(
            select(SafetyFacility).where(
                SafetyFacility.facility_no == facility_no,
                SafetyFacility.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def create_facility(
        self, data: SafetyFacilityCreate, user_id: UUID | None = None
    ) -> SafetyFacility:
        if data.category not in _VALID_CATEGORIES:
            raise AppException(status_code=422, message="无效的设施类别")
        if data.status not in _VALID_STATUSES:
            raise AppException(status_code=422, message="无效的设施状态")
        if data.facility_no and await self.get_by_no(data.facility_no) is not None:
            raise AppException(status_code=409, message="设施编号已存在")
        facility = SafetyFacility(
            **data.model_dump(),
            search_text=build_search_text(
                data.name,
                data.facility_no,
                data.department,
                data.location,
                data.model_spec,
            ),
            created_by=user_id,
            updated_by=user_id,
        )
        self.db.add(facility)
        await self.db.flush()
        return facility

    async def update_facility(
        self, facility_id: UUID, data: SafetyFacilityUpdate, user_id: UUID | None = None
    ) -> SafetyFacility:
        facility = await self.get_facility(facility_id)
        if facility is None:
            raise NotFoundException("安全设施不存在")
        changes = data.model_dump(exclude_unset=True)
        if "category" in changes and changes["category"] not in _VALID_CATEGORIES:
            raise AppException(status_code=422, message="无效的设施类别")
        if "status" in changes and changes["status"] not in _VALID_STATUSES:
            raise AppException(status_code=422, message="无效的设施状态")
        new_no = changes.get("facility_no", facility.facility_no)
        if new_no and new_no != facility.facility_no:
            existing = await self.get_by_no(new_no)
            if existing is not None and existing.id != facility.id:
                raise AppException(status_code=409, message="设施编号已存在")
        for field, value in changes.items():
            setattr(facility, field, value)
        facility.search_text = build_search_text(
            facility.name,
            facility.facility_no,
            facility.department,
            facility.location,
            facility.model_spec,
        )
        facility.updated_by = user_id
        await self.db.flush()
        return facility

    async def delete_facility(self, facility_id: UUID) -> bool:
        facility = await self.get_facility(facility_id)
        if facility is None:
            return False
        facility.is_deleted = True
        await self.db.flush()
        return True

    async def create_inspection(
        self,
        facility_id: UUID,
        data: CreateSafetyFacilityInspectionRequest,
        *,
        inspector_id: UUID | None = None,
    ) -> SafetyFacilityInspection:
        facility = await self.get_facility(facility_id)
        if facility is None:
            raise NotFoundException("安全设施不存在")

        checklist = get_checklist(facility.category).items
        valid_keys = {item.key for item in checklist}
        seen: set[str] = set()
        for item in data.items:
            if item.key not in valid_keys:
                raise AppException(
                    status_code=400,
                    message=f"点检项 {item.key} 不属于当前设施类别的检查卡",
                )
            if item.key in seen:
                raise AppException(
                    status_code=400, message=f"点检项 {item.key} 重复提交"
                )
            seen.add(item.key)
        missing = valid_keys - seen
        if missing:
            raise AppException(
                status_code=400,
                message=f"点检项未填完整：{'、'.join(sorted(missing))}",
            )

        result = "fail" if any(i.result == "fail" for i in data.items) else "pass"
        inspected_at = data.inspected_at or datetime.now(UTC)
        record = SafetyFacilityInspection(
            facility_id=facility.id,
            facility_category=facility.category,
            facility_no=facility.facility_no,
            facility_name=facility.name,
            items=[item.model_dump() for item in data.items],
            result=result,
            abnormal_action=data.abnormal_action,
            inspector_id=inspector_id,
            inspector_name=data.inspector_name,
            inspected_at=inspected_at,
            source="web",
        )
        self.db.add(record)
        facility.last_inspected_at = inspected_at
        facility.last_inspection_result = result
        if result == "fail" and facility.status == "normal":
            facility.status = "damaged"
        await self.db.flush()
        return record

    async def list_inspections(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        facility_id: UUID | None = None,
        result: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> tuple[list[SafetyFacilityInspection], int]:
        conditions: list[ColumnElement[bool]] = [
            SafetyFacilityInspection.is_deleted.is_(False)
        ]
        if facility_id is not None:
            conditions.append(SafetyFacilityInspection.facility_id == facility_id)
        if result:
            conditions.append(SafetyFacilityInspection.result == result)
        if start_date is not None:
            conditions.append(SafetyFacilityInspection.inspected_at >= start_date)
        if end_date is not None:
            conditions.append(SafetyFacilityInspection.inspected_at <= end_date)

        total = (
            await self.db.execute(
                select(func.count())
                .select_from(SafetyFacilityInspection)
                .where(*conditions)
            )
        ).scalar() or 0
        rows = await self.db.execute(
            select(SafetyFacilityInspection)
            .where(*conditions)
            .order_by(SafetyFacilityInspection.inspected_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows.scalars().all()), total

    async def get_stats(self) -> SafetyFacilityStatsResponse:
        rows = (
            await self.db.execute(
                select(
                    SafetyFacility.category,
                    SafetyFacility.status,
                    SafetyFacility.expiry_date,
                    SafetyFacility.last_inspection_result,
                ).where(SafetyFacility.is_deleted.is_(False))
            )
        ).all()

        by_category: dict[str, int] = {}
        by_status: dict[str, int] = {}
        expiring = 0
        failed = 0
        horizon = date.today() + timedelta(days=90)
        today = date.today()
        for category, status, expiry_date, last_result in rows:
            by_category[category] = by_category.get(category, 0) + 1
            by_status[status] = by_status.get(status, 0) + 1
            if expiry_date is not None and today <= expiry_date <= horizon:
                expiring += 1
            if last_result == "fail":
                failed += 1
        return SafetyFacilityStatsResponse(
            total=len(rows),
            by_category=by_category,
            by_status=by_status,
            expiring_in_90d=expiring,
            failed_recent=failed,
        )
