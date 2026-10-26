"""Native energy ledger, deliberately separate from archived Wiki snapshots."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import Date, DateTime, Index, Integer, Numeric, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class LedgerBase(BaseModel):
    __abstract__ = True
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    updated_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


class EnergyMeterPoint(LedgerBase):
    __tablename__ = "meter_points"
    __table_args__ = (
        Index("uq_energy_meter_code", "code", unique=True),
        {"schema": "energy"},
    )
    code: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer, default=1)
    definition: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)


class EnergyCalculationRule(LedgerBase):
    __tablename__ = "calculation_rules"
    __table_args__ = (
        Index("uq_energy_rule_code", "code", unique=True),
        {"schema": "energy"},
    )
    code: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer, default=1)
    definition: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)


class EnergyReading(LedgerBase):
    __tablename__ = "readings"
    __table_args__ = (
        Index("uq_energy_reading_point_day", "point_id", "reading_date", unique=True),
        {"schema": "energy"},
    )
    point_id: Mapped[UUID] = mapped_column(Uuid)
    task_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    reading_date: Mapped[date] = mapped_column(Date, index=True)
    value: Mapped[Decimal | None] = mapped_column(Numeric(28, 8), nullable=True)
    draft_value: Mapped[Decimal | None] = mapped_column(Numeric(28, 8), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(20), default="platform")
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    exception: Mapped[dict[str, JsonValue]] = mapped_column(JSONB, default=dict)


class EnergyUsageFact(LedgerBase):
    __tablename__ = "usage_facts"
    __table_args__ = (
        Index("uq_energy_usage_key_day", "metric_key", "usage_date", unique=True),
        {"schema": "energy"},
    )
    metric_key: Mapped[str] = mapped_column(String(100))
    usage_date: Mapped[date] = mapped_column(Date, index=True)
    definition: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    calculated_value: Mapped[Decimal | None] = mapped_column(
        Numeric(28, 8), nullable=True
    )
    effective_value: Mapped[Decimal | None] = mapped_column(
        Numeric(28, 8), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32))
    provenance: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)


class EnergyLedgerRevision(LedgerBase):
    __tablename__ = "ledger_revisions"
    __table_args__ = ({"schema": "energy"},)
    entity_kind: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(Text, default="")


class EnergyImportBatch(LedgerBase):
    __tablename__ = "import_batches"
    __table_args__ = (
        Index("uq_energy_import_hash", "content_hash", unique=True),
        {"schema": "energy"},
    )
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="preview")
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)


class EnergyBotConfig(LedgerBase):
    __tablename__ = "bot_configs"
    __table_args__ = (
        Index("uq_energy_bot_name", "name", unique=True),
        {"schema": "energy"},
    )
    name: Mapped[str] = mapped_column(String(40), default="default")
    definition: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    encrypted_secret: Mapped[str | None] = mapped_column(Text, nullable=True)


class EnergyNotificationRun(LedgerBase):
    __tablename__ = "notification_runs"
    __table_args__ = (
        Index("uq_energy_notification_key", "delivery_key", unique=True),
        {"schema": "energy"},
    )
    task_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    delivery_key: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    definition: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


LEDGER_TABLES = tuple(
    model.__table__
    for model in (
        EnergyMeterPoint,
        EnergyCalculationRule,
        EnergyReading,
        EnergyUsageFact,
        EnergyLedgerRevision,
        EnergyImportBatch,
        EnergyBotConfig,
        EnergyNotificationRun,
    )
)
