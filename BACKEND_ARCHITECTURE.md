# Backend Architecture

## Runtime Entry Points

- `app/main.py` is a lightweight FastAPI composition entry point: application setup, CORS/security middleware, route inclusion, startup migration invocation, static frontend mount, and homepage.
- `main.py` remains a compatibility entry point that imports `app.main`.

## Modular Layout

- `app/core/` contains configuration, authentication dependencies, security helpers, and middleware.
- `app/database/` owns MySQL connection pooling, transactions, and additive operational migrations.
- `app/routes/` owns HTTP route definitions for auth, services, bookings, staff, manager administration/dispatch, notifications, location, and payments.
- `app/services/` owns authentication, booking, pricing, staff, manager, notification, location, and payment business logic.
- `app/schemas/` contains Pydantic request models for modular route inputs, including location and payments.
- `app/utils/` contains encryption, notification, and postcode/geolocation helpers.

## Active Modular Routes

The following route groups are registered from `app/routes/`:

- `/api/auth/*`
- `/api/services`
- `/api/pricing/calculate`
- `/api/bookings/*`
- `/api/staff/*`
- `/api/notifications/*`
- `/api/maps/*`
- `/api/payments/*`
- Manager dashboard, bookings, staff-vetting, assignment, reassignment, auto-match, payments, support, shifts, time-off, settings, notifications, audit, and reports under `/api/manager/*`

The modular route implementations preserve the existing authentication, role checks, idempotency, booking cancellation/reschedule behavior, staff state transitions, and dispatch conflict rules.

## Database and Operational Behavior

Database access uses `app/database/connection.py`. Transactions, connection pooling, notification outbox writes, and operational startup schema changes remain database-compatible with the existing Docker/MySQL setup.

Sensitive access notes continue to use the encryption utility and staff visibility masking logic.

## Payments and Webhooks

Stripe checkout creation, mock/live session behavior, session verification, webhook parsing, signature verification, and payment fulfillment are implemented in `app/services/payments.py` and exposed through `app/routes/payments.py`. Production webhook handling requires a valid Stripe signature and configured webhook secret. The mock development handler preserves the existing JSON payload fallback.

## Operational Startup

Additive table and column migrations are implemented in `app/database/migrations.py`. `app/main.py` invokes `ensure_operational_schema()` on startup.

## Validation

The refactor stages are validated with `python -m pytest -q`, Python import/startup checks, and OpenAPI route registration checks. The completed stages pass the existing 16-test suite.
