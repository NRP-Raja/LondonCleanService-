"""CleanLondon Stripe checkout and webhook services."""

import hashlib
import json
import random
from typing import Optional

import stripe
from fastapi import HTTPException, Request

from app.core.config import (
    IS_PRODUCTION,
    MOCK_MODE,
    STRIPE_CANCEL_URL,
    STRIPE_SECRET_KEY,
    STRIPE_SUCCESS_URL,
    STRIPE_WEBHOOK_SECRET,
)
from app.database.connection import get_db


def create_checkout_session(booking_id: int, idempotency_key: Optional[str], user: dict) -> dict:
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT b.*, s.name AS service_name,
                       u.email AS customer_email, u.full_name AS customer_name
                FROM bookings b
                JOIN services s ON b.service_id = s.id
                JOIN users u ON b.customer_id = u.id
                WHERE b.id = %s
                """,
                (booking_id,),
            )
            booking = cursor.fetchone()
            if not booking:
                raise HTTPException(status_code=404, detail="Booking not found")
            if user["role"] == "customer" and booking["customer_id"] != user["id"]:
                raise HTTPException(status_code=403, detail="You can only pay for your own bookings")
            if booking["payment_status"] == "PAID":
                return {
                    "message": "Booking is already paid",
                    "payment_status": "PAID",
                    "booking_id": booking["id"],
                    "checkout_url": f"/static/success.html?booking_id={booking['id']}&already_paid=true",
                }

            price_pence = int(round(float(booking["total_price_gbp"]) * 100))
            is_mock_stripe = not STRIPE_SECRET_KEY or "mock" in STRIPE_SECRET_KEY.lower()
            checkout_url = None
            session_id = None

            if not is_mock_stripe:
                try:
                    success_url = STRIPE_SUCCESS_URL
                    if "{CHECKOUT_SESSION_ID}" in success_url:
                        success_url += f"&booking_id={booking['id']}"
                    else:
                        success_url += f"?session_id={{CHECKOUT_SESSION_ID}}&booking_id={booking['id']}"
                    cancel_url = f"{STRIPE_CANCEL_URL}?booking_id={booking['id']}"
                    session = stripe.checkout.Session.create(
                        payment_method_types=["card"],
                        customer_email=booking["customer_email"],
                        line_items=[{
                            "price_data": {
                                "currency": "gbp",
                                "unit_amount": price_pence,
                                "product_data": {
                                    "name": f"CleanLondon: {booking['service_name']}",
                                    "description": f"Ref: {booking['reference_code']} - {booking['property_type']} at {booking['postcode']}",
                                    "images": ["https://images.unsplash.com/photo-1581578731548-c64695cc6952?w=300"],
                                },
                            },
                            "quantity": 1,
                        }],
                        mode="payment",
                        client_reference_id=str(booking["id"]),
                        metadata={
                            "booking_id": str(booking["id"]),
                            "reference_code": booking["reference_code"],
                            "customer_id": str(booking["customer_id"]),
                        },
                        success_url=success_url,
                        cancel_url=cancel_url,
                        idempotency_key=idempotency_key,
                    )
                    checkout_url = session.url
                    session_id = session.id
                except Exception:
                    is_mock_stripe = True

            if is_mock_stripe:
                stable_key = idempotency_key or f"booking-{booking['id']}"
                stable_suffix = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:12]
                session_id = f"cs_test_mock_{booking['id']}_{stable_suffix}"
                checkout_url = f"/static/success.html?session_id={session_id}&booking_id={booking['id']}&mock=true"

            cursor.execute(
                "UPDATE bookings SET stripe_session_id = %s WHERE id = %s",
                (session_id, booking["id"]),
            )
            return {
                "message": "Stripe Checkout session created successfully",
                "checkout_url": checkout_url,
                "session_id": session_id,
                "booking_id": booking["id"],
                "total_price_gbp": float(booking["total_price_gbp"]),
                "currency": "GBP (£)",
                "is_mock": is_mock_stripe,
            }


def parse_stripe_webhook(payload: bytes, sig_header: Optional[str]) -> dict:
    if IS_PRODUCTION:
        if not sig_header:
            raise HTTPException(status_code=400, detail="Missing stripe-signature header")
        if not STRIPE_WEBHOOK_SECRET or "mock" in STRIPE_WEBHOOK_SECRET.lower():
            raise HTTPException(status_code=500, detail="Stripe webhook secret is not configured for production")
        try:
            return stripe.Webhook.construct_event(
                payload=payload,
                sig_header=sig_header,
                secret=STRIPE_WEBHOOK_SECRET,
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid Stripe webhook payload")
        except stripe.error.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature")

    if sig_header and STRIPE_WEBHOOK_SECRET and "mock" not in STRIPE_WEBHOOK_SECRET.lower():
        try:
            return stripe.Webhook.construct_event(
                payload=payload,
                sig_header=sig_header,
                secret=STRIPE_WEBHOOK_SECRET,
            )
        except (ValueError, stripe.error.SignatureVerificationError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid webhook signature: {str(exc)}")
    try:
        return json.loads(payload.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Could not parse mock JSON payload")


def fulfill_stripe_payment(booking_id: int, session_id: Optional[str], payment_intent_id: str) -> dict:
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, customer_id, status, payment_status FROM bookings WHERE id = %s",
                (booking_id,),
            )
            booking = cursor.fetchone()
            if not booking:
                return {"status": "ignored", "reason": "Booking not found"}
            cursor.execute(
                """
                UPDATE bookings
                SET payment_status = 'PAID',
                    stripe_session_id = COALESCE(stripe_session_id, %s),
                    stripe_payment_intent_id = %s
                WHERE id = %s
                """,
                (session_id, payment_intent_id, booking_id),
            )
            cursor.execute(
                """
                INSERT INTO booking_status_logs
                    (booking_id, changed_by_user_id, previous_status, new_status, notes)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    booking_id,
                    booking["customer_id"],
                    booking["status"],
                    booking["status"],
                    f"Payment fulfilled via Stripe ({payment_intent_id})",
                ),
            )
            return {
                "status": "success",
                "booking_id": booking_id,
                "payment_status": "PAID",
                "payment_intent": payment_intent_id,
            }


def verify_payment_session(session_id: str, booking_id: Optional[int] = None) -> dict:
    with get_db() as conn:
        with conn.cursor() as cursor:
            query = """
                SELECT b.*, s.name AS service_name,
                       u.full_name AS customer_name, u.email AS customer_email
                FROM bookings b
                JOIN services s ON b.service_id = s.id
                JOIN users u ON b.customer_id = u.id
                WHERE b.stripe_session_id = %s
            """
            params = [session_id]
            if booking_id:
                query += " AND b.id = %s"
                params.append(booking_id)
            cursor.execute(query, tuple(params))
            booking = cursor.fetchone()
            if not booking:
                raise HTTPException(status_code=404, detail="Payment session or booking not found")
            if MOCK_MODE and booking["payment_status"] != "PAID":
                mock_pi = f"pi_mock_{random.randint(100000, 999999)}"
                cursor.execute(
                    """
                    UPDATE bookings
                    SET payment_status = 'PAID',
                        stripe_session_id = %s,
                        stripe_payment_intent_id = COALESCE(stripe_payment_intent_id, %s)
                    WHERE id = %s
                    """,
                    (session_id, mock_pi, booking["id"]),
                )
                booking["payment_status"] = "PAID"
                booking["stripe_payment_intent_id"] = mock_pi
            return {
                "booking_id": booking["id"],
                "reference_code": booking["reference_code"],
                "service_name": booking["service_name"],
                "customer_name": booking["customer_name"],
                "postcode": booking["postcode"],
                "scheduled_date": str(booking["scheduled_date"]),
                "scheduled_time_slot": booking["scheduled_time_slot"],
                "total_price_gbp": float(booking["total_price_gbp"]),
                "payment_status": booking["payment_status"],
                "session_id": session_id,
                "payment_intent_id": booking["stripe_payment_intent_id"],
            }
