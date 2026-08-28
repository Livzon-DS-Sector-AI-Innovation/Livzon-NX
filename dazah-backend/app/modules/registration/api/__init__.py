"""Registration API routes."""

from app.modules.registration.api.authorization_letters import (
    router as auth_letters_router,
)
from app.modules.registration.api.certificates import router as certificates_router
from app.modules.registration.api.declaration_progress import (
    router as declaration_progress_router,
)
from app.modules.registration.api.drugs import router as drugs_router
from app.modules.registration.api.fees import router as fees_router
from app.modules.registration.api.holidays import router as holidays_router
from app.modules.registration.api.knowledge import router as knowledge_router
from app.modules.registration.api.project import router as project_router
from app.modules.registration.api.project_ledger import router as project_ledger_router
from app.modules.registration.api.reference_standards import (
    router as reference_standards_router,
)
from app.modules.registration.api.reference_substances import (
    router as ref_substances_router,
)
from app.modules.registration.api.supplementary_replies import (
    router as supplementary_replies_router,
)
from app.modules.registration.api.validation_audit import (
    router as validation_audit_router,
)
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["registration"])

# Preserve the current registration entry points alongside the migrated
# project/ledger/certificate/knowledge workflows.
router.include_router(drugs_router, prefix="/drugs", tags=["申报进度-药品"])
router.include_router(holidays_router, prefix="/holidays", tags=["申报进度-节假日"])
router.include_router(
    ref_substances_router, prefix="/reference-substances", tags=["对照品说明表"]
)
router.include_router(
    reference_standards_router, prefix="/reference-standards", tags=["对照物质说明表"]
)
router.include_router(
    supplementary_replies_router, prefix="/supplementary-replies", tags=["发补回复"]
)
router.include_router(
    validation_audit_router, prefix="/validation-audit", tags=["验证文件审核"]
)

# 注册子路由
router.include_router(
    project_router,
    prefix="/project",
    tags=["申报项目"],
)
router.include_router(
    project_ledger_router,
    prefix="/project-ledger",
    tags=["申报台账"],
)
router.include_router(
    declaration_progress_router,
    prefix="/declaration-progress",
    tags=["申报进度"],
)
router.include_router(
    auth_letters_router, prefix="/authorization-letters", tags=["授权书管理"]
)
router.include_router(
    certificates_router, prefix="/certificate-management", tags=["证书管理"]
)
router.include_router(fees_router, prefix="/fees", tags=["注册费用"])
router.include_router(knowledge_router, prefix="/knowledge", tags=["注册知识库"])
