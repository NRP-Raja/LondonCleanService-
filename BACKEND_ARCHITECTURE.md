# Backend Architecture

## Runtime Entry Points

- `app/main.py` creates the FastAPI application, shared middleware/configuration, operational startup migration, static frontend mount, and still owns endpoints not yet extracted.
- `main.py` remains a compatibility entry point that imports `app.main`.

## Modular Layout

- `app/core/` contains configuration, authentication dependencies, security helpers, and middleware.
- `app/database/` owns MySQL connection pooling and transaction context managers.
- `app/routes/` owns HTTP route definitions for auth, services, bookings, staff, and the dispatch subset of manager operations.
- `app/services/` owns authentication, booking, pricing, staff, and manager business logic.
- `app/schemas/` contains Pydantic request models for modular route inputs.
- `app/utils/` contains encryption, notification, and postcode/geolocation helpers.

## Active Modular Routes

The following route groups are registered from `app/routes/`:

- `/api/auth/*`
- `/api/services`
- `/api/pricing/calculate`
- `/api/bookings/*`
- `/api/staff/*`
- Manager dashboard, booking, staff-vetting, assignment, reassignment, and auto-match routes under `/api/manager/*`

The modular route implementations preserve the existing authentication, role checks, idempotency, booking cancellation/reschedule behavior, staff state transitions, and dispatch conflict rules.

## Database and Operational Behavior

Database access uses `app/database/connection.py`. Transactions, connection pooling, notification outbox writes, and operational startup schema changes remain database-compatible with the existing Docker/MySQL setup.

Sensitive access notes continue to use the encryption utility and staff visibility masking logic.

## Remaining Monolith Areas

`app/main.py` still contains legacy implementations for notifications, additional manager administration endpoints, maps/geocoding, and Stripe checkout/webhook operations. Those endpoints remain active and have not been duplicated: they are registered directly by the existing FastAPI application.

The remaining cleanup work is to move those route groups into dedicated routers and service modules, then remove their legacy implementations only after route-schema and integration verification.

## Validation

The refactor stages are validated with `python -m pytest -q`, Python import/startup checks, and OpenAPI route registration checks. The completed stages pass the existing 16-test suite.
