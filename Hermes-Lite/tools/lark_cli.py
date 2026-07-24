"""Single safe Hermes tool for official Feishu CLI operations."""

from __future__ import annotations

import json
import os
from typing import Any

from services.feishu_runtime import (
    authorize,
    classify_risk,
    create_confirmation,
    enqueue_audit,
    has_active_grant,
    load_credentials,
    run_cli,
    validate_args,
)
from tools.dazah_platform import current_dazah_request_context
from tools.registry import registry


def check_lark_cli_requirements() -> bool:
    # Keep the tool visible so configuration errors are returned explicitly.
    # Requiring the credential key here silently removes lark_cli from the
    # model's tool list and makes it fall back to unrelated Dazah tools.
    return bool(os.getenv("LARK_CLI_PATH"))


async def lark_cli(
    args: list[str] | dict[str, Any],
    stdin_json: dict[str, Any] | list[Any] | None = None,
    attachment_refs: list[str] | None = None,
    resource: str = "",
    module: str | None = None,
    impact_count: int = 1,
    risk_hint: str | None = None,
    **_ignored: Any,
) -> str:
    if isinstance(args, dict):
        payload = args
        args = payload.get("args", [])
        stdin_json = payload.get("stdin_json", stdin_json)
        attachment_refs = payload.get("attachment_refs", attachment_refs)
        resource = str(payload.get("resource", resource) or "")
        module_value = payload.get("module", module)
        module = str(module_value) if module_value else None
        impact_count = int(payload.get("impact_count", impact_count))
        risk_value = payload.get("risk_hint", risk_hint)
        risk_hint = str(risk_value) if risk_value else None
    task_id = str(_ignored.get("task_id", "") or "")
    context = current_dazah_request_context(task_id)
    user_id = str(context.get("feishu_sender_id") or context.get("user_id") or "")
    if not user_id:
        return json.dumps(
            {
                "ok": False,
                "error": "missing Feishu sender context",
                "task_id_received": bool(task_id),
                "trusted_context_found": bool(context),
                "trusted_context_fields": sorted(context),
            },
            ensure_ascii=False,
        )
    if not os.getenv("HERMES_FEISHU_CREDENTIAL_KEY"):
        return json.dumps(
            {
                "ok": False,
                "error": (
                    "Hermes Feishu credential encryption key is not configured; "
                    "set HERMES_FEISHU_CREDENTIAL_KEY and save the Livzon Feishu "
                    "credentials again"
                ),
            },
            ensure_ascii=False,
        )
    try:
        safe_args = validate_args(args, attachment_refs)
        risk, reason = classify_risk(safe_args, risk_hint)
        write = risk != "low" or any(word in " ".join(safe_args).lower() for word in ("append", "comment", "add"))
        user = authorize(user_id, write=write, module=module)
        credentials = load_credentials()
        if credentials is None:
            raise RuntimeError("Feishu credentials are not configured")
        app_id = credentials[0]
        if risk == "prohibited":
            return json.dumps({"ok": False, "risk": risk, "error": reason}, ensure_ascii=False)
        if impact_count < 0:
            raise ValueError("impact_count must be non-negative")
        if risk == "low" and write and impact_count > 20:
            risk, reason = "medium", "新增影响数量超过低风险阈值"
        if write:
            enqueue_audit(
                {
                    "user_id": user_id,
                    "resource_fingerprint": resource,
                    "capability": " ".join(safe_args[:2]),
                    "risk": risk,
                    "confirmation": "none" if risk == "low" else "pending",
                    "impact_count": impact_count,
                }
            )
            dry_run_args = safe_args if "--dry-run" in safe_args else [*safe_args, "--dry-run"]
            preview = await run_cli(dry_run_args, stdin_text=json.dumps(stdin_json or {}, ensure_ascii=False))
            if preview.returncode != 0:
                return json.dumps(
                    {"ok": False, "stage": "dry_run", "risk": risk, "error": preview.stderr[-1000:]},
                    ensure_ascii=False,
                )
        if risk in {"medium", "high"}:
            action = " ".join(safe_args[:2])
            if risk == "medium" and has_active_grant(
                user_id=user_id,
                app_id=app_id,
                resource=resource or "unknown",
                action=action,
            ):
                risk = "low"
            else:
                pending = create_confirmation(
                    user_id=user_id,
                    app_id=app_id,
                    resource=resource or "unknown",
                    action=action,
                    args=safe_args,
                    stdin_json=stdin_json,
                    module=module,
                    risk=risk,
                    reason=reason,
                    impact_count=impact_count,
                    preview=preview.stdout,
                )
                return json.dumps(
                    {
                        "ok": True,
                        "status": "pending_confirmation",
                        "requires_confirmation": True,
                        "confirmation": pending,
                        "pending_confirmation": pending,
                        "allow_always": risk == "medium",
                        "reason": reason,
                        "resource": resource,
                        "impact_count": impact_count,
                    },
                    ensure_ascii=False,
                )
        result = await run_cli(safe_args, stdin_text=json.dumps(stdin_json or {}, ensure_ascii=False))
        if write and result.returncode == 0 and resource:
            enqueue_audit(
                {
                    "resource_fingerprint": resource,
                    "capability": " ".join(safe_args[:2]),
                },
                event_type="resource_change",
            )
        return json.dumps(
            {
                "ok": result.returncode == 0,
                "status": "completed" if result.returncode == 0 else "failed",
                "output": result.stdout,
                "error": result.stderr,
                "elapsed_ms": result.elapsed_ms,
                "user": user.get("display_name") or user_id,
            },
            ensure_ascii=False,
        )
    except (ValueError, PermissionError, RuntimeError) as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


registry.register(
    name="lark_cli",
    toolset="feishu",
    schema={
        "name": "lark_cli",
        "description": (
            "Use the pinned official lark-cli as the Feishu bot identity. Pass an argument array only. "
            "Reads and small traceable additions may execute immediately; edits return confirmation data; "
            "deletes, moves, sharing, permissions and version replacement always require one-time confirmation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "args": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 64},
                "stdin_json": {
                    "type": "object",
                    "description": "Optional JSON object passed to lark-cli stdin.",
                },
                "attachment_refs": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
                "resource": {"type": "string", "description": "Feishu resource token or URL shown in confirmation."},
                "module": {
                    "type": "string",
                    "description": "Optional Dazah module code when the resource is registered to a module.",
                },
                "impact_count": {"type": "integer", "minimum": 0},
                "risk_hint": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Optional semantic risk review; it can only raise the fixed risk.",
                },
            },
            "required": ["args"],
        },
    },
    handler=lark_cli,
    check_fn=check_lark_cli_requirements,
    requires_env=["LARK_CLI_PATH"],
    is_async=True,
    description="Pinned official Feishu CLI with local authorization and risk enforcement",
    emoji="",
)
