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
_task_tool_traces: dict[str, list[dict[str, Any]]] = {}
_task_confirmations: dict[str, list[dict[str, Any]]] = {}
_task_request_contexts_lock = threading.Lock()
_FORCED_OPERATION_FALLBACKS = frozenset({"identity.deliver_feishu_message"})


def register_dazah_task_context(task_id: str, context: dict[str, Any]) -> None:
    with _task_request_contexts_lock:
        _task_request_contexts[task_id] = dict(context)
        _task_tool_traces[task_id] = []
        _task_confirmations[task_id] = []


def unregister_dazah_task_context(task_id: str) -> None:
    with _task_request_contexts_lock:
        _task_request_contexts.pop(task_id, None)
        _task_tool_traces.pop(task_id, None)
        _task_confirmations.pop(task_id, None)


def current_dazah_task_tool_trace(task_id: str) -> list[dict[str, Any]]:
    """Return only tool executions recorded for the registered runtime task."""
    with _task_request_contexts_lock:
        return [dict(item) for item in _task_tool_traces.get(task_id, [])]


def current_dazah_task_confirmations(task_id: str) -> list[dict[str, Any]]:
    """Return confirmations created by tools during this runtime task only."""
    with _task_request_contexts_lock:
        return [dict(item) for item in _task_confirmations.get(task_id, [])]


def record_dazah_task_confirmation(
    task_id: str | None,
    confirmation: dict[str, Any],
) -> None:
    if not task_id or confirmation.get("status") != "pending":
        return
    confirmation_id = str(confirmation.get("id") or "")
    if not confirmation_id:
        return
    with _task_request_contexts_lock:
        items = _task_confirmations.get(task_id)
        if items is None or any(str(item.get("id")) == confirmation_id for item in items):
            return
        items.append(dict(confirmation))


def _record_dazah_task_tool_trace(
    task_id: str | None,
    item: dict[str, Any],
) -> None:
    if not task_id:
        return
    with _task_request_contexts_lock:
        trace = _task_tool_traces.get(task_id)
        if trace is not None:
            trace.append(dict(item))


def record_dazah_task_tool_trace(task_id: str | None, item: dict[str, Any]) -> None:
    """Record a trusted tool attempt for gateway postcondition checks."""
    _record_dazah_task_tool_trace(task_id, item)


def _execute_trace_item(
    operation: str,
    payload: dict[str, Any],
    *,
    status_code: int,
) -> dict[str, Any]:
    data = payload.get("data")
    result = data if isinstance(data, dict) and "ok" in data else payload
    ok = status_code < 400 and result.get("ok") is True
    requires_confirmation = result.get("requires_confirmation") is True
    trace_item: dict[str, Any] = {
        "action": "execute",
        "operation": operation,
        "ok": ok,
        "status": (
            "confirmation_required"
            if ok and requires_confirmation
            else "completed"
            if ok
            else "failed"
        ),
        "confirmation_created": ok and requires_confirmation,
    }
    result_data = result.get("data")
    if isinstance(result_data, dict):
        delivery = {
            key: result_data[key]
            for key in ("delivery_id", "status", "channel")
            if result_data.get(key) is not None
        }
        if delivery:
            trace_item["result"] = delivery
    return trace_item


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

    context = current_dazah_request_context(task_id)
    if action == "execute" and not operation:
        forced_operation = str(context.get("forced_operation") or "").strip()
        if forced_operation in _FORCED_OPERATION_FALLBACKS:
            operation = forced_operation

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
                response = await client.post(
                    f"{_base_url()}/agent/tools/execute",
                    json={
                        "operation": operation,
                        "params": params or {},
                        "body": body,
                        "subject": subject,
                        "session_id": context.get("platform_session_id"),
                        "trace_id": context.get("trace_id"),
                        "reason": reason,
                    },
                    headers=headers,
                )
        if response.status_code >= 400:
            if action == "execute" and operation:
                _record_dazah_task_tool_trace(
                    task_id,
                    _execute_trace_item(
                        operation,
                        {},
                        status_code=response.status_code,
                    ),
                )
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
        response_payload = response.json()
        if action == "execute" and operation and isinstance(response_payload, dict):
            _record_dazah_task_tool_trace(
                task_id,
                _execute_trace_item(
                    operation,
                    response_payload,
                    status_code=response.status_code,
                ),
            )
            response_data = response_payload.get("data")
            confirmation_source = (
                response_data if isinstance(response_data, dict) else response_payload
            )
            confirmation = confirmation_source.get("confirmation")
            if isinstance(confirmation, dict):
                record_dazah_task_confirmation(task_id, confirmation)
        return json.dumps(response_payload, ensure_ascii=False)
    except httpx.HTTPError as exc:
        if action == "execute" and operation:
            _record_dazah_task_tool_trace(
                task_id,
                _execute_trace_item(operation, {}, status_code=503),
            )
        return json.dumps(
            {
                "ok": False,
                "action": action,
                "operation": operation,
                "error": type(exc).__name__,
            },
            ensure_ascii=False,
        )


async def _dispatch_dazah_tool(
    args: dict[str, Any],
    *,
    task_id: str | None = None,
    user_task: str | None = None,
) -> str:
    """Adapt the registry's dict-argument contract to ``dazah_tool`` kwargs."""
    return await dazah_tool(
        action=args.get("action", ""),
        query=args.get("query", ""),
        module=args.get("module"),
        limit=args.get("limit", 12),
        operation=args.get("operation"),
        params=args.get("params"),
        body=args.get("body"),
        reason=args.get("reason"),
        task_id=task_id,
        user_task=user_task,
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
    handler=_dispatch_dazah_tool,
    check_fn=check_dazah_requirements,
    requires_env=["DAZAH_AGENT_TOOL_TOKEN"],
    is_async=True,
    description="Dazah progressive tool gateway",
    emoji="",
)
