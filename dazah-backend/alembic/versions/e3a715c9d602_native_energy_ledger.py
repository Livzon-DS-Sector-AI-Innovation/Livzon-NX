"""Create native energy ledger without altering archived Wiki tables."""

from alembic import op

revision = "e3a715c9d602"
down_revision = "807ad84a1158"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE energy.meter_points (\n"
        "\tcode VARCHAR(80) NOT NULL, \n"
        "\tversion INTEGER NOT NULL, \n"
        "\tdefinition JSONB NOT NULL, \n"
        "\tcreated_by UUID, \n"
        "\tupdated_by UUID, \n"
        "\tid UUID NOT NULL, \n"
        "\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n"
        "\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n"
        "\tis_deleted BOOLEAN DEFAULT 'false' NOT NULL, \n"
        "\tPRIMARY KEY (id)\n"
        ")"
    )
    op.execute("CREATE UNIQUE INDEX uq_energy_meter_code ON energy.meter_points (code)")
    op.execute(
        "CREATE TABLE energy.calculation_rules (\n"
        "\tcode VARCHAR(80) NOT NULL, \n"
        "\tversion INTEGER NOT NULL, \n"
        "\tdefinition JSONB NOT NULL, \n"
        "\tcreated_by UUID, \n"
        "\tupdated_by UUID, \n"
        "\tid UUID NOT NULL, \n"
        "\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n"
        "\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n"
        "\tis_deleted BOOLEAN DEFAULT 'false' NOT NULL, \n"
        "\tPRIMARY KEY (id)\n"
        ")"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_energy_rule_code ON energy.calculation_rules (code)"
    )
    op.execute(
        "CREATE TABLE energy.entry_plans (\n"
        "\tversion INTEGER NOT NULL, \n"
        "\tdefinition JSONB NOT NULL, \n"
        "\tcreated_by UUID, \n"
        "\tupdated_by UUID, \n"
        "\tid UUID NOT NULL, \n"
        "\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n"
        "\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n"
        "\tis_deleted BOOLEAN DEFAULT 'false' NOT NULL, \n"
        "\tPRIMARY KEY (id)\n"
        ")"
    )
    op.execute(
        "CREATE TABLE energy.entry_tasks (\n"
        "\tplan_id UUID NOT NULL, \n"
        "\ttask_date DATE NOT NULL, \n"
        "\tdefinition JSONB NOT NULL, \n"
        "\tcreated_by UUID, \n"
        "\tupdated_by UUID, \n"
        "\tid UUID NOT NULL, \n"
        "\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n"
        "\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n"
        "\tis_deleted BOOLEAN DEFAULT 'false' NOT NULL, \n"
        "\tPRIMARY KEY (id)\n"
        ")"
    )
    op.execute(
        "CREATE INDEX ix_energy_entry_tasks_task_date ON energy.entry_tasks (task_date)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_energy_task_plan_day ON energy.entry_tasks "
        "(plan_id, task_date)"
    )
    op.execute(
        "CREATE TABLE energy.readings (\n"
        "\tpoint_id UUID NOT NULL, \n"
        "\ttask_id UUID NOT NULL, \n"
        "\treading_date DATE NOT NULL, \n"
        "\tvalue NUMERIC(28, 8), \n"
        "\tdraft_value NUMERIC(28, 8), \n"
        "\tversion INTEGER NOT NULL, \n"
        "\tsource VARCHAR(20) NOT NULL, \n"
        "\tsubmitted_at TIMESTAMP WITH TIME ZONE, \n"
        "\texception JSONB NOT NULL, \n"
        "\tcreated_by UUID, \n"
        "\tupdated_by UUID, \n"
        "\tid UUID NOT NULL, \n"
        "\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n"
        "\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n"
        "\tis_deleted BOOLEAN DEFAULT 'false' NOT NULL, \n"
        "\tPRIMARY KEY (id)\n"
        ")"
    )
    op.execute(
        "CREATE INDEX ix_energy_readings_reading_date ON energy.readings (reading_date)"
    )
    op.execute("CREATE INDEX ix_energy_readings_task_id ON energy.readings (task_id)")
    op.execute(
        "CREATE UNIQUE INDEX uq_energy_reading_point_day ON energy.readings "
        "(point_id, reading_date)"
    )
    op.execute(
        "CREATE TABLE energy.usage_facts (\n"
        "\tmetric_key VARCHAR(100) NOT NULL, \n"
        "\tusage_date DATE NOT NULL, \n"
        "\tdefinition JSONB NOT NULL, \n"
        "\tcalculated_value NUMERIC(28, 8), \n"
        "\teffective_value NUMERIC(28, 8), \n"
        "\tstatus VARCHAR(32) NOT NULL, \n"
        "\tprovenance JSONB NOT NULL, \n"
        "\tcreated_by UUID, \n"
        "\tupdated_by UUID, \n"
        "\tid UUID NOT NULL, \n"
        "\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n"
        "\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n"
        "\tis_deleted BOOLEAN DEFAULT 'false' NOT NULL, \n"
        "\tPRIMARY KEY (id)\n"
        ")"
    )
    op.execute(
        "CREATE INDEX ix_energy_usage_facts_usage_date ON energy.usage_facts "
        "(usage_date)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_energy_usage_key_day ON energy.usage_facts "
        "(metric_key, usage_date)"
    )
    op.execute(
        "CREATE TABLE energy.usage_adjustments (\n"
        "\tmetric_key VARCHAR(100) NOT NULL, \n"
        "\tusage_date DATE NOT NULL, \n"
        "\tmode VARCHAR(16) NOT NULL, \n"
        "\tvalue NUMERIC(28, 8) NOT NULL, \n"
        "\treason TEXT NOT NULL, \n"
        "\tcreated_by UUID, \n"
        "\tupdated_by UUID, \n"
        "\tid UUID NOT NULL, \n"
        "\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n"
        "\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n"
        "\tis_deleted BOOLEAN DEFAULT 'false' NOT NULL, \n"
        "\tPRIMARY KEY (id)\n"
        ")"
    )
    op.execute(
        "CREATE INDEX ix_energy_usage_adjustments_metric_key ON "
        "energy.usage_adjustments (metric_key)"
    )
    op.execute(
        "CREATE INDEX ix_energy_usage_adjustments_usage_date ON "
        "energy.usage_adjustments (usage_date)"
    )
    op.execute(
        "CREATE TABLE energy.ledger_revisions (\n"
        "\tentity_kind VARCHAR(32) NOT NULL, \n"
        "\tentity_id UUID NOT NULL, \n"
        "\tversion INTEGER NOT NULL, \n"
        "\tpayload JSONB NOT NULL, \n"
        "\treason TEXT NOT NULL, \n"
        "\tcreated_by UUID, \n"
        "\tupdated_by UUID, \n"
        "\tid UUID NOT NULL, \n"
        "\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n"
        "\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n"
        "\tis_deleted BOOLEAN DEFAULT 'false' NOT NULL, \n"
        "\tPRIMARY KEY (id)\n"
        ")"
    )
    op.execute(
        "CREATE INDEX ix_energy_ledger_revisions_entity_id ON "
        "energy.ledger_revisions (entity_id)"
    )
    op.execute(
        "CREATE INDEX ix_energy_ledger_revisions_entity_kind ON "
        "energy.ledger_revisions (entity_kind)"
    )
    op.execute(
        "CREATE TABLE energy.period_locks (\n"
        "\tmonth VARCHAR(7) NOT NULL, \n"
        "\tversion INTEGER NOT NULL, \n"
        "\tlocked BOOLEAN NOT NULL, \n"
        "\tsnapshot JSONB NOT NULL, \n"
        "\tcreated_by UUID, \n"
        "\tupdated_by UUID, \n"
        "\tid UUID NOT NULL, \n"
        "\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n"
        "\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n"
        "\tis_deleted BOOLEAN DEFAULT 'false' NOT NULL, \n"
        "\tPRIMARY KEY (id)\n"
        ")"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_energy_lock_month ON energy.period_locks (month)"
    )
    op.execute(
        "CREATE TABLE energy.import_batches (\n"
        "\tcontent_hash VARCHAR(64) NOT NULL, \n"
        "\tstatus VARCHAR(20) NOT NULL, \n"
        "\tpayload JSONB NOT NULL, \n"
        "\tcreated_by UUID, \n"
        "\tupdated_by UUID, \n"
        "\tid UUID NOT NULL, \n"
        "\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n"
        "\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n"
        "\tis_deleted BOOLEAN DEFAULT 'false' NOT NULL, \n"
        "\tPRIMARY KEY (id)\n"
        ")"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_energy_import_hash ON energy.import_batches "
        "(content_hash)"
    )
    op.execute(
        "CREATE TABLE energy.bot_configs (\n"
        "\tname VARCHAR(40) NOT NULL, \n"
        "\tdefinition JSONB NOT NULL, \n"
        "\tencrypted_secret TEXT, \n"
        "\tcreated_by UUID, \n"
        "\tupdated_by UUID, \n"
        "\tid UUID NOT NULL, \n"
        "\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n"
        "\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n"
        "\tis_deleted BOOLEAN DEFAULT 'false' NOT NULL, \n"
        "\tPRIMARY KEY (id)\n"
        ")"
    )
    op.execute("CREATE UNIQUE INDEX uq_energy_bot_name ON energy.bot_configs (name)")
    op.execute(
        "CREATE TABLE energy.notification_runs (\n"
        "\ttask_id UUID NOT NULL, \n"
        "\tdelivery_key VARCHAR(200) NOT NULL, \n"
        "\tstatus VARCHAR(20) NOT NULL, \n"
        "\tattempts INTEGER NOT NULL, \n"
        "\tdefinition JSONB NOT NULL, \n"
        "\tmessage_id VARCHAR(128), \n"
        "\terror TEXT, \n"
        "\tnext_attempt_at TIMESTAMP WITH TIME ZONE, \n"
        "\tcreated_by UUID, \n"
        "\tupdated_by UUID, \n"
        "\tid UUID NOT NULL, \n"
        "\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n"
        "\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n"
        "\tis_deleted BOOLEAN DEFAULT 'false' NOT NULL, \n"
        "\tPRIMARY KEY (id)\n"
        ")"
    )
    op.execute(
        "CREATE INDEX ix_energy_notification_runs_task_id ON "
        "energy.notification_runs (task_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_energy_notification_key ON "
        "energy.notification_runs (delivery_key)"
    )


def downgrade() -> None:
    op.drop_table("notification_runs", schema="energy")
    op.drop_table("bot_configs", schema="energy")
    op.drop_table("import_batches", schema="energy")
    op.drop_table("period_locks", schema="energy")
    op.drop_table("ledger_revisions", schema="energy")
    op.drop_table("usage_adjustments", schema="energy")
    op.drop_table("usage_facts", schema="energy")
    op.drop_table("readings", schema="energy")
    op.drop_table("entry_tasks", schema="energy")
    op.drop_table("entry_plans", schema="energy")
    op.drop_table("calculation_rules", schema="energy")
    op.drop_table("meter_points", schema="energy")
