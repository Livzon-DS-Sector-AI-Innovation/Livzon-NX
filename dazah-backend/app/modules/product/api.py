from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import paginated_response, success_response
from app.modules.product.schemas import (
    ProductCreate,
    ProductResponse,
    ProductUpdate,
)
from app.modules.product.service import ProductService
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE
from app.shared.schemas import PageParams

router = create_module_router(MODULES_BY_CODE["product"])


def get_product_service(session: AsyncSession = Depends(get_db)) -> ProductService:
    return ProductService(session)


# ─── Product Routes ───

@router.get("/products", summary="产品列表")
async def list_products(
    name: str | None = Query(None, description="产品名称筛选"),
    category: str | None = Query(None, description="产品大类筛选"),
    product_type: str | None = Query(None, description="产品类别筛选"),
    keyword: str | None = Query(None, description="名称或料件编号关键词"),
    page_params: PageParams = Depends(),
    service: ProductService = Depends(get_product_service),
):
    products, total = await service.list_products(
        name=name,
        category=category,
        product_type=product_type,
        keyword=keyword,
        page=page_params.page,
        page_size=page_params.page_size,
    )
    data = [
        ProductResponse.model_validate(p).model_dump(mode="json")
        for p in products
    ]
    return paginated_response(
        data=data,
        page=page_params.page,
        page_size=page_params.page_size,
        total=total,
    )


@router.post("/products", summary="创建产品")
async def create_product(
    payload: ProductCreate,
    service: ProductService = Depends(get_product_service),
):
    product = await service.create_product(payload)
    return success_response(
        data=ProductResponse.model_validate(product).model_dump(mode="json"),
        message="产品创建成功",
        status_code=201,
    )


@router.get("/products/{product_id}", summary="产品详情")
async def get_product(
    product_id: UUID,
    service: ProductService = Depends(get_product_service),
):
    product = await service.get_product(product_id)
    return success_response(
        data=ProductResponse.model_validate(product).model_dump(mode="json"),
    )


@router.put("/products/{product_id}", summary="更新产品")
async def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    service: ProductService = Depends(get_product_service),
):
    product = await service.update_product(product_id, payload)
    return success_response(
        data=ProductResponse.model_validate(product).model_dump(mode="json"),
        message="产品更新成功",
    )


@router.delete("/products/{product_id}", summary="删除产品")
async def delete_product(
    product_id: UUID,
    service: ProductService = Depends(get_product_service),
):
    await service.delete_product(product_id)
    return success_response(message="产品删除成功")


@router.post("/products/sync-from-feishu", summary="从飞书多维表格同步产品数据")
async def sync_products_from_feishu(
    service: ProductService = Depends(get_product_service),
):
    """手动触发：从飞书多维表格拉取全部产品数据并 upsert 到本地 PG。"""
    stats = await service.sync_from_feishu()
    msg = (
        f"同步完成：新增 {stats['created']} 条，"
        f"更新 {stats['updated']} 条，失败 {stats['failed']} 条"
    )
    if stats.get("errors"):
        msg += f" | 错误: {'; '.join(stats['errors'][:3])}"
    return success_response(
        data=stats,
        message=msg,
    )


@router.get("/products/sync-status", summary="飞书同步状态")
async def get_product_sync_status(
    service: ProductService = Depends(get_product_service),
):
    """查看本地与飞书的数据同步统计。"""
    status = await service.get_sync_status()
    return success_response(
        data=status.model_dump(mode="json"),
    )


@router.post("/products/{product_id}/sync-to-feishu", summary="同步单个产品到飞书")
async def sync_product_to_feishu(
    product_id: UUID,
    service: ProductService = Depends(get_product_service),
):
    """将本地单个产品强制同步到飞书多维表格。"""
    record_id = await service.sync_to_feishu(product_id)
    return success_response(
        data={"feishu_record_id": record_id},
        message="产品已同步到飞书",
    )
