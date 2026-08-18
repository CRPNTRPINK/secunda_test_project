from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session


async def check_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    if not x_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "X-API-Key header is required")
    if not compare_digest(x_api_key, settings.api_key):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid API key")


async def get_idempotency_key(idempotency_key: Annotated[str | None, Header()] = None) -> str:
    key = (idempotency_key or "").strip()
    if not key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Idempotency-Key header is required")
    if len(key) > 255:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Idempotency-Key must be at most 255 characters"
        )
    return key


SessionDep = Annotated[AsyncSession, Depends(get_session)]
IdempotencyKeyDep = Annotated[str, Depends(get_idempotency_key)]
