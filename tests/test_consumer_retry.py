"""Consumer сам решает, повторить сообщение или отправить его в DLQ."""

import uuid
from datetime import UTC, datetime

import pytest

from app.broker import consumer
from app.core.config import settings


@pytest.fixture
def published(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    async def fake_publish(message, **kwargs):
        calls.append({"message": message, **kwargs})

    monkeypatch.setattr(consumer.broker, "publish", fake_publish)
    return calls


def event() -> consumer.PaymentCreatedEvent:
    return consumer.PaymentCreatedEvent(
        event_id=uuid.uuid4(), payment_id=uuid.uuid4(), occurred_at=datetime.now(UTC)
    )


async def test_first_failure_goes_to_retry_queue(published: list[dict]) -> None:
    await consumer.retry_later(event(), attempt=1, error="boom")

    (call,) = published
    assert call["queue"] == settings.queue_retry
    assert call["expiration"] == settings.retry_base_delay_seconds
    assert call["headers"] == {"x-attempt": 2, "x-last-error": "boom"}


async def test_second_failure_waits_twice_as_long(published: list[dict]) -> None:
    await consumer.retry_later(event(), attempt=2, error="boom")

    (call,) = published
    assert call["expiration"] == settings.retry_base_delay_seconds * 2
    assert call["headers"]["x-attempt"] == 3


async def test_last_attempt_goes_to_dlq(published: list[dict]) -> None:
    await consumer.retry_later(event(), attempt=settings.max_delivery_attempts, error="boom")

    (call,) = published
    assert call["routing_key"] == settings.queue_dlq
    assert call["exchange"] is consumer.dead_letter_exchange
    assert call["headers"]["x-attempt"] == settings.max_delivery_attempts


class FakeMessage:
    def __init__(self, headers: dict) -> None:
        self.headers = headers


@pytest.mark.parametrize(
    ("headers", "expected"),
    [({}, 1), ({"x-attempt": 3}, 3), ({"x-attempt": "2"}, 2), ({"x-attempt": "junk"}, 1)],
)
def test_attempt_number_is_read_from_headers(headers: dict, expected: int) -> None:
    assert consumer.attempt_number(FakeMessage(headers)) == expected
