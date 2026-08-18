import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Payment, PaymentStatus
from app.schemas.payment import PaymentCreateRequest
from app.services.outbox import payment_created_message

logger = logging.getLogger(__name__)


class IdempotencyConflict(Exception):
    """Idempotency-Key уже использован, но с другим телом запроса."""


def fingerprint(payload: PaymentCreateRequest) -> str:
    body = json.dumps(
        payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(body.encode()).hexdigest()


async def get_payment(session: AsyncSession, payment_id: uuid.UUID) -> Payment | None:
    return await session.get(Payment, payment_id)


async def create_payment(
    session: AsyncSession, payload: PaymentCreateRequest, idempotency_key: str
) -> tuple[Payment, bool]:
    """Создаёт платеж вместе с событием outbox.

    Возвращает платеж и признак того, что он создан именно этим запросом:
    повтор с тем же Idempotency-Key отдаёт уже существующий платеж.
    """
    digest = fingerprint(payload)

    existing = await _find_by_key(session, idempotency_key)
    if existing:
        return _same_request_or_conflict(existing, digest), False

    payment = Payment(
        id=uuid.uuid4(),
        idempotency_key=idempotency_key,
        request_fingerprint=digest,
        amount=payload.amount,
        currency=payload.currency,
        description=payload.description,
        meta=payload.metadata,
        status=PaymentStatus.PENDING,
        webhook_url=str(payload.webhook_url) if payload.webhook_url else None,
        webhook_attempts=0,
        created_at=datetime.now(UTC),
    )
    session.add(payment)
    session.add(payment_created_message(payment.id, settings.queue_new))

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        concurrent = await _find_by_key(session, idempotency_key)
        if concurrent is None:
            raise
        return _same_request_or_conflict(concurrent, digest), False

    logger.info("Payment %s created (idempotency key %s)", payment.id, idempotency_key)
    return payment, True


async def _find_by_key(session: AsyncSession, idempotency_key: str) -> Payment | None:
    result = await session.execute(
        select(Payment).where(Payment.idempotency_key == idempotency_key)
    )
    return result.scalar_one_or_none()


def _same_request_or_conflict(payment: Payment, digest: str) -> Payment:
    if payment.request_fingerprint != digest:
        raise IdempotencyConflict("Idempotency-Key already used with a different request body")
    return payment
