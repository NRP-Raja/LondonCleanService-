"""CleanLondon FastAPI Dependencies — current user extraction and role-based access control."""

from fastapi import Depends, HTTPException, status
from jose import JWTError, jwt
from typing import Callable

from app.core.security import oauth2_scheme
from app.core.config import JWT_SECRET_KEY, JWT_ALGORITHM
from app.database.connection import get_db


# ---------------------------------------------------------------------------
# Current User Dependency
# ---------------------------------------------------------------------------
def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """Extract and validate the current authenticated user from a JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or token expired",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id: int = payload.get("user_id")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.id, u.role_id, r.name as role, u.email, u.full_name, u.phone, u.avatar_url, u.is_active
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE u.id = %s
                """,
                (user_id,),
            )
            user = cursor.fetchone()
            if not user or not user["is_active"]:
                raise credentials_exception
            return user


# ---------------------------------------------------------------------------
# Role-Based Access Control
# ---------------------------------------------------------------------------
def require_role(allowed_roles: list[str]) -> Callable:
    """Return a dependency that enforces the user has one of the allowed roles."""

    def role_checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return role_checker
