"""CleanLondon payment request schemas."""

from pydantic import BaseModel


class CreateCheckoutSessionSchema(BaseModel):
    booking_id: int
