"""CleanLondon Manager and Dispatch Routes."""

from typing import Optional

from fastapi import APIRouter, Depends

from app.core.dependencies import require_role
from app.schemas.manager import AssignStaffSchema, VettingSchema
from app.services.manager import (
    assign_staff_to_booking,
    auto_match_booking,
    get_all_bookings,
    get_all_staff,
    get_dashboard_stats,
    update_staff_vetting,
)

router = APIRouter(prefix="/api/manager", tags=["Manager"])


@router.get("/dashboard-stats")
def dashboard_stats(user: dict = Depends(require_role(["manager"]))):
    return get_dashboard_stats()


@router.get("/bookings")
def manager_bookings(
    status_filter: Optional[str] = None,
    user: dict = Depends(require_role(["manager"])),
):
    return get_all_bookings(status_filter)


@router.get("/staff")
def manager_staff(
    scheduled_date: Optional[str] = None,
    postcode: Optional[str] = None,
    user: dict = Depends(require_role(["manager"])),
):
    return get_all_staff(scheduled_date, postcode)


@router.patch("/staff/{staff_id}/vetting")
def manager_staff_vetting(
    staff_id: int,
    payload: VettingSchema,
    user: dict = Depends(require_role(["manager"])),
):
    return update_staff_vetting(
        staff_id,
        payload.vetting_status,
        payload.verified_dbs,
        payload.right_to_work_verified,
        payload.dbs_document_ref,
        payload.right_to_work_document_ref,
    )


@router.post("/bookings/{booking_id}/assign")
def manager_assign_booking(
    booking_id: int,
    payload: AssignStaffSchema,
    user: dict = Depends(require_role(["manager"])),
):
    return assign_staff_to_booking(booking_id, payload.staff_id)


@router.post("/bookings/{booking_id}/reassign")
def manager_reassign_booking(
    booking_id: int,
    payload: AssignStaffSchema,
    user: dict = Depends(require_role(["manager"])),
):
    return assign_staff_to_booking(booking_id, payload.staff_id)


@router.post("/bookings/{booking_id}/auto-match")
def manager_auto_match(
    booking_id: int,
    user: dict = Depends(require_role(["manager"])),
):
    result = auto_match_booking(booking_id)
    return {
        "message": result["message"],
        "booking_id": result["booking_id"],
        "reference_code": result["reference_code"],
        "cleaner_id": result["assigned_staff_id"],
        "cleaner_name": result["assigned_cleaner_name"],
        "distance_miles": result["distance_miles"],
        "rating": None,
    }
