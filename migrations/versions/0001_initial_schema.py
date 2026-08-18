"""initial schema: payments and outbox

Revision ID: 0001
Revises:
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

currency_enum = postgresql.ENUM("RUB", "USD", "EUR", name="currency", create_type=False)
payment_status_enum = postgresql.ENUM(
    "pending", "succeeded", "failed", name="payment_status", create_type=False
)
outbox_status_enum = postgresql.ENUM(
    "pending", "published", "failed", name="outbox_status", create_type=False
)


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    bind = op.get_bind()
    currency_enum.create(bind, checkfirst=True)
    payment_status_enum.create(bind, checkfirst=True)
    outbox_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "payments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", currency_enum, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", payment_status_enum, server_default="pending", nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("webhook_url", sa.String(length=2048), nullable=True),
        sa.Column("webhook_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("webhook_delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("webhook_last_error", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("amount > 0", name="amount_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_payments"),
        sa.UniqueConstraint("idempotency_key", name="uq_payments_idempotency_key"),
    )
    op.create_index("ix_payments_status_created_at", "payments", ["status", "created_at"])

    op.create_table(
        "outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("routing_key", sa.String(length=128), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", outbox_status_enum, server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_outbox"),
    )
    op.create_index("ix_outbox_dispatch", "outbox", ["status", "available_at"])
    op.create_index("ix_outbox_aggregate_id", "outbox", ["aggregate_id"])


def downgrade() -> None:
    op.drop_index("ix_outbox_aggregate_id", table_name="outbox")
    op.drop_index("ix_outbox_dispatch", table_name="outbox")
    op.drop_table("outbox")
    op.drop_index("ix_payments_status_created_at", table_name="payments")
    op.drop_table("payments")

    bind = op.get_bind()
    outbox_status_enum.drop(bind, checkfirst=True)
    payment_status_enum.drop(bind, checkfirst=True)
    currency_enum.drop(bind, checkfirst=True)
