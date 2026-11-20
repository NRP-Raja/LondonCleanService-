"""CleanLondon Staff/Cleaner Service — business logic for staff/cleaner workflow."""

import datetime
import re
from typing import Optional, Tuple, List

from fastapi import HTTPException

from app.core.config import STRIPE_SECRET_KEY
from app.database.connection import get_db
from app.utils.encryption import mask_access_notes_for_staff
from app.utils.postcode import (
    parse_time_slot_minutes,
    format_minutes_to_time,
    calculate_tfl_travel_buffer_minutes,
)
from app.utils.notifications import queue_notification
from app.schemas.staff import WeeklyAvailabilitySchema, HolidaySchema


# ---------------------------------------------------------------------------
# Get Staff Jobs
# ---------------------------------------------------------------------------
def get_staff_jobs(user_id: int) -> dict:
    """Return all jobs assigned to a staff member, with GDPR-compliant access-code masking."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT b.*, s.name as service_name, c.full_name as customer_name, c.phone as customer_phone
                FROM bookings b
                JOIN services s ON b.service_id = s.id
                JOIN users c ON b.customer_id = c.id
                WHERE b.staff_id = %s
                ORDER BY b.scheduled_date ASC, b.id ASC
                """,
                (user_id,),
            )
            jobs = cursor.fetchall()
            for job in jobs:
                job["access_notes"] = mask_access_notes_for_staff(
                    job["status"], job.get("access_notes")
                )
            return {"jobs": jobs}


# ---------------------------------------------------------------------------
# Update Staff Job Status
# ---------------------------------------------------------------------------
def update_staff_job_status(
    booking_id: int,
    payload_status: str,
    payload_notes: Optional[str],
    user_id: int,
    user_role: str,
) -> dict:
    """Update booking status with sequential state machine validation."""
    valid_transitions = {
        "PENDING": ["APPROVED", "REJECTED", "CANCELLED"],
        "APPROVED": ["CONFIRMED", "REJECTED", "CANCELLED"],
        "CONFIRMED": ["EN_ROUTE", "CANCELLED"],
        "REJECTED": [],
        "CANCELLED": [],
        "SCHEDULED": ["EN_ROUTE", "CANCELLED"],
        "EN_ROUTE": ["IN_PROGRESS", "CANCELLED"],
        "IN_PROGRESS": ["COMPLETED"],
        "COMPLETED": [],
    }

    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM bookings WHERE id = %s", (booking_id,))
            booking = cursor.fetchone()
            if not booking:
                raise HTTPException(status_code=404, detail="Booking not found")

            # Check ownership if staff
            if user_role == "staff" and booking["staff_id"] != user_id:
                raise HTTPException(
                    status_code=403,
                    detail="You can only update status for jobs assigned to you",
                )

            current_status = booking["status"]
            target_status = payload_status.upper()

            if target_status not in valid_transitions.get(current_status, []):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Invalid transition from '{current_status}' to '{target_status}'. "
                        f"Allowed next: {valid_transitions.get(current_status)}"
                    ),
                )

            # Time Guardrail: Prevent advancing status before scheduled appointment time
            if target_status in ["EN_ROUTE", "IN_PROGRESS", "COMPLETED"]:
                times = re.findall(r"(\d{1,2}:\d{2})", booking["scheduled_time_slot"])
                start_time_str = times[0] if times else "08:00"
                try:
                    scheduled_dt = datetime.datetime.strptime(
                        f"{booking['scheduled_date']} {start_time_str}:00",
                        "%Y-%m-%d %H:%M:%S",
                    )
                except Exception:
                    scheduled_dt = datetime.datetime.combine(
                        booking["scheduled_date"], datetime.time(8, 0)
                    )

                now = datetime.datetime.now()
                hours_until_start = (scheduled_dt - now).total_seconds() / 3600.0

                # 1. Cleaner cannot be EN_ROUTE more than 2 hours before scheduled start
                if target_status == "EN_ROUTE" and hours_until_start > 2.0:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Time Guardrail: Cannot mark job 'EN_ROUTE' prematurely. "
                            f"Appointment is scheduled for {booking['scheduled_date']} at {start_time_str} "
                            f"({round(hours_until_start, 1)} hours away). "
                            f"Cleaners can only go en route within 2 hours of scheduled start."
                        ),
                    )

                # 2. Cleaner cannot be IN_PROGRESS or COMPLETED before scheduled start time
                if target_status in ["IN_PROGRESS", "COMPLETED"] and hours_until_start > 0.25:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Time Guardrail: Cannot mark job '{target_status}' before the scheduled appointment time. "
                            f"Appointment is scheduled for {booking['scheduled_date']} at {start_time_str} "
                            f"({round(hours_until_start, 1)} hours away)."
                        ),
                    )





            # Update status
            payment_status = "PAID" if target_status == "COMPLETED" else booking["payment_status"]
            cursor.execute(
                """
                UPDATE bookings
                SET status = %s, payment_status = %s
                WHERE id = %s
                """,
                (target_status, payment_status, booking_id),
            )

            # Audit log
            cursor.execute(
                """
                INSERT INTO booking_status_logs (booking_id, changed_by_user_id, previous_status, new_status, notes)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    booking_id,
                    user_id,
                    current_status,
                    target_status,
                    payload_notes or f"Status changed to {target_status}",
                ),
            )

            # Notify customer and staff
            cursor.execute(
                """
                SELECT u.id, u.email, u.full_name
                FROM users u
                WHERE u.id IN (%s, %s)
                """,
                (booking["customer_id"], booking["staff_id"] or 0),
            )
            for recipient in cursor.fetchall():
                queue_notification(
                    cursor,
                    recipient["id"],
                    recipient["email"],
                    f"CleanLondon booking {booking_id}: {target_status}",
                    f"Booking {booking_id} is now {target_status.replace('_', ' ')}.",
                )

            return {
                "message": f"Job status updated to {target_status}",
                "booking_id": booking_id,
                "previous_status": current_status,
                "current_status": target_status,
            }


# ---------------------------------------------------------------------------
# Get Staff Schedule
# ---------------------------------------------------------------------------
def get_staff_schedule(user_id: int) -> dict:
    """Return weekly availability and upcoming holidays for a staff member."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT day_of_week, TIME_FORMAT(start_time, '%%H:%%i') AS start_time,
                       TIME_FORMAT(end_time, '%%H:%%i') AS end_time
                FROM staff_weekly_availability
                WHERE staff_id = %s ORDER BY day_of_week
                """,
                (user_id,),
            )
            weekly = cursor.fetchall()
            cursor.execute(
                """
                SELECT DATE_FORMAT(holiday_date, '%%Y-%%m-%%d') AS holiday_date, reason
                FROM staff_holidays
                WHERE staff_id = %s AND holiday_date >= CURRENT_DATE()
                ORDER BY holiday_date
                """,
                (user_id,),
            )
            holidays = cursor.fetchall()
            return {"weekly_availability": weekly, "holidays": holidays}


# ---------------------------------------------------------------------------
# Update Staff Schedule
# ---------------------------------------------------------------------------
def update_staff_schedule(schedule: List[WeeklyAvailabilitySchema], user_id: int) -> dict:
    """Save weekly availability for a staff member."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM staff_weekly_availability WHERE staff_id = %s", (user_id,))
            for shift in schedule:
                try:
                    start = datetime.datetime.strptime(shift.start_time, "%H:%M")
                    end = datetime.datetime.strptime(shift.end_time, "%H:%M")
                except ValueError as exc:
                    raise HTTPException(
                        status_code=422, detail="Shift times must use HH:MM format"
                    ) from exc
                if end <= start:
                    raise HTTPException(
                        status_code=422, detail="Shift end time must be after start time"
                    )
                cursor.execute(
                    """
                    INSERT INTO staff_weekly_availability
                        (staff_id, day_of_week, start_time, end_time)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (user_id, shift.day_of_week, shift.start_time, shift.end_time),
                )
            return {"message": "Weekly availability saved", "days_configured": len(schedule)}


# ---------------------------------------------------------------------------
# Staff Holidays
# ---------------------------------------------------------------------------
def add_staff_holiday(holiday_date: str, reason: Optional[str], user_id: int) -> dict:
    """Add a holiday for a staff member."""
    try:
        datetime.date.fromisoformat(holiday_date)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="Holiday date must use YYYY-MM-DD format"
        ) from exc
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO staff_holidays (staff_id, holiday_date, reason)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE reason = VALUES(reason)
                """,
                (user_id, holiday_date, reason),
            )
            return {"message": "Holiday saved", "holiday_date": holiday_date}


def remove_staff_holiday(holiday_date: str, user_id: int) -> dict:
    """Remove a holiday for a staff member."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM staff_holidays WHERE staff_id = %s AND holiday_date = %s",
                (user_id, holiday_date),
            )
            return {"message": "Holiday removed", "holiday_date": holiday_date}


# ---------------------------------------------------------------------------
# Staff Earnings
# ---------------------------------------------------------------------------
def get_staff_earnings(user_id: int) -> dict:
    """Return earnings summary for completed jobs assigned to a staff member."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, reference_code, scheduled_date, total_price_gbp, duration_hours
                FROM bookings
                WHERE staff_id = %s AND status = 'COMPLETED'
                ORDER BY scheduled_date DESC, id DESC
                """,
                (user_id,),
            )
            jobs = cursor.fetchall()
            gross = sum(float(job["total_price_gbp"]) for job in jobs)
            cleaner_share = round(gross * 0.70, 2)
            today = datetime.date.today().isoformat()
            return {
                "currency": "GBP",
                "completed_jobs": len(jobs),
                "gross_bookings_gbp": round(gross, 2),
                "cleaner_earnings_gbp": cleaner_share,
                "today_earnings_gbp": round(
                    sum(
                        float(job["total_price_gbp"]) * 0.70
                        for job in jobs
                        if str(job["scheduled_date"])[:10] == today
                    ),
                    2,
                ),
                "completed_hours": round(
                    sum(float(job["duration_hours"] or 0) for job in jobs), 2
                ),
                "jobs": jobs,
            }


# ---------------------------------------------------------------------------
# Cleaner Schedule Conflict Check
# ---------------------------------------------------------------------------
def check_cleaner_schedule_conflict(
    cursor,
    cleaner_id: int,
    target_date: str,
    target_time_slot: str,
    target_postcode: str,
    exclude_booking_id: Optional[int] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Checks if a cleaner has an overlapping active booking or insufficient TfL travel buffer
    on the target date. Returns (has_conflict, reason_string).
    """
    target_start, target_end = parse_time_slot_minutes(target_time_slot)

    query = """
        SELECT id, reference_code, scheduled_time_slot, postcode, address_line1, status
        FROM bookings
        WHERE staff_id = %s
          AND scheduled_date = %s
          AND status IN ('SCHEDULED', 'EN_ROUTE', 'IN_PROGRESS')
    """
    params: List = [cleaner_id, str(target_date)]
    if exclude_booking_id:
        query += " AND id != %s"
        params.append(exclude_booking_id)

    cursor.execute(query, tuple(params))
    existing_bookings = cursor.fetchall()

    for eb in existing_bookings:
        eb_start, eb_end = parse_time_slot_minutes(eb["scheduled_time_slot"])

        # 1. Direct Time Overlap Check
        if max(target_start, eb_start) < min(target_end, eb_end):
            return True, (
                f"Schedule Conflict: Cleaner is already assigned to active booking {eb['reference_code']} "
                f"at {eb['address_line1']} ({eb['scheduled_time_slot']}), directly overlapping with requested slot {target_time_slot}."
            )

        # 2. London TfL Travel Buffer Check
        buffer_mins = calculate_tfl_travel_buffer_minutes(target_postcode, eb["postcode"])

        # If target slot starts after existing booking ends
        if target_start >= eb_end:
            earliest_allowed_start = eb_end + buffer_mins
            if target_start < earliest_allowed_start:
                return True, (
                    f"TfL Travel Buffer Conflict: Cleaner finishes booking {eb['reference_code']} at {format_minutes_to_time(eb_end)} "
                    f"in {eb['postcode']} and requires a {buffer_mins}-min TfL travel buffer to reach {target_postcode}. "
                    f"Earliest available start time is {format_minutes_to_time(earliest_allowed_start)}."
                )

        # If target slot ends before existing booking starts
        elif target_end <= eb_start:
            latest_allowed_end = eb_start - buffer_mins
            if target_end > latest_allowed_end:
                return True, (
                    f"TfL Travel Buffer Conflict: Cleaner has booking {eb['reference_code']} starting at {format_minutes_to_time(eb_start)} "
                    f"in {eb['postcode']} and requires a {buffer_mins}-min TfL travel buffer from {target_postcode}. "
                    f"Target booking must conclude by {format_minutes_to_time(latest_allowed_end)}."
                )

    return False, None


# ---------------------------------------------------------------------------
# Staff Availability Check
# ---------------------------------------------------------------------------
def check_staff_availability(
    cursor, staff_id: int, target_date: str, target_time_slot: str
) -> Tuple[bool, Optional[str]]:
    """Apply configured weekly hours and holidays without restricting unconfigured cleaners."""
    try:
        target_day = datetime.date.fromisoformat(str(target_date)).weekday()
    except ValueError:
        return True, "Invalid scheduled date"

    cursor.execute(
        "SELECT reason FROM staff_holidays WHERE staff_id = %s AND holiday_date = %s",
        (staff_id, str(target_date)),
    )
    holiday = cursor.fetchone()
    if holiday:
        return True, f"Cleaner is unavailable on holiday ({holiday['reason'] or 'holiday'})."

    cursor.execute(
        """
        SELECT start_time, end_time
        FROM staff_weekly_availability
        WHERE staff_id = %s AND day_of_week = %s
        """,
        (staff_id, target_day),
    )
    availability = cursor.fetchone()
    if availability:
        slot_start, slot_end = parse_time_slot_minutes(target_time_slot)
        avail_start, _ = parse_time_slot_minutes(availability["start_time"])
        avail_end, _ = parse_time_slot_minutes(availability["end_time"])
        if slot_start < avail_start or slot_end > avail_end:
            return True, (
                f"Cleaner is not available at {target_time_slot} on this day. "
                f"Configured hours: {availability['start_time']} - {availability['end_time']}."
            )

    return False, None





