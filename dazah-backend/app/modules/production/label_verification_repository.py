"""Quality database queries live here."""

from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production.label_verification_models import LabelVerification


class LabelVerificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, verification_id: UUID) -> LabelVerification | None:
        result = await self.session.execute(
            select(LabelVerification).where(
                LabelVerification.id == verification_id,
                LabelVerification.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_video_file_key(
        self, video_file_key: str
    ) -> LabelVerification | None:
        """根据视频文件 key 查询（用于去重）"""
        result = await self.session.execute(
            select(LabelVerification).where(
                LabelVerification.video_file_key == video_file_key,
                LabelVerification.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_verifications(
        self,
        *,
        batch_number: str | None = None,
        product_name: str | None = None,
        result_status: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "verification_time",
        sort_order: str = "desc",
    ) -> tuple[list[LabelVerification], int]:
        stmt = select(LabelVerification).where(
            LabelVerification.is_deleted.is_(False)
        )

        if batch_number:
            stmt = stmt.where(
                LabelVerification.batch_number.ilike(f"%{batch_number}%")
            )
        if product_name:
            stmt = stmt.where(
                LabelVerification.product_name.ilike(f"%{product_name}%")
            )
        if result_status:
            stmt = stmt.where(LabelVerification.result_status == result_status)
        if start_date:
            stmt = stmt.where(LabelVerification.verification_date >= start_date)
        if end_date:
            stmt = stmt.where(LabelVerification.verification_date <= end_date)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        sort_column = getattr(
            LabelVerification, sort_by, LabelVerification.verification_time
        )
        order_func = desc if sort_order == "desc" else asc
        stmt = stmt.order_by(order_func(sort_column))
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def create(self, verification: LabelVerification) -> LabelVerification:
        self.session.add(verification)
        await self.session.flush()
        await self.session.refresh(verification)
        return verification

    async def update(self, verification: LabelVerification) -> LabelVerification:
        await self.session.flush()
        await self.session.refresh(verification)
        return verification

    async def soft_delete(self, verification: LabelVerification) -> None:
        verification.is_deleted = True
        await self.session.flush()

    async def get_statistics(self) -> dict:
        """获取标签复核统计数据"""
        base_filter = LabelVerification.is_deleted.is_(False)
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)

        # 总数
        total_result = await self.session.execute(
            select(func.count()).where(base_filter)
        )
        total = total_result.scalar() or 0

        # 全部一致/存在差异
        all_match_result = await self.session.execute(
            select(func.count()).where(
                base_filter,
                LabelVerification.result_status == "全部一致",
            )
        )
        all_match = all_match_result.scalar() or 0

        has_diff_result = await self.session.execute(
            select(func.count()).where(
                base_filter,
                LabelVerification.result_status == "存在差异",
            )
        )
        has_difference = has_diff_result.scalar() or 0

        match_rate = (all_match / total * 100) if total > 0 else 0.0

        # 今日/本周/本月
        today_result = await self.session.execute(
            select(func.count()).where(
                base_filter,
                LabelVerification.verification_date == today,
            )
        )
        today_count = today_result.scalar() or 0

        week_result = await self.session.execute(
            select(func.count()).where(
                base_filter,
                LabelVerification.verification_date >= week_start,
            )
        )
        this_week_count = week_result.scalar() or 0

        month_result = await self.session.execute(
            select(func.count()).where(
                base_filter,
                LabelVerification.verification_date >= month_start,
            )
        )
        this_month_count = month_result.scalar() or 0

        # 按批号统计
        batch_stmt = (
            select(
                LabelVerification.batch_number,
                func.count().label("count"),
            )
            .where(base_filter)
            .group_by(LabelVerification.batch_number)
            .order_by(desc("count"))
            .limit(20)
        )
        batch_result = await self.session.execute(batch_stmt)
        batch_map = {row[0]: row[1] for row in batch_result.all()}

        return {
            "total": total,
            "all_match": all_match,
            "has_difference": has_difference,
            "match_rate": round(match_rate, 1),
            "today_count": today_count,
            "this_week_count": this_week_count,
            "this_month_count": this_month_count,
            "by_batch": batch_map,
        }

    async def get_by_batch_number(
        self, batch_number: str
    ) -> list[LabelVerification]:
        """根据批号查询历史记录"""
        result = await self.session.execute(
            select(LabelVerification)
            .where(
                LabelVerification.batch_number == batch_number,
                LabelVerification.is_deleted.is_(False),
            )
            .order_by(desc(LabelVerification.verification_time))
        )
        return list(result.scalars().all())
