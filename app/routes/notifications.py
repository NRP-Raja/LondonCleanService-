"""CleanLondon notification routes."""

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user
from app.services.notifications import get_my_notifications

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.get("/my")
def notifications_for_current_user(user: dict = Depends(get_current_user)):
    return get_my_notifications(user["id"])
