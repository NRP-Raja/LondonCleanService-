"""CleanLondon FastAPI application composition."""

import os

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import (
    ALLOWED_ORIGINS,
    DEMO_ACCOUNT_ROLES,
    DEMO_AUTH_ALLOWED_ENVIRONMENTS,
    DEMO_AUTH_ENABLED,
    ENVIRONMENT,
    IS_PRODUCTION,
)
from app.core.middleware import SecurityHeadersMiddleware
from app.core.security import limiter
from app.database.migrations import ensure_operational_schema
from app.database.connection import get_db, get_transaction
from app.core.security import create_access_token
from app.services.auth import demo_switch_role as modular_demo_switch_role
from app.routes.auth import router as auth_router
from app.routes.bookings import router as bookings_router
from app.routes.location import router as location_router
from app.routes.manager import router as manager_router
from app.routes.notifications import router as notifications_router
from app.routes.payments import router as payments_router
from app.routes.services import router as services_router
from app.routes.staff import router as staff_router


app = FastAPI(
    title="CleanLondon API",
    description="UK Domestic Cleaning Platform - End-to-End API",
    version="1.0.0",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in ALLOWED_ORIGINS.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth_router)
app.include_router(services_router)
app.include_router(bookings_router)
app.include_router(staff_router)
app.include_router(manager_router)
app.include_router(notifications_router)
app.include_router(location_router)
app.include_router(payments_router)


@app.on_event("startup")
def run_operational_migrations() -> None:
    ensure_operational_schema()


project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
frontend_dir = os.path.join(project_root, "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.get("/")
def serve_homepage():
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "CleanLondon API is online. Mount frontend files under /frontend."}


# Compatibility wrapper for existing imports and tests.
def demo_switch_role(role: str):
    if not DEMO_AUTH_ENABLED or ENVIRONMENT.strip().lower() not in DEMO_AUTH_ALLOWED_ENVIRONMENTS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    approved_account = DEMO_ACCOUNT_ROLES.get(role.strip().lower())
    if not approved_account:
        raise HTTPException(status_code=400, detail="Invalid demo role.")
    target_email, expected_role = approved_account
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.id, u.email, u.full_name, r.name as role, u.avatar_url, u.is_active
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE u.email = %s
                """,
                (target_email,),
            )
            user = cursor.fetchone()
            if not user or not user["is_active"] or user["role"] != expected_role:
                raise HTTPException(status_code=404, detail="Not found")
            token = create_access_token({"user_id": user["id"], "role": user["role"]})
            return {
                "access_token": token,
                "token_type": "bearer",
                "user": {key: user[key] for key in ("id", "email", "full_name", "role", "avatar_url")},
            }
