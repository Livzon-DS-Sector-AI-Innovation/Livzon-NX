"""HTTP API for the native energy ledger.

Archived Wiki snapshots remain available as history, but the former Feishu
ingestion and mapping routes are intentionally no longer mounted.
"""

from app.modules.energy.ledger_api import router as ledger_router
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["energy"])
router.include_router(ledger_router)

__all__ = ["router"]
