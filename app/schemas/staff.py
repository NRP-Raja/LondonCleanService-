"""CleanLondon Staff Schemas — Pydantic request/response models for staff/cleaner endpoints."""

from pydantic import BaseModel, Field
from typing import Optional, List


class WeeklyAvailabilitySchema(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6)
    start_time: str
    end_time: str


class HolidaySchema(BaseModel):
    holiday_date: str
    reason: Optional[str] = None


class StaffStatusUpdateSchema(BaseModel):
    status: str
    notes: Optional[str] = None
