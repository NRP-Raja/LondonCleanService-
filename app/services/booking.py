"""CleanLondon Booking Service — business logic for customer booking endpoints."""

import datetime
import random
import re
from typing import Optional

from fastapi import HTTPException

from app.database.connection import get_db
from app.utils.encryption import encrypt_sensitive_data, decrypt_sensitive_data
from app.utils.postcode import resolve_postcode_coords
from app.schemas.bookings import (
    BookingCreateSchema,
    CancelBookingSchema,
    RescheduleBookingSchema,
    ReviewCreateSchema,
)
from app.services.pricing import compute_quote
from app.schemas.services import QuoteRequestSchema
from app.utils.notifications import queue_notification


# ---------------------------------------------------------------------------
# Create Booking
# ---------------------------------------------------------------------------
def create_booking(
    payload: BookingCreateSchema,
    idempotency_key: Optional[str],
    user_id: int,
) -> dict:
    """Create a new customer booking with idempotency, duplicate guard, pricing, and access-data encryption."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            # 1. Idempotency Check
            if idempotency_key:
                cursor.execute(
                    """
                    SELECT id, customer_id, reference_code, total_price_gbp, status, payment_status, created_at
                    FROM bookings
                    WHERE idempotency_key = %s
                    """,
                    (idempotency_key,),
                )
                existing_idem = cursor.fetchone()
                if existing_idem:
                    if existing_idem["customer_id"] != user_id:
                        raise HTTPException(
                            status_code=409,
                            detail="The supplied Idempotency-Key has already been used.",
                        )
                    return {
                        "message": "Booking request recognized (idempotent replay)",
                        "booking_id": existing_idem["id"],
                        "reference_code": existing_idem["reference_code"],
                        "total_price_gbp": float(existing_idem["total_price_gbp"]),
                        "status": existing_idem["status"],
                        "idempotent_replayed": True,
                    }

            # 2. Duplicate Submission Guard
            cursor.execute(
                """
                SELECT id, reference_code, status, created_at
                FROM bookings
                WHERE customer_id = %s
                  AND address_line1 = %s
                  AND postcode = %s
                  AND scheduled_date = %s
                  AND scheduled_time_slot = %s
                  AND status IN ('SCHEDULED', 'EN_ROUTE', 'IN_PROGRESS')
                """,
                (
                    user_id,
                    payload.address_line1,
                    payload.postcode,
                    payload.scheduled_date,
                    payload.scheduled_time_slot,
                ),
            )
            duplicate_active = cursor.fetchone()
            if duplicate_active:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Duplicate booking detected: You already have an active appointment "
                        f"(Ref: {duplicate_active['reference_code']}, Status: {duplicate_active['status']}) at this address "
                        f"for {payload.scheduled_date} ({payload.scheduled_time_slot}). "
                        f"Please manage your existing booking or select a different time slot."
                    ),
                )

            cursor.execute("SELECT * FROM services WHERE id = %s", (payload.service_id,))
            service = cursor.fetchone()
            if not service:
                raise HTTPException(status_code=404, detail="Selected service not found")

            # Coordinate resolution
            coords = resolve_postcode_coords(payload.postcode)
            lat, lon = coords[0], coords[1]

            # Price calculations via pricing service
            quote = compute_quote(QuoteRequestSchema(
                postcode=payload.postcode,
                service_id=payload.service_id,
                property_type=payload.property_type,
                bedrooms=payload.bedrooms,
                bathrooms=payload.bathrooms,
                has_pets=payload.has_pets,
                deep_clean=payload.deep_clean_requested,
                eco_products=payload.eco_cleaning_products,
            ))

            reference_code = None
            for _ in range(10):
                candidate = f"CL-{datetime.datetime.now().year}-{random.randint(100000, 999999)}"
                cursor.execute("SELECT id FROM bookings WHERE reference_code = %s", (candidate,))
                if not cursor.fetchone():
                    reference_code = candidate
                    break
            if reference_code is None:
                raise HTTPException(
                    status_code=409,
                    detail="Could not generate a unique booking reference. Please retry.",
                )

            # UK GDPR: Encrypt sensitive access data at rest
            encrypted_access_notes = encrypt_sensitive_data(payload.access_notes)

            cursor.execute(
                """
                INSERT INTO bookings (
                    reference_code, idempotency_key, customer_id, service_id,
                    property_type, bedrooms, bathrooms, has_pets, deep_clean_requested, eco_cleaning_products,
                    address_line1, address_line2, city, postcode, latitude, longitude,
                    key_handling_type, access_notes, scheduled_date, scheduled_time_slot,
                    duration_hours, hourly_rate_gbp, total_price_gbp, status, payment_status
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, 'SCHEDULED', 'PENDING'
                )
                """,
                (
                    reference_code, idempotency_key, user_id, payload.service_id,
                    payload.property_type, payload.bedrooms, payload.bathrooms, payload.has_pets,
                    payload.deep_clean_requested, payload.eco_cleaning_products,
                    payload.address_line1, payload.address_line2, payload.city, payload.postcode,
                    lat, lon, payload.key_handling_type, encrypted_access_notes,
                    payload.scheduled_date, payload.scheduled_time_slot,
                    quote["estimated_duration_hours"], quote["hourly_equivalent_gbp"], quote["total_price_gbp"],
                ),
            )
            booking_id = cursor.lastrowid

            # Add status audit log
            cursor.execute(
                """
                INSERT INTO booking_status_logs (booking_id, changed_by_user_id, previous_status, new_status, notes)
                VALUES (%s, %s, NULL, 'SCHEDULED', 'Booking created by customer')
                """,
                (booking_id, user_id),
            )

            cursor.execute("SELECT email FROM users WHERE id = %s", (user_id,))
            recipient = cursor.fetchone()
            if recipient:
                queue_notification(
                    cursor,
                    user_id,
                    recipient["email"],
                    f"CleanLondon booking confirmed: {reference_code}",
                    f"Your cleaning is scheduled for {payload.scheduled_date} ({payload.scheduled_time_slot}). Reference: {reference_code}",
                )

            return {
                "message": "Booking created successfully",
                "booking_id": booking_id,
                "reference_code": reference_code,
                "total_price_gbp": quote["total_price_gbp"],
                "estimated_duration_hours": quote["estimated_duration_hours"],
                "status": "SCHEDULED",
                "idempotent_replayed": False,
            }


# ---------------------------------------------------------------------------
# Get My Bookings (Customer)
# ---------------------------------------------------------------------------
def get_my_bookings(user_id: int) -> dict:
    """Return all bookings for a customer with decrypted access notes."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT b.*, s.name as service_name, u.full_name as staff_name, u.phone as staff_phone,
                       u.avatar_url as staff_avatar_url, sp.rating_avg as staff_rating,
                       sp.verified_dbs as staff_dbs_verified,
                       r.rating as review_rating, r.comment as review_comment
                FROM bookings b
                JOIN services s ON b.service_id = s.id
                LEFT JOIN users u ON b.staff_id = u.id
                LEFT JOIN staff_profiles sp ON b.staff_id = sp.user_id
                LEFT JOIN reviews r ON b.id = r.booking_id
                WHERE b.customer_id = %s
                ORDER BY b.scheduled_date DESC, b.id DESC
                """,
                (user_id,),
            )
            bookings = cursor.fetchall()
            for b in bookings:
                b["access_notes"] = decrypt_sensitive_data(b.get("access_notes"))
            return {"bookings": bookings}



# ---------------------------------------------------------------------------
# Cancel Booking
# ---------------------------------------------------------------------------
def cancel_booking(
    booking_id: int,
    payload: Optional[CancelBookingSchema],
    user_id: int,
    user_role: str,
) -> dict:
    """Cancel a booking with UK Consumer Protection cancellation policy."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM bookings WHERE id = %s", (booking_id,))
            booking = cursor.fetchone()
            if not booking:
                raise HTTPException(status_code=404, detail="Booking not found")

            # Ownership check: Customers can only cancel their own bookings
            if user_role == "customer" and booking["customer_id"] != user_id:
                raise HTTPException(status_code=403, detail="You can only cancel your own bookings")

            if booking["status"] == "CANCELLED":
                raise HTTPException(status_code=400, detail="This booking has already been cancelled")

            if booking["status"] in ["EN_ROUTE", "IN_PROGRESS", "COMPLETED"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot cancel booking: Cleaner is already '{booking['status']}'. Cancellations are only permitted while status is 'SCHEDULED'.",
                )

            # Parse scheduled start time
            times = re.findall(r"(\d{1,2}:\d{2})", booking["scheduled_time_slot"])
            start_time_str = times[0] if times else "09:00"
            try:
                service_dt = datetime.datetime.strptime(
                    f"{booking['scheduled_date']} {start_time_str}:00", "%Y-%m-%d %H:%M:%S"
                )
            except Exception:
                service_dt = datetime.datetime.combine(booking["scheduled_date"], datetime.time(9, 0))

            now = datetime.datetime.now()
            hours_until_service = (service_dt - now).total_seconds() / 3600.0

            if hours_until_service < 0:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot cancel an appointment whose scheduled start time has already passed.",
                )

            total_price = float(booking["total_price_gbp"])
            reason = payload.reason if payload and payload.reason else "Cancelled by customer"

            # Late cancellation fee rule: >24h = free, <24h = 50% fee
            if hours_until_service >= 24.0:
                cancellation_fee = 0.00
                refund_amount = total_price
                policy_note = f"Free cancellation (>24h notice). Full refund of £{refund_amount:.2f} issued."
                policy_applied = "FREE_CANCELLATION"
            else:
                cancellation_fee = round(total_price * 0.50, 2)
                refund_amount = round(total_price - cancellation_fee, 2)
                policy_note = f"Late cancellation (<24h notice): 50% fee (£{cancellation_fee:.2f}) retained. Refund of £{refund_amount:.2f} issued."
                policy_applied = "50_PERCENT_LATE_FEE"

            new_payment_status = "REFUNDED" if booking["payment_status"] == "PAID" else "PENDING"

            if booking["payment_status"] == "PAID" and refund_amount > 0:
                payment_intent_id = booking.get("stripe_payment_intent_id")
                is_mock_stripe = not STRIPE_SECRET_KEY or "mock" in STRIPE_SECRET_KEY.lower()
                if not is_mock_stripe and not payment_intent_id:
                    raise HTTPException(
                        status_code=409,
                        detail="Paid booking has no payment reference; refund cannot be safely issued.",
                    )
                if not is_mock_stripe and payment_intent_id:
                    import stripe
                    try:
                        stripe.Refund.create(
                            payment_intent=payment_intent_id,
                            amount=int(round(refund_amount * 100)),
                            metadata={
                                "booking_id": str(booking_id),
                                "policy": policy_applied,
                            },
                        )
                    except stripe.error.StripeError as exc:
                        raise HTTPException(
                            status_code=502,
                            detail="The payment provider rejected the refund. The booking was not cancelled.",
                        ) from exc

            cursor.execute(
                """
                UPDATE bookings
                SET status = 'CANCELLED',
                    payment_status = %s,
                    cancelled_at = NOW(),
                    cancellation_fee_gbp = %s,
                    refund_amount_gbp = %s,
                    cancellation_reason = %s,
                    staff_id = NULL
                WHERE id = %s
                """,
                (new_payment_status, cancellation_fee, refund_amount, f"{reason} | {policy_note}", booking_id),
            )

            cursor.execute(
                """
                INSERT INTO booking_status_logs (booking_id, changed_by_user_id, previous_status, new_status, notes)
                VALUES (%s, %s, %s, 'CANCELLED', %s)
                """,
                (booking_id, user_id, booking["status"], f"Booking cancelled. {policy_note} Reason: {reason}"),
            )

            queue_notification(
                cursor,
                user_id,
                booking["email"] if "email" in booking else "",
                f"CleanLondon booking {booking_id}: CANCELLED",
                f"Booking {booking_id} is now cancelled. {policy_note}",
            )

            return {
                "message": "Booking cancelled successfully",
                "booking_id": booking_id,
                "reference_code": booking["reference_code"],
                "status": "CANCELLED",
                "hours_until_service": round(hours_until_service, 1),
                "total_price_gbp": total_price,
                "cancellation_fee_gbp": cancellation_fee,
                "refund_amount_gbp": refund_amount,
                "policy_applied": policy_applied,
                "policy_note": policy_note,
            }



# ---------------------------------------------------------------------------
# Reschedule Booking
# ---------------------------------------------------------------------------
def reschedule_booking(
    booking_id: int,
    payload: RescheduleBookingSchema,
    user_id: int,
    user_role: str,
) -> dict:
    """Reschedule a booking to a new date/time slot with cleaner conflict checking."""
    from app.services.staff import check_cleaner_schedule_conflict

    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM bookings WHERE id = %s", (booking_id,))
            booking = cursor.fetchone()
            if not booking:
                raise HTTPException(status_code=404, detail="Booking not found")

            if user_role == "customer" and booking["customer_id"] != user_id:
                raise HTTPException(status_code=403, detail="You can only reschedule your own bookings")

            if booking["status"] != "SCHEDULED":
                raise HTTPException(
                    status_code=400,
                    detail=f"Only bookings in 'SCHEDULED' status can be rescheduled. Current status: '{booking['status']}'.",
                )

            # Validate new appointment date is in future
            times = re.findall(r"(\d{1,2}:\d{2})", payload.new_time_slot)
            start_str = times[0] if times else "09:00"
            try:
                new_dt = datetime.datetime.strptime(
                    f"{payload.new_date} {start_str}:00", "%Y-%m-%d %H:%M:%S"
                )
            except Exception:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid date or time slot format. Use YYYY-MM-DD and HH:MM - HH:MM.",
                )

            if new_dt <= datetime.datetime.now():
                raise HTTPException(
                    status_code=400,
                    detail="New scheduled date and time must be in the future",
                )

            # Check if currently assigned cleaner has conflict on new slot
            reassigned_note = ""
            staff_id = booking["staff_id"]
            if staff_id:
                has_conflict, reason = check_cleaner_schedule_conflict(
                    cursor, staff_id, payload.new_date, payload.new_time_slot,
                    booking["postcode"], exclude_booking_id=booking_id,
                )
                if has_conflict:
                    staff_id = None
                    reassigned_note = " (Assigned cleaner unavailable on new slot; cleaner unassigned for re-dispatch)"

            cursor.execute(
                """
                UPDATE bookings
                SET scheduled_date = %s,
                    scheduled_time_slot = %s,
                    staff_id = %s
                WHERE id = %s
                """,
                (payload.new_date, payload.new_time_slot, staff_id, booking_id),
            )

            cursor.execute(
                """
                INSERT INTO booking_status_logs (booking_id, changed_by_user_id, previous_status, new_status, notes)
                VALUES (%s, %s, 'SCHEDULED', 'SCHEDULED', %s)
                """,
                (
                    booking_id,
                    user_id,
                    f"Rescheduled to {payload.new_date} ({payload.new_time_slot}){reassigned_note}",
                ),
            )

            cursor.execute(
                """
                SELECT email FROM users WHERE id = %s
                """,
                (user_id,),
            )
            recipient = cursor.fetchone()
            if recipient:
                queue_notification(
                    cursor,
                    user_id,
                    recipient["email"],
                    f"CleanLondon booking rescheduled: {booking['reference_code']}",
                    f"Your booking is now scheduled for {payload.new_date} ({payload.new_time_slot}).",
                )

            return {
                "message": f"Booking rescheduled successfully to {payload.new_date} ({payload.new_time_slot}){reassigned_note}",
                "booking_id": booking_id,
                "reference_code": booking["reference_code"],
                "scheduled_date": payload.new_date,
                "scheduled_time_slot": payload.new_time_slot,
                "cleaner_assigned": staff_id is not None,
            }


# ---------------------------------------------------------------------------
# Review Booking (Customer)
# ---------------------------------------------------------------------------
def review_booking(
    booking_id: int,
    payload: ReviewCreateSchema,
    user_id: int,
) -> dict:
    """Submit a customer review for a completed booking and update cleaner aggregate rating."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM bookings WHERE id = %s AND customer_id = %s",
                (booking_id, user_id),
            )
            booking = cursor.fetchone()
            if not booking:
                raise HTTPException(status_code=404, detail="Booking not found or not owned by you")
            if booking["status"] != "COMPLETED":
                raise HTTPException(status_code=400, detail="Only completed bookings can be reviewed")
            if not booking["staff_id"]:
                raise HTTPException(status_code=400, detail="Cannot review a booking without assigned cleaner")

            # Check if review already exists
            cursor.execute("SELECT id FROM reviews WHERE booking_id = %s", (booking_id,))
            if cursor.fetchone():
                raise HTTPException(
                    status_code=400,
                    detail="A review has already been submitted for this booking",
                )

            cursor.execute(
                """
                INSERT INTO reviews (booking_id, customer_id, staff_id, rating, comment, punctuality_score, thoroughness_score)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    booking_id, user_id, booking["staff_id"],
                    payload.rating, payload.comment,
                    payload.punctuality_score, payload.thoroughness_score,
                ),
            )

            # Recalculate staff rating
            cursor.execute(
                """
                SELECT AVG(rating) as avg_rating, COUNT(*) as count_rating
                FROM reviews WHERE staff_id = %s
                """,
                (booking["staff_id"],),
            )
            agg = cursor.fetchone()
            cursor.execute(
                """
                UPDATE staff_profiles
                SET rating_avg = %s, rating_count = %s
                WHERE user_id = %s
                """,
                (agg["avg_rating"], agg["count_rating"], booking["staff_id"]),
            )

            return {"message": "Thank you! Your review has been published.", "rating": payload.rating}

