import logging
import uuid
from datetime import UTC, datetime

import httpx
from faststream.rabbit.annotations import RabbitMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.broker.broker import broker
from app.broker.topology import (
    ATTEMPT_HEADER,
    ERROR_HEADER,
    dead_letter_exchange,
    payments_exchange,
    payments_new_queue,
)
from app.core.config import settings
from app.db.session import session_factory
from app.models import Payment, PaymentStatus
from app.schemas.events import PaymentCreatedEvent
from app.services import gateway, webhook
from app.services.retry import backoff_delay

logger = logging.getLogger(__name__)

http_client = httpx.AsyncClient(timeout=settings.webhook_timeout_seconds)


class WebhookNotDelivered(Exception):
    pass


class PaymentNotFound(Exception):
    pass


@broker.subscriber(payments_new_queue, payments_exchange, retry=False)
async def on_payment_created(event: PaymentCreatedEvent, message: RabbitMessage) -> None:
    """Проводит платеж и уведомляет клиента.

    Исключения наружу не пробрасываем: штатный requeue у RabbitMQ мгновенный и
    бесконечный, а нам нужны ровно три попытки с растущей паузой. Поэтому
    решение о повторе принимаем сами и складываем сообщение в очередь ожидания.
    """
    attempt = attempt_number(message)
    try:
        await process(event.payment_id)
    except PaymentNotFound as exc:
        logger.error("Payment %s: %s", event.payment_id, exc)
        await move_to_dlq(event, attempt, str(exc))
    except Exception as exc:
        logger.warning(
            "Payment %s failed on attempt %s/%s: %s",
            event.payment_id,
            attempt,
            settings.max_delivery_attempts,
            exc,
        )
        await retry_later(event, attempt, f"{type(exc).__name__}: {exc}"[:512])
    else:
        logger.info("Payment %s handled on attempt %s", event.payment_id, attempt)


async def process(payment_id: uuid.UUID) -> None:
    async with session_factory() as session:
        payment = await session.get(Payment, payment_id)
        if payment is None:
            raise PaymentNotFound("payment is not in the database")

        if payment.status is PaymentStatus.PENDING:
            await charge(session, payment)
        else:
            logger.info("Payment %s is already %s, skipping gateway", payment.id, payment.status)

        await notify(session, payment)


async def charge(session: AsyncSession, payment: Payment) -> None:
    result = await gateway.charge(payment.id)
    payment.status = PaymentStatus.SUCCEEDED if result.success else PaymentStatus.FAILED
    payment.failure_reason = result.failure_reason
    payment.processed_at = datetime.now(UTC)
    await session.commit()
    logger.info("Payment %s is %s", payment.id, payment.status)


async def notify(session: AsyncSession, payment: Payment) -> None:
    if not payment.webhook_url or payment.webhook_delivered_at:
        return

    result = await webhook.send(http_client, payment)
    payment.webhook_attempts += 1
    if result.delivered:
        payment.webhook_delivered_at = datetime.now(UTC)
        payment.webhook_last_error = None
    else:
        payment.webhook_last_error = result.error
    await session.commit()

    if not result.delivered:
        raise WebhookNotDelivered(f"webhook delivery failed: {result.error}")


def attempt_number(message: RabbitMessage) -> int:
    try:
        return max(int(message.headers.get(ATTEMPT_HEADER, 1)), 1)
    except (TypeError, ValueError):
        return 1


async def retry_later(event: PaymentCreatedEvent, attempt: int, error: str) -> None:
    if attempt >= settings.max_delivery_attempts:
        await move_to_dlq(event, attempt, error)
        return

    delay = backoff_delay(
        attempt, settings.retry_base_delay_seconds, settings.retry_max_delay_seconds
    )
    await broker.publish(
        event.model_dump(mode="json"),
        queue=settings.queue_retry,
        persist=True,
        expiration=delay,
        headers={ATTEMPT_HEADER: attempt + 1, ERROR_HEADER: error},
    )
    logger.info("Payment %s: attempt %s in %.0fs", event.payment_id, attempt + 1, delay)


async def move_to_dlq(event: PaymentCreatedEvent, attempt: int, error: str) -> None:
    await broker.publish(
        event.model_dump(mode="json"),
        exchange=dead_letter_exchange,
        routing_key=settings.queue_dlq,
        persist=True,
        headers={ATTEMPT_HEADER: attempt, ERROR_HEADER: error},
    )
    logger.error(
        "Payment %s moved to DLQ after %s attempt(s): %s", event.payment_id, attempt, error
    )
