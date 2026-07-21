"""CPV Statistics service layer."""

import math
import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.quality import repository as repo
from app.modules.quality.schemas import (
    CpvStatisticsResponse,
    CpvTrendItem,
    CpvTrendResponse,
)


def _to_float(value: str | None) -> float | None:
    """尝试将字符串转换为浮点数"""
    if value is None or value == "":
        return None
    if value in ("未检出", "-"):
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _calc_std_dev(values: list[float]) -> float:
    """计算样本标准差"""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


def _calc_cpk(
    values: list[float],
    lower_limit: float | None,
    upper_limit: float | None,
) -> float:
    """计算CPK值

    当 lower_limit 或 upper_limit 为 None 时，自动从数据中计算：
    - LSL = min(values)
    - USL = max(values)
    """
    if not values:
        return 0.0
    
    mean = sum(values) / len(values)
    std_dev = _calc_std_dev(values)
    
    if std_dev == 0:
        return 0.0
    
    # Auto-calculate limits from data when not provided
    usl = upper_limit if upper_limit is not None else max(values)
    lsl = lower_limit if lower_limit is not None else min(values)
    
    cpk = min(usl - mean, mean - lsl) / (3 * std_dev)
    
    return max(0.0, cpk) if math.isfinite(cpk) else 0.0


async def get_statistics(
    db: AsyncSession,
    product_id: uuid.UUID,
    parameter_id: uuid.UUID,
    batch_no: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> CpvStatisticsResponse:
    """获取统计数据"""
    # 获取参数定义
    parameter = await repo.get_parameter_by_id(db, parameter_id)
    if not parameter:
        raise NotFoundException("参数", str(parameter_id))
    
    # 获取批次（使用大 page_size 确保获取所有数据用于统计）
    batches, _ = await repo.get_batches(
        db, product_id, parameter.parameter_type, batch_no, start_date, end_date,
        page=1, page_size=100000
    )
    
    if not batches:
        return CpvStatisticsResponse(
            total_batches=0,
            min_value=0.0,
            max_value=0.0,
            avg_value=0.0,
            std_dev=0.0,
            cpk_value=0.0,
            abnormal_count=0,
            lower_limit=parameter.lower_limit or 0.0,
            upper_limit=parameter.upper_limit or 0.0,
        )
    
    # 获取参数值
    batch_ids = [b.id for b in batches]
    values = await repo.get_values_by_batch_ids(db, batch_ids)
    
    # 筛选当前参数的值
    param_values = [v for v in values if v.parameter_id == parameter_id]
    
    numeric_values = []
    abnormal_count = 0
    
    for v in param_values:
        num_val = _to_float(v.actual_value)
        if num_val is not None:
            numeric_values.append(num_val)
            if v.is_abnormal:
                abnormal_count += 1
    
    if not numeric_values:
        return CpvStatisticsResponse(
            total_batches=len(batches),
            min_value=0.0,
            max_value=0.0,
            avg_value=0.0,
            std_dev=0.0,
            cpk_value=0.0,
            abnormal_count=abnormal_count,
            lower_limit=parameter.lower_limit or 0.0,
            upper_limit=parameter.upper_limit or 0.0,
        )
    
    min_value = min(numeric_values)
    max_value = max(numeric_values)
    avg_value = sum(numeric_values) / len(numeric_values)
    std_dev = _calc_std_dev(numeric_values)
    cpk_value = _calc_cpk(numeric_values, parameter.lower_limit, parameter.upper_limit)
    
    # Use auto-calculated limits from data when parameter limits are not set
    effective_lower = parameter.lower_limit if parameter.lower_limit is not None else min_value
    effective_upper = parameter.upper_limit if parameter.upper_limit is not None else max_value
    
    return CpvStatisticsResponse(
        total_batches=len(batches),
        min_value=min_value,
        max_value=max_value,
        avg_value=avg_value,
        std_dev=std_dev,
        cpk_value=cpk_value,
        abnormal_count=abnormal_count,
        lower_limit=effective_lower,
        upper_limit=effective_upper,
    )


async def get_trend_data(
    db: AsyncSession,
    product_id: uuid.UUID,
    parameter_id: uuid.UUID,
    batch_no: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> CpvTrendResponse:
    """获取趋势图数据"""
    # 获取参数定义
    parameter = await repo.get_parameter_by_id(db, parameter_id)
    if not parameter:
        raise NotFoundException("参数", str(parameter_id))
    
    # 获取批次（使用大 page_size 确保获取所有数据用于统计）
    batches, _ = await repo.get_batches(
        db, product_id, parameter.parameter_type, batch_no, start_date, end_date,
        page=1, page_size=100000
    )
    
    # 获取参数值
    batch_ids = [b.id for b in batches]
    values = await repo.get_values_by_batch_ids(db, batch_ids)
    
    # 构建批次映射
    batch_map = {b.id: b for b in batches}
    
    # Collect numeric values first to compute auto-limits
    all_numeric = []
    for v in values:
        if v.parameter_id == parameter_id:
            num_val = _to_float(v.actual_value)
            if num_val is not None:
                all_numeric.append(num_val)
    
    # Auto-calculate limits from data when parameter limits are not set
    effective_lower = parameter.lower_limit if parameter.lower_limit is not None else (min(all_numeric) if all_numeric else 0.0)
    effective_upper = parameter.upper_limit if parameter.upper_limit is not None else (max(all_numeric) if all_numeric else 0.0)
    
    # 构建趋势数据
    items = []
    for v in values:
        if v.parameter_id == parameter_id:
            batch = batch_map.get(v.batch_id)
            if batch:
                num_val = _to_float(v.actual_value)
                if num_val is not None:
                    items.append(
                        CpvTrendItem(
                            batch_no=batch.batch_no,
                            production_date=batch.production_date.isoformat(),
                            value=num_val,
                            lower_limit=effective_lower,
                            upper_limit=effective_upper,
                            is_abnormal=v.is_abnormal,
                        )
                    )
    
    # 按生产日期排序
    items.sort(key=lambda x: (x.production_date, x.batch_no))
    
    return CpvTrendResponse(
        parameter_name=parameter.name,
        parameter_unit=parameter.unit,
        items=items,
    )
