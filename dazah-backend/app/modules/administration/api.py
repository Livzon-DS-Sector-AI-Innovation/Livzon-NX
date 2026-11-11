from app.modules.administration.feishu_read_api import router as feishu_read_router
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["administration"])
router.include_router(feishu_read_router)
