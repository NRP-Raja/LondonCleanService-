"""CleanLondon Manager Service — business logic for manager/dashboard operations."""

import datetime
import json
import random
import re
from typing import Optional, List

from fastapi import HTTPException

from app.core.config import STRIPE_SECRET_KEY
from app.database.connection import get_db, get_transaction
from app.utils.notifications import queue_notification
from app.utils.postcode import resolve_postcode_coords, haversine_distance_miles
from app.services.staff import check_cleaner_schedule_conflict, check_staff_availability


def log_activity(cursor, user: dict, action: str, entity_type: str, entity_id, before=None, after=None) -> None:
    cursor.execute(
        """
        INSERT INTO activity_audit_log
            (actor_id, actor_role, action, entity_type, entity_id, before_json, after_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            user.get("id"),
            user.get("role"),
            action,
            entity_type,
            str(entity_id),
            json.dumps(before, default=str) if before is not None else None,
            json.dumps(after, default=str) if after is not None else None,
        ),
    )


# ---------------------------------------------------------------------------
# Manager Dashboard Stats
# ---------------------------------------------------------------------------
def get_dashboard_stats() -> dict:
    """Return live KPIs for manager dispatch console."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT COALESCE(SUM(total_price_gbp), 0) AS daily_revenue
                FROM bookings
                WHERE scheduled_date = CURRENT_DATE() AND status != 'CANCELLED'
            """)
            daily_rev = float(cursor.fetchone()["daily_revenue"])
            cursor.execute("""
                SELECT COALESCE(SUM(total_price_gbp), 0) AS total_revenue
                FROM bookings
                WHERE status != 'CANCELLED'
            """)
            total_booking_value = float(cursor.fetchone()["total_revenue"])
            cursor.execute("""
                SELECT
                    COALESCE(SUM(CASE WHEN scheduled_date = CURRENT_DATE() AND payment_status = 'PAID'
                                      THEN total_price_gbp ELSE 0 END), 0) AS collected_today,
                    COALESCE(SUM(CASE WHEN scheduled_date >= DATE_FORMAT(CURRENT_DATE(), '%Y-%m-01')
                                      AND scheduled_date < DATE_ADD(DATE_FORMAT(CURRENT_DATE(), '%Y-%m-01'), INTERVAL 1 MONTH)
                                      AND payment_status = 'PAID'
                                      THEN total_price_gbp ELSE 0 END), 0) AS collected_month,
                    COALESCE(SUM(CASE WHEN payment_status IN ('PENDING', 'AUTHORIZED')
                                      AND status != 'CANCELLED'
                                      THEN total_price_gbp ELSE 0 END), 0) AS unpaid_amount
                FROM bookings
            """)
            payment_totals = cursor.fetchone()
            cursor.execute("""
                SELECT COUNT(*) AS completed_today
                FROM bookings
                WHERE scheduled_date = CURRENT_DATE() AND status = 'COMPLETED'
            """)
            completed_today = cursor.fetchone()["completed_today"] or 0
            cursor.execute("""
                SELECT
                    COUNT(*) AS total_bookings,
                    SUM(CASE WHEN scheduled_date = CURRENT_DATE() THEN 1 ELSE 0 END) AS bookings_today,
                    SUM(CASE WHEN status = 'SCHEDULED' THEN 1 ELSE 0 END) AS scheduled_count,
                    SUM(CASE WHEN status = 'EN_ROUTE' THEN 1 ELSE 0 END) AS en_route_count,
                    SUM(CASE WHEN status = 'IN_PROGRESS' THEN 1 ELSE 0 END) AS in_progress_count,
                    SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed_count,
                    SUM(CASE WHEN staff_id IS NULL AND status = 'SCHEDULED' THEN 1 ELSE 0 END) AS unassigned_count
                FROM bookings
            """)
            counts = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) AS total_staff FROM users WHERE role_id = 2")
            total_cleaners = cursor.fetchone()["total_staff"] or 1
            cursor.execute("""
                SELECT COUNT(DISTINCT staff_id) AS active_cleaners
                FROM bookings
                WHERE scheduled_date = CURRENT_DATE() AND status IN ('SCHEDULED', 'EN_ROUTE', 'IN_PROGRESS')
            """)
            active_cleaners = cursor.fetchone()["active_cleaners"] or 0
            utilization_rate = round((active_cleaners / total_cleaners) * 100, 1)
            return {
                "kpis": {
                    "daily_revenue_gbp": round(daily_rev, 2),
                    "total_revenue_gbp": round(total_booking_value, 2),
                    "collected_today_gbp": float(payment_totals["collected_today"] or 0),
                    "collected_month_gbp": float(payment_totals["collected_month"] or 0),
                    "unpaid_amount_gbp": float(payment_totals["unpaid_amount"] or 0),
                    "overdue_amount_gbp": None,
                    "bookings_today": counts["bookings_today"] or 0,
                    "completed_today": completed_today,
                    "staff_utilization_pct": utilization_rate,
                    "total_cleaners": total_cleaners,
                    "active_cleaners_today": active_cleaners,
                    "unassigned_jobs": counts["unassigned_count"],
                },
                "status_breakdown": counts,
            }


# ---------------------------------------------------------------------------
# Get All Bookings (Manager)
# ---------------------------------------------------------------------------
def get_all_bookings(status_filter: Optional[str] = None) -> dict:
    """Return all bookings for manager dispatch console with optional status filter."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            query = """
                SELECT b.*, s.name as service_name,
                       c.full_name as customer_name, c.email as customer_email, c.phone as customer_phone,
                       cl.full_name as staff_name, cl.phone as staff_phone
                FROM bookings b
                JOIN services s ON b.service_id = s.id
                JOIN users c ON b.customer_id = c.id
                LEFT JOIN users cl ON b.staff_id = cl.id
            """
            params = []
            if status_filter and status_filter.upper() != "ALL":
                query += " WHERE b.status = %s"
                params.append(status_filter.upper())
            query += " ORDER BY b.scheduled_date DESC, b.id DESC"
            cursor.execute(query, tuple(params))
            return {"bookings": cursor.fetchall()}


# ---------------------------------------------------------------------------
# Auto-Match Nearest Cleaner
# ---------------------------------------------------------------------------
def auto_match_booking(booking_id: int) -> dict:
    """Auto-match the nearest available cleaner based on postcode proximity and TfL travel buffer."""
    with get_transaction() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM bookings WHERE id = %s", (booking_id,))
            booking = cursor.fetchone()
            if not booking:
                raise HTTPException(status_code=404, detail="Booking not found")
            if booking["staff_id"] is not None:
                raise HTTPException(
                    status_code=400, detail="Booking already has a cleaner assigned"
                )
            if booking["status"] != "SCHEDULED":
                raise HTTPException(
                    status_code=400,
                    detail=f"Booking status is '{booking['status']}', must be 'SCHEDULED'",
                )

            target_date = booking["scheduled_date"]
            target_time_slot = booking["scheduled_time_slot"]
            target_postcode = booking["postcode"]

            # Get all active staff with profiles
            cursor.execute(
                """
                SELECT u.id, u.full_name, sp.base_postcode, sp.service_radius_miles
                FROM users u
                JOIN staff_profiles sp ON u.id = sp.user_id
                WHERE u.role_id = 2 AND u.is_active = TRUE
                """
            )
            staff_members = cursor.fetchall()
            if not staff_members:
                raise HTTPException(status_code=400, detail="No active cleaners available")

            # Calculate distances and check availability/conflicts
            candidates = []
            target_coords = resolve_postcode_coords(target_postcode)[0:2]
            for sm in staff_members:
                sm_id = sm["id"]
                base_postcode = sm["base_postcode"]
                service_radius = float(sm["service_radius_miles"] or 10)

                # Check schedule conflicts (existing jobs, holidays, availability)
                has_conflict, reason = check_cleaner_schedule_conflict(
                    cursor, sm_id, str(target_date), target_time_slot, target_postcode
                )
                if has_conflict:
                    continue

                # Check weekly availability
                has_avail_conflict, avail_reason = check_staff_availability(
                    cursor, sm_id, str(target_date), target_time_slot
                )
                if has_avail_conflict:
                    continue

                # Distance check
                base_coords = resolve_postcode_coords(base_postcode)[0:2]
                distance_miles = haversine_distance_miles(*target_coords, *base_coords)

                if distance_miles > service_radius:
                    continue

                candidates.append((distance_miles, sm_id, sm["full_name"], base_postcode))

            if not candidates:
                raise HTTPException(
                    status_code=400,
                    detail="No available cleaners within service radius for this booking.",
                )

            # Sort by distance (nearest first) and pick the nearest
            candidates.sort(key=lambda x: x[0])
            nearest_distance, nearest_staff_id, nearest_name, nearest_postcode = candidates[0]

            # Assign the cleaner
            cursor.execute(
                "UPDATE bookings SET staff_id = %s WHERE id = %s",
                (nearest_staff_id, booking_id),
            )

            # Audit log
            cursor.execute(
                """
                INSERT INTO booking_status_logs (booking_id, changed_by_user_id, previous_status, new_status, notes)
                VALUES (%s, NULL, %s, %s, %s)
                """,
                (
                    booking_id,
                    booking["status"],
                    booking["status"],
                    f"Auto-matched nearest cleaner: {nearest_name} ({nearest_distance} miles away)",
                ),
            )

            # Notify assigned cleaner
            cursor.execute("SELECT email FROM users WHERE id = %s", (nearest_staff_id,))
            cleaner_email = cursor.fetchone()
            if cleaner_email:
                queue_notification(
                    cursor,
                    nearest_staff_id,
                    cleaner_email["email"],
                    f"New job assigned: {booking['reference_code']}",
                    f"You have been assigned a new cleaning job on {booking['scheduled_date']} "
                    f"({booking['scheduled_time_slot']}) at {booking['address_line1']}, "
                    f"{booking['postcode']}. Distance from your base: {nearest_distance} miles.",
                )

            return {
                "message": "Cleaner auto-matched successfully",
                "booking_id": booking_id,
                "reference_code": booking["reference_code"],
                "assigned_staff_id": nearest_staff_id,
                "assigned_cleaner_name": nearest_name,
                "distance_miles": round(nearest_distance, 1),
            }


# ---------------------------------------------------------------------------
# Get All Staff (Manager Dispatch Console)
# ---------------------------------------------------------------------------
def get_all_staff(scheduled_date: Optional[str] = None, postcode: Optional[str] = None) -> dict:
    """Return all staff cleaners with profiles, optionally filtered by date and postcode for dispatch."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.id, u.full_name, u.email, u.phone, u.avatar_url,
                       sp.base_postcode, sp.service_radius_miles, sp.rating_avg, sp.rating_count,
                       sp.is_available, sp.verified_dbs, sp.right_to_work_verified,
                       sp.vetting_status, sp.dbs_document_ref, sp.right_to_work_document_ref,
                       COALESCE(j.job_count, 0) AS jobs_today
                FROM users u
                JOIN staff_profiles sp ON u.id = sp.user_id
                LEFT JOIN (
                    SELECT staff_id, COUNT(*) AS job_count
                    FROM bookings
                    WHERE scheduled_date = COALESCE(%s, CURRENT_DATE())
                      AND status NOT IN ('CANCELLED', 'COMPLETED')
                    GROUP BY staff_id
                ) j ON j.staff_id = u.id
                WHERE u.role_id = 2
                """,
                (scheduled_date,),
            )
            staff = cursor.fetchall()
            target_coords = resolve_postcode_coords(postcode)[0:2] if postcode else None
            for cleaner in staff:
                if target_coords:
                    base_coords = resolve_postcode_coords(cleaner["base_postcode"])[0:2]
                    cleaner["distance_miles"] = round(
                        haversine_distance_miles(*target_coords, *base_coords), 1
                    )
                else:
                    cleaner["distance_miles"] = None
            return {"staff": staff}


# ---------------------------------------------------------------------------
# Assign Staff to Booking (Manager)
# ---------------------------------------------------------------------------
def assign_staff_to_booking(booking_id: int, staff_id: int) -> dict:
    """Manually assign a staff member to a booking."""
    with get_transaction() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM bookings WHERE id = %s", (booking_id,))
            booking = cursor.fetchone()
            if not booking:
                raise HTTPException(status_code=404, detail="Booking not found")
            if booking["status"] != "SCHEDULED":
                raise HTTPException(
                    status_code=400,
                    detail=f"Booking status is '{booking['status']}', must be 'SCHEDULED'",
                )

            cursor.execute(
                "SELECT id FROM users WHERE id = %s AND role_id = 2 AND is_active = TRUE",
                (staff_id,),
            )
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Active cleaner staff not found")

            # Check cleaner schedule conflict
            target_date = booking["scheduled_date"]
            target_time_slot = booking["scheduled_time_slot"]
            target_postcode = booking["postcode"]
            has_conflict, reason = check_cleaner_schedule_conflict(
                cursor, staff_id, str(target_date), target_time_slot, target_postcode,
                exclude_booking_id=booking_id,
            )
            if has_conflict:
                raise HTTPException(status_code=400, detail=reason)
            has_avail_conflict, avail_reason = check_staff_availability(
                cursor, staff_id, str(target_date), target_time_slot
            )
            if has_avail_conflict:
                raise HTTPException(status_code=400, detail=avail_reason)

            cursor.execute(
                "UPDATE bookings SET staff_id = %s WHERE id = %s",
                (staff_id, booking_id),
            )

            cursor.execute(
                """
                INSERT INTO booking_status_logs (booking_id, changed_by_user_id, previous_status, new_status, notes)
                VALUES (%s, NULL, %s, %s, %s)
                """,
                (
                    booking_id,
                    booking["status"],
                    booking["status"],
                    f"Manually assigned staff ID {staff_id}",
                ),
            )

            cursor.execute("SELECT email, full_name FROM users WHERE id = %s", (staff_id,))
            cleaner = cursor.fetchone()
            if cleaner:
                queue_notification(
                    cursor,
                    staff_id,
                    cleaner["email"],
                    f"New job assigned: {booking['reference_code']}",
                    f"You have been manually assigned a cleaning job on {booking['scheduled_date']} "
                    f"({booking['scheduled_time_slot']}) at {booking['address_line1']}.",
                )

            return {
                "message": "Staff assigned successfully",
                "booking_id": booking_id,
                "assigned_staff_id": staff_id,
                "assigned_staff_name": cleaner["full_name"] if cleaner else None,
            }


# ---------------------------------------------------------------------------
# Create Staff Shift (Manager)
# ---------------------------------------------------------------------------
def update_staff_vetting(
    staff_id: int,
    vetting_status: str,
    verified_dbs: bool,
    right_to_work_verified: bool,
    dbs_document_ref: Optional[str],
    right_to_work_document_ref: Optional[str],
) -> dict:
    """Update cleaner vetting and account activation state."""
    approved = (
        vetting_status == "APPROVED"
        and verified_dbs
        and right_to_work_verified
    )
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM users WHERE id = %s AND role_id = 2",
                (staff_id,),
            )
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Cleaner staff not found")
            cursor.execute(
                """
                UPDATE staff_profiles
                SET verified_dbs = %s,
                    right_to_work_verified = %s,
                    vetting_status = %s,
                    dbs_document_ref = %s,
                    right_to_work_document_ref = %s,
                    vetted_at = CASE WHEN %s = 'APPROVED' THEN NOW() ELSE NULL END
                WHERE user_id = %s
                """,
                (
                    verified_dbs,
                    right_to_work_verified,
                    vetting_status,
                    dbs_document_ref,
                    right_to_work_document_ref,
                    vetting_status,
                    staff_id,
                ),
            )
            cursor.execute(
                "UPDATE users SET is_active = %s WHERE id = %s",
                (approved, staff_id),
            )
            return {
                "message": "Cleaner vetting updated",
                "staff_id": staff_id,
                "vetting_status": vetting_status,
                "is_active": approved,
            }


def create_shift(staff_id: int, shift_date: str, start_time: str, end_time: str, notes: Optional[str]) -> dict:
    """Create a shift assignment for a staff member."""
    try:
        datetime.date.fromisoformat(shift_date)
        datetime.datetime.strptime(start_time, "%H:%M")
        datetime.datetime.strptime(end_time, "%H:%M")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid date or time format") from exc

    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM users WHERE id = %s AND role_id = 2 AND is_active = TRUE",
                (staff_id,),
            )
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Active cleaner staff not found")

            cursor.execute(
                """
                INSERT INTO staff_shifts (staff_id, shift_date, start_time, end_time, notes)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (staff_id, shift_date, start_time, end_time, notes),
            )
            shift_id = cursor.lastrowid

            return {
                "message": "Shift created successfully",
                "shift_id": shift_id,
                "staff_id": staff_id,
                "shift_date": shift_date,
                "start_time": start_time,
                "end_time": end_time,
            }


# ---------------------------------------------------------------------------
# Business Settings (Manager)
# ---------------------------------------------------------------------------
def get_settings() -> dict:
    """Return all business settings."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT setting_key, setting_value FROM business_settings")
            rows = cursor.fetchall()
            return {"settings": {row["setting_key"]: row["setting_value"] for row in rows}}


def update_setting(setting_key: str, value: str) -> dict:
    """Update a single business setting."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO business_settings (setting_key, setting_value, updated_at)
                VALUES (%s, %s, NOW())
                ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value), updated_at = NOW()
                """,
                (setting_key, value),
            )
            cursor.execute(
                """
                INSERT INTO audit_log (user_id, action, details, created_at)
                VALUES (NULL, 'setting_updated', %s, NOW())
                """,
                (f"{setting_key}: {value}",),
            )
            return {"message": "Setting updated", "setting_key": setting_key}


def list_payment_records() -> dict:
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT p.*, b.reference_code
                FROM payment_records p
                JOIN bookings b ON b.id = p.booking_id
                ORDER BY p.recorded_at DESC
                """
            )
            return {"payments": cursor.fetchall()}


def record_payment(booking_id: int, amount_gbp: float, method: str, reference: Optional[str], user: dict) -> dict:
    with get_transaction() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM bookings WHERE id = %s FOR UPDATE", (booking_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Booking not found")
            cursor.execute(
                """
                INSERT INTO payment_records
                    (booking_id, amount_gbp, method, status, reference, recorded_by)
                VALUES (%s, %s, %s, 'RECORDED', %s, %s)
                """,
                (booking_id, amount_gbp, method, reference, user["id"]),
            )
            record_id = cursor.lastrowid
            log_activity(
                cursor,
                user,
                "payment_recorded",
                "payment",
                record_id,
                after={"booking_id": booking_id, "amount_gbp": amount_gbp, "method": method},
            )
            return {"message": "Payment recorded", "payment_id": record_id}


def verify_payment(payment_id: int, user: dict) -> dict:
    with get_transaction() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM payment_records WHERE id = %s FOR UPDATE", (payment_id,))
            payment = cursor.fetchone()
            if not payment:
                raise HTTPException(status_code=404, detail="Payment not found")
            cursor.execute(
                """
                UPDATE payment_records
                SET status = 'VERIFIED', verified_by = %s, verified_at = NOW()
                WHERE id = %s
                """,
                (user["id"], payment_id),
            )
            log_activity(cursor, user, "payment_verified", "payment", payment_id, before=payment, after={"status": "VERIFIED"})
            return {"message": "Payment verified", "payment_id": payment_id}


def list_support_cases() -> dict:
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT sc.*, c.full_name AS customer_name, cl.full_name AS assigned_name
                FROM support_cases sc
                JOIN users c ON c.id = sc.customer_id
                LEFT JOIN users cl ON cl.id = sc.assigned_to
                ORDER BY sc.created_at DESC
                """
            )
            return {"cases": cursor.fetchall()}


def create_support_case(payload, user: dict) -> dict:
    with get_transaction() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO support_cases (booking_id, customer_id, subject, description)
                VALUES (%s, %s, %s, %s)
                """,
                (payload.booking_id, payload.customer_id, payload.subject, payload.description),
            )
            case_id = cursor.lastrowid
            log_activity(
                cursor,
                user,
                "support_case_created",
                "support_case",
                case_id,
                after={"customer_id": payload.customer_id, "subject": payload.subject},
            )
            return {"message": "Support case created", "case_id": case_id}


def update_support_case(case_id: int, payload, user: dict) -> dict:
    with get_transaction() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM support_cases WHERE id = %s FOR UPDATE", (case_id,))
            before = cursor.fetchone()
            if not before:
                raise HTTPException(status_code=404, detail="Support case not found")
            cursor.execute(
                """
                UPDATE support_cases
                SET status = %s, assigned_to = %s, outcome = %s, follow_up_at = %s
                WHERE id = %s
                """,
                (payload.status, payload.assigned_to, payload.outcome, payload.follow_up_at, case_id),
            )
            log_activity(
                cursor,
                user,
                "support_case_updated",
                "support_case",
                case_id,
                before=before,
                after={"status": payload.status, "assigned_to": payload.assigned_to, "outcome": payload.outcome},
            )
            return {"message": "Support case updated", "case_id": case_id}


def list_manager_notifications(user: dict) -> dict:
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, subject, body, status, is_read, priority, deep_link, created_at
                FROM notification_outbox
                WHERE recipient_user_id = %s OR recipient_user_id IS NULL
                ORDER BY created_at DESC LIMIT 100
                """,
                (user["id"],),
            )
            notifications = cursor.fetchall()
            unread = sum(1 for item in notifications if not item["is_read"])
            return {"notifications": notifications, "unread_count": unread}


def mark_notification_read(notification_id: int, user: dict) -> dict:
    with get_transaction() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE notification_outbox SET is_read = TRUE
                WHERE id = %s AND (recipient_user_id = %s OR recipient_user_id IS NULL)
                """,
                (notification_id, user["id"]),
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Notification not found")
            log_activity(cursor, user, "notification_read", "notification", notification_id)
            return {"message": "Notification marked as read"}


def list_audit_log() -> dict:
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM activity_audit_log ORDER BY created_at DESC LIMIT 200")
            return {"audit": cursor.fetchall()}


def list_shifts() -> dict:
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT ss.*, u.full_name AS staff_name
                FROM staff_shifts ss
                JOIN users u ON u.id = ss.staff_id
                ORDER BY ss.shift_date, ss.start_time
                """
            )
            return {"shifts": cursor.fetchall()}


def create_admin_shift(payload, user: dict) -> dict:
    with get_transaction() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO staff_shifts
                    (staff_id, shift_date, start_time, end_time, created_by)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (payload.staff_id, payload.shift_date, payload.start_time, payload.end_time, user["id"]),
            )
            shift_id = cursor.lastrowid
            log_activity(
                cursor,
                user,
                "shift_created",
                "shift",
                shift_id,
                after={"staff_id": payload.staff_id, "shift_date": payload.shift_date, "start_time": payload.start_time, "end_time": payload.end_time},
            )
            return {"message": "Shift created", "shift_id": shift_id}


def list_time_off() -> dict:
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT t.*, u.full_name AS staff_name
                FROM staff_time_off t
                JOIN users u ON u.id = t.staff_id
                ORDER BY t.created_at DESC
                """
            )
            return {"time_off": cursor.fetchall()}


def review_time_off(time_off_id: int, payload, user: dict) -> dict:
    with get_transaction() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM staff_time_off WHERE id = %s FOR UPDATE", (time_off_id,))
            before = cursor.fetchone()
            if not before:
                raise HTTPException(status_code=404, detail="Time-off request not found")
            cursor.execute(
                "UPDATE staff_time_off SET status = %s, reviewed_by = %s, reviewed_at = NOW() WHERE id = %s",
                (payload.status, user["id"], time_off_id),
            )
            log_activity(cursor, user, "time_off_reviewed", "time_off", time_off_id, before=before, after={"status": payload.status})
            return {"message": "Time-off request reviewed", "time_off_id": time_off_id}


def update_manager_setting(setting_key: str, payload: dict, user: dict) -> dict:
    if not setting_key or len(setting_key) > 100:
        raise HTTPException(status_code=400, detail="Invalid setting key")
    if not payload:
        raise HTTPException(status_code=400, detail="Setting value is required")
    with get_transaction() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO business_settings (setting_key, setting_value, updated_by)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value),
                                        updated_by = VALUES(updated_by)
                """,
                (setting_key, json.dumps(payload), user["id"]),
            )
            log_activity(cursor, user, "setting_updated", "business_setting", setting_key, after=payload)
            return {"message": "Setting updated", "setting_key": setting_key}


def manager_report_summary(start_date: str, end_date: str) -> dict:
    try:
        datetime.date.fromisoformat(start_date)
        datetime.date.fromisoformat(end_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date range")
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="End date must not precede start date")
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COUNT(*) AS booking_count,
                    COALESCE(SUM(CASE WHEN status != 'CANCELLED' THEN total_price_gbp ELSE 0 END), 0) AS booking_value,
                    COALESCE(SUM(CASE WHEN payment_status = 'PAID' THEN total_price_gbp ELSE 0 END), 0) AS collected_payments,
                    COALESCE(SUM(CASE WHEN payment_status IN ('PENDING','AUTHORIZED') AND status != 'CANCELLED' THEN total_price_gbp ELSE 0 END), 0) AS outstanding
                FROM bookings
                WHERE scheduled_date BETWEEN %s AND %s
                """,
                (start_date, end_date),
            )
            booking_totals = cursor.fetchone()
            cursor.execute(
                "SELECT COALESCE(SUM(amount_gbp), 0) AS expenses FROM expenses WHERE expense_date BETWEEN %s AND %s",
                (start_date, end_date),
            )
            expense_totals = cursor.fetchone()
            return {
                "date_range": {"start": start_date, "end": end_date},
                "booking_count": booking_totals["booking_count"] or 0,
                "booking_value_gbp": float(booking_totals["booking_value"] or 0),
                "collected_payments_gbp": float(booking_totals["collected_payments"] or 0),
                "outstanding_gbp": float(booking_totals["outstanding"] or 0),
                "expenses_gbp": float(expense_totals["expenses"] or 0),
                "profit_gbp": None,
                "profit_note": "Profit is not reported until a complete expense model is verified.",
            }






