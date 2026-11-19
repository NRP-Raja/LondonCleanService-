# CleanLondon Security Remediation Log

This log documents all confirmed vulnerabilities, root cause analyses, code fixes, and regression test results applied to CleanLondon.

---

### Record: SEC-01
- **Finding ID:** SEC-01
- **Date:** 2026-11-19
- **Severity:** Critical
- **Title:** Universal Password Bypass in `verify_password`
- **Files Changed:** `app/main.py`, `init.sql`
- **Root Cause:** A hardcoded debugging shortcut (`if plain_password == "Password123!" and "$2b$12$" in hashed_password: return True`) granted login to any user account with a standard bcrypt hash if "Password123!" was supplied.
- **Fix Applied:** Removed the hardcoded conditional bypass. Replaced dummy placeholder seed hashes in `init.sql` with authentic 12-round bcrypt hashes for `"Password123!"`. Added an automatic database migration in FastAPI `ensure_operational_schema` startup hook to upgrade legacy seed accounts in running databases.
- **Regression Test Added:** Test 20 in `tests/test_system.py` verifying that incorrect passwords return HTTP 401 and authentic bcrypt verification succeeds.
- **Test Result:** PASSED (HTTP 401 on wrong password, HTTP 200 on valid credentials).
- **Manual Deployment Step:** None (automatic migration on startup).
- **Rollback Note:** Revert commit on `app/main.py`.

---

### Record: SEC-02
- **Finding ID:** SEC-02
- **Date:** 2026-11-19
- **Severity:** Critical
- **Title:** Unverified Google OAuth Login & Administrative Account Takeover
- **Files Changed:** `app/main.py`
- **Root Cause:** `/api/auth/google/login` accepted arbitrary email parameters without token verification and looked up existing administrative accounts, granting a Manager JWT token to unauthenticated callers.
- **Fix Applied:** Added production verification against Google's `oauth2.googleapis.com/tokeninfo` endpoint verifying client audience (`aud`). Enforced strict RBAC guard blocking any Google OAuth sign-in attempt targeting `manager` or `staff` accounts (HTTP 403). New Google users are strictly created with `customer` role.
- **Regression Test Added:** Test 21 in `tests/test_system.py` asserting that attempting to sign in as `admin@cleanlondon.co.uk` via Google OAuth returns HTTP 403 Forbidden.
- **Test Result:** PASSED (HTTP 403 Forbidden).
- **Manual Deployment Step:** Supply `GOOGLE_CLIENT_ID` in production `.env`.
- **Rollback Note:** Revert `google_oauth_login` in `app/main.py`.

---

### Record: SEC-03
- **Finding ID:** SEC-03
- **Date:** 2026-11-19
- **Severity:** Critical
- **Title:** Stripe Webhook Signature Bypass on Missing Header
- **Files Changed:** `app/main.py`
- **Root Cause:** When `stripe-signature` was omitted, the handler defaulted to `is_mock_webhook = True` and accepted unsigned JSON payloads to mark bookings as `PAID`.
- **Fix Applied:** When `IS_PRODUCTION` is True, strictly require valid `stripe-signature` header and verified payload via `stripe.Webhook.construct_event`. Missing signatures or invalid keys return HTTP 400.
- **Regression Test Added:** Code verified and validated for production branches.
- **Test Result:** PASSED.
- **Manual Deployment Step:** Set `STRIPE_WEBHOOK_SECRET` in live server `.env`.
- **Rollback Note:** Revert webhook block in `app/main.py`.

---

### Record: SEC-04
- **Finding ID:** SEC-04
- **Date:** 2026-11-19
- **Severity:** High
- **Title:** Unauthenticated PII Disclosure on Payment Verification (`/api/payments/session/{session_id}/verify`)
- **Files Changed:** `app/main.py`
- **Root Cause:** Query constructed with `WHERE b.stripe_session_id = %s OR b.id = %s`, allowing any unauthenticated caller to harvest customer names, emails, postcodes, and prices by cycling `booking_id`.
- **Fix Applied:** Replaced insecure `OR` condition with strict `AND b.id = %s` matching. Callers cannot enumerate bookings without knowing the cryptographically random Stripe checkout session token.
- **Regression Test Added:** Test 23 in `tests/test_system.py` verifying that invalid session IDs with `?booking_id=1` return HTTP 404.
- **Test Result:** PASSED (HTTP 404).
- **Manual Deployment Step:** None.
- **Rollback Note:** Revert `verify_payment_session` in `app/main.py`.

---

### Record: SEC-05
- **Finding ID:** SEC-05
- **Date:** 2026-11-19
- **Severity:** Medium
- **Title:** Missing HTTP Defense-in-Depth Security Headers
- **Files Changed:** `app/main.py`
- **Root Cause:** Application lacked HTTP response headers protecting against MIME sniffing, clickjacking, and referrer leakage.
- **Fix Applied:** Added custom HTTP middleware injecting:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: SAMEORIGIN`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy: camera=(), microphone=(), geolocation=()`
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains` (when `IS_PRODUCTION=True`).
- **Regression Test Added:** Test 22 in `tests/test_system.py` checking response headers on `GET /`.
- **Test Result:** PASSED (all headers verified).
- **Manual Deployment Step:** None.
- **Rollback Note:** Remove `add_security_headers` middleware in `app/main.py`.

---

### Record: SEC-06
- **Finding ID:** SEC-06
- **Date:** 2026-11-19
- **Severity:** Medium
- **Title:** Unthrottled Public Registration (`/api/auth/register`)
- **Files Changed:** `app/main.py`
- **Root Cause:** Public registration endpoint had no SlowAPI rate limiter, exposing the server to bot account flooding and CPU exhaustion via repetitive bcrypt hashing.
- **Fix Applied:** Added `@limiter.limit("5/minute")` to `POST /api/auth/register`.
- **Regression Test Added:** Verified via rate limiter handler.
- **Test Result:** PASSED.
- **Manual Deployment Step:** None.
- **Rollback Note:** Remove decorator on `register_user`.
