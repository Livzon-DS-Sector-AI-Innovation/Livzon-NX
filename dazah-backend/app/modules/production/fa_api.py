"""FA 苯丙氨酸 — 发酵液放罐 API"""

import logging

from fastapi import Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.modules.production.fa_models import (
    FaAcidificationRecord,
    FaDecolor1Record,
    FaFermentationBatch,
    FaFermentationSubBatch,
)
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

logger = logging.getLogger(__name__)
router = create_module_router(MODULES_BY_CODE["production"])


# ========== 格式化 ==========


def format_batch(b: FaFermentationBatch) -> dict:
    return {
        "发酵罐号": b.发酵罐号,
        "放罐日期": str(b.放罐日期) if b.放罐日期 else None,
        "放罐体积_kl": b.放罐体积_kl,
        "放罐含量_gL": b.放罐含量_gL,
        "主批自身总量_kg": b.主批自身总量_kg,
        "汇总总量_kg": b.汇总总量_kg,
        "电导_uscm": b.电导_uscm,
        "调酸量_L": b.调酸量_L,
        "酸化液滤速_ml10min": b.酸化液滤速_ml10min,
        "发酵液湿固": b.发酵液湿固,
        "产量": b.产量,
        "收率": b.收率,
        "created_at": str(b.created_at) if b.created_at else None,
        "updated_at": str(b.updated_at) if b.updated_at else None,
    }


def format_sub(s: FaFermentationSubBatch) -> dict:
    return {
        "id": str(s.id),
        "发酵批号": s.发酵批号,
        "父发酵罐号": s.父发酵罐号,
        "子批后缀": s.子批后缀,
        "放罐体积_kl": s.放罐体积_kl,
        "放罐含量_gL": s.放罐含量_gL,
        "批总量_kg": s.批总量_kg,
    }


# ========== 主批 API ==========


@router.get("/fa/fermentation/batches", summary="发酵液放罐 — 主批列表（含子批）")
async def list_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    tank_no: str | None = Query(None, description="罐号筛选"),
    session: AsyncSession = Depends(get_db),
):
    """返回主批列表，每条主批包含 C/D 子批数据"""
    # 查询条件
    q = (
        select(FaFermentationBatch)
        .where(not FaFermentationBatch.is_deleted)
        .order_by(FaFermentationBatch.放罐日期.desc().nulls_last())
    )
    count_q = (
        select(func.count())
        .select_from(FaFermentationBatch)
        .where(not FaFermentationBatch.is_deleted)
    )

    if tank_no:
        q = q.where(FaFermentationBatch.发酵罐号.ilike(f"%{tank_no}%"))
        count_q = count_q.where(FaFermentationBatch.发酵罐号.ilike(f"%{tank_no}%"))

    # 总数
    total = (await session.execute(count_q)).scalar() or 0

    # 分页
    q = q.offset((page - 1) * page_size).limit(page_size)
    batches = (await session.execute(q)).scalars().all()

    # 获取所有相关子批
    tank_nos = [b.发酵罐号 for b in batches]
    subs_by_parent: dict[str, list] = {}
    if tank_nos:
        sub_q = (
            select(FaFermentationSubBatch)
            .where(
                FaFermentationSubBatch.父发酵罐号.in_(tank_nos),
                not FaFermentationSubBatch.is_deleted,
            )
            .order_by(FaFermentationSubBatch.子批后缀)
        )
        subs = (await session.execute(sub_q)).scalars().all()
        for s in subs:
            subs_by_parent.setdefault(s.父发酵罐号, []).append(format_sub(s))

    items = []
    for b in batches:
        item = format_batch(b)
        item["子批"] = subs_by_parent.get(b.发酵罐号, [])
        items.append(item)

    return success_response(
        {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get(
    "/fa/fermentation/flat-list", summary="发酵液放罐 — 平铺列表（飞书原表格式）"
)
async def list_flat(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    tank_no: str | None = Query(None, description="罐号筛选"),
    month: int | None = Query(None, ge=1, le=12),
    session: AsyncSession = Depends(get_db),
):
    """返回平铺列表：每行=一个子批+主批所有字段，_is_first 标记 rowSpan 起始行"""
    # 按主批分页
    b_q = select(FaFermentationBatch).where(not FaFermentationBatch.is_deleted)
    count_q = (
        select(func.count())
        .select_from(FaFermentationBatch)
        .where(not FaFermentationBatch.is_deleted)
    )
    if month is not None:
        b_q = b_q.where(
            text(
                f'CASE WHEN EXTRACT(DAY FROM "放罐日期") >= 27 THEN CASE WHEN EXTRACT(MONTH FROM "放罐日期") = 12 THEN 1 ELSE EXTRACT(MONTH FROM "放罐日期") + 1 END ELSE EXTRACT(MONTH FROM "放罐日期") END = {month}'  # noqa: E501
            )
        )
        count_q = count_q.where(
            text(
                f'CASE WHEN EXTRACT(DAY FROM "放罐日期") >= 27 THEN CASE WHEN EXTRACT(MONTH FROM "放罐日期") = 12 THEN 1 ELSE EXTRACT(MONTH FROM "放罐日期") + 1 END ELSE EXTRACT(MONTH FROM "放罐日期") END = {month}'  # noqa: E501
            )
        )
    b_q = b_q.order_by(FaFermentationBatch.放罐日期.asc().nulls_last())
    if tank_no:
        b_q = b_q.where(FaFermentationBatch.发酵罐号.ilike(f"%{tank_no}%"))
        count_q = count_q.where(FaFermentationBatch.发酵罐号.ilike(f"%{tank_no}%"))

    total_batches = (await session.execute(count_q)).scalar() or 0
    b_q = b_q.offset((page - 1) * page_size).limit(page_size)
    batches = (await session.execute(b_q)).scalars().all()

    # 查所有子批
    tank_nos = [b.发酵罐号 for b in batches]
    subs_by_parent: dict[str, list] = {}
    if tank_nos:
        sub_q = (
            select(FaFermentationSubBatch)
            .where(
                FaFermentationSubBatch.父发酵罐号.in_(tank_nos),
                not FaFermentationSubBatch.is_deleted,
            )
            .order_by(FaFermentationSubBatch.子批后缀)
        )
        subs = (await session.execute(sub_q)).scalars().all()
        for s in subs:
            subs_by_parent.setdefault(s.父发酵罐号, []).append(s)

    # 拼成平铺行
    rows = []
    for b in batches:
        batch_info = format_batch(b)
        children = subs_by_parent.get(b.发酵罐号, [])
        for idx, s in enumerate(children):
            row = {**batch_info, **format_sub(s), "_is_first": idx == 0}
            rows.append(row)

    # total 按主批数返回
    return success_response(
        {
            "items": rows,
            "total": total_batches,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/fa/fermentation/batches/{tank_no}", summary="发酵液放罐 — 主批详情")
async def get_batch(
    tank_no: str,
    session: AsyncSession = Depends(get_db),
):
    b = (
        await session.execute(
            select(FaFermentationBatch).where(
                FaFermentationBatch.发酵罐号 == tank_no,
                not FaFermentationBatch.is_deleted,
            )
        )
    ).scalar_one_or_none()
    if not b:
        return success_response(None, message="记录不存在", status_code=404)

    subs = (
        (
            await session.execute(
                select(FaFermentationSubBatch)
                .where(
                    FaFermentationSubBatch.父发酵罐号 == tank_no,
                    not FaFermentationSubBatch.is_deleted,
                )
                .order_by(FaFermentationSubBatch.子批后缀)
            )
        )
        .scalars()
        .all()
    )

    result = format_batch(b)
    result["子批"] = [format_sub(s) for s in subs]
    return success_response(result)


# ========== 子批 API ==========


@router.put("/fa/fermentation/sub-batches/{sub_id}", summary="更新子批记录")
async def update_sub_batch(
    sub_id: str,
    data: dict,
    session: AsyncSession = Depends(get_db),
):
    s = (
        await session.execute(
            select(FaFermentationSubBatch).where(
                FaFermentationSubBatch.id == sub_id,
                not FaFermentationSubBatch.is_deleted,
            )
        )
    ).scalar_one_or_none()
    if not s:
        return success_response(None, message="子批不存在", status_code=404)
    for k, v in data.items():
        if hasattr(s, k):
            setattr(s, k, v)
    await session.commit()
    return success_response(format_sub(s), message="更新成功")


# ========== 酸化过滤 API ==========


@router.get("/fa/acidification/flat-list", summary="酸化过滤 — 平铺列表")
async def list_acidification(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    batch_no: str | None = Query(None, description="批号筛选"),
    month: int | None = Query(None, ge=1, le=12),
    session: AsyncSession = Depends(get_db),
):
    """返回平铺列表，_is_first 标记 rowSpan 起始行"""
    q = select(FaAcidificationRecord).order_by(FaAcidificationRecord.id.asc())
    count_q = select(func.count()).select_from(FaAcidificationRecord)

    if batch_no:
        q = q.where(FaAcidificationRecord.批号.ilike(f"%{batch_no}%"))
        count_q = count_q.where(FaAcidificationRecord.批号.ilike(f"%{batch_no}%"))
    if month is not None:
        q = q.where(
            text(
                f'CASE WHEN EXTRACT(DAY FROM "日期") >= 27 THEN CASE WHEN EXTRACT(MONTH FROM "日期") = 12 THEN 1 ELSE EXTRACT(MONTH FROM "日期") + 1 END ELSE EXTRACT(MONTH FROM "日期") END = {month}'  # noqa: E501
            )
        )
        count_q = count_q.where(
            text(
                f'CASE WHEN EXTRACT(DAY FROM "日期") >= 27 THEN CASE WHEN EXTRACT(MONTH FROM "日期") = 12 THEN 1 ELSE EXTRACT(MONTH FROM "日期") + 1 END ELSE EXTRACT(MONTH FROM "日期") END = {month}'  # noqa: E501
            )
        )

    total = (await session.execute(count_q)).scalar() or 0
    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(q)).scalars().all()

    items = []
    last_batch = ""
    for r in rows:
        # 日期格式化：2025-12-27 → 12月27日
        date_str = None
        if r.日期:
            date_str = f"{r.日期.month}月{r.日期.day}日"
        item = {
            "id": r.id,
            "日期": date_str,
            "批号": r.批号,
            "发酵液体积（kl)": r.发酵液体积_kl,
            "发酵液含量（g/L）": r.发酵液含量_gL,
            "发酵液罐产（kg）": r.发酵液罐产_kg,
            "用酸量（95-98%浓硫酸）": r.用酸量,
            "PH（酸化后）": r.PH酸化后,
            "酸化液体积（kl)": r.酸化液体积_kl,
            "理论酸化液含量（g/L）": r.理论酸化液含量_gL,
            "PH": r.PH,
            "膜滤液体积（KL）": r.膜滤液体积_KL,
            "膜滤液含量（g/L）": r.膜滤液含量_gL,
            "膜滤液产品量（kg）": r.膜滤液产品量_kg,
            "膜滤液产品总量（kg）": r.膜滤液产品总量_kg,
            "本批低单位含量（g/L）": r.本批低单位含量_gL,
            "本批低单位体积（KL）": r.本批低单位体积_KL,
            "本批低单位苯产品（kg）": r.本批低单位苯产品_kg,
            "本批低单位量（kg）": r.本批低单位量_kg,
            "上批套用低单位量（kg）": r.上批套用低单位量_kg,
            "批收率": r.批收率,
            "顶洗前体积（kl）": r.顶洗前体积_kl,
            "尾液含量（g/L）": r.尾液含量_gL,
            "渣含量（g/L）": r.渣含量_gL,
            "体积（罐渣+膜渣（kl）": r.体积_罐渣膜渣_kl,
            "渣产品量（kg）": r.渣产品量_kg,
            "渣损失率（渣苯丙量/罐产）": r.渣损失率,
            "渣体积/发酵液体积": r.渣体积_发酵液体积,
            "酸化液/发酵液体积": r.酸化液_发酵液体积,
            "滤液体积/发酵液体积": r.滤液体积_发酵液体积,
            "平衡率": r.平衡率,
            "消泡剂使用量（L）": r.消泡剂使用量_L,
        }
        item["_is_first"] = item["批号"] != last_batch
        last_batch = item["批号"] or ""
        items.append(item)

    return success_response(
        {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


# ========== 一次脱色过滤 API ==========


@router.get("/fa/decolor1/list", summary="一次脱色过滤 — 列表")
async def list_decolor1(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    month: int | None = Query(None, ge=1, le=12),
    session: AsyncSession = Depends(get_db),
):
    q = select(FaDecolor1Record).order_by(FaDecolor1Record.id.asc())
    count_q = select(func.count()).select_from(FaDecolor1Record)
    if month is not None:
        q = q.where(
            text(
                f'CASE WHEN EXTRACT(DAY FROM "日期") >= 27 THEN CASE WHEN EXTRACT(MONTH FROM "日期") = 12 THEN 1 ELSE EXTRACT(MONTH FROM "日期") + 1 END ELSE EXTRACT(MONTH FROM "日期") END = {month}'  # noqa: E501
            )
        )
        count_q = count_q.where(
            text(
                f'CASE WHEN EXTRACT(DAY FROM "日期") >= 27 THEN CASE WHEN EXTRACT(MONTH FROM "日期") = 12 THEN 1 ELSE EXTRACT(MONTH FROM "日期") + 1 END ELSE EXTRACT(MONTH FROM "日期") END = {month}'  # noqa: E501
            )
        )
    total = (await session.execute(count_q)).scalar() or 0
    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(q)).scalars().all()

    items = []
    for r in rows:
        date_str = f"{r.日期.month}月{r.日期.day}日" if r.日期 else None
        items.append(
            {
                "id": r.id,
                "日期": date_str,
                "批号": r.批号,
                "体积(kl)": r.体积_kl,
                "含量(g/L)": r.含量_gL,
                "电导(us/cm)": r.电导_uscm,
                "调前电导碳柱(us/cm)": r.调前电导碳柱,
                "混合含量(g/L)": r.混合含量_gL,
                "母液体积(kl)": r.母液体积_kl,
                "母液含量(g/L)": r.母液含量_gL,
                "电导(us/cm)2": r.电导2,
                "活性炭添加量(kg)": r.活性炭添加量_kg,
                "碳后含量(g/L)": r.碳后含量_gL,
                "湿重(kg）": r.湿碳_kg,
                "收率": r.收率,
                "产品量(kg)": r.产品量_kg,
                "滤损失率": r.滤损失率,
                "备注": r.备注,
            }
        )
    return success_response(
        {"items": items, "total": total, "page": page, "page_size": page_size}
    )


@router.get("/fa/mvr/list", summary="MVR浓缩 — 列表")
async def list_mvr(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    month: int | None = Query(None, ge=1, le=12),
    session: AsyncSession = Depends(get_db),
):
    from app.modules.production.fa_models import FaMvrRecord

    q = select(FaMvrRecord).order_by(FaMvrRecord.id.asc())
    count_q = select(func.count()).select_from(FaMvrRecord)
    if month is not None:
        q = q.where(
            text(
                f'CASE WHEN EXTRACT(DAY FROM "日期") >= 27 THEN CASE WHEN EXTRACT(MONTH FROM "日期") = 12 THEN 1 ELSE EXTRACT(MONTH FROM "日期") + 1 END ELSE EXTRACT(MONTH FROM "日期") END = {month}'  # noqa: E501
            )
        )
        count_q = count_q.where(
            text(
                f'CASE WHEN EXTRACT(DAY FROM "日期") >= 27 THEN CASE WHEN EXTRACT(MONTH FROM "日期") = 12 THEN 1 ELSE EXTRACT(MONTH FROM "日期") + 1 END ELSE EXTRACT(MONTH FROM "日期") END = {month}'  # noqa: E501
            )
        )
    total = (await session.execute(count_q)).scalar() or 0
    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(q)).scalars().all()
    items = []
    for r in rows:
        date_str = f"{r.日期.month}月{r.日期.day}日" if r.日期 else None
        items.append(
            {
                "id": r.id,
                "日期": date_str,
                "白班进料/m3": r.白班进料,
                "白班出料/m3": r.白班出料,
                "白班进料合计/m3": r.白班进料合计,
                "白班进料累计合计/m3": r.白班进料累计合计,
                "夜班进料/m3": r.夜班进料,
                "夜班出料/m3": r.夜班出料,
                "夜班进料合计/m3": r.夜班进料合计,
                "夜班进料累计合计/m3": r.夜班进料累计合计,
                "备注": r.备注,
            }
        )
    return success_response(
        {"items": items, "total": total, "page": page, "page_size": page_size}
    )


@router.get("/fa/mother-liquor/list", summary="母液溶粉 — 列表")
async def list_mother_liquor(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    month: int | None = Query(None, ge=1, le=12),
    session: AsyncSession = Depends(get_db),
):
    from app.modules.production.fa_models import FaMotherLiquorRecord

    q = select(FaMotherLiquorRecord).order_by(FaMotherLiquorRecord.id.asc())
    count_q = select(func.count()).select_from(FaMotherLiquorRecord)
    if month is not None:
        q = q.where(
            text(
                f'CASE WHEN EXTRACT(DAY FROM "日期") >= 27 THEN CASE WHEN EXTRACT(MONTH FROM "日期") = 12 THEN 1 ELSE EXTRACT(MONTH FROM "日期") + 1 END ELSE EXTRACT(MONTH FROM "日期") END = {month}'  # noqa: E501
            )
        )
        count_q = count_q.where(
            text(
                f'CASE WHEN EXTRACT(DAY FROM "日期") >= 27 THEN CASE WHEN EXTRACT(MONTH FROM "日期") = 12 THEN 1 ELSE EXTRACT(MONTH FROM "日期") + 1 END ELSE EXTRACT(MONTH FROM "日期") END = {month}'  # noqa: E501
            )
        )
    total = (await session.execute(count_q)).scalar() or 0
    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(q)).scalars().all()
    items = []
    for r in rows:
        date_str = f"{r.日期.month}月{r.日期.day}日" if r.日期 else None
        items.append(
            {
                "id": r.id,
                "日期": date_str,
                "批号": r.批号,
                "母液打料量(m3)": r.母液打料量,
                "溶解体积(m3)": r.溶解体积,
                "溶解含量(g/L)": r.溶解含量,
                "电导(ms/cm)": r.电导,
                "ph": r.ph,
                "备注": r.备注,
            }
        )
    return success_response(
        {"items": items, "total": total, "page": page, "page_size": page_size}
    )


@router.get("/fa/plate-recovery/list", summary="板框回收 — 列表")
async def list_plate_recovery(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    month: int | None = Query(None, ge=1, le=12),
    session: AsyncSession = Depends(get_db),
):
    from app.modules.production.fa_models import FaPlateRecoveryRecord

    q = select(FaPlateRecoveryRecord).order_by(FaPlateRecoveryRecord.id.asc())
    count_q = select(func.count()).select_from(FaPlateRecoveryRecord)
    if month is not None:
        q = q.where(
            text(
                f'CASE WHEN EXTRACT(DAY FROM "日期") >= 27 THEN CASE WHEN EXTRACT(MONTH FROM "日期") = 12 THEN 1 ELSE EXTRACT(MONTH FROM "日期") + 1 END ELSE EXTRACT(MONTH FROM "日期") END = {month}'  # noqa: E501
            )
        )
        count_q = count_q.where(
            text(
                f'CASE WHEN EXTRACT(DAY FROM "日期") >= 27 THEN CASE WHEN EXTRACT(MONTH FROM "日期") = 12 THEN 1 ELSE EXTRACT(MONTH FROM "日期") + 1 END ELSE EXTRACT(MONTH FROM "日期") END = {month}'  # noqa: E501
            )
        )
    total = (await session.execute(count_q)).scalar() or 0
    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(q)).scalars().all()
    items = []
    for r in rows:
        ds = f"{r.日期.month}月{r.日期.day}日" if r.日期 else None
        items.append(
            {
                "id": r.id,
                "日期": ds,
                "白班板框进料量/方": r.白班板框进料量,
                "白班板框拆卸回收粉包数": r.白班板框拆卸回收粉包数,
                "白班分液罐投回收粉包数/包": r.白班分液罐投回收粉包数,
                "白班分液罐体积/方": r.白班分液罐体积,
                "复滤粉拆包数": r.复滤粉拆包数,
                "夜班板框进料量/方": r.夜班板框进料量,
                "夜班板框拆卸回收粉包数": r.夜班板框拆卸回收粉包数,
                "夜班分液罐投回收粉包数/包": r.夜班分液罐投回收粉包数,
                "夜班分液罐体积/方": r.夜班分液罐体积,
                "复滤粉拆包数(夜)": r.复滤粉拆包数夜,
                "白班装车体积": r.白班装车体积,
                "废液槽接收体积": r.废液槽接收体积,
                "总进料体积（m3/天）": r.总进料体积,
                "累计进料体积m3": r.累计进料体积,
            }
        )
    return success_response(
        {"items": items, "total": total, "page": page, "page_size": page_size}
    )


@router.get("/fa/decolor-centrifuge/list", summary="脱色离心 — 列表")
async def list_decolor_centrifuge(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    month: int | None = Query(None, ge=1, le=12),
    session: AsyncSession = Depends(get_db),
):
    where = (
        ""
        if month is None
        else f' WHERE CASE WHEN EXTRACT(DAY FROM "日期") >= 27 THEN CASE WHEN EXTRACT(MONTH FROM "日期") = 12 THEN 1 ELSE EXTRACT(MONTH FROM "日期") + 1 END ELSE EXTRACT(MONTH FROM "日期") END = {month}'  # noqa: E501
    )
    params = {"limit": page_size, "offset": (page - 1) * page_size}
    q = text(
        f"SELECT * FROM production.fa_decolor_centrifuge_records{where} ORDER BY id LIMIT :limit OFFSET :offset"  # noqa: E501
    )
    total = (
        await session.execute(
            text(
                f"SELECT count(*) FROM production.fa_decolor_centrifuge_records{where}"
            ),
            params,
        )
    ).scalar() or 0
    rows = (await session.execute(q, params)).mappings().all()
    items = []
    for r in rows:
        d = r.get("日期")
        ds = f"{d.month}月{d.day}日" if hasattr(d, "month") and d else None
        items.append(
            {
                "id": r["id"],
                "日期": ds,
                "批号": r.get("批号"),
                "进料体积（kl）": r.get("进料体积（kl）"),
                "出料体积（kl）": r.get("出料体积（kl）"),
                "顶洗时长（min）": r.get("顶洗时长（min）"),
                "甩料车数": r.get("甩料车数"),
                "水分（%）": r.get("水分（%）"),
                "体积（kl）": r.get("体积（kl）"),
                "炭脱PH": r.get("炭脱PH"),
                "炭前真实含量（g/L）": r.get("炭前真实含量（g/L）"),
                "炭前总量": r.get("炭前总量"),
                "活性炭用量（kg)": r.get("活性炭用量（kg)"),
                "活性炭品牌": r.get("活性炭品牌"),
                "炭后真实含量(g/L）": r.get("炭后真实含量(g/L）"),
                "透光（%）": r.get("透光（%）"),
                "亚硫酸氢钠（kg）": r.get("亚硫酸氢钠（kg）"),
                "顶洗时长（min)2": r.get("顶洗时长（min)2"),
                "收率": r.get("收率"),
                "二次离心_批号": r.get("二次离心_批号"),
                "二次离心_甩料车数": r.get("二次离心_甩料车数"),
                "二次离心_顶洗次数": r.get("二次离心_顶洗次数"),
            }
        )
    return success_response(
        {"items": items, "total": total, "page": page, "page_size": page_size}
    )


@router.get("/fa/intermediate/list", summary="母液中间体 — 列表")
async def list_intermediate(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    month: int | None = Query(None, ge=1, le=12),
    session: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text as stext

    where = (
        ""
        if month is None
        else f' WHERE CASE WHEN EXTRACT(DAY FROM "日期") >= 27 THEN CASE WHEN EXTRACT(MONTH FROM "日期") = 12 THEN 1 ELSE EXTRACT(MONTH FROM "日期") + 1 END ELSE EXTRACT(MONTH FROM "日期") END = {month}'  # noqa: E501
    )
    params = {"limit": page_size, "offset": (page - 1) * page_size}
    q = stext(
        f"SELECT * FROM production.fa_intermediate_records{where} ORDER BY id LIMIT :limit OFFSET :offset"  # noqa: E501
    )
    total = (
        await session.execute(
            stext(f"SELECT count(*) FROM production.fa_intermediate_records{where}"),
            params,
        )
    ).scalar() or 0
    rows = (await session.execute(q, params)).mappings().all()
    items = []
    for r in rows:
        d = r.get("日期")
        ds = f"{d.month}月{d.day}日" if hasattr(d, "month") and d else None
        items.append(
            {
                "id": r["id"],
                "日期": ds,
                "当日母液总体积/方": r.get("当日母液总体积/方"),
                "顶水回流/方6#板框": r.get("顶水回流/方6#板框"),
                "当日结晶液产母液量（方）": r.get("当日结晶液产母液量（方）"),
                "一次离心日用水量（方）": r.get("一次离心日用水量（方）"),
                "一次甩料车数": r.get("一次甩料车数"),
                "离心每车平均用水量（L)160": r.get("离心每车平均用水量（L)160"),
                "三效产生一次母液量（方）": r.get("三效产生一次母液量（方）"),
                "三效单车产母液量(L)410": r.get("三效单车产母液量(L)410"),
                "合计570": r.get("合计570"),
                "二次母液总量": r.get("二次母液总量"),
                "二次离心日用水量（方）": r.get("二次离心日用水量（方）"),
                "二次甩料车数": r.get("二次甩料车数"),
                "离心每车平均用水量(L)170左右": r.get("离心每车平均用水量(L)170左右"),
                "合计750": r.get("合计750"),
            }
        )
    return success_response(
        {"items": items, "total": total, "page": page, "page_size": page_size}
    )


# ========== 月度平均值 API ==========

AVG_TABLES = {
    "fermentation_batches": (
        "fa_fermentation_monthly",
        "放罐日期",
    ),  # 视图：JOIN 子批表取体积/含量
    "acidification_records": ("fa_acidification_records", "日期"),
    "decolor1_records": ("fa_decolor1_records", "日期"),
    "mvr_records": ("fa_mvr_records", "日期"),
    "mother_liquor_records": ("fa_mother_liquor_records", "日期"),
    "plate_recovery_records": ("fa_plate_recovery_records", "日期"),
    "decolor_centrifuge_records": ("fa_decolor_centrifuge_records", "日期"),
    "intermediate_records": ("fa_intermediate_records", "日期"),
}


@router.get("/fa/monthly-averages", summary="月度平均值")
async def monthly_averages(
    table: str = Query(..., description="表名"),
    session: AsyncSession = Depends(get_db),
):
    if table not in AVG_TABLES:
        return success_response(None, message=f"未知表: {table}", status_code=400)
    tbl, date_col = AVG_TABLES[table]

    cols_sql = text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'production' AND table_name = :tbl
        AND data_type = 'double precision' ORDER BY ordinal_position
    """)
    col_rows = (await session.execute(cols_sql, {"tbl": tbl})).fetchall()
    num_cols = [
        r[0] for r in col_rows if r[0] not in ("created_at", "updated_at", "is_deleted")
    ]
    if not num_cols:
        return success_response({"data": [], "columns": []})

    avg_exprs = ", ".join(f'ROUND(AVG("{c}")::numeric, 2) AS "{c}"' for c in num_cols)
    sql = text(f"""
        SELECT CASE WHEN EXTRACT(DAY FROM "{date_col}") >= 27
            THEN to_char("{date_col}" + INTERVAL '5 days', 'FMMM"月"')
            ELSE to_char("{date_col}", 'FMMM"月"')
        END AS "月份", {avg_exprs}
        FROM production."{tbl}" WHERE "{date_col}" IS NOT NULL
        GROUP BY 1 ORDER BY MIN("{date_col}")
    """)
    rows = (await session.execute(sql)).mappings().all()
    return success_response({"columns": num_cols, "data": [dict(r) for r in rows]})


# ========== 手动同步 API ==========


@router.post("/fa/sync/trigger", summary="手动触发 FA 飞书同步")
async def trigger_fa_sync(
    data: dict = {},
    session: AsyncSession = Depends(get_db),
):
    """同 MC 的 /mc/sync/trigger"""
    modules = data.get(
        "modules",
        [
            "fermentation",
            "acidification",
            "decolor1",
            "mvr",
            "mother_liquor",
            "plate_recovery",
            "decolor_centrifuge",
            "intermediate",
        ],
    )
    from app.modules.production.fa_feishu_scheduler import run_fa_sync

    results = await run_fa_sync(modules, session)
    errors = [m for m, r in results.items() if isinstance(r, dict) and "error" in r]
    return success_response(
        {"results": results, "errors": len(errors)},
        message=f"同步完成: {len(results) - len(errors)}/{len(results)} 成功",
    )
