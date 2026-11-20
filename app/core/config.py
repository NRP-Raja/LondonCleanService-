"""CleanLondon Backend Configuration — all environment variables and constants."""

import os
from typing import Final

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# ---------------------------------------------------------------------------
# Environment & Security Controls
# ---------------------------------------------------------------------------
ENVIRONMENT: Final[str] = os.getenv("ENVIRONMENT", "development")
IS_PRODUCTION: Final[bool] = ENVIRONMENT.lower() == "production"

# ---------------------------------------------------------------------------
# Database Configuration
# ---------------------------------------------------------------------------
DB_HOST: Final[str] = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT: Final[int] = int(os.getenv("DB_PORT", "3306"))
DB_USER: Final[str] = os.getenv("DB_USER", "cleanlondon_user")
DB_PASSWORD: Final[str] = os.getenv("DB_PASSWORD", "cleanlondon_pass")
DB_NAME: Final[str] = os.getenv("DB_NAME", "cleanlondon_db")
DB_POOL_SIZE: Final[int] = max(2, int(os.getenv("DB_POOL_SIZE", "10")))
DB_POOL_TIMEOUT_SECONDS: Final[float] = float(os.getenv("DB_POOL_TIMEOUT_SECONDS", "5"))

# ---------------------------------------------------------------------------
# SMTP / Mail Configuration
# ---------------------------------------------------------------------------
SMTP_HOST: Final[str] = os.getenv("SMTP_HOST", "127.0.0.1")
SMTP_PORT: Final[int] = int(os.getenv("SMTP_PORT", "1025"))
SMTP_FROM: Final[str] = os.getenv("SMTP_FROM", "notifications@cleanlondon.local")

# ---------------------------------------------------------------------------
# JWT Authentication Configuration
# ---------------------------------------------------------------------------
JWT_SECRET_KEY: Final[str] = os.getenv("JWT_SECRET_KEY", "supersecretjwtkey_cleanlondon_production_grade_token_2026")
JWT_ALGORITHM: Final[str] = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES: Final[int] = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

# ---------------------------------------------------------------------------
# Demo / Development Controls
# ---------------------------------------------------------------------------
MOCK_MODE: Final[bool] = False if IS_PRODUCTION else (os.getenv("MOCK_MODE", "true").lower() == "true")
DEMO_AUTH_ENABLED: Final[bool] = os.getenv("DEMO_AUTH_ENABLED", "false").strip().lower() == "true"
DEMO_AUTH_ALLOWED_ENVIRONMENTS: Final[frozenset[str]] = frozenset({"development", "staging"})

DEMO_ACCOUNT_ROLES: Final[dict[str, tuple[str, str]]] = {
    "manager": ("admin@cleanlondon.co.uk", "manager"),
    "staff": ("cleaner.elena@cleanlondon.co.uk", "staff"),
    "staff_elena": ("cleaner.elena@cleanlondon.co.uk", "staff"),
    "staff_marcus": ("cleaner.marcus@cleanlondon.co.uk", "staff"),
    "customer": ("oliver.smith@example.co.uk", "customer"),
}

# ---------------------------------------------------------------------------
# Google APIs
# ---------------------------------------------------------------------------
GOOGLE_CLIENT_ID: Final[str] = os.getenv("GOOGLE_CLIENT_ID", "mock-client-id.apps.googleusercontent.com")
GOOGLE_MAPS_API_KEY: Final[str] = os.getenv("GOOGLE_MAPS_API_KEY", "MOCK_GOOGLE_MAPS_KEY_LONDON")

# ---------------------------------------------------------------------------
# Stripe Payment Gateway Configuration
# ---------------------------------------------------------------------------
STRIPE_SECRET_KEY: Final[str] = os.getenv("STRIPE_SECRET_KEY", "sk_test_mockCleanLondonKey2026")
STRIPE_PUBLISHABLE_KEY: Final[str] = os.getenv("STRIPE_PUBLISHABLE_KEY", "pk_test_mockCleanLondonPubKey2026")
STRIPE_WEBHOOK_SECRET: Final[str] = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_mockWebhookSecret2026")
STRIPE_SUCCESS_URL: Final[str] = os.getenv(
    "STRIPE_SUCCESS_URL", "http://localhost:8000/static/success.html?session_id={CHECKOUT_SESSION_ID}"
)
STRIPE_CANCEL_URL: Final[str] = os.getenv("STRIPE_CANCEL_URL", "http://localhost:8000/static/cancel.html")

# ---------------------------------------------------------------------------
# Allowed CORS Origins
# ---------------------------------------------------------------------------
ALLOWED_ORIGINS: Final[str] = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000")
