"""Registration API routes."""

from app.modules.registration.api.authorization_letters import router as auth_letters_router
from app.modules.registration.api.drugs import router as drugs_router
from app.modules.registration.api.holidays import router as holidays_router
from app.modules.registration.api.reference_standards import router as ref_standards_router
from app.modules.registration.api.reference_substances import router as ref_substances_router
from app.modules.registration.api.supplementary_replies import router as supp_replies_router
from app.modules.registration.api.validation_audit import router as validation_audit_router
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["registration"])

# 注册子路由
router.include_router(drugs_router, prefix="/drugs", tags=["申报进度-药品"])
router.include_router(holidays_router, prefix="/holidays", tags=["申报进度-节假日"])
router.include_router(auth_letters_router, prefix="/authorization-letters", tags=["授权书管理"])
router.include_router(ref_substances_router, prefix="/reference-substances", tags=["对照品说明表"])
router.include_router(ref_standards_router, prefix="/reference-standards", tags=["对照物质说明表"])
router.include_router(supp_replies_router, prefix="/supplementary-replies", tags=["发补回复"])
router.include_router(validation_audit_router, prefix="/validation-audit", tags=["验证文件审核"])
