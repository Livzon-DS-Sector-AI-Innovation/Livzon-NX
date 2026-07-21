"""Quality API routes."""

from fastapi import APIRouter

from app.modules.quality.api.cpv_import import router as cpv_import_router
from app.modules.quality.api.cpv_products import router as cpv_products_router
from app.modules.quality.api.external_quality import router as external_quality_router
from app.modules.quality.api.feishu_capa import router as feishu_capa_router
from app.modules.quality.api.inspection import router as inspection_router
from app.modules.quality.api.oos_oot import router as oos_oot_router
from app.modules.quality.api.read_mirror import router as read_mirror_router
from app.modules.quality.api.quality_management import (
    router as quality_management_router,
)
from app.modules.quality.api.validation import router as validation_router

router = APIRouter()

# Mount CPV sub-routes
router.include_router(cpv_products_router, prefix="/cpv", tags=["CPV-产品"])
router.include_router(cpv_import_router, prefix="/cpv", tags=["CPV-导入"])
router.include_router(inspection_router, tags=["Quality-Inspection"])
router.include_router(oos_oot_router, tags=["Quality-OOS-OOT"])
router.include_router(external_quality_router, tags=["Quality-External"])

# Mount quality management routes (deviations, CAPA, contacts, etc.)
router.include_router(quality_management_router, tags=["Quality-Management"])
router.include_router(validation_router, tags=["Quality-Validation"])
router.include_router(feishu_capa_router, tags=["Quality-Feishu-CAPA"])
router.include_router(read_mirror_router, tags=["Quality-Feishu-Read"])
