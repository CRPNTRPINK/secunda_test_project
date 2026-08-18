"""Проверки контракта API, не требующие БД: аутентификация и валидация."""

import httpx
import pytest

from app.core.config import settings
from app.main import app

HEADERS = {"X-API-Key": settings.api_key, "Idempotency-Key": "test-key-1"}
BODY = {"amount": "100.00", "currency": "RUB", "description": "test"}


@pytest.fixture
async def client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_missing_api_key_is_401(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/payments", json=BODY)
    assert response.status_code == 401


async def test_wrong_api_key_is_403(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/payments", json=BODY, headers={**HEADERS, "X-API-Key": "nope"}
    )
    assert response.status_code == 403


async def test_missing_idempotency_key_is_400(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/payments", json=BODY, headers={"X-API-Key": settings.api_key}
    )
    assert response.status_code == 400
    assert "Idempotency-Key" in response.json()["detail"]


async def test_invalid_body_is_422(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/payments", json={"amount": "-1", "currency": "RUB"}, headers=HEADERS
    )
    assert response.status_code == 422


async def test_get_payment_requires_api_key(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/payments/6f8d0a4e-1b1e-4e3a-8d3f-2f0c9d0b1a2b")
    assert response.status_code == 401


async def test_invalid_uuid_is_422(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/payments/not-a-uuid", headers=HEADERS)
    assert response.status_code == 422
