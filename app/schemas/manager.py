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
