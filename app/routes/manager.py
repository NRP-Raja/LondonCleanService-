"""CleanLondon Manager and Dispatch Routes."""

from typing import Optional

from fastapi import APIRouter, Depends, Body

from app.core.dependencies import require_role
from app.schemas.manager import (
    AssignStaffSchema,
    PaymentRecordSchema,
    StaffShiftSchema,
    SupportCaseSchema,
    SupportCaseUpdateSchema,
    TimeOffReviewSchema,
    VettingSchema,
)
from app.services.manager import (
    assign_staff_to_booking,
    auto_match_booking,
    create_admin_shift,
    create_support_case,
    list_audit_log,
    list_manager_notifications,
    list_payment_records,
    list_shifts,
    list_support_cases,
    list_time_off,
    manager_report_summary,
    mark_notification_read,
    record_payment,
    review_time_off,
    update_support_case,
    get_all_bookings,
    get_all_staff,
    get_dashboard_stats,
    get_settings,
    update_manager_setting,
    update_staff_vetting,
    verify_payment,
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


@router.get("/payments")
def manager_payments(user: dict = Depends(require_role(["manager"]))):
    return list_payment_records()


@router.post("/payments")
def manager_record_payment(payload: PaymentRecordSchema, user: dict = Depends(require_role(["manager"]))):
    return record_payment(payload.booking_id, payload.amount_gbp, payload.method, payload.reference, user)


@router.patch("/payments/{payment_id}/verify")
def manager_verify_payment(payment_id: int, user: dict = Depends(require_role(["manager"]))):
    return verify_payment(payment_id, user)


@router.get("/support")
def manager_support(user: dict = Depends(require_role(["manager"]))):
    return list_support_cases()


@router.post("/support")
def manager_create_support(payload: SupportCaseSchema, user: dict = Depends(require_role(["manager"]))):
    return create_support_case(payload, user)


@router.patch("/support/{case_id}")
def manager_update_support(case_id: int, payload: SupportCaseUpdateSchema, user: dict = Depends(require_role(["manager"]))):
    return update_support_case(case_id, payload, user)


@router.get("/notifications")
def manager_notifications(user: dict = Depends(require_role(["manager"]))):
    return list_manager_notifications(user)


@router.patch("/notifications/{notification_id}/read")
def manager_mark_notification_read(notification_id: int, user: dict = Depends(require_role(["manager"]))):
    return mark_notification_read(notification_id, user)


@router.get("/audit")
def manager_audit(user: dict = Depends(require_role(["manager"]))):
    return list_audit_log()


@router.get("/shifts")
def manager_shifts(user: dict = Depends(require_role(["manager"]))):
    return list_shifts()


@router.post("/shifts")
def manager_create_shift(payload: StaffShiftSchema, user: dict = Depends(require_role(["manager"]))):
    return create_admin_shift(payload, user)


@router.get("/time-off")
def manager_time_off(user: dict = Depends(require_role(["manager"]))):
    return list_time_off()


@router.patch("/time-off/{time_off_id}")
def manager_review_time_off(time_off_id: int, payload: TimeOffReviewSchema, user: dict = Depends(require_role(["manager"]))):
    return review_time_off(time_off_id, payload, user)


@router.get("/settings")
def manager_get_settings(user: dict = Depends(require_role(["manager"]))):
    return get_settings()


@router.put("/settings/{setting_key}")
def manager_update_setting(setting_key: str, payload: dict = Body(...), user: dict = Depends(require_role(["manager"]))):
    return update_manager_setting(setting_key, payload, user)


@router.get("/reports/summary")
def manager_report(start_date: str, end_date: str, user: dict = Depends(require_role(["manager"]))):
    return manager_report_summary(start_date, end_date)
