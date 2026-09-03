"""Quality API routes."""

from enum import Enum

from fastapi import APIRouter
from fastapi.routing import APIRoute

from app.modules.quality.api.complaint import router as complaint_router
from app.modules.quality.api.complaint_return_feishu import (
    router as complaint_return_feishu_router,
)
from app.modules.quality.api.cpv_import import router as cpv_import_router
from app.modules.quality.api.cpv_products import router as cpv_products_router
from app.modules.quality.api.document_catalog import router as document_catalog_router
from app.modules.quality.api.external_quality import router as external_quality_router
from app.modules.quality.api.feishu_capa import router as feishu_capa_router
from app.modules.quality.api.inspection import router as inspection_router
from app.modules.quality.api.inspection_feishu import router as inspection_feishu_router
from app.modules.quality.api.inspection_feishu_crud import (
    router as inspection_feishu_crud_router,
)
from app.modules.quality.api.inspection_submodules import (
    router as inspection_submodules_router,
)
from app.modules.quality.api.oos_oot import router as oos_oot_router
from app.modules.quality.api.oos_oot_feishu import router as oos_oot_feishu_router
from app.modules.quality.api.oot_limit import router as oot_limit_router
from app.modules.quality.api.product_quality import router as product_quality_router
from app.modules.quality.api.product_quality_feishu import (
    router as product_quality_feishu_router,
)
from app.modules.quality.api.quality_ai import router as quality_ai_router
from app.modules.quality.api.quality_capa import router as quality_capa_router
from app.modules.quality.api.quality_change import router as quality_change_router
from app.modules.quality.api.quality_contacts import router as quality_contacts_router
from app.modules.quality.api.quality_deviation import router as quality_deviation_router
from app.modules.quality.api.quality_deviation_workbench import (
    router as quality_deviation_workbench_router,
)
from app.modules.quality.api.quality_feishu_sync import (
    router as quality_feishu_sync_router,
)
from app.modules.quality.api.quality_historical_deviation import (
    router as quality_historical_deviation_router,
)
from app.modules.quality.api.quality_management import (
    router as quality_management_router,
)
from app.modules.quality.api.read_mirror import router as read_mirror_router
from app.modules.quality.api.return_recall import router as return_recall_router
from app.modules.quality.api.supplier import router as supplier_router
from app.modules.quality.api.supplier_feishu import router as supplier_feishu_router
from app.modules.quality.api.validation import router as validation_router
from app.modules.quality.api.validation_qc import router as validation_qc_router

router = APIRouter()


def _include_compatibility_routes(source: APIRouter, *, tags: list[str | Enum]) -> None:
    """Mount only compatibility endpoints not already owned by split routers.

    The migration keeps the platform-owned compatibility surface, but mounting
    both routers wholesale registers identical method/path pairs twice. Besides
    making runtime dispatch order-dependent, that produces unstable prefixed
    OpenAPI schema names. Split (migrated) routes are mounted first and therefore
    remain authoritative; only genuinely current-only endpoints are added here.
    """
    existing = {
        (route.path, method)
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods or set()
    }
    unique_router = APIRouter()
    for route in source.routes:
        if isinstance(route, APIRoute):
            methods = route.methods or set()
            if any((route.path, method) in existing for method in methods):
                continue
            existing.update((route.path, method) for method in methods)
        unique_router.routes.append(route)
    router.include_router(unique_router, tags=tags)


# Preserve the current CPV and Feishu read-mirror entry points while the
# migrated quality submodules provide the broader quality workflow.
router.include_router(cpv_products_router, prefix="/cpv", tags=["CPV-产品"])
router.include_router(cpv_import_router, prefix="/cpv", tags=["CPV-导入"])
router.include_router(read_mirror_router, tags=["Quality-Feishu-Read"])

# Mount quality management routes (deviations, CAPA, contacts, etc.)
# Q1 拆分：原 quality_management 单一路由按实体拆为 6 个子路由
router.include_router(quality_deviation_router, tags=["Quality-Management"])
router.include_router(
    quality_historical_deviation_router, tags=["Quality-Management"]
)
router.include_router(
    quality_deviation_workbench_router, tags=["Quality-Management"]
)
router.include_router(quality_change_router, tags=["Quality-Management"])
router.include_router(quality_capa_router, tags=["Quality-Management"])
router.include_router(quality_feishu_sync_router, tags=["Quality-Management"])
router.include_router(quality_ai_router, tags=["Quality-Management"])
router.include_router(quality_contacts_router, tags=["Quality-Management"])
router.include_router(validation_router, tags=["Quality-Validation"])
router.include_router(validation_qc_router, tags=["Quality-Validation-QC"])
router.include_router(feishu_capa_router, tags=["Quality-Feishu-CAPA"])

# Mount quality inspection routes
router.include_router(inspection_router, tags=["Quality-Inspection"])
router.include_router(inspection_feishu_router, tags=["Quality-Inspection-Feishu"])
router.include_router(
    inspection_feishu_crud_router, tags=["Quality-Inspection-Feishu-CRUD"]
)
router.include_router(
    inspection_submodules_router, tags=["Quality-Inspection-Submodules"]
)

# Mount new quality sub-module routes
# IMPORTANT: oos_oot_feishu_router and oot_limit_router must come before oos_oot_router
# to prevent /oos-oot/{record_id} from shadowing literal paths like /oos-oot/oos-ledger
router.include_router(oos_oot_feishu_router, tags=["Quality-OOS/OOT-Feishu"])
router.include_router(oot_limit_router, tags=["Quality-OOS/OOT-Limits"])
router.include_router(oos_oot_router, tags=["Quality-OOS/OOT"])
# IMPORTANT: complaint_return_feishu_router must come before complaint_router and
# return_recall_router
# to prevent /complaints/{id} or /return-recalls/{id} from shadowing literal paths
router.include_router(
    complaint_return_feishu_router, tags=["Quality-ComplaintReturn-Feishu"]
)
router.include_router(complaint_router, tags=["Quality-Complaint"])
router.include_router(return_recall_router, tags=["Quality-ReturnRecall"])
# supplier_feishu_router must come before supplier_router to prevent path conflicts
router.include_router(supplier_feishu_router, tags=["Quality-Supplier-Feishu"])
router.include_router(supplier_router, tags=["Quality-Supplier"])
router.include_router(
    product_quality_feishu_router, tags=["Quality-ProductQuality-Feishu"]
)
router.include_router(product_quality_router, tags=["Quality-ProductQuality"])

# Mount document catalog routes (各部门文件目录管理)
router.include_router(document_catalog_router, tags=["Quality-Document-Catalog"])

# Keep the current platform-owned compatibility surface available while the
# migrated split routers provide the newer module pages and APIs.  Split routes
# are mounted first, so exact-path conflicts continue to resolve to the
# migrated implementation.
_include_compatibility_routes(external_quality_router, tags=["Quality-External"])
_include_compatibility_routes(
    quality_management_router,
    tags=["Quality-Management-Compatibility"],
)
