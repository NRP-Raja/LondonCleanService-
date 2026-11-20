"""CleanLondon maps and location services."""

from app.core.config import MOCK_MODE
from app.utils.postcode import (
    normalize_london_postcode,
    resolve_postcode_coords,
    haversine_distance_miles,
)


def geocode_postcode(postcode: str) -> dict:
    outcode = normalize_london_postcode(postcode)
    latitude, longitude, neighborhood = resolve_postcode_coords(postcode)
    return {
        "input_postcode": postcode,
        "outcode": outcode,
        "neighborhood": neighborhood,
        "latitude": latitude,
        "longitude": longitude,
        "is_mock": MOCK_MODE,
        "formatted_address": f"{postcode.upper()}, London, United Kingdom",
    }


def calculate_postcode_distance(origin_postcode: str, destination_postcode: str) -> dict:
    normalize_london_postcode(origin_postcode)
    normalize_london_postcode(destination_postcode)
    origin = resolve_postcode_coords(origin_postcode)
    destination = resolve_postcode_coords(destination_postcode)
    distance_miles = haversine_distance_miles(
        origin[0],
        origin[1],
        destination[0],
        destination[1],
    )
    return {
        "origin": origin_postcode,
        "destination": destination_postcode,
        "distance_miles": distance_miles,
        "estimated_travel_minutes": int(distance_miles * 7 + 10),
        "mode": "London Underground & Bus (TfL)",
        "is_mock": MOCK_MODE,
    }
