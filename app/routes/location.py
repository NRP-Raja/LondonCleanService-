"""CleanLondon maps and location routes."""

from fastapi import APIRouter

from app.schemas.location import GeocodeRequestSchema, DistanceRequestSchema
from app.services.location import geocode_postcode, calculate_postcode_distance

router = APIRouter(prefix="/api/maps", tags=["Location & Maps"])


@router.post("/geocode")
def geocode_london_postcode(payload: GeocodeRequestSchema):
    return geocode_postcode(payload.postcode)


@router.post("/distance")
def calculate_distance(payload: DistanceRequestSchema):
    return calculate_postcode_distance(
        payload.origin_postcode,
        payload.destination_postcode,
    )
