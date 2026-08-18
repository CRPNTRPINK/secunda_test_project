from fastapi import APIRouter, Depends

from app.api.deps import check_api_key
from app.api.v1.payments import router as payments_router

api_router = APIRouter(prefix="/api/v1", dependencies=[Depends(check_api_key)])
api_router.include_router(payments_router)
