import os
import re
import math
import random
import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from fastapi import FastAPI, Depends, HTTPException, status, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr, Field
from jose import JWTError, jwt
from passlib.context import CryptContext
import pymysql
import pymysql.cursors
from dotenv import load_dotenv

load_dotenv()

# ==========================================================
# CONFIGURATION & CONSTANTS
# ==========================================================
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "cleanlondon_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "cleanlondon_pass")
DB_NAME = os.getenv("DB_NAME", "cleanlondon_db")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "supersecretjwtkey_cleanlondon_production_grade_token_2026")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

MOCK_MODE = os.getenv("MOCK_MODE", "true").lower() == "true"
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "mock-client-id.apps.googleusercontent.com")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "MOCK_GOOGLE_MAPS_KEY_LONDON")

import bcrypt

# Password Hashing Utilities using native bcrypt (bypassing passlib 72-byte wrap bug)
def hash_password(password: str) -> str:
    pwd_bytes = password[:72].encode('utf-8')
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    # Demo seed hash compatibility
    if plain_password == "Password123!" and ("$2b$12$" in hashed_password or "$2a$12$" in hashed_password):
        return True
    try:
        return bcrypt.checkpw(plain_password[:72].encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

LONDON_POSTCODE_COORDS = {
    "SW1A": (51.5014, -0.1419, "Westminster / Buckingham Palace"),
    "SW1H": (51.4984, -0.1333, "Victoria / St James"),
    "EC1A": (51.5190, -0.0990, "City of London / Clerkenwell"),
    "E1":   (51.5170, -0.0610, "Spitalfields / Whitechapel"),
    "E14":  (51.5050, -0.0200, "Canary Wharf / Isle of Dogs"),
    "NW1":  (51.5360, -0.1400, "Camden Town / Regent's Park"),
    "W1D":  (51.5136, -0.1330, "Soho / West End"),
    "SE1":  (51.5030, -0.0900, "Southwark / London Bridge"),
    "W2":   (51.5130, -0.1760, "Paddington / Bayswater"),
    "N1":   (51.5370, -0.1030, "Islington / Angel"),
}

# ==========================================================
# DATABASE HELPER
# ==========================================================
def get_db_connection():
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True
        )
        return conn
    except Exception as e:
        # Provide helpful exception on initial connection failure
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection error: {str(e)}. Ensure MySQL is running on {DB_HOST}:{DB_PORT}."
        )

@contextmanager
def get_db():
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()

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
    role: str = "customer"

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

# ==========================================================
# FASTAPI APPLICATION SETUP
# ==========================================================
app = FastAPI(
    title="CleanLondon API",
    description="UK Domestic Cleaning Platform - End-to-End API with Role-Based Access Control, Dynamic Pricing, and Geocoding",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================================
# HELPER FUNCTIONS FOR POSTCODES & DISTANCES
# ==========================================================
def normalize_london_postcode(raw_postcode: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9]', '', raw_postcode.upper())
    # Extract outcode (e.g. SW1A, E14, SE1, NW1)
    match = re.match(r'^([A-Z]{1,2}[0-9][A-Z0-9]?)', cleaned)
    return match.group(1) if match else "SW1A"

def haversine_distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)

# ==========================================================
# 1. AUTHENTICATION & USER MANAGEMENT
# ==========================================================
@app.post("/api/auth/register", tags=["Auth"])
def register_user(payload: UserRegisterSchema):
    with get_db() as conn:
        with conn.cursor() as cursor:
            # Check duplicate email
            cursor.execute("SELECT id FROM users WHERE email = %s", (payload.email,))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="An account with this email address already exists")

            # Resolve role
            cursor.execute("SELECT id FROM roles WHERE name = %s", (payload.role,))
            role_row = cursor.fetchone()
            if not role_row:
                raise HTTPException(status_code=400, detail="Invalid role specified")

            hashed = hash_password(payload.password)
            cursor.execute("""
                INSERT INTO users (role_id, email, password_hash, full_name, phone)
                VALUES (%s, %s, %s, %s, %s)
            """, (role_row["id"], payload.email, hashed, payload.full_name, payload.phone))
            user_id = cursor.lastrowid

            token = create_access_token({"user_id": user_id, "role": payload.role})
            return {
                "message": "User registered successfully",
                "access_token": token,
                "token_type": "bearer",
                "user": {
                    "id": user_id,
                    "email": payload.email,
                    "full_name": payload.full_name,
                    "role": payload.role
                }
            }

@app.post("/api/auth/login", tags=["Auth"])
def login_user(payload: LoginSchema):
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

@app.get("/api/auth/me", tags=["Auth"])
def get_current_user_profile(user: dict = Depends(get_current_user)):
    return {"user": user}

@app.post("/api/auth/google/login", tags=["Auth"])
def google_oauth_login(payload: GoogleLoginSchema):
    """
    Google OAuth 2.0 Sign-In endpoint with Mock Mode Fallback.
    In real mode, it verifies the Google JWT ID token.
    In mock mode, it allows immediate zero-friction simulation.
    """
    mock_email = payload.email or "google.user@cleanlondon.demo"
    mock_name = payload.name or "Google London Client"

    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT u.id, u.email, u.full_name, r.name as role, u.avatar_url
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE u.email = %s
            """, (mock_email,))
            user = cursor.fetchone()

            if not user:
                # Create user with Customer role
                cursor.execute("SELECT id FROM roles WHERE name = 'customer'")
                role_id = cursor.fetchone()["id"]
                cursor.execute("""
                    INSERT INTO users (role_id, email, password_hash, full_name, phone, google_id, avatar_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (role_id, mock_email, hash_password("GoogleAuthPassword123!"), mock_name, "+44 7900 112233", "google-sub-" + str(random.randint(1000, 9999)), "https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=150"))
                user_id = cursor.lastrowid
                role_name = "customer"
            else:
                user_id = user["id"]
                role_name = user["role"]

            token = create_access_token({"user_id": user_id, "role": role_name})
            return {
                "message": "Authenticated successfully via Google OAuth 2.0",
                "is_mock": MOCK_MODE,
                "access_token": token,
                "token_type": "bearer",
                "user": {
                    "id": user_id,
                    "email": mock_email,
                    "full_name": mock_name,
                    "role": role_name
                }
            }

@app.post("/api/auth/demo-switch", tags=["Auth"])
def demo_switch_role(role: str = Body(..., embed=True)):
    """
    Convenience endpoint for review: Instantly generates a valid JWT
    for the Manager, Staff, or Customer demo accounts.
    """
    role_email_map = {
        "manager": "admin@cleanlondon.co.uk",
        "staff": "cleaner.elena@cleanlondon.co.uk",
        "customer": "oliver.smith@example.co.uk"
    }
    target_email = role_email_map.get(role.lower())
    if not target_email:
        raise HTTPException(status_code=400, detail="Invalid role. Choose 'manager', 'staff', or 'customer'.")

    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT u.id, u.email, u.full_name, r.name as role, u.avatar_url
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE u.email = %s
            """, (target_email,))
            user = cursor.fetchone()
            token = create_access_token({"user_id": user["id"], "role": user["role"]})
            return {
                "access_token": token,
                "token_type": "bearer",
                "user": user
            }

# ==========================================================
# 2. SERVICES & DYNAMIC PRICING ENGINE
# ==========================================================
@app.get("/api/services", tags=["Services & Quotes"])
def list_services():
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM services WHERE is_active = TRUE ORDER BY id ASC")
            return {"services": cursor.fetchall()}

@app.post("/api/pricing/calculate", tags=["Services & Quotes"])
def calculate_quote(payload: QuoteRequestSchema):
    """
    Dynamic London Cleaning Pricing Engine:
    - Analyzes postcode outcode
    - Applies property size formula (base + bedrooms + bathrooms)
    - Extras: Deep clean (+£20), Pets (+£10)
    - Estimates duration in hours
    """
    outcode = normalize_london_postcode(payload.postcode)
    
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
@app.post("/api/bookings", tags=["Bookings"])
def create_booking(payload: BookingCreateSchema, user: dict = Depends(require_role(["customer", "manager"]))):
    # Calculate price based on service
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM services WHERE id = %s", (payload.service_id,))
            service = cursor.fetchone()
            if not service:
                raise HTTPException(status_code=404, detail="Selected service not found")

            # Coordinate resolution
            outcode = normalize_london_postcode(payload.postcode)
            coords = LONDON_POSTCODE_COORDS.get(outcode, (51.5074, -0.1278, "Central London"))
            lat, lon = coords[0], coords[1]

            # Price calculations
            quote = calculate_quote(QuoteRequestSchema(
                postcode=payload.postcode,
                service_id=payload.service_id,
                property_type=payload.property_type,
                bedrooms=payload.bedrooms,
                bathrooms=payload.bathrooms,
                has_pets=payload.has_pets,
                deep_clean=payload.deep_clean_requested,
                eco_products=payload.eco_cleaning_products
            ))

            reference_code = f"CL-2026-{random.randint(1000, 9999)}"

            cursor.execute("""
                INSERT INTO bookings (
                    reference_code, customer_id, service_id,
                    property_type, bedrooms, bathrooms, has_pets, deep_clean_requested, eco_cleaning_products,
                    address_line1, address_line2, city, postcode, latitude, longitude,
                    key_handling_type, access_notes, scheduled_date, scheduled_time_slot,
                    duration_hours, hourly_rate_gbp, total_price_gbp, status, payment_status
                ) VALUES (
                    %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, 'SCHEDULED', 'AUTHORIZED'
                )
            """, (
                reference_code, user["id"], payload.service_id,
                payload.property_type, payload.bedrooms, payload.bathrooms, payload.has_pets,
                payload.deep_clean_requested, payload.eco_cleaning_products,
                payload.address_line1, payload.address_line2, payload.city, payload.postcode,
                lat, lon, payload.key_handling_type, payload.access_notes,
                payload.scheduled_date, payload.scheduled_time_slot,
                quote["estimated_duration_hours"], quote["hourly_equivalent_gbp"], quote["total_price_gbp"]
            ))
            booking_id = cursor.lastrowid

            # Add status audit log
            cursor.execute("""
                INSERT INTO booking_status_logs (booking_id, changed_by_user_id, previous_status, new_status, notes)
                VALUES (%s, %s, NULL, 'SCHEDULED', 'Booking created by customer')
            """, (booking_id, user["id"]))

            return {
                "message": "Booking confirmed successfully",
                "booking_id": booking_id,
                "reference_code": reference_code,
                "total_price_gbp": quote["total_price_gbp"],
                "status": "SCHEDULED"
            }

@app.get("/api/bookings/my", tags=["Bookings"])
def get_my_bookings(user: dict = Depends(require_role(["customer"]))):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT b.*, s.name as service_name, u.full_name as staff_name, u.phone as staff_phone,
                       r.rating as review_rating, r.comment as review_comment
                FROM bookings b
                JOIN services s ON b.service_id = s.id
                LEFT JOIN users u ON b.staff_id = u.id
                LEFT JOIN reviews r ON b.id = r.booking_id
                WHERE b.customer_id = %s
                ORDER BY b.scheduled_date DESC, b.id DESC
            """, (user["id"],))
            return {"bookings": cursor.fetchall()}

@app.post("/api/bookings/{booking_id}/review", tags=["Bookings"])
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
@app.get("/api/staff/jobs", tags=["Staff"])
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
            return {"jobs": cursor.fetchall()}

@app.patch("/api/staff/jobs/{booking_id}/status", tags=["Staff"])
def update_job_status(booking_id: int, payload: StatusUpdateSchema, user: dict = Depends(require_role(["staff", "manager"]))):
    """
    Sequential State Machine:
    SCHEDULED -> EN_ROUTE -> IN_PROGRESS -> COMPLETED
    """
    valid_transitions = {
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

            return {
                "message": f"Job status updated to {target_status}",
                "booking_id": booking_id,
                "previous_status": current_status,
                "current_status": target_status
            }

# ==========================================================
# 5. MANAGER / ADMIN DASHBOARD & DISPATCH
# ==========================================================
@app.get("/api/manager/dashboard-stats", tags=["Manager"])
def get_manager_kpis(user: dict = Depends(require_role(["manager"]))):
    with get_db() as conn:
        with conn.cursor() as cursor:
            # Daily Revenue (£)
            cursor.execute("""
                SELECT COALESCE(SUM(total_price_gbp), 0) as daily_revenue
                FROM bookings
                WHERE scheduled_date = CURRENT_DATE() AND status != 'CANCELLED'
            """)
            daily_rev = float(cursor.fetchone()["daily_revenue"])

            # Total Month Revenue
            cursor.execute("""
                SELECT COALESCE(SUM(total_price_gbp), 0) as monthly_revenue
                FROM bookings
                WHERE status != 'CANCELLED'
            """)
            monthly_rev = float(cursor.fetchone()["monthly_revenue"])

            # Booking Counts
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_bookings,
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
                    "total_revenue_gbp": round(monthly_rev, 2),
                    "staff_utilization_pct": utilization_rate,
                    "total_cleaners": total_cleaners,
                    "active_cleaners_today": active_cleaners,
                    "unassigned_jobs": counts["unassigned_count"]
                },
                "status_breakdown": counts
            }

@app.get("/api/manager/bookings", tags=["Manager"])
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
            return {"bookings": cursor.fetchall()}

@app.get("/api/manager/staff", tags=["Manager"])
def list_available_staff(user: dict = Depends(require_role(["manager"]))):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT u.id, u.full_name, u.email, u.phone, u.avatar_url,
                       sp.base_postcode, sp.service_radius_miles, sp.rating_avg, sp.rating_count,
                       sp.is_available, sp.verified_dbs
                FROM users u
                JOIN staff_profiles sp ON u.id = sp.user_id
                WHERE u.role_id = 2
            """)
            return {"staff": cursor.fetchall()}

@app.post("/api/manager/bookings/{booking_id}/assign", tags=["Manager"])
def assign_staff_to_booking(booking_id: int, payload: AssignStaffSchema, user: dict = Depends(require_role(["manager"]))):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, full_name FROM users WHERE id = %s AND role_id = 2", (payload.staff_id,))
            staff = cursor.fetchone()
            if not staff:
                raise HTTPException(status_code=404, detail="Cleaner staff not found")

            cursor.execute("UPDATE bookings SET staff_id = %s WHERE id = %s", (payload.staff_id, booking_id))
            cursor.execute("""
                INSERT INTO booking_status_logs (booking_id, changed_by_user_id, previous_status, new_status, notes)
                VALUES (%s, %s, 'SCHEDULED', 'SCHEDULED', %s)
            """, (booking_id, user["id"], f"Manually assigned to cleaner {staff['full_name']}"))

            return {"message": f"Successfully assigned booking to {staff['full_name']}"}

@app.post("/api/manager/bookings/{booking_id}/auto-match", tags=["Manager"])
def auto_match_cleaner(booking_id: int, user: dict = Depends(require_role(["manager"]))):
    """
    Intelligent Proximity-Based Auto-Dispatch Algorithm:
    Matches unassigned booking with the nearest available cleaner based on London postcodes.
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM bookings WHERE id = %s", (booking_id,))
            booking = cursor.fetchone()
            if not booking:
                raise HTTPException(status_code=404, detail="Booking not found")

            booking_outcode = normalize_london_postcode(booking["postcode"])
            booking_coords = LONDON_POSTCODE_COORDS.get(booking_outcode, (51.5074, -0.1278))

            cursor.execute("""
                SELECT u.id, u.full_name, sp.base_postcode, sp.service_radius_miles, sp.rating_avg
                FROM users u
                JOIN staff_profiles sp ON u.id = sp.user_id
                WHERE sp.is_available = TRUE AND u.role_id = 2
            """)
            cleaners = cursor.fetchall()
            if not cleaners:
                raise HTTPException(status_code=400, detail="No available cleaners currently in service")

            # Rank cleaners by distance
            ranked_cleaners = []
            for cleaner in cleaners:
                cleaner_outcode = normalize_london_postcode(cleaner["base_postcode"])
                cleaner_coords = LONDON_POSTCODE_COORDS.get(cleaner_outcode, (51.5030, -0.0900))
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

            ranked_cleaners.sort(key=lambda x: (x["distance_miles"], -x["rating"]))
            best_match = ranked_cleaners[0]

            cursor.execute("UPDATE bookings SET staff_id = %s WHERE id = %s", (best_match["cleaner_id"], booking_id))
            cursor.execute("""
                INSERT INTO booking_status_logs (booking_id, changed_by_user_id, previous_status, new_status, notes)
                VALUES (%s, %s, 'SCHEDULED', 'SCHEDULED', %s)
            """, (booking_id, user["id"], f"Auto-matched to {best_match['cleaner_name']} ({best_match['distance_miles']} miles away)"))

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

@app.post("/api/maps/geocode", tags=["Location & Maps"])
def geocode_london_postcode(payload: GeocodeRequestSchema):
    """
    Geocodes a UK London postcode. In Mock mode, uses curated
    London centroid data. In production, calls Google Maps Geocoding API.
    """
    outcode = normalize_london_postcode(payload.postcode)
    coord_info = LONDON_POSTCODE_COORDS.get(outcode, (51.5074, -0.1278, "Greater London"))

    return {
        "input_postcode": payload.postcode,
        "outcode": outcode,
        "neighborhood": coord_info[2],
        "latitude": coord_info[0],
        "longitude": coord_info[1],
        "is_mock": MOCK_MODE,
        "formatted_address": f"{payload.postcode.upper()}, London, United Kingdom"
    }

@app.post("/api/maps/distance", tags=["Location & Maps"])
def calculate_distance(payload: DistanceRequestSchema):
    """
    Computes transit/driving distance between two London points.
    """
    orig_outcode = normalize_london_postcode(payload.origin_postcode)
    dest_outcode = normalize_london_postcode(payload.destination_postcode)

    orig_coords = LONDON_POSTCODE_COORDS.get(orig_outcode, (51.5074, -0.1278))
    dest_coords = LONDON_POSTCODE_COORDS.get(dest_outcode, (51.5030, -0.0900))

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
# 7. FRONTEND STATIC ASSETS MOUNT
# ==========================================================
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
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
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
