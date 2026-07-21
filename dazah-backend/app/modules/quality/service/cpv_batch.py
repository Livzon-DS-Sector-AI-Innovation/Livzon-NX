"""CPV Batch service layer."""

import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.quality import repository as repo
from app.modules.quality.models.cpv_batch import CpvBatch
from app.modules.quality.schemas import CpvBatchWideResponse


async def get_batches(
    db: AsyncSession,
    product_id: uuid.UUID,
    data_type: str | None = None,
    batch_no: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[CpvBatch], int]:
    """获取批次列表"""
    return await repo.get_batches(
        db, product_id, data_type, batch_no, start_date, end_date, page, page_size
    )


async def get_batches_wide(
    db: AsyncSession,
    product_id: uuid.UUID,
    data_type: str,
    batch_no: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[CpvBatchWideResponse], int]:
    """获取批次宽表数据（参数值展开）"""
    batches, total = await get_batches(
        db, product_id, data_type, batch_no, start_date, end_date, page, page_size
    )
    
    if not batches:
        return [], total
    
    # 获取参数定义
    parameters = await repo.get_parameters(db, product_id, data_type)
    param_map = {p.id: p for p in parameters}
    
    # 获取所有批次的参数值
    batch_ids = [b.id for b in batches]
    values = await repo.get_values_by_batch_ids(db, batch_ids)
    
    # 按批次组织数据
    values_by_batch: dict[uuid.UUID, list] = {}
    for v in values:
        if v.batch_id not in values_by_batch:
            values_by_batch[v.batch_id] = []
        values_by_batch[v.batch_id].append(v)
    
    # 构建宽表响应
    result = []
    for batch in batches:
        batch_values = values_by_batch.get(batch.id, [])
        params_dict = {}
        has_abnormal = False
        
        for v in batch_values:
            param = param_map.get(v.parameter_id)
            if param:
                params_dict[param.name] = {
                    "value": v.actual_value,
                    "is_abnormal": v.is_abnormal,
                    "lower_limit": param.lower_limit,
                    "upper_limit": param.upper_limit,
                }
                if v.is_abnormal:
                    has_abnormal = True
        
        result.append(
            CpvBatchWideResponse(
                id=batch.id,
                batch_no=batch.batch_no,
                production_date=batch.production_date,
                data_type=batch.data_type,
                source=batch.source,
                parameters=params_dict,
                has_abnormal=has_abnormal,
            )
        )
    
    return result, total
