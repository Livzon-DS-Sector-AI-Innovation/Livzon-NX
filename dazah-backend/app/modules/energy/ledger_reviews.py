"""Audited, date-bounded review overlays; original readings remain immutable."""

import hashlib
from datetime import date
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid5

from pydantic import JsonValue
from sqlalchemy import select

from app.core.exceptions import AppException
from app.modules.energy.ledger_models import EnergyLedgerRevision
from app.modules.energy.ledger_schemas import (
    MeterDefinition,
    RuleDefinition,
    UsageReview,
    UsageReviewPeriod,
    UsageRow,
)

if TYPE_CHECKING:
    from app.modules.energy.ledger_service import EnergyLedgerService

REVIEW_KIND = "usage_review"

# Backwards-compatible name for callers that imported the period model here.
ReviewPeriod = UsageReviewPeriod


def matches_review(
    key: str, definition: MeterDefinition | RuleDefinition, review: UsageReview
) -> bool:
    if definition.source_sheet:
        return (
            definition.source_sheet == review.dataset
            and definition.source_column == review.column
        )
    # Compatibility with existing extracted configurations without source metadata.
    suffix = (
        "xlsx_"
        + hashlib.sha256(review.dataset.encode()).hexdigest()[:10]
        + "_"
        + str(review.column)
    )
    return key.split(":", 1)[-1] == suffix or key.endswith("_" + suffix)


def pending_metrics(
    day: date,
    definitions: dict[str, MeterDefinition | RuleDefinition],
    reviews: list[UsageReview],
) -> dict[str, list[dict[str, JsonValue]]]:
    pending: dict[str, list[dict[str, JsonValue]]] = {}
    for key, definition in definitions.items():
        evidence = [
            item
            for review in reviews
            if matches_review(key, definition, review)
            for item in review.evidence_on(day)
        ]
        if evidence:
            pending[key] = evidence
    # Fixed point handles arbitrary configuration ordering and shared dependencies.
    for _ in range(len(definitions)):
        changed = False
        for key, definition in definitions.items():
            if not isinstance(definition, RuleDefinition):
                continue
            evidence = list(pending.get(key, []))
            for term in definition.terms:
                for item in pending.get(term.metric_key, []):
                    if item not in evidence:
                        evidence.append(item)
            if evidence and evidence != pending.get(key):
                pending[key] = evidence
                changed = True
        if not changed:
            break
    return pending


def apply_usage_review(row: UsageRow, evidence: list[dict[str, JsonValue]]) -> UsageRow:
    if not evidence:
        return row
    return row.model_copy(
        update={
            "effective_value": None,
            "status": "pending_review",
            "provenance": review_provenance(row.provenance, evidence),
        }
    )


def review_provenance(
    provenance: dict[str, JsonValue], evidence: list[dict[str, JsonValue]]
) -> dict[str, JsonValue]:
    items: list[JsonValue] = list(evidence)
    return {**provenance, "review": items}


async def load_usage_review_records(
    service: "EnergyLedgerService",
) -> list[EnergyLedgerRevision]:
    """Return the latest review revision for each source field."""
    records = (
        await service.db.scalars(
            select(EnergyLedgerRevision)
            .where(
                EnergyLedgerRevision.entity_kind == REVIEW_KIND,
                EnergyLedgerRevision.is_deleted.is_(False),
            )
            .order_by(
                EnergyLedgerRevision.created_at.desc(),
                EnergyLedgerRevision.version.desc(),
            )
        )
    ).all()
    latest: dict[str, EnergyLedgerRevision] = {}
    for record in records:
        latest.setdefault(str(record.entity_id), record)
    return list(latest.values())


async def load_usage_reviews(service: "EnergyLedgerService") -> list[UsageReview]:
    return [
        UsageReview.model_validate(record.payload)
        for record in await load_usage_review_records(service)
    ]


async def save_usage_reviews(
    service: "EnergyLedgerService", reviews: list[UsageReview], reason: str
) -> None:
    """Maintenance entry point: append audit metadata, never edit readings/imports."""
    await service.require_manager()
    await service.repo.serialize_write()
    from app.modules.energy.ledger_workbook import DATASETS

    allowed = {dataset.name for dataset in DATASETS if dataset.kind != "reading"}
    if any(review.dataset not in allowed for review in reviews):
        raise AppException(422, "只允许标记用量字段，原始表码保持不变")
    existing = await load_usage_reviews(service)
    if len({(review.dataset, review.column) for review in reviews}) != len(reviews):
        raise AppException(422, "同一字段不能重复核对")
    for review in reviews:
        if review in existing:
            continue
        identity = uuid5(
            NAMESPACE_URL, f"energy:usage-review:{review.dataset}:{review.column}"
        )
        previous = await service.db.scalar(
            select(EnergyLedgerRevision)
            .where(
                EnergyLedgerRevision.entity_kind == REVIEW_KIND,
                EnergyLedgerRevision.entity_id == identity,
            )
            .order_by(EnergyLedgerRevision.version.desc())
            .limit(1)
        )
        service.db.add(
            EnergyLedgerRevision(
                entity_kind=REVIEW_KIND,
                entity_id=identity,
                version=previous.version + 1 if previous else 1,
                payload=review.model_dump(mode="json"),
                reason=reason,
                created_by=service.actor_id,
                updated_by=service.actor_id,
            )
        )
    await service.db.flush()
    service._usage_reviews = None
