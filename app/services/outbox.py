import uuid
from datetime import UTC, datetime

from app.models import OutboxMessage

PAYMENT_CREATED = "payment.created"


def payment_created_message(payment_id: uuid.UUID, routing_key: str) -> OutboxMessage:
    """Событие о новом платеже. id записи он же event_id сообщения."""
    event_id = uuid.uuid4()
    occurred_at = datetime.now(UTC)
    return OutboxMessage(
        id=event_id,
        aggregate_type="payment",
        aggregate_id=payment_id,
        event_type=PAYMENT_CREATED,
        routing_key=routing_key,
        payload={
            "event_id": str(event_id),
            "event_type": PAYMENT_CREATED,
            "payment_id": str(payment_id),
            "occurred_at": occurred_at.isoformat(),
        },
        available_at=occurred_at,
    )
