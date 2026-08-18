import uuid

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import IdempotencyKeyDep, SessionDep
from app.schemas.payment import (
    ErrorResponse,
    PaymentAccepted,
    PaymentCreateRequest,
    PaymentResponse,
)
from app.services import payments

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Создание платежа",
    responses={409: {"model": ErrorResponse, "description": "Idempotency-Key уже использован"}},
)
async def create_payment(
    payload: PaymentCreateRequest,
    idempotency_key: IdempotencyKeyDep,
    session: SessionDep,
    response: Response,
) -> PaymentAccepted:
    try:
        payment, created = await payments.create_payment(session, payload, idempotency_key)
    except payments.IdempotencyConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    response.headers["Location"] = f"/api/v1/payments/{payment.id}"
    response.headers["Idempotent-Replay"] = "false" if created else "true"
    return PaymentAccepted(
        payment_id=payment.id, status=payment.status, created_at=payment.created_at
    )


@router.get(
    "/{payment_id}",
    summary="Получение информации о платеже",
    responses={404: {"model": ErrorResponse, "description": "Платеж не найден"}},
)
async def get_payment(payment_id: uuid.UUID, session: SessionDep) -> PaymentResponse:
    payment = await payments.get_payment(session, payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    return PaymentResponse.model_validate(payment)
