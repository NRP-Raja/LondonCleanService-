"""CleanLondon Authentication Routes — HTTP endpoint definitions for auth."""

from fastapi import APIRouter, Request, Depends, Body, status
from fastapi.responses import JSONResponse

from app.core.dependencies import get_current_user
from app.core.security import limiter, oauth2_scheme
from app.core.config import IS_PRODUCTION, ENVIRONMENT, DEMO_AUTH_ENABLED, DEMO_AUTH_ALLOWED_ENVIRONMENTS
from app.database.connection import get_idempotency_key
from app.schemas.auth import (
    UserRegisterSchema,
    LoginSchema,
    GoogleLoginSchema,
    TokenResponse,
)
from app.services.auth import (
    authenticate_user,
    register_user,
    google_oauth_login,
    demo_switch_role,
)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/login", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
def login_user(request: Request, payload: LoginSchema):
    """Authenticate user with email and password, return JWT token."""
    user = authenticate_user(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    from app.core.security import create_access_token
    token = create_access_token({"user_id": user["id"], "role": user["role"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user["role"],
            "avatar_url": user["avatar_url"],
        },
    }


@router.get("/me", status_code=status.HTTP_200_OK)
def get_current_user_profile(user: dict = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return {"user": user}


@router.post("/google/login", status_code=status.HTTP_200_OK)
def google_oauth_login_route(payload: GoogleLoginSchema):
    """Google OAuth 2.0 Sign-In endpoint with Mock Mode Fallback."""
    return google_oauth_login(
        id_token=payload.id_token,
        email=payload.email,
        name=payload.name,
    )


@router.post("/demo-switch", status_code=status.HTTP_200_OK)
def demo_switch_route(role: str = Body(..., embed=True)):
    """Convenience endpoint for demo: instantly generates a valid JWT for an approved demo account."""
    if not DEMO_AUTH_ENABLED or ENVIRONMENT.strip().lower() not in DEMO_AUTH_ALLOWED_ENVIRONMENTS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )
    return demo_switch_role(role)
