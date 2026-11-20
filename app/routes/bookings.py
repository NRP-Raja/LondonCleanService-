"""CleanLondon Booking Routes — HTTP endpoint definitions for customer bookings."""

from fastapi import APIRouter, Request, Depends, Body
from fastapi import HTTPException, status
from typing import Optional

from app.core.dependencies import get_current_user, require_role
from app.core.security import limiter
from app.database.connection import get_idempotency_key
from app.schemas.bookings import (
    BookingCreateSchema,
    CancelBookingSchema,
    RescheduleBookingSchema,
    ReviewCreateSchema,
)
from app.services.booking import (
    create_booking,
    get_my_bookings,
    cancel_booking,
    reschedule_booking,
    review_booking,
)

router = APIRouter(prefix="/api/bookings", tags=["Bookings"])


@router.post("", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
def create_booking_route(
    request: Request,
    payload: BookingCreateSchema,
    user: dict = Depends(require_role(["customer", "manager"])),
):
    """Create a new cleaning booking."""
    idempotency_key = get_idempotency_key(request, payload.idempotency_key)
    return create_booking(payload, idempotency_key, user["id"])


@router.get("/my")
def list_my_bookings(user: dict = Depends(require_role(["customer"]))):
    """List all bookings for the authenticated customer."""
    return get_my_bookings(user["id"])


@router.patch("/{booking_id}/cancel")
def cancel_booking_route(
    booking_id: int,
    payload: Optional[CancelBookingSchema] = Body(None),
    user: dict = Depends(require_role(["customer", "manager"])),
):
    """Cancel a booking with UK Consumer Protection cancellation policy."""
    return cancel_booking(booking_id, payload, user["id"], user["role"])


@router.post("/{booking_id}/reschedule")
def reschedule_booking_route(
    booking_id: int,
    payload: RescheduleBookingSchema = Body(...),
    user: dict = Depends(require_role(["customer", "manager"])),
):
    """Reschedule a booking to a new date/time slot."""
    return reschedule_booking(booking_id, payload, user["id"], user["role"])


@router.post("/{booking_id}/review")
def review_booking_route(
    booking_id: int,
    payload: ReviewCreateSchema = Body(...),
    user: dict = Depends(require_role(["customer"])),
):
    """Submit a review for a completed booking."""
    return review_booking(booking_id, payload, user["id"])
