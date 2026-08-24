# ruff: noqa: E402, I001
import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

import app.modules.agent.models as _agent_models  # noqa: F401
import app.platform.audit.models as _audit_models  # noqa: F401

# Ensure platform models are registered in SQLAlchemy metadata
import app.platform.identity.models as _identity_models  # noqa: F401
from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.llm import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
)
from app.core.response import error_response
from app.modules.regulatory_tracker.tasks.sync_tasks import (
    start_scheduler,
    stop_scheduler,
)
from app.platform.audit import AuditMiddleware

settings = get_settings()

__all__ = ["app"]

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# 抑制第三方库的 DEBUG 日志噪音
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# ── MCP 服务初始化（模块级别，确保 lifespan 可合并）──
from app.modules.agent.tool_registration import ensure_agent_tools_registered  # noqa: E402
from app.modules.equipment import mcp_tools  # noqa: E402, F401 — 触发 @mcp.tool() 注册
from app.modules.hr import mcp_tools as hr_mcp_tools  # noqa: E402, F401
from app.modules.quality import mcp_tools as quality_mcp_tools  # noqa: E402, F401
from app.modules.registration import mcp_tools as registration_mcp_tools  # noqa: E402, F401
from app.modules.warehouse import mcp_tools as warehouse_mcp_tools  # noqa: E402, F401
from app.platform.mcp.middleware import build_mcp_middleware  # noqa: E402
from app.platform.mcp.server import get_mcp_app  # noqa: E402

ensure_agent_tools_registered()
mcp_middleware = build_mcp_middleware()
mcp_asgi = get_mcp_app(path="/", middleware=mcp_middleware)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting %s (%s)", settings.APP_NAME, settings.APP_ENV)

    from app.platform.identity.service import bootstrap_local_users

    await bootstrap_local_users()

    # RBAC/menu seeds are additive and idempotent. Existing module grants,
    # users and custom menus are never deleted or overwritten.
    from app.core.database import async_session_factory
    from app.platform.identity.rbac import seed_menus, seed_permissions

    try:
        async with async_session_factory() as seed_db:
            await seed_permissions(seed_db)
    except Exception:
        logger.exception("RBAC permission seed failed (non-fatal)")
    try:
        async with async_session_factory() as seed_db:
            await seed_menus(seed_db)
    except Exception:
        logger.exception("RBAC menu seed failed (non-fatal)")

    from app.modules.procurement.material_source import reset_interrupted_syncs

    try:
        async with async_session_factory() as session:
            await reset_interrupted_syncs(session)
    except Exception:
        logger.exception("Failed to reset interrupted procurement material sync status")

    from app.modules.procurement.api import clear_stale_material_sync_lock

    await clear_stale_material_sync_lock()

    from app.modules.warehouse.feishu_events import register_feishu_event_handlers

    register_feishu_event_handlers()

    from app.modules.equipment.scheduler import (
        maintenance_plan_loop,
        stop_maintenance_plan_flag,
        stop_timeout_flag,
        timeout_scan_loop,
    )
    from app.platform.identity.scheduler import (
        member_sync_loop,
        stop_member_sync_flag,
    )

    start_scheduler()
    maintenance_plan_task = asyncio.ensure_future(maintenance_plan_loop())
    timeout_task = asyncio.ensure_future(timeout_scan_loop())
    member_task = asyncio.ensure_future(member_sync_loop())

    hr_member_task: asyncio.Task[None] | None = None
    try:
        from app.modules.hr.contract_settings_api import hr_member_sync_loop

        hr_member_task = asyncio.create_task(hr_member_sync_loop())
    except Exception:
        logger.exception("HR member sync task could not start (non-fatal)")

    # ── 仓储模块飞书 WebSocket 长连接（模块独立应用凭据） ──
    from app.modules.warehouse.ws_client import (
        set_main_loop as set_warehouse_ws_main_loop,
    )
    from app.modules.warehouse.ws_client import (
        start_ws_from_db as start_warehouse_ws,
    )

    set_warehouse_ws_main_loop(asyncio.get_running_loop())
    await start_warehouse_ws()

    # ── 设备模块飞书 WebSocket 长连接（独立交互机器人，原生 WebSocket） ──
    equipment_ws_task: asyncio.Task[None] | None = None
    if settings.EQUIPMENT_FEISHU_APP_ID and settings.EQUIPMENT_FEISHU_APP_SECRET:
        from app.modules.equipment.feishu.ws_client import start_equipment_ws

        equipment_ws_task = asyncio.create_task(start_equipment_ws())

    # ── 安全模块专属飞书事件订阅（WebSocket 长连接，独立应用凭据）──
    from app.modules.safety.feishu.event_client import start_ws, stop_ws

    safety_ws_task = asyncio.create_task(start_ws())

    # ── 安全模块定时任务调度引擎 ──
    from app.modules.safety.scheduler import (
        scheduled_task_loop,
        stop_scheduled_task_flag,
    )

    scheduler_task = asyncio.create_task(scheduled_task_loop())

    # ── 统一调度引擎（平台级，各模块可渐进迁移）──
    from app.platform.scheduler import SchedulerEngine, SchedulerRegistry

    scheduler_registry = SchedulerRegistry()
    scheduler_engine = SchedulerEngine(scheduler_registry)

    from app.modules.equipment.scheduled import (
        InspectionScheduleGenerator,
    )
    from app.modules.energy.scheduler import EnergyWikiSyncGenerator
    from app.modules.hr.scheduler import (
        ContractExpiryReminderGenerator,
        ContractSignReminderGenerator,
        MailFetchScanner,
        OffboardingReminderGenerator,
        ResumeFolderScanner,
    )
    from app.modules.quality.scheduled import ChangeActionPlanReminderGenerator
    from app.modules.registration.scheduled import CertificateReminderGenerator
    from app.modules.warehouse.scheduler import (
        WarehouseFeishuAnalysisGenerator,
        WarehouseFeishuDailySyncGenerator,
    )
    from app.platform.integrations.feishu.read_scheduler import (
        QualityFeishuReadDailySyncGenerator,
    )
    from app.modules.agent.scheduled import (
        AgentAccessScopeSyncGenerator,
        AgentAutomationGenerator,
        AgentPushDeliveryGenerator,
    )

    scheduler_registry.register_generator(AgentAccessScopeSyncGenerator())
    scheduler_registry.register_generator(AgentAutomationGenerator())
    scheduler_registry.register_generator(AgentPushDeliveryGenerator())
    scheduler_registry.register_generator(InspectionScheduleGenerator())
    scheduler_registry.register_generator(EnergyWikiSyncGenerator())
    scheduler_registry.register_generator(WarehouseFeishuDailySyncGenerator())
    scheduler_registry.register_generator(WarehouseFeishuAnalysisGenerator())
    scheduler_registry.register_generator(QualityFeishuReadDailySyncGenerator())
    scheduler_registry.register_generator(CertificateReminderGenerator())
    scheduler_registry.register_generator(ChangeActionPlanReminderGenerator())
    scheduler_registry.register_generator(OffboardingReminderGenerator())
    scheduler_registry.register_generator(ContractExpiryReminderGenerator())
    scheduler_registry.register_generator(ContractSignReminderGenerator())
    scheduler_registry.register_generator(ResumeFolderScanner())
    scheduler_registry.register_generator(MailFetchScanner())

    try:
        from app.modules.warehouse.scheduled import warehouse_sync_task

        scheduler_registry.register_task(warehouse_sync_task)
    except Exception:
        logger.exception("Warehouse scheduled sync could not register (non-fatal)")

    # ── 生产模块飞书电子表格定时同步（MC/FA/DR）──
    from app.modules.production.mc_feishu_sheets_sync import start_mc_sync_scheduler

    start_mc_sync_scheduler()
    from app.modules.production.fa_feishu_scheduler import start_fa_sync_scheduler

    start_fa_sync_scheduler()
    from app.modules.production.dr_feishu_sync import start_dr_sync_scheduler

    start_dr_sync_scheduler()

    scheduler_engine_task = asyncio.create_task(scheduler_engine.run())

    logger.info("Background tasks started")

    yield

    stop_scheduler()
    stop_maintenance_plan_flag.set()
    stop_timeout_flag.set()
    stop_member_sync_flag.set()

    # 停止安全模块 WebSocket
    await stop_ws()
    safety_ws_task.cancel()

    # 停止定时任务调度引擎
    stop_scheduled_task_flag.set()
    scheduler_task.cancel()

    # ── 停止统一调度引擎 ──
    scheduler_engine.stop()
    try:
        await asyncio.wait_for(scheduler_engine_task, timeout=10)
    except (TimeoutError, asyncio.CancelledError):
        pass

    # 停止设备模块 WebSocket
    if equipment_ws_task:
        from app.modules.equipment.feishu.ws_client import stop_equipment_ws

        await stop_equipment_ws()
        equipment_ws_task.cancel()

    from app.modules.warehouse.ws_client import stop_ws as stop_warehouse_ws

    await stop_warehouse_ws()

    # ── 停止生产模块飞书同步调度器 ──
    from app.modules.production.mc_feishu_sheets_sync import stop_mc_sync_scheduler

    stop_mc_sync_scheduler()
    from app.modules.production.fa_feishu_scheduler import stop_fa_sync_scheduler

    stop_fa_sync_scheduler()
    from app.modules.production.dr_feishu_sync import stop_dr_sync_scheduler

    stop_dr_sync_scheduler()

    maintenance_plan_task.cancel()
    timeout_task.cancel()
    member_task.cancel()
    if hr_member_task is not None:
        hr_member_task.cancel()

    logger.info("Shutting down %s", settings.APP_NAME)


from fastmcp.utilities.lifespan import combine_lifespans  # noqa: E402

app = FastAPI(
    title=settings.APP_NAME,
    description="原料药事业部工厂基座系统",
    version="0.1.0",
    lifespan=combine_lifespans(lifespan, mcp_asgi.lifespan),
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(AuditMiddleware)

# Enforce the same RBAC decision used by the permission simulator. In the
# current default ``MODULE_ACCESS_MODE=all`` it keeps the existing behavior;
# deployments opting into ``roles`` get path-level read/write enforcement.
from app.platform.identity.permission_middleware import PermissionMiddleware  # noqa: E402

app.add_middleware(PermissionMiddleware)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)

# ── 挂载 MCP 服务（AI Agent 协议入口）──
app.mount("/mcp", mcp_asgi, name="mcp")
logger.info("MCP server mounted at /mcp")


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return error_response(
        message=exc.message,
        detail=exc.detail_msg,
        status_code=exc.status_code,
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    return error_response(
        message=str(exc.detail),
        status_code=exc.status_code,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = exc.errors()
    detail = "; ".join(f"{e.get('loc', [''])[-1]}: {e.get('msg', '')}" for e in errors)
    return error_response(
        message="请求参数校验失败",
        detail=detail,
        status_code=422,
    )


@app.exception_handler(IntegrityError)
async def database_integrity_exception_handler(
    request: Request, _exc: IntegrityError
) -> JSONResponse:
    logger.warning(
        "database integrity conflict: %s %s",
        request.method,
        request.url.path,
    )
    return error_response(
        message="数据状态冲突，请刷新后重试",
        status_code=409,
    )


def _llm_error_response(message: str, status_code: int) -> JSONResponse:
    return error_response(message=message, status_code=status_code)


@app.exception_handler(LLMConfigError)
async def llm_config_exception_handler(
    request: Request, exc: LLMConfigError
) -> JSONResponse:
    logger.warning(
        "LLM configuration unavailable for %s %s", request.method, request.url.path
    )
    return _llm_error_response("AI 服务尚未配置", 503)


@app.exception_handler(LLMRateLimitError)
async def llm_rate_limit_exception_handler(
    request: Request, exc: LLMRateLimitError
) -> JSONResponse:
    logger.warning("LLM rate limited for %s %s", request.method, request.url.path)
    return _llm_error_response("AI 服务繁忙，请稍后重试", 429)


@app.exception_handler(LLMOutputError)
async def llm_output_exception_handler(
    request: Request, exc: LLMOutputError
) -> JSONResponse:
    logger.warning(
        "LLM output validation failed for %s %s", request.method, request.url.path
    )
    return _llm_error_response("AI 返回结果无法校验，请稍后重试", 502)


@app.exception_handler(LLMProviderError)
async def llm_provider_exception_handler(
    request: Request, exc: LLMProviderError
) -> JSONResponse:
    logger.warning("LLM provider failed for %s %s", request.method, request.url.path)
    status_code = exc.status_code if exc.status_code in {429, 502, 503, 504} else 502
    return _llm_error_response("AI 服务调用失败，请稍后重试", status_code)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url=settings.FRONTEND_URL)
