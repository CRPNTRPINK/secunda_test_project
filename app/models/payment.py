import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Enum, Index, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import Currency, PaymentStatus, enum_values


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_payments_status_created_at", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64))

    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[Currency] = mapped_column(
        Enum(Currency, name="currency", values_callable=enum_values)
    )
    description: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )

    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", values_callable=enum_values),
        default=PaymentStatus.PENDING,
        server_default=PaymentStatus.PENDING.value,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text)

    webhook_url: Mapped[str | None] = mapped_column(String(2048))
    webhook_attempts: Mapped[int] = mapped_column(server_default=text("0"))
    webhook_delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    webhook_last_error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<Payment {self.id} {self.amount} {self.currency} {self.status}>"
