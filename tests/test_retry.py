import pytest

from app.services.retry import backoff_delay


@pytest.mark.parametrize(("attempt", "expected"), [(1, 2.0), (2, 4.0), (3, 8.0), (4, 16.0)])
def test_delay_doubles_every_attempt(attempt: int, expected: float) -> None:
    assert backoff_delay(attempt, base_delay=2.0, max_delay=60.0) == expected


def test_delay_is_capped() -> None:
    assert backoff_delay(10, base_delay=2.0, max_delay=30.0) == 30.0


def test_first_attempt_is_not_negative() -> None:
    assert backoff_delay(0, base_delay=2.0, max_delay=60.0) == 2.0
