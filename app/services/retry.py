def backoff_delay(attempt: int, base_delay: float, max_delay: float) -> float:
    """Задержка перед попыткой номер attempt + 1: base, base*2, base*4, ... но не больше max."""
    return min(base_delay * 2 ** (max(attempt, 1) - 1), max_delay)
