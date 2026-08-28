from enum import Enum

from fastapi import APIRouter, Depends

from app.core.llm.api import router as llm_router
from app.modules.administration import router as administration_router
from app.modules.agent import router as agent_router
from app.modules.dossier_writer import router as dossier_writer_router
from app.modules.energy import router as energy_router
from app.modules.environment import router as environment_router
from app.modules.equipment import router as equipment_router
from app.modules.hr import router as hr_router
from app.modules.procurement import router as procurement_router
from app.modules.product import router as product_router
from app.modules.production import router as production_router
from app.modules.production.label_verification_api import (
    router as label_verification_router,
)
from app.modules.quality import router as quality_router
from app.modules.registration import router as registration_router
from app.modules.regulatory_tracker import router as regulatory_tracker_router
from app.modules.research import router as research_router
from app.modules.safety import router as safety_router
from app.modules.warehouse import router as warehouse_router
from app.platform.audit.api import router as audit_router
from app.platform.identity.api import (
    auth_router,
    dept_router,
    feishu_config_router,
    feishu_router,
    personnel_router,
    sync_router,
    user_router,
)
from app.platform.identity.deps import require_module_view
from app.platform.identity.hermes_api import router as hermes_feishu_router
from app.platform.identity.rbac_api import rbac_router
from app.platform.storage.api import router as storage_router
from app.platform.system import router as system_router

api_router = APIRouter()

api_router.include_router(dept_router, prefix="/identity", tags=["组织架构"])
api_router.include_router(personnel_router, prefix="/identity", tags=["人员名单"])
api_router.include_router(auth_router, prefix="/identity", tags=["认证"])
api_router.include_router(user_router, prefix="/identity", tags=["用户信息"])
api_router.include_router(rbac_router, prefix="/identity", tags=["权限管理"])
api_router.include_router(sync_router, prefix="/identity", tags=["飞书同步"])
api_router.include_router(
    feishu_config_router,
    prefix="/identity",
    tags=["Livzon 助手飞书设置"],
)
api_router.include_router(feishu_router, prefix="/identity", tags=["Livzon 助手飞书"])
api_router.include_router(hermes_feishu_router)
api_router.include_router(system_router, prefix="/system", tags=["系统"])
api_router.include_router(audit_router, prefix="/audit", tags=["审计日志"])
api_router.include_router(storage_router)


def include_business_router(
    router: APIRouter,
    *,
    module_code: str,
    prefix: str = "",
    tags: list[str | Enum],
) -> None:
    """Mount a business router behind the grant fact-source access check."""
    api_router.include_router(
        router,
        prefix=prefix,
        tags=tags,
        dependencies=[Depends(require_module_view(module_code))],
    )


include_business_router(
    production_router, module_code="production", prefix="/production", tags=["生产管理"]
)
include_business_router(
    equipment_router, module_code="equipment", prefix="/equipment", tags=["设备管理"]
)
include_business_router(
    safety_router,
    module_code="safety",
    prefix="/safety",
    tags=["安全管理"],
)
include_business_router(
    environment_router,
    module_code="environment",
    prefix="/environment",
    tags=["环保管理"],
)
include_business_router(
    energy_router,
    module_code="energy",
    prefix="/energy",
    tags=["能源管理"],
)
include_business_router(
    warehouse_router,
    module_code="warehouse",
    prefix="/warehouse",
    tags=["仓储管理"],
)
include_business_router(
    product_router,
    module_code="product",
    prefix="/product",
    tags=["产品管理"],
)
include_business_router(
    procurement_router,
    module_code="procurement",
    prefix="/procurement",
    tags=["采购管理"],
)
include_business_router(
    administration_router,
    module_code="administration",
    prefix="/administration",
    tags=["行政管理"],
)
include_business_router(hr_router, module_code="hr", prefix="/hr", tags=["人事管理"])
include_business_router(
    research_router, module_code="research", prefix="/research", tags=["研发管理"]
)
include_business_router(
    registration_router,
    module_code="registration",
    prefix="/registration",
    tags=["注册管理"],
)
include_business_router(
    quality_router,
    module_code="quality",
    prefix="/quality",
    tags=["质量管理"],
)
include_business_router(
    label_verification_router,
    module_code="quality",
    prefix="/quality",
    tags=["质量管理 - 标签复核"],
)
include_business_router(
    regulatory_tracker_router,
    module_code="regulatory_tracker",
    tags=["法规追踪"],
)
include_business_router(
    dossier_writer_router,
    module_code="dossier_writer",
    prefix="/dossier-writer",
    tags=["申报资料撰写"],
)

api_router.include_router(llm_router, tags=["LLM配置"])
api_router.include_router(agent_router, prefix="/agent", tags=["中枢 Agent"])
