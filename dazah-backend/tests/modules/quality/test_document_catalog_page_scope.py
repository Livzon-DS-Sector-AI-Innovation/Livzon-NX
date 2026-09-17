from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.response import error_response
from app.modules.quality.api import document_catalog as api
from app.modules.quality.models.document_catalog import (
    DocumentDepartment,
    DocumentEntry,
)
from app.platform.identity.data_scope import DepartmentScope
from app.platform.identity.deps import get_current_user


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operate,delete,method,foreign,expected",
    [
        (False, False, "GET", False, 200),
        (False, False, "PUT", False, 403),
        (True, False, "PUT", False, 200),
        (True, False, "PUT", True, 404),
        (True, False, "DELETE", False, 403),
        (True, True, "DELETE", False, 200),
        (True, True, "DELETE", True, 404),
    ],
)
async def test_document_page_grants_and_scope_apply_together(
    monkeypatch, db_session, operate, delete, method, foreign, expected
):
    from app.platform.identity import deps, page_policy
    from app.platform.identity.page_permissions import PagePermissionService
    from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput

    own_dept = DocumentDepartment(name=f"own-{uuid4()}", sort_order=1)
    other_dept = DocumentDepartment(name=f"other-{uuid4()}", sort_order=2)
    db_session.add_all([own_dept, other_dept])
    await db_session.flush()
    entry = DocumentEntry(
        department_id=(other_dept if foreign else own_dept).id,
        name="授权验收",
        seq_no=1,
        attachments=[],
    )
    db_session.add(entry)
    await db_session.flush()
    scope = DepartmentScope(department_names={own_dept.name})
    monkeypatch.setattr(
        api, "_resolve_quality_list_scope", AsyncMock(return_value=scope)
    )
    grant = EffectivePageGrantOut(
        page_key="quality:documents",
        module_code="quality",
        permissions=["access", "query", "operate"] if operate else ["access", "query"],
        sensitive_actions=["delete"] if delete else [],
        data_scope=PageDataScopeInput(
            scope_type="departments", department_ids=[str(own_dept.id)]
        ),
        source="user",
    )
    monkeypatch.setattr(
        PagePermissionService, "effective_grants", AsyncMock(return_value=[grant])
    )
    app = FastAPI()
    app.include_router(
        api.router,
        prefix="/api/v1/quality",
        dependencies=[Depends(deps.require_module_view("quality"))],
    )
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid4(), role="user"
    )
    app.dependency_overrides[deps.get_settings] = lambda: SimpleNamespace(
        effective_module_access_mode="all"
    )
    monkeypatch.setattr(
        page_policy,
        "_api_catalog_provider",
        lambda: page_policy.collect_http_route_catalog(app.routes),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.request(
            method,
            "/api/v1/quality/document-entries"
            + ("" if method == "GET" else f"/{entry.id}"),
            headers={"X-Dazah-Page-Key": "quality:documents"},
            json={"name": "已更新"} if method == "PUT" else None,
        )
    assert response.status_code == expected, response.text
    if expected == 200 and method == "PUT":
        assert response.json()["data"]["name"] == "已更新"
    if expected != 200:
        assert entry.name == "授权验收"
        assert entry.is_deleted is False


@pytest.mark.asyncio
async def test_mixed_department_import_is_rejected_before_replacement(monkeypatch):
    from app.modules.quality.service import document_catalog as service

    monkeypatch.setattr(
        service,
        "parse_document_catalog_workbook",
        lambda _: {
            "范围内": [{"name": "新文件"}],
            "范围外": [{"name": "范围外文件"}],
        },
    )
    db = AsyncMock()
    with pytest.raises(AppException) as exc:
        await service.import_document_catalog(
            db,
            b"workbook",
            "catalog.xlsx",
            scope=DepartmentScope(department_names={"范围内"}),
        )
    assert exc.value.status_code == 403
    db.execute.assert_not_awaited()
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_attachment_matching_never_uses_foreign_candidates(
    monkeypatch, db_session
):
    from app.modules.quality.service import document_catalog_attachment as service

    department = DocumentDepartment(name=f"foreign-{uuid4()}", sort_order=1)
    db_session.add(department)
    await db_session.flush()
    entry = DocumentEntry(
        department_id=department.id,
        name="权限验收文件",
        code="SOP-QA-989/01",
        seq_no=1,
        attachments=[],
    )
    db_session.add(entry)
    await db_session.flush()
    llm = AsyncMock()
    monkeypatch.setattr(
        service,
        "llm_client",
        SimpleNamespace(chat_json=llm),
    )
    result, match_type = await service.match_entry_for_attachment(
        db_session,
        "权限验收文件SOP-QA-989-01.md",
        ("SOP-QA-989/01", "权限验收文件"),
        scope=DepartmentScope(),
    )
    assert result is None
    assert match_type == "none"
    llm.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation", ["resolve", "preview", "update", "delete", "export"]
)
async def test_foreign_document_paths_do_not_expose_or_change_records(
    monkeypatch, db_session, operation
):
    department = DocumentDepartment(name=f"outside-{uuid4()}", sort_order=1)
    db_session.add(department)
    await db_session.flush()
    entry = DocumentEntry(
        department_id=department.id, name="范围外文件", seq_no=1, attachments=[]
    )
    db_session.add(entry)
    await db_session.flush()
    monkeypatch.setattr(
        api, "_resolve_quality_list_scope", AsyncMock(return_value=DepartmentScope())
    )
    from unittest.mock import Mock

    preview = Mock(return_value=(b"private", "text/plain"))
    exporter = Mock(return_value=b"document")
    reader = Mock(return_value=[])
    monkeypatch.setattr(api, "read_attachment_preview", preview)
    monkeypatch.setattr(api, "read_entry_md_contents", reader)
    monkeypatch.setattr(api, "export_document_catalog_docx", exporter)
    app = FastAPI()

    @app.exception_handler(AppException)
    async def handle_error(request, exc):
        return error_response(message=exc.message, status_code=exc.status_code)

    app.include_router(api.router, prefix="/api/v1/quality")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid4(), role="user"
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        base = f"/api/v1/quality/document-entries/{entry.id}"
        if operation == "resolve":
            response = await client.post(
                "/api/v1/quality/document-entries/resolve-content",
                json={"entries": [{"name": entry.name, "entry_id": str(entry.id)}]},
            )
            assert response.status_code == 200
            assert response.json()["data"]["results"][0]["matched"] is False
            reader.assert_not_called()
        elif operation == "preview":
            response = await client.get(base + "/attachments/file.pdf/content")
            assert response.status_code == 404
            preview.assert_not_called()
        elif operation == "export":
            response = await client.get("/api/v1/quality/document-catalog/export")
            assert response.status_code == 200
            assert exporter.call_args.args[0] == []
        else:
            response = await client.request(
                operation == "update" and "PUT" or "DELETE",
                base,
                json={"name": "越权改名"} if operation == "update" else None,
            )
            assert response.status_code == 404
            assert entry.name == "范围外文件"
            assert entry.is_deleted is False


@pytest.mark.asyncio
@pytest.mark.parametrize("is_all", [False, True])
async def test_empty_department_scope_never_becomes_unrestricted(
    monkeypatch, db_session, is_all
):
    department = DocumentDepartment(name=f"scope-{uuid4()}", sort_order=1)
    db_session.add(department)
    await db_session.flush()
    entry = DocumentEntry(
        department_id=department.id,
        name="验收文件",
        code=f"scope-{uuid4()}",
        seq_no=1,
        attachments=[],
    )
    db_session.add(entry)
    await db_session.flush()
    monkeypatch.setattr(
        api,
        "_resolve_quality_list_scope",
        AsyncMock(return_value=DepartmentScope(is_all=is_all, department_names=set())),
    )
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1/quality")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid4(), role="user"
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/quality/document-entries",
            params={"department_id": str(department.id)},
        )
    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert [row["id"] for row in rows] == ([str(entry.id)] if is_all else [])
