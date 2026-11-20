"""CleanLondon Staff Routes — HTTP endpoint definitions for staff/cleaner workflow."""

from fastapi import APIRouter, Body, Depends
from typing import Optional, List

from app.core.dependencies import require_role
from app.schemas.staff import WeeklyAvailabilitySchema, HolidaySchema, StaffStatusUpdateSchema
from app.services.staff import (
    get_staff_jobs,
    update_staff_job_status,
    get_staff_schedule,
    update_staff_schedule,
    add_staff_holiday,
    remove_staff_holiday,
    get_staff_earnings,
)

router = APIRouter(prefix="/api/staff", tags=["Staff"])


@router.get("/jobs")
def list_staff_jobs(user: dict = Depends(require_role(["staff"]))):
    """List all jobs assigned to the authenticated staff member."""
    return get_staff_jobs(user["id"])


@router.patch("/jobs/{booking_id}/status")
def update_job_status_route(
    booking_id: int,
    payload: StaffStatusUpdateSchema = Body(...),
    user: dict = Depends(require_role(["staff", "manager"])),
):
    """Update a booking's status (staff/manager only)."""
    return update_staff_job_status(
        booking_id, payload.status, payload.notes, user["id"], user["role"]
    )


@router.get("/schedule")
def get_staff_schedule_route(user: dict = Depends(require_role(["staff"]))):
    """Get weekly availability and holidays for the authenticated staff member."""
    return get_staff_schedule(user["id"])


@router.put("/schedule")
def update_staff_schedule_route(
    schedule: List[WeeklyAvailabilitySchema] = Body(...),
    user: dict = Depends(require_role(["staff"])),
):
    """Update weekly availability for the authenticated staff member."""
    return update_staff_schedule(schedule, user["id"])


@router.post("/holidays")
def add_staff_holiday_route(
    payload: HolidaySchema = Body(...),
    user: dict = Depends(require_role(["staff"])),
):
    """Add a holiday for the authenticated staff member."""
    return add_staff_holiday(payload.holiday_date, payload.reason, user["id"])


@router.delete("/holidays/{holiday_date}")
def remove_staff_holiday_route(
    holiday_date: str,
    user: dict = Depends(require_role(["staff"])),
):
    """Remove a holiday for the authenticated staff member."""
    return remove_staff_holiday(holiday_date, user["id"])


@router.get("/earnings")
def get_staff_earnings_route(user: dict = Depends(require_role(["staff"]))):
    """Get earnings summary for completed jobs."""
    return get_staff_earnings(user["id"])

