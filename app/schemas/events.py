import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import Currency, PaymentStatus


class PaymentCreatedEvent(BaseModel):
    """Сообщение очереди payments.new."""

    model_config = ConfigDict(extra="ignore")

    event_id: uuid.UUID
    event_type: str = "payment.created"
    payment_id: uuid.UUID
    occurred_at: datetime


class WebhookPayload(BaseModel):
    """Тело уведомления, которое уходит клиенту на webhook_url."""

    event: str
    payment_id: uuid.UUID
    status: PaymentStatus
    amount: Decimal
    currency: Currency
    description: str | None
    metadata: dict[str, Any]
    failure_reason: str | None
    created_at: datetime
    processed_at: datetime | None
