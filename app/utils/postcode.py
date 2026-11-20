"""CleanLondon Postcode & Location Utilities — postcode normalization, distance, and travel estimates."""

import re
import math
import json
import urllib.request
import urllib.error
import urllib.parse
from functools import lru_cache
from typing import Optional, Tuple

from fastapi import HTTPException

# ---------------------------------------------------------------------------
# London Postcode Coordinates Lookup Table
# ---------------------------------------------------------------------------
LONDON_POSTCODE_COORDS: dict[str, Tuple[float, float, str]] = {
    "SW1A": (51.5014, -0.1419, "Westminster / Buckingham Palace"),
    "SW1H": (51.4984, -0.1333, "Victoria / St James"),
    "SW1": (51.4984, -0.1333, "Westminster / Victoria"),
    "EC1A": (51.5190, -0.0990, "City of London / Clerkenwell"),
    "E1": (51.5170, -0.0610, "Spitalfields / Whitechapel"),
    "E14": (51.5050, -0.0200, "Canary Wharf / Isle of Dogs"),
    "NW1": (51.5360, -0.1400, "Camden Town / Regent's Park"),
    "W1D": (51.5136, -0.1330, "Soho / West End"),
    "W1": (51.5136, -0.1330, "West End / Mayfair"),
    "SE1": (51.5030, -0.0900, "Southwark / London Bridge"),
    "W2": (51.5130, -0.1760, "Paddington / Bayswater"),
    "W8": (51.5010, -0.1947, "Kensington / High Street"),
    "SW3": (51.4900, -0.1650, "Chelsea / Kings Road"),
    "TW9": (51.4613, -0.3037, "Richmond / Surrey Border"),
    "WC1": (51.5240, -0.1230, "Bloomsbury / Holborn"),
    "SE10": (51.4820, -0.0070, "Greenwich / Maritime"),
    "N1": (51.5370, -0.1030, "Islington / Angel"),
    "BR1": (51.4050, 0.0150, "Bromley"),
    "BR2": (51.3940, 0.0190, "Bromley"),
    "BR6": (51.3670, 0.0940, "Orpington"),
    "CR0": (51.3710, -0.1010, "Croydon"),
    "CR2": (51.3510, -0.0900, "South Croydon"),
    "CR7": (51.3970, -0.1190, "Thornton Heath"),
    "DA1": (51.4450, 0.2190, "Dartford"),
    "EN1": (51.6530, -0.0800, "Enfield"),
    "HA0": (51.5550, -0.3050, "Wembley"),
    "HA3": (51.5980, -0.3330, "Harrow"),
    "IG1": (51.5590, 0.0690, "Ilford"),
    "KT1": (51.4120, -0.3000, "Kingston"),
    "RM1": (51.5790, 0.1820, "Romford"),
    "SM1": (51.3620, -0.1960, "Sutton"),
    "UB1": (51.5090, -0.3780, "Southall"),
    "UB6": (51.5350, -0.3500, "Greenford"),
    "WD3": (51.6400, -0.4720, "Rickmansworth"),
}


# ---------------------------------------------------------------------------
# Postcode Normalization & Resolution
# ---------------------------------------------------------------------------
def normalize_london_postcode(raw_postcode: str) -> str:
    """Extract and validate the outcode from a UK postcode (e.g. SW1A 1AA -> SW1A)."""
    cleaned = re.sub(r"[^A-Za-z0-9]", "", raw_postcode.upper())
    full_match = re.match(r"^([A-Z]{1,2}[0-9]{1,2}[A-Z]?)[0-9][A-Z]{2}$", cleaned)
    match = full_match or re.match(r"^([A-Z]{1,2}[0-9]{1,2}[A-Z]?)$", cleaned)
    if not match:
        raise HTTPException(status_code=422, detail="Enter a valid UK postcode")
    return match.group(1)


@lru_cache(maxsize=4096)
def _lookup_postcode_online(postcode: str) -> Optional[Tuple[float, float, str]]:
    """Resolve an unlisted full postcode via postcodes.io API."""
    url = f"https://api.postcodes.io/postcodes/{urllib.parse.quote(postcode)}"
    try:
        with urllib.request.urlopen(url, timeout=2.5) as response:
            data = json.loads(response.read().decode("utf-8"))
        result = data.get("result") or {}
        if result.get("latitude") is None or result.get("longitude") is None:
            return None
        return (
            float(result["latitude"]),
            float(result["longitude"]),
            result.get("admin_district") or "Greater London",
        )
    except (OSError, ValueError, KeyError, urllib.error.URLError):
        return None


def resolve_postcode_coords(raw_postcode: str) -> Tuple[float, float, str]:
    """Resolve a postcode to (latitude, longitude, description). Uses local table first, then online API."""
    outcode = normalize_london_postcode(raw_postcode)
    known = LONDON_POSTCODE_COORDS.get(outcode)
    if known:
        return known

    compact = re.sub(r"[^A-Za-z0-9]", "", raw_postcode.upper())
    if len(compact) < 5:
        raise HTTPException(
            status_code=422,
            detail=f"Postcode outcode '{outcode}' is not in the local map; provide a full UK postcode.",
        )
    resolved = _lookup_postcode_online(compact)
    if not resolved:
        raise HTTPException(
            status_code=422,
            detail=f"Could not resolve postcode '{raw_postcode}'. Check the postcode and try again.",
        )
    return resolved


# ---------------------------------------------------------------------------
# Distance & Travel Estimates
# ---------------------------------------------------------------------------
def haversine_distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points in miles."""
    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)


def parse_time_slot_minutes(time_slot: str) -> Tuple[int, int]:
    """Extract start and end times in minutes from midnight. e.g. '10:00 - 13:00' -> (600, 780)."""
    matches = re.findall(r"(\d{1,2}):(\d{2})", time_slot)
    if len(matches) >= 2:
        start_min = int(matches[0][0]) * 60 + int(matches[0][1])
        end_min = int(matches[1][0]) * 60 + int(matches[1][1])
        return start_min, end_min
    elif len(matches) == 1:
        start_min = int(matches[0][0]) * 60 + int(matches[0][1])
        return start_min, start_min + 180
    return 540, 720


def format_minutes_to_time(minutes: int) -> str:
    """Convert minutes since midnight to HH:MM string."""
    h = (minutes // 60) % 24
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


def calculate_tfl_travel_buffer_minutes(postcode1: str, postcode2: str) -> int:
    """
    Compute realistic London TfL travel buffer between two postcodes:
    - Same outcode: 30 minutes
    - Different outcodes: 30 to 60 minutes based on haversine distance
    """
    out1 = normalize_london_postcode(postcode1)
    out2 = normalize_london_postcode(postcode2)
    if out1 == out2:
        return 30

    coords1 = resolve_postcode_coords(postcode1)
    coords2 = resolve_postcode_coords(postcode2)
    dist_miles = haversine_distance_miles(coords1[0], coords1[1], coords2[0], coords2[1])

    buffer_mins = int(30 + (dist_miles * 5))
    return min(60, max(30, buffer_mins))