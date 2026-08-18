from enum import StrEnum


class Currency(StrEnum):
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"


def enum_values(enum_cls: type[StrEnum]) -> list[str]:
    """SQLAlchemy по умолчанию кладёт в БД имена членов enum, а нам нужны значения."""
    return [member.value for member in enum_cls]
