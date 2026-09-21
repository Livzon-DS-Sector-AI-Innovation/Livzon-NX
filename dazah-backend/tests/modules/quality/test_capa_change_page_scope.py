"""Record details and mutations must keep the page's real department scope."""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from docx import Document
from fastapi import Depends, FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.modules.quality.api import (
    inspection_submodules,
    oos_oot,
    quality_ai,
    quality_capa,
    quality_change,
)
from app.modules.quality.models import (
    CAPA,
    CapaPlanTrack,
    ChangeActionPlan,
    ChangeControl,
    QualityAiAnalysisLog,
)
from app.modules.quality.models.lab_instrument import LabInstrument
from app.modules.quality.models.oos_oot import OosOotRecord
from app.modules.quality.service import quality_ai as quality_ai_service
from app.platform.identity.data_scope import (
    current_page_actor,
    current_page_data_scope,
    current_page_key,
)
from app.platform.identity.deps import get_current_user, require_module_view
from app.platform.identity.models import Department, User
from app.platform.identity.page_permission_repository import PagePermissionRepository
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput


@pytest.fixture(autouse=True)
def reset_page_context():
    tokens = [
        (var, var.set(None))
        for var in (current_page_actor, current_page_key, current_page_data_scope)
    ]
    yield
    for var, token in tokens:
        var.reset(token)


def _grant(page_key: str, department_id: str) -> EffectivePageGrantOut:
    return EffectivePageGrantOut(
        page_key=page_key,
        module_code="quality",
        permissions=["access", "query", "operate"],
        sensitive_actions=["delete", "sensitive_export"],
        data_scope=PageDataScopeInput(
            scope_type="departments", department_ids=[department_id]
        ),
        source="user",
    )


@pytest.mark.asyncio
async def test_bulk_operations_reject_partial_page_scopes(monkeypatch) -> None:
    actor = SimpleNamespace(id=uuid4(), role="user")
    partial_scope = SimpleNamespace(is_all=False)

    current_page_key.set("quality:capas:capa-ledger")
    monkeypatch.setattr(
        quality_capa,
        "_resolve_quality_list_scope",
        AsyncMock(return_value=partial_scope),
    )
    with pytest.raises(HTTPException, match="需要全部数据范围"):
        await quality_capa._require_full_capa_page_scope(object(), actor)

    current_page_key.set(None)
    await quality_change._require_full_change_page_scope(object(), actor)
    current_page_key.set("quality:change:change-ledger")
    monkeypatch.setattr(
        quality_change,
        "_resolve_quality_list_scope",
        AsyncMock(return_value=partial_scope),
    )
    with pytest.raises(HTTPException, match="需要全部数据范围"):
        await quality_change._require_full_change_page_scope(object(), actor)


@pytest.mark.asyncio
async def test_ai_log_list_builds_department_scoped_entity_query(monkeypatch) -> None:
    actor = SimpleNamespace(id=uuid4(), role="user", department="本部")
    current_page_key.set("quality:capas:capa-ledger")
    current_page_actor.set(actor)
    monkeypatch.setattr(
        quality_ai_service,
        "resolve_user_department_scope",
        AsyncMock(return_value=object()),
    )
    monkeypatch.setattr(
        quality_ai_service,
        "department_in_clause",
        lambda _column, _scope: CAPA.department == "本部",
    )
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar=lambda: 0),
                SimpleNamespace(
                    scalars=lambda: SimpleNamespace(all=lambda: [])
                ),
            ]
        )
    )

    result = await quality_ai_service.list_ai_logs(db)

    assert result == {"items": [], "total": 0, "page": 1, "page_size": 20}
    assert db.execute.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("page_key", "path", "model"),
    [
        ("quality:capas:capa-ledger", "/capas", CAPA),
        ("quality:change:change-ledger", "/changes", ChangeControl),
    ],
)
async def test_detail_rejects_record_from_other_department(
    db_session, monkeypatch, page_key, path, model
) -> None:
    connection = await db_session.connection()
    async with AsyncSession(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        suffix = uuid4().hex[:10]
        own_id = "own-" + suffix
        own_name = "本部-" + suffix
        actor = User(
            username="scope-" + suffix,
            name="范围用户",
            role="user",
            status="active",
            auth_source="local",
            department=own_name,
        )
        db.add_all([
            actor,
            Department(feishu_department_id=own_id, name=own_name),
        ])
        if model is CAPA:
            own = CAPA(capa_code="CAPA-OWN-" + suffix, department=own_name)
            outside = CAPA(
                capa_code="CAPA-OTHER-" + suffix, department="其他部门"
            )
            router = quality_capa.router
        else:
            own = ChangeControl(
                change_code="BG-OWN-" + suffix,
                applicant_department=own_name,
            )
            outside = ChangeControl(
                change_code="BG-OTHER-" + suffix,
                applicant_department="其他部门",
            )
            router = quality_change.router
        db.add_all([own, outside])
        await db.flush()

        monkeypatch.setattr(
            PagePermissionRepository, "get_rollout",
            AsyncMock(return_value=SimpleNamespace(status="enforced")),
        )
        monkeypatch.setattr(
            PagePermissionService, "effective_grants",
            AsyncMock(return_value=[_grant(page_key, own_id)]),
        )
        monkeypatch.setattr(
            quality_capa if model is CAPA else quality_change,
            "_assert_quality_edit_scope",
            AsyncMock(),
        )
        app = FastAPI()
        app.include_router(
            router,
            prefix="/api/v1/quality",
            dependencies=[Depends(require_module_view("quality"))],
        )
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
            effective_module_access_mode="all"
        )
        app.dependency_overrides[get_current_user] = lambda: actor
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            headers = {"X-Dazah-Page-Key": page_key}
            own_response = await client.get(
                f"/api/v1/quality{path}/{own.id}", headers=headers
            )
            outside_response = await client.get(
                f"/api/v1/quality{path}/{outside.id}", headers=headers
            )
            list_response = await client.get(
                f"/api/v1/quality{path}", headers=headers
            )
            outside_update = await client.put(
                f"/api/v1/quality{path}/{outside.id}",
                headers=headers,
                json=(
                    {"title": "越权变更"}
                    if model is CAPA
                    else {"change_object": "越权变更"}
                ),
            )
            export_response = (
                await client.get("/api/v1/quality/capas/export", headers=headers)
                if model is CAPA
                else None
            )
        assert own_response.status_code == 200
        assert outside_response.status_code == 403
        assert list_response.status_code == 200
        visible_ids = {item["id"] for item in list_response.json()["data"]}
        assert str(own.id) in visible_ids
        assert str(outside.id) not in visible_ids
        assert outside_update.status_code == 403
        if export_response is not None:
            assert export_response.status_code == 200
            document = Document(BytesIO(export_response.content))
            exported_text = "\n".join(
                cell.text
                for table in document.tables
                for row in table.rows
                for cell in row.cells
            )
            assert own.capa_code in exported_text
            assert outside.capa_code not in exported_text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("page_key", "path", "parent_model", "plan_model"),
    [
        ("quality:capas:capa-plans", "/capa-plan-tracks", CAPA, CapaPlanTrack),
        (
            "quality:change:change-action-plans",
            "/change-action-plans",
            ChangeControl,
            ChangeActionPlan,
        ),
    ],
)
async def test_plan_list_and_update_follow_parent_department(
    db_session, monkeypatch, page_key, path, parent_model, plan_model
) -> None:
    connection = await db_session.connection()
    async with AsyncSession(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        suffix = uuid4().hex[:10]
        own_id = "own-" + suffix
        own_name = "本部-" + suffix
        actor = User(
            username="scope-plan-" + suffix,
            name="计划用户",
            role="user",
            status="active",
            auth_source="local",
            department=own_name,
        )
        db.add_all([actor, Department(feishu_department_id=own_id, name=own_name)])
        if parent_model is CAPA:
            own_parent = CAPA(capa_code="CAPA-OWN-" + suffix, department=own_name)
            outside_parent = CAPA(
                capa_code="CAPA-OTHER-" + suffix, department="其他部门"
            )
            router = quality_capa.router
        else:
            own_parent = ChangeControl(
                change_code="BG-OWN-" + suffix, applicant_department=own_name
            )
            outside_parent = ChangeControl(
                change_code="BG-OTHER-" + suffix,
                applicant_department="其他部门",
            )
            router = quality_change.router
        db.add_all([own_parent, outside_parent])
        await db.flush()
        if plan_model is CapaPlanTrack:
            own_plan = CapaPlanTrack(
                capa_id=own_parent.id,
                capa_code=own_parent.capa_code,
                plan_content="本部门计划",
            )
            outside_plan = CapaPlanTrack(
                capa_id=outside_parent.id,
                capa_code=outside_parent.capa_code,
                plan_content="外部门计划",
            )
        else:
            own_plan = ChangeActionPlan(
                change_id=own_parent.id,
                change_code=own_parent.change_code,
                project_name="本部门计划",
            )
            outside_plan = ChangeActionPlan(
                change_id=outside_parent.id,
                change_code=outside_parent.change_code,
                project_name="外部门计划",
            )
        db.add_all([own_plan, outside_plan])
        await db.flush()
        monkeypatch.setattr(
            PagePermissionRepository,
            "get_rollout",
            AsyncMock(return_value=SimpleNamespace(status="enforced")),
        )
        monkeypatch.setattr(
            PagePermissionService,
            "effective_grants",
            AsyncMock(return_value=[_grant(page_key, own_id)]),
        )
        monkeypatch.setattr(
            quality_capa if plan_model is CapaPlanTrack else quality_change,
            "_assert_quality_edit_scope",
            AsyncMock(),
        )
        app = FastAPI()
        app.include_router(
            router,
            prefix="/api/v1/quality",
            dependencies=[Depends(require_module_view("quality"))],
        )
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
            effective_module_access_mode="all"
        )
        app.dependency_overrides[get_current_user] = lambda: actor
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            headers = {"X-Dazah-Page-Key": page_key}
            listing = await client.get(f"/api/v1/quality{path}", headers=headers)
            blocked = await client.put(
                f"/api/v1/quality{path}/{outside_plan.id}",
                headers=headers,
                json={"plan_content": "越权变更"}
                if plan_model is CapaPlanTrack
                else {"project_name": "越权变更"},
            )
        assert listing.status_code == 200
        visible_ids = {item["id"] for item in listing.json()["data"]}
        assert str(own_plan.id) in visible_ids
        assert str(outside_plan.id) not in visible_ids
        assert blocked.status_code == 403


@pytest.mark.asyncio
async def test_ai_log_list_and_detail_follow_page_department(
    db_session, monkeypatch
) -> None:
    connection = await db_session.connection()
    async with AsyncSession(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        suffix = uuid4().hex[:10]
        own_id = "own-" + suffix
        own_name = "本部-" + suffix
        actor = User(
            username="scope-ai-" + suffix,
            name="AI 范围用户",
            role="user",
            status="active",
            auth_source="local",
            department=own_name,
        )
        own = CAPA(capa_code="CAPA-AI-OWN-" + suffix, department=own_name)
        outside = CAPA(
            capa_code="CAPA-AI-OTHER-" + suffix, department="其他部门"
        )
        db.add_all([
            actor,
            Department(feishu_department_id=own_id, name=own_name),
            own,
            outside,
        ])
        await db.flush()
        own_log = QualityAiAnalysisLog(
            entity_type="capa",
            entity_id=own.id,
            analysis_type="capa_review",
            input_snapshot={},
            model_name="test",
        )
        outside_log = QualityAiAnalysisLog(
            entity_type="capa",
            entity_id=outside.id,
            analysis_type="capa_review",
            input_snapshot={},
            model_name="test",
        )
        db.add_all([own_log, outside_log])
        await db.flush()
        page_key = "quality:capas:capa-ledger"
        monkeypatch.setattr(
            PagePermissionRepository,
            "get_rollout",
            AsyncMock(return_value=SimpleNamespace(status="enforced")),
        )
        monkeypatch.setattr(
            PagePermissionService,
            "effective_grants",
            AsyncMock(return_value=[_grant(page_key, own_id)]),
        )
        app = FastAPI()
        app.include_router(
            quality_ai.router,
            prefix="/api/v1/quality",
            dependencies=[Depends(require_module_view("quality"))],
        )
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
            effective_module_access_mode="all"
        )
        app.dependency_overrides[get_current_user] = lambda: actor
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            headers = {"X-Dazah-Page-Key": page_key}
            listing = await client.get("/api/v1/quality/ai/logs", headers=headers)
            blocked_detail = await client.get(
                f"/api/v1/quality/ai/logs/{outside_log.id}", headers=headers
            )
            blocked_analysis = await client.post(
                f"/api/v1/quality/ai/capas/{outside.id}/analyze",
                headers=headers,
            )
        assert listing.status_code == 200
        visible_ids = {item["id"] for item in listing.json()["data"]}
        assert str(own_log.id) in visible_ids
        assert str(outside_log.id) not in visible_ids
        assert blocked_detail.status_code == 403
        assert blocked_analysis.status_code == 403


@pytest.mark.asyncio
async def test_lab_instrument_crud_follows_record_department(
    db_session, monkeypatch
) -> None:
    connection = await db_session.connection()
    async with AsyncSession(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        suffix = uuid4().hex[:10]
        own_id = "own-" + suffix
        own_name = "本部-" + suffix
        actor = User(
            username="scope-instrument-" + suffix,
            name="仪器用户",
            role="user",
            status="active",
            auth_source="local",
            department=own_name,
        )
        own = LabInstrument(name="本部仪器-" + suffix, department=own_name)
        outside = LabInstrument(name="外部仪器-" + suffix, department="其他部门")
        db.add_all([
            actor,
            Department(feishu_department_id=own_id, name=own_name),
            own,
            outside,
        ])
        await db.flush()
        page_key = (
            "quality:inspection:inspection-instruments:"
            "inspection-instruments-equipment"
        )
        monkeypatch.setattr(
            PagePermissionRepository,
            "get_rollout",
            AsyncMock(return_value=SimpleNamespace(status="enforced")),
        )
        monkeypatch.setattr(
            PagePermissionService,
            "effective_grants",
            AsyncMock(return_value=[_grant(page_key, own_id)]),
        )
        monkeypatch.setattr(
            inspection_submodules,
            "_assert_quality_edit_scope",
            AsyncMock(),
        )
        app = FastAPI()
        app.include_router(
            inspection_submodules.router,
            prefix="/api/v1/quality",
            dependencies=[Depends(require_module_view("quality"))],
        )
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
            effective_module_access_mode="all"
        )
        app.dependency_overrides[get_current_user] = lambda: actor
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            headers = {"X-Dazah-Page-Key": page_key}
            listing = await client.get(
                "/api/v1/quality/lab-instruments", headers=headers
            )
            blocked_detail = await client.get(
                f"/api/v1/quality/lab-instruments/{outside.id}", headers=headers
            )
            blocked_update = await client.put(
                f"/api/v1/quality/lab-instruments/{outside.id}",
                headers=headers,
                json={"name": "越权变更"},
            )
        assert listing.status_code == 200
        visible_ids = {item["id"] for item in listing.json()["data"]}
        assert str(own.id) in visible_ids
        assert str(outside.id) not in visible_ids
        assert blocked_detail.status_code == 403
        assert blocked_update.status_code == 403


@pytest.mark.asyncio
async def test_oos_legacy_department_grant_restricts_current_and_legacy_paths(
    db_session, monkeypatch
) -> None:
    connection = await db_session.connection()
    async with AsyncSession(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        suffix = uuid4().hex[:10]
        own_id = "own-" + suffix
        own_name = "本部-" + suffix
        actor = User(
            username="scope-oos-" + suffix,
            name="OOS 用户",
            role="user",
            status="active",
            auth_source="local",
            department=own_name,
        )
        own = OosOotRecord(
            record_code="OOS-OWN-" + suffix,
            record_type="OOS",
            title="本部记录",
            department=own_name,
        )
        outside = OosOotRecord(
            record_code="OOS-OTHER-" + suffix,
            record_type="OOS",
            title="外部记录",
            department="其他部门",
        )
        db.add_all([
            actor,
            Department(feishu_department_id=own_id, name=own_name),
            own,
            outside,
        ])
        await db.flush()
        page_key = "quality:oos-oot:oos-ledger"
        monkeypatch.setattr(
            PagePermissionRepository,
            "get_rollout",
            AsyncMock(return_value=SimpleNamespace(status="enforced")),
        )
        monkeypatch.setattr(
            PagePermissionService,
            "effective_grants",
            AsyncMock(return_value=[_grant(page_key, own_id)]),
        )
        monkeypatch.setattr(oos_oot, "_assert_quality_edit_scope", AsyncMock())
        app = FastAPI()
        app.include_router(
            oos_oot.router,
            prefix="/api/v1/quality",
            dependencies=[Depends(require_module_view("quality"))],
        )
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
            effective_module_access_mode="all"
        )
        app.dependency_overrides[get_current_user] = lambda: actor
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            headers = {"X-Dazah-Page-Key": page_key}
            listing = await client.get("/api/v1/quality/oos-oot", headers=headers)
            legacy_listing = await client.get(
                "/api/v1/quality/oos-oot/records", headers=headers
            )
            blocked_detail = await client.get(
                f"/api/v1/quality/oos-oot/{outside.id}", headers=headers
            )
            blocked_update = await client.put(
                f"/api/v1/quality/oos-oot/{outside.id}",
                headers=headers,
                json={"title": "越权变更"},
            )
        assert listing.status_code == 200
        assert legacy_listing.status_code == 200
        for response in (listing, legacy_listing):
            visible_ids = {item["id"] for item in response.json()["data"]}
            assert str(own.id) in visible_ids
            assert str(outside.id) not in visible_ids
        assert blocked_detail.status_code == 403
        assert blocked_update.status_code == 403
