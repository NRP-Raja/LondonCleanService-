"""CleanLondon Authentication Service — business logic for auth endpoints."""

import json
import random
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from fastapi import HTTPException, status

from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.core.config import (
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    MOCK_MODE,
    IS_PRODUCTION,
    DEMO_AUTH_ENABLED,
    DEMO_AUTH_ALLOWED_ENVIRONMENTS,
    DEMO_ACCOUNT_ROLES,
    GOOGLE_CLIENT_ID,
    ENVIRONMENT,
)
from app.database.connection import get_db


# ---------------------------------------------------------------------------
# Auth Business Logic
# ---------------------------------------------------------------------------

def authenticate_user(email: str, password: str) -> dict | None:
    """Verify credentials and return the user dict, or None if invalid."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.id, u.email, u.password_hash, u.full_name, u.phone,
                       u.avatar_url, r.name as role, u.is_active
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE u.email = %s
                """,
                (email,),
            )
            user = cursor.fetchone()
            if not user or not user["is_active"]:
                return None
            if not verify_password(password, user["password_hash"]):
                return None
            return user


def register_user(
    email: str,
    password: str,
    full_name: str,
    phone: str,
    role: str = "customer",
) -> dict:
    """Register a new user. Defaults to 'customer' role to prevent escalation."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM roles WHERE name = %s", (role,))
            role_row = cursor.fetchone()
            if not role_row:
                raise HTTPException(status_code=400, detail="Invalid role specified")
            role_id = role_row["id"]

            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                raise HTTPException(status_code=409, detail="Email already registered")

            password_hash = hash_password(password)
            cursor.execute(
                """
                INSERT INTO users (role_id, email, password_hash, full_name, phone, google_id, avatar_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (role_id, email, password_hash, full_name, phone, None, None),
            )
            user_id = cursor.lastrowid

            return {
                "id": user_id,
                "email": email,
                "full_name": full_name,
                "role": role,
                "avatar_url": None,
            }


def google_oauth_login(
    id_token: str,
    email: Optional[str] = None,
    name: Optional[str] = None,
) -> dict:
    """Handle Google OAuth 2.0 sign-in with production verification and RBAC guards."""
    google_email: str
    google_name: str
    google_sub: str

    if IS_PRODUCTION and not MOCK_MODE:
        try:
            req = urllib.request.Request(
                f"https://oauth2.googleapis.com/tokeninfo?id_token={urllib.parse.quote(id_token)}"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                token_data = json.loads(resp.read().decode("utf-8"))
            if token_data.get("aud") != GOOGLE_CLIENT_ID:
                raise HTTPException(status_code=401, detail="Invalid Google OAuth token audience")
            google_email = token_data.get("email") or ""
            google_sub = token_data.get("sub") or ""
            google_name = token_data.get("name") or "Google User"
            if not google_email:
                raise HTTPException(status_code=401, detail="Google token does not contain email")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid or expired Google OAuth ID token")
    else:
        google_email = email or "google.user@cleanlondon.demo"
        google_name = name or "Google London Client"
        google_sub = "google-sub-" + str(random.randint(1000, 9999))

    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.id, u.email, u.full_name, r.name as role, u.avatar_url, u.google_id
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE u.email = %s
                """,
                (google_email,),
            )
            user = cursor.fetchone()

            if user:
                # Security Protection: Prevent takeover of administrative / staff accounts via Google OAuth
                if user["role"] in ["manager", "staff"]:
                    raise HTTPException(
                        status_code=403,
                        detail="Staff and Manager accounts cannot sign in via Google OAuth. Please use your email and password.",
                    )
                user_id = user["id"]
                role_name = user["role"]
                if not user.get("google_id"):
                    cursor.execute(
                        "UPDATE users SET google_id = %s WHERE id = %s",
                        (google_sub, user_id),
                    )
            else:
                cursor.execute("SELECT id FROM roles WHERE name = 'customer'")
                role_row = cursor.fetchone()
                role_id = role_row["id"]
                cursor.execute(
                    """
                    INSERT INTO users (role_id, email, password_hash, full_name, phone, google_id, avatar_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        role_id,
                        google_email,
                        hash_password("GoogleAuthPassword123!"),
                        google_name,
                        "+44 7900 112233",
                        google_sub,
                        "https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=150",
                    ),
                )
                user_id = cursor.lastrowid
                role_name = "customer"

    token = create_access_token({"user_id": user_id, "role": role_name})
    return {
        "message": "Authenticated successfully via Google OAuth 2.0",
        "is_mock": MOCK_MODE,
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user_id,
            "email": google_email,
            "full_name": user["full_name"] if user else google_name,
            "role": role_name,
        },
    }


def demo_switch_role(role: str) -> dict:
    """Generate a JWT for an approved demo account (development/staging only)."""
    if not DEMO_AUTH_ENABLED or ENVIRONMENT.strip().lower() not in DEMO_AUTH_ALLOWED_ENVIRONMENTS:
        raise HTTPException(status_code=404, detail="Not found")

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
                "user": {
                    key: user[key]
                    for key in ("id", "email", "full_name", "role", "avatar_url")
                },
            }

