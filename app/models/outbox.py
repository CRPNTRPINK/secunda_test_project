import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import OutboxStatus, enum_values


class OutboxMessage(Base):
    """Событие, записанное в одной транзакции с платежом и ждущее публикации."""

    __tablename__ = "outbox"
    __table_args__ = (
        Index("ix_outbox_dispatch", "status", "available_at"),
        Index("ix_outbox_aggregate_id", "aggregate_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(String(64))
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    event_type: Mapped[str] = mapped_column(String(128))
    routing_key: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)

    status: Mapped[OutboxStatus] = mapped_column(
        Enum(OutboxStatus, name="outbox_status", values_callable=enum_values),
        default=OutboxStatus.PENDING,
        server_default=OutboxStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(server_default=text("0"))
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<OutboxMessage {self.id} {self.event_type} {self.status}>"
