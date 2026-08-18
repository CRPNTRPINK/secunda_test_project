import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.broker.broker import broker
from app.broker.topology import ATTEMPT_HEADER, payments_exchange
from app.core.config import settings
from app.models import OutboxMessage, OutboxStatus
from app.services.retry import backoff_delay

logger = logging.getLogger(__name__)


class OutboxRelay:
    """Публикует в RabbitMQ события, накопленные в таблице outbox.

    Строки берём через SKIP LOCKED, поэтому relay можно запускать в нескольких
    экземплярах: одно и то же событие не уйдёт дважды.
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions
        self._stop = asyncio.Event()

    async def run(self) -> None:
        logger.info("Outbox relay started")
        while not self._stop.is_set():
            try:
                published = await self.publish_batch()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Outbox relay iteration failed")
                published = 0

            if not published:
                with suppress(TimeoutError):
                    await asyncio.wait_for(
                        self._stop.wait(), settings.outbox_poll_interval_seconds
                    )
        logger.info("Outbox relay stopped")

    def stop(self) -> None:
        self._stop.set()

    async def publish_batch(self) -> int:
        async with self._sessions() as session, session.begin():
            messages = await self._take_batch(session)
            for message in messages:
                await self._publish(message)
            return len(messages)

    async def _take_batch(self, session: AsyncSession) -> list[OutboxMessage]:
        result = await session.execute(
            select(OutboxMessage)
            .where(
                OutboxMessage.status == OutboxStatus.PENDING,
                OutboxMessage.available_at <= datetime.now(UTC),
            )
            .order_by(OutboxMessage.available_at, OutboxMessage.created_at)
            .limit(settings.outbox_batch_size)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())

    async def _publish(self, message: OutboxMessage) -> None:
        message.attempts += 1
        try:
            await broker.publish(
                message.payload,
                exchange=payments_exchange,
                routing_key=message.routing_key,
                persist=True,
                message_id=str(message.id),
                content_type="application/json",
                headers={ATTEMPT_HEADER: 1},
            )
        except Exception as exc:
            self._schedule_next_try(message, f"{type(exc).__name__}: {exc}")
            return

        message.status = OutboxStatus.PUBLISHED
        message.published_at = datetime.now(UTC)
        message.last_error = None
        logger.info("Event %s published to %s", message.id, message.routing_key)

    def _schedule_next_try(self, message: OutboxMessage, error: str) -> None:
        message.last_error = error
        if message.attempts >= settings.outbox_max_attempts:
            message.status = OutboxStatus.FAILED
            logger.error(
                "Event %s gave up after %s attempts: %s", message.id, message.attempts, error
            )
            return

        delay = backoff_delay(
            message.attempts, settings.retry_base_delay_seconds, settings.retry_max_delay_seconds
        )
        message.available_at = datetime.now(UTC) + timedelta(seconds=delay)
        logger.warning("Event %s will be retried in %.0fs: %s", message.id, delay, error)
