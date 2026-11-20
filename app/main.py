import os
import re
import math
import random
import datetime
import json
import queue
import threading
import urllib.error
import urllib.parse
import urllib.request
import smtplib
from email.message import EmailMessage
from functools import lru_cache
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from fastapi import FastAPI, Depends, HTTPException, status, Query, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, EmailStr, Field
from jose import JWTError, jwt
from passlib.context import CryptContext
import pymysql
import pymysql.cursors
import stripe
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

load_dotenv()

# ==========================================================
# CONFIGURATION & CONSTANTS
# ==========================================================
# --- Environment & Security Controls ---
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
IS_PRODUCTION = ENVIRONMENT.lower() == "production"
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "cleanlondon_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "cleanlondon_pass")
DB_NAME = os.getenv("DB_NAME", "cleanlondon_db")
DB_POOL_SIZE = max(2, int(os.getenv("DB_POOL_SIZE", "10")))
DB_POOL_TIMEOUT_SECONDS = float(os.getenv("DB_POOL_TIMEOUT_SECONDS", "5"))
SMTP_HOST = os.getenv("SMTP_HOST", "127.0.0.1")
SMTP_PORT = int(os.getenv("SMTP_PORT", "1025"))
SMTP_FROM = os.getenv("SMTP_FROM", "notifications@cleanlondon.local")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "supersecretjwtkey_cleanlondon_production_grade_token_2026")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

MOCK_MODE = False if IS_PRODUCTION else (os.getenv("MOCK_MODE", "true").lower() == "true")
DEMO_AUTH_ENABLED = os.getenv("DEMO_AUTH_ENABLED", "false").strip().lower() == "true"
DEMO_AUTH_ALLOWED_ENVIRONMENTS = frozenset({"development", "staging"})
DEMO_ACCOUNT_ROLES = {
    "manager": ("admin@cleanlondon.co.uk", "manager"),
    "staff": ("cleaner.elena@cleanlondon.co.uk", "staff"),
    "staff_elena": ("cleaner.elena@cleanlondon.co.uk", "staff"),
    "staff_marcus": ("cleaner.marcus@cleanlondon.co.uk", "staff"),
    "customer": ("oliver.smith@example.co.uk", "customer"),
}
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "mock-client-id.apps.googleusercontent.com")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "MOCK_GOOGLE_MAPS_KEY_LONDON")

# Stripe Payment Gateway Configuration
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "sk_test_mockCleanLondonKey2026")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "pk_test_mockCleanLondonPubKey2026")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_mockWebhookSecret2026")
STRIPE_SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL", "http://localhost:8000/static/success.html?session_id={CHECKOUT_SESSION_ID}")
STRIPE_CANCEL_URL = os.getenv("STRIPE_CANCEL_URL", "http://localhost:8000/static/cancel.html")
stripe.api_key = STRIPE_SECRET_KEY

import bcrypt
import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken

# UK GDPR Sensitive Data Encryption Key (AES-256 Fernet)
DATA_ENCRYPTION_KEY = os.getenv("DATA_ENCRYPTION_KEY")
if not DATA_ENCRYPTION_KEY:
    # Deterministically derive 32-byte urlsafe base64 key from JWT_SECRET_KEY as fallback
    derived = hashlib.sha256(JWT_SECRET_KEY.encode('utf-8')).digest()
    DATA_ENCRYPTION_KEY = base64.urlsafe_b64encode(derived).decode('utf-8')

cipher_suite = Fernet(DATA_ENCRYPTION_KEY.encode('utf-8') if isinstance(DATA_ENCRYPTION_KEY, str) else DATA_ENCRYPTION_KEY)

def encrypt_sensitive_data(plaintext: Optional[str]) -> Optional[str]:
    """Encrypt sensitive customer access notes & PIN codes at rest (AES-256 Fernet)."""
    if not plaintext or not plaintext.strip():
        return plaintext
    try:
        cipher_suite.decrypt(plaintext.encode("utf-8"))
        return plaintext
    except (InvalidToken, ValueError, TypeError):
        pass
    try:
        return cipher_suite.encrypt(plaintext.encode("utf-8")).decode("utf-8")
    except Exception as exc:
        raise RuntimeError("Unable to encrypt sensitive access data") from exc

def decrypt_sensitive_data(ciphertext: Optional[str]) -> Optional[str]:
    """Decrypt sensitive customer access notes at rest."""
    if not ciphertext or not ciphertext.strip():
        return ciphertext
    try:
        return cipher_suite.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Stored sensitive access data is not a valid encrypted value") from exc

def mask_access_notes_for_staff(status_val: str, encrypted_or_plain_notes: Optional[str]) -> Optional[str]:
    """
    UK GDPR & Access Code Security Masking:
    - Cleaners ONLY see entry PINs & access notes when actively 'EN_ROUTE' or 'IN_PROGRESS'.
    - When 'SCHEDULED', entry codes are masked with a security shield notice.
    - When 'COMPLETED' or 'CANCELLED', entry codes are concealed following appointment conclusion.
    """
    if not encrypted_or_plain_notes:
        return None

    status_upper = status_val.upper() if status_val else "SCHEDULED"
    if status_upper in ["EN_ROUTE", "IN_PROGRESS"]:
        return decrypt_sensitive_data(encrypted_or_plain_notes)
    elif status_upper == "SCHEDULED":
        return "🔒 [Protected by CleanLondon Security: Entry PIN & access notes will be revealed when your status is updated to 'En Route']"
    else:
        return "🔒 [Access notes concealed following appointment completion]"

def migrate_plaintext_access_notes(cursor) -> None:
    """Encrypt legacy plaintext access notes before the application serves requests."""
    cursor.execute("""
        SELECT id, access_notes
        FROM bookings
        WHERE access_notes IS NOT NULL AND TRIM(access_notes) <> ''
    """)
    for booking in cursor.fetchall():
        try:
            cipher_suite.decrypt(booking["access_notes"].encode("utf-8"))
        except (InvalidToken, ValueError, TypeError):
            encrypted_notes = encrypt_sensitive_data(booking["access_notes"])
            cursor.execute(
                "UPDATE bookings SET access_notes = %s WHERE id = %s",
                (encrypted_notes, booking["id"]),
            )

# Password Hashing Utilities using native bcrypt (bypassing passlib 72-byte wrap bug)
def hash_password(password: str) -> str:
    pwd_bytes = password[:72].encode('utf-8')
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    try:
        return bcrypt.checkpw(plain_password[:72].encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

LONDON_POSTCODE_COORDS = {
    "SW1A": (51.5014, -0.1419, "Westminster / Buckingham Palace"),
    "SW1H": (51.4984, -0.1333, "Victoria / St James"),
    "SW1":  (51.4984, -0.1333, "Westminster / Victoria"),
    "EC1A": (51.5190, -0.0990, "City of London / Clerkenwell"),
    "E1":   (51.5170, -0.0610, "Spitalfields / Whitechapel"),
    "E14":  (51.5050, -0.0200, "Canary Wharf / Isle of Dogs"),
    "NW1":  (51.5360, -0.1400, "Camden Town / Regent's Park"),
    "W1D":  (51.5136, -0.1330, "Soho / West End"),
    "W1":   (51.5136, -0.1330, "West End / Mayfair"),
    "SE1":  (51.5030, -0.0900, "Southwark / London Bridge"),
    "W2":   (51.5130, -0.1760, "Paddington / Bayswater"),
    "W8":   (51.5010, -0.1947, "Kensington / High Street"),
    "SW3":  (51.4900, -0.1650, "Chelsea / Kings Road"),
    "TW9":  (51.4613, -0.3037, "Richmond / Surrey Border"),
    "WC1":  (51.5240, -0.1230, "Bloomsbury / Holborn"),
    "SE10": (51.4820, -0.0070, "Greenwich / Maritime"),
    "N1":   (51.5370, -0.1030, "Islington / Angel"),
    # Outer London outcodes used by customer addresses and staff territories.
    # Full postcodes not represented here are resolved through postcodes.io.
    "BR1":  (51.4050, 0.0150, "Bromley"),
    "BR2":  (51.3940, 0.0190, "Bromley"),
    "BR6":  (51.3670, 0.0940, "Orpington"),
    "CR0":  (51.3710, -0.1010, "Croydon"),
    "CR2":  (51.3510, -0.0900, "South Croydon"),
    "CR7":  (51.3970, -0.1190, "Thornton Heath"),
    "DA1":  (51.4450, 0.2190, "Dartford"),
    "EN1":  (51.6530, -0.0800, "Enfield"),
    "HA0":  (51.5550, -0.3050, "Wembley"),
    "HA3":  (51.5980, -0.3330, "Harrow"),
    "IG1":  (51.5590, 0.0690, "Ilford"),
    "KT1":  (51.4120, -0.3000, "Kingston"),
    "RM1":  (51.5790, 0.1820, "Romford"),
    "SM1":  (51.3620, -0.1960, "Sutton"),
    "UB1":  (51.5090, -0.3780, "Southall"),
    "UB6":  (51.5350, -0.3500, "Greenford"),
    "WD3":  (51.6400, -0.4720, "Rickmansworth"),
}

# ==========================================================
# DATABASE HELPER
# ==========================================================
_DB_POOL = queue.LifoQueue(maxsize=DB_POOL_SIZE)
_DB_POOL_LOCK = threading.Lock()
_DB_POOL_CREATED = 0


def _create_db_connection():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )


def get_db_connection():
    global _DB_POOL_CREATED
    try:
        conn = _DB_POOL.get_nowait()
        conn.ping(reconnect=True)
        return conn
    except queue.Empty:
        with _DB_POOL_LOCK:
            if _DB_POOL_CREATED < DB_POOL_SIZE:
                _DB_POOL_CREATED += 1
                try:
                    return _create_db_connection()
                except Exception as e:
                    _DB_POOL_CREATED -= 1
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=f"Database connection error: {str(e)}. Ensure MySQL is running on {DB_HOST}:{DB_PORT}."
                    )
        try:
            conn = _DB_POOL.get(timeout=DB_POOL_TIMEOUT_SECONDS)
            conn.ping(reconnect=True)
            return conn
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Database connection pool is exhausted or unavailable: {str(e)}"
            )
    except Exception:
        # Drop a stale pooled connection and create a replacement.
        with _DB_POOL_LOCK:
            _DB_POOL_CREATED = max(0, _DB_POOL_CREATED - 1)
        try:
            conn.close()
        except Exception:
            pass
        try:
            with _DB_POOL_LOCK:
                _DB_POOL_CREATED += 1
            return _create_db_connection()
        except Exception as e:
            with _DB_POOL_LOCK:
                _DB_POOL_CREATED = max(0, _DB_POOL_CREATED - 1)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Database connection error: {str(e)}. Ensure MySQL is running on {DB_HOST}:{DB_PORT}."
            )


def release_db_connection(conn):
    try:
        conn.ping(reconnect=True)
        _DB_POOL.put(conn, timeout=DB_POOL_TIMEOUT_SECONDS)
    except Exception:
        global _DB_POOL_CREATED
        try:
            conn.close()
        finally:
            with _DB_POOL_LOCK:
                _DB_POOL_CREATED = max(0, _DB_POOL_CREATED - 1)


@contextmanager
def get_db():
    conn = get_db_connection()
    try:
        yield conn
    finally:
        release_db_connection(conn)


def get_idempotency_key(request: Request, payload_key: Optional[str] = None) -> Optional[str]:
    """Prefer the standard header while retaining compatibility with older clients."""
    header_key = request.headers.get("Idempotency-Key")
    if header_key and payload_key and header_key != payload_key:
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key header does not match the request payload.",
        )
    key = header_key or payload_key
    if key and (len(key) > 100 or not re.fullmatch(r"[A-Za-z0-9._:-]+", key)):
        raise HTTPException(status_code=400, detail="Invalid Idempotency-Key.")
    return key


@contextmanager
def get_transaction():
    """Provide an explicit transaction for operations that require row locking."""
    conn = get_db_connection()
    try:
        conn.begin()
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        release_db_connection(conn)


def queue_notification(cursor, recipient_user_id: Optional[int], recipient_address: str,
                       subject: str, body: str) -> None:
    """Persist every notification and deliver it to local SMTP/Mailpit when available."""
    cursor.execute("""
        INSERT INTO notification_outbox
            (recipient_user_id, recipient_address, channel, subject, body, status)
        VALUES (%s, %s, 'EMAIL', %s, %s, 'QUEUED')
    """, (recipient_user_id, recipient_address, subject, body))
    notification_id = cursor.lastrowid
    message = EmailMessage()
    message["From"] = SMTP_FROM
    message["To"] = recipient_address
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=3) as smtp:
            smtp.send_message(message)
        cursor.execute(
            "UPDATE notification_outbox SET status = 'SENT', sent_at = NOW() WHERE id = %s",
            (notification_id,),
        )
    except (OSError, smtplib.SMTPException) as exc:
        cursor.execute(
            "UPDATE notification_outbox SET status = 'FAILED', error_message = %s WHERE id = %s",
            (str(exc)[:500], notification_id),
        )


def log_activity(cursor, user: dict, action: str, entity_type: str, entity_id: object,
                 before: object = None, after: object = None, reason: Optional[str] = None,
                 request_id: Optional[str] = None) -> None:
    cursor.execute("""
        INSERT INTO activity_audit_log
            (actor_id, actor_role, action, entity_type, entity_id, before_json, after_json, reason, request_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        user.get("id"),
        user.get("role"),
        action,
        entity_type,
        str(entity_id) if entity_id is not None else None,
        json.dumps(before, default=str) if before is not None else None,
        json.dumps(after, default=str) if after is not None else None,
        reason,
        request_id,
    ))


# ==========================================================
# SECURITY & AUTH UTILITIES
# ==========================================================
# Password utilities are defined above using native bcrypt

def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + (expires_delta or datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
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
            cursor.execute("""
                SELECT u.id, u.role_id, r.name as role, u.email, u.full_name, u.phone, u.avatar_url, u.is_active
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE u.id = %s
            """, (user_id,))
            user = cursor.fetchone()
            if not user or not user["is_active"]:
                raise HTTPException(status_code=401, detail="User not found or inactive")
            return user

def require_role(allowed_roles: List[str]):
    def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: requires one of {allowed_roles} roles. Your role is '{current_user['role']}'."
            )
        return current_user
    return role_checker

# ==========================================================
# PYDANTIC SCHEMAS
# ==========================================================
class UserRegisterSchema(BaseModel):
    email: str
    password: str = Field(..., min_length=8)
    full_name: str
    phone: str
    role: Optional[str] = "customer"

class LoginSchema(BaseModel):
    email: str
    password: str

class GoogleLoginSchema(BaseModel):
    id_token: str
    email: Optional[str] = None
    name: Optional[str] = None

class QuoteRequestSchema(BaseModel):
    postcode: str
    service_id: int
    property_type: str = "Flat/Apartment"
    bedrooms: int = 1
    bathrooms: int = 1
    has_pets: bool = False
    deep_clean: bool = False
    eco_products: bool = True

class BookingCreateSchema(BaseModel):
    service_id: int
    property_type: str = "Flat/Apartment"
    bedrooms: int = 1
    bathrooms: int = 1
    has_pets: bool = False
    deep_clean_requested: bool = False
    eco_cleaning_products: bool = True
    address_line1: str
    address_line2: Optional[str] = None
    city: str = "London"
    postcode: str
    key_handling_type: str = "MEET_IN_PERSON"
    access_notes: Optional[str] = None
    scheduled_date: str
    scheduled_time_slot: str
    idempotency_key: Optional[str] = None

class CancelBookingSchema(BaseModel):
    reason: Optional[str] = None

class RescheduleBookingSchema(BaseModel):
    new_date: str
    new_time_slot: str
    reason: Optional[str] = None

class ReviewCreateSchema(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str
    punctuality_score: int = 5
    thoroughness_score: int = 5

class StatusUpdateSchema(BaseModel):
    status: str
    notes: Optional[str] = None

class AssignStaffSchema(BaseModel):
    staff_id: int

class WeeklyAvailabilitySchema(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6)
    start_time: str
    end_time: str

class HolidaySchema(BaseModel):
    holiday_date: str
    reason: Optional[str] = None

class VettingSchema(BaseModel):
    verified_dbs: bool
    right_to_work_verified: bool
    vetting_status: str = Field(..., pattern="^(PENDING|APPROVED|REJECTED)$")
    dbs_document_ref: Optional[str] = None
    right_to_work_document_ref: Optional[str] = None

class CreateCheckoutSessionSchema(BaseModel):
    booking_id: int

class PaymentRecordSchema(BaseModel):
    booking_id: int
    amount_gbp: float = Field(..., gt=0)
    method: str = Field(..., pattern="^(CASH|CARD|BANK_TRANSFER|REFUND|OTHER)$")
    reference: Optional[str] = None

class SupportCaseSchema(BaseModel):
    booking_id: Optional[int] = None
    customer_id: int
    subject: str = Field(..., min_length=3, max_length=160)
    description: str = Field(..., min_length=3, max_length=5000)

class SupportCaseUpdateSchema(BaseModel):
    status: str = Field(..., pattern="^(OPEN|IN_PROGRESS|RESOLVED)$")
    assigned_to: Optional[int] = None
    outcome: Optional[str] = None
    follow_up_at: Optional[str] = None

class StaffShiftSchema(BaseModel):
    staff_id: int
    shift_date: str
    start_time: str
    end_time: str

class TimeOffReviewSchema(BaseModel):
    status: str = Field(..., pattern="^(APPROVED|REJECTED)$")

# ==========================================================
# FASTAPI APPLICATION SETUP
# ==========================================================
# Rate limiter setup (slowapi)
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="CleanLondon API",
    description="UK Domestic Cleaning Platform - End-to-End API with Role-Based Access Control, Dynamic Pricing, and Geocoding",
    version="1.0.0",
    # Disable interactive API docs in production to prevent schema exposure
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)

# Attach rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

from app.routes.auth import router as auth_router
app.include_router(auth_router)
from app.routes.services import router as services_router
app.include_router(services_router)
from app.routes.bookings import router as bookings_router
app.include_router(bookings_router)
from app.routes.staff import router as staff_router
app.include_router(staff_router)
from app.routes.manager import router as manager_router
app.include_router(manager_router)
from app.routes.notifications import router as notifications_router
app.include_router(notifications_router)
from app.routes.location import router as location_router
app.include_router(location_router)
from app.routes.payments import router as payments_router
app.include_router(payments_router)

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Enforce defense-in-depth HTTP security response headers."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# ==========================================================
# HELPER FUNCTIONS FOR POSTCODES & DISTANCES
# ==========================================================
def normalize_london_postcode(raw_postcode: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9]', '', raw_postcode.upper())
    # Extract outcode (e.g. SW1A, E14, SE1, NW1); never silently use Central London.
    full_match = re.match(r'^([A-Z]{1,2}[0-9]{1,2}[A-Z]?)[0-9][A-Z]{2}$', cleaned)
    match = full_match or re.match(r'^([A-Z]{1,2}[0-9]{1,2}[A-Z]?)$', cleaned)
    if not match:
        raise HTTPException(status_code=422, detail="Enter a valid UK postcode")
    return match.group(1)


@lru_cache(maxsize=4096)
def _lookup_postcode_online(postcode: str) -> Optional[tuple[float, float, str]]:
    """Resolve an unlisted full postcode without maintaining a fragile local centroid list."""
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


def resolve_postcode_coords(raw_postcode: str) -> tuple[float, float, str]:
    """Resolve a postcode to a real centroid or reject it instead of using Central London."""
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

def haversine_distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)

def parse_time_slot_minutes(time_slot: str) -> tuple[int, int]:
    """
    Extracts start and end times in minutes from midnight.
    e.g. '10:00 - 13:00' -> (600, 780)
    """
    matches = re.findall(r'(\d{1,2}):(\d{2})', time_slot)
    if len(matches) >= 2:
        start_min = int(matches[0][0]) * 60 + int(matches[0][1])
        end_min = int(matches[1][0]) * 60 + int(matches[1][1])
        return start_min, end_min
    elif len(matches) == 1:
        start_min = int(matches[0][0]) * 60 + int(matches[0][1])
        return start_min, start_min + 180
    return 540, 720

def format_minutes_to_time(minutes: int) -> str:
    h = (minutes // 60) % 24
    m = minutes % 60
    return f"{h:02d}:{m:02d}"

def calculate_tfl_travel_buffer_minutes(postcode1: str, postcode2: str) -> int:
    """
    Computes realistic London TfL travel buffer between two postcodes:
    - Same outcode: 30 minutes (local transit / building access / turnover)
    - Different outcodes: 30 to 60 minutes based on distance across London (TfL Underground / bus)
    """
    out1 = normalize_london_postcode(postcode1)
    out2 = normalize_london_postcode(postcode2)
    if out1 == out2:
        return 30

    coords1 = resolve_postcode_coords(postcode1)
    coords2 = resolve_postcode_coords(postcode2)
    dist_miles = haversine_distance_miles(coords1[0], coords1[1], coords2[0], coords2[1])

    # Base 30 min + 5 min per mile across London boroughs, capped at 60 mins
    buffer_mins = int(30 + (dist_miles * 5))
    return min(60, max(30, buffer_mins))

def check_cleaner_schedule_conflict(
    cursor,
    cleaner_id: int,
    target_date: str,
    target_time_slot: str,
    target_postcode: str,
    exclude_booking_id: Optional[int] = None
) -> tuple[bool, Optional[str]]:
    """
    Checks if a cleaner has an overlapping active booking or insufficient TfL travel buffer
    on the target date.
    Returns (has_conflict, reason_string).
    """
    target_start, target_end = parse_time_slot_minutes(target_time_slot)

    query = """
        SELECT id, reference_code, scheduled_time_slot, postcode, address_line1, status
        FROM bookings
        WHERE staff_id = %s
          AND scheduled_date = %s
          AND status IN ('SCHEDULED', 'EN_ROUTE', 'IN_PROGRESS')
    """
    params: list = [cleaner_id, str(target_date)]
    if exclude_booking_id:
        query += " AND id != %s"
        params.append(exclude_booking_id)

    cursor.execute(query, tuple(params))
    existing_bookings = cursor.fetchall()

    for eb in existing_bookings:
        eb_start, eb_end = parse_time_slot_minutes(eb["scheduled_time_slot"])

        # 1. Direct Time Overlap Check
        if max(target_start, eb_start) < min(target_end, eb_end):
            return True, (
                f"Schedule Conflict: Cleaner is already assigned to active booking {eb['reference_code']} "
                f"at {eb['address_line1']} ({eb['scheduled_time_slot']}), directly overlapping with requested slot {target_time_slot}."
            )

        # 2. London TfL Travel Buffer Check
        buffer_mins = calculate_tfl_travel_buffer_minutes(target_postcode, eb["postcode"])

        # If target slot starts after existing booking ends
        if target_start >= eb_end:
            earliest_allowed_start = eb_end + buffer_mins
            if target_start < earliest_allowed_start:
                return True, (
                    f"TfL Travel Buffer Conflict: Cleaner finishes booking {eb['reference_code']} at {format_minutes_to_time(eb_end)} "
                    f"in {eb['postcode']} and requires a {buffer_mins}-min TfL travel buffer to reach {target_postcode}. "
                    f"Earliest available start time is {format_minutes_to_time(earliest_allowed_start)}."
                )

        # If target slot ends before existing booking starts
        elif target_end <= eb_start:
            latest_allowed_end = eb_start - buffer_mins
            if target_end > latest_allowed_end:
                return True, (
                    f"TfL Travel Buffer Conflict: Cleaner has booking {eb['reference_code']} starting at {format_minutes_to_time(eb_start)} "
                    f"in {eb['postcode']} and requires a {buffer_mins}-min TfL travel buffer from {target_postcode}. "
                    f"Target booking must conclude by {format_minutes_to_time(latest_allowed_end)}."
                )

    return False, None


def check_staff_availability(cursor, staff_id: int, target_date: str, target_time_slot: str) -> tuple[bool, Optional[str]]:
    """Apply configured weekly hours and holidays without restricting unconfigured cleaners."""
    try:
        target_day = datetime.date.fromisoformat(str(target_date)).weekday()
    except ValueError:
        return True, "Invalid scheduled date"

    cursor.execute(
        "SELECT reason FROM staff_holidays WHERE staff_id = %s AND holiday_date = %s",
        (staff_id, str(target_date)),
    )
    holiday = cursor.fetchone()
    if holiday:
        return True, f"Cleaner is unavailable on holiday ({holiday['reason'] or 'holiday'})."

    cursor.execute("""
        SELECT start_time, end_time
        FROM staff_weekly_availability
        WHERE staff_id = %s AND day_of_week = %s
    """, (staff_id, target_day))
    shift = cursor.fetchone()
    if not shift:
        return False, None

    start = datetime.datetime.strptime(str(shift["start_time"])[:5], "%H:%M")
    end = datetime.datetime.strptime(str(shift["end_time"])[:5], "%H:%M")
    start_min, end_min = parse_time_slot_minutes(target_time_slot)
    shift_start = start.hour * 60 + start.minute
    shift_end = end.hour * 60 + end.minute
    if start_min < shift_start or end_min > shift_end:
        return True, (
            f"Booking is outside the cleaner's configured shift "
            f"({str(shift['start_time'])[:5]}-{str(shift['end_time'])[:5]})."
        )
    return False, None

# ==========================================================
# 1. AUTHENTICATION & USER MANAGEMENT
# ==========================================================
# Legacy implementation retained temporarily for compatibility; route owned by app.routes.auth.
@limiter.limit("5/minute")
def register_user(request: Request, payload: UserRegisterSchema):
    with get_db() as conn:
        with conn.cursor() as cursor:
            # Check duplicate email
            cursor.execute("SELECT id FROM users WHERE email = %s", (payload.email,))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="An account with this email address already exists")

            # UK Security Standard: Strict role isolation on public registration.
            # All public registrations are strictly assigned 'customer' role. Any client-sent role is ignored.
            cursor.execute("SELECT id FROM roles WHERE name = 'customer'")
            role_row = cursor.fetchone()
            if not role_row:
                raise HTTPException(status_code=500, detail="Default customer role not configured in database")

            hashed = hash_password(payload.password)
            cursor.execute("""
                INSERT INTO users (role_id, email, password_hash, full_name, phone)
                VALUES (%s, %s, %s, %s, %s)
            """, (role_row["id"], payload.email, hashed, payload.full_name, payload.phone))
            user_id = cursor.lastrowid

            token = create_access_token({"user_id": user_id, "role": "customer"})
            return {
                "message": "User registered successfully",
                "access_token": token,
                "token_type": "bearer",
                "user": {
                    "id": user_id,
                    "email": payload.email,
                    "full_name": payload.full_name,
                    "role": "customer"
                }
            }

# Legacy implementation retained temporarily for compatibility; route owned by app.routes.auth.
@limiter.limit("10/minute")
def login_user(request: Request, payload: LoginSchema):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT u.id, u.email, u.password_hash, u.full_name, u.phone, u.avatar_url, r.name as role
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE u.email = %s
            """, (payload.email,))
            user = cursor.fetchone()
            if not user or not verify_password(payload.password, user["password_hash"]):
                raise HTTPException(status_code=401, detail="Invalid email or password")

            token = create_access_token({"user_id": user["id"], "role": user["role"]})
            return {
                "access_token": token,
                "token_type": "bearer",
                "user": {
                    "id": user["id"],
                    "email": user["email"],
                    "full_name": user["full_name"],
                    "role": user["role"],
                    "avatar_url": user["avatar_url"]
                }
            }

# Legacy implementation retained temporarily for compatibility; route owned by app.routes.auth.
def get_current_user_profile(user: dict = Depends(get_current_user)):
    return {"user": user}

# Legacy implementation retained temporarily for compatibility; route owned by app.routes.auth.
def google_oauth_login(payload: GoogleLoginSchema):
    """
    Google OAuth 2.0 Sign-In endpoint with Mock Mode Fallback.
    In production mode, verifies the Google JWT ID token with Google tokeninfo.
    In development mock mode, allows simulation but strictly blocks privilege escalation
    and prevents takeover of manager or staff accounts.
    """
    if IS_PRODUCTION and not MOCK_MODE:
        try:
            req = urllib.request.Request(
                f"https://oauth2.googleapis.com/tokeninfo?id_token={urllib.parse.quote(payload.id_token)}"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                token_data = json.loads(resp.read().decode("utf-8"))
            if token_data.get("aud") != GOOGLE_CLIENT_ID:
                raise HTTPException(status_code=401, detail="Invalid Google OAuth token audience")
            google_email = token_data.get("email")
            google_sub = token_data.get("sub")
            google_name = token_data.get("name") or "Google User"
            if not google_email:
                raise HTTPException(status_code=401, detail="Google token does not contain email")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid or expired Google OAuth ID token")
    else:
        google_email = payload.email or "google.user@cleanlondon.demo"
        google_name = payload.name or "Google London Client"
        google_sub = "google-sub-" + str(random.randint(1000, 9999))

    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT u.id, u.email, u.full_name, r.name as role, u.avatar_url, u.google_id
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE u.email = %s
            """, (google_email,))
            user = cursor.fetchone()

            if user:
                # Security Protection: Prevent takeover of administrative / staff accounts via Google OAuth
                if user["role"] in ["manager", "staff"]:
                    raise HTTPException(
                        status_code=403,
                        detail="Staff and Manager accounts cannot sign in via Google OAuth. Please use your email and password."
                    )
                user_id = user["id"]
                role_name = user["role"]
                if not user.get("google_id"):
                    cursor.execute("UPDATE users SET google_id = %s WHERE id = %s", (google_sub, user_id))
            else:
                cursor.execute("SELECT id FROM roles WHERE name = 'customer'")
                role_id = cursor.fetchone()["id"]
                cursor.execute("""
                    INSERT INTO users (role_id, email, password_hash, full_name, phone, google_id, avatar_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (role_id, google_email, hash_password("GoogleAuthPassword123!"), google_name, "+44 7900 112233", google_sub, "https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=150"))
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
                    "role": role_name
                }
            }

# Legacy implementation retained temporarily for compatibility; route owned by app.routes.auth.
def demo_switch_role(role: str = Body(..., embed=True)):
    """
    Convenience endpoint for review: Instantly generates a valid JWT
    for an explicitly approved demo account.
    Requires DEMO_AUTH_ENABLED=true in development or staging.
    """
    if not DEMO_AUTH_ENABLED or ENVIRONMENT.strip().lower() not in DEMO_AUTH_ALLOWED_ENVIRONMENTS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found"
        )
    approved_account = DEMO_ACCOUNT_ROLES.get(role.strip().lower())
    if not approved_account:
        raise HTTPException(status_code=400, detail="Invalid demo role.")
    target_email, expected_role = approved_account

    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT u.id, u.email, u.full_name, r.name as role, u.avatar_url, u.is_active
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE u.email = %s
            """, (target_email,))
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
                }
            }

# ==========================================================
# 2. SERVICES & DYNAMIC PRICING ENGINE
# ==========================================================
# Legacy implementation retained temporarily for compatibility.
def list_services():
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM services WHERE is_active = TRUE ORDER BY id ASC")
            return {"services": cursor.fetchall()}

# Legacy implementation retained temporarily for compatibility.
@limiter.limit("30/minute")
def calculate_quote(request: Request, payload: QuoteRequestSchema):
    """
    Dynamic London Cleaning Pricing Engine:
    - Analyzes postcode outcode
    - Applies property size formula (base + bedrooms + bathrooms)
    - Extras: Deep clean (+£20), Pets (+£10)
    - Estimates duration in hours
    """
    return _compute_quote(payload)


def _compute_quote(payload: QuoteRequestSchema) -> dict:
    """Internal pricing helper — called by the endpoint and by create_booking."""
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
        "currency": "GBP (£)"
    }

# ==========================================================
# 3. BOOKINGS (CUSTOMER)
# ==========================================================
# Legacy implementation retained temporarily for compatibility.
def create_booking(
    payload: BookingCreateSchema,
    request: Request,
    user: dict = Depends(require_role(["customer", "manager"])),
):
    # Calculate price based on service
    idempotency_key = get_idempotency_key(request, payload.idempotency_key)
    with get_db() as conn:
        with conn.cursor() as cursor:
            # 1. Idempotency Check: Return existing booking if same idempotency_key was already processed
            if idempotency_key:
                cursor.execute("""
                    SELECT id, customer_id, reference_code, total_price_gbp, status, payment_status, created_at
                    FROM bookings
                    WHERE idempotency_key = %s
                """, (idempotency_key,))
                existing_idem = cursor.fetchone()
                if existing_idem:
                    if existing_idem["customer_id"] != user["id"]:
                        raise HTTPException(
                            status_code=409,
                            detail="The supplied Idempotency-Key has already been used.",
                        )
                    return {
                        "message": "Booking request recognized (idempotent replay)",
                        "booking_id": existing_idem["id"],
                        "reference_code": existing_idem["reference_code"],
                        "total_price_gbp": float(existing_idem["total_price_gbp"]),
                        "status": existing_idem["status"],
                        "idempotent_replayed": True
                    }

            # 2. Duplicate Submission Guard: Prevent rapid double-clicks / identical overlapping bookings for same user
            cursor.execute("""
                SELECT id, reference_code, status, created_at
                FROM bookings
                WHERE customer_id = %s
                  AND address_line1 = %s
                  AND postcode = %s
                  AND scheduled_date = %s
                  AND scheduled_time_slot = %s
                  AND status IN ('SCHEDULED', 'EN_ROUTE', 'IN_PROGRESS')
            """, (user["id"], payload.address_line1, payload.postcode, payload.scheduled_date, payload.scheduled_time_slot))
            duplicate_active = cursor.fetchone()
            if duplicate_active:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Duplicate booking detected: You already have an active appointment "
                        f"(Ref: {duplicate_active['reference_code']}, Status: {duplicate_active['status']}) at this address "
                        f"for {payload.scheduled_date} ({payload.scheduled_time_slot}). "
                        f"Please manage your existing booking or select a different time slot."
                    )
                )

            cursor.execute("SELECT * FROM services WHERE id = %s", (payload.service_id,))
            service = cursor.fetchone()
            if not service:
                raise HTTPException(status_code=404, detail="Selected service not found")

            # Coordinate resolution
            coords = resolve_postcode_coords(payload.postcode)
            lat, lon = coords[0], coords[1]

            # Price calculations
            quote = _compute_quote(QuoteRequestSchema(
                postcode=payload.postcode,
                service_id=payload.service_id,
                property_type=payload.property_type,
                bedrooms=payload.bedrooms,
                bathrooms=payload.bathrooms,
                has_pets=payload.has_pets,
                deep_clean=payload.deep_clean_requested,
                eco_products=payload.eco_cleaning_products
            ))

            reference_code = None
            for _ in range(10):
                candidate = f"CL-{datetime.datetime.now().year}-{random.randint(100000, 999999)}"
                cursor.execute("SELECT id FROM bookings WHERE reference_code = %s", (candidate,))
                if not cursor.fetchone():
                    reference_code = candidate
                    break
            if reference_code is None:
                raise HTTPException(
                    status_code=409,
                    detail="Could not generate a unique booking reference. Please retry.",
                )

            # UK GDPR Sensitive Physical Access Data Encryption at Rest (AES-256)
            encrypted_access_notes = encrypt_sensitive_data(payload.access_notes)

            cursor.execute("""
                INSERT INTO bookings (
                    reference_code, idempotency_key, customer_id, service_id,
                    property_type, bedrooms, bathrooms, has_pets, deep_clean_requested, eco_cleaning_products,
                    address_line1, address_line2, city, postcode, latitude, longitude,
                    key_handling_type, access_notes, scheduled_date, scheduled_time_slot,
                    duration_hours, hourly_rate_gbp, total_price_gbp, status, payment_status
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, 'SCHEDULED', 'PENDING'
                )
            """, (
                reference_code, idempotency_key, user["id"], payload.service_id,
                payload.property_type, payload.bedrooms, payload.bathrooms, payload.has_pets,
                payload.deep_clean_requested, payload.eco_cleaning_products,
                payload.address_line1, payload.address_line2, payload.city, payload.postcode,
                lat, lon, payload.key_handling_type, encrypted_access_notes,
                payload.scheduled_date, payload.scheduled_time_slot,
                quote["estimated_duration_hours"], quote["hourly_equivalent_gbp"], quote["total_price_gbp"]
            ))
            booking_id = cursor.lastrowid

            # Add status audit log
            cursor.execute("""
                INSERT INTO booking_status_logs (booking_id, changed_by_user_id, previous_status, new_status, notes)
                VALUES (%s, %s, NULL, 'SCHEDULED', 'Booking created by customer')
            """, (booking_id, user["id"]))

            cursor.execute("SELECT email FROM users WHERE id = %s", (user["id"],))
            recipient = cursor.fetchone()
            if recipient:
                queue_notification(
                    cursor,
                    user["id"],
                    recipient["email"],
                    f"CleanLondon booking confirmed: {reference_code}",
                    f"Your cleaning booking {reference_code} is scheduled for "
                    f"{payload.scheduled_date} ({payload.scheduled_time_slot}). "
                    f"Payment remains pending until Stripe confirms it.",
                )

            return {
                "message": "Booking confirmed successfully",
                "booking_id": booking_id,
                "reference_code": reference_code,
                "total_price_gbp": quote["total_price_gbp"],
                "status": "SCHEDULED",
                "idempotent_replayed": False
            }

# Legacy implementation retained temporarily for compatibility.
def get_my_bookings(user: dict = Depends(require_role(["customer"]))):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT b.*, s.name as service_name, u.full_name as staff_name, u.phone as staff_phone,
                       u.avatar_url as staff_avatar_url, sp.rating_avg as staff_rating,
                       sp.verified_dbs as staff_dbs_verified,
                       r.rating as review_rating, r.comment as review_comment
                FROM bookings b
                JOIN services s ON b.service_id = s.id
                LEFT JOIN users u ON b.staff_id = u.id
                LEFT JOIN staff_profiles sp ON b.staff_id = sp.user_id
                LEFT JOIN reviews r ON b.id = r.booking_id
                WHERE b.customer_id = %s
                ORDER BY b.scheduled_date DESC, b.id DESC
            """, (user["id"],))
            bookings = cursor.fetchall()
            for b in bookings:
                b["access_notes"] = decrypt_sensitive_data(b.get("access_notes"))
            return {"bookings": bookings}

# Legacy implementation retained temporarily for compatibility.
def cancel_booking(
    booking_id: int,
    payload: Optional[CancelBookingSchema] = None,
    user: dict = Depends(require_role(["customer", "manager"]))
):
    """
    UK Consumer Protection & Booking Cancellation Workflow:
    - Enforces strict late-cancellation penalty policy:
      * Free cancellation & 100% refund when cancelled >24 hours before scheduled appointment.
      * 50% late-cancellation fee retained and 50% refund when cancelled within 24 hours of appointment.
      * Appointments cannot be cancelled after the scheduled start time has arrived.
    - Frees up assigned cleaner and logs audit trail.
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM bookings WHERE id = %s", (booking_id,))
            booking = cursor.fetchone()
            if not booking:
                raise HTTPException(status_code=404, detail="Booking not found")

            # Ownership check: Customers can only cancel their own bookings
            if user["role"] == "customer" and booking["customer_id"] != user["id"]:
                raise HTTPException(status_code=403, detail="You can only cancel your own bookings")

            if booking["status"] == "CANCELLED":
                raise HTTPException(status_code=400, detail="This booking has already been cancelled")

            if booking["status"] in ["EN_ROUTE", "IN_PROGRESS", "COMPLETED"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot cancel booking: Cleaner is already '{booking['status']}'. Cancellations are only permitted while status is 'SCHEDULED'."
                )

            # Parse scheduled start time
            times = re.findall(r'(\d{1,2}:\d{2})', booking["scheduled_time_slot"])
            start_time_str = times[0] if times else "09:00"
            try:
                service_dt = datetime.datetime.strptime(f"{booking['scheduled_date']} {start_time_str}:00", "%Y-%m-%d %H:%M:%S")
            except Exception:
                service_dt = datetime.datetime.combine(booking["scheduled_date"], datetime.time(9, 0))

            now = datetime.datetime.now()
            hours_until_service = (service_dt - now).total_seconds() / 3600.0

            if hours_until_service < 0:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot cancel an appointment whose scheduled start time has already passed."
                )

            total_price = float(booking["total_price_gbp"])
            reason = payload.reason if payload and payload.reason else "Cancelled by customer"

            # Late cancellation fee rule:
            # > 24 hours: Full refund, 0 fee
            # < 24 hours: 50% penalty fee, 50% refund
            if hours_until_service >= 24.0:
                cancellation_fee = 0.00
                refund_amount = total_price
                policy_note = f"Free cancellation (>24h notice). Full refund of £{refund_amount:.2f} issued."
                policy_applied = "FREE_CANCELLATION"
            else:
                cancellation_fee = round(total_price * 0.50, 2)
                refund_amount = round(total_price - cancellation_fee, 2)
                policy_note = f"Late cancellation (<24h notice): 50% fee (£{cancellation_fee:.2f}) retained. Refund of £{refund_amount:.2f} issued."
                policy_applied = "50_PERCENT_LATE_FEE"

            new_payment_status = "REFUNDED" if booking["payment_status"] == "PAID" else "PENDING"

            if booking["payment_status"] == "PAID" and refund_amount > 0:
                payment_intent_id = booking.get("stripe_payment_intent_id")
                is_mock_stripe = not STRIPE_SECRET_KEY or "mock" in STRIPE_SECRET_KEY.lower()
                if not is_mock_stripe and not payment_intent_id:
                    raise HTTPException(
                        status_code=409,
                        detail="Paid booking has no payment reference; refund cannot be safely issued.",
                    )
                if not is_mock_stripe and payment_intent_id:
                    try:
                        stripe.Refund.create(
                            payment_intent=payment_intent_id,
                            amount=int(round(refund_amount * 100)),
                            metadata={
                                "booking_id": str(booking_id),
                                "policy": policy_applied,
                            },
                        )
                    except stripe.error.StripeError as exc:
                        raise HTTPException(
                            status_code=502,
                            detail="The payment provider rejected the refund. The booking was not cancelled.",
                        ) from exc

            cursor.execute("""
                UPDATE bookings
                SET status = 'CANCELLED',
                    payment_status = %s,
                    cancelled_at = NOW(),
                    cancellation_fee_gbp = %s,
                    refund_amount_gbp = %s,
                    cancellation_reason = %s,
                    staff_id = NULL
                WHERE id = %s
            """, (new_payment_status, cancellation_fee, refund_amount, f"{reason} | {policy_note}", booking_id))

            cursor.execute("""
                INSERT INTO booking_status_logs (booking_id, changed_by_user_id, previous_status, new_status, notes)
                VALUES (%s, %s, %s, 'CANCELLED', %s)
            """, (booking_id, user["id"], booking["status"], f"Booking cancelled. {policy_note} Reason: {reason}"))

            queue_notification(
                cursor,
                user["id"],
                user["email"],
                f"CleanLondon booking cancelled: {booking['reference_code']}",
                f"Your booking was cancelled. {policy_note}",
            )

            return {
                "message": "Booking cancelled successfully",
                "booking_id": booking_id,
                "reference_code": booking["reference_code"],
                "status": "CANCELLED",
                "hours_until_service": round(hours_until_service, 1),
                "total_price_gbp": total_price,
                "cancellation_fee_gbp": cancellation_fee,
                "refund_amount_gbp": refund_amount,
                "policy_applied": policy_applied,
                "policy_note": policy_note
            }

# Legacy implementation retained temporarily for compatibility.
def reschedule_booking(
    booking_id: int,
    payload: RescheduleBookingSchema,
    user: dict = Depends(require_role(["customer", "manager"]))
):
    """
    Rescheduling Workflow:
    - Allows customer or manager to select a new appointment date & time slot.
    - Re-validates that new slot is strictly in the future.
    - Checks assigned cleaner availability on new slot (unassigns cleaner with audit note if conflict arises).
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM bookings WHERE id = %s", (booking_id,))
            booking = cursor.fetchone()
            if not booking:
                raise HTTPException(status_code=404, detail="Booking not found")

            if user["role"] == "customer" and booking["customer_id"] != user["id"]:
                raise HTTPException(status_code=403, detail="You can only reschedule your own bookings")

            if booking["status"] != "SCHEDULED":
                raise HTTPException(
                    status_code=400,
                    detail=f"Only bookings in 'SCHEDULED' status can be rescheduled. Current status: '{booking['status']}'."
                )

            # Validate new appointment date is in future
            times = re.findall(r'(\d{1,2}:\d{2})', payload.new_time_slot)
            start_str = times[0] if times else "09:00"
            try:
                new_dt = datetime.datetime.strptime(f"{payload.new_date} {start_str}:00", "%Y-%m-%d %H:%M:%S")
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid date or time slot format. Use YYYY-MM-DD and HH:MM - HH:MM.")

            if new_dt <= datetime.datetime.now():
                raise HTTPException(status_code=400, detail="New scheduled date and time must be in the future")

            # Check if currently assigned cleaner has conflict on new slot
            reassigned_note = ""
            staff_id = booking["staff_id"]
            if staff_id:
                has_conflict, reason = check_cleaner_schedule_conflict(
                    cursor, staff_id, payload.new_date, payload.new_time_slot, booking["postcode"], exclude_booking_id=booking_id
                )
                if has_conflict:
                    staff_id = None
                    reassigned_note = " (Assigned cleaner unavailable on new slot; cleaner unassigned for re-dispatch)"

            cursor.execute("""
                UPDATE bookings
                SET scheduled_date = %s,
                    scheduled_time_slot = %s,
                    staff_id = %s
                WHERE id = %s
            """, (payload.new_date, payload.new_time_slot, staff_id, booking_id))

            cursor.execute("""
                INSERT INTO booking_status_logs (booking_id, changed_by_user_id, previous_status, new_status, notes)
                VALUES (%s, %s, 'SCHEDULED', 'SCHEDULED', %s)
            """, (
                booking_id, user["id"],
                f"Rescheduled from {booking['scheduled_date']} ({booking['scheduled_time_slot']}) to {payload.new_date} ({payload.new_time_slot}){reassigned_note}."
            ))

            queue_notification(
                cursor,
                user["id"],
                user["email"],
                f"CleanLondon booking rescheduled: {booking['reference_code']}",
                f"Your booking is now scheduled for {payload.new_date} ({payload.new_time_slot}).",
            )

            return {
                "message": f"Booking rescheduled successfully to {payload.new_date} ({payload.new_time_slot}){reassigned_note}",
                "booking_id": booking_id,
                "reference_code": booking["reference_code"],
                "scheduled_date": payload.new_date,
                "scheduled_time_slot": payload.new_time_slot,
                "cleaner_assigned": staff_id is not None
            }

# Legacy implementation retained temporarily for compatibility.
def review_booking(booking_id: int, payload: ReviewCreateSchema, user: dict = Depends(require_role(["customer"]))):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM bookings WHERE id = %s AND customer_id = %s", (booking_id, user["id"]))
            booking = cursor.fetchone()
            if not booking:
                raise HTTPException(status_code=404, detail="Booking not found or not owned by you")
            if booking["status"] != "COMPLETED":
                raise HTTPException(status_code=400, detail="Only completed bookings can be reviewed")
            if not booking["staff_id"]:
                raise HTTPException(status_code=400, detail="Cannot review a booking without assigned cleaner")

            # Check if review already exists
            cursor.execute("SELECT id FROM reviews WHERE booking_id = %s", (booking_id,))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="A review has already been submitted for this booking")

            cursor.execute("""
                INSERT INTO reviews (booking_id, customer_id, staff_id, rating, comment, punctuality_score, thoroughness_score)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (booking_id, user["id"], booking["staff_id"], payload.rating, payload.comment, payload.punctuality_score, payload.thoroughness_score))

            # Recalculate staff rating
            cursor.execute("""
                SELECT AVG(rating) as avg_rating, COUNT(*) as count_rating
                FROM reviews WHERE staff_id = %s
            """, (booking["staff_id"],))
            agg = cursor.fetchone()
            cursor.execute("""
                UPDATE staff_profiles
                SET rating_avg = %s, rating_count = %s
                WHERE user_id = %s
            """, (agg["avg_rating"], agg["count_rating"], booking["staff_id"]))

            return {"message": "Thank you! Your review has been published.", "rating": payload.rating}

# ==========================================================
# 4. STAFF / CLEANER WORKFLOW
# ==========================================================
# Legacy implementation retained temporarily for compatibility.
def get_staff_jobs(user: dict = Depends(require_role(["staff"]))):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT b.*, s.name as service_name, c.full_name as customer_name, c.phone as customer_phone
                FROM bookings b
                JOIN services s ON b.service_id = s.id
                JOIN users c ON b.customer_id = c.id
                WHERE b.staff_id = %s
                ORDER BY b.scheduled_date ASC, b.id ASC
            """, (user["id"],))
            jobs = cursor.fetchall()
            for job in jobs:
                # UK GDPR & Least Privilege: Mask residential PIN / access codes for staff until EN_ROUTE
                job["access_notes"] = mask_access_notes_for_staff(job["status"], job.get("access_notes"))
            return {"jobs": jobs}

# Legacy implementation retained temporarily for compatibility.
def update_job_status(booking_id: int, payload: StatusUpdateSchema, user: dict = Depends(require_role(["staff", "manager"]))):
    """
    Sequential State Machine:
    SCHEDULED -> EN_ROUTE -> IN_PROGRESS -> COMPLETED
    """
    valid_transitions = {
        "PENDING": ["APPROVED", "REJECTED", "CANCELLED"],
        "APPROVED": ["CONFIRMED", "REJECTED", "CANCELLED"],
        "CONFIRMED": ["EN_ROUTE", "CANCELLED"],
        "REJECTED": [],
        "CANCELLED": [],
        "SCHEDULED": ["EN_ROUTE", "CANCELLED"],
        "EN_ROUTE": ["IN_PROGRESS", "CANCELLED"],
        "IN_PROGRESS": ["COMPLETED"],
        "COMPLETED": [],
        "CANCELLED": []
    }

    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM bookings WHERE id = %s", (booking_id,))
            booking = cursor.fetchone()
            if not booking:
                raise HTTPException(status_code=404, detail="Booking not found")

            # Check ownership if staff
            if user["role"] == "staff" and booking["staff_id"] != user["id"]:
                raise HTTPException(status_code=403, detail="You can only update status for jobs assigned to you")

            current_status = booking["status"]
            target_status = payload.status.upper()

            if target_status not in valid_transitions.get(current_status, []):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid transition from '{current_status}' to '{target_status}'. Allowed next: {valid_transitions.get(current_status)}"
                )

            # Time Guardrail: Prevent advancing status before scheduled appointment time
            if target_status in ["EN_ROUTE", "IN_PROGRESS", "COMPLETED"]:
                times = re.findall(r'(\d{1,2}:\d{2})', booking["scheduled_time_slot"])
                start_time_str = times[0] if times else "08:00"
                try:
                    scheduled_dt = datetime.datetime.strptime(
                        f"{booking['scheduled_date']} {start_time_str}:00", "%Y-%m-%d %H:%M:%S"
                    )
                except Exception:
                    scheduled_dt = datetime.datetime.combine(booking["scheduled_date"], datetime.time(8, 0))

                now = datetime.datetime.now()
                hours_until_start = (scheduled_dt - now).total_seconds() / 3600.0

                # 1. Cleaner cannot be EN_ROUTE more than 2 hours before scheduled start (and not on a future date)
                if target_status == "EN_ROUTE" and hours_until_start > 2.0:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Time Guardrail: Cannot mark job 'EN_ROUTE' prematurely. "
                            f"Appointment is scheduled for {booking['scheduled_date']} at {start_time_str} "
                            f"({round(hours_until_start, 1)} hours away). Cleaners can only go en route within 2 hours of scheduled start."
                        )
                    )

                # 2. Cleaner cannot be IN_PROGRESS or COMPLETED before scheduled start time
                if target_status in ["IN_PROGRESS", "COMPLETED"] and hours_until_start > 0.25:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Time Guardrail: Cannot mark job '{target_status}' before the scheduled appointment time. "
                            f"Appointment is scheduled for {booking['scheduled_date']} at {start_time_str} "
                            f"({round(hours_until_start, 1)} hours away)."
                        )
                    )

            # Update status
            payment_status = "PAID" if target_status == "COMPLETED" else booking["payment_status"]
            cursor.execute("""
                UPDATE bookings
                SET status = %s, payment_status = %s
                WHERE id = %s
            """, (target_status, payment_status, booking_id))

            # Audit log
            cursor.execute("""
                INSERT INTO booking_status_logs (booking_id, changed_by_user_id, previous_status, new_status, notes)
                VALUES (%s, %s, %s, %s, %s)
            """, (booking_id, user["id"], current_status, target_status, payload.notes or f"Status changed to {target_status}"))

            cursor.execute("""
                SELECT u.id, u.email, u.full_name
                FROM users u
                WHERE u.id IN (%s, %s)
            """, (booking["customer_id"], booking["staff_id"] or 0))
            for recipient in cursor.fetchall():
                queue_notification(
                    cursor,
                    recipient["id"],
                    recipient["email"],
                    f"CleanLondon booking {booking_id}: {target_status}",
                    f"Booking {booking_id} is now {target_status.replace('_', ' ')}.",
                )

            return {
                "message": f"Job status updated to {target_status}",
                "booking_id": booking_id,
                "previous_status": current_status,
                "current_status": target_status
            }


# Legacy implementation retained temporarily for compatibility.
def get_staff_schedule(user: dict = Depends(require_role(["staff"]))):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT day_of_week, TIME_FORMAT(start_time, '%%H:%%i') AS start_time,
                       TIME_FORMAT(end_time, '%%H:%%i') AS end_time
                FROM staff_weekly_availability
                WHERE staff_id = %s ORDER BY day_of_week
            """, (user["id"],))
            weekly = cursor.fetchall()
            cursor.execute("""
                SELECT DATE_FORMAT(holiday_date, '%%Y-%%m-%%d') AS holiday_date, reason
                FROM staff_holidays
                WHERE staff_id = %s AND holiday_date >= CURRENT_DATE()
                ORDER BY holiday_date
            """, (user["id"],))
            holidays = cursor.fetchall()
            return {"weekly_availability": weekly, "holidays": holidays}


# Legacy implementation retained temporarily for compatibility.
def update_staff_schedule(
    schedule: List[WeeklyAvailabilitySchema],
    user: dict = Depends(require_role(["staff"])),
):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM staff_weekly_availability WHERE staff_id = %s", (user["id"],))
            for shift in schedule:
                try:
                    start = datetime.datetime.strptime(shift.start_time, "%H:%M")
                    end = datetime.datetime.strptime(shift.end_time, "%H:%M")
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail="Shift times must use HH:MM format") from exc
                if end <= start:
                    raise HTTPException(status_code=422, detail="Shift end time must be after start time")
                cursor.execute("""
                    INSERT INTO staff_weekly_availability
                        (staff_id, day_of_week, start_time, end_time)
                    VALUES (%s, %s, %s, %s)
                """, (user["id"], shift.day_of_week, shift.start_time, shift.end_time))
            return {"message": "Weekly availability saved", "days_configured": len(schedule)}


# Legacy implementation retained temporarily for compatibility.
def add_staff_holiday(payload: HolidaySchema, user: dict = Depends(require_role(["staff"]))):
    try:
        datetime.date.fromisoformat(payload.holiday_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Holiday date must use YYYY-MM-DD format") from exc
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO staff_holidays (staff_id, holiday_date, reason)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE reason = VALUES(reason)
            """, (user["id"], payload.holiday_date, payload.reason))
            return {"message": "Holiday saved", "holiday_date": payload.holiday_date}


# Legacy implementation retained temporarily for compatibility.
def remove_staff_holiday(holiday_date: str, user: dict = Depends(require_role(["staff"]))):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM staff_holidays WHERE staff_id = %s AND holiday_date = %s",
                (user["id"], holiday_date),
            )
            return {"message": "Holiday removed", "holiday_date": holiday_date}


# Legacy implementation retained temporarily for compatibility.
def get_staff_earnings(user: dict = Depends(require_role(["staff"]))):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, reference_code, scheduled_date, total_price_gbp, duration_hours
                FROM bookings
                WHERE staff_id = %s AND status = 'COMPLETED'
                ORDER BY scheduled_date DESC, id DESC
            """, (user["id"],))
            jobs = cursor.fetchall()
            gross = sum(float(job["total_price_gbp"]) for job in jobs)
            cleaner_share = round(gross * 0.70, 2)
            today = datetime.date.today().isoformat()
            return {
                "currency": "GBP",
                "completed_jobs": len(jobs),
                "gross_bookings_gbp": round(gross, 2),
                "cleaner_earnings_gbp": cleaner_share,
                "today_earnings_gbp": round(sum(float(job["total_price_gbp"]) * 0.70 for job in jobs if str(job["scheduled_date"])[:10] == today), 2),
                "completed_hours": round(sum(float(job["duration_hours"] or 0) for job in jobs), 2),
                "jobs": jobs,
            }


# Legacy notification implementation retained temporarily for compatibility.
def get_my_notifications(user: dict = Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, channel, subject, body, status, created_at, sent_at
                FROM notification_outbox
                WHERE recipient_user_id = %s
                ORDER BY created_at DESC LIMIT 50
            """, (user["id"],))
            return {"notifications": cursor.fetchall()}

# ==========================================================
# 5. MANAGER / ADMIN DASHBOARD & DISPATCH
# ==========================================================
# Legacy implementation retained temporarily for compatibility.
def get_manager_kpis(user: dict = Depends(require_role(["manager"]))):
    with get_db() as conn:
        with conn.cursor() as cursor:
            # Booking value is separate from collected revenue.
            cursor.execute("""
                SELECT COALESCE(SUM(total_price_gbp), 0) as daily_revenue
                FROM bookings
                WHERE scheduled_date = CURRENT_DATE() AND status != 'CANCELLED'
            """)
            daily_rev = float(cursor.fetchone()["daily_revenue"])

            cursor.execute("""
                SELECT COALESCE(SUM(total_price_gbp), 0) as total_revenue
                FROM bookings
                WHERE status != 'CANCELLED'
            """)
            total_booking_value = float(cursor.fetchone()["total_revenue"])

            cursor.execute("""
                SELECT
                    COALESCE(SUM(CASE WHEN scheduled_date = CURRENT_DATE()
                                      AND payment_status = 'PAID'
                                      THEN total_price_gbp ELSE 0 END), 0) AS collected_today,
                    COALESCE(SUM(CASE WHEN scheduled_date >= DATE_FORMAT(CURRENT_DATE(), '%Y-%m-01')
                                      AND scheduled_date < DATE_ADD(DATE_FORMAT(CURRENT_DATE(), '%Y-%m-01'), INTERVAL 1 MONTH)
                                      AND payment_status = 'PAID'
                                      THEN total_price_gbp ELSE 0 END), 0) AS collected_month,
                    COALESCE(SUM(CASE WHEN payment_status IN ('PENDING', 'AUTHORIZED')
                                      AND status != 'CANCELLED'
                                      THEN total_price_gbp ELSE 0 END), 0) AS unpaid_amount
                FROM bookings
            """)
            payment_totals = cursor.fetchone()

            cursor.execute("""
                SELECT COUNT(*) AS completed_today
                FROM bookings
                WHERE scheduled_date = CURRENT_DATE() AND status = 'COMPLETED'
            """)
            completed_today = cursor.fetchone()["completed_today"] or 0

            # Booking Counts
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_bookings,
                    SUM(CASE WHEN scheduled_date = CURRENT_DATE() THEN 1 ELSE 0 END) as bookings_today,
                    SUM(CASE WHEN status = 'SCHEDULED' THEN 1 ELSE 0 END) as scheduled_count,
                    SUM(CASE WHEN status = 'EN_ROUTE' THEN 1 ELSE 0 END) as en_route_count,
                    SUM(CASE WHEN status = 'IN_PROGRESS' THEN 1 ELSE 0 END) as in_progress_count,
                    SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed_count,
                    SUM(CASE WHEN staff_id IS NULL AND status = 'SCHEDULED' THEN 1 ELSE 0 END) as unassigned_count
                FROM bookings
            """)
            counts = cursor.fetchone()

            # Staff Utilization
            cursor.execute("SELECT COUNT(*) as total_staff FROM users WHERE role_id = 2")
            total_cleaners = cursor.fetchone()["total_staff"] or 1

            cursor.execute("""
                SELECT COUNT(DISTINCT staff_id) as active_cleaners
                FROM bookings
                WHERE scheduled_date = CURRENT_DATE() AND status IN ('SCHEDULED', 'EN_ROUTE', 'IN_PROGRESS')
            """)
            active_cleaners = cursor.fetchone()["active_cleaners"] or 0
            utilization_rate = round((active_cleaners / total_cleaners) * 100, 1)

            return {
                "kpis": {
                    "daily_revenue_gbp": round(daily_rev, 2),
                    "total_revenue_gbp": round(total_booking_value, 2),
                    "collected_today_gbp": float(payment_totals["collected_today"] or 0),
                    "collected_month_gbp": float(payment_totals["collected_month"] or 0),
                    "unpaid_amount_gbp": float(payment_totals["unpaid_amount"] or 0),
                    "overdue_amount_gbp": None,
                    "bookings_today": counts["bookings_today"] or 0,
                    "completed_today": completed_today,
                    "staff_utilization_pct": utilization_rate,
                    "total_cleaners": total_cleaners,
                    "active_cleaners_today": active_cleaners,
                    "unassigned_jobs": counts["unassigned_count"]
                },
                "status_breakdown": counts
            }

# Legacy manager implementation retained temporarily for compatibility.
def list_payment_records(user: dict = Depends(require_role(["manager"]))):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT p.*, b.reference_code
                FROM payment_records p
                JOIN bookings b ON b.id = p.booking_id
                ORDER BY p.recorded_at DESC
            """)
            return {"payments": cursor.fetchall()}

# Legacy manager implementation retained temporarily for compatibility.
def record_payment(payload: PaymentRecordSchema, user: dict = Depends(require_role(["manager"]))):
    with get_transaction() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM bookings WHERE id = %s FOR UPDATE", (payload.booking_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Booking not found")
            cursor.execute("""
                INSERT INTO payment_records
                    (booking_id, amount_gbp, method, status, reference, recorded_by)
                VALUES (%s, %s, %s, 'RECORDED', %s, %s)
            """, (payload.booking_id, payload.amount_gbp, payload.method, payload.reference, user["id"]))
            record_id = cursor.lastrowid
            log_activity(cursor, user, "payment_recorded", "payment", record_id,
                         after={"booking_id": payload.booking_id, "amount_gbp": payload.amount_gbp,
                               "method": payload.method})
            return {"message": "Payment recorded", "payment_id": record_id}

# Legacy manager implementation retained temporarily for compatibility.
def verify_payment(payment_id: int, user: dict = Depends(require_role(["manager"]))):
    with get_transaction() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM payment_records WHERE id = %s FOR UPDATE", (payment_id,))
            payment = cursor.fetchone()
            if not payment:
                raise HTTPException(status_code=404, detail="Payment not found")
            cursor.execute("""
                UPDATE payment_records
                SET status = 'VERIFIED', verified_by = %s, verified_at = NOW()
                WHERE id = %s
            """, (user["id"], payment_id))
            log_activity(cursor, user, "payment_verified", "payment", payment_id,
                         before=payment, after={"status": "VERIFIED"})
            return {"message": "Payment verified", "payment_id": payment_id}

# Legacy manager implementation retained temporarily for compatibility.
def list_support_cases(user: dict = Depends(require_role(["manager"]))):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT sc.*, c.full_name AS customer_name, cl.full_name AS assigned_name
                FROM support_cases sc
                JOIN users c ON c.id = sc.customer_id
                LEFT JOIN users cl ON cl.id = sc.assigned_to
                ORDER BY sc.created_at DESC
            """)
            return {"cases": cursor.fetchall()}

# Legacy manager implementation retained temporarily for compatibility.
def create_support_case(payload: SupportCaseSchema, user: dict = Depends(require_role(["manager"]))):
    with get_transaction() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO support_cases (booking_id, customer_id, subject, description)
                VALUES (%s, %s, %s, %s)
            """, (payload.booking_id, payload.customer_id, payload.subject, payload.description))
            case_id = cursor.lastrowid
            log_activity(cursor, user, "support_case_created", "support_case", case_id,
                         after={"customer_id": payload.customer_id, "subject": payload.subject})
            return {"message": "Support case created", "case_id": case_id}

# Legacy manager implementation retained temporarily for compatibility.
def update_support_case(case_id: int, payload: SupportCaseUpdateSchema,
                        user: dict = Depends(require_role(["manager"]))):
    with get_transaction() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM support_cases WHERE id = %s FOR UPDATE", (case_id,))
            before = cursor.fetchone()
            if not before:
                raise HTTPException(status_code=404, detail="Support case not found")
            cursor.execute("""
                UPDATE support_cases
                SET status = %s, assigned_to = %s, outcome = %s,
                    follow_up_at = %s
                WHERE id = %s
            """, (payload.status, payload.assigned_to, payload.outcome,
                  payload.follow_up_at, case_id))
            log_activity(cursor, user, "support_case_updated", "support_case", case_id,
                         before=before, after={"status": payload.status,
                                               "assigned_to": payload.assigned_to,
                                               "outcome": payload.outcome})
            return {"message": "Support case updated", "case_id": case_id}

# Legacy manager implementation retained temporarily for compatibility.
def list_manager_notifications(user: dict = Depends(require_role(["manager"]))):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, subject, body, status, is_read, priority, deep_link, created_at
                FROM notification_outbox
                WHERE recipient_user_id = %s OR recipient_user_id IS NULL
                ORDER BY created_at DESC LIMIT 100
            """, (user["id"],))
            notifications = cursor.fetchall()
            unread = sum(1 for item in notifications if not item["is_read"])
            return {"notifications": notifications, "unread_count": unread}

# Legacy manager implementation retained temporarily for compatibility.
def mark_notification_read(notification_id: int, user: dict = Depends(require_role(["manager"]))):
    with get_transaction() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE notification_outbox SET is_read = TRUE
                WHERE id = %s AND (recipient_user_id = %s OR recipient_user_id IS NULL)
            """, (notification_id, user["id"]))
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Notification not found")
            log_activity(cursor, user, "notification_read", "notification", notification_id)
            return {"message": "Notification marked as read"}

# Legacy manager implementation retained temporarily for compatibility.
def list_audit_log(user: dict = Depends(require_role(["manager"]))):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT * FROM activity_audit_log
                ORDER BY created_at DESC LIMIT 200
            """)
            return {"audit": cursor.fetchall()}

# Legacy manager implementation retained temporarily for compatibility.
def list_shifts(user: dict = Depends(require_role(["manager"]))):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT ss.*, u.full_name AS staff_name
                FROM staff_shifts ss
                JOIN users u ON u.id = ss.staff_id
                ORDER BY ss.shift_date, ss.start_time
            """)
            return {"shifts": cursor.fetchall()}

# Legacy manager implementation retained temporarily for compatibility.
def create_shift(payload: StaffShiftSchema, user: dict = Depends(require_role(["manager"]))):
    with get_transaction() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO staff_shifts
                    (staff_id, shift_date, start_time, end_time, created_by)
                VALUES (%s, %s, %s, %s, %s)
            """, (payload.staff_id, payload.shift_date, payload.start_time,
                  payload.end_time, user["id"]))
            shift_id = cursor.lastrowid
            log_activity(cursor, user, "shift_created", "shift", shift_id,
                         after={"staff_id": payload.staff_id, "shift_date": payload.shift_date,
                               "start_time": payload.start_time, "end_time": payload.end_time})
            return {"message": "Shift created", "shift_id": shift_id}

# Legacy manager implementation retained temporarily for compatibility.
def list_time_off(user: dict = Depends(require_role(["manager"]))):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT t.*, u.full_name AS staff_name
                FROM staff_time_off t
                JOIN users u ON u.id = t.staff_id
                ORDER BY t.created_at DESC
            """)
            return {"time_off": cursor.fetchall()}

# Legacy manager implementation retained temporarily for compatibility.
def review_time_off(time_off_id: int, payload: TimeOffReviewSchema,
                    user: dict = Depends(require_role(["manager"]))):
    with get_transaction() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM staff_time_off WHERE id = %s FOR UPDATE", (time_off_id,))
            before = cursor.fetchone()
            if not before:
                raise HTTPException(status_code=404, detail="Time-off request not found")
            cursor.execute("""
                UPDATE staff_time_off
                SET status = %s, reviewed_by = %s, reviewed_at = NOW()
                WHERE id = %s
            """, (payload.status, user["id"], time_off_id))
            log_activity(cursor, user, "time_off_reviewed", "time_off", time_off_id,
                         before=before, after={"status": payload.status})
            return {"message": "Time-off request reviewed", "time_off_id": time_off_id}

# Legacy manager implementation retained temporarily for compatibility.
def get_settings(user: dict = Depends(require_role(["manager"]))):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT setting_key, setting_value, updated_at FROM business_settings")
            return {"settings": cursor.fetchall()}

# Legacy manager implementation retained temporarily for compatibility.
def update_setting(setting_key: str, payload: dict,
                   user: dict = Depends(require_role(["manager"]))):
    if not setting_key or len(setting_key) > 100:
        raise HTTPException(status_code=400, detail="Invalid setting key")
    if not payload:
        raise HTTPException(status_code=400, detail="Setting value is required")
    with get_transaction() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO business_settings (setting_key, setting_value, updated_by)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value),
                                        updated_by = VALUES(updated_by)
            """, (setting_key, json.dumps(payload), user["id"]))
            log_activity(cursor, user, "setting_updated", "business_setting", setting_key,
                         after=payload)
            return {"message": "Setting updated", "setting_key": setting_key}

# Legacy manager implementation retained temporarily for compatibility.
def manager_report_summary(start_date: str, end_date: str,
                           user: dict = Depends(require_role(["manager"]))):
    try:
        datetime.date.fromisoformat(start_date)
        datetime.date.fromisoformat(end_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date range")
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="End date must not precede start date")
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT
                    COUNT(*) AS booking_count,
                    COALESCE(SUM(CASE WHEN status != 'CANCELLED'
                                      THEN total_price_gbp ELSE 0 END), 0) AS booking_value,
                    COALESCE(SUM(CASE WHEN payment_status = 'PAID'
                                      THEN total_price_gbp ELSE 0 END), 0) AS collected_payments,
                    COALESCE(SUM(CASE WHEN payment_status IN ('PENDING','AUTHORIZED')
                                      AND status != 'CANCELLED'
                                      THEN total_price_gbp ELSE 0 END), 0) AS outstanding
                FROM bookings
                WHERE scheduled_date BETWEEN %s AND %s
            """, (start_date, end_date))
            booking_totals = cursor.fetchone()
            cursor.execute("""
                SELECT COALESCE(SUM(amount_gbp), 0) AS expenses
                FROM expenses
                WHERE expense_date BETWEEN %s AND %s
            """, (start_date, end_date))
            expense_totals = cursor.fetchone()
            return {
                "date_range": {"start": start_date, "end": end_date},
                "booking_count": booking_totals["booking_count"] or 0,
                "booking_value_gbp": float(booking_totals["booking_value"] or 0),
                "collected_payments_gbp": float(booking_totals["collected_payments"] or 0),
                "outstanding_gbp": float(booking_totals["outstanding"] or 0),
                "expenses_gbp": float(expense_totals["expenses"] or 0),
                "profit_gbp": None,
                "profit_note": "Profit is not reported until a complete expense model is verified.",
            }

# Legacy implementation retained temporarily for compatibility.
def get_all_bookings(status_filter: Optional[str] = None, user: dict = Depends(require_role(["manager"]))):
    with get_db() as conn:
        with conn.cursor() as cursor:
            query = """
                SELECT b.*, s.name as service_name, 
                       c.full_name as customer_name, c.email as customer_email, c.phone as customer_phone,
                       cl.full_name as staff_name, cl.phone as staff_phone
                FROM bookings b
                JOIN services s ON b.service_id = s.id
                JOIN users c ON b.customer_id = c.id
                LEFT JOIN users cl ON b.staff_id = cl.id
            """
            params = []
            if status_filter and status_filter.upper() != "ALL":
                query += " WHERE b.status = %s"
                params.append(status_filter.upper())
            query += " ORDER BY b.scheduled_date DESC, b.id DESC"

            cursor.execute(query, tuple(params))
            bookings = cursor.fetchall()
            for b in bookings:
                b["access_notes"] = decrypt_sensitive_data(b.get("access_notes"))
            return {"bookings": bookings}

# Legacy implementation retained temporarily for compatibility.
def list_available_staff(
    postcode: Optional[str] = None,
    scheduled_date: Optional[str] = None,
    user: dict = Depends(require_role(["manager"])),
):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT u.id, u.full_name, u.email, u.phone, u.avatar_url,
                       sp.base_postcode, sp.service_radius_miles, sp.rating_avg, sp.rating_count,
                       sp.is_available, sp.verified_dbs, sp.right_to_work_verified,
                       sp.vetting_status, sp.dbs_document_ref, sp.right_to_work_document_ref,
                       COALESCE(j.job_count, 0) AS jobs_today
                FROM users u
                JOIN staff_profiles sp ON u.id = sp.user_id
                LEFT JOIN (
                    SELECT staff_id, COUNT(*) AS job_count
                    FROM bookings
                    WHERE scheduled_date = COALESCE(%s, CURRENT_DATE())
                      AND status NOT IN ('CANCELLED', 'COMPLETED')
                    GROUP BY staff_id
                ) j ON j.staff_id = u.id
                WHERE u.role_id = 2
            """, (scheduled_date,))
            staff = cursor.fetchall()
            target_coords = resolve_postcode_coords(postcode)[0:2] if postcode else None
            for cleaner in staff:
                if target_coords:
                    base_coords = resolve_postcode_coords(cleaner["base_postcode"])[0:2]
                    cleaner["distance_miles"] = round(
                        haversine_distance_miles(*target_coords, *base_coords), 1
                    )
                else:
                    cleaner["distance_miles"] = None
            return {"staff": staff}


# Legacy implementation retained temporarily for compatibility.
def update_staff_vetting(
    staff_id: int,
    payload: VettingSchema,
    user: dict = Depends(require_role(["manager"])),
):
    approved = payload.vetting_status == "APPROVED" and payload.verified_dbs and payload.right_to_work_verified
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE id = %s AND role_id = 2", (staff_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Cleaner staff not found")
            cursor.execute("""
                UPDATE staff_profiles
                SET verified_dbs = %s,
                    right_to_work_verified = %s,
                    vetting_status = %s,
                    dbs_document_ref = %s,
                    right_to_work_document_ref = %s,
                    vetted_at = CASE WHEN %s = 'APPROVED' THEN NOW() ELSE NULL END
                WHERE user_id = %s
            """, (
                payload.verified_dbs,
                payload.right_to_work_verified,
                payload.vetting_status,
                payload.dbs_document_ref,
                payload.right_to_work_document_ref,
                payload.vetting_status,
                staff_id,
            ))
            cursor.execute("UPDATE users SET is_active = %s WHERE id = %s", (approved, staff_id))
            return {
                "message": "Cleaner vetting updated",
                "staff_id": staff_id,
                "vetting_status": payload.vetting_status,
                "is_active": approved,
            }

# Legacy implementation retained temporarily for compatibility.
def assign_staff_to_booking(booking_id: int, payload: AssignStaffSchema, user: dict = Depends(require_role(["manager"]))):
    with get_transaction() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, full_name, email FROM users WHERE id = %s AND role_id = 2 FOR UPDATE",
                (payload.staff_id,),
            )
            staff = cursor.fetchone()
            if not staff:
                raise HTTPException(status_code=404, detail="Cleaner staff not found")

            cursor.execute("SELECT * FROM bookings WHERE id = %s FOR UPDATE", (booking_id,))
            booking = cursor.fetchone()
            if not booking:
                raise HTTPException(status_code=404, detail="Booking not found")
            if booking["status"] == "CANCELLED":
                raise HTTPException(status_code=400, detail="Cancelled bookings cannot be reassigned")

            # Check cleaner schedule conflict & TfL travel buffer
            unavailable, availability_reason = check_staff_availability(
                cursor, payload.staff_id, booking["scheduled_date"], booking["scheduled_time_slot"]
            )
            if unavailable:
                raise HTTPException(status_code=400, detail=availability_reason)
            has_conflict, reason = check_cleaner_schedule_conflict(
                cursor, payload.staff_id, booking["scheduled_date"], booking["scheduled_time_slot"], booking["postcode"], exclude_booking_id=booking_id
            )
            if has_conflict:
                raise HTTPException(status_code=400, detail=reason)

            cursor.execute("UPDATE bookings SET staff_id = %s WHERE id = %s", (payload.staff_id, booking_id))
            cursor.execute("""
                INSERT INTO booking_status_logs (booking_id, changed_by_user_id, previous_status, new_status, notes)
                VALUES (%s, %s, 'SCHEDULED', 'SCHEDULED', %s)
            """, (booking_id, user["id"], f"Manually assigned to cleaner {staff['full_name']}"))
            queue_notification(
                cursor,
                staff["id"],
                staff["email"],
                f"CleanLondon job assigned: {booking['reference_code']}",
                f"You have been assigned booking {booking['reference_code']} for "
                f"{booking['scheduled_date']} ({booking['scheduled_time_slot']}).",
            )

            return {"message": f"Successfully assigned booking to {staff['full_name']}"}


# Legacy implementation retained temporarily for compatibility.
def reassign_cleaner(booking_id: int, payload: AssignStaffSchema, user: dict = Depends(require_role(["manager"]))):
    """Explicit reassignment workflow used when the scheduled cleaner cancels."""
    return assign_staff_to_booking(booking_id, payload, user)

# Legacy implementation retained temporarily for compatibility.
def auto_match_cleaner(booking_id: int, user: dict = Depends(require_role(["manager"]))):
    """
    Intelligent Proximity-Based Auto-Dispatch Algorithm:
    Matches unassigned booking with the nearest available cleaner based on London postcodes,
    verifying cleaner schedule availability and London TfL travel buffers.
    """
    with get_transaction() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM bookings WHERE id = %s FOR UPDATE", (booking_id,))
            booking = cursor.fetchone()
            if not booking:
                raise HTTPException(status_code=404, detail="Booking not found")
            if booking["status"] == "CANCELLED":
                raise HTTPException(status_code=400, detail="Cancelled bookings cannot be auto-matched")
            if booking["staff_id"]:
                raise HTTPException(status_code=409, detail="Booking is already assigned to a cleaner")

            booking_coords = resolve_postcode_coords(booking["postcode"])

            cursor.execute("""
                SELECT u.id, u.full_name, u.email, sp.base_postcode, sp.service_radius_miles, sp.rating_avg
                FROM users u
                JOIN staff_profiles sp ON u.id = sp.user_id
                WHERE sp.is_available = TRUE
                  AND sp.vetting_status = 'APPROVED'
                  AND sp.verified_dbs = TRUE
                  AND sp.right_to_work_verified = TRUE
                  AND u.role_id = 2
            """)
            cleaners = cursor.fetchall()
            if not cleaners:
                raise HTTPException(status_code=400, detail="No available cleaners currently in service")

            # Filter out cleaners with schedule conflicts or insufficient travel buffer
            ranked_cleaners = []
            conflict_reasons = []
            for cleaner in cleaners:
                cursor.execute(
                    "SELECT id FROM users WHERE id = %s FOR UPDATE",
                    (cleaner["id"],),
                )
                unavailable, availability_reason = check_staff_availability(
                    cursor, cleaner["id"], booking["scheduled_date"], booking["scheduled_time_slot"]
                )
                if unavailable:
                    conflict_reasons.append(f"{cleaner['full_name']}: {availability_reason}")
                    continue
                has_conflict, reason = check_cleaner_schedule_conflict(
                    cursor, cleaner["id"], booking["scheduled_date"], booking["scheduled_time_slot"], booking["postcode"], exclude_booking_id=booking_id
                )
                if has_conflict:
                    conflict_reasons.append(f"{cleaner['full_name']}: {reason}")
                    continue

                cleaner_coords = resolve_postcode_coords(cleaner["base_postcode"])
                dist = haversine_distance_miles(
                    booking_coords[0], booking_coords[1],
                    cleaner_coords[0], cleaner_coords[1]
                )
                ranked_cleaners.append({
                    "cleaner_id": cleaner["id"],
                    "cleaner_name": cleaner["full_name"],
                    "distance_miles": dist,
                    "rating": float(cleaner["rating_avg"])
                })

            if not ranked_cleaners:
                conflict_summary = " | ".join(conflict_reasons[:2]) if conflict_reasons else "All cleaners are booked."
                raise HTTPException(
                    status_code=400,
                    detail=f"No conflict-free cleaners available for {booking['scheduled_date']} ({booking['scheduled_time_slot']}). {conflict_summary}"
                )

            ranked_cleaners.sort(key=lambda x: (x["distance_miles"], -x["rating"]))
            best_match = ranked_cleaners[0]

            cursor.execute("UPDATE bookings SET staff_id = %s WHERE id = %s", (best_match["cleaner_id"], booking_id))
            cursor.execute("""
                INSERT INTO booking_status_logs (booking_id, changed_by_user_id, previous_status, new_status, notes)
                VALUES (%s, %s, 'SCHEDULED', 'SCHEDULED', %s)
            """, (booking_id, user["id"], f"Auto-matched to {best_match['cleaner_name']} ({best_match['distance_miles']} miles away, schedule conflict-free)"))
            selected_cleaner = next(c for c in cleaners if c["id"] == best_match["cleaner_id"])
            queue_notification(
                cursor,
                selected_cleaner["id"],
                selected_cleaner["email"],
                f"CleanLondon job assigned: {booking['reference_code']}",
                f"You have been assigned booking {booking['reference_code']} for "
                f"{booking['scheduled_date']} ({booking['scheduled_time_slot']}).",
            )

            return {
                "message": f"Auto-matched booking to {best_match['cleaner_name']}",
                "cleaner_name": best_match["cleaner_name"],
                "distance_miles": best_match["distance_miles"],
                "rating": best_match["rating"]
            }

# ==========================================================
# 6. GOOGLE MAPS API & LOCATION SERVICES
# ==========================================================
class GeocodeRequestSchema(BaseModel):
    postcode: str

class DistanceRequestSchema(BaseModel):
    origin_postcode: str
    destination_postcode: str

# Legacy location implementation retained temporarily for compatibility.
def geocode_london_postcode(payload: GeocodeRequestSchema):
    """
    Geocodes a UK London postcode. In Mock mode, uses curated
    London centroid data. In production, calls Google Maps Geocoding API.
    """
    outcode = normalize_london_postcode(payload.postcode)
    coord_info = resolve_postcode_coords(payload.postcode)

    return {
        "input_postcode": payload.postcode,
        "outcode": outcode,
        "neighborhood": coord_info[2],
        "latitude": coord_info[0],
        "longitude": coord_info[1],
        "is_mock": MOCK_MODE,
        "formatted_address": f"{payload.postcode.upper()}, London, United Kingdom"
    }

# Legacy location implementation retained temporarily for compatibility.
def calculate_distance(payload: DistanceRequestSchema):
    """
    Computes transit/driving distance between two London points.
    """
    orig_outcode = normalize_london_postcode(payload.origin_postcode)
    dest_outcode = normalize_london_postcode(payload.destination_postcode)

    orig_coords = resolve_postcode_coords(payload.origin_postcode)
    dest_coords = resolve_postcode_coords(payload.destination_postcode)

    dist_miles = haversine_distance_miles(orig_coords[0], orig_coords[1], dest_coords[0], dest_coords[1])
    est_transit_mins = int(dist_miles * 7 + 10)  # London TfL Underground estimate

    return {
        "origin": payload.origin_postcode,
        "destination": payload.destination_postcode,
        "distance_miles": dist_miles,
        "estimated_travel_minutes": est_transit_mins,
        "mode": "London Underground & Bus (TfL)",
        "is_mock": MOCK_MODE
    }

# ==========================================================
# 7. STRIPE PAYMENT GATEWAY & WEBHOOKS
# ==========================================================
# Legacy payment implementation retained temporarily for compatibility.
def create_checkout_session(
    payload: CreateCheckoutSessionSchema,
    request: Request,
    user: dict = Depends(require_role(["customer", "manager"])),
):
    """
    Creates a Stripe Checkout Session for a CleanLondon booking in GBP (£).
    If valid Stripe API credentials are present, communicates with Stripe API.
    Otherwise, activates realistic mock mode with zero-friction checkout URL.
    """
    idempotency_key = get_idempotency_key(request)
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT b.*, s.name as service_name, u.email as customer_email, u.full_name as customer_name
                FROM bookings b
                JOIN services s ON b.service_id = s.id
                JOIN users u ON b.customer_id = u.id
                WHERE b.id = %s
            """, (payload.booking_id,))
            booking = cursor.fetchone()

            if not booking:
                raise HTTPException(status_code=404, detail="Booking not found")

            # Ownership check: Customer must own the booking
            if user["role"] == "customer" and booking["customer_id"] != user["id"]:
                raise HTTPException(status_code=403, detail="You can only pay for your own bookings")

            if booking["payment_status"] == "PAID":
                return {
                    "message": "Booking is already paid",
                    "payment_status": "PAID",
                    "booking_id": booking["id"],
                    "checkout_url": f"/static/success.html?booking_id={booking['id']}&already_paid=true"
                }

            price_pence = int(round(float(booking["total_price_gbp"]) * 100))
            is_mock_stripe = not STRIPE_SECRET_KEY or "mock" in STRIPE_SECRET_KEY.lower()

            checkout_url = None
            session_id = None

            if not is_mock_stripe:
                try:
                    success_url = STRIPE_SUCCESS_URL
                    if "{CHECKOUT_SESSION_ID}" in success_url:
                        success_url = success_url.replace("{CHECKOUT_SESSION_ID}", "{CHECKOUT_SESSION_ID}") + f"&booking_id={booking['id']}"
                    else:
                        success_url += f"?session_id={{CHECKOUT_SESSION_ID}}&booking_id={booking['id']}"

                    cancel_url = f"{STRIPE_CANCEL_URL}?booking_id={booking['id']}"

                    session = stripe.checkout.Session.create(
                        payment_method_types=["card"],
                        customer_email=booking["customer_email"],
                        line_items=[{
                            "price_data": {
                                "currency": "gbp",
                                "unit_amount": price_pence,
                                "product_data": {
                                    "name": f"CleanLondon: {booking['service_name']}",
                                    "description": f"Ref: {booking['reference_code']} - {booking['property_type']} at {booking['postcode']}",
                                    "images": ["https://images.unsplash.com/photo-1581578731548-c64695cc6952?w=300"]
                                },
                            },
                            "quantity": 1,
                        }],
                        mode="payment",
                        client_reference_id=str(booking["id"]),
                        metadata={
                            "booking_id": str(booking["id"]),
                            "reference_code": booking["reference_code"],
                            "customer_id": str(booking["customer_id"]),
                        },
                        success_url=success_url,
                        cancel_url=cancel_url,
                        idempotency_key=idempotency_key,
                    )
                    checkout_url = session.url
                    session_id = session.id
                except Exception as e:
                    # Graceful fallback to mock mode if live Stripe API is blocked or key is expired
                    is_mock_stripe = True

            if is_mock_stripe:
                stable_key = idempotency_key or f"booking-{booking['id']}"
                stable_suffix = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:12]
                session_id = f"cs_test_mock_{booking['id']}_{stable_suffix}"
                checkout_url = f"/static/success.html?session_id={session_id}&booking_id={booking['id']}&mock=true"

            # Update booking record with session id
            cursor.execute("""
                UPDATE bookings 
                SET stripe_session_id = %s 
                WHERE id = %s
            """, (session_id, booking["id"]))

            return {
                "message": "Stripe Checkout session created successfully",
                "checkout_url": checkout_url,
                "session_id": session_id,
                "booking_id": booking["id"],
                "total_price_gbp": float(booking["total_price_gbp"]),
                "currency": "GBP (£)",
                "is_mock": is_mock_stripe
            }

# Legacy payment implementation retained temporarily for compatibility.
async def stripe_webhook(request: Request):
    """
    Secure Stripe Webhook Listener:
    Verifies stripe-signature header, parses 'checkout.session.completed',
    and updates MySQL booking payment_status to 'PAID'.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    event = None
    if IS_PRODUCTION:
        if not sig_header:
            raise HTTPException(status_code=400, detail="Missing stripe-signature header")
        if not STRIPE_WEBHOOK_SECRET or "mock" in STRIPE_WEBHOOK_SECRET.lower():
            raise HTTPException(status_code=500, detail="Stripe webhook secret is not configured for production")
        try:
            event = stripe.Webhook.construct_event(
                payload=payload,
                sig_header=sig_header,
                secret=STRIPE_WEBHOOK_SECRET
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid Stripe webhook payload")
        except stripe.error.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature")
    else:
        # Development / test webhook handler
        if sig_header and STRIPE_WEBHOOK_SECRET and "mock" not in STRIPE_WEBHOOK_SECRET.lower():
            try:
                event = stripe.Webhook.construct_event(
                    payload=payload,
                    sig_header=sig_header,
                    secret=STRIPE_WEBHOOK_SECRET
                )
            except (ValueError, stripe.error.SignatureVerificationError) as exc:
                raise HTTPException(status_code=400, detail=f"Invalid webhook signature: {str(exc)}")
        else:
            try:
                event = json.loads(payload.decode("utf-8"))
            except Exception:
                raise HTTPException(status_code=400, detail="Could not parse mock JSON payload")

    event_type = event.get("type")

    # Fulfillment handler
    if event_type == "checkout.session.completed":
        session = event.get("data", {}).get("object", {})
        metadata = session.get("metadata", {})
        booking_id = metadata.get("booking_id") or session.get("client_reference_id")
        session_id = session.get("id")
        payment_intent_id = session.get("payment_intent") or f"pi_mock_{random.randint(1000, 9999)}"

        if not booking_id:
            return {"status": "ignored", "reason": "No booking_id associated with session"}

        return await run_in_threadpool(
            _fulfill_stripe_payment,
            int(booking_id),
            session_id,
            payment_intent_id,
        )

    return {"status": "unhandled_event", "type": event_type}


def _fulfill_stripe_payment(booking_id: int, session_id: Optional[str], payment_intent_id: str) -> dict:
    """Run blocking MySQL fulfillment off the event loop used by the async webhook."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, customer_id, status, payment_status FROM bookings WHERE id = %s",
                (booking_id,),
            )
            booking = cursor.fetchone()
            if not booking:
                return {"status": "ignored", "reason": "Booking not found"}

            cursor.execute("""
                UPDATE bookings
                SET payment_status = 'PAID',
                    stripe_session_id = COALESCE(stripe_session_id, %s),
                    stripe_payment_intent_id = %s
                WHERE id = %s
            """, (session_id, payment_intent_id, booking_id))

            cursor.execute("""
                INSERT INTO booking_status_logs (booking_id, changed_by_user_id, previous_status, new_status, notes)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                booking_id,
                booking["customer_id"],
                booking["status"],
                booking["status"],
                f"Payment fulfilled via Stripe ({payment_intent_id})",
            ))

            return {
                "status": "success",
                "booking_id": booking_id,
                "payment_status": "PAID",
                "payment_intent": payment_intent_id,
            }

# Legacy payment implementation retained temporarily for compatibility.
def verify_payment_session(session_id: str, booking_id: Optional[int] = None):
    """
    Verification endpoint called by success.html to verify fulfillment
    and display receipt details to the customer.
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            query = """
                SELECT b.*, s.name as service_name, u.full_name as customer_name, u.email as customer_email
                FROM bookings b
                JOIN services s ON b.service_id = s.id
                JOIN users u ON b.customer_id = u.id
                WHERE b.stripe_session_id = %s
            """
            params = [session_id]

            if booking_id:
                # Security Fix: Enforce AND condition so callers cannot enumerate bookings by ID without a valid Stripe session ID
                query += " AND b.id = %s"
                params.append(booking_id)

            cursor.execute(query, tuple(params))
            booking = cursor.fetchone()

            if not booking:
                raise HTTPException(status_code=404, detail="Payment session or booking not found")

            # Only mock mode may simulate fulfillment from the browser redirect.
            # Real payments become authoritative when Stripe calls /webhook.
            if MOCK_MODE and booking["payment_status"] != "PAID":
                mock_pi = f"pi_mock_{random.randint(100000, 999999)}"
                cursor.execute("""
                    UPDATE bookings 
                    SET payment_status = 'PAID',
                        stripe_session_id = %s,
                        stripe_payment_intent_id = COALESCE(stripe_payment_intent_id, %s)
                    WHERE id = %s
                """, (session_id, mock_pi, booking["id"]))
                booking["payment_status"] = "PAID"
                booking["stripe_payment_intent_id"] = mock_pi

            return {
                "booking_id": booking["id"],
                "reference_code": booking["reference_code"],
                "service_name": booking["service_name"],
                "customer_name": booking["customer_name"],
                "postcode": booking["postcode"],
                "scheduled_date": str(booking["scheduled_date"]),
                "scheduled_time_slot": booking["scheduled_time_slot"],
                "total_price_gbp": float(booking["total_price_gbp"]),
                "payment_status": booking["payment_status"],
                "session_id": session_id,
                "payment_intent_id": booking["stripe_payment_intent_id"]
            }


@app.on_event("startup")
def ensure_operational_schema():
    """Apply additive operational schema changes to existing Docker volumes."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT COLUMN_NAME
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'staff_profiles'
            """, (DB_NAME,))
            existing_columns = {row["COLUMN_NAME"] for row in cursor.fetchall()}
            additions = {
                "right_to_work_verified": "BOOLEAN NOT NULL DEFAULT TRUE",
                "vetting_status": "ENUM('PENDING', 'APPROVED', 'REJECTED') NOT NULL DEFAULT 'APPROVED'",
                "dbs_document_ref": "VARCHAR(255) NULL",
                "right_to_work_document_ref": "VARCHAR(255) NULL",
                "vetted_at": "TIMESTAMP NULL",
            }
            for column, definition in additions.items():
                if column not in existing_columns:
                    cursor.execute(f"ALTER TABLE staff_profiles ADD COLUMN {column} {definition}")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS staff_weekly_availability (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    staff_id INT NOT NULL,
                    day_of_week TINYINT NOT NULL,
                    start_time TIME NOT NULL,
                    end_time TIME NOT NULL,
                    UNIQUE KEY uq_staff_weekly_slot (staff_id, day_of_week),
                    CONSTRAINT fk_weekly_staff FOREIGN KEY (staff_id) REFERENCES users (id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS staff_holidays (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    staff_id INT NOT NULL,
                    holiday_date DATE NOT NULL,
                    reason VARCHAR(255) NULL,
                    UNIQUE KEY uq_staff_holiday (staff_id, holiday_date),
                    CONSTRAINT fk_holiday_staff FOREIGN KEY (staff_id) REFERENCES users (id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notification_outbox (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    recipient_user_id INT NULL,
                    recipient_address VARCHAR(255) NOT NULL,
                    channel ENUM('EMAIL', 'SMS') NOT NULL DEFAULT 'EMAIL',
                    subject VARCHAR(255) NOT NULL,
                    body TEXT NOT NULL,
                    status ENUM('QUEUED', 'SENT', 'FAILED') NOT NULL DEFAULT 'QUEUED',
                    error_message VARCHAR(500) NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    sent_at TIMESTAMP NULL,
                    CONSTRAINT fk_notification_user FOREIGN KEY (recipient_user_id) REFERENCES users (id) ON DELETE SET NULL,
                    INDEX idx_notification_recipient (recipient_user_id, created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                SELECT COLUMN_NAME FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'notification_outbox'
            """, (DB_NAME,))
            notification_columns = {row["COLUMN_NAME"] for row in cursor.fetchall()}
            for column, definition in {
                "is_read": "BOOLEAN NOT NULL DEFAULT FALSE",
                "priority": "ENUM('LOW','NORMAL','HIGH','CRITICAL') NOT NULL DEFAULT 'NORMAL'",
                "deep_link": "VARCHAR(255) NULL",
            }.items():
                if column not in notification_columns:
                    cursor.execute(f"ALTER TABLE notification_outbox ADD COLUMN {column} {definition}")

            cursor.execute("""
                ALTER TABLE bookings MODIFY COLUMN status
                ENUM('PENDING','APPROVED','CONFIRMED','SCHEDULED','EN_ROUTE','IN_PROGRESS','COMPLETED','REJECTED','CANCELLED')
                NOT NULL DEFAULT 'SCHEDULED'
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS payment_records (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    booking_id INT NOT NULL,
                    amount_gbp DECIMAL(8,2) NOT NULL,
                    method ENUM('CASH','CARD','BANK_TRANSFER','REFUND','OTHER') NOT NULL,
                    status ENUM('RECORDED','VERIFIED','REFUND_REQUESTED','REFUNDED','REJECTED') NOT NULL DEFAULT 'RECORDED',
                    reference VARCHAR(100) NULL,
                    recorded_by INT NOT NULL,
                    verified_by INT NULL,
                    recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    verified_at TIMESTAMP NULL,
                    CONSTRAINT fk_payment_booking FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE RESTRICT,
                    CONSTRAINT fk_payment_recorded_by FOREIGN KEY (recorded_by) REFERENCES users(id) ON DELETE RESTRICT,
                    CONSTRAINT fk_payment_verified_by FOREIGN KEY (verified_by) REFERENCES users(id) ON DELETE RESTRICT,
                    INDEX idx_payment_booking (booking_id, recorded_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS support_cases (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    booking_id INT NULL,
                    customer_id INT NOT NULL,
                    assigned_to INT NULL,
                    subject VARCHAR(160) NOT NULL,
                    description TEXT NOT NULL,
                    status ENUM('OPEN','IN_PROGRESS','RESOLVED') NOT NULL DEFAULT 'OPEN',
                    outcome TEXT NULL,
                    follow_up_at TIMESTAMP NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    CONSTRAINT fk_support_booking FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE SET NULL,
                    CONSTRAINT fk_support_customer FOREIGN KEY (customer_id) REFERENCES users(id) ON DELETE RESTRICT,
                    CONSTRAINT fk_support_assignee FOREIGN KEY (assigned_to) REFERENCES users(id) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS activity_audit_log (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    actor_id INT NULL,
                    actor_role VARCHAR(30) NULL,
                    action VARCHAR(80) NOT NULL,
                    entity_type VARCHAR(80) NOT NULL,
                    entity_id VARCHAR(100) NULL,
                    before_json JSON NULL,
                    after_json JSON NULL,
                    reason VARCHAR(500) NULL,
                    request_id VARCHAR(100) NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_audit_entity (entity_type, entity_id),
                    INDEX idx_audit_actor (actor_id, created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS staff_shifts (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    staff_id INT NOT NULL,
                    shift_date DATE NOT NULL,
                    start_time TIME NOT NULL,
                    end_time TIME NOT NULL,
                    status ENUM('PLANNED','CONFIRMED','CANCELLED') NOT NULL DEFAULT 'PLANNED',
                    created_by INT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_staff_shift_slot (staff_id, shift_date, start_time, end_time),
                    CONSTRAINT fk_shift_staff FOREIGN KEY (staff_id) REFERENCES users(id) ON DELETE CASCADE,
                    CONSTRAINT fk_shift_creator FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS staff_time_off (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    staff_id INT NOT NULL,
                    start_date DATE NOT NULL,
                    end_date DATE NOT NULL,
                    reason VARCHAR(255) NULL,
                    status ENUM('PENDING','APPROVED','REJECTED') NOT NULL DEFAULT 'PENDING',
                    reviewed_by INT NULL,
                    reviewed_at TIMESTAMP NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_timeoff_staff FOREIGN KEY (staff_id) REFERENCES users(id) ON DELETE CASCADE,
                    CONSTRAINT fk_timeoff_reviewer FOREIGN KEY (reviewed_by) REFERENCES users(id) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS business_settings (
                    setting_key VARCHAR(100) PRIMARY KEY,
                    setting_value JSON NOT NULL,
                    updated_by INT NULL,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    CONSTRAINT fk_settings_updater FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS expenses (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    expense_date DATE NOT NULL,
                    category VARCHAR(80) NOT NULL,
                    amount_gbp DECIMAL(10,2) NOT NULL,
                    description VARCHAR(255) NULL,
                    recorded_by INT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_expense_recorded_by FOREIGN KEY (recorded_by) REFERENCES users(id) ON DELETE RESTRICT
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            migrate_plaintext_access_notes(cursor)
            # Migrate dummy legacy seed password hashes to valid bcrypt hashes matching Password123!
            valid_demo_hash = "$2b$12$Ww6zkTlA7XwpVflMIq1aRuvMunTakRHn3ShYtgTFF//GWiEmZRjNq"
            cursor.execute("""
                UPDATE users
                SET password_hash = %s
                WHERE password_hash = '$2b$12$Kk2rI0PjU7zT5lY4k2bV0O6uH0jQ4k8l1m2n3o4p5q6r7s8t9u0v.'
            """, (valid_demo_hash,))

# ==========================================================
# 8. FRONTEND STATIC ASSETS MOUNT
# ==========================================================
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
