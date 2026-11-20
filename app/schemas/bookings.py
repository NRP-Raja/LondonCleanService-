"""CleanLondon Booking Schemas — Pydantic request/response models for booking endpoints."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


class BookingCreateSchema(BaseModel):
    service_id: int
    property_type: str = "Flat/Apartment"
    bedrooms: int = 1
    bathrooms: int = 1
    has_pets: bool = False
    deep_clean_requested: bool = False
    eco_cleaning_products: bool = True
    address_line1: str
    address_line2: Optional[str] = ""
    city: str = "London"
    postcode: str
    key_handling_type: str = "concierge"
    access_notes: Optional[str] = ""
    scheduled_date: date
    scheduled_time_slot: str
    idempotency_key: Optional[str] = None


class CancelBookingSchema(BaseModel):
    reason: Optional[str] = None


class RescheduleBookingSchema(BaseModel):
    new_date: date
    new_time_slot: str


class ReviewCreateSchema(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str
    punctuality_score: int = Field(..., ge=1, le=5)
    thoroughness_score: int = Field(..., ge=1, le=5)
