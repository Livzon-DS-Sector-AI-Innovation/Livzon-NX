from app.modules.safety.api import router
from app.modules.safety.todos import router as todos_router

router.include_router(todos_router)

__all__ = ["router"]
