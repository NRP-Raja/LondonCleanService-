"""CleanLondon Security Headers Middleware — defense-in-depth HTTP headers."""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import IS_PRODUCTION


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject defense-in-depth security headers on every response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if IS_PRODUCTION:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response
