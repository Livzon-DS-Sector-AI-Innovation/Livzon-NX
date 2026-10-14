"""Quality management module."""

from app.modules.quality import repository
from app.modules.quality.api import router
from app.modules.quality.todos import router as todos_router

router.include_router(todos_router)

__all__ = ["router", "repository"]
