"""设备模块 API 路由入口 — 瘦身后仅保留台账、巡检、检修、报修、车间与共享配置."""

from app.modules.equipment.api.claim import router as claim_router
from app.modules.equipment.api.config import router as config_router
from app.modules.equipment.api.equipment import (
    router as equipment_router,
)
from app.modules.equipment.api.inspection_feishu import (
    router as inspection_feishu_router,
)
from app.modules.equipment.api.repair_ledger import router as repair_ledger_router
from app.modules.equipment.api.workshops import router as workshops_router
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["equipment"])

# 设备台账路由
router.include_router(equipment_router)

# 巡检模块（飞书镜像只读）
router.include_router(inspection_feishu_router, prefix="/inspection")

# 检修台账（飞书镜像只读 + 频次分析 + 同步配置）
router.include_router(repair_ledger_router, prefix="/repair")

# 报修卡片操作（接单/完成/验收回调）
router.include_router(claim_router, prefix="/maintenance/work-orders")

# 报修配置（共享）
router.include_router(config_router, prefix="/maintenance/config")

# 车间注册表（工作台车间数据源）
router.include_router(workshops_router, prefix="/workshops")
