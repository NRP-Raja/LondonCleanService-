"""CleanLondon Stripe payment routes."""

from typing import Optional

from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool

from app.core.dependencies import require_role
from app.database.connection import get_idempotency_key
from app.schemas.payments import CreateCheckoutSessionSchema
from app.services.payments import (
    create_checkout_session,
    fulfill_stripe_payment,
    parse_stripe_webhook,
    verify_payment_session,
)

router = APIRouter(prefix="/api/payments", tags=["Payments"])


@router.post("/create-checkout-session")
def create_checkout_session_route(
    payload: CreateCheckoutSessionSchema,
    request: Request,
    user: dict = Depends(require_role(["customer", "manager"])),
):
    idempotency_key = get_idempotency_key(request)
    return create_checkout_session(payload.booking_id, idempotency_key, user)


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(request: Request):
    payload = await request.body()
    event = parse_stripe_webhook(payload, request.headers.get("stripe-signature"))
    event_type = event.get("type")
    if event_type == "checkout.session.completed":
        session = event.get("data", {}).get("object", {})
        metadata = session.get("metadata", {})
        booking_id = metadata.get("booking_id") or session.get("client_reference_id")
        session_id = session.get("id")
        payment_intent_id = session.get("payment_intent") or f"pi_mock_{__import__('random').randint(1000, 9999)}"
        if not booking_id:
            return {"status": "ignored", "reason": "No booking_id associated with session"}
        return await run_in_threadpool(
            fulfill_stripe_payment,
            int(booking_id),
            session_id,
            payment_intent_id,
        )
    return {"status": "unhandled_event", "type": event_type}


@router.get("/session/{session_id}/verify")
def verify_payment_session_route(
    session_id: str,
    booking_id: Optional[int] = None,
):
    return verify_payment_session(session_id, booking_id)
