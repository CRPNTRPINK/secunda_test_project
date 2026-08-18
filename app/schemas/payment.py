import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.models.enums import Currency, PaymentStatus

MAX_AMOUNT = Decimal("9999999999999999.99")


class PaymentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    amount: Decimal = Field(gt=0, le=MAX_AMOUNT)
    currency: Currency
    description: str | None = Field(default=None, max_length=1024)
    metadata: dict[str, Any] = Field(default_factory=dict)
    webhook_url: HttpUrl | None = None

    @field_validator("amount")
    @classmethod
    def check_precision(cls, amount: Decimal) -> Decimal:
        if amount.as_tuple().exponent < -2:
            raise ValueError("amount must have at most 2 decimal places")
        return amount.quantize(Decimal("0.01"))


class PaymentAccepted(BaseModel):
    """Ответ на создание платежа: 202 и минимум данных, остальное - в GET."""

    payment_id: uuid.UUID
    status: PaymentStatus
    created_at: datetime


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    amount: Decimal
    currency: Currency
    description: str | None
    metadata: dict[str, Any] = Field(validation_alias="meta")
    status: PaymentStatus
    idempotency_key: str
    webhook_url: str | None
    webhook_attempts: int
    webhook_delivered_at: datetime | None
    failure_reason: str | None
    created_at: datetime
    processed_at: datetime | None


class ErrorResponse(BaseModel):
    detail: str
