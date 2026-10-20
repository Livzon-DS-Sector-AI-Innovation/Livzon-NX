import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.agent import api
from app.modules.agent.catalog import ToolCatalogService
from app.platform.identity import deps
from app.platform.identity.models import User
from app.platform.identity.rbac import seed_menus


@pytest.mark.asyncio
async def test_module_coverage_http_inventory_disabled_and_admin_boundary(
    db_session: AsyncSession,
) -> None:
    await seed_menus(db_session)
    user = User(name="接入盘点管理员", role="admin", tenant_key="local")
    db_session.add(user)
    await db_session.flush()
    app = FastAPI()
    app.include_router(api.router, prefix="/agent")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[deps.get_current_user] = lambda: user
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/agent/control/module-coverage")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["registered_count"] == 178
        assert data["personal_count"] == 30
        assert data["excluded_count"] == 33
        modules = {item["module_code"]: item for item in data["modules"]}
        assert len(modules) == 11
        assert {
            "regulatory_tracker",
            "product",
            "environment",
            "dossier_writer",
        }.isdisjoint(modules)
        assert {"法规追踪", "产品管理", "环保管理", "资料撰写"}.isdisjoint(
            item["module_name"] for item in data["modules"]
        )
        assert sum(item["registered_count"] > 0 for item in data["modules"]) == 6
        # 设备模块已收敛为统一工作台：45 个 workshop-叶页面退役，目录保留功能页 key；
        # 飞书配置页（equipment:feishu-config）按 agent 工具排除策略（config 路径段）
        # 不计入可接入页面
        equipment_page_keys = {
            page["page_key"] for page in modules["equipment"]["pages"]
        }
        assert equipment_page_keys == {
            "equipment:stats",
            "equipment:assets",
            "equipment:maintenance",
            "equipment:inspection",
            "equipment:spare-parts",
            "equipment:personnel",
        }
        assert not any(
            key.startswith("equipment:workshop-") for key in equipment_page_keys
        )
        assert modules["equipment"]["registered_count"] == 0
        assert modules["equipment"]["covered_pages"] == 0
        # Native energy replaces the legacy workspace and adds four net pages;
        # 设备模块 45 个 workshop-叶页面退役后总量相应减少
        assert data["total_pages"] == 269
        assert {"/energy/entry", "/energy/reports", "/energy/analysis"} <= {
            page["route_path"] for page in modules["energy"]["pages"]
        }
        assert data["covered_pages"] == 228
        assert modules["hr"]["registered_count"] == 16
        assert modules["hr"]["covered_pages"] == 17
        assert modules["hr"]["coverage_percent"] == 100.0
        assert modules["registration"]["coverage_percent"] == 100.0
        assert modules["registration"]["covered_pages"] == 20
        assert modules["warehouse"]["coverage_percent"] == 100.0
        assert modules["warehouse"]["covered_pages"] == 47
        assert modules["production"]["coverage_percent"] == 95.5
        assert {
            page["page_key"]
            for page in modules["production"]["pages"]
            if page["registered_count"] == 0
        } == {"production:plan:auto-scheduling"}
        assert modules["production"]["covered_pages"] == 21
        assert modules["quality"]["registered_count"] == 89
        assert modules["quality"]["covered_pages"] == 59
        assert modules["quality"]["coverage_percent"] == 100.0
        procurement = modules["procurement"]
        assert procurement["registered_count"] == 17
        assert procurement["covered_pages"] <= procurement["total_pages"]
        supplier = next(
            page
            for page in procurement["pages"]
            if page["route_path"] == "/purchasing/supplier"
        )
        assert supplier["registered_count"] >= 2
        assert data["covered_pages"] < sum(
            item["registered_count"]
            for module in data["modules"]
            for item in module["pages"]
        )
        assert all(
            not page["route_path"].startswith("/settings")
            for module in data["modules"]
            for page in module["pages"]
        )
        assert modules["energy"]["state"] == "not_integrated"
        assert modules["energy"]["excluded_count"] == 15
        assert all(
            tool["state"] == "excluded" and tool["reason"]
            for tool in modules["energy"]["tools"]
        )
        decision = next(
            tool
            for tool in procurement["tools"]
            if tool["operation"] == "procurement.reject_purchase_request"
        )
        assert decision["human_decision_required"] is True
        for tool in procurement["tools"]:
            await ToolCatalogService().set_enabled(
                db_session, operation=tool["operation"], enabled=False
            )
        disabled = (await client.get("/agent/control/module-coverage")).json()["data"]
        disabled_procurement = next(
            item for item in disabled["modules"] if item["module_code"] == "procurement"
        )
        assert disabled_procurement["state"] == "disabled"
        assert disabled_procurement["enabled_pages"] == 0
        assert disabled_procurement["covered_pages"] == procurement["covered_pages"]
        assert disabled["enabled_count"] == data["enabled_count"] - 17
        user.role = "user"
        assert (await client.get("/agent/control/module-coverage")).status_code == 403
        user.role = "admin"
        user.status = "disabled"
        assert (await client.get("/agent/control/module-coverage")).status_code == 403
