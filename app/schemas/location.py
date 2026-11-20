"""CleanLondon location request schemas."""

from pydantic import BaseModel


class GeocodeRequestSchema(BaseModel):
    postcode: str


class DistanceRequestSchema(BaseModel):
    origin_postcode: str
    destination_postcode: str
