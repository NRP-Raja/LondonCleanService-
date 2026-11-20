"""CleanLondon Services & Pricing Schemas — Pydantic request/response models."""

from pydantic import BaseModel, Field


class QuoteRequestSchema(BaseModel):
    postcode: str
    service_id: int
    property_type: str = "Flat/Apartment"
    bedrooms: int = 1
    bathrooms: int = 1
    has_pets: bool = False
    deep_clean: bool = False
    eco_products: bool = True
