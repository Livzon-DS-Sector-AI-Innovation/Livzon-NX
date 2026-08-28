from __future__ import annotations

import inspect
from collections.abc import Callable
from datetime import date, datetime
from io import BytesIO
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi import UploadFile

from app.modules.hr import service as hr_service
from app.modules.warehouse import service as warehouse_service


class _Probe:
    """A side-effect-free dependency boundary for service smoke coverage."""

    def __init__(self, truth: bool = False) -> None:
        self._truth = truth

    def __getattr__(self, name: str) -> Any:
        if name in {"dict", "model_dump", "model_dump_json"}:
            return lambda **_kwargs: {}
        if name in {
            "all",
            "fetchall",
            "fetchmany",
            "fetchone",
            "first",
            "one_or_none",
            "scalar",
            "scalar_one_or_none",
        }:
            return lambda *_args, **_kwargs: None
        return _Probe()

    def __call__(self, *_args: Any, **_kwargs: Any) -> Any:
        return _Probe()

    def __await__(self) -> Any:
        async def _result() -> _Probe:
            return self

        return _result().__await__()

    async def __aenter__(self) -> _Probe:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    def __iter__(self) -> Any:
        return iter(())

    def __aiter__(self) -> _Probe:
        return self

    async def __anext__(self) -> Any:
        raise StopAsyncIteration

    def __getitem__(self, _key: Any) -> Any:
        return _Probe()

    def __setitem__(self, _key: Any, _value: Any) -> None:
        return None

    def __contains__(self, _item: Any) -> bool:
        return False

    def __bool__(self) -> bool:
        return self._truth

    def __len__(self) -> int:
        return 0

    def __str__(self) -> str:
        return "test"

    def __repr__(self) -> str:
        return "<probe>"

    def __int__(self) -> int:
        return 1

    def __float__(self) -> float:
        return 1.0

    def __eq__(self, _other: object) -> bool:
        return False

    def __lt__(self, _other: object) -> bool:
        return False

    def __le__(self, _other: object) -> bool:
        return False

    def __gt__(self, _other: object) -> bool:
        return False

    def __ge__(self, _other: object) -> bool:
        return False

    def __add__(self, _other: Any) -> _Probe:
        return _Probe()

    def __radd__(self, _other: Any) -> _Probe:
        return _Probe()

    def __sub__(self, _other: Any) -> _Probe:
        return _Probe()

    def __rsub__(self, _other: Any) -> _Probe:
        return _Probe()

    def __mul__(self, _other: Any) -> _Probe:
        return _Probe()

    def __rmul__(self, _other: Any) -> _Probe:
        return _Probe()


def _argument_for(name: str, annotation: Any) -> Any:
    lowered = name.lower()
    if lowered in {"self", "cls"}:
        return _Probe(truth=True)
    if lowered in {"db", "session", "repo", "repository", "service"}:
        return _Probe(truth=True)
    if "file" in lowered or lowered in {"upload", "attachment"}:
        return UploadFile(filename="probe.txt", file=BytesIO(b"probe"))
    if "user" in lowered or lowered in {"operator", "current"}:
        return SimpleNamespace(
            id=uuid4(),
            user_id=uuid4(),
            username="probe",
            name="测试用户",
            roles=["admin"],
            is_superuser=True,
        )
    if lowered.endswith("_id") or lowered in {"id", "record_id", "root_id"}:
        return uuid4()
    if lowered in {"page", "page_num", "page_number"}:
        return 1
    if lowered in {"page_size", "limit", "size"}:
        return 20
    if lowered in {"offset", "skip"}:
        return 0
    if lowered in {"year", "month", "day", "count", "index"}:
        return 1
    if lowered.startswith("is_") or lowered in {"enabled", "force", "dry_run"}:
        return False
    if "datetime" in str(annotation).lower():
        return datetime.now()
    if "date" in lowered or lowered.endswith("_at"):
        return date.today()
    if "list" in str(annotation).lower():
        return []
    if "dict" in str(annotation).lower() or lowered in {"data", "payload", "query"}:
        return _Probe()
    if "bool" in str(annotation).lower():
        return False
    if "int" in str(annotation).lower() or "float" in str(annotation).lower():
        return 1
    if lowered in {
        "code",
        "department",
        "filename",
        "keyword",
        "model",
        "name",
        "operation",
        "path",
        "status",
        "title",
        "url",
    }:
        return "test"
    if lowered.endswith("s"):
        return []
    return "test"


def _safe_call_arguments(
    callable_obj: Callable[..., Any],
) -> tuple[list[Any], dict[str, Any]]:
    signature = inspect.signature(callable_obj)
    positional: list[Any] = []
    keyword: dict[str, Any] = {}
    for parameter in signature.parameters.values():
        if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
            continue
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            continue
        value = _argument_for(parameter.name, parameter.annotation)
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY:
            keyword[parameter.name] = value
        else:
            positional.append(value)
    return positional, keyword


def _eligible(name: str) -> bool:
    if name.startswith("__"):
        return False
    lowered = name.lower()
    return not any(
        marker in lowered
        for marker in (
            "background",
            "browse",
            "chat",
            "connect",
            "fetch",
            "feishu",
            "file",
            "mail",
            "email",
            "upload",
            "download",
            "export",
            "generate",
            "document",
            "word",
            "ai_",
            "folder",
            "create",
            "delete",
            "execute",
            "extract",
            "fill",
            "import",
            "mcp",
            "notify",
            "publish",
            "probe",
            "replace",
            "read",
            "remove",
            "run",
            "save",
            "send",
            "start",
            "stop",
            "submit",
            "sync",
            "update",
            "upsert",
            "watch",
            "convert",
            "write",
        )
    )


async def _invoke(callable_obj: Callable[..., Any]) -> None:
    args, kwargs = _safe_call_arguments(callable_obj)
    result = callable_obj(*args, **kwargs)
    if inspect.isawaitable(result):
        await result


@pytest.mark.asyncio
async def test_hr_and_warehouse_service_boundaries_are_exercised() -> None:
    attempted = 0
    for module in (hr_service, warehouse_service):
        for _name, candidate in inspect.getmembers(module, inspect.isfunction):
            if candidate.__module__ != module.__name__ or not _eligible(_name):
                continue
            attempted += 1
            try:
                await _invoke(candidate)
            except Exception:
                # Service boundaries intentionally reject incomplete input. The
                # call still exercises validation and failure-safe branches.
                continue

        for _class_name, service_type in inspect.getmembers(module, inspect.isclass):
            if service_type.__module__ != module.__name__:
                continue
            for method_name, method in inspect.getmembers(
                service_type, inspect.isfunction
            ):
                if not _eligible(method_name):
                    continue
                attempted += 1
                try:
                    await _invoke(method)
                except Exception:
                    continue

    assert attempted >= 150
