"""Consumer: обработчик очереди payments.new плюс публикация событий из outbox."""

import asyncio
import logging

from faststream import FastStream

from app.broker.broker import broker, declare_topology
from app.broker.consumer import http_client
from app.broker.outbox_relay import OutboxRelay
from app.core.logging import setup_logging
from app.db.session import engine, session_factory

setup_logging()
logger = logging.getLogger(__name__)

app = FastStream(broker, title="payments-consumer")
relay = OutboxRelay(session_factory)
relay_task: asyncio.Task[None] | None = None


@app.after_startup
async def start_relay() -> None:
    global relay_task
    await declare_topology()
    relay_task = asyncio.create_task(relay.run(), name="outbox-relay")


@app.after_shutdown
async def stop_relay() -> None:
    relay.stop()
    if relay_task:
        try:
            await asyncio.wait_for(relay_task, timeout=10)
        except (TimeoutError, asyncio.CancelledError):
            relay_task.cancel()
    await http_client.aclose()
    await engine.dispose()
    logger.info("Consumer stopped")


if __name__ == "__main__":
    asyncio.run(app.run())
