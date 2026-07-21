"""Pressure differential inspection database queries."""

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production.pressure_models import (
    DataMaster,
    Notification,
    OcrTask,
    PointMapping,
    PressureRecord,
)


class PressureRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── PointMapping ───

    async def list_point_mappings(
        self,
        *,
        area: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[PointMapping], int]:
        stmt = select(PointMapping).where(PointMapping.is_deleted.is_(False))
        if area:
            stmt = stmt.where(PointMapping.area == area)
        if keyword:
            stmt = stmt.where(PointMapping.point_id.ilike(f"%{keyword}%"))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(PointMapping.point_id).offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def get_point_mapping_by_id(self, mapping_id: UUID) -> PointMapping | None:
        result = await self.session.execute(
            select(PointMapping).where(
                PointMapping.id == mapping_id, PointMapping.is_deleted.is_(False)
            )
        )
        return result.scalar_one_or_none()

    async def get_point_mapping_by_point_id(self, point_id: str) -> PointMapping | None:
        result = await self.session.execute(
            select(PointMapping).where(
                PointMapping.point_id == point_id, PointMapping.is_deleted.is_(False)
            )
        )
        return result.scalar_one_or_none()

    async def check_point_id_unique(self, point_id: str) -> bool:
        result = await self.session.execute(
            select(func.count()).where(
                PointMapping.point_id == point_id, PointMapping.is_deleted.is_(False)
            )
        )
        return (result.scalar() or 0) > 0

    async def get_points_by_area(self, area: str) -> list[PointMapping]:
        result = await self.session.execute(
            select(PointMapping).where(
                PointMapping.area == area, PointMapping.is_deleted.is_(False)
            ).order_by(PointMapping.point_id)
        )
        return list(result.scalars().all())

    async def create_point_mapping(self, data: dict) -> PointMapping:
        mapping = PointMapping(**data)
        self.session.add(mapping)
        await self.session.flush()
        await self.session.refresh(mapping)
        return mapping

    async def update_point_mapping(
        self, mapping_id: UUID, data: dict
    ) -> PointMapping | None:
        stmt = (
            update(PointMapping)
            .where(PointMapping.id == mapping_id, PointMapping.is_deleted.is_(False))
            .values(**data)
            .returning(PointMapping)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_point_mapping(self, mapping_id: UUID) -> bool:
        stmt = (
            update(PointMapping)
            .where(PointMapping.id == mapping_id, PointMapping.is_deleted.is_(False))
            .values(is_deleted=True)
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    # ─── PressureRecord ───

    async def list_records(
        self,
        *,
        area: str | None = None,
        point_id: str | None = None,
        input_type: str | None = None,
        status: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[PressureRecord], int]:
        stmt = select(PressureRecord).where(PressureRecord.is_deleted.is_(False))
        if area:
            stmt = stmt.where(PressureRecord.area == area)
        if point_id:
            stmt = stmt.where(PressureRecord.point_id == point_id)
        if input_type:
            stmt = stmt.where(PressureRecord.input_type == input_type)
        if status:
            stmt = stmt.where(PressureRecord.status == status)
        if start_date:
            stmt = stmt.where(PressureRecord.record_time >= start_date)
        if end_date:
            stmt = stmt.where(PressureRecord.record_time <= end_date)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(PressureRecord.record_time.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def get_record_by_id(self, record_id: UUID) -> PressureRecord | None:
        result = await self.session.execute(
            select(PressureRecord).where(
                PressureRecord.id == record_id, PressureRecord.is_deleted.is_(False)
            )
        )
        return result.scalar_one_or_none()

    async def create_record(self, data: dict) -> PressureRecord:
        record = PressureRecord(**data)
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def create_records_batch(self, records: list[PressureRecord]) -> list[PressureRecord]:
        for r in records:
            self.session.add(r)
        await self.session.flush()
        for r in records:
            await self.session.refresh(r)
        return records

    async def update_record(self, record_id: UUID, data: dict) -> PressureRecord | None:
        stmt = (
            update(PressureRecord)
            .where(PressureRecord.id == record_id, PressureRecord.is_deleted.is_(False))
            .values(**data)
            .returning(PressureRecord)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_record(self, record_id: UUID) -> bool:
        stmt = (
            update(PressureRecord)
            .where(PressureRecord.id == record_id, PressureRecord.is_deleted.is_(False))
            .values(is_deleted=True)
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def batch_delete_records(self, ids: list[UUID]) -> int:
        if not ids:
            return 0
        stmt = (
            update(PressureRecord)
            .where(PressureRecord.id.in_(ids), PressureRecord.is_deleted.is_(False))
            .values(is_deleted=True)
        )
        result = await self.session.execute(stmt)
        return result.rowcount

    async def audit_record(
        self, record_id: UUID, status: str, reject_reason: str | None = None
    ) -> PressureRecord | None:
        data = {"status": status}
        if reject_reason:
            data["reject_reason"] = reject_reason
        return await self.update_record(record_id, data)

    async def batch_audit_records(
        self, ids: list[UUID], status: str, reject_reason: str | None = None
    ) -> int:
        if not ids:
            return 0
        data: dict = {"status": status}
        if reject_reason:
            data["reject_reason"] = reject_reason
        stmt = (
            update(PressureRecord)
            .where(PressureRecord.id.in_(ids), PressureRecord.is_deleted.is_(False))
            .values(**data)
        )
        result = await self.session.execute(stmt)
        return result.rowcount

    # ─── Merged View ───

    async def list_merged_records(
        self,
        *,
        area: str | None = None,
        point_id: str | None = None,
        input_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """查询合并后的压差记录（同一位点同一天合并为一行）"""
        stmt = select(PressureRecord).where(PressureRecord.is_deleted.is_(False))
        if area:
            stmt = stmt.where(PressureRecord.area == area)
        if point_id:
            stmt = stmt.where(PressureRecord.point_id == point_id)
        if input_type:
            stmt = stmt.where(PressureRecord.input_type == input_type)
        if start_date:
            stmt = stmt.where(PressureRecord.record_time >= start_date)
        if end_date:
            stmt = stmt.where(PressureRecord.record_time <= end_date)

        stmt = stmt.order_by(PressureRecord.record_time.desc())
        result = await self.session.execute(stmt)
        all_records = list(result.scalars().all())

        # 按 point_id + date 分组
        group_map: dict[str, dict] = {}
        for rec in all_records:
            date_str = rec.record_time.strftime("%Y-%m-%d")
            group_key = f"{rec.point_id}|{date_str}"
            if group_key not in group_map:
                group_map[group_key] = {
                    "point_id": rec.point_id,
                    "area": rec.area,
                    "date": date_str,
                    "time_slot_values": {},
                    "standard_pressure": rec.standard_pressure,
                    "record_ids": [],
                    "statuses": [],
                    "input_type": rec.input_type,
                }
            group = group_map[group_key]
            slot = rec.time_slot or "默认"
            group["time_slot_values"][slot] = rec.pressure_value
            group["record_ids"].append(rec.id)
            group["statuses"].append(rec.status)

        all_groups = list(group_map.values())
        total = len(all_groups)
        offset = (page - 1) * page_size
        paged = all_groups[offset : offset + page_size]

        # 计算合并状态
        items = []
        for g in paged:
            if "rejected" in g["statuses"]:
                merged_status = "rejected"
            elif "pending" in g["statuses"]:
                merged_status = "pending"
            else:
                merged_status = "approved"

            items.append({
                "point_id": g["point_id"],
                "area": g["area"],
                "date": g["date"],
                "time_slot_values": g["time_slot_values"],
                "standard_pressure": g["standard_pressure"],
                "record_ids": g["record_ids"],
                "status": merged_status,
                "input_type": g["input_type"],
            })

        return items, total

    async def delete_merged_row(self, point_id: str, record_date: str) -> int:
        start = datetime.strptime(record_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
        end = start.replace(hour=23, minute=59, second=59)
        stmt = (
            update(PressureRecord)
            .where(
                PressureRecord.point_id == point_id,
                PressureRecord.record_time >= start,
                PressureRecord.record_time <= end,
                PressureRecord.is_deleted.is_(False),
            )
            .values(is_deleted=True)
        )
        result = await self.session.execute(stmt)
        return result.rowcount

    async def batch_delete_merged_rows(self, rows: list[dict]) -> int:
        total_deleted = 0
        for row in rows:
            total_deleted += await self.delete_merged_row(row["point_id"], row["date"])
        return total_deleted

    async def update_merged_row(
        self, point_id: str, record_date: str, time_slot_values: dict
    ) -> int:
        start = datetime.strptime(record_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
        end = start.replace(hour=23, minute=59, second=59)

        stmt = select(PressureRecord).where(
            PressureRecord.point_id == point_id,
            PressureRecord.record_time >= start,
            PressureRecord.record_time <= end,
            PressureRecord.is_deleted.is_(False),
        )
        result = await self.session.execute(stmt)
        existing = list(result.scalars().all())

        success_count = 0
        for slot, new_value in time_slot_values.items():
            record = next(
                (r for r in existing if (r.time_slot or "默认") == slot), None
            )
            if record and new_value is not None:
                record.pressure_value = int(new_value)
                success_count += 1

        await self.session.flush()
        return success_count

    # ─── Export ───

    async def get_export_by_area(
        self,
        *,
        area: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        point_id: str | None = None,
    ) -> list[dict]:
        stmt = select(PressureRecord).where(PressureRecord.is_deleted.is_(False))
        if area:
            stmt = stmt.where(PressureRecord.area == area)
        if start_date:
            stmt = stmt.where(PressureRecord.record_time >= start_date)
        if end_date:
            stmt = stmt.where(PressureRecord.record_time <= end_date)
        if point_id:
            stmt = stmt.where(PressureRecord.point_id == point_id)

        stmt = stmt.order_by(PressureRecord.record_time)
        result = await self.session.execute(stmt)
        records = list(result.scalars().all())

        # 按区域分组
        area_groups: dict[str, dict] = {}
        for rec in records:
            if rec.area not in area_groups:
                area_groups[rec.area] = {"area": rec.area, "time_slots": set(), "rows": defaultdict(dict)}
            group = area_groups[rec.area]
            slot = rec.time_slot or "默认"
            group["time_slots"].add(slot)
            date_str = rec.record_time.strftime("%Y-%m-%d")
            row_key = f"{date_str}|{rec.point_id}"
            group["rows"][row_key]["date"] = date_str
            group["rows"][row_key]["point_id"] = rec.point_id
            group["rows"][row_key]["standard_pressure"] = str(rec.standard_pressure)
            if "values" not in group["rows"][row_key]:
                group["rows"][row_key]["values"] = {}
            group["rows"][row_key]["values"][slot] = rec.pressure_value

        export_data = []
        for area_name, group in area_groups.items():
            export_data.append({
                "area": area_name,
                "time_slots": sorted(group["time_slots"]),
                "rows": list(group["rows"].values()),
            })
        return export_data

    # ─── Dashboard ───

    async def get_dashboard_stats(self) -> dict:
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        today_result = await self.session.execute(
            select(func.count()).where(
                PressureRecord.record_time >= today_start,
                PressureRecord.is_deleted.is_(False),
            )
        )
        today_count = today_result.scalar() or 0

        pending_result = await self.session.execute(
            select(func.count()).where(
                PressureRecord.status == "pending",
                PressureRecord.is_deleted.is_(False),
            )
        )
        pending_count = pending_result.scalar() or 0

        last_result = await self.session.execute(
            select(PressureRecord.record_time)
            .where(PressureRecord.is_deleted.is_(False))
            .order_by(PressureRecord.record_time.desc())
            .limit(1)
        )
        last_record_time = last_result.scalar_one_or_none()

        return {
            "today_count": today_count,
            "pending_count": pending_count,
            "last_record_time": last_record_time.isoformat() if last_record_time else None,
        }

    async def get_audit_stats(self) -> dict:
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        base = PressureRecord.is_deleted.is_(False)

        pending = await self.session.execute(
            select(func.count()).where(base, PressureRecord.status == "pending")
        )
        today_approved = await self.session.execute(
            select(func.count()).where(
                base,
                PressureRecord.status == "approved",
                PressureRecord.updated_at >= today_start,
            )
        )
        rejected = await self.session.execute(
            select(func.count()).where(base, PressureRecord.status == "rejected")
        )

        return {
            "pending_count": pending.scalar() or 0,
            "today_approved_count": today_approved.scalar() or 0,
            "rejected_count": rejected.scalar() or 0,
        }

    # ─── OcrTask ───

    async def list_ocr_tasks(
        self,
        *,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[OcrTask], int]:
        stmt = select(OcrTask).where(OcrTask.is_deleted.is_(False))
        if status:
            stmt = stmt.where(OcrTask.status == status)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(OcrTask.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def get_ocr_task_by_id(self, task_id: UUID) -> OcrTask | None:
        result = await self.session.execute(
            select(OcrTask).where(
                OcrTask.id == task_id, OcrTask.is_deleted.is_(False)
            )
        )
        return result.scalar_one_or_none()

    async def create_ocr_task(self, data: dict) -> OcrTask:
        task = OcrTask(**data)
        self.session.add(task)
        await self.session.flush()
        await self.session.refresh(task)
        return task

    async def update_ocr_task(self, task_id: UUID, data: dict) -> OcrTask | None:
        stmt = (
            update(OcrTask)
            .where(OcrTask.id == task_id, OcrTask.is_deleted.is_(False))
            .values(**data)
            .returning(OcrTask)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # ─── DataMaster ───

    async def list_data_master(
        self,
        *,
        material_name: str | None = None,
        supplier: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        source: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[DataMaster], int]:
        stmt = select(DataMaster).where(DataMaster.is_deleted.is_(False))
        if material_name:
            stmt = stmt.where(DataMaster.material_name.ilike(f"%{material_name}%"))
        if supplier:
            stmt = stmt.where(DataMaster.supplier.ilike(f"%{supplier}%"))
        if start_date:
            stmt = stmt.where(DataMaster.record_date >= start_date)
        if end_date:
            stmt = stmt.where(DataMaster.record_date <= end_date)
        if source:
            stmt = stmt.where(DataMaster.source == source)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(DataMaster.record_date.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def get_data_master_by_id(self, item_id: UUID) -> DataMaster | None:
        result = await self.session.execute(
            select(DataMaster).where(
                DataMaster.id == item_id, DataMaster.is_deleted.is_(False)
            )
        )
        return result.scalar_one_or_none()

    async def create_data_master(self, data: dict) -> DataMaster:
        item = DataMaster(**data)
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def create_data_master_batch(self, items: list[DataMaster]) -> list[DataMaster]:
        for item in items:
            self.session.add(item)
        await self.session.flush()
        for item in items:
            await self.session.refresh(item)
        return items

    async def update_data_master(self, item_id: UUID, data: dict) -> DataMaster | None:
        stmt = (
            update(DataMaster)
            .where(DataMaster.id == item_id, DataMaster.is_deleted.is_(False))
            .values(**data)
            .returning(DataMaster)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_data_master(self, item_id: UUID) -> bool:
        stmt = (
            update(DataMaster)
            .where(DataMaster.id == item_id, DataMaster.is_deleted.is_(False))
            .values(is_deleted=True)
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def batch_delete_data_master(self, ids: list[UUID]) -> int:
        if not ids:
            return 0
        stmt = (
            update(DataMaster)
            .where(DataMaster.id.in_(ids), DataMaster.is_deleted.is_(False))
            .values(is_deleted=True)
        )
        result = await self.session.execute(stmt)
        return result.rowcount

    # ─── Notification ───

    async def list_notifications(
        self,
        *,
        user_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Notification], int]:
        stmt = select(Notification).where(Notification.is_deleted.is_(False))
        if user_id:
            stmt = stmt.where(Notification.target_user_id == user_id)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(Notification.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def get_unread_count(self, user_id: str | None = None) -> int:
        stmt = select(func.count()).where(
            Notification.is_read.is_(False),
            Notification.is_deleted.is_(False),
        )
        if user_id:
            stmt = stmt.where(Notification.target_user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def create_notification(self, data: dict) -> Notification:
        item = Notification(**data)
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def mark_read(self, notification_id: UUID) -> bool:
        stmt = (
            update(Notification)
            .where(notification_id == notification_id, Notification.is_deleted.is_(False))
            .values(is_read=True)
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def mark_all_read(self, user_id: str | None = None) -> int:
        stmt = (
            update(Notification)
            .where(Notification.is_read.is_(False), Notification.is_deleted.is_(False))
            .values(is_read=True)
        )
        if user_id:
            stmt = stmt.where(Notification.target_user_id == user_id)
        result = await self.session.execute(stmt)
        return result.rowcount
