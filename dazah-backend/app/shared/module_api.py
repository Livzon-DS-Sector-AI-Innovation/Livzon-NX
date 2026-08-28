from fastapi import APIRouter

from app.shared.module_registry import ModuleDefinition


def create_module_router(module: ModuleDefinition) -> APIRouter:
    router = APIRouter()

    # Production is composed from many sub-routers.  Its sub-routers are
    # mounted at the same module prefix, so registering the generic root
    # endpoint in each one creates duplicate paths and operation IDs.  The
    # composed production router owns that endpoint instead.
    if module.code != "production":

        @router.get("/", summary=f"{module.name}模块信息")
        async def read_module() -> dict[str, str]:
            return module.as_dict()

    return router
