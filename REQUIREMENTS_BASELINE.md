# LondonCleaningService — Authoritative Requirements Baseline

**Document:** Single product, workflow, architecture and acceptance baseline  
**Status:** Consolidated planning baseline — development not yet authorised  
**Prepared:** 20 November 2026  
**Repository:** `NRP-Raja/LondonCleanService-`  
**Audited source snapshot:** `docs/cross-dashboard-integration`  
**Companion evidence:** `REPOSITORY_REQUIREMENTS_AUDIT.md`  
**Audience:** Product owner, Kilo Code/AI coding agent, developers and testers

---

## 0. Authority and how to use this document

This is the **single authoritative requirements baseline** for the first release. It combines the decisions agreed across customer, staff and manager planning with the repository audit.

- This document governs product behaviour and acceptance.
- `REPOSITORY_REQUIREMENTS_AUDIT.md` records what the inspected code currently does, what is missing and where it conflicts.
- Earlier `CUSTOMER_DASHBOARD_REQUIREMENTS.md`, `STAFF_DASHBOARD_REQUIREMENTS.md`, `MANAGER_DASHBOARD_REDESIGN.md` and `CROSS_DASHBOARD_INTEGRATION.md` are supporting history/reference documents. If any wording conflicts, follow this baseline and update the supporting documents together.
- A feature listed here is a requirement, not a claim that it already exists.
- No implementation, migration, merge or deployment is authorised by this document alone.
- The coding agent must inspect the actual checked-out repository and confirm file paths/current behaviour before acting.

### Requirement labels

- **AGREED:** Explicitly selected or accepted by the product owner.
- **DEFAULT:** A reasonable implementation default already accepted in discussion or recommended to avoid unnecessary decisions.
- **PROPOSED — SIGN-OFF REQUIRED:** A material business rule that still needs explicit approval.
- **TECHNICAL:** Engineering requirement; the agent should implement without asking routine questions.
- **NOT FIRST RELEASE:** Deliberately excluded from the first release.

---

# Part A — Product purpose and scope

## 1. Product purpose

Build one reliable cleaning booking and operations management platform for a cleaning company operating in Kathmandu/Nepal context as the target business concept, with customer, cleaner/staff and manager experiences.

The business manages its own customers, cleaners, services, appointments, schedules, payments, communication and service quality. Customers book cleaning services; managers operate the business; cleaners perform assigned work.

The platform must be a coherent operational system, not three disconnected dashboards. All roles read from one backend and one authoritative data model.

## 2. First-release roles

**AGREED:** Three roles only:

1. **Customer** — create/manage own bookings, pay through Stripe, communicate about own booking, see service progress and receipts, review completed services.
2. **Staff/Cleaner** — view own assigned jobs and shifts, accept/decline assignments, update job progress, record work duration, upload completion evidence and use the booking conversation.
3. **Manager** — full operational control of bookings, dispatch, staff, schedules, payments/refunds, customer support, quality, reports, business settings, notifications and audit.

No separate Owner role in the first release. Do not create an extra role without explicit approval.

## 3. Product principles

- One source of truth: the backend/database.
- Server-side authorisation for every sensitive action and record.
- Mobile-first staff experience; responsive customer and manager dashboards.
- Manager has operational control; cleaners cannot change confirmed schedules or allocate jobs.
- Stripe is the only first-release payment provider.
- Financial state is separate from booking and cleaning progress.
- Preserve working code/features; improve incrementally rather than replacing the entire application.
- Keep UI clean, professional, accessible and easy to use.
- Do not fabricate metrics, status, payment confirmation or test results.

---

# Part B — Canonical shared business model

## 4. Independent lifecycle dimensions

These must be separate logical state dimensions. They may use existing tables plus additive tables/columns; the coding agent must inspect schema and propose migrations rather than blindly create duplicate models.

### 4.1 Temporary slot reservation

`HELD → CONSUMED` or `HELD → EXPIRED/RELEASED`

- A slot is held for 10 minutes during checkout.
- The hold is persisted server-side and blocks another customer.
- Countdown is visible to the customer.
- Drafts do not reserve slots.
- Expiry releases the slot automatically.
- Late successful payment must never silently double-book a slot.

### 4.2 Booking lifecycle

Canonical logical states:

- `PAYMENT_PENDING` — checkout initiated/awaiting verified payment.
- `PENDING_REVIEW` — Stripe payment verified; awaiting manager decision.
- `CONFIRMED` — manager approved; appointment is accepted by the business.
- `REJECTED` — manager rejected or 24-hour review expired.
- `CANCELLED` — cancelled under the applicable policy.
- `COMPLETED` — service completed (may be derived from job progress, but preserve explicit booking reporting if needed).

Do not keep duplicate/ambiguous approval states such as PENDING/APPROVED/SCHEDULED without a documented compatibility mapping.

### 4.3 Payment lifecycle

Canonical logical states:

- `REQUIRES_PAYMENT`
- `PROCESSING`
- `PAID`
- `FAILED`
- `REFUND_PENDING`
- `REFUNDED`
- `PARTIALLY_REFUNDED`
- `REFUND_FAILED`

Payment state is driven by trusted Stripe events/provider retrieval and authorised refund workflows only. Never change it because a cleaner completed a job or a manager clicked a manual “paid” button.

### 4.4 Assignment lifecycle

- `UNASSIGNED`
- `AWAITING_RESPONSE`
- `ACCEPTED`
- `DECLINED`
- `EXPIRED`
- `REASSIGNED`
- `WITHDRAWN`

Keep an assignment record/history. Do not only overwrite `bookings.staff_id`.

### 4.5 Job progress lifecycle

- `NOT_STARTED`
- `ON_THE_WAY`
- `ARRIVED`
- `CLEANING_STARTED`
- `CLEANING_COMPLETED`

Assignment acceptance is recorded separately. Customer-facing labels may be simpler but must truthfully reflect backend events.

## 5. Core invariants

1. Stripe payment success does not equal manager approval.
2. Manager approval does not equal cleaner acceptance.
3. Cleaner acceptance does not equal job start.
4. Cleaner job completion does not equal payment success.
5. Refund request does not equal completed refund.
6. Assignment decline/expiry does not cancel a confirmed customer booking.
7. Checkout hold expiry is not the manager's 24-hour review window.
8. Every role sees the same underlying booking, payment, assignment, progress and conversation records, filtered by permissions.
9. Only the backend can validate/commit lifecycle transitions.
10. All sensitive actions are audited and idempotent where retries are possible.

---

# Part C — Customer experience

## 6. Customer dashboard and navigation

**AGREED**

- Responsive customer dashboard.
- Desktop: sidebar navigation.
- Mobile: bottom navigation.
- Homepage prioritises the next upcoming booking; if none exists, make booking the primary action.
- Show relevant payment state, notifications and messages without overwhelming the customer.
- Booking list newest first, with filters: Upcoming, Completed and Cancelled.
- Booking detail page includes booking reference, service, date/time, status, payment summary, cleaner information when assigned, progress timeline, customer instructions, receipts, messages and allowed actions.
- Real-time updates with refresh/polling fallback.
- Notification centre with unread count, history and mark-as-read.

## 7. Customer account and authentication

**AGREED**

- Registered customers can register/login and manage their own profile.
- Public registration must always create a customer role; clients cannot select manager/staff roles.
- Email verification is required for registered account email.
- Password reset uses a one-time, expiring link/token.
- Account security includes password/session controls, active device/session list where supported, recent login information and remote logout.
- Account deletion is a **request**, not immediate hard deletion. Manager reviews it; legally/business-required transaction and audit records are retained according to a documented retention policy; customer is notified.
- Google sign-in may be offered for customer accounts only if secure token verification is configured. It must not allow manager/staff account takeover.
- No MFA requirement selected for first release.

## 8. Guest booking

**AGREED**

- Allow booking as guest and as registered customer.
- Guest provides name, email and phone.
- Verify guest email before enabling access to booking details.
- Guest receives a secure, expiring booking-tracking link and booking reference.
- Guest may convert the booking into a registered account.
- Guest access must be scoped to their booking and protected against IDOR/enumeration.

## 9. Booking wizard and pricing

**AGREED**

- Step-by-step booking flow.
- Select service, date, available time slot, property type/size, bedrooms/bathrooms, pets, cleaning preferences, address, access/key handling and instructions.
- Save multiple customer addresses and select one during booking.
- Optional property photos/instructions can be supplied to manager and the eventually assigned cleaner.
- Show server-calculated price estimate before payment.
- Price is hourly-based for the target business model; quote logic must be server authoritative.
- Supplies/products checkbox adds a clearly displayed extra charge where configured.
- Customer can see itemised price, duration estimate and total in GBP or configured business currency as appropriate. The current repository is GBP-oriented; the product owner must confirm the production currency/business locale before live launch if the Kathmandu target remains unchanged. Do not hard-code currency assumptions beyond current environment without review.
- Booking horizon: maximum 30 days ahead.
- Availability shown must be based on actual business hours, staff capacity and existing holds/bookings.

## 10. Checkout and Stripe payment

**AGREED — STRIPE ONLY**

- Stripe is the only first-release payment provider.
- Customer pays during the booking flow.
- Stripe Checkout is preferred to avoid handling card data directly.
- Cards and Stripe-supported wallet methods such as Apple Pay/Google Pay may appear only when enabled and eligible for the configured Stripe account, currency, domain and device.
- No cash, bank transfer, manual/off-platform collection or second payment provider.
- The customer sees a 10-minute reservation countdown while the slot is held.
- Incomplete booking draft is saved automatically for 30 days; it does not retain a slot after the 10-minute hold expires.
- Failed payment: hold slot temporarily; customer can retry or use another Stripe-supported method while hold remains valid. Booking remains unconfirmed until Stripe verification.
- If payment is not completed before hold expiry, release slot and allow customer to select another.
- Payment success is verified server-side through Stripe webhook/provider evidence. A browser redirect alone is never proof.
- After verified payment, show “Payment received — awaiting manager approval”.
- Do not display “Booking confirmed” until manager approval.
- Receipts: email and downloadable PDF, including booking reference, service, amount, currency, payment status and transaction reference.
- Saved payment methods are optional only if supported securely by Stripe; never store card numbers/CVC in this application's database. Customer can remove saved methods using provider-supported mechanisms.

## 11. Manager review and booking confirmation

**AGREED**

- A booking enters manager review only after successful verified Stripe payment.
- The manager has 24 hours from verified payment to approve or reject.
- The deadline runs continuously, including nights, weekends and holidays.
- Manager approval moves booking to `CONFIRMED`.
- Cleaner assignment is permitted only after approval.
- Customer is notified when approved or rejected.
- Unpaid checkout attempts do not start the 24-hour manager-review clock.

**PROPOSED — SIGN-OFF REQUIRED:** If manager rejects or fails to review within 24 hours, automatically reject and initiate a full Stripe refund. This is the recommended customer-protection rule; the owner must approve it before implementation.

## 12. Customer cancellation and rescheduling

**AGREED**

- Cancellation at least 24 hours before appointment: full refund through Stripe to original payment method.
- Cancellation under 24 hours: no automatic refund. Customer can submit a request for manager exception; manager decides.
- Do not automatically apply the existing repository's 50% late-cancellation fee.
- Customer cannot ordinarily cancel a job already in progress or completed.
- Customer can self-reschedule at least 24 hours before appointment, subject to availability.
- Under 24 hours, customer submits a reschedule request for manager approval.
- Availability must be checked atomically to prevent double booking.
- Company-initiated cancellation/change: notify customer with reason and offer alternative appointment or full Stripe refund.
- Refund state is pending until Stripe confirms it. Never show refunded prematurely.

## 13. Customer booking progress

Customer sees a timeline based on backend events:

1. Payment received — awaiting manager approval.
2. Booking confirmed.
3. Cleaner assigned.
4. Cleaner accepted assignment (optional detail).
5. Cleaner on the way.
6. Cleaner arrived (optional detail).
7. Cleaning started.
8. Cleaning completed.

- Do not show cleaner before assignment.
- Customer sees cleaner's name, photo and role only after assignment.
- Do not reveal cleaner's personal phone number. Use booking chat or company contact details.
- Show real-time progress or refresh fallback.
- Customer can view permitted completion evidence only after manager explicitly releases it; default evidence access is private.

## 14. Customer communication and support

**AGREED**

- One booking-specific conversation per booking.
- Customer, currently assigned cleaner and authorised manager/support staff can participate according to access policy.
- Photo-only chat attachments; server validates type/size and stores privately.
- Messages show sender, timestamp and read state.
- New messages trigger in-app notifications and browser notifications when permitted.
- Avoid duplicate notification if the recipient is already viewing the conversation.
- Customer can contact business by phone and use FAQ/support.
- No separate duplicate messaging system.
- Customer can submit support requests; manager handles case workflow.

## 15. Customer notifications and preferences

**AGREED**

- Central notification centre and durable in-app history.
- Essential transactional notifications cannot be disabled where required for service delivery.
- Customer receives booking/payment/approval/rejection/cancellation/refund/progress/message notifications.
- Appointment reminder 24 hours before service by in-app + email.
- Category-based preferences for reminders, messages, reviews and marketing.
- Marketing off by default.
- Browser notification permission is optional; in-app/email fallback remains.
- Do not send duplicate notifications on webhook retries or background-worker retries.

## 16. Recurring bookings and reviews

**AGREED**

- Recurring weekly, fortnightly or monthly cleaning.
- Customer can pause, resume, change, skip or cancel recurring schedule.
- Each occurrence is an individual booking with its own availability and payment.
- No automatic future charges in first release; each appointment requires its own Stripe payment.
- Review becomes available after completed service.
- One review per booking; manager can review quality metrics.

---

# Part D — Staff/Cleaner experience

## 17. Staff dashboard

**AGREED**

- Mobile-first layout, quick loading and large touch targets.
- Today's jobs first, then next appointment and upcoming shifts.
- Job cards show service, time, customer/property details required to perform the job, status and quick actions.
- Staff can see their own job history (completed/cancelled), date, service and booking reference.
- No broad customer financial reports or commission/earnings dashboard.
- Staff sees own profile, work contact details, role, upcoming shifts and account status.
- Staff must not see other cleaners' personal data or jobs.

## 18. Assignment workflow

**AGREED**

- Manager assigns a cleaner to an approved/confirmed booking.
- Cleaner receives in-app and browser notification where permission exists.
- Cleaner must accept or decline.
- Default response deadline: two hours from assignment; manager-configurable.
- Decline immediately notifies manager; optional reason.
- No response before deadline expires assignment and notifies manager; manager can reassign.
- Decline/expiry does not cancel customer booking.
- Manager controls reassignment.
- Assignment history retained.
- After reassignment, previous cleaner loses current access to customer/property data; new cleaner gets access.
- Staff cannot self-assign, choose replacement or remove themselves from confirmed job.

## 19. Staff job progression

**AGREED**

Required sequence:

1. Assigned (awaiting response)
2. Accepted
3. On the way
4. Arrived
5. Cleaning started
6. Cleaning completed

- Timestamp every transition server-side.
- Do not skip required stages.
- Customer sees safe progress updates.
- Manager can correct exceptional mistakes only with reason and audit trail.
- Completed job cannot silently reopen.
- No continuous GPS tracking. Only On the way and Arrived timestamps; no background location collection.

## 20. Cleaning timer and completion evidence

**AGREED**

- Timer starts automatically when cleaner selects Cleaning started.
- Timer stops automatically when cleaner selects Cleaning completed.
- Persist start/end timestamps and elapsed duration server-side.
- Prevent duplicate active timers and duplicate completion requests.
- Full elapsed duration; no break tracking in first release.
- Connectivity-safe: server is authoritative and clients reconcile after reconnect.
- Cleaner adds completion notes and before/after photos.
- Store photos privately with validation and role-based access.
- Manager can review photos and notes.
- Job completion is immediate; no manager approval gate required.
- On completion, customer receives in-app + email update.
- Customer photo visibility defaults to private until manager explicitly releases evidence.

## 21. Staff availability and schedule

**AGREED**

- Manager controls staff shifts, availability, schedule changes and time-off approval.
- Staff can view own confirmed schedule read-only.
- Staff cannot edit confirmed shifts or weekly availability directly.
- Manager changes notify affected staff.
- Assignment validation blocks overlaps, outside working hours, time off, cancelled/unavailable booking and other hard conflicts.
- Manager sees conflict explanation.
- If staff becomes unavailable after accepting, they contact manager through booking chat or phone. Manager decides reassignment; history is retained and customer notified.

## 22. Staff notifications and communication

**AGREED**

Essential staff notifications:
- New assignment.
- Assignment changed/reassigned/withdrawn.
- Appointment time or booking changed/cancelled.
- Upcoming appointment.
- Customer booking message.
- Important manager updates.
- Late arrival alert to manager.

- In-app notification is durable baseline.
- Browser push/notification requires explicit permission; fallback must work.
- Do not send email for every chat message.
- Existing booking-specific chat only; no separate manager messaging tool.
- Staff can contact manager via booking chat or configured business phone.

## 23. Staff permissions and access

**AGREED**

- Manager creates staff accounts and assigns role.
- Secure account activation.
- Manager can suspend/reactivate staff.
- Suspended staff cannot access dashboard; historical records retained.
- Staff may update password and manage their own session security.
- Staff only accesses their active assigned jobs.
- Customer address/access details are revealed only when operationally necessary, following current access-note masking policy.
- Staff cannot see card details, Stripe identifiers, refunds, manager finance records or other cleaners' information.
- Staff cannot alter payment state, collect cash, record payment or issue refunds.
- Job completion never marks payment paid.

---

# Part E — Manager experience

## 24. Manager dashboard and navigation

**AGREED**

Professional light interface, visible fixed/collapsible left sidebar on desktop and usable responsive navigation on mobile. Sidebar must be accessible, keyboard operable and never rely on hover-only interaction.

Manager sections:

1. Overview.
2. Bookings.
3. Dispatch & Assignments.
4. Staff Schedule.
5. Cleaners & Staff.
6. Vetting & Compliance.
7. Payments & Finance.
8. Customer Support.
9. Reviews & Quality.
10. Reports & Analytics.
11. Notifications.
12. Business Settings.
13. Activity & Audit Log.

Every visible menu item must work. Do not display disabled placeholder navigation as completed functionality.

## 25. Manager operational authority

**AGREED**

Manager has full operational control over:
- All bookings and booking lifecycle decisions.
- Approve/reject paid pending-review bookings.
- Assign, auto-match, reassign and withdraw cleaners.
- Create/edit/move/cancel shifts and manage staff schedules.
- Review time-off/unavailability.
- Manage staff accounts, roles, vetting, activation and suspension.
- View Stripe transactions, investigate failures and initiate refunds through Stripe.
- Handle customer support and service quality.
- Manage reviews and complaints.
- View accurate operational/financial reports.
- Manage business settings, services, prices, opening hours, service areas, additional charges and notification settings.
- Review central notifications and audit log.

No manager can manually mark an unverified Stripe payment successful.

## 26. Booking operations

Manager can:
- Search/filter bookings by reference, customer, status, date, service, postcode, assigned cleaner and payment state.
- View booking details and event history.
- Approve/reject bookings in `PENDING_REVIEW` with reason.
- Assign/reassign/withdraw cleaner only when booking is eligible.
- Change date/time and handle reschedule requests.
- Cancel booking under policy and initiate required Stripe refund.
- Review customer instructions, property photos and support context.
- See who changed what and when.

All actions are server-authorised, confirmed for destructive operations and audited.

## 27. Dispatch and cleaner matching

**AGREED**

Manual assignment and automatic nearest-suitable-cleaner matching.

Eligibility checks:
- Staff account active.
- Vetting approved and required compliance checks verified.
- Service suitability/skills.
- Service radius and geographic coverage.
- Working hours and confirmed shifts.
- Time off/unavailability.
- Existing booking overlap.
- Configured travel buffer.
- Booking itself is manager-approved and confirmed.

- Hard conflicts block assignment.
- Explain why a cleaner is unavailable.
- Keep existing postcode/geospatial/TfL travel calculation where useful, but validate accuracy and do not treat estimate as guaranteed travel time.
- Assignment response deadline default two hours, manager-configurable.

## 28. Staff and compliance management

**AGREED**

- Create/edit staff profile and account.
- Assign role and permissions.
- Activate/suspend/reactivate.
- View contact/profile/work information and job history.
- Maintain service areas, skills and availability.
- Manage shifts/time-off.
- Vetting includes DBS and right-to-work status, evidence reference, reviewer, verification timestamp and expiry/review date where relevant.
- New staff default to unverified/PENDING; never default new staff to approved.
- Secure document storage; never expose compliance documents to customers or other staff.
- Keep historical records for audit.

## 29. Manager finance — Stripe only

**AGREED**

- Stripe is sole provider.
- View payments linked to booking and customer, amount, currency, provider reference, event state and timestamps.
- Monitor paid, processing, failed, refund pending, refunded and refund failed.
- Investigate mismatches and payment exceptions.
- Initiate refunds through Stripe via secure backend action.
- Do not expose card details.
- Do not create manual payment records or allow cash/bank transfer methods.
- Staff cannot record or verify payment.
- Refund state updates only from Stripe-confirmed provider evidence.
- Use Decimal/fixed-point money values.
- Record actor, amount, reason, Stripe payment/refund reference, timestamps and outcome.
- Payment lifecycle remains separate from booking/job lifecycle.

## 30. Manager customer support and quality

**AGREED**

- View customer profiles and relevant booking history.
- Handle customer support cases, complaints and follow-ups.
- Review booking conversation with authorised/audited access.
- Track support case status and assigned manager.
- Review ratings, comments, punctuality and thoroughness.
- Resolve service quality issues.
- Manager decisions and customer communications are recorded.

## 31. Manager reports and analytics

**AGREED**

Reports must be grounded in real records:
- Booking volume and status breakdown.
- Booking cancellation/rejection rates.
- Stripe payments collected by actual payment timestamp.
- Refund totals by actual refund timestamp.
- Net collected amount.
- Outstanding/failed payment states.
- Cleaner completed jobs and recorded hours.
- Customer growth.
- Popular services.
- Staff utilisation based on clear, documented formula.
- Expenses only if expense records are complete.

Do not label booking value as revenue collected. Do not calculate profit until a complete cost model exists. Do not display overdue balance without an agreed due-date/overdue definition. CSV/XLSX export can be included once metrics are accurate and access-controlled.

## 32. Manager business settings

**AGREED**

- Business name, logo, contact details.
- Services, hourly pricing, add-ons and supplies charge.
- Opening hours, holidays and service coverage areas.
- Booking/cancellation/reschedule policy text.
- Assignment response deadline and late arrival threshold.
- Notification preferences/templates.
- Currency/timezone configuration where relevant.

Do not expose secret keys, provider credentials or raw sensitive environment settings through the manager UI.

## 33. Late cleaner and exceptions

**AGREED**

- If cleaner has not marked On the way/Arrived by expected appointment time, system flags potential delay and alerts manager.
- Grace/late threshold must be configurable by manager.
- Do not invent automatic penalties or automatic cancellation.
- Manager contacts customer, handles reassurance/reassignment and records decision.
- If cleaner becomes unavailable after accepting, manager controls reassignment and customer notification.

---

# Part F — Shared platform requirements

## 34. Single source of truth and architecture

**TECHNICAL**

- One backend application and one database.
- Customer, staff and manager are role-specific views over shared domain entities.
- Use existing modular FastAPI architecture where appropriate; inspect current branch before deciding implementation base.
- Keep route/controller, schema/DTO, service/business logic and data access responsibilities clear.
- Do not duplicate lifecycle logic in frontend or role-specific services.
- Centralise state transition rules and permission checks.
- Preserve current working code; refactor incrementally.
- API contracts must be explicit, validated and consistent.
- Avoid returning `SELECT *` payloads to role dashboards; use role-specific response DTOs.

## 35. Database and data integrity

**TECHNICAL**

- MySQL 8 compatible.
- Use foreign keys, unique constraints, indexes and transactions for multi-record workflows.
- Use explicit versioned migrations; no destructive reset/drop of existing data.
- Back up before schema/data migration.
- Existing data must be mapped/backfilled safely.
- Store timestamps consistently (UTC preferred) and display Europe/London if operating UK; confirm final business timezone if Kathmandu is production target.
- Use server timestamps for lifecycle events.
- GBP/currency values use Decimal/fixed-point, not binary float.
- Add durable records for slot holds, Stripe events, refunds, assignment history, job work sessions, chat, notifications/outbox and audit where needed.
- Enforce one active assignment per booking and one active timer per assignment.
- Ensure concurrency safety for booking slot holds and staff dispatch.

## 36. Notifications

**TECHNICAL**

- One central event/outbox system.
- Write event/outbox records transactionally with state changes.
- Stable event IDs and idempotency/deduplication keys.
- Recipient, channel, status, retry/error metadata, timestamps, read state and deep link.
- In-app notification is durable baseline.
- Customer transactional email for key booking/payment/refund/reminder events.
- Staff in-app/browser notification.
- Manager central operational notification centre.
- Browser push permission denial must not break the system.
- Notification delivery retries cannot duplicate customer messages or state transitions.
- Fix existing schema mismatch between `notification_outbox` and notification utility before relying on it.

## 37. Chat and attachments

**TECHNICAL**

- One conversation per booking.
- Enforce participant membership server-side on every read/write.
- Update membership when assignment changes.
- Remove active access for previous cleaner after reassignment.
- Photo-only attachments in first release; validate MIME, actual file type, size and image decoding.
- Private storage; short-lived authorised access links; no public bucket exposure.
- Keep message and attachment metadata/audit as required by retention policy.

## 38. Real-time and offline recovery

**TECHNICAL**

- WebSocket, SSE or another maintainable mechanism for booking progress/chat/notifications.
- If real-time channel disconnects, fetch authoritative state on reconnect.
- Polling fallback is acceptable for initial release if properly rate-limited.
- Do not trust client-side clock, timer or optimistic status as authoritative.
- Do not lose staff progress events during temporary connectivity loss; use safe retry/idempotency.

## 39. Security, privacy and compliance

**TECHNICAL / RELEASE BLOCKER**

- Password hashing with secure configuration; no hard-coded secrets.
- Fail fast on missing/weak production secrets.
- Role-based and object-level access control.
- Prevent IDOR/BOLA for booking, payment, chat, evidence and notification resources.
- Server-side validation for every form and state transition.
- Parameterised SQL only.
- XSS protection and safe DOM rendering.
- CSRF protection if cookie-based sessions are used.
- HTTPS in production; secure session/token handling.
- Security headers including CSP, HSTS, nosniff, referrer and permissions policy.
- Rate limiting for login, registration, password reset, booking and sensitive endpoints.
- Strict CORS allowlist.
- Secure cookies if using cookies: HttpOnly, Secure, SameSite appropriate to architecture.
- Stripe webhook signature verification in production; no mock bypass.
- Secrets in environment/secret manager; never in source, logs or UI.
- Encrypt sensitive property access instructions at rest and mask them from staff until operationally required.
- No continuous GPS tracking.
- Audit sensitive manager/staff actions and manager corrections.
- Data minimisation, retention and deletion request workflow.
- New staff must not be auto-approved by default.

## 40. Authentication and session requirements

**AGREED / TECHNICAL**

- Customer registration, login, logout, email verification, password reset.
- Manager-created staff accounts and secure activation.
- Role cannot be self-selected on public registration.
- Suspended accounts cannot authenticate/use APIs.
- Expiring access session and secure logout/revocation strategy.
- Customer account security view: sessions/devices and remote logout where supported.
- No MFA requirement selected for first release.
- Do not truncate passwords silently to a smaller effective value; define and validate maximum supported password length.

## 41. Audit and operational observability

**TECHNICAL**

- Append-only audit records for manager approvals/rejections, assignment/reassignment, staff vetting, schedule changes, payment/refund actions, cancellations, support decisions, settings and corrections.
- Record actor, role, action, entity, timestamp, before/after values, reason and request/correlation ID.
- Never log secrets, card data, password, full access codes or unnecessary PII.
- Monitor Stripe webhook failures, notification failures, scheduler/worker errors and background job retries.
- Health/readiness checks and structured logs.
- Alerts for stuck pending payments/refunds, expired assignment offers, review deadlines and notification delivery failures.

---

# Part G — Acceptance criteria and test plan

## 42. Required end-to-end scenarios

All must be covered by automated tests before release:

1. Customer draft saved; draft expiry after 30 days; draft does not reserve slot.
2. Slot hold created atomically and visible countdown starts at 10 minutes.
3. Second customer cannot hold the same capacity while first hold is active.
4. Payment failure allows retry within hold period and does not confirm booking.
5. Verified Stripe payment consumes hold and moves booking to PAID + PENDING_REVIEW.
6. Customer sees payment received/awaiting approval, not confirmed.
7. Browser redirect without verified Stripe event cannot mark payment paid.
8. Duplicate/out-of-order Stripe webhook does not duplicate payment, booking, audit or notification.
9. Stripe provider outage cannot fall back to mock checkout in production.
10. Late successful Stripe payment after hold expiry cannot double-book; safe refund/reconciliation occurs.
11. Manager approves within 24 hours; booking becomes CONFIRMED and customer is notified.
12. Manager rejects paid booking; approved refund policy is applied; refund remains pending until Stripe confirmation.
13. Review deadline expiry works after 24 elapsed hours including nights/weekends and is idempotent.
14. Cleaner cannot see or accept booking before manager assignment.
15. Manager assignment checks vetting, active status, skill/service, area, schedule, time off, overlap and travel buffer.
16. Cleaner accepts assignment; manager/customer see accepted state.
17. Cleaner declines or two-hour deadline expires; manager notified, booking remains confirmed, cleaner access removed and dispatch permits reassignment.
18. Reassignment retains history and removes previous cleaner's current customer/property/chat access.
19. Cleaner cannot edit confirmed schedule or own assignment.
20. Cleaner cannot update another cleaner's job.
21. Job stages cannot be skipped or updated out of order.
22. Timer starts/stops once, uses server timestamps and records duration.
23. Duplicate requests and reconnect do not duplicate timer sessions or progress events.
24. Completion notes/photos are stored securely; customer cannot view until manager release.
25. Cleaner completion never changes payment status.
26. Customer, current cleaner and manager can use the one booking conversation according to role permissions.
27. Previous cleaner cannot read new messages or private booking details after reassignment.
28. Unauthorised users cannot access chat, attachments, notifications or booking details.
29. Notification retries do not duplicate alerts; in-app fallback remains.
30. Customer sees cleaner name/photo/role but not cleaner personal phone.
31. Customer cancellation >=24h initiates full Stripe refund.
32. Customer cancellation under 24h does not automatically refund; manager exception workflow works.
33. Customer reschedule >=24h works only when slot available; under 24h requires manager approval.
34. Company cancellation/change sends reason and alternative/refund process.
35. Manager dashboard metrics reconcile with Stripe payment/refund timestamps and ledger.
36. No false overdue/profit/revenue metrics.
37. Staff cannot see Stripe IDs, payment records, refund details or other cleaner records.
38. Customer cannot read another customer's booking or payment.
39. Public registration cannot create manager/staff.
40. Suspended staff cannot authenticate or access existing API tokens.
41. Manager corrections require reason and create audit event.
42. Real-time reconnect fetches current backend state and does not show stale/fabricated progress.
43. Database migration can be applied safely to a copy of existing data and verified without destructive reset.
44. Existing working features (pricing, authentication, postcode, dispatch conflict checks, encrypted access notes, customer booking list, manager sidebar) do not regress.

## 43. Test strategy

- Unit tests for state transitions, pricing, refund policy, access masking and permission functions.
- API integration tests using isolated disposable MySQL database and fixtures.
- Stripe test-mode integration/webhook tests; no live charge during tests.
- Concurrency tests for slot holds and cleaner assignment.
- Role/object-level security tests.
- Frontend functional/accessibility/responsive tests.
- End-to-end scenarios across customer, manager and cleaner.
- Regression suite for all preserved features.
- Do not run destructive tests against production or shared database.
- Existing `tests/test_system.py` is a live-server script with destructive setup and stale policy assumptions; refactor it into safe isolated tests before treating it as the release gate.
- Report exact commands, environment and actual outcomes. Never claim tests passed if not executed.

---

# Part H — Scope and unresolved sign-off

## 44. Not first release

Unless the product owner later approves:
- Cash payments or bank transfers.
- Any payment provider other than Stripe.
- Continuous GPS/location tracking.
- Staff commission/earnings dashboard or hard-coded 70% cleaner share.
- Customer-to-cleaner personal phone exchange.
- Cleaner self-management of confirmed schedule.
- Automatic late-cancellation fee/refund under 24 hours.
- Automatic future recurring charges.
- Owner role or additional role types.
- MFA requirement.
- Separate general-purpose staff/manager chat outside booking conversation.
- Automatic penalties or cancellation for late cleaners.
- Customer-visible completion photos without manager release.

## 45. Material policy sign-offs still required

Do not ask the owner routine technical questions. The coding agent should make sound engineering decisions. Only these business-policy items should block final policy sign-off:

1. **Manager rejection/24-hour expiry refund — PROPOSED:** Full Stripe refund automatically. Recommended because the company cannot fulfil the paid appointment. Owner must explicitly approve.
2. **Business deployment currency/timezone:** Current code is GBP/Europe-London-oriented while the target business concept is Kathmandu. Confirm production currency (likely NPR if operating in Nepal) and business timezone before live pricing/payment deployment. Keep currency and timezone configurable, never assume a Stripe account can process an unsupported currency.
3. **Completion photo customer visibility:** Default private until manager release is set as the safe default. Owner can later decide to show automatically.
4. **Staff arrival grace threshold:** Manager-configurable. Exact default to be set by manager in business settings; no penalty automation.

Everything else in this baseline is sufficiently decided for technical planning. Do not turn minor implementation choices into questions for the owner.

---

# Part I — Implementation governance

## 46. Source control and change management

**AGREED**

- Never develop directly on `main`.
- Before each task, create a new, clearly named feature branch from the agreed integration base.
- Confirm working tree and branch before editing.
- Never overwrite uncommitted user changes.
- Do not use destructive reset/clean commands.
- Make small, reviewable changes.
- Run relevant tests after each meaningful change.
- Run full regression tests before merge.
- Merge only after tests pass and user explicitly approves.
- Do not push/merge automatically without permission.
- Keep requirements and implementation docs updated when a policy changes.
- Report changed files, migration impact, tests run and known risks.

## 47. Recommended implementation sequence

The AI coding agent must begin with a fresh repository audit and baseline tests, not immediately code.

1. **Phase 0 — Repository and environment verification:** identify checked-out branch, compare with main, verify dependencies, inspect schema, backup and isolate test DB, record baseline tests.
2. **Phase 1 — Domain model and API contracts:** canonical lifecycle dimensions, DTOs, permission matrix, migration plan, audit/outbox.
3. **Phase 2 — Booking and Stripe integrity:** 10-minute hold, Stripe-only fail-closed checkout, webhook event deduplication, payment/refund ledger.
4. **Phase 3 — Manager review:** approval/rejection, 24-hour worker, notifications and audit.
5. **Phase 4 — Dispatch and assignment:** conflict checks, assignment history, accept/decline/timeout/reassignment and access revocation.
6. **Phase 5 — Staff execution:** progress, timer, notes, evidence uploads and manager correction.
7. **Phase 6 — Shared communication:** booking chat, membership, attachments, notifications and browser push.
8. **Phase 7 — Customer dashboard completion:** booking details, self-service, receipts, account, guest flow and notifications.
9. **Phase 8 — Manager dashboard completion:** visible sidebar, all functional sections, schedules, vetting, finance, support, reports, settings and audit.
10. **Phase 9 — Security, reporting and operational hardening:** session controls, CSP, secrets, accurate ledger metrics, observability.
11. **Phase 10 — Full acceptance and release review:** automated cross-role tests, migration rehearsal, accessibility, regression and explicit owner approval.

Do not implement every phase in one giant change. Create separate feature branches as appropriate and preserve a working system throughout.

## 48. Definition of done

A phase is done only when:
- Its behaviour matches this baseline.
- Backend permission and validation checks are in place.
- Database migration is safe and documented.
- Frontend displays truthful backend state.
- Tests cover happy paths, failures, retries and unauthorised access.
- Existing features remain working.
- No unresolved critical security/financial/data-integrity defect remains in that phase.
- Test results are reported honestly.
- User approves merge.

The product is ready for first-release sign-off only when all P0 and P1 audit findings are resolved, all mandatory acceptance tests pass, the business policy sign-offs in section 45 are confirmed, and the customer/staff/manager journeys operate against the same authoritative records.

---

**Final instruction:** Build the product described here, not merely the appearance of three dashboards. If the current code conflicts with this baseline, report the exact conflict and implement a safe, tested migration/refactor. Never silently weaken a requirement, invent a business policy or mark an unverified payment/job/booking as successful.
