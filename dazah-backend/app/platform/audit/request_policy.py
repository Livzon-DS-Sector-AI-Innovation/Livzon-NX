"""Select request-level audit evidence without suppressing explicit business events.

Unclassified writes retain the audit fallback. Only reviewed, exact POST route
templates can be excluded as reads; names such as ``preview`` are not sufficient
because those endpoints may persist uploads or trigger work. Security outcomes
always take precedence over exclusions. Modules can set the server-owned
``request.state.audit_required`` for sensitive reads with nonstandard routes.
"""

from typing import Literal

AuditReason = Literal[
    "write", "security", "authentication", "sensitive_read", "business_callback"
]

READ_ONLY_POST_ROUTES = frozenset(
    {
        "/api/v1/warehouse/analytics/query",
        "/api/v1/identity/admin/permission-simulate",
        "/api/v1/identity/admin/page-permissions/simulate",
    }
)
_AUTH_EVENT_ROUTES = frozenset(
    {
        "/api/v1/identity/auth/local/login",
        "/api/v1/identity/auth/callback",
        "/api/v1/identity/auth/session/logout",
    }
)
# These existing GET endpoints have business effects, despite their HTTP method.
_EFFECTFUL_GET_ROUTES = frozenset(
    {
        "/api/v1/hr/candidates/sync-from-feishu",
        "/api/v1/hr/plan-tracking/period",
        "/api/v1/hr/hr-settings/reminders",
        "/api/v1/hr/hr-settings/push-templates",
        "/api/v1/hr/hr-settings/push-recipients",
        "/api/v1/hr/hr-settings/hr-members",
        "/api/v1/production/mc/lineage/ai-analysis",
        "/api/v1/production/mc/lineage/ai-analysis-stream",
        "/api/v1/production/fa/lineage/ai-analysis",
        "/api/v1/production/fa/lineage/ai-analysis-stream",
        "/api/v1/production/fa/dashboard/batch-params",
    }
)
_BUSINESS_CALLBACK_ROUTES = frozenset({"/api/v1/hr/contracts/approval-callback"})
_SENSITIVE_READ_ROUTES = frozenset(
    {
        "/api/v1/audit/logs/{log_id}",
        "/api/v1/identity/users/{user_id}/module-permissions",
        "/api/v1/identity/users/{user_id}/livzon-access-scope",
        "/api/v1/identity/users/{user_id}/permission-audit",
    }
)


def request_audit_reason(
    method: str,
    route_path: str,
    status_code: int,
    *,
    content_disposition: str | None = None,
    required: bool = False,
) -> AuditReason | None:
    """Classify a matched API route using server-verified request information."""
    if method == "OPTIONS":
        return None
    if status_code in {401, 403, 429}:
        return "security"
    if route_path in _AUTH_EVENT_ROUTES:
        return "authentication"
    if route_path in _BUSINESS_CALLBACK_ROUTES:
        return "business_callback"
    if required:
        return "sensitive_read" if method in {"GET", "HEAD"} else "write"
    if method not in {"GET", "HEAD"}:
        if method == "POST" and route_path in READ_ONLY_POST_ROUTES:
            return None
        return "write"
    if route_path in _EFFECTFUL_GET_ROUTES:
        return "write"
    if route_path in _SENSITIVE_READ_ROUTES:
        return "sensitive_read"

    segments = route_path.split("/")
    last = segments[-1]
    # Match route templates, never user-supplied resource IDs or query values.
    if any(
        segment == verb or segment.startswith(f"{verb}-")
        for segment in segments
        for verb in ("export", "download", "print")
    ):
        return "sensitive_read"
    if last in {"file", "docx-file", "resume-file", "document", "msds"}:
        return "sensitive_read"
    if "attachments" in segments and last in {"content", "preview", "{file_token}"}:
        return "sensitive_read"
    # Catch protected file responses even when the route name is unconventional.
    if content_disposition and content_disposition.split(";", 1)[0].strip().lower() in {
        "attachment", "inline"
    }:
        # Thumbnail polling is an ordinary list-rendering request.
        if last != "thumbnail":
            return "sensitive_read"
    return None
