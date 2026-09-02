from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import tool_registry
from app.modules.quality.api import quality_deviation as api
from app.modules.quality.models import CAPA, Deviation
from app.modules.quality.page_access import DEVIATION_LEDGER_PAGE, deviation_page_scope
from app.modules.quality.service import quality_deviation as service
from app.modules.quality.service import quality_feishu_sync
from app.platform.audit.models import AuditLog
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
def page_context():
    tokens = [
        (var, var.set(None))
        for var in (current_page_actor, current_page_key, current_page_data_scope)
    ]
    yield
    for var, token in tokens:
        var.reset(token)


def _grant(department_ids=None, permissions=None, actions=None):
    return EffectivePageGrantOut(
        page_key=DEVIATION_LEDGER_PAGE,
        module_code="quality",
        permissions=permissions
        if permissions is not None
        else ["access", "query", "operate"],
        sensitive_actions=actions
        if actions is not None
        else ["delete", "sensitive_export"],
        data_scope=PageDataScopeInput(
            scope_type="departments",
            department_ids=department_ids or ["test-department"],
        ),
        source="user",
    )


def _app(db, user, monkeypatch, grant):
    monkeypatch.setattr(
        PagePermissionRepository,
        "get_rollout",
        AsyncMock(return_value=SimpleNamespace(status="enforced")),
    )
    monkeypatch.setattr(
        PagePermissionService, "effective_grants", AsyncMock(return_value=[grant])
    )
    app = FastAPI()
    app.include_router(
        api.router,
        prefix="/api/v1/quality",
        dependencies=[Depends(require_module_view("quality"))],
    )
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        effective_module_access_mode="all"
    )
    app.dependency_overrides[get_current_user] = lambda: user
    return app


@pytest.mark.asyncio
async def test_ledger_http_scope_crud_export_and_audit(db_session, monkeypatch):
    connection = await db_session.connection()
    async with AsyncSession(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        suffix = uuid4().hex[:10]
        own_name, child_name, other_name = (
            f"{name}-{suffix}" for name in ("本部", "下级", "外部")
        )
        own_id = "od-" + suffix
        actor = User(
            username="ledger-" + suffix,
            name="台账经办人",
            role="user",
            status="active",
            auth_source="local",
        )
        db.add_all(
            [
                actor,
                Department(feishu_department_id=own_id, name=own_name),
                Department(
                    feishu_department_id="child-" + suffix,
                    name=child_name,
                    parent_feishu_department_id=own_id,
                ),
            ]
        )
        rows = [
            Deviation(
                deviation_code=f"PC-{suffix}-{index}",
                title="偏差",
                department=department,
                description="原内容",
                status="draft",
                affected_items="产品",
                has_occurred_before=False,
            )
            for index, department in enumerate((own_name, child_name, other_name, None))
        ]
        db.add_all(rows)
        await db.flush()
        own, child, other, unowned = rows
        capas = [
            CAPA(
                capa_code=f"CAPA-{suffix}-{index}",
                deviation_id=own.id,
                department=department,
                title="措施",
            )
            for index, department in enumerate((own_name, other_name, None))
        ]
        db.add_all(capas)
        await db.flush()
        sync = AsyncMock()
        contact = AsyncMock(
            return_value=service.SelectedReporterContact(
                name="报告人", open_id="test-contact", department=child_name
            )
        )
        monkeypatch.setattr(
            quality_feishu_sync, "auto_sync_deviation_after_write", sync
        )
        monkeypatch.setattr(service, "_resolve_selected_reporter_contact", contact)
        monkeypatch.setattr(
            service,
            "_generate_monthly_deviation_code",
            AsyncMock(return_value="PC-new-" + suffix),
        )
        render = Mock(return_value=b"test-docx")
        monkeypatch.setattr(api, "generate_deviation_ledger_export_docx", render)
        app = _app(db, actor, monkeypatch, _grant([own_id]))
        base = "/api/v1/quality/deviations"
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Dazah-Page-Key": DEVIATION_LEDGER_PAGE},
        ) as client:
            response = await client.get(base)
            assert response.status_code == 200, response.text
            assert {row["id"] for row in response.json()["data"]} == {
                str(own.id),
                str(child.id),
            }
            assert response.json()["meta"]["total"] == 2
            own_item = next(
                row for row in response.json()["data"] if row["id"] == str(own.id)
            )
            assert own_item["related_capa_codes"] == [capas[0].capa_code]
            assert (await client.get(f"{base}/{own.id}")).status_code == 200
            linked = await client.get(f"{base}/{own.id}/related-capas")
            assert linked.status_code == 200
            assert [row["id"] for row in linked.json()["data"]] == [str(capas[0].id)]
            for row in (other, unowned):
                for method in ("GET", "PUT", "DELETE"):
                    denied = await client.request(
                        method, f"{base}/{row.id}", json={} if method == "PUT" else None
                    )
                    assert denied.status_code == 403, denied.text
                assert (
                    await client.get(f"{base}/{row.id}/related-capas")
                ).status_code == 403
            for suffix_path in ("", "/export"):
                assert (
                    await client.get(
                        base + suffix_path, params={"department": other_name}
                    )
                ).status_code == 403
            for department in (other_name, None):
                assert (
                    await client.put(
                        f"{base}/{own.id}", json={"department": department}
                    )
                ).status_code == 403
                assert (
                    await client.post(base, json={"department": department})
                ).status_code == 403
            for payload in (
                {"status": "closed"},
                {"review_opinions": [{"result": "approved"}]},
                {"is_closed": True},
                {"needs_cross_dept_review": False},
            ):
                assert (
                    await client.put(f"{base}/{own.id}", json=payload)
                ).status_code == 403
            assert (
                await client.post(
                    base, json={"department": own_name, "is_closed": True}
                )
            ).status_code == 403
            contact.assert_not_awaited()
            sync.assert_not_awaited()
            render.assert_not_called()
            assert (
                await client.put(
                    f"{base}/{own.id}",
                    json={"description": "修订内容", "status": "draft"},
                )
            ).status_code == 200
            created = await client.post(
                base,
                json={
                    "department": child_name,
                    "description": "新增内容",
                    "affected_items": "产品",
                    "reporter_open_id": "test-contact",
                },
            )
            assert created.status_code == 200, created.text
            exported = await client.get(
                base + "/export",
                params={
                    "deviation_code": own.deviation_code,
                    "has_occurred_before": "false",
                    "product_keyword": "产品",
                    "is_closed": "false",
                },
            )
            assert exported.status_code == 200, exported.text
            assert [row["id"] for row in render.call_args.args[0]] == [own.id]
            assert (await client.delete(f"{base}/{own.id}")).status_code == 200
            assert own.is_deleted and not other.is_deleted
            assert (
                await client.post(
                    base + "/batch-delete", json={"ids": [str(child.id), str(other.id)]}
                )
            ).status_code == 403
            assert not child.is_deleted
            assert (
                await client.get(
                    base,
                    headers={
                        "X-Dazah-Page-Key": "quality:deviations:deviation-records"
                    },
                )
            ).status_code == 403
        audits = list(
            (
                await db.execute(select(AuditLog).where(AuditLog.user_id == actor.id))
            ).scalars()
        )
        assert {row.action for row in audits} == {
            "创建偏差记录",
            "修改偏差记录",
            "delete",
            "导出偏差台账",
        }
        assert all(row.extra["page_key"] == DEVIATION_LEDGER_PAGE for row in audits)

        # Agent handlers call the same scoped service, without going through HTTP.
        ensure_agent_tools_registered()
        current_page_actor.set(actor)
        current_page_key.set(DEVIATION_LEDGER_PAGE)
        current_page_data_scope.set(
            {"scope_type": "departments", "department_ids": [own_id]}
        )
        context = SimpleNamespace(db=db, user_id=actor.id, user=actor)
        tool = tool_registry.require("quality.list_deviations")
        listed = await tool.handler(context, tool.input_model.model_validate({}))
        assert str(other.id) not in {str(row["id"]) for row in listed["items"]}
        for operation, payload in (
            ("quality.get_deviation", {"deviation_id": str(other.id)}),
            (
                "quality.update_deviation",
                {"deviation_id": str(other.id), "description": "工具越权"},
            ),
            ("quality.create_deviation", {"department": other_name}),
        ):
            tool = tool_registry.require(operation)
            with pytest.raises(HTTPException) as denied:
                await tool.handler(context, tool.input_model.model_validate(payload))
            assert denied.value.status_code == 403

        # Full system-administrator authority still includes out-of-scope records.
        actor.role = "admin"
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Dazah-Page-Key": DEVIATION_LEDGER_PAGE},
        ) as client:
            assert (await client.get(f"{base}/{other.id}")).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "suffix", "permissions", "actions"),
    [
        ("GET", "", ["access"], []),
        ("PUT", "/00000000-0000-0000-0000-000000000001", ["access", "query"], []),
        (
            "DELETE",
            "/00000000-0000-0000-0000-000000000001",
            ["access", "query", "operate"],
            [],
        ),
        ("GET", "/export", ["access", "query", "operate"], []),
    ],
)
async def test_ledger_permission_rejected_before_database(
    monkeypatch, method, suffix, permissions, actions
):
    db = AsyncMock()
    app = _app(
        db,
        SimpleNamespace(id=uuid4(), role="user"),
        monkeypatch,
        _grant(permissions=permissions, actions=actions),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        result = await client.request(
            method,
            "/api/v1/quality/deviations" + suffix,
            json={} if method == "PUT" else None,
            headers={"X-Dazah-Page-Key": DEVIATION_LEDGER_PAGE},
        )
    assert result.status_code == 403
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_and_untrusted_scope_fail_closed(monkeypatch):
    current_page_key.set(DEVIATION_LEDGER_PAGE)
    with pytest.raises(HTTPException, match="可信用户"):
        await deviation_page_scope(None)
    current_page_actor.set(SimpleNamespace(id=uuid4(), role="user"))
    current_page_data_scope.set({"scope_type": "departments", "department_ids": []})
    with pytest.raises(HTTPException) as error:
        await deviation_page_scope(
            AsyncMock(
                execute=AsyncMock(
                    return_value=Mock(
                        scalars=Mock(return_value=Mock(all=Mock(return_value=[])))
                    )
                )
            )
        )
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_batch_delete_is_atomic_and_requires_independent_permission(
    db_session, monkeypatch
):
    connection = await db_session.connection()
    async with AsyncSession(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        suffix = uuid4().hex
        actor = User(name="批量删除经办人", role="user")
        dept = Department(
            name="允许部门-" + suffix, feishu_department_id="od-" + suffix
        )
        rows = [
            Deviation(
                title="待删除",
                deviation_code=f"BATCH-{suffix}-{i}",
                department=dept.name if i < 2 else "其他部门",
            )
            for i in range(3)
        ]
        db.add_all([actor, dept, *rows])
        await db.flush()
        grant = _grant([dept.feishu_department_id])
        app = _app(db, actor, monkeypatch, grant)
        url = "/api/v1/quality/deviations/batch-delete"
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Dazah-Page-Key": DEVIATION_LEDGER_PAGE},
        ) as client:
            assert (
                await client.post(url, json={"ids": [str(rows[0].id), str(rows[2].id)]})
            ).status_code == 403
            assert not rows[0].is_deleted
            assert (
                await client.post(url, json={"ids": [str(rows[0].id), str(uuid4())]})
            ).status_code == 404
            for ids in (
                [],
                ["invalid"],
                [str(rows[0].id)] * 2,
                [str(uuid4()) for _ in range(101)],
            ):
                assert (await client.post(url, json={"ids": ids})).status_code == 422
            grant.sensitive_actions = []
            assert (
                await client.post(url, json={"ids": [str(rows[0].id)]})
            ).status_code == 403
            grant.sensitive_actions = ["delete"]
            result = await client.post(
                url, json={"ids": [str(rows[0].id), str(rows[1].id)]}
            )
            assert result.status_code == 200, result.text
            assert result.json()["data"] == {"deleted": 2, "failed": []}
            assert rows[0].is_deleted and rows[1].is_deleted and not rows[2].is_deleted
            audits = list(
                (
                    await db.execute(
                        select(AuditLog).where(AuditLog.user_id == actor.id)
                    )
                ).scalars()
            )
            assert len(audits) == 2
            assert {audit.resource_id for audit in audits} == {rows[0].id, rows[1].id}


def _fake_reporters(monkeypatch, records):
    runtime = SimpleNamespace(
        is_enabled=lambda: True,
        get_entity_config=lambda *args, **kwargs: SimpleNamespace(
            app_token="test-app", table_id="test-table"
        ),
        app_id="test-id",
        app_secret="placeholder",
    )
    monkeypatch.setattr(
        quality_feishu_sync.feishu_sync,
        "_resolve_runtime",
        AsyncMock(return_value=runtime),
    )
    external = SimpleNamespace(list_all_records=AsyncMock(return_value=records))
    monkeypatch.setattr(
        "app.platform.integrations.feishu.bitable.BitableClient",
        lambda **kwargs: external,
    )
    return external


def _reporter_record(open_id, name, department):
    return {
        "record_id": "record-" + open_id,
        "fields": {
            "姓名 (人员 )": name,
            "Open ID": open_id,
            "部门": department,
            "企业邮箱": "private@example.test",
        },
    }


@pytest.mark.asyncio
async def test_reporter_options_are_scoped_minimal_and_create_revalidates(
    db_session, monkeypatch
):
    import httpx

    connection = await db_session.connection()
    async with AsyncSession(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        suffix = uuid4().hex
        actor = User(name="报告人选择经办人", role="user")
        dept = Department(name="质量-" + suffix, feishu_department_id="od-" + suffix)
        second_dept = Department(
            name="质量二部-" + suffix, feishu_department_id="od-second-" + suffix
        )
        db.add_all([actor, dept, second_dept])
        await db.flush()
        records = [
            _reporter_record("own", "王报告", dept.name),
            _reporter_record("other", "外部人员", "范围外"),
            _reporter_record("duplicate", "重名映射", dept.name),
            _reporter_record("duplicate", "冲突映射", "范围外"),
            _reporter_record("blank", "", dept.name),
            _reporter_record("moved", "已调部门", second_dept.name),
        ]
        external = _fake_reporters(monkeypatch, records)
        sync = AsyncMock()
        monkeypatch.setattr(
            quality_feishu_sync, "auto_sync_deviation_after_write", sync
        )
        monkeypatch.setattr(
            service,
            "_generate_monthly_deviation_code",
            AsyncMock(return_value="REPORTER-" + suffix),
        )
        grant = _grant([dept.feishu_department_id, second_dept.feishu_department_id])
        app = _app(db, actor, monkeypatch, grant)
        base = "/api/v1/quality/deviations"
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Dazah-Page-Key": DEVIATION_LEDGER_PAGE},
        ) as client:
            result = await client.get(
                base + "/reporter-options", params={"keyword": "王", "page_size": 1}
            )
            assert result.status_code == 200, result.text
            assert result.json()["data"] == [
                {"open_id": "own", "name": "王报告", "department": dept.name}
            ]
            assert result.json()["meta"]["total"] == 1
            assert (
                await client.get(base + "/reporter-options", params={"page": 0})
            ).status_code == 422
            assert (
                await client.get(base + "/reporter-options", params={"page_size": 101})
            ).status_code == 422
            grant.permissions = ["access"]
            assert (await client.get(base + "/reporter-options")).status_code == 403
            grant.permissions = ["access", "query", "operate"]
            body = {
                "department": dept.name,
                "description": "偏差",
                "affected_items": "产品",
            }
            for reporter, status in (
                ("other", 403),
                ("duplicate", 400),
                ("missing", 400),
                ("moved", 400),
            ):
                response = await client.post(
                    base, json={**body, "reporter_open_id": reporter}
                )
                assert response.status_code == status, response.text
            sync.assert_not_awaited()
            result = await client.post(base, json={**body, "reporter_open_id": "own"})
            assert result.status_code == 200, result.text
            from uuid import UUID

            row = await db.get(Deviation, UUID(result.json()["data"]["id"]))
            assert row.discoverer == "王报告" and row.department == dept.name
            external.list_all_records.side_effect = httpx.ReadTimeout(
                "hidden upstream details"
            )
            result = await client.get(base + "/reporter-options")
            assert result.status_code == 504
            assert "hidden upstream details" not in result.text
            external.list_all_records.side_effect = RuntimeError("hidden credentials")
            result = await client.get(base + "/reporter-options")
            assert result.status_code == 502
            assert "hidden credentials" not in result.text


@pytest.mark.asyncio
async def test_reporter_lookup_is_not_limited_to_first_thousand(monkeypatch):
    records = [_reporter_record(str(i), "报告人", "质量部") for i in range(1002)]
    _fake_reporters(monkeypatch, records)
    contact = await service._resolve_selected_reporter_contact(None, "1001")
    assert contact.open_id == "1001" and contact.department == "质量部"


@pytest.mark.asyncio
async def test_batch_audit_failure_rolls_back_all_rows(db_session, monkeypatch):
    connection = await db_session.connection()
    async with AsyncSession(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        actor = User(name="事务回滚测试", role="admin")
        rows = [
            Deviation(title="事务记录", deviation_code=uuid4().hex) for _ in range(2)
        ]
        db.add_all([actor, *rows])
        await db.commit()
        actor_id, ids = actor.id, [row.id for row in rows]
        record_audit = service.record_audit_log
        calls = 0

        async def fail_second_audit(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("simulated storage failure")
            return await record_audit(*args, **kwargs)

        monkeypatch.setattr(service, "record_audit_log", fail_second_audit)
        with pytest.raises(RuntimeError, match="simulated"):
            await service.batch_delete_deviations(db, ids, deleted_by=actor_id)
        retained = list(
            (await db.execute(select(Deviation).where(Deviation.id.in_(ids)))).scalars()
        )
        assert len(retained) == 2 and all(not row.is_deleted for row in retained)
        assert (
            list(
                (
                    await db.execute(
                        select(AuditLog).where(AuditLog.user_id == actor_id)
                    )
                ).scalars()
            )
            == []
        )
