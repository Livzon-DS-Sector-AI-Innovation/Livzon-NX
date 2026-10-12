#!/usr/bin/env python3
"""Single progressively-disclosed Dazah business tool gateway."""

import contextvars
import json
import logging
import os
import threading
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

import httpx

from tools.registry import registry
from services.agent_task_contract import AgentTaskPlan, TaskEvidence, build_draft_evidence, evaluate_plan, safe_business_value
from services.task_recovery import empty_result, validation_fields
from services.business_reply import reported_total

dazah_request_context: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "dazah_request_context",
    default={},
)
_dazah_thread_request_context = threading.local()
_MISSING_THREAD_CONTEXT = object()
_task_request_contexts: dict[str, dict[str, Any]] = {}
_task_tool_traces: dict[str, list[dict[str, Any]]] = {}
_task_confirmations: dict[str, list[dict[str, Any]]] = {}
_task_plans: dict[str, AgentTaskPlan] = {}
_task_evidence: dict[str, list[TaskEvidence]] = {}
_task_request_contexts_lock = threading.Lock()
_FORCED_OPERATION_FALLBACKS = frozenset({"identity.deliver_feishu_message"})


def register_dazah_task_context(task_id: str, context: dict[str, Any]) -> None:
    with _task_request_contexts_lock:
        _task_request_contexts[task_id] = dict(context)
        _task_tool_traces[task_id] = []
        _task_confirmations[task_id] = []
        _task_evidence[task_id] = []


def unregister_dazah_task_context(task_id: str) -> None:
    with _task_request_contexts_lock:
        _task_request_contexts.pop(task_id, None)
        _task_tool_traces.pop(task_id, None)
        _task_confirmations.pop(task_id, None)
        _task_plans.pop(task_id, None)
        _task_evidence.pop(task_id, None)


def configure_dazah_task_plan(task_id: str, plan: AgentTaskPlan) -> None:
    with _task_request_contexts_lock:
        if task_id in _task_request_contexts:
            _task_plans[task_id] = plan.model_copy(deep=True)


def current_dazah_task_evidence(task_id: str) -> list[TaskEvidence]:
    with _task_request_contexts_lock:
        return [item.model_copy(deep=True) for item in _task_evidence.get(task_id, [])]


def retain_dazah_analysis_evidence(task_id: str, evidence: list[TaskEvidence]) -> None:
    with _task_request_contexts_lock:
        if task_id not in _task_evidence:
            return
        _task_evidence[task_id].extend(item.model_copy(deep=True) for item in evidence)
        _task_tool_traces[task_id].extend({
            "action": "analysis", "step_id": item.step_id,
            "status": "completed" if item.ok else "failed", "evidence_id": item.id,
        } for item in evidence)


def complete_dazah_draft_steps(task_id: str) -> None:
    with _task_request_contexts_lock:
        plan = _task_plans.get(task_id)
        if plan is None:
            return
        additions = build_draft_evidence(plan, _task_evidence.get(task_id, []))
        _task_evidence[task_id].extend(additions)
        _task_tool_traces[task_id].extend({"action": "draft", "status": "preview",
                                         "step_id": item.step_id, "evidence_id": item.id} for item in additions)


def _retain_task_evidence(
    task_id: str | None, step_id: str | None, action: str, operation: str | None,
    *, ok: bool, data: Any = None, filters: dict[str, Any] | None = None,
    write: bool | None = None, confirmation_id: str | None = None, error_code: str | None = None,
    evidence_id: str | None = None,
    error_fields: list[str] | None = None,
) -> None:
    if not task_id or action not in {"search", "describe", "execute"}:
        return
    # Directory entries are bounded by the backend search limit; preserve all
    # entries. Business record lists are capped before retention and rendering.
    safe_data = data if action == "search" else safe_business_value(data)
    description = _described_capability(task_id, operation) if action == "execute" else {}
    result_kind = description.get("result_kind")
    output_hint = description.get("output_hint")
    output_hint = output_hint[:800] if isinstance(output_hint, str) else None
    if result_kind not in {"records", "statistics", "knowledge_index", "knowledge"}:
        result_kind = None
    item = TaskEvidence(id=evidence_id or uuid.uuid4().hex, step_id=step_id or "unplanned", action=action, operation=operation,
                        ok=ok, occurred_at=datetime.now(UTC).isoformat(), filters=safe_business_value(filters or {}),
                        data=safe_data, write=write, confirmation_id=confirmation_id, error_code=error_code,
                        error_fields=error_fields or [], result_kind=result_kind, output_hint=output_hint)
    if action == "execute" and ok and write is False:
        total = reported_total(safe_data)
        logging.getLogger(__name__).info(
            "Read query outcome operation=%s filter_keys=%s reported_total=%s",
            operation, sorted(item.filters), total[0] if total is not None else None,
        )
    with _task_request_contexts_lock:
        items = _task_evidence.get(task_id)
        if items is not None:
            items.append(item)
            if step_id:
                _task_tool_traces[task_id].append({
                    "action": "evidence", "step_id": step_id, "evidence_id": item.id,
                    "operation": operation, "status": "verified" if ok else "failed",
                    "occurred_at": item.occurred_at,
                })


def _described_capability(task_id: str | None, operation: str | None) -> dict[str, Any]:
    return next((entry for item in reversed(current_dazah_task_tool_trace(task_id or ""))
                 if item.get("action") == "describe" and item.get("ok") is True
                 for entry in item.get("capabilities", []) if entry.get("operation") == operation), {})


async def _request_with_read_retry(
    client: httpx.AsyncClient, method: str, url: str, *, task_id: str | None, retry: bool, **kwargs: Any,
) -> httpx.Response:
    """Retry a temporary failure once, with exactly the same read request."""
    for attempt in range(2):
        try:
            response = await getattr(client, method)(url, **kwargs)
        except httpx.HTTPError:
            if not retry or attempt:
                raise
        else:
            if not retry or attempt or response.status_code not in {429, 500, 502, 503, 504}:
                return response
        cancellation = current_dazah_request_context(task_id).get("_cancellation_event")
        if cancellation is not None and cancellation.is_set():
            raise httpx.RequestError("run_cancelled")
        _record_dazah_task_tool_trace(task_id, {"action": "retry", "status": "attempted", "attempt": 1})
    raise RuntimeError("unreachable retry state")


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


def enable_dazah_task_read_only_repair(task_id: str, *, max_calls: int = 6) -> None:
    """Bind a bounded repair policy to gateway-owned task context."""
    with _task_request_contexts_lock:
        context = _task_request_contexts.get(task_id)
        if context is not None:
            context["_read_only_repair"] = True
            context["_repair_calls_remaining"] = max_calls


def finish_dazah_task_read_only_repair(task_id: str) -> None:
    """End only the bounded repair phase; retain all write receipts and guards."""
    with _task_request_contexts_lock:
        context = _task_request_contexts.get(task_id)
        if context is not None:
            context.pop("_read_only_repair", None)
            context.pop("_repair_calls_remaining", None)


def _tool_failure(task_id: str | None, action: str, operation: str | None, code: str) -> str:
    _record_dazah_task_tool_trace(task_id, {
        "action": action, "operation": operation, "ok": False,
        "status": "failed", "error_code": code,
    })
    return json.dumps({"ok": False, "action": action, "operation": operation, "error": code})


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
    if status_code >= 400:
        trace_item["status_code"] = status_code
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
    step_id: str | None = None,
    user_task: str | None = None,
) -> str:
    del user_task
    evidence_id = uuid.uuid4().hex
    spec = _described_capability(task_id, operation)

    def fail(code: str) -> str:
        _retain_task_evidence(task_id, step_id, action, operation, ok=False, write=spec.get("write"),
                              filters=params or {}, error_code=code, evidence_id=evidence_id)
        return _tool_failure(task_id, action, operation, code)

    plan = _task_plans.get(task_id or "")
    if plan is not None:
        complete_dazah_draft_steps(task_id or "")
        if step_id is None and len(plan.steps) == 1:
            step_id = plan.steps[0].id
        step = next((item for item in plan.steps if item.id == step_id), None)
        if step is None:
            return fail("valid_step_id_required")
        outcomes = evaluate_plan(plan, current_dazah_task_evidence(task_id or ""))
        states = {item.id: item.state for item in outcomes}
        if action == "execute" and (step.missing_inputs or any(states[dep] != "completed" for dep in step.depends_on)):
            return fail("step_dependencies_or_inputs_missing")
        if action == "execute":
            descriptions = [entry for item in current_dazah_task_tool_trace(task_id or "")
                            if item.get("action") == "describe" and item.get("ok") is True
                            for entry in item.get("capabilities", []) if entry.get("operation") == operation]
            latest = descriptions[-1] if descriptions else {}
            expected_write = step.kind == "write"
            if step.kind in {"capability", "general", "draft"} or latest.get("write") is not expected_write:
                return fail("step_operation_kind_mismatch")

    def retain_failure(code: str, fields: list[str] | None = None) -> None:
        _retain_task_evidence(task_id, step_id, action, operation, ok=False, write=spec.get("write"),
                              filters=params or {}, error_code=code, evidence_id=evidence_id, error_fields=fields)
        if action == "execute" and code in {"http_400", "http_422"}:
            with _task_request_contexts_lock:
                trusted = _task_request_contexts.get(task_id or "")
                if trusted is not None:
                    trusted.setdefault("_parameter_failures", {})[step_id or operation] = {
                        "operation": operation, "input": {**(params or {}), **(body or {})}, "fields": fields or [],
                    }
        if action == "execute" and spec.get("write") is not False and code in {
            "timeout", "connection_failed", "http_500", "http_502", "http_503", "http_504", "invalid_response",
        }:
            with _task_request_contexts_lock:
                trusted = _task_request_contexts.get(task_id or "")
                if trusted is not None:
                    trusted.setdefault("_uncertain_writes", set()).add(operation)

    token = os.getenv("DAZAH_AGENT_TOOL_TOKEN")
    if not token:
        retain_failure("tool_not_configured")
        return _tool_failure(task_id, action, operation, "tool_not_configured")
    try:
        subject = _trusted_subject(task_id)
    except PermissionError:
        retain_failure("subject_unavailable")
        return _tool_failure(task_id, action, operation, "subject_unavailable")

    context = current_dazah_request_context(task_id)
    if action == "execute" and context.get("_uncertain_writes") and spec.get("write") is not False:
        return fail("write_execution_unknown")
    if action == "execute" and task_id:
        previous = [item for item in current_dazah_task_evidence(task_id or "")
                    if (item.step_id == step_id if plan is not None else item.operation == operation)
                    and item.action == "execute" and item.ok]
        if previous and empty_result(previous[-1].data):
            return fail("empty_result_requires_user_choice")
        if spec.get("write") is True and previous:
            return fail("write_already_submitted")
    cancellation = context.get("_cancellation_event")
    if cancellation is not None and cancellation.is_set():
        return fail("run_cancelled")
    if context.get("_read_only_repair"):
        parameter_failure = context.get("_parameter_failures", {}).get(step_id or operation)
        if action == "execute" and parameter_failure:
            allowed_fields = {field.split(".")[0] for field in parameter_failure["fields"]}
            previous_input = parameter_failure["input"]
            proposed = {**(params or {}), **(body or {})}
            if not allowed_fields or parameter_failure["operation"] != operation or any(
                key not in allowed_fields and previous_input.get(key) != proposed.get(key)
                for key in set(previous_input) | set(proposed)
            ):
                return fail("parameter_repair_requires_user_input")
        with _task_request_contexts_lock:
            trusted_context = _task_request_contexts.get(task_id or "", {})
            remaining = trusted_context.get("_repair_calls_remaining", 0)
            if remaining > 0:
                trusted_context["_repair_calls_remaining"] = remaining - 1
        if remaining <= 0:
            return fail("repair_budget_exhausted")
        if action == "execute":
            trace = current_dazah_task_tool_trace(task_id or "")
            if any(item.get("action") == "execute" and item.get("operation") == operation
                   and item.get("ok") is True for item in trace):
                return fail("repair_already_completed")
            descriptions = [
                entry for item in trace if item.get("action") == "describe" and item.get("ok") is True
                for entry in item.get("capabilities", []) if entry.get("operation") == operation
            ]
            latest = descriptions[-1] if descriptions else {}
            described_read = latest.get("write") is False and latest.get("confirmation_required") is not True
            if not described_read:
                return fail("repair_read_only")
    trace_id = str(context.get("trace_id") or uuid.uuid4())
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
                response = await _request_with_read_retry(
                    client, "post", f"{_base_url()}/agent/tools/search", task_id=task_id, retry=True,
                    json={
                        "query": query,
                        "module": module,
                        "limit": limit,
                        "subject": subject,
                        "trace_id": trace_id,
                    },
                    headers=headers,
                )
            elif action == "describe":
                if not operation:
                    return json.dumps(
                        {"ok": False, "error": "operation is required for describe"},
                        ensure_ascii=False,
                    )
                response = await _request_with_read_retry(
                    client, "get", f"{_base_url()}/agent/tools/{operation}", task_id=task_id, retry=True,
                    params={
                        "subject_user_id": subject["user_id"],
                        "subject_tenant_id": subject["tenant_id"],
                        "trace_id": trace_id,
                    },
                    headers=headers,
                )
            else:
                if not operation:
                    return json.dumps(
                        {"ok": False, "error": "operation is required for execute"},
                        ensure_ascii=False,
                    )
                response = await _request_with_read_retry(
                    client, "post", f"{_base_url()}/agent/tools/execute", task_id=task_id, retry=spec.get("write") is False,
                    json={
                        "operation": operation,
                        "params": params or {},
                        "body": body,
                        "subject": subject,
                        "session_id": context.get("platform_session_id"),
                        "trace_id": trace_id,
                        "reason": reason,
                        **({"execution_context": {"task_step_id": step_id, "evidence_id": evidence_id}}
                           if plan is not None else {}),
                    },
                    headers=headers,
                )
        if response.status_code >= 400:
            fields = []
            if response.status_code in {400, 422}:
                try:
                    fields = validation_fields(response.json())
                except ValueError:
                    pass
            retain_failure(f"http_{response.status_code}", fields)
            if action == "execute" and operation:
                _record_dazah_task_tool_trace(
                    task_id,
                    _execute_trace_item(
                        operation,
                        {},
                        status_code=response.status_code,
                    ),
                )
            else:
                _record_dazah_task_tool_trace(task_id, {
                    "action": action, "operation": operation, "ok": False,
                    "status": "failed", "status_code": response.status_code,
                })
            error_payload = {
                    "ok": False,
                    "action": action,
                    "operation": operation,
                    "status_code": response.status_code,
                    "error": response.text[:1000],
                }
            if response.status_code == 403:
                error_payload["repair_hint"] = (
                    "当前 Dazah 身份没有此能力的模块 Scope 或数据权限。"
                    "请管理员在用户模块权限中授权对应模块，并同步 Livzon Agent 访问范围后重试。"
                )
            return json.dumps(error_payload, ensure_ascii=False)
        try:
            response_payload = response.json()
        except ValueError:
            retain_failure("invalid_response")
            return _tool_failure(task_id, action, operation, "invalid_response")
        if action in {"search", "describe"} and isinstance(response_payload, dict):
            # Catalog evidence describes available operations; it is never
            # evidence that an operation executed or returned business records.
            data = response_payload.get("data")
            entries = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
            if isinstance(data, (list, dict)) and response_payload.get("ok") is not False:
                capabilities = [
                    {
                        key: entry[key]
                        for key in ("operation", "summary", "write", "confirmation_required", "result_kind", "output_hint")
                        if key in entry
                    }
                    for entry in entries
                    if isinstance(entry, dict) and isinstance(entry.get("operation"), str)
                ]
                _record_dazah_task_tool_trace(
                    task_id,
                    {"action": action, "ok": True, "capabilities": capabilities},
                )
                _retain_task_evidence(task_id, step_id, action, operation, ok=True,
                                      data=capabilities if action == "search" else data,
                                      filters={"query": query, "module": module, "limit": limit} if action == "search" else {},
                                      evidence_id=evidence_id)
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
            spec = next((entry for item in reversed(current_dazah_task_tool_trace(task_id or ""))
                         if item.get("action") == "describe" and item.get("ok") is True
                         for entry in item.get("capabilities", []) if entry.get("operation") == operation), {})
            ok = confirmation_source.get("ok") is True
            meta = confirmation_source.get("meta")
            if not ok and isinstance(meta, dict) and meta.get("validation") == "failed":
                invalid_data = confirmation_source.get("data")
                message = invalid_data.get("message") if isinstance(invalid_data, dict) else None
                retain_failure("http_400", validation_fields({"detail": message}))
            else:
                _retain_task_evidence(task_id, step_id, action, operation, ok=ok,
                                      data=confirmation_source.get("data"), filters=params or {},
                                      write=spec.get("write"),
                                      confirmation_id=str(confirmation.get("id")) if isinstance(confirmation, dict) else None,
                                      error_code=None if ok else "execution_rejected", evidence_id=evidence_id)
        return json.dumps(response_payload, ensure_ascii=False)
    except httpx.HTTPError as exc:
        retain_failure("timeout" if isinstance(exc, httpx.TimeoutException) else "connection_failed")
        _record_dazah_task_tool_trace(task_id, {
            "action": action, "operation": operation, "ok": False, "status": "failed",
            "error_code": "timeout" if isinstance(exc, httpx.TimeoutException) else "connection_failed",
        })
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
        step_id=args.get("step_id"),
        user_task=user_task,
    )


DAZAH_TOOL_SCHEMA = {
    "name": "dazah_tool",
    "description": (
        "Discover and execute Dazah business capabilities. Start with action=search, "
        "then action=describe for the selected operation, then action=execute with "
        "schema-valid input. Dazah permissions and confirmations are enforced by the "
        "backend. Search using business objects/actions; if results are empty or irrelevant, "
        "rephrase, split the goal, filter by module, or browse with an empty query and limit up to 50. "
        "Search results are partial discovery, not business data or an exhaustive capability list. "
        "Read schemas before asking for missing input; continue discovery as new results arrive. "
        "This tool is not used for native Feishu documents, Drive, Base or "
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
            "step_id": {
                "type": "string",
                "description": "Subtask ID from the current validated task plan; required for multi-step requests.",
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
