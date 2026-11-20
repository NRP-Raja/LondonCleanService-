"""CleanLondon Manager Schemas — Pydantic request/response models for manager/dashboard endpoints."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date


class AssignStaffSchema(BaseModel):
    staff_id: int


class VettingSchema(BaseModel):
    vetting_status: str = Field(..., pattern="^(PENDING|APPROVED|REJECTED)$")
    verified_dbs: bool = False
    right_to_work_verified: bool = False
    dbs_document_ref: Optional[str] = None
    right_to_work_document_ref: Optional[str] = None


class ShiftCreateSchema(BaseModel):
    staff_id: int
    shift_date: date
    start_time: str
    end_time: str
    notes: Optional[str] = None


class SettingsUpdateSchema(BaseModel):
    key: str
    value: str


class PaymentRecordSchema(BaseModel):
    booking_id: int
    amount_gbp: float = Field(..., gt=0)
    method: str = Field(..., pattern="^(CASH|CARD|BANK_TRANSFER|REFUND|OTHER)$")
    reference: Optional[str] = None


class SupportCaseSchema(BaseModel):
    booking_id: Optional[int] = None
    customer_id: int
    subject: str = Field(..., min_length=3, max_length=160)
    description: str = Field(..., min_length=3, max_length=5000)


class SupportCaseUpdateSchema(BaseModel):
    status: str = Field(..., pattern="^(OPEN|IN_PROGRESS|RESOLVED)$")
    assigned_to: Optional[int] = None
    outcome: Optional[str] = None
    follow_up_at: Optional[str] = None


class StaffShiftSchema(BaseModel):
    staff_id: int
    shift_date: str
    start_time: str
    end_time: str


class TimeOffReviewSchema(BaseModel):
    status: str = Field(..., pattern="^(APPROVED|REJECTED)$")
