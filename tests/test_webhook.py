import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from app.models import Currency, Payment, PaymentStatus
from app.services import webhook


def payment(status: PaymentStatus = PaymentStatus.SUCCEEDED) -> Payment:
    return Payment(
        id=uuid.uuid4(),
        idempotency_key="key",
        request_fingerprint="f" * 64,
        amount=Decimal("10.00"),
        currency=Currency.RUB,
        description="test",
        meta={"order_id": 7},
        status=status,
        failure_reason="card_declined" if status is PaymentStatus.FAILED else None,
        webhook_url="https://example.com/hook",
        webhook_attempts=0,
        created_at=datetime.now(UTC),
        processed_at=datetime.now(UTC),
    )


def client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_event_name_depends_on_status() -> None:
    assert webhook.build_payload(payment()).event == "payment.succeeded"
    assert webhook.build_payload(payment(PaymentStatus.FAILED)).event == "payment.failed"


@pytest.mark.parametrize("status", [PaymentStatus.SUCCEEDED, PaymentStatus.FAILED])
def test_payload_is_json_serializable(status: PaymentStatus) -> None:
    assert "payment_id" in webhook.build_payload(payment(status)).model_dump_json()


async def test_2xx_means_delivered() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Webhook-Event"] == "payment.succeeded"
        return httpx.Response(200)

    async with client(handler) as http:
        result = await webhook.send(http, payment())

    assert result.delivered
    assert result.status_code == 200


async def test_5xx_is_a_failure() -> None:
    async with client(lambda request: httpx.Response(500)) as http:
        result = await webhook.send(http, payment())

    assert not result.delivered
    assert result.error == "unexpected status 500"


async def test_network_error_is_a_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    async with client(handler) as http:
        result = await webhook.send(http, payment())

    assert not result.delivered
    assert "ConnectTimeout" in result.error


async def test_payment_without_webhook_url_is_skipped() -> None:
    without_url = payment()
    without_url.webhook_url = None

    async with client(lambda request: httpx.Response(500)) as http:
        result = await webhook.send(http, without_url)

    assert result.delivered
