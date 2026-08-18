import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1 import api_router
from app.core.logging import setup_logging
from app.db.session import engine

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


app = FastAPI(
    title="Payments Processing Service",
    description="Приём платежей, асинхронная обработка и уведомление клиента через webhook.",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(api_router)


@app.get("/health", tags=["system"], summary="Проверка живости сервиса")
async def health() -> JSONResponse:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("Health check failed: %s", exc)
        return JSONResponse(
            content={"status": "degraded", "database": "unavailable"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return JSONResponse(content={"status": "ok", "database": "ok"})
