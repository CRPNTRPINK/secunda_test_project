"""Мини-приёмник webhook'ов для ручной проверки.

Запускается через docker compose --profile demo. С WEBHOOK_ECHO_FAIL=true
отвечает 500 - так видно повторы и попадание сообщения в DLQ.
"""

import json
import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("webhook-echo")

FAIL = os.getenv("WEBHOOK_ECHO_FAIL", "false").lower() in {"1", "true", "yes"}

app = FastAPI(title="webhook-echo")
received: list[dict] = []


@app.post("/hook")
async def hook(request: Request) -> JSONResponse:
    payload = await request.json()
    received.append(payload)
    logger.info("received webhook: %s", json.dumps(payload, ensure_ascii=False))
    if FAIL:
        return JSONResponse(status_code=500, content={"error": "simulated failure"})
    return JSONResponse(content={"received": True})


@app.get("/received")
async def list_received() -> list[dict]:
    return received
