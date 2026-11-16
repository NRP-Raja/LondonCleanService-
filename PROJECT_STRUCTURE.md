# CleanLondon — Recommended Project Architecture & Directory Structure

This guide outlines how to reorganize your current flat codebase (`main.py`, `frontend/app.js`, root test files) into a clean, scalable **Layered MVC (Router → Service → Repository)** backend and a **Modular ES6** frontend—without needing heavy build tools like Webpack or React.

---

## 1. Architectural Philosophy (Why This Structure?)

Right now, all backend routes, SQL queries, pricing math, and Stripe logic live inside a single `main.py`, while all UI rendering and API calls live inside `frontend/app.js`. As you add conflict-free cleaner scheduling, Stripe webhooks, and role-specific dashboards, single files become hard to navigate and debug.

| Layer | Folder | Responsibility | Golden Rule |
| :--- | :--- | :--- | :--- |
| **Controller (HTTP)** | `app/routers/` | Receives HTTP requests, checks user role permissions, and returns JSON responses. | **No raw SQL** and no complex business math here. |
| **Business Logic** | `app/services/` | Handles pricing rules, Haversine distance, conflict-free dispatch, state transitions, and Stripe logic. | Pure Python business rules; unaware of HTTP status headers where possible. |
| **Data Access (Model)** | `app/models/` | Executes parameterized MySQL queries (`SELECT`, `INSERT`, `UPDATE`). | Only talks to MySQL; returns clean Python dicts. |
| **Validation Contracts** | `app/schemas/` | Pydantic models defining what JSON the API expects and returns. | Automatic input validation and Swagger `/docs` generation. |
| **Infrastructure** | `app/core/` | Environment settings, MySQL connection helper/pool, password hashing, and JWT guards. | Shared utilities imported across all layers. |
| **View (Frontend)** | `frontend/` | Semantic HTML, split CSS, and native browser ES6 JavaScript modules per user role. | One JS module per dashboard/domain; centralized API helper. |

---

## 2. Target Directory Tree

```text
LondonCleanService-/
├── .env                          # Local secrets (ignored by Git)
├── .env.example                  # Template of required environment variables
├── .gitignore                    # Excludes .env, __pycache__, mysql_data, .venv
├── Dockerfile                    # Container build (points Uvicorn to app.main:app)
├── docker-compose.yml            # Orchestrates FastAPI, MySQL 8.0 (+ optional Stripe CLI)
├── requirements.txt              # Python dependencies
├── init.sql                      # Base MySQL schema & London demo seed data
├── PROJECT_STRUCTURE.md          # This architectural reference guide
│
├── app/                          # PYTHON BACKEND PACKAGE
│   ├── __init__.py               # Marks 'app' as a Python package
│   ├── main.py                   # App initialization, CORS, static mounts & router registration
│   │
│   ├── core/                     # Configuration, Database & Security
│   │   ├── __init__.py
│   │   ├── config.py             # Loads .env variables (DB, JWT, Stripe, Google keys, MOCK_MODE)
│   │   ├── database.py           # MySQL connection manager / pool & transaction rollback helper
│   │   └── security.py           # Bcrypt password hashing, JWT creation & require_role() guards
│   │
│   ├── schemas/                  # Pydantic Request & Response Models
│   │   ├── __init__.py
│   │   ├── auth.py               # Register, Login, Google OAuth, and Token schemas
│   │   ├── booking.py            # QuoteRequest, BookingCreate, StatusUpdate, ReviewCreate
│   │   └── payment.py            # CheckoutSessionRequest & Stripe webhook response models
│   │
│   ├── models/                   # Data Access / Repository Layer (SQL Queries Only)
│   │   ├── __init__.py
│   │   ├── user_repo.py          # Queries for users, roles, and staff_profiles
│   │   ├── booking_repo.py       # Queries for services, bookings, status logs, and reviews
│   │   └── payment_repo.py       # Queries for Stripe session IDs & event deduplication
│   │
│   ├── services/                 # Core Business Logic Layer
│   │   ├── __init__.py
│   │   ├── pricing_service.py    # London postcode zone detection & dynamic GBP (£) quote math
│   │   ├── maps_service.py       # Postcode geocoding, Haversine distance & TfL transit estimates
│   │   ├── dispatch_service.py   # Conflict-free cleaner filtering & proximity auto-matching
│   │   ├── booking_service.py    # Sequential state machine, UK GDPR key masking & refunds
│   │   └── stripe_service.py     # Stripe Checkout session creation & webhook signature handling
│   │
│   └── routers/                  # API Controllers (Grouped by Feature Domain)
│       ├── __init__.py
│       ├── auth.py               # /api/auth/* (register, login, google, demo-switch, me)
│       ├── bookings.py           # /api/services, /api/pricing/calculate, /api/bookings/*
│       ├── payments.py           # /api/payments/create-checkout-session & /webhook
│       ├── staff.py              # /api/staff/jobs & /api/staff/jobs/{id}/status
│       ├── manager.py            # /api/manager/dashboard-stats, /auto-match, /assign
│       └── maps.py               # /api/maps/geocode & /api/maps/distance
│
├── frontend/                     # FRONTEND VIEW LAYER (Zero-Build ES6 Modules)
│   ├── index.html                # Main SPA shell (Public Landing + Role Dashboards + Modals)
│   ├── success.html              # Stripe Checkout payment success confirmation page
│   ├── cancel.html               # Stripe Checkout payment cancelled page
│   │
│   ├── assets/                   # Static Images & Icons
│   │   └── logo.jpg              # Brand logo (moved from frontend/logo.jpg)
│   │
│   ├── css/                      # Modular Stylesheets
│   │   ├── base.css              # CSS variables, typography, navbar, buttons, modals & toasts
│   │   └── dashboards.css        # Role-specific styles (mobile cleaner cards, schedule grid)
│   │
│   └── js/                       # Modular ES6 JavaScript (Replaces monolithic app.js)
│       ├── main.js               # App entry point: initializes auth check, routing & global events
│       ├── api.js                # Centralized fetch() wrapper (attaches JWT & handles 401 expiry)
│       ├── auth.js               # Login/Register modal handlers, localStorage state & logout
│       ├── quote.js              # Public instant quote calculator & guest cart persistence
│       ├── customer.js           # Customer bookings list, progress stepper, cancel & reviews
│       ├── staff.js              # Cleaner mobile-first job cards, Google Maps links & status steps
│       └── manager.js            # Manager KPI cards, status filters, cleaner grid & auto-match
│
└── tests/                        # AUTOMATED TEST SUITE (Pytest)
    ├── __init__.py
    ├── conftest.py               # Shared Pytest fixtures, test client & auth token helpers
    ├── test_system.py            # End-to-end API workflow tests (moved from root)
    ├── test_sensitive_data.py    # UK GDPR access-code shielding & RBAC tests (moved from root)
    └── test_dispatch_conflicts.py # Verifies cleaners cannot be double-booked in the same slot
```

---

## 3. Structural Hints & Best Practices

### Backend Hints (`app/`)
1. **Don't Forget `__init__.py`:** Place an empty `__init__.py` file inside `app/` and every subfolder (`core`, `schemas`, `models`, `services`, `routers`). This allows clean absolute imports like `from app.services.pricing_service import PricingService`.
2. **Keep `app/main.py` Tiny (~50 lines):** It should only initialize `FastAPI()`, configure CORS middleware, mount `/static` to `frontend/`, expose `/health`, and call `app.include_router(...)` for each router.
3. **Isolate SQL in `app/models/`:** Whenever you need to fix a database bug (such as preventing double-bookings), you will know immediately to open `app/models/user_repo.py` or `app/models/booking_repo.py` instead of hunting through HTTP routes.
4. **Update Docker Entrypoint:** Because `main.py` moves inside the `app/` package, remember to update the `CMD` in your `Dockerfile` from `main:app` to `app.main:app`.

### Frontend Hints (`frontend/`)
1. **Use Native Browser ES6 Modules:** You do **not** need Node.js, npm, or Vite to split `app.js`. Simply load your entry script in `index.html` using `type="module"` (e.g., `<script type="module" src="/static/js/main.js"></script>`).
2. **Centralize API Calls in `js/api.js`:** Create one helper function in `api.js` that automatically reads `cleanlondon_token` from `localStorage`, attaches the `Authorization: Bearer ...` header, and intercepts `401 Unauthorized` responses to log the user out cleanly when their token expires.
3. **Separate Role Dashboards:** Keep `customer.js`, `staff.js`, and `manager.js` strictly focused on rendering their respective views. That way, redesigning the Cleaner mobile view will never accidentally break the Manager dispatch table.

### DevOps & Testing Hints
1. **Group All Tests in `tests/`:** Moving `test_system.py` and `test_sensitive_data.py` into `tests/` keeps your project root clean and lets you run the entire suite with a single `pytest` command inside Docker.
2. **Preserve Git History When Moving Files:** Use `git mv` instead of dragging and dropping files in your file explorer so VS Code **GitLens** keeps the full commit history attached to moved files.

---

## 4. Recommended Migration Workflow (Step-by-Step)

When you are ready to reorganize your files, follow this safe sequence in your VS Code terminal:

1. **Create a dedicated Git branch** so your current working `main` branch remains untouched until refactoring is verified:
   ```bash
   git checkout -b refactor/mvc-project-structure
   ```
2. **Create the new folder skeleton** (PowerShell / Windows Terminal):
   ```powershell
   mkdir app, app/core, app/schemas, app/models, app/services, app/routers, frontend/assets, frontend/css, frontend/js, tests
   ```
3. **Move existing static and test files using `git mv`**:
   ```bash
   git mv test_system.py tests/test_system.py
   git mv test_sensitive_data.py tests/test_sensitive_data.py
   git mv frontend/logo.jpg frontend/assets/logo.jpg
   git mv frontend/style.css frontend/css/base.css
   ```
4. **Move logic domain-by-domain:** Split `main.py` into `core` → `schemas` → `models` → `services` → `routers`, then split `frontend/app.js` into `api.js` → `auth.js` → `quote.js` → role dashboards.
5. **Verify in Docker:** Run `docker compose up --build` and check `http://localhost:8000/docs` and `pytest` before merging `refactor/mvc-project-structure` back into `main`.