# Repository Requirements Audit

**Repository:** `NRP-Raja/LondonCleanService-`  
**Audit date:** 20 November 2026  
**Audited branch:** `docs/cross-dashboard-integration` (modular FastAPI branch used for this requirements review)  
**Audit type:** Static source, schema, route, frontend and test inspection  
**Status:** Findings recorded; no application code changed; no tests executed  
**Companion authority:** `REQUIREMENTS_BASELINE.md`

---

## 1. Executive summary

The repository contains useful working foundations: a modular FastAPI backend, MySQL schema, JWT role checks, Stripe Checkout/webhook code, pricing, postcode/travel calculations, manager dispatch, basic cleaner status updates, email outbox, vetting, shifts, support-case and audit primitives, plus a vanilla-JavaScript single-page frontend.

However, **the current implementation is not yet the agreed three-dashboard product**. Several important workflows exist only partially or contradict the agreed policy. Some high-risk defects directly affect money, access control and data consistency.

The most important conclusions:

1. The current booking creation path creates a `SCHEDULED` booking and sends a “booking confirmed” email before Stripe payment or manager approval.
2. Stripe checkout silently falls back to a mock checkout after provider errors. This must never happen in production.
3. The payment-session verification route has no authentication dependency and returns booking/customer details.
4. Cleaner job completion currently changes payment status to `PAID`. This violates the Stripe-only financial authority rule.
5. Staff can edit their weekly availability and holidays, despite the agreed manager-controlled schedule.
6. Manager assignment directly overwrites `bookings.staff_id`; there is no separate assignment acceptance/decline/expiry lifecycle.
7. There is no implementation found for the agreed booking-specific chat, persisted cleaning timer, before/after evidence upload, customer real-time progress, 10-minute slot hold, or 24-hour manager review expiry.
8. The manager page contains disabled navigation placeholders for major sections. Backend routes exist for some functions, but the full dashboard workflows are not implemented.
9. Notification utility SQL does not match the notification table created by the schema/migration.
10. The repository has multiple historical branches. The audited modular branch is not the same code tree as `main`; do not assume documentation or modular changes are already merged into `main`.

This is a static audit of repository contents. GitHub file inspection does not execute the application, connect to MySQL, validate deployed secrets or run tests. No claim is made that runtime tests passed.

## 2. Repository and branch baseline

### 2.1 Audited source branch

The review inspected the modular source on `docs/cross-dashboard-integration`, including:

- `app/main.py`
- `app/core/*`
- `app/database/*`
- `app/routes/*`
- `app/schemas/*`
- `app/services/*`
- `app/utils/*`
- `frontend/index.html`, `frontend/app.js`, `frontend/style.css`
- `init.sql`, Docker files and `tests/*`

This branch contains the modular FastAPI application and the role-dashboard requirements documents.

### 2.2 Main branch is not the same baseline

At audit time, `main` was at commit `381020121c875fc04712116dab6f11ce095e247d`. Its tree contains a much smaller/older application layout and does not contain the same modular `app/core`, `app/routes`, `app/services` and `app/schemas` tree inspected on the documentation branch.

**Decision:** The final requirements baseline describes the intended product, not a claim that the modular branch is already merged. Before implementation, the coding agent must inspect the checked-out branch, compare it with `main`, identify the intended source of truth and preserve working changes. Do not merge or overwrite branches automatically.

### 2.3 Architecture documentation is partly aspirational

`PROJECT_STRUCTURE.md` describes a future MVC/repository layout with `app/routers`, `app/models` and ES-module frontend files. The actual modular branch instead uses `app/routes`, direct SQL in services, and one large `frontend/app.js`. Treat the architecture document as guidance, not a description of the current file tree.

---

## 3. Findings by severity

Severity guide:

- **P0 — release blocker:** security, financial integrity or serious data-integrity risk.
- **P1 — required before the agreed product can launch:** core workflow missing or contradicts approved requirements.
- **P2 — important product completeness/maintainability work:** required for the planned full dashboard experience, but can be staged after core lifecycle.
- **OBS — observation:** existing useful foundation or documentation issue to account for.

### P0 — Release blockers

#### AUD-001 — Stripe checkout can silently switch to mock mode

**Evidence:** `app/services/payments.py`, especially checkout-session creation around lines 50–110.

The service sets mock mode when the configured key is absent or contains “mock”. More importantly, a broad exception handler around Stripe Checkout catches provider errors and changes `is_mock_stripe = True`, then returns a fabricated mock session URL.

**Risk:** A production Stripe outage, invalid key or provider error could be presented as a successful mock payment flow. This can mislead customers and create bookings with no real charge.

**Required outcome:**
- Production must fail closed when Stripe configuration is missing or invalid.
- Never switch from real Stripe to mock after a provider exception.
- Mock payment behaviour must require an explicit development/test-only flag and must be impossible in production.
- Log provider failures without exposing secrets or sensitive payment data.
- Add tests proving production checkout errors never create mock sessions or mark bookings paid.

#### AUD-002 — Payment-session verification route is unauthenticated

**Evidence:** `app/routes/payments.py`: `GET /api/payments/session/{session_id}/verify` has no `Depends(get_current_user)` or manager/customer role check. The service returns customer name, postcode, booking reference, service, date/time and amount.

**Risk:** Anyone obtaining a Stripe session identifier may retrieve personal and booking information. Session IDs are hard to guess, but they are not a replacement for object-level authorisation.

**Required outcome:**
- Require an authenticated customer who owns the booking, or a manager.
- Verify booking ownership and session association server-side.
- Return only the minimum data required for the success page.
- Do not expose customer PII to unauthorised requests.
- Add positive and negative customer/manager/other-customer tests.

#### AUD-003 — Cleaner completion can mark a booking paid

**Evidence:** `app/services/staff.py`, `update_staff_job_status`, around lines 140–148:

`payment_status = "PAID" if target_status == "COMPLETED" ...`

**Risk:** Staff job progress can create a false financial record. A cleaner could complete a job and thereby mark an unpaid booking paid.

**Required outcome:**
- Remove all payment-state mutation from staff progress services.
- Payment status can change only from verified Stripe events and authorised refund reconciliation.
- Add a regression test proving every staff job status leaves payment state unchanged.

#### AUD-004 — Production configuration has hard-coded fallback secrets and mock values

**Evidence:** `app/core/config.py` defaults JWT, Stripe, Google and Maps secrets to hard-coded development-looking strings, including a JWT signing key and mock Stripe secrets.

**Risk:** A missing environment variable can leave the application running with a known signing secret or fake payment configuration.

**Required outcome:**
- Validate mandatory production configuration at startup and fail fast if absent/weak.
- No hard-coded production-capable JWT, encryption, Stripe or OAuth secrets.
- Separate development/test defaults from production settings.
- Rotate any real secrets that may have been exposed; never commit real secrets.
- Keep `.env` out of Git and maintain a safe `.env.example`.

#### AUD-005 — Stripe webhook fulfilment is not durably idempotent

**Evidence:** `app/routes/payments.py` handles `checkout.session.completed` and calls `fulfill_stripe_payment`; `app/services/payments.py` updates the booking but does not persist a Stripe event ID/deduplication record. A fallback mock payment-intent ID is generated when one is missing.

**Risk:** Replayed or out-of-order webhooks can duplicate side effects/audit events; a fabricated payment intent identifier is not provider evidence. The handler also needs to verify the session is actually paid and reconcile amount, currency, booking and customer metadata.

**Required outcome:**
- Persist Stripe event IDs with a unique constraint and processing outcome.
- Process webhook and booking/payment state changes transactionally.
- Verify `payment_status`, currency, amount, session ID, metadata and booking ownership/association from the trusted event/provider record.
- Handle duplicate, delayed, failed, refunded and unexpected events safely.
- Never invent Stripe payment-intent IDs.
- Do not mark paid from a client redirect or arbitrary event payload.

### P1 — Core workflow and data-integrity gaps

#### AUD-006 — Booking is created as scheduled/confirmed before payment

**Evidence:** `app/services/booking.py`, booking INSERT around lines 132–163 sets status `SCHEDULED`, payment status `PENDING`; it immediately queues a “booking confirmed” email. The customer frontend then launches Stripe Checkout.

**Risk:** The booking appears scheduled/confirmed before payment and before manager review. This contradicts the agreed workflow.

**Required outcome:** Separate draft/checkout, verified payment, manager review and confirmed appointment states. Verified Stripe payment enters `PENDING_REVIEW`; manager approval moves it to `CONFIRMED`. No confirmation email before approval.

#### AUD-007 — No persisted 10-minute slot reservation was found

**Evidence:** Booking schema, `init.sql`, migrations and booking/payment services contain no explicit slot-hold entity, hold expiry or atomic availability reservation. The frontend stores an idempotency key but does not establish a server-side hold.

**Risk:** Two customers can attempt the same slot concurrently; payment may succeed after the intended slot has been taken.

**Required outcome:** Server-side atomic 10-minute hold, expiry/release, capacity locking, late-payment reconciliation and concurrency tests. Drafts do not reserve a slot.

#### AUD-008 — No manager approval/rejection and 24-hour review worker found

**Evidence:** `app/routes/manager.py` exposes booking list and assignment endpoints but no approve/reject route. `app/services/manager.py` does not implement the review timer/expiry worker.

**Risk:** The paid-booking review workflow cannot operate as specified.

**Required outcome:** Add explicit approve/reject actions, reviewer/reason/timestamp history, server-side 24-hour deadline, idempotent expiry worker, customer notifications and the agreed refund outcome.

**Policy note:** A full Stripe refund after manager rejection or 24-hour review expiry is the recommended safeguard in the integration contract, but still needs explicit business-owner sign-off before implementation.

#### AUD-009 — Assignment acceptance lifecycle is missing

**Evidence:** `app/services/manager.py` assignment functions update `bookings.staff_id` directly and notify the cleaner. No assignment table/history, acceptance/decline endpoint, response deadline, expiry worker or active assignment membership check was found.

**Risk:** The system cannot distinguish offered, accepted, declined, expired and reassigned assignments. Previous cleaners may retain access through the booking's current staff ID model.

**Required outcome:** Persist assignment records and history, default two-hour response deadline (manager-configurable), cleaner accept/decline endpoints, expiry handling, notifications and reassignment access revocation. Keep the customer booking confirmed when a cleaner declines.

#### AUD-010 — Existing job status model does not match agreed job progress

**Evidence:** `app/services/staff.py` transitions between legacy booking states `SCHEDULED → EN_ROUTE → IN_PROGRESS → COMPLETED`. No separate `ARRIVED` event or accepted assignment state is represented.

**Risk:** Booking approval, cleaner assignment and actual job execution are conflated.

**Required outcome:** Separate booking, assignment and job-progress state dimensions. Required cleaner progression: Assigned → Accepted → On the way → Arrived → Cleaning started → Cleaning completed. Keep legacy mappings/migrations backward-compatible.

#### AUD-011 — No persisted cleaning timer or completion evidence upload found

**Evidence:** Staff service updates status and notification only. No work-session/timer table, start/stop timestamp pair, elapsed duration persistence or photo-upload endpoint/storage contract was found in the inspected schema/routes/services.

**Risk:** Work duration and completion evidence cannot be trusted or reviewed.

**Required outcome:** Server-authoritative, idempotent timer; one active work session per assignment; before/after photos and notes; secure private storage; manager review; manager correction with reason/audit. Customer photo visibility remains manager-controlled by default.

#### AUD-012 — Booking-specific chat is absent

**Evidence:** No chat/conversation/message route, schema/table, service or frontend feature was found in the audited tree.

**Risk:** Agreed customer/cleaner/manager communication cannot happen in the product.

**Required outcome:** One conversation per booking; customer, current assigned cleaner and authorised manager participants; photo-only attachments; access revoked for previous/declined cleaner; durable message/read state and notification delivery. No separate duplicate messaging systems.

#### AUD-013 — Staff can change their own availability and holidays

**Evidence:** `app/routes/staff.py` exposes `PUT /api/staff/schedule`, `POST /api/staff/holidays`, and `DELETE /api/staff/holidays/{holiday_date}`; the staff UI provides editable weekly hours and holiday controls.

**Risk:** Conflicts with the agreed manager-controlled schedule and can invalidate dispatch decisions.

**Required outcome:** Staff schedule is read-only in the first release. Manager controls shifts, availability, time-off decisions and changes. Staff may submit an availability/time-off request only if this is later explicitly added; it is not part of the agreed baseline.

#### AUD-014 — Staff earnings UI conflicts with agreed staff scope

**Evidence:** `GET /api/staff/earnings`, `get_staff_earnings` and the staff dashboard show earnings and a hard-coded “70% cleaner share”.

**Risk:** A commission/pay arrangement was not agreed and the displayed 70% is not a confirmed business rule. The staff dashboard was agreed to show job history and hours, not financial reports.

**Required outcome:** Remove the 70% earnings/commission display from first-release staff scope. Show completed job history and recorded job duration only. Do not invent cleaner pay calculations.

#### AUD-015 — Customer booking response exposes cleaner contact details

**Evidence:** `app/services/booking.py`, `get_my_bookings` selects `u.phone AS staff_phone` for assigned cleaners. Customer UI displays the cleaner profile.

**Risk:** Contradicts the agreed policy that customer sees cleaner name/photo/role but not the cleaner's personal phone number.

**Required outcome:** Remove cleaner personal phone from customer API payloads/UI. Use business contact details and booking chat for communication.

#### AUD-016 — Staff API returns more booking/payment data than needed

**Evidence:** `app/services/staff.py`, `get_staff_jobs` selects `b.*`, including fields such as payment status, amount and Stripe references, in addition to address/customer details.

**Risk:** Violates least privilege and unnecessarily exposes financial/provider identifiers to cleaners.

**Required outcome:** Explicit response DTO selecting only operational fields needed for the cleaner's active assigned job. Never return Stripe identifiers, card/payment details or manager-only financial data to staff.

#### AUD-017 — Notification schema and utility are inconsistent

**Evidence:**
- `init.sql` and `app/database/migrations.py` create `notification_outbox` with `recipient_address` and statuses `QUEUED/SENT/FAILED`.
- `app/utils/notifications.py` inserts `recipient_email` and status `PENDING`.

**Risk:** Notification inserts can fail at runtime due to unknown column/enum values. Notification reliability is a core cross-dashboard dependency.

**Required outcome:** Define one canonical notification schema and repository/service contract. Use an outbox written in the same transaction as the business event, with deduplication, retry/error metadata, in-app read state and channel delivery tracking. Add integration tests.

#### AUD-018 — Refund state is set before Stripe confirms it

**Evidence:** `app/services/booking.py` cancellation calls `stripe.Refund.create` and then sets booking `payment_status='REFUNDED'` immediately. No refund webhook/event reconciliation path was found.

**Risk:** A requested refund may fail or remain pending while the UI says refunded.

**Required outcome:** Track `REFUND_PENDING`, `REFUNDED`, `REFUND_FAILED` (and partial refund where relevant) separately. Only trusted Stripe events/provider retrieval can confirm completion. Store Stripe refund IDs and idempotency keys.

#### AUD-019 — Current late-cancellation behaviour contradicts approved policy

**Evidence:** `app/services/booking.py` applies a 50% fee and issues a partial refund under 24 hours. `tests/test_system.py` explicitly asserts the 50% late-fee policy.

**Risk:** The agreed policy is no automatic refund under 24 hours; exceptions are manager-reviewed. The current implementation and tests encode a different policy.

**Required outcome:** Remove automatic 50% fee/refund. Under 24 hours, create a manager-review request with no automatic refund. At least 24 hours, full Stripe refund to original payment method. Update tests and customer copy.

#### AUD-020 — Manager finance metrics are misleading

**Evidence:** `app/services/manager.py`, `get_dashboard_stats`:
- daily revenue sums booking value scheduled today, not collected money.
- total revenue is lifetime non-cancelled booking value.
- “collected today/month” groups paid bookings by appointment date, not actual Stripe payment date.
- unpaid includes booking payment states rather than a reconciled payment ledger.
- overdue is `None`.
`manager_report_summary` uses similar booking-date grouping.

**Risk:** Manager may make business decisions from incorrectly labelled financial totals.

**Required outcome:** Separate booking value, amount paid, amount refunded, net collected and outstanding. Collection reports use actual Stripe payment/refund timestamps. Use GBP Decimal/fixed-point values. Do not display overdue unless a real due-date rule exists. Do not claim profit without a complete cost model.

#### AUD-021 — Manager UI is incomplete; major navigation items are disabled

**Evidence:** `frontend/index.html` manager sidebar includes disabled links for schedule, finance, support, quality, reports, notifications, settings and audit. The actual rendered sections include overview/dispatch and vetting. `frontend/app.js` loads KPIs, bookings and vetting only.

**Risk:** The existing sidebar suggests capabilities that are not usable, and managers cannot perform the full agreed operations from the dashboard.

**Required outcome:** Build the manager workspace as functional, role-protected sections. Keep the visible/collapsible accessible sidebar, responsive mobile navigation, clear active states, keyboard support and no dead/disabled menu items presented as available features.

#### AUD-022 — Manager schedule API is incomplete

**Evidence:** Manager routes include `GET /shifts`, `POST /shifts`, `GET /time-off`, and time-off review. No manager shift update/move/delete endpoint or staff availability management route was found in the inspected router. The staff UI edits its own weekly availability.

**Risk:** Manager cannot fully control the schedule as agreed.

**Required outcome:** Manager create/edit/move/cancel shifts, manage weekly availability, review time-off, prevent overlaps and notify staff. Staff read-only schedule.

#### AUD-023 — Booking cancellation and reschedule permissions need policy alignment

**Evidence:** Customer/manager cancel and reschedule routes exist. Current cancellation allows only `SCHEDULED` and blocks late cancellation via automatic 50% fee. Reschedule accepts only `SCHEDULED` and checks the new date/time but does not implement the agreed 24-hour self-service/manager-approval split or the pending-review state.

**Required outcome:** Implement agreed 24-hour customer self-service threshold; under 24 hours submit a manager request; preserve slot concurrency safety; notify customer and cleaner; reconcile assignment changes. Apply cancellation policy in section AUD-019.

#### AUD-024 — Booking creation, payment fulfilment and notifications are not transactionally consistent

**Evidence:** `get_db()` uses PyMySQL connections with `autocommit=True`. Booking creation and Stripe fulfilment use `get_db` while performing multiple SQL writes. Explicit `get_transaction()` exists but is not used by those workflows.

**Risk:** Partial booking/payment/audit/notification writes can remain after an intermediate failure.

**Required outcome:** Use explicit database transactions for multi-record business state changes and a transactional outbox. External Stripe API calls must be coordinated using durable intent/idempotency records and retry-safe reconciliation; do not hold database locks during slow provider calls.

### P2 — Product completeness and quality gaps

#### AUD-025 — Customer dashboard is a basic list, not the agreed self-service dashboard

**Evidence:** `frontend/index.html` and `frontend/app.js` show a customer booking table and basic progress stepper. No full booking detail view, notification centre, chat, saved payment methods, guest account flow, deletion request UI, session management, or complete receipt workflow was found in the audited frontend/API.

**Required outcome:** Implement the customer features listed in `REQUIREMENTS_BASELINE.md` in staged increments.

#### AUD-026 — No real-time event transport or refresh recovery contract found

**Evidence:** The frontend loads customer bookings, staff jobs and manager data through fetch calls. No WebSocket/SSE implementation or polling/reconnect event model was found.

**Required outcome:** Implement a maintainable real-time mechanism or polling fallback. Backend remains authoritative; reconnect must refetch current state.

#### AUD-027 — Browser push notifications are not implemented

**Evidence:** Notification outbox supports EMAIL/SMS only; no service worker, push subscription storage or browser push delivery code found.

**Required outcome:** In-app notifications are durable baseline. Browser notifications require explicit permission and a reliable fallback. Email remains for customer transactional messages.

#### AUD-028 — Manager reports/support/audit primitives are partial

**Evidence:** Some routes and tables exist for support cases, audit logs, settings and summary reports, but UI sections are disabled. Audit logging uses both `activity_audit_log` and a legacy `audit_log` utility. No full report export or comprehensive immutable audit contract was found.

**Required outcome:** Consolidate audit writes, define protected append-only history, implement actual manager pages and report semantics. Add export only after each metric is correct.

#### AUD-029 — Staff vetting defaults may be unsafe

**Evidence:** `init.sql` gives `verified_dbs` and `right_to_work_verified` default TRUE; the operational migration adds `right_to_work_verified` with default TRUE and vetting status APPROVED.

**Risk:** Newly added staff records can appear vetted without an actual check.

**Required outcome:** New staff default to PENDING/unverified. Only manager evidence review can approve. Preserve existing data through an explicit migration/backfill review; do not silently mark existing records verified.

#### AUD-030 — Authentication and frontend token storage need hardening review

**Evidence:** Frontend stores JWT in `localStorage`; JWT configuration uses HS256 and default 480-minute expiry. Password helper truncates input to 72 bytes for bcrypt. No refresh/revocation/session inventory or password reset flow was found in the inspected route list.

**Required outcome:** Retain secure authentication while planning a safer session strategy (prefer HttpOnly, Secure, SameSite cookies if the architecture can support CSRF protection; otherwise document and harden the token model). Add one-time expiring password reset, session/device controls, logout/revocation and robust password length validation. Never silently truncate distinct passwords to the same bcrypt input.

#### AUD-031 — Security headers are incomplete

**Evidence:** `app/core/middleware.py` sets `X-Frame-Options: SAMEORIGIN`, nosniff, referrer and permissions policy; HSTS only in production. No Content-Security-Policy is set.

**Required outcome:** Add a tested CSP compatible with the frontend, use an appropriate frame policy (DENY unless framing is a real requirement), preserve HSTS in HTTPS production, and review all security headers.

#### AUD-032 — Runtime migrations are not a versioned migration system

**Evidence:** `app/database/migrations.py` runs additive DDL and data updates at application startup. It modifies booking enum and creates tables on every startup check.

**Risk:** Schema changes are difficult to review, roll back and coordinate across multiple app instances.

**Required outcome:** Adopt ordered, versioned migrations with backups, migration status tracking, explicit rollback/forward-fix strategy and staging verification. Never drop/reset production data.

#### AUD-033 — Existing end-to-end test is unsafe as a routine suite

**Evidence:** `tests/test_system.py` is a live HTTP script against `127.0.0.1:8000`; it modifies booking records before testing and creates records far beyond the agreed 30-day booking horizon. It asserts the old 50% late-fee policy and old auto-match-before-manager-review workflow.

**Risk:** Running it against a shared or production database can mutate real data. Its assertions are now obsolete.

**Required outcome:**
- Split unit, API integration and end-to-end tests.
- Use isolated disposable test DB and seeded fixtures.
- Never run destructive test setup against production/shared data.
- Update old assumptions to the baseline.
- Add full Stripe webhook, booking hold, manager review, assignment acceptance, chat, timer, refund and role/IDOR coverage.
- Record actual test commands and outcomes in each implementation phase.

---

## 4. Existing capabilities worth preserving

The audit found foundations that should be reused where technically sound:

| Area | Existing foundation | Required treatment |
|---|---|---|
| Backend | FastAPI app composition and route/service/schema separation | Preserve modular backend; improve boundaries/contracts |
| Database | MySQL 8, foreign keys, DECIMAL money columns, indexes | Extend safely with versioned migrations |
| Authentication | JWT login, customer-only public registration, role dependency | Preserve and harden; manager-created staff accounts |
| Passwords | bcrypt hashing/checking | Fix truncation/configuration and reset/session gaps |
| Pricing | Quote service and server-side pricing calculation | Preserve; always validate amount server-side |
| Stripe | Hosted Checkout, webhook signature validation in production | Preserve real integration; remove silent mock fallback and add durable event/refund reconciliation |
| Dispatch | Postcode distance and schedule conflict checks | Preserve, test, and connect to assignment entity and manager approval |
| Sensitive data | Fernet encryption for access notes and staff masking helper | Preserve; tighten response-field minimisation and key management |
| Manager operations | Vetting, shifts/time-off, support, settings, reports and audit primitives | Complete and reconcile with dashboard |
| Notifications | MySQL outbox concept and email delivery primitives | Fix schema mismatch and make transactional/deduplicated |
| Frontend | Existing responsive single-page app and manager sidebar shell | Preserve brand/working UI; implement role modules and functional navigation |
| Tests | Existing security, dispatch, sensitive-data and payment test files | Keep useful cases; isolate DB and replace stale expectations |

Do not rewrite working features wholesale. First add tests around current behaviour, then refactor in small branches.

## 5. Cross-cutting mismatches that must be resolved together

1. **Booking state:** `SCHEDULED` currently means several things. Separate checkout/payment, manager review, confirmed appointment and job progress.
2. **Payment authority:** Stripe events own payment state. Neither staff completion nor manager manual verification can create a paid state.
3. **Assignment authority:** Manager assigns; cleaner accepts/declines; manager reassigns. Store assignment history separately.
4. **Schedule authority:** Manager owns schedule. Staff sees it read-only.
5. **Communication:** One booking chat and one central notification/event model.
6. **Data access:** Customers see no cleaner private phone; staff sees no Stripe/financial fields; prior cleaners lose current booking access.
7. **Cancellation:** Replace current 50% automatic late fee with no automatic refund under 24 hours and manager review.
8. **Manager finance:** Replace misleading booking-date “revenue” labels with Stripe ledger-based collection/refund dates.
9. **Notifications:** Fix table/utility mismatch before relying on notification delivery.
10. **Source control:** Keep modular feature baseline and `main` distinction explicit; no automatic merge.

## 6. Recommended implementation order

The coding agent must not attempt a giant rewrite. Once development is explicitly authorised, use this sequence:

1. **Phase 0 — Baseline and safety:** Confirm branch, diff against main, backup, dependency/security review, current tests, schema snapshot, test database.
2. **Phase 1 — Domain/data contracts:** Define canonical booking/payment/assignment/job states, migration plan, DTOs, permission matrix, audit/outbox model.
3. **Phase 2 — Booking + Stripe integrity:** Checkout hold, Stripe-only fail-closed integration, webhook dedupe, verified payment, refund reconciliation.
4. **Phase 3 — Manager review:** Approve/reject, 24-hour expiry worker, review notifications, decision audit.
5. **Phase 4 — Dispatch + assignment acceptance:** Manager assignment, conflict checks, cleaner accept/decline/timeout/reassignment and access revocation.
6. **Phase 5 — Cleaner job execution:** Progress events, timer, notes/photos, manager corrections and customer-safe timeline.
7. **Phase 6 — Shared communication:** Booking chat, participants, attachments, notification outbox and browser push.
8. **Phase 7 — Dashboard completion:** Customer self-service, staff mobile-first view, manager functional sections and responsive navigation.
9. **Phase 8 — Finance/reporting/security:** Stripe ledger, accurate KPIs, audit, account controls, export, security headers and production configuration.
10. **Phase 9 — End-to-end acceptance:** Cross-role scenarios, concurrency, IDOR, Stripe webhook replay, refund, accessibility and regression tests.

Each phase uses a new feature branch, tests before merge, explicit review, no direct main edits, and no merge without the user's approval.

## 7. Audit limitations

- Static source inspection only; the application and database were not executed.
- No test suite was run.
- No production environment, deployed infrastructure, Stripe account, webhook endpoint, database contents or secret store was accessed.
- File/line references identify inspected source locations; a coding agent must verify them against the exact checked-out commit before changing code.
- This audit is a snapshot of the named branch, not proof of the state of `main` or a deployed environment.

**Audit conclusion:** The repository has a useful foundation but is not yet ready for implementation of the complete agreed product without the P0 and P1 corrections. Use `REQUIREMENTS_BASELINE.md` as the single product/technical requirements authority and this audit as the factual map of existing code gaps.
