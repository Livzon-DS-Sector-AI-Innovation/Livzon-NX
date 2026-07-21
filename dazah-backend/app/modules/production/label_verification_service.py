"""Quality business workflows live here."""

import logging
from datetime import date, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.production.label_verification_models import LabelVerification
from app.modules.production.label_verification_repository import LabelVerificationRepository
from app.modules.production.label_verification_schemas import (
    LabelVerificationCreate,
    LabelVerificationResponse,
    LabelVerificationStatistics,
    LabelVerificationUpdate,
)

logger = logging.getLogger(__name__)


class LabelVerificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = LabelVerificationRepository(session)

    def _to_response(self, obj: LabelVerification) -> LabelVerificationResponse:
        return LabelVerificationResponse.model_validate(obj)

    async def get_verification(
        self, verification_id: UUID
    ) -> LabelVerificationResponse:
        """获取单条标签复核记录"""
        verification = await self.repo.get_by_id(verification_id)
        if not verification:
            raise NotFoundException("标签复核记录", str(verification_id))
        return self._to_response(verification)

    async def create_verification(
        self, data: LabelVerificationCreate
    ) -> LabelVerificationResponse:
        """创建标签复核记录"""
        # 检查视频是否已处理（去重）
        existing = await self.repo.get_by_video_file_key(data.video_file_key)
        if existing:
            logger.info(
                f"视频 {data.video_file_key} 已处理，返回已有记录"
            )
            return self._to_response(existing)

        verification = LabelVerification(
            batch_number=data.batch_number,
            product_name=data.product_name,
            production_date=data.production_date,
            expiry_date=data.expiry_date,
            total_barrels=data.total_barrels,
            standard_barrels=data.standard_barrels,
            remainder_barrel=data.remainder_barrel,
            standard_weight=data.standard_weight,
            remainder_weight=data.remainder_weight,
            total_weight=data.total_weight,
            check_batch_number=data.check_batch_number,
            check_production_date=data.check_production_date,
            check_expiry_date=data.check_expiry_date,
            check_standard_barrels=data.check_standard_barrels,
            check_remainder_barrel=data.check_remainder_barrel,
            check_total_weight=data.check_total_weight,
            check_all_barrels_identified=data.check_all_barrels_identified,
            check_exception_handled=data.check_exception_handled,
            result_status=data.result_status,
            result_summary=data.result_summary,
            video_file_key=data.video_file_key,
            video_file_name=data.video_file_name,
            video_frame_count=data.video_frame_count,
            video_fps=data.video_fps,
            verification_date=data.verification_date,
            verification_time=data.verification_time,
            remarks=data.remarks,
        )

        created = await self.repo.create(verification)
        return self._to_response(created)

    async def update_verification(
        self, verification_id: UUID, data: LabelVerificationUpdate
    ) -> LabelVerificationResponse:
        """更新标签复核记录"""
        verification = await self.repo.get_by_id(verification_id)
        if not verification:
            raise NotFoundException("标签复核记录", str(verification_id))

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(verification, field, value)

        updated = await self.repo.update(verification)
        return self._to_response(updated)

    async def delete_verification(self, verification_id: UUID) -> None:
        """删除标签复核记录（软删除）"""
        verification = await self.repo.get_by_id(verification_id)
        if not verification:
            raise NotFoundException("标签复核记录", str(verification_id))
        await self.repo.soft_delete(verification)

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
    ) -> tuple[list[LabelVerificationResponse], int]:
        """查询标签复核记录列表"""
        verifications, total = await self.repo.list_verifications(
            batch_number=batch_number,
            product_name=product_name,
            result_status=result_status,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        responses = [self._to_response(v) for v in verifications]
        return responses, total

    async def get_statistics(self) -> LabelVerificationStatistics:
        """获取标签复核统计数据"""
        stats = await self.repo.get_statistics()
        return LabelVerificationStatistics(**stats)

    async def get_by_batch_number(
        self, batch_number: str
    ) -> list[LabelVerificationResponse]:
        """根据批号查询历史记录"""
        verifications = await self.repo.get_by_batch_number(batch_number)
        return [self._to_response(v) for v in verifications]
