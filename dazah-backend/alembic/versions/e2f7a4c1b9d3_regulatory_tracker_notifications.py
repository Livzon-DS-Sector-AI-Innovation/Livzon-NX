"""regulatory_tracker notification tables and document filter columns

法规跟踪三阶段流水线（00:10 抓取 / 02:00 AI 分析 / 10:00 推送）所需的
通知能力：
- notification_settings / notification_records 两张推送配置与记录表
- regulatory_documents 补 capture_date / filter_status / filter_reason /
  content_hash（推送窗口与过滤状态）

Revision ID: e2f7a4c1b9d3
Revises: d9f5b3c7a1e2
Create Date: 2026-08-28 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2f7a4c1b9d3"
down_revision: str | None = "d9f5b3c7a1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS regulatory_tracker")
    # 文档表补列
    op.execute(
        """
        ALTER TABLE regulatory_tracker.regulatory_documents
            ADD COLUMN IF NOT EXISTS source_site_code varchar(100),
            ADD COLUMN IF NOT EXISTS source_site_name varchar(255),
            ADD COLUMN IF NOT EXISTS source_url varchar(1000),
            ADD COLUMN IF NOT EXISTS version_text varchar(200),
            ADD COLUMN IF NOT EXISTS effective_date date,
            ADD COLUMN IF NOT EXISTS summary_text text,
            ADD COLUMN IF NOT EXISTS capture_date date,
            ADD COLUMN IF NOT EXISTS content_hash varchar(128),
            ADD COLUMN IF NOT EXISTS filter_status varchar(50),
            ADD COLUMN IF NOT EXISTS filter_reason text
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_regulatory_documents_capture_date
        ON regulatory_tracker.regulatory_documents (capture_date)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_regulatory_documents_filter_status
        ON regulatory_tracker.regulatory_documents (filter_status)
        """
    )
    # 推送设置表
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS regulatory_tracker.notification_settings (
            id uuid PRIMARY KEY,
            is_enabled boolean NOT NULL DEFAULT false,
            recent_days integer NOT NULL DEFAULT 7,
            recipient_open_id varchar(255),
            recipient_name varchar(255),
            recipient_department varchar(255),
            schedule_time varchar(16) NOT NULL DEFAULT '10:00',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            created_by uuid,
            updated_by uuid,
            is_deleted boolean NOT NULL DEFAULT false
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS
        ix_regulatory_tracker_notification_settings_recipient_open_id
        ON regulatory_tracker.notification_settings (recipient_open_id)
        """
    )
    # 推送记录表
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS regulatory_tracker.notification_records (
            id uuid PRIMARY KEY,
            document_id uuid NOT NULL,
            recipient_open_id varchar(255) NOT NULL,
            recipient_name varchar(255),
            content_hash varchar(128) NOT NULL,
            document_title varchar(1000) NOT NULL,
            source_site_name varchar(255),
            publish_date date,
            source_url varchar(1000),
            summary_text text,
            trigger_type varchar(50) NOT NULL DEFAULT 'daily_auto_sync',
            notified_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            created_by uuid,
            updated_by uuid,
            is_deleted boolean NOT NULL DEFAULT false,
            CONSTRAINT uq_regulatory_tracker_notification_record
                UNIQUE (document_id, recipient_open_id, content_hash)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS
        ix_regulatory_tracker_notification_records_document_id
        ON regulatory_tracker.notification_records (document_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS
        ix_regulatory_tracker_notification_records_notified_at
        ON regulatory_tracker.notification_records (notified_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS regulatory_tracker.notification_records")
    op.execute("DROP TABLE IF EXISTS regulatory_tracker.notification_settings")
    op.execute(
        "DROP INDEX IF EXISTS ix_regulatory_documents_capture_date"
    )
    op.execute(
        "DROP INDEX IF EXISTS ix_regulatory_documents_filter_status"
    )
    op.execute(
        """
        ALTER TABLE regulatory_tracker.regulatory_documents
            DROP COLUMN IF EXISTS source_site_code,
            DROP COLUMN IF EXISTS source_site_name,
            DROP COLUMN IF EXISTS source_url,
            DROP COLUMN IF EXISTS version_text,
            DROP COLUMN IF EXISTS effective_date,
            DROP COLUMN IF EXISTS summary_text,
            DROP COLUMN IF EXISTS capture_date,
            DROP COLUMN IF EXISTS content_hash,
            DROP COLUMN IF EXISTS filter_status,
            DROP COLUMN IF EXISTS filter_reason
        """
    )
