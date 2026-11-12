"""Reviewed safety routes that use the dashboard page authorization boundary."""

from collections.abc import Iterator

_ACCIDENT = "safety:emergency-accident:accident-ledger"
_CHECK = "safety:training-check:safety-check"
_HAZARD = "safety:risk-hazard:hazard-inspection:hazard-inspection-ledger"
_CONTRACTOR = "safety:training-check:contractor"
_TRAINING = "safety:training-check:safety-training"
_RISK_REPORT = "safety:ops-safety:daily-risk-report"
_SPECIAL_OPS = "safety:ops-safety:special-ops-mgmt"
_WORKFLOW = "safety:risk-hazard:risk-grading:hazard-identification"
_LEDGER = "safety:risk-hazard:risk-grading:hazard-ledger"
_AI_CONFIG = "safety:system-config:ai-workflow"
_SCHEDULED = "safety:system-config:scheduled-tasks"
_KNOWLEDGE = "safety:regulation-info:knowledge-base"
_FEISHU = "safety:system-config:safety-feishu-settings"
_MSDS = "safety:site-mgmt:hazchem-msds"

SafetyRouteRule = tuple[str, str, tuple[str, ...], str, str | None, str]


def _routes(
    pages: tuple[str, ...],
    grant: str,
    endpoints: tuple[str, ...],
    *,
    department_scoped: bool = False,
) -> Iterator[SafetyRouteRule]:
    permission = "query" if grant == "query" else "operate"
    action = None if grant in {"query", "operate"} else grant
    adapter = "safety.department" if department_scoped else "not_applicable"
    for endpoint in endpoints:
        method, path = endpoint.split(" ", 1)
        yield method, path, pages, permission, action, adapter


def safety_route_rules() -> Iterator[SafetyRouteRule]:
    yield from _routes(
        (_ACCIDENT,),
        "query",
        (
            "GET /accidents",
            "GET /accidents/{accident_id}",
        ),
        department_scoped=True,
    )
    yield from _routes(
        (_ACCIDENT,),
        "operate",
        (
            "POST /accidents",
            "PUT /accidents/{accident_id}",
            "POST /accidents/{accident_id}/investigate",
            "POST /accidents/{accident_id}/resolve",
            "POST /accidents/{accident_id}/start-capa",
        ),
        department_scoped=True,
    )
    yield from _routes(
        (_ACCIDENT,),
        "delete",
        ("DELETE /accidents/{accident_id}",),
        department_scoped=True,
    )
    yield from _routes(
        (_ACCIDENT,),
        "approve",
        (
            "POST /accidents/{accident_id}/verify-capa",
            "POST /accidents/{accident_id}/close",
        ),
        department_scoped=True,
    )

    yield from _routes(
        (_CHECK,),
        "query",
        (
            "GET /checks",
            "GET /checks/{check_id}",
        ),
        department_scoped=True,
    )
    yield from _routes(
        (_CHECK,),
        "operate",
        (
            "POST /checks",
            "PUT /checks/{check_id}",
            "POST /checks/{check_id}/submit",
        ),
        department_scoped=True,
    )
    yield from _routes(
        (_CHECK,), "delete", ("DELETE /checks/{check_id}",), department_scoped=True
    )
    yield from _routes(
        (_CHECK,),
        "approve",
        ("POST /checks/{check_id}/confirm",),
        department_scoped=True,
    )

    yield from _routes(
        (_HAZARD,),
        "query",
        (
            "GET /hazards",
            "GET /hazards/{hazard_id}",
            "GET /hazards/stats",
            "GET /hazards/department-leader",
        ),
        department_scoped=True,
    )
    yield from _routes(
        (_HAZARD,),
        "operate",
        (
            "POST /hazards",
            "PUT /hazards/{hazard_id}",
            "POST /hazards/{hazard_id}/ai/run/{script_number}",
            "POST /hazards/{hazard_id}/rectification/reply",
            "POST /hazards/{hazard_id}/rectification/rework",
            "POST /hazards/{hazard_id}/rectification/start",
            "POST /hazards/{hazard_id}/upload-photo",
            "POST /hazards/{hazard_id}/upload-rectification-photo",
        ),
        department_scoped=True,
    )
    yield from _routes(
        (_HAZARD,), "delete", ("DELETE /hazards/{hazard_id}",), department_scoped=True
    )

    yield from _routes(
        (_CONTRACTOR,),
        "query",
        (
            "GET /contractors",
            "GET /contractors/{contractor_id}",
            "GET /contractors/{contractor_id}/work-records",
        ),
    )
    yield from _routes(
        (_CONTRACTOR,),
        "operate",
        (
            "POST /contractors",
            "PUT /contractors/{contractor_id}",
            "POST /contractors/{contractor_id}/update-training",
            "POST /contractors/{contractor_id}/work-records",
            "PUT /contractors/{contractor_id}/work-records/{record_id}",
            "POST /contractors/{contractor_id}/work-records/{record_id}/evaluate",
        ),
    )
    yield from _routes(
        (_CONTRACTOR,),
        "delete",
        (
            "DELETE /contractors/{contractor_id}",
            "DELETE /contractors/{contractor_id}/work-records/{record_id}",
        ),
    )
    yield from _routes(
        (_CONTRACTOR,), "approve", ("POST /contractors/{contractor_id}/activate",)
    )
    yield from _routes(
        (_CONTRACTOR,), "reject", ("POST /contractors/{contractor_id}/blacklist",)
    )

    yield from _routes(
        (_TRAINING,),
        "query",
        (
            "GET /trainings",
            "GET /trainings/{training_id}",
            "GET /trainings/{training_id}/records",
            "GET /training-certificates",
            "GET /training-certificates/expiring",
        ),
    )
    yield from _routes(
        (_TRAINING,),
        "operate",
        (
            "POST /trainings",
            "PUT /trainings/{training_id}",
            "POST /trainings/{training_id}/start",
            "POST /trainings/{training_id}/complete",
            "POST /trainings/{training_id}/records",
            "PUT /training-records/{record_id}",
        ),
    )
    yield from _routes(
        (_TRAINING,),
        "delete",
        (
            "DELETE /trainings/{training_id}",
            "DELETE /training-records/{record_id}",
        ),
    )

    yield from _routes(
        (_RISK_REPORT,), "query", ("GET /daily-risk-reports/{report_id}",)
    )
    yield from _routes(
        (_RISK_REPORT,),
        "operate",
        (
            "POST /daily-risk-reports",
            "PUT /daily-risk-reports/{report_id}",
            "POST /daily-risk-reports/{report_id}/submit",
        ),
    )
    yield from _routes(
        (_RISK_REPORT,), "approve", ("POST /daily-risk-reports/{report_id}/approve",)
    )
    yield from _routes(
        (_RISK_REPORT,), "reject", ("POST /daily-risk-reports/{report_id}/reject",)
    )
    yield from _routes(
        (_RISK_REPORT,), "delete", ("DELETE /daily-risk-reports/{report_id}",)
    )

    yield from _routes(
        (_SPECIAL_OPS,),
        "query",
        (
            "GET /special-operation-ledger",
            "GET /special-operation-ledger/stats",
            "GET /special-operation-permits",
            "GET /special-operation-permits/{permit_id}",
            "GET /special-operation-personnel",
            "GET /special-operation-personnel/{personnel_id}",
            "GET /special-operation-reports",
            "GET /special-operation-reports/{report_id}",
        ),
    )
    yield from _routes(
        (_SPECIAL_OPS,),
        "operate",
        (
            "POST /special-operation-ledger/parse-query",
            "POST /special-operation-permits",
            "PUT /special-operation-permits/{permit_id}",
            "POST /special-operation-permits/{permit_id}/archive",
            "POST /special-operation-permits/{permit_id}/complete",
            "POST /special-operation-permits/{permit_id}/start",
            "POST /special-operation-permits/{permit_id}/submit",
            "POST /special-operation-personnel",
            "PUT /special-operation-personnel/{personnel_id}",
            "POST /special-operation-reports",
            "PUT /special-operation-reports/{report_id}",
            "POST /special-operation-reports/{report_id}/submit",
        ),
    )
    yield from _routes(
        (_SPECIAL_OPS,),
        "delete",
        (
            "DELETE /special-operation-permits/{permit_id}",
            "DELETE /special-operation-personnel/{personnel_id}",
            "DELETE /special-operation-reports/{report_id}",
        ),
    )
    yield from _routes(
        (_SPECIAL_OPS,),
        "approve",
        (
            "POST /special-operation-permits/{permit_id}/approve",
            "POST /special-operation-reports/{report_id}/approve",
        ),
    )
    yield from _routes(
        (_SPECIAL_OPS,),
        "reject",
        (
            "POST /special-operation-permits/{permit_id}/reject",
            "POST /special-operation-reports/{report_id}/reject",
        ),
    )
    yield from _routes(
        (_SPECIAL_OPS,), "sensitive_export", ("POST /special-operation-ledger/export",)
    )

    yield from _routes((_WORKFLOW,), "query", ("GET /hazard-identifications/stats",))
    yield from _routes(
        (_WORKFLOW,),
        "operate",
        (
            "POST /hazard-identifications",
            "POST /hazard-identifications/{hid}/run-script",
            "POST /hazard-identifications/{hid}/submit",
            "POST /hazard-identifications/{hid}/upload",
        ),
    )
    yield from _routes(
        (_WORKFLOW,), "delete", ("DELETE /hazard-identifications/{hid}",)
    )

    yield from _routes(
        (_LEDGER,),
        "query",
        (
            "GET /hazard-identifications/filter-options",
            "GET /hazard-identifications/ledger-stats",
        ),
    )
    yield from _routes(
        (_LEDGER,), "operate", ("POST /hazard-identifications/parse-query",)
    )
    yield from _routes(
        (_LEDGER,),
        "bulk_import",
        (
            "POST /hazard-identifications/import",
            "POST /hazard-identifications/import/parse",
        ),
    )
    yield from _routes(
        (_LEDGER,), "sensitive_export", ("POST /hazard-identifications/export-pdf",)
    )

    yield from _routes(
        (_AI_CONFIG,),
        "query",
        (
            "GET /ai-workflow-configs",
            "GET /ai-workflow-configs/{config_id}",
            "GET /ai-workflow-configs/attachments/{attachment_id}/preview",
        ),
    )
    yield from _routes(
        (_AI_CONFIG,),
        "sync_config",
        (
            "POST /ai-workflow-configs",
            "PUT /ai-workflow-configs/{config_id}",
            "POST /ai-workflow-configs/attachments/from-knowledge",
            "POST /ai-workflow-configs/attachments/upload",
        ),
    )
    yield from _routes(
        (_AI_CONFIG,),
        "delete",
        (
            "DELETE /ai-workflow-configs/{config_id}",
            "DELETE /ai-workflow-configs/attachments/{attachment_id}",
        ),
    )

    yield from _routes(
        (_SCHEDULED,),
        "query",
        (
            "GET /scheduled-tasks",
            "GET /scheduled-tasks/data-source-options",
            "GET /scheduled-tasks/feishu-chats",
            "GET /scheduled-tasks/{task_id}",
            "GET /scheduled-tasks/{task_id}/logs",
        ),
    )
    yield from _routes(
        (_SCHEDULED,), "operate", ("POST /scheduled-tasks/preview-card",)
    )
    yield from _routes(
        (_SCHEDULED,),
        "sync_config",
        (
            "POST /scheduled-tasks",
            "PUT /scheduled-tasks/{task_id}",
            "POST /scheduled-tasks/{task_id}/run",
            "POST /scheduled-tasks/{task_id}/toggle",
        ),
    )
    yield from _routes((_SCHEDULED,), "delete", ("DELETE /scheduled-tasks/{task_id}",))

    yield from _routes(
        (_KNOWLEDGE,),
        "query",
        (
            "GET /knowledge-articles/{article_id}",
            "GET /knowledge-articles/feishu/records/{record_id}"
            "/attachments/{file_token}/content",
            "GET /knowledge-articles/feishu/records/{record_id}"
            "/attachments/{file_token}/preview",
            "GET /knowledge-articles/{article_id}/attachments/{token}/content",
            "GET /knowledge-articles/{article_id}/attachments/{token}/preview",
        ),
    )
    yield from _routes(
        (_KNOWLEDGE,),
        "operate",
        (
            "POST /knowledge-articles",
            "PUT /knowledge-articles/{article_id}",
        ),
    )
    yield from _routes(
        (_KNOWLEDGE,), "delete", ("DELETE /knowledge-articles/{article_id}",)
    )

    yield from _routes((_FEISHU,), "query", ("GET /feishu/ws/status",))
    yield from _routes(
        (_FEISHU,),
        "sync_config",
        (
            "POST /feishu/ws/restart",
            "POST /feishu-settings/commitment-notify/test",
        ),
    )

    yield from _routes(
        (_MSDS,),
        "query",
        (
            "GET /hazardous-chemicals/{chemical_id}/msds-files",
            "GET /hazardous-chemicals/{chemical_id}/msds-files/{file_id}/content",
            "GET /hazardous-chemicals/{chemical_id}/msds-files/{file_id}/preview",
        ),
    )
    yield from _routes(
        (_MSDS,),
        "operate",
        (
            "POST /hazardous-chemicals/{chemical_id}/msds-files",
            "POST /hazardous-chemicals/{chemical_id}/msds-files/{file_id}/extract",
        ),
    )
    yield from _routes(
        (_MSDS,),
        "delete",
        ("DELETE /hazardous-chemicals/{chemical_id}/msds-files/{file_id}",),
    )

    # Shared reads serve the dashboard, ledger detail and workflow pickers.
    yield from _routes((_RISK_REPORT,), "query", ("GET /daily-risk-reports",))
    yield from _routes(
        (_WORKFLOW, _LEDGER),
        "query",
        (
            "GET /hazard-identifications",
            "GET /hazard-identifications/{hid}",
        ),
    )
    yield from _routes(
        (_WORKFLOW, _LEDGER), "operate", ("PUT /hazard-identifications/{hid}",)
    )
    yield from _routes(
        (_RISK_REPORT,), "query", ("GET /hazard-identifications/risk-options",)
    )
    yield from _routes((_KNOWLEDGE, _AI_CONFIG), "query", ("GET /knowledge-articles",))
    yield from _routes(("safety:overview",), "query", ("GET /enums",))


# Mixed approval/rejection endpoints require the action matching the request.
# The final field is the query parameter for check review and the JSON field otherwise.
SAFETY_DECISION_ROUTES = (
    (
        "/hazards/{hazard_id}/rectification/verify-level",
        _HAZARD,
        "safety.department",
        "action",
        (("approved", "approve"), ("rejected", "reject")),
        False,
    ),
    (
        "/hazard-identifications/{hid}/review",
        _WORKFLOW,
        "not_applicable",
        "action",
        (("approved", "approve"), ("rejected", "reject")),
        False,
    ),
    (
        "/checks/{check_id}/review",
        _CHECK,
        "safety.department",
        "result",
        (("qualified", "approve"), ("unqualified", "reject")),
        True,
    ),
)


# These mounted routes belong to the signed-link and relay protocols. They
# retain their own admission checks and are never usable as page API bindings.
SAFETY_SIGNATURE_ROUTES = frozenset(
    {
        ("GET", "/api/v1/safety/work-permit-sign/{token}"),
        ("POST", "/api/v1/safety/work-permit-sign"),
        ("GET", "/api/v1/safety/work-permit-file/{token}"),
        ("GET", "/api/v1/safety/sign-relay/{token}"),
        ("POST", "/api/v1/safety/sign-relay"),
        ("POST", "/api/v1/safety/sign-relay/pull"),
    }
)
