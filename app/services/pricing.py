"""CleanLondon Pricing Service — dynamic London cleaning quote engine."""

from fastapi import HTTPException

from app.database.connection import get_db
from app.utils.postcode import normalize_london_postcode, resolve_postcode_coords
from app.schemas.services import QuoteRequestSchema


# ---------------------------------------------------------------------------
# Service Listing
# ---------------------------------------------------------------------------
def list_active_services() -> list[dict]:
    """Return all active cleaning services ordered by ID."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM services WHERE is_active = TRUE ORDER BY id ASC"
            )
            return cursor.fetchall()


# ---------------------------------------------------------------------------
# Dynamic Quote Calculation
# ---------------------------------------------------------------------------
def compute_quote(payload: QuoteRequestSchema) -> dict:
    """
    Dynamic London Cleaning Pricing Engine:
    - Analyzes postcode outcode
    - Applies property size formula (base + bedrooms + bathrooms)
    - Extras: Deep clean (+£25), Pets (+£10)
    - Estimates duration in hours
    - Central London congestion surcharge (SW1A, SW1H, EC1A, W1D)
    """
    outcode = normalize_london_postcode(payload.postcode)
    resolve_postcode_coords(payload.postcode)

    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM services WHERE id = %s", (payload.service_id,))
            service = cursor.fetchone()
            if not service:
                raise HTTPException(status_code=404, detail="Service not found")

    base = float(service["base_price_gbp"])
    bedroom_rate = float(service["price_per_bedroom_gbp"])
    bathroom_rate = float(service["price_per_bathroom_gbp"])
    est_hours = float(service["estimated_duration_hours"])

    # Formula
    property_cost = (payload.bedrooms * bedroom_rate) + (payload.bathrooms * bathroom_rate)
    pet_fee = 10.00 if payload.has_pets else 0.00
    deep_clean_fee = 25.00 if payload.deep_clean else 0.00

    # Congestion / Central London factor (EC1, SW1, W1 have slight surcharge)
    zone_charge = 5.00 if outcode in ["SW1A", "SW1H", "EC1A", "W1D"] else 0.00

    total_price = round(base + property_cost + pet_fee + deep_clean_fee + zone_charge, 2)
    calculated_hours = round(est_hours + (payload.bedrooms * 0.5) + (payload.bathrooms * 0.3), 1)

    return {
        "postcode": payload.postcode,
        "outcode": outcode,
        "service_name": service["name"],
        "breakdown": {
            "base_service_gbp": base,
            "property_rooms_gbp": round(property_cost, 2),
            "pet_care_addon_gbp": pet_fee,
            "deep_clean_addon_gbp": deep_clean_fee,
            "central_london_travel_gbp": zone_charge,
        },
        "estimated_duration_hours": calculated_hours,
        "hourly_equivalent_gbp": round(total_price / calculated_hours, 2),
        "total_price_gbp": total_price,
        "currency": "GBP (£)",
    }
