#!/usr/bin/env python3
"""Single progressively-disclosed Dazah business tool gateway."""

import contextvars
import json
import os
import threading
from typing import Any, Literal

import httpx

from tools.registry import registry

dazah_request_context: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "dazah_request_context",
    default={},
)
_dazah_thread_request_context = threading.local()
_MISSING_THREAD_CONTEXT = object()
_task_request_contexts: dict[str, dict[str, Any]] = {}
_task_request_contexts_lock = threading.Lock()


def register_dazah_task_context(task_id: str, context: dict[str, Any]) -> None:
    with _task_request_contexts_lock:
        _task_request_contexts[task_id] = dict(context)


def unregister_dazah_task_context(task_id: str) -> None:
    with _task_request_contexts_lock:
        _task_request_contexts.pop(task_id, None)


def current_dazah_request_context(task_id: str | None = None) -> dict[str, Any]:
    if task_id:
        with _task_request_contexts_lock:
            task_context = _task_request_contexts.get(task_id)
            if task_context:
                return dict(task_context)
    context = dazah_request_context.get({})
    if context:
        return context
    thread_context = getattr(_dazah_thread_request_context, "value", None)
    if isinstance(thread_context, dict):
        return thread_context
    return {}


def bind_dazah_thread_request_context(context: dict[str, Any]) -> Any:
    previous = getattr(
        _dazah_thread_request_context,
        "value",
        _MISSING_THREAD_CONTEXT,
    )
    _dazah_thread_request_context.value = dict(context)
    return previous


def reset_dazah_thread_request_context(previous: Any) -> None:
    if previous is _MISSING_THREAD_CONTEXT:
        try:
            del _dazah_thread_request_context.value
        except AttributeError:
            pass
        return
    _dazah_thread_request_context.value = previous


def _base_url() -> str:
    return os.getenv(
        "DAZAH_API_BASE_URL",
        "http://127.0.0.1:8000/api/v1",
    ).rstrip("/")


def check_dazah_requirements() -> bool:
    return bool(os.getenv("DAZAH_AGENT_TOOL_TOKEN"))


def _trusted_subject(task_id: str | None) -> dict[str, Any]:
    context = current_dazah_request_context(task_id)
    user_id = str(context.get("user_id") or "").strip()
    tenant_id = str(context.get("tenant_id") or "").strip()
    if not user_id or not tenant_id:
        raise PermissionError("trusted Dazah subject is unavailable")
    source = str(context.get("channel") or "internal")
    if source not in {"web", "feishu", "automation", "internal"}:
        source = "internal"
    return {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "display_name": context.get("user_name"),
        "source": source,
        "external_binding_id": context.get("external_binding_id"),
    }


async def dazah_tool(
    action: Literal["search", "describe", "execute"],
    *,
    query: str = "",
    module: str | None = None,
    limit: int = 12,
    operation: str | None = None,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    reason: str | None = None,
    task_id: str | None = None,
    user_task: str | None = None,
) -> str:
    del user_task
    token = os.getenv("DAZAH_AGENT_TOOL_TOKEN")
    if not token:
        return json.dumps(
            {"ok": False, "error": "DAZAH_AGENT_TOOL_TOKEN is not configured"},
            ensure_ascii=False,
        )
    try:
        subject = _trusted_subject(task_id)
    except PermissionError as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            if action == "search":
                response = await client.post(
                    f"{_base_url()}/agent/tools/search",
                    json={
                        "query": query,
                        "module": module,
                        "limit": limit,
                        "subject": subject,
                    },
                    headers=headers,
                )
            elif action == "describe":
                if not operation:
                    return json.dumps(
                        {"ok": False, "error": "operation is required for describe"},
                        ensure_ascii=False,
                    )
                response = await client.get(
                    f"{_base_url()}/agent/tools/{operation}",
                    params={"subject_user_id": subject["user_id"]},
                    headers=headers,
                )
            else:
                if not operation:
                    return json.dumps(
                        {"ok": False, "error": "operation is required for execute"},
                        ensure_ascii=False,
                    )
                context = current_dazah_request_context(task_id)
                response = await client.post(
                    f"{_base_url()}/agent/tools/execute",
                    json={
                        "operation": operation,
                        "params": params or {},
                        "body": body,
                        "subject": subject,
                        "trace_id": context.get("trace_id"),
                        "reason": reason,
                    },
                    headers=headers,
                )
        if response.status_code >= 400:
            return json.dumps(
                {
                    "ok": False,
                    "action": action,
                    "operation": operation,
                    "status_code": response.status_code,
                    "error": response.text[:1000],
                },
                ensure_ascii=False,
            )
        return json.dumps(response.json(), ensure_ascii=False)
    except httpx.HTTPError as exc:
        return json.dumps(
            {
                "ok": False,
                "action": action,
                "operation": operation,
                "error": type(exc).__name__,
            },
            ensure_ascii=False,
        )


DAZAH_TOOL_SCHEMA = {
    "name": "dazah_tool",
    "description": (
        "Discover and execute Dazah business capabilities. Start with action=search, "
        "then action=describe for the selected operation, then action=execute with "
        "schema-valid input. Dazah permissions and confirmations are enforced by the "
        "backend. This tool is not used for native Feishu documents, Drive, Base or "
        "messages; use lark_cli for those resources."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["search", "describe", "execute"],
            },
            "query": {
                "type": "string",
                "description": "Capability intent for search.",
            },
            "module": {
                "type": "string",
                "description": "Optional Dazah business module filter.",
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            "operation": {
                "type": "string",
                "description": "Exact operation returned by search.",
            },
            "params": {"type": "object"},
            "body": {"type": "object"},
            "reason": {
                "type": "string",
                "description": "User-facing summary for a write confirmation.",
            },
        },
        "required": ["action"],
    },
}


registry.register(
    name="dazah_tool",
    toolset="dazah",
    schema=DAZAH_TOOL_SCHEMA,
    handler=dazah_tool,
    check_fn=check_dazah_requirements,
    requires_env=["DAZAH_AGENT_TOOL_TOKEN"],
    is_async=True,
    description="Dazah progressive tool gateway",
    emoji="",
)
