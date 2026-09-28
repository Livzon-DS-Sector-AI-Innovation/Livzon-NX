"""培训管理跨页面共享端点的页面契约回归测试。

生产曾因培训资料页（hr:training:sign-in-sheet）调用的 5 组端点未登记该页面，
被页面上下文校验统一拒绝（403「当前页面不能调用此业务接口」，超管同样被拦）：
配置人员弹窗候选人全空（feishu-members）、班组配置读写失败
（training-personnel-configs）、年度计划/附件加载为空（annual-training-plans）、
拉取新员工报错（employees/new-hires）；新员工培训页保存初始岗位映射失败
（position-training-mappings）。回归锁定这些端点对实际调用页开放，
且未登记页面（如员工档案页调联系人列表）仍被拒绝。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.database import get_db
from app.modules.hr import api
from app.platform.identity.data_scope import (
    current_page_actor,
    current_page_data_scope,
    current_page_key,
)
from app.platform.identity.deps import get_current_user, require_module_view
from app.platform.identity.models import User
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.page_policy import api_binding_for_route
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput

SIGN_IN_PAGE_KEY = "hr:training:sign-in-sheet"
NEW_EMPLOYEE_PAGE_KEY = "hr:training:new-employee-training"
PROFILE_PAGE_KEY = "hr:employee-management:profile"
TRAINER_PAGE_KEY = "hr:training:trainer"

FEISHU_MEMBERS = "/api/v1/hr/hr-settings/feishu-members"
PERSONNEL_CONFIGS = "/api/v1/hr/training-personnel-configs"
ANNUAL_PLANS = "/api/v1/hr/annual-training-plans"
NEW_HIRES = "/api/v1/hr/employees/new-hires"
POSITION_MAPPINGS = "/api/v1/hr/position-training-mappings"


@pytest.fixture(autouse=True)
def page_context():
    key = current_page_key.set(None)
    actor = current_page_actor.set(None)
    scope = current_page_data_scope.set(None)
    yield
    current_page_key.reset(key)
    current_page_actor.reset(actor)
    current_page_data_scope.reset(scope)


def _binding_pages(method: str, path: str) -> tuple[str, ...]:
    binding = api_binding_for_route(method, path)
    assert binding is not None, f"{method} {path} 绑定缺失或契约校验未通过"
    return binding.page_keys


def test_feishu_members_open_to_sign_in_page():
    assert _binding_pages("GET", FEISHU_MEMBERS) == (
        "hr:hr-settings:hr-settings-feishu",
        "hr:employee-management:feishu-contacts",
        "hr:hr-settings:hr-settings-dept-mapping",
        SIGN_IN_PAGE_KEY,
    )


def test_personnel_configs_open_to_trainer_and_sign_in_pages():
    expected = (TRAINER_PAGE_KEY, SIGN_IN_PAGE_KEY)
    assert _binding_pages("GET", PERSONNEL_CONFIGS) == expected
    assert _binding_pages("POST", PERSONNEL_CONFIGS) == expected
    assert _binding_pages("DELETE", PERSONNEL_CONFIGS + "/{config_id}") == expected


def test_annual_plans_get_open_to_sign_in_page():
    for path in (
        ANNUAL_PLANS,
        ANNUAL_PLANS + "/{plan_id}",
        ANNUAL_PLANS + "/{plan_id}/items",
        ANNUAL_PLANS + "/{plan_id}/attachments",
        ANNUAL_PLANS + "/{plan_id}/attachment-sections",
    ):
        assert _binding_pages("GET", path) == (
            "hr:training:annual-plan",
            SIGN_IN_PAGE_KEY,
        ), path


def test_new_hires_open_to_profile_and_sign_in_pages():
    assert _binding_pages("GET", NEW_HIRES) == (PROFILE_PAGE_KEY, SIGN_IN_PAGE_KEY)
    # 同组其余端点仍仅员工档案页
    assert _binding_pages(
        "GET", "/api/v1/hr/employees/contract-expiring"
    ) == (PROFILE_PAGE_KEY,)


def test_position_mapping_post_open_to_new_employee_page():
    assert _binding_pages("POST", POSITION_MAPPINGS) == (
        "hr:training:position-training",
        NEW_EMPLOYEE_PAGE_KEY,
    )
    # 岗位培训清单创建仍仅岗位培训页
    assert _binding_pages("POST", "/api/v1/hr/position-training-lists") == (
        "hr:training:position-training",
    )


def _app(db, user):
    app = FastAPI()
    app.include_router(
        api.router,
        prefix="/api/v1/hr",
        dependencies=[Depends(require_module_view("hr"))],
    )
    app.dependency_overrides[get_db] = lambda: db
    # 模块访问模式由身份测试套件覆盖；此处隔离页面授权链路。
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        effective_module_access_mode="all"
    )
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _sign_in_grant(*, actions: list[str]) -> EffectivePageGrantOut:
    return EffectivePageGrantOut(
        page_key=SIGN_IN_PAGE_KEY,
        module_code="hr",
        permissions=["access", "query", "operate"],
        sensitive_actions=actions,
        data_scope=PageDataScopeInput(scope_type="all", department_ids=[]),
        source="user",
    )


def _personnel_payload(suffix: str) -> dict[str, object]:
    return {
        "level": "公司级",
        "department": None,
        "config_name": f"回归测试配置-{suffix}",
        "personnel": [
            {"name": "测试人员甲", "employee_number": "T-0001", "department": "一车间"}
        ],
    }


async def _persist_user(db, *, role: str) -> User:
    user = User(
        name=f"培训回归-{role}-{uuid4().hex[:6]}",
        username=f"trn-{role}-" + uuid4().hex[:10],
        role=role,
        status="active",
        auth_source="local",
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_super_admin_can_call_sign_in_page_shared_endpoints(db_session):
    admin = await _persist_user(db_session, role="admin")
    app = _app(db_session, admin)
    headers = {"X-Dazah-Page-Key": SIGN_IN_PAGE_KEY}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (
            await client.get(
                FEISHU_MEMBERS,
                params={"page": 1, "page_size": 5},
                headers=headers,
            )
        ).status_code == 200
        assert (
            await client.get(
                PERSONNEL_CONFIGS,
                params={"level": "公司级"},
                headers=headers,
            )
        ).status_code == 200
        created = await client.post(
            PERSONNEL_CONFIGS,
            json=_personnel_payload(uuid4().hex[:8]),
            headers=headers,
        )
        assert created.status_code == 200, created.text
        config_id = created.json()["data"]["id"]
        deleted = await client.delete(
            f"{PERSONNEL_CONFIGS}/{config_id}",
            headers=headers,
        )
        assert deleted.status_code == 200, deleted.text
        assert (
            await client.get(ANNUAL_PLANS, headers=headers)
        ).status_code == 200
        assert (
            await client.get(NEW_HIRES, params={"days": 7}, headers=headers)
        ).status_code == 200


@pytest.mark.asyncio
async def test_unregistered_page_still_rejected(db_session):
    admin = await _persist_user(db_session, role="admin")
    app = _app(db_session, admin)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 员工档案页调联系人列表：不在绑定内，仍拒绝
        assert (
            await client.get(
                FEISHU_MEMBERS,
                params={"page": 1, "page_size": 5},
                headers={"X-Dazah-Page-Key": PROFILE_PAGE_KEY},
            )
        ).status_code == 403
        # 培训资料页调岗位映射创建：不在绑定内，仍拒绝
        assert (
            await client.post(
                POSITION_MAPPINGS,
                json={
                    "department": "一车间",
                    "employee_position": "操作工",
                    "training_position": "操作工",
                },
                headers={"X-Dazah-Page-Key": SIGN_IN_PAGE_KEY},
            )
        ).status_code == 403


@pytest.mark.asyncio
async def test_new_employee_page_can_create_position_mapping(db_session):
    admin = await _persist_user(db_session, role="admin")
    app = _app(db_session, admin)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            POSITION_MAPPINGS,
            json={
                "department": "一车间",
                "employee_position": "操作工",
                "training_position": "操作工",
            },
            headers={"X-Dazah-Page-Key": NEW_EMPLOYEE_PAGE_KEY},
        )
        assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_granted_user_can_save_personnel_config(db_session, monkeypatch):
    actor = await _persist_user(db_session, role="user")
    monkeypatch.setattr(
        PagePermissionService,
        "effective_grants",
        AsyncMock(return_value=[_sign_in_grant(actions=["sync_config"])]),
    )
    app = _app(db_session, actor)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            PERSONNEL_CONFIGS,
            json=_personnel_payload(uuid4().hex[:8]),
            headers={"X-Dazah-Page-Key": SIGN_IN_PAGE_KEY},
        )
        assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_granted_user_without_sensitive_action_rejected(
    db_session, monkeypatch
):
    actor = await _persist_user(db_session, role="user")
    monkeypatch.setattr(
        PagePermissionService,
        "effective_grants",
        AsyncMock(return_value=[_sign_in_grant(actions=["delete"])]),
    )
    app = _app(db_session, actor)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            PERSONNEL_CONFIGS,
            json=_personnel_payload(uuid4().hex[:8]),
            headers={"X-Dazah-Page-Key": SIGN_IN_PAGE_KEY},
        )
        assert response.status_code == 403, response.text
