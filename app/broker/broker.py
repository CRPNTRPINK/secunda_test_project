import logging

from faststream.rabbit import RabbitBroker

from app.broker.topology import (
    dead_letter_exchange,
    payments_dlq,
    payments_exchange,
    payments_new_queue,
    payments_retry_queue,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

broker = RabbitBroker(settings.rabbitmq_url, max_consumers=settings.consumer_prefetch_count)


async def declare_topology() -> None:
    """Объявляет обменники, очереди и биндинги.

    Подписчик FastStream объявляет только свою очередь, а publish в payments.new
    должен работать в любом случае, поэтому биндинги создаём явно.
    """
    exchange = await broker.declare_exchange(payments_exchange)
    dlx = await broker.declare_exchange(dead_letter_exchange)

    new_queue = await broker.declare_queue(payments_new_queue)
    await broker.declare_queue(payments_retry_queue)
    dlq = await broker.declare_queue(payments_dlq)

    await new_queue.bind(exchange, routing_key=settings.queue_new)
    await dlq.bind(dlx, routing_key=settings.queue_dlq)
    logger.info("RabbitMQ topology is ready")
