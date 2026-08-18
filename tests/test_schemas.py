from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.enums import Currency
from app.schemas.payment import PaymentCreateRequest


def test_valid_request() -> None:
    request = PaymentCreateRequest(
        amount="100.5",
        currency="RUB",
        description="order #1",
        metadata={"order_id": 1},
        webhook_url="https://example.com/hook",
    )
    assert request.amount == Decimal("100.50")
    assert request.currency is Currency.RUB


@pytest.mark.parametrize("amount", ["0", "-1", "10.123"])
def test_invalid_amount(amount: str) -> None:
    with pytest.raises(ValidationError):
        PaymentCreateRequest(amount=amount, currency="RUB")


def test_unknown_currency_rejected() -> None:
    with pytest.raises(ValidationError):
        PaymentCreateRequest(amount="10", currency="GBP")


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        PaymentCreateRequest(amount="10", currency="RUB", unexpected="x")


def test_metadata_defaults_to_empty_dict() -> None:
    assert PaymentCreateRequest(amount="10", currency="USD").metadata == {}
