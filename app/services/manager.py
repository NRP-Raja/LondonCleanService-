"""CleanLondon Manager Service — business logic for manager/dashboard operations."""

import datetime
import random
import re
from typing import Optional, List

from fastapi import HTTPException

from app.core.config import STRIPE_SECRET_KEY
from app.database.connection import get_db, get_transaction
from app.utils.notifications import queue_notification
from app.utils.postcode import resolve_postcode_coords, haversine_distance_miles
from app.services.staff import check_cleaner_schedule_conflict, check_staff_availability


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






