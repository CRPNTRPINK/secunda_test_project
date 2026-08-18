"""Обменники и очереди сервиса.

Событие о новом платеже приходит в payments.new через обменник payments.
Если обработка не удалась, consumer перекладывает сообщение в payments.retry -
очередь без потребителей, где оно ждёт свой TTL и по dead-letter возвращается
в payments.new. После max_delivery_attempts попыток сообщение уходит в
payments.dlq; туда же ведёт dead-letter самой payments.new на случай, когда
сообщение отклонили помимо нашей логики.
"""

from faststream.rabbit import ExchangeType, RabbitExchange, RabbitQueue

from app.core.config import settings

ATTEMPT_HEADER = "x-attempt"
ERROR_HEADER = "x-last-error"

payments_exchange = RabbitExchange(
    settings.exchange_name, type=ExchangeType.DIRECT, durable=True
)
dead_letter_exchange = RabbitExchange(settings.dlx_name, type=ExchangeType.DIRECT, durable=True)

payments_new_queue = RabbitQueue(
    settings.queue_new,
    durable=True,
    routing_key=settings.queue_new,
    arguments={
        "x-dead-letter-exchange": settings.dlx_name,
        "x-dead-letter-routing-key": settings.queue_dlq,
    },
)

payments_retry_queue = RabbitQueue(
    settings.queue_retry,
    durable=True,
    routing_key=settings.queue_retry,
    arguments={
        "x-dead-letter-exchange": settings.exchange_name,
        "x-dead-letter-routing-key": settings.queue_new,
    },
)

payments_dlq = RabbitQueue(settings.queue_dlq, durable=True, routing_key=settings.queue_dlq)
