from app.modules.registration.api import router
from app.modules.registration.todos import router as todos_router

router.include_router(todos_router)

__all__ = ["router"]
