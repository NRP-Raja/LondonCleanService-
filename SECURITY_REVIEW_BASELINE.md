# CleanLondon Security Review Baseline

**Audit Date:** 19 November 2026  
**Auditor:** Antigravity AppSec & Full-Stack Reviewer  
**Branch:** `security/audit-and-hardening` (branched from `main`)  
**Scope:** Repository codebase (`app/main.py`, `frontend/`, `init.sql`, `docker-compose.yml`, `tests/`)  
**Status:** Initial Assessment & Baseline Completed (Awaiting Owner Approval)

---

## 1. Project Architecture & Runtime Summary

| Component | Technology & Details |
| :--- | :--- |
| **Backend Framework** | FastAPI (Python 3.11) with Uvicorn ASGI server |
| **Database** | MySQL 8.0 with InnoDB, PyMySQL client & thread-safe LIFO connection pool |
| **Frontend** | Vanilla JavaScript SPA (`frontend/index.html`, `frontend/app.js`, `frontend/style.css`) |
| **Containerization** | Docker Compose running `cleanlondon_api`, `cleanlondon_mysql`, `cleanlondon_mailpit` (and optional Stripe CLI profile) |
| **Authentication** | Stateless JWT (HS256) via `Authorization: Bearer <token>`, stored in browser `localStorage` |
| **Payment Gateway** | Stripe Hosted Checkout (`/api/payments/create-checkout-session` & `/api/payments/webhook`) |
| **Local Notifications** | SMTP delivery to Mailpit (`notifications@cleanlondon.local`) with MySQL `notification_outbox` logging |
| **Access Code Encryption** | AES-256 Fernet encryption at rest for customer key-safe codes and intercom PINs |

---

## 2. Security-Sensitive Components & Trust Boundaries

```
[Unauthenticated Web Visitor]
             │
             ▼ (Untrusted Boundary: Registration, Login, Quote, Webhook)
┌────────────────────────────────────────────────────────┐
│ CleanLondon FastAPI Gateway                            │
│  - Input validation via Pydantic schemas              │
│  - SlowAPI IP-based rate limiting                     │
│  - JWT Authentication & RBAC (Customer, Staff, Manager)│
└────────────────────────────────────────────────────────┘
             │
             ├──────────────────────────┬─────────────────────────┐
             ▼                          ▼                         ▼
   [MySQL 8.0 Database]       [Stripe API & Webhooks]      [Mailpit SMTP]
   - Parameterized queries    - Signature verification     - Transactional alerts
   - AES-256 encrypted PINs   - Payment state machine      - Outbox logging
```

1. **Client Browser → API Server:** Untrusted boundary. All user IDs, roles, amounts, and statuses must be server-validated.
2. **Customer vs. Staff vs. Manager Permissions:** RBAC boundary enforced by `require_role(...)`.
3. **Stripe Webhook → API Server:** External boundary requiring cryptographic signature verification.
4. **Data at Rest in Database:** Storage of customer residential key-safe and intercom PINs under UK GDPR.

---

## 3. Existing Security Controls (Verified Working)

- **Parameterized SQL Queries:** 100% of database queries use `%s` parameterization via PyMySQL, preventing SQL injection.
- **UK GDPR Access Note Encryption at Rest:** Customer key-safe codes and intercom PINs are encrypted at rest with AES-256 Fernet.
- **Role Isolation on Public Registration:** `/api/auth/register` strictly enforces role `customer`, discarding any client-submitted `role`.
- **Cleaner Status Shielding:** Cleaners cannot view entry PINs while jobs are `SCHEDULED`; PINs are masked until the cleaner transitions to `EN_ROUTE`.
- **Idempotency & Double-Booking Prevention:** Booking creation enforces idempotency keys and blocks rapid duplicate submissions.
- **Sequential State Machine & Time Guardrails:** Cleaner job statuses enforce `SCHEDULED -> EN_ROUTE -> IN_PROGRESS -> COMPLETED` with guardrails preventing premature status advancement.
- **Late Cancellation Enforcement:** >24h free cancellation vs 50% penalty within 24 hours.

---

## 4. Initial Audit Findings

| ID | Title | Severity | Affected File / Route | Evidence & Impact | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SEC-01** | **Universal Demo Password Backdoor in `verify_password`** | **CRITICAL** | `app/main.py:160` | Line 160 unconditionally grants login to *any* account whose hash contains `$2b$12$` if the supplied password is `"Password123!"`. An attacker knowing any manager or customer email can log in with `"Password123!"`. | Confirmed Vulnerability |
| **SEC-02** | **Unverified Google OAuth Login Allows Account Takeover** | **CRITICAL** | `app/main.py:795` | `/api/auth/google/login` accepts any email in the JSON body without cryptographically verifying `payload.id_token`. An attacker can submit `{"email": "admin@cleanlondon.co.uk"}` to obtain a valid Manager JWT. | Confirmed Vulnerability |
| **SEC-03** | **Unauthenticated Stripe Webhook Bypass via Missing Signature** | **CRITICAL** | `app/main.py:2086` | If `stripe-signature` header is omitted, the endpoint treats the request as a mock webhook and accepts unverified JSON payloads to mark arbitrary bookings as `PAID`. In production, missing signatures must be rejected with HTTP 400. | Confirmed Vulnerability |
| **SEC-04** | **Unauthenticated PII Disclosure in Payment Verification Endpoint** | **HIGH** | `app/main.py:2172` | `GET /api/payments/session/{session_id}/verify` requires no authentication and permits `?booking_id=X` query params, returning customer name, email, postcode, and booking total to any unauthenticated visitor. | Confirmed Vulnerability |
| **SEC-05** | **Missing HTTP Security Headers** | **MEDIUM** | `app/main.py:512` | The application returns no security headers (`Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`). | Confirmed Vulnerability |
| **SEC-06** | **Unthrottled Public User Registration (`/api/auth/register`)** | **MEDIUM** | `app/main.py:727` | While `/api/auth/login` is rate limited to 10/min, `/api/auth/register` has no rate limiter, permitting registration flooding and CPU exhaustion via repetitive bcrypt hashing. | Confirmed Vulnerability |
| **SEC-07** | **Insecure Fallback Secrets in Production** | **MEDIUM** | `app/main.py:54, 72` | If `JWT_SECRET_KEY` or `STRIPE_WEBHOOK_SECRET` are omitted in `.env`, the code falls back to hardcoded strings instead of failing fast in production. | Confirmed Vulnerability |
| **SEC-08** | **Missing `pytest` in Project Dependencies** | **LOW / QA** | `requirements.txt` | Dedicated test files (`tests/test_sensitive_data.py`, `tests/test_demo_switch_security.py`, `tests/test_dispatch_conflicts.py`) import `pytest`, but `pytest` is not included in `requirements.txt`. | Confirmed Issue |

---

## 5. Prioritized Remediation Plan

### Priority 0 — Critical Exposure & Auth Bypasses
1. **Remove Backdoor in `verify_password`:** Delete the `"Password123!"` shortcut. Seed database demo accounts with genuine bcrypt hashes matching `"Password123!"` so standard password verification works without bypasses.
2. **Harden Google OAuth Login:** Require valid Google token verification, or gate mock Google authentication behind `ENVIRONMENT=development` and reject arbitrary existing account impersonation.
3. **Strict Webhook Signature Enforcement:** If running in production or when live keys are present, strictly require valid `stripe-signature` and reject unauthenticated payloads.

### Priority 1 — High Risk Authorization & Data Protection
4. **Secure Payment Session Verification:** Require authentication on `/api/payments/session/{session_id}/verify` (verifying `booking.customer_id == user.id` or manager), and eliminate unauthenticated `OR b.id = %s` disclosure.

### Priority 2 — Medium Risk Hardening
5. **Add HTTP Security Headers Middleware:** Inject `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, and an appropriate CSP.
6. **Rate Limit Registration:** Apply `@limiter.limit("5/minute")` on `/api/auth/register` to block brute-force account creation.
7. **Production Secret Safeguards:** Add startup validation to refuse running in production if `JWT_SECRET_KEY` is using the default placeholder.

### Priority 3 — Testing & Quality Hygiene
8. **Add `pytest` to `requirements.txt` / Container:** Ensure the complete test suite runs seamlessly under both `python tests/test_system.py` and `pytest tests/`.

---

## 6. Proposed Verification Tests

- **Test SEC-01:** Attempt logging in with `"Password123!"` against an account with a different real password; verify rejection (HTTP 401).
- **Test SEC-02:** Attempt unverified Google login against `admin@cleanlondon.co.uk`; verify rejection or restriction.
- **Test SEC-03:** Send unauthenticated webhook payload with missing `stripe-signature`; verify HTTP 400 rejection in production mode.
- **Test SEC-04:** Attempt unauthenticated PII harvest via `/api/payments/session/fake/verify?booking_id=1`; verify HTTP 401 / access denied.
- **Test SEC-05:** Inspect response headers on `GET /` and `GET /api/services`; verify `X-Content-Type-Options`, `X-Frame-Options`, etc.
- **Test SEC-06:** Hammer `/api/auth/register` 6 times in 1 minute; verify HTTP 429 Too Many Requests.
- **Regression Tests:** Execute full 19-test suite in `tests/test_system.py` to guarantee zero regressions to booking, dispatch, and pricing workflows.

---

## 7. Actions Requiring Owner Approval

1. **Removal of Universal Password Bypass (`Password123!` shortcut):** Confirms that only accounts explicitly seeded with that password can use it.
2. **Google OAuth Production Behavior:** Clarify whether live Google Client ID verification should be enforced when `MOCK_MODE=false`.
3. **Approval to proceed with Priority 0 and Priority 1 remediations on branch `security/audit-and-hardening`.**
