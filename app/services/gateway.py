import asyncio
import logging
import random
import uuid
from dataclasses import dataclass

from app.core.config import settings

logger = logging.getLogger(__name__)

FAILURE_REASONS = ("insufficient_funds", "card_declined", "gateway_timeout", "fraud_suspected")


@dataclass(slots=True)
class GatewayResult:
    success: bool
    failure_reason: str | None = None


async def charge(payment_id: uuid.UUID) -> GatewayResult:
    """Эмуляция внешнего шлюза: 2-5 секунд, 90% успешных списаний."""
    delay = random.uniform(settings.processing_min_seconds, settings.processing_max_seconds)
    logger.info("Sending payment %s to gateway, waiting ~%.1fs", payment_id, delay)
    await asyncio.sleep(delay)

    if random.random() < settings.processing_success_rate:
        return GatewayResult(success=True)
    return GatewayResult(success=False, failure_reason=random.choice(FAILURE_REASONS))
