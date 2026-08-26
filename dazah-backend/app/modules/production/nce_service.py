"""非密事件与运行偏差 service."""
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production.nce_repository import NCERepository

CN_TZ = ZoneInfo("Asia/Shanghai")


class NCEService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = NCERepository(session)

    async def list_records(
        self,
        page: Any=1,
        page_size: Any=20,
        workshop: Any=None,
        event_type: Any=None,
        date_from: Any=None,
        date_to: Any=None,
    ) -> Any:
        return await self.repo.list(
            page=page,
            page_size=page_size,
            workshop=workshop,
            event_type=event_type,
            date_from=date_from,
            date_to=date_to,
        )

    async def get_record(self, record_id: UUID) -> Any:
        return await self.repo.get_by_id(record_id)

    async def create_record(self, data: dict[str, Any]) -> Any:
        record = await self.repo.create(data)
        await self.auto_link_batches(record)
        return record

    async def update_record(self, record_id: UUID, data: dict[str, Any]) -> Any:
        record = await self.repo.update(record_id, data)
        if not record:
            raise ValueError(f"NCE {record_id} not found")
        await self.auto_link_batches(record)
        return record

    async def delete_record(self, record_id: UUID) -> Any:
        if not await self.repo.delete(record_id):
            raise ValueError(f"NCE {record_id} not found")

    async def auto_link_batches(self, event: Any) -> Any:
        """自动关联：清除旧链接 → 计算时间重叠的in_progress批次 → 插入新链接"""
        # 删除旧链接
        await self.session.execute(
            text("DELETE FROM production.nce_batch_links WHERE nce_id = :nid"),
            {"nid": event.id},
        )
        # 查找重叠批次 — 转为北京时间比较日期
        ed_date = event.event_time.astimezone(CN_TZ).date()
        rt = event.restore_time or event.event_time
        dd_date = rt.astimezone(CN_TZ).date()
        rows = await self.session.execute(
            text("""
            SELECT id FROM production.fermentation_records
            WHERE is_deleted = false AND status = 'in_progress'
              AND entry_date <= :dd
              AND (discharge_date >= :ed OR discharge_date IS NULL)
        """),
            {"ed": ed_date, "dd": dd_date},
        )
        batch_ids = [r[0] for r in rows]
        # 插入新链接
        for bid in batch_ids:
            await self.session.execute(
                text(
                    "INSERT INTO production.nce_batch_links (id, nce_id, batch_id) VALUES (gen_random_uuid(), :nid, :bid)"  # noqa: E501
                ),
                {"nid": event.id, "bid": bid},
            )
        await self.session.flush()

    async def get_affected_batches(self, event_id: UUID) -> Any:
        rows = await self.session.execute(
            text("""
            SELECT f.id, f.batch_no, f.product_name, f.fermenter, f.entry_date,
        f.discharge_date, f.status
            FROM production.nce_batch_links l
            JOIN production.fermentation_records f ON f.id = l.batch_id
            WHERE l.nce_id = :nid AND f.is_deleted = false
            ORDER BY f.fermenter
        """),
            {"nid": event_id},
        )
        return [
            {
                "id": str(r[0]),
                "batch_no": r[1],
                "product_name": r[2],
                "fermenter": r[3],
                "entry_date": r[4].isoformat() if r[4] else None,
                "discharge_date": r[5].isoformat() if r[5] else None,
                "status": r[6],
            }
            for r in rows
        ]
