"""Single safe Hermes tool for official Feishu CLI operations."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from services.feishu_runtime import (
    classify_risk,
    cli_result_succeeded,
    create_confirmation,
    enqueue_audit,
    effective_verification_mode,
    expected_absence_text,
    expected_verification_text,
    has_active_grant,
    infer_explicit_resource,
    infer_impact_count,
    is_write_operation,
    load_credentials,
    normalize_base_record_write_args,
    normalize_document_write_content,
    run_cli,
    resource_fingerprint,
    safe_change_preview,
    safe_resource_label,
    validate_args,
    validate_base_record_write_values,
    validate_destructive_intent,
    validate_nonempty_write_content,
    validate_verification_contract,
    verify_write_result,
)
from tools.dazah_platform import (
    current_dazah_request_context,
    record_dazah_task_confirmation,
    record_dazah_task_tool_trace,
)
from tools.registry import registry


def check_lark_cli_requirements() -> bool:
    # Keep the tool visible so configuration errors are returned explicitly.
    # Requiring the credential key here silently removes lark_cli from the
    # model's tool list and makes it fall back to unrelated Dazah tools.
    return bool(os.getenv("LARK_CLI_PATH"))


def _confirmation_owner_id(context: dict[str, Any]) -> str:
    """Use the stable Dazah subject; Feishu IDs vary by event shape."""
    return str(context.get("user_id") or context.get("feishu_sender_id") or "")


def _bind_trusted_resource_target(args: list[str], resource: str) -> list[str]:
    """Materialize a trusted follow-up URL into typed write argv."""
    if not resource or len(args) < 2:
        return args
    root = args[0].lower()
    mappings = {
        "docs": (("--doc", "--document-id", "--document-token", "--url"), "--doc"),
        "sheets": (("--spreadsheet-token", "--url"), "--url"),
        "wiki": (("--node-token", "--token", "--url"), "--node-token"),
    }
    mapping = mappings.get(root)
    if mapping is None:
        return args
    aliases, target_flag = mapping
    if any(item.lower() in aliases for item in args):
        return args
    return [*args, target_flag, resource]


async def lark_cli(
    args: list[str] | dict[str, Any],
    stdin_json: dict[str, Any] | list[Any] | None = None,
    attachment_refs: list[str] | None = None,
    resource: str = "",
    module: str | None = None,
    impact_count: int = 1,
    risk_hint: str | None = None,
    verification_args: list[str] | None = None,
    verification_mode: str | None = None,
    verification_text: str = "",
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
        verification_args = payload.get("verification_args", verification_args)
        verification_mode_value = payload.get("verification_mode", verification_mode)
        verification_mode = str(verification_mode_value) if verification_mode_value else None
        verification_text = str(payload.get("verification_text", verification_text) or "")
    task_id = str(_ignored.get("task_id", "") or "")
    context = current_dazah_request_context(task_id)

    def ensure_run_active() -> None:
        cancellation = context.get("_cancellation_event")
        if cancellation is not None and cancellation.is_set():
            raise RuntimeError("agent run was cancelled before the operation completed")

    raw_root = args.get("args", []) if isinstance(args, dict) else args
    operation = " ".join(
        str(item) for item in (raw_root[:2] if isinstance(raw_root, list) else [])
    )
    record_dazah_task_tool_trace(
        task_id,
        {
            "action": "execute",
            "operation": f"lark_cli {operation}".strip(),
            "status": "attempted",
        },
    )
    user_id = _confirmation_owner_id(context)
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
        ensure_run_active()
        safe_args = normalize_document_write_content(
            normalize_base_record_write_args(
                validate_args(args, attachment_refs),
                force_single_create=context.get("_single_base_record_create") is True,
            )
        )
        validate_destructive_intent(
            safe_args,
            str(context.get("current_user_message") or ""),
        )
        risk, reason = classify_risk(safe_args, risk_hint)
        if risk == "prohibited":
            return json.dumps({"ok": False, "risk": risk, "error": reason}, ensure_ascii=False)
        write = is_write_operation(safe_args)
        if not write:
            risk, reason = "low", "只读飞书资源操作"
        elif not resource:
            resource = infer_explicit_resource(safe_args)
        if write and not resource:
            # Follow-up turns often say "the document above". The gateway
            # extracts only an explicit URL from recent user messages and
            # stores it in trusted request-scoped context; never infer a target
            # from model text or a fuzzy title.
            resource = str(context.get("feishu_resource_url") or "")
        if write:
            safe_args = _bind_trusted_resource_target(safe_args, resource)
        if impact_count < 0:
            raise ValueError("impact_count must be non-negative")
        if write:
            validate_nonempty_write_content(safe_args)
            validate_base_record_write_values(
                safe_args,
                require_date_strings=context.get("_single_base_record_create") is True,
            )
        impact_count = infer_impact_count(safe_args, stdin_json, impact_count)
        fingerprint = resource_fingerprint(resource) if write else ""
        resource_label = safe_resource_label(resource)
        if verification_mode not in {None, "readback", "absence", "creation_receipt"}:
            raise ValueError("verification_mode must be readback, absence, or creation_receipt")
        verification_mode = effective_verification_mode(safe_args, verification_mode)
        verification_text = re.sub(r"\s+", " ", verification_text).strip()
        if len(verification_text) > 500:
            raise ValueError("verification_text must not exceed 500 characters")
        safe_verification_args = None
        if verification_args:
            safe_verification_args = validate_args(verification_args)
            if is_write_operation(safe_verification_args):
                raise ValueError("verification command must be read-only")
        command = ""
        if len(safe_args) >= 2 and safe_args[:2] == ["docs", "+update"] and "--command" in safe_args:
            command_index = safe_args.index("--command") + 1
            command = safe_args[command_index].lower() if command_index < len(safe_args) else ""
        if command == "block_delete":
            verification_mode = "absence"
            if not verification_text:
                raise ValueError("document block_delete requires verification_text")
            if not safe_verification_args:
                raise ValueError("document block_delete requires read-only verification_args")
            before = await run_cli(safe_verification_args)
            if before.returncode != 0:
                raise RuntimeError("pre-write readback failed for document block_delete")
            before_output = re.sub(r"\s+", " ", before.stdout)
            if verification_text not in before_output:
                raise ValueError("verification_text is not present in the target document")
        if write and verification_mode is None:
            raise ValueError("write operations require a verification_mode")
        if write:
            validate_verification_contract(
                safe_args,
                safe_verification_args,
                verification_mode,
                verification_text,
            )
        credentials = load_credentials()
        if credentials is None:
            raise RuntimeError("Feishu credentials are not configured")
        app_id = credentials[0]
        if risk == "low" and write and impact_count > 20:
            risk, reason = "medium", "新增影响数量超过低风险阈值"
        if write:
            enqueue_audit(
                {
                    "user_id": user_id,
                    "resource_fingerprint": fingerprint,
                    "capability": " ".join(safe_args[:2]),
                    "risk": risk,
                    "confirmation": "none" if risk == "low" else "pending",
                    "impact_count": impact_count,
                }
            )
            dry_run_args = safe_args if "--dry-run" in safe_args else [*safe_args, "--dry-run"]
            preview = await run_cli(dry_run_args, stdin_text=json.dumps(stdin_json or {}, ensure_ascii=False))
            if not cli_result_succeeded(preview):
                return json.dumps(
                    {"ok": False, "stage": "dry_run", "risk": risk, "error": preview.stderr[-1000:]},
                    ensure_ascii=False,
                )
            ensure_run_active()
        if risk in {"medium", "high"}:
            action = " ".join(safe_args[:2])
            if risk == "medium" and has_active_grant(
                user_id=user_id,
                app_id=app_id,
                resource=fingerprint,
                action=action,
            ):
                risk = "low"
            else:
                ensure_run_active()
                pending = create_confirmation(
                    user_id=user_id,
                    app_id=app_id,
                    resource=fingerprint,
                    action=action,
                    args=safe_args,
                    stdin_json=stdin_json,
                    module=module,
                    risk=risk,
                    reason=reason,
                    impact_count=impact_count,
                    preview=safe_change_preview(
                        safe_args,
                        impact_count=impact_count,
                        verification_text=verification_text,
                    ),
                    resource_label=resource_label,
                    verification_args=safe_verification_args,
                    verification_mode=verification_mode,
                    verification_text=verification_text,
                    attachment_refs=attachment_refs,
                )
                record_dazah_task_confirmation(task_id, pending)
                return json.dumps(
                    {
                        "ok": True,
                        "status": "pending_confirmation",
                        "requires_confirmation": True,
                        "confirmation": pending,
                        "pending_confirmation": pending,
                        "allow_always": risk == "medium",
                        "reason": reason,
                        "resource": resource_label,
                        "impact_count": impact_count,
                    },
                    ensure_ascii=False,
                )
        ensure_run_active()
        result = await run_cli(safe_args, stdin_text=json.dumps(stdin_json or {}, ensure_ascii=False))
        verification = None
        execution_succeeded = cli_result_succeeded(result)
        status_value = "completed" if execution_succeeded else "failed"
        if write and execution_succeeded:
            try:
                verification, verified = await verify_write_result(
                    result,
                    safe_verification_args,
                    verification_mode,
                    (
                        verification_text or expected_verification_text(safe_args)
                        if verification_mode == "readback"
                        else expected_verification_text(safe_args)
                    ),
                    (
                        verification_text or expected_absence_text(safe_args)
                        if verification_mode == "absence"
                        else expected_absence_text(safe_args)
                    ),
                    write_args=safe_args,
                )
            except (ValueError, PermissionError, RuntimeError) as exc:
                verification = {"verified": False, "error": str(exc)[:500]}
                verified = False
            if not verified:
                status_value = "verification_failed"
        if write and status_value == "completed":
            enqueue_audit(
                {
                    "resource_fingerprint": fingerprint,
                    "capability": " ".join(safe_args[:2]),
                },
                event_type="resource_change",
            )
        return json.dumps(
            {
                "ok": execution_succeeded and status_value != "verification_failed",
                "status": status_value,
                "output": result.stdout if status_value != "verification_failed" else "",
                "error": result.stderr or (
                    "write result could not be verified by readback"
                    if status_value == "verification_failed"
                    else ""
                ),
                "elapsed_ms": result.elapsed_ms,
                "user": context.get("user_name") or user_id,
                "verification": verification,
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
            "Supported file domains are docs, drive, sheets, base, wiki, slides, markdown, mindnotes, "
            "minutes, note, and whiteboard. Read the matching bundled Skill before every write. "
            "For Base records use `base +record-list`; use `base +record-search` for keyword search and "
            "`base +record-get` when record IDs are known. Resolve Base/Wiki URLs with `base +url-resolve`, "
            "then reuse the returned base_token/table_id. Never add a Dazah `subject` argument. "
            "Reads and small traceable additions may execute immediately; edits return confirmation data; "
            "deletes, moves, clears, overwrites and batch operations always require one-time confirmation. "
            "Sharing, membership, permissions, ownership, roles and human decisions are prohibited."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 64,
                    "description": (
                        "Exact lark-cli argv. Base record example: "
                        "['base','+record-list','--base-token','<token>','--table-id','<table_id>',"
                        "'--limit','50','--format','json','--as','bot']."
                    ),
                },
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
                "verification_args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 64,
                    "description": "Read-only lark-cli argv used after a write to verify the result.",
                },
                "verification_mode": {
                    "type": "string",
                    "enum": ["readback", "absence", "creation_receipt"],
                    "description": "Required for writes: readback, absence after delete, or structured creation receipt.",
                },
                "verification_text": {
                    "type": "string",
                    "maxLength": 500,
                    "description": (
                        "Bounded text used for readback assertions. Required for docs block_delete; "
                        "it must exist before execution and be absent afterward."
                    ),
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
