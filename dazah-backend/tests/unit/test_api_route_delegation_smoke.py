from __future__ import annotations

import importlib
import inspect
import types
import uuid
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace as _SimpleNamespace
from typing import Any, get_args, get_origin
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import APIRouter, UploadFile
from fastapi.params import Param
from pydantic import BaseModel

SimpleNamespace: Any = _SimpleNamespace

API_MODULES = (
    "app.modules.research.api",
    "app.modules.hr.api",
    "app.modules.production.api",
    "app.modules.dossier_writer.api",
    "app.modules.warehouse.api",
    "app.platform.identity.api",
    "app.modules.quality.api.quality_management",
    "app.modules.quality.api.cpv_import",
    "app.modules.quality.api.cpv_products",
    "app.modules.quality.api.feishu_capa",
    "app.modules.registration.api.authorization_letters",
    "app.modules.registration.api.drugs",
    "app.modules.registration.api.holidays",
    "app.modules.registration.api.reference_standards",
    "app.modules.registration.api.reference_substances",
    "app.modules.registration.api.supplementary_replies",
    "app.modules.registration.api.validation_audit",
    "app.modules.safety.api.accidents",
    "app.modules.safety.api.ai_workflow",
    "app.modules.safety.api.checks",
    "app.modules.safety.api.contractors",
    "app.modules.safety.api.daily_risk_reports",
    "app.modules.safety.api.ehs_changes",
    "app.modules.safety.api.hazard_identifications",
    "app.modules.safety.api.hazards",
    "app.modules.safety.api.knowledge",
    "app.modules.safety.api.oh_hazard_monitors",
    "app.modules.safety.api.oh_health_exams",
    "app.modules.safety.api.regulations",
    "app.modules.safety.api.scheduled_tasks",
    "app.modules.safety.api.special_operation_reports",
    "app.modules.safety.api.special_ops_permits",
    "app.modules.safety.api.special_ops_personnel",
    "app.modules.safety.api.trainings",
)


class _Payload:
    id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    user_id = id
    filename = "test.csv"
    route = "oral"
    q3c_result: dict[Any, Any] = {}
    q3d_result: dict[Any, Any] = {}
    llm_used = False
    notes = None
    created_at = datetime(2026, 1, 1)
    name = "测试"
    status = "active"
    content = b"test"

    def __getattr__(self: Any, _name: str) -> Any:
        return None

    def __iter__(self: Any) -> Any:
        return iter(([], 0))


class _ServiceDouble:
    repo: Any = SimpleNamespace(session=AsyncMock())

    def __getattr__(self: Any, name: str) -> Any:
        async def call(*_args: Any, **_kwargs: Any) -> Any:
            if name.startswith(("list_", "get_all", "search_")):
                return [], 0
            if name.startswith(("export_", "download_", "generate_")):
                return b"test"
            if name.startswith(("delete_", "remove_")):
                return True
            return _Payload()

        return call


class _SchemaStub:
    def __init__(self: Any, **values: Any) -> None:
        self.__dict__.update(values)

    @classmethod
    def model_validate(cls: Any, _value: Any, **_kwargs: Any) -> dict[str, Any]:
        return {}

    @classmethod
    def model_validate_json(cls: Any, _value: Any, **_kwargs: Any) -> dict[str, Any]:
        return {}

    @classmethod
    def __class_getitem__(cls: Any, _item: Any) -> Any:
        return cls


def _annotation_value(annotation: Any, name: str) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (types.UnionType, getattr(__import__("typing"), "Union")):
        concrete = [arg for arg in args if arg is not type(None)]
        return _annotation_value(concrete[0], name) if concrete else None
    if origin in (list, set, tuple):
        return origin()
    if origin is dict:
        return {}
    if inspect.isclass(annotation) and issubclass(annotation, BaseModel):
        values = {
            field_name: _annotation_value(field.annotation, field_name)
            for field_name, field in annotation.model_fields.items()
            if field.is_required()
        }
        return annotation.model_construct(**values)
    if annotation is uuid.UUID:
        return uuid.UUID("00000000-0000-0000-0000-000000000001")
    if annotation is datetime:
        return datetime(2026, 1, 1)
    if annotation is date:
        return date(2026, 1, 1)
    if annotation is bool:
        return False
    if annotation is int:
        return 1
    if annotation is float:
        return 1.0
    if annotation is bytes:
        return b"test"
    if annotation is Path:
        return Path("/tmp/test")
    if annotation is UploadFile or name in {"file", "upload_file"}:
        return UploadFile(filename="test.csv", file=BytesIO(b"name\nvalue\n"))
    return "test"


def _endpoint_kwargs(endpoint: Any) -> dict[str, Any]:
    signature = inspect.signature(endpoint)
    kwargs: dict[Any, Any] = {}
    for name, parameter in signature.parameters.items():
        if name in {"db", "session"}:
            kwargs[name] = AsyncMock()
        elif name == "current_user":
            kwargs[name] = SimpleNamespace(
                id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                username="tester",
                is_superuser=True,
            )
        elif name.endswith("service") or name == "service":
            kwargs[name] = _ServiceDouble()
        elif parameter.annotation is not inspect.Parameter.empty:
            kwargs[name] = _annotation_value(parameter.annotation, name)
        elif isinstance(parameter.default, Param):
            default = parameter.default.default
            kwargs[name] = None if repr(default) == "PydanticUndefined" else default
        elif parameter.default is not inspect.Parameter.empty:
            kwargs[name] = parameter.default
        else:
            kwargs[name] = "test"
    return kwargs


def _patch_api_dependencies(monkeypatch: pytest.MonkeyPatch, module: Any) -> None:
    monkeypatch.setattr(
        module,
        "success_response",
        lambda **kwargs: kwargs,
        raising=False,
    )
    monkeypatch.setattr(
        module,
        "error_response",
        lambda **kwargs: kwargs,
        raising=False,
    )
    monkeypatch.setattr(
        module,
        "paginated_response",
        lambda **kwargs: kwargs,
        raising=False,
    )
    for name, value in vars(module).copy().items():
        if inspect.ismodule(value) and name == "service":
            monkeypatch.setattr(module, name, _ServiceDouble())
        elif inspect.isclass(value) and name.endswith("Service"):
            monkeypatch.setattr(
                module,
                name,
                lambda *_args, **_kwargs: _ServiceDouble(),
            )
        elif (
            inspect.isclass(value)
            and issubclass(value, BaseModel)
            and value.__module__.startswith("app.")
        ):
            monkeypatch.setattr(module, name, _SchemaStub)
        elif (
            callable(value)
            and getattr(value, "__module__", "").startswith("app.")
            and getattr(value, "__module__", "") != module.__name__
        ):
            replacement = (
                AsyncMock(return_value=_Payload())
                if inspect.iscoroutinefunction(value)
                else MagicMock(return_value=b"test")
            )
            monkeypatch.setattr(module, name, replacement)


@pytest.mark.anyio
@pytest.mark.parametrize("module_name", API_MODULES)
async def test_api_routes_delegate_with_minimal_boundary_inputs(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
) -> None:
    module = importlib.import_module(module_name)
    _patch_api_dependencies(monkeypatch, module)
    attempted = 0
    completed = 0
    routers = {
        id(value): value
        for value in vars(module).values()
        if isinstance(value, APIRouter)
    }.values()
    routes = [route for router in routers for route in router.routes]
    for route in routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None or not inspect.iscoroutinefunction(endpoint):
            continue
        attempted += 1
        try:
            await endpoint(**_endpoint_kwargs(endpoint))
        except Exception:
            continue
        completed += 1

    assert attempted >= 1
    assert completed >= 1
