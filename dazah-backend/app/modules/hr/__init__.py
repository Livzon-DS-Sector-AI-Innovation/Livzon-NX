from app.modules.hr.api import router
from app.modules.hr.todos import router as todos_router

router.include_router(todos_router)

__all__ = ["router"]
