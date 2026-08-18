import os

os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://payments:payments@localhost:55432/payments_test"
)
