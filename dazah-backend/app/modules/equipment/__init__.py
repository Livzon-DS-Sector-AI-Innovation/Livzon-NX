from app.modules.equipment.api import router
from app.modules.equipment.todos import router as todos_router

router.include_router(todos_router)

__all__ = ["router"]
