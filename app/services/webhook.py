import logging
from dataclasses import dataclass

import httpx

from app.models import Payment, PaymentStatus
from app.schemas.events import WebhookPayload

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class WebhookResult:
    delivered: bool
    status_code: int | None = None
    error: str | None = None


def build_payload(payment: Payment) -> WebhookPayload:
    event = "payment.succeeded" if payment.status is PaymentStatus.SUCCEEDED else "payment.failed"
    return WebhookPayload(
        event=event,
        payment_id=payment.id,
        status=payment.status,
        amount=payment.amount,
        currency=payment.currency,
        description=payment.description,
        metadata=payment.meta or {},
        failure_reason=payment.failure_reason,
        created_at=payment.created_at,
        processed_at=payment.processed_at,
    )


async def send(client: httpx.AsyncClient, payment: Payment) -> WebhookResult:
    """Одна попытка доставки. Повторы планирует consumer через очередь ожидания."""
    if not payment.webhook_url:
        return WebhookResult(delivered=True)

    payload = build_payload(payment)
    try:
        response = await client.post(
            payment.webhook_url,
            content=payload.model_dump_json(),
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Event": payload.event,
                "X-Payment-Id": str(payment.id),
            },
        )
    except httpx.HTTPError as exc:
        logger.warning("Webhook for payment %s failed: %s", payment.id, exc)
        return WebhookResult(delivered=False, error=f"{type(exc).__name__}: {exc}")

    if response.is_success:
        logger.info("Webhook for payment %s delivered (%s)", payment.id, response.status_code)
        return WebhookResult(delivered=True, status_code=response.status_code)

    logger.warning(
        "Webhook for payment %s rejected with status %s", payment.id, response.status_code
    )
    return WebhookResult(
        delivered=False,
        status_code=response.status_code,
        error=f"unexpected status {response.status_code}",
    )
