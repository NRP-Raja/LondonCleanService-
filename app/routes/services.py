"""CleanLondon Services & Pricing Routes — HTTP endpoint definitions."""

from fastapi import APIRouter, Request

from app.core.security import limiter
from app.schemas.services import QuoteRequestSchema
from app.services.pricing import list_active_services, compute_quote

router = APIRouter(prefix="/api", tags=["Services & Quotes"])


@router.get("/services")
def list_services():
    """List all active cleaning services."""
    return {"services": list_active_services()}


@router.post("/pricing/calculate")
@limiter.limit("30/minute")
def calculate_quote(request: Request, payload: QuoteRequestSchema):
    """Calculate a dynamic cleaning quote for a London postcode."""
    return compute_quote(payload)
