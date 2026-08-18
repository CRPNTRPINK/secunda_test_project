from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "payments-service"
    log_level: str = "INFO"

    api_key: str = "local-dev-api-key"

    database_url: str = "postgresql+asyncpg://payments:payments@localhost:5432/payments"
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 10

    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    exchange_name: str = "payments"
    dlx_name: str = "payments.dlx"
    queue_new: str = "payments.new"
    queue_retry: str = "payments.retry"
    queue_dlq: str = "payments.dlq"
    consumer_prefetch_count: int = 10

    processing_min_seconds: float = 2.0
    processing_max_seconds: float = 5.0
    processing_success_rate: float = Field(default=0.9, ge=0, le=1)

    max_delivery_attempts: int = Field(default=3, ge=1)
    retry_base_delay_seconds: float = 2.0
    retry_max_delay_seconds: float = 60.0

    webhook_timeout_seconds: float = 10.0

    outbox_poll_interval_seconds: float = 1.0
    outbox_batch_size: int = 50
    outbox_max_attempts: int = 10


settings = Settings()
