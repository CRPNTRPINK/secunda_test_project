from app.schemas.payment import PaymentCreateRequest
from app.services.payments import fingerprint


def request(**overrides) -> PaymentCreateRequest:
    body = {
        "amount": "10.00",
        "currency": "RUB",
        "description": "test",
        "metadata": {"a": 1, "b": 2},
    }
    return PaymentCreateRequest(**body | overrides)


def test_equal_requests_give_equal_fingerprints() -> None:
    assert fingerprint(request()) == fingerprint(request())


def test_metadata_key_order_does_not_matter() -> None:
    assert fingerprint(request(metadata={"a": 1, "b": 2})) == fingerprint(
        request(metadata={"b": 2, "a": 1})
    )


def test_changed_amount_changes_fingerprint() -> None:
    assert fingerprint(request()) != fingerprint(request(amount="10.01"))
