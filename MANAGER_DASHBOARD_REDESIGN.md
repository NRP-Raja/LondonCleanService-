> **Authority note:** `REQUIREMENTS_BASELINE.md` is the single authoritative first-release requirements document. This file is supporting detail. If anything here conflicts with the baseline, follow the baseline and update this document in the same change.

# LondonCleanService --- Manager Dashboard Redesign Specification

**Document type:** Product, UX and technical implementation
specification\
**Repository reviewed:** `NRP-Raja/LondonCleanService-`\
**Implementation approach:** Preserve and improve the existing
application\
**Status:** Requirements agreed; implementation details must be verified
against the current local code before changes

------------------------------------------------------------------------

## 1. Purpose

Redesign the manager area into a modern, professional operations
workspace. The manager should be able to run the cleaning business from
one coherent dashboard instead of navigating a long page with scattered
controls.

This document is a specification for the coding agent. It is **not
permission to replace the application wholesale**. Inspect the current
local repository first, confirm the live schema and route behaviour,
then implement in small, testable stages.

## 2. Agreed product decisions

  -----------------------------------------------------------------------
  Area                                Agreed requirement
  ----------------------------------- -----------------------------------
  Manager scope                       Full operations manager

  Scheduling                          Full scheduling control

  Staff                               Full staff and cleaner management

  Finance                             Full finance management

  Bookings                            Full booking lifecycle control

  Customer support                    Full customer support and service
                                      quality

  Reports                             Advanced reports and analytics

  Business settings                   Full business settings

  Access model                        Role-based access; current roles
                                      are Manager, Staff/Cleaner and
                                      Customer. Do not add Owner now.

  Security                            Full audit and security controls

  Notifications                       Central notification centre

  Design                              Modern professional, light
                                      interface, fixed/collapsible left
                                      sidebar

  Existing application                Preserve and improve; reuse working
                                      APIs and database structures where
                                      suitable
  -----------------------------------------------------------------------

### Current roles

-   **Manager:** Full management access to operational areas and
    business settings.
-   **Staff/Cleaner:** Access only to their own profile, assigned work,
    schedule and relevant customer communication.
-   **Customer:** Access only to their own account, bookings, payments,
    messages and reviews.

Do not introduce an Owner role in this release. Keep the permission
design extensible so an Owner role can be added later without rebuilding
authorization.

## 3. Repository and current implementation baseline

The public repository version reviewed is built with:

-   **Backend:** FastAPI (Python)
-   **Database:** MySQL
-   **Frontend:** HTML, CSS and vanilla JavaScript

Do not assume this is a Django application. Do not introduce a new
frontend framework or ORM simply to implement the redesign.

The reviewed manager page currently contains or references:

-   Revenue and booking KPI cards.
-   Booking list and status filtering.
-   Unassigned-booking visibility.
-   Manual cleaner assignment.
-   Automatic nearest-cleaner matching.
-   Cleaner schedule/timeline display.
-   DBS and right-to-work vetting information.

The reviewed frontend calls manager endpoints including:

-   `GET /api/manager/dashboard-stats`
-   `GET /api/manager/bookings`
-   `GET /api/manager/staff`
-   `POST /api/manager/bookings/{booking_id}/auto-match`
-   `PATCH /api/manager/staff/{staff_id}/vetting`

The frontend manager logic is currently part of a larger JavaScript file
and the manager markup is part of the main HTML page. Confirm exact
paths, route contracts and current behaviour in the checked-out local
branch before editing; repository code may have changed since the
review.

### Known issues to verify and address

1.  The manager interface is currently presented as a long page rather
    than a navigable management workspace.
2.  Manager-specific JavaScript is mixed into a large shared frontend
    script. Improve separation carefully without breaking global
    functions or script loading.
3.  The booking list appears to fetch staff options separately for each
    booking (an N+1 request pattern). Prefer one appropriately filtered
    staff request or a dedicated assignment-options endpoint.
4.  The KPI labelled as monthly revenue must be checked against its
    backend calculation. The reviewed implementation appeared to use a
    broader non-cancelled-booking total rather than a clearly defined
    current-month collected-payment total.
5.  KPI placeholders should not look like real values before data loads.
    Use skeletons and explicit empty/error states.
6.  Verify whether schedule timeline travel buffers are real
    configurable values or display-only assumptions. Never imply a
    travel duration is guaranteed unless supported by data.

**Important:** The items above are observations from the reviewed public
repository version, not a guarantee about the user's current local
working tree. Re-check before implementation.

------------------------------------------------------------------------

## 4. Information architecture and sidebar

Create a fixed, visible left sidebar with icons and text labels. It
should be collapsible on desktop and become a usable drawer/navigation
panel on smaller screens. The active destination must be obvious.

Recommended navigation:

1.  **Overview**
2.  **Bookings**
3.  **Dispatch & Assignments**
4.  **Staff Schedule**
5.  **Cleaners & Staff**
6.  **Vetting & Compliance**
7.  **Payments & Finance**
8.  **Customer Support**
9.  **Reviews & Quality**
10. **Reports & Analytics**
11. **Notifications**
12. **Business Settings**
13. **Activity & Audit Log**

Use clear page headings, breadcrumbs where useful, consistent action
placement and sensible empty states. Avoid hiding the sidebar behind an
invisible hover target. Navigation controls must be keyboard accessible
and have visible focus states.

## 5. Functional requirements

### 5.1 Overview

Provide an at-a-glance operational summary:

-   Today's bookings and completed jobs.
-   Pending requests and requests approaching the 24-hour expiry.
-   Unassigned bookings.
-   Active cleaners and availability.
-   Today's and current-month collected payments.
-   Unpaid/overdue amounts.
-   Open complaints and unread notifications.
-   Recent booking, staff and payment activity.

Every KPI must have a defined calculation, time period, currency and
source. Do not label booking value as collected revenue. Show loading,
empty, stale-data and error states clearly. KPI cards should link to the
relevant filtered page.

### 5.2 Bookings

Manager capabilities:

-   View, search, sort and filter bookings.
-   Review new requests and approve or reject them.
-   Assign and reassign cleaners only after a booking has been approved and moved to `CONFIRMED`.
-   Change booking date, time and permitted service details.
-   Process customer change requests.
-   Cancel bookings and record a reason.
-   View customer, service, address, supplies/add-ons, assigned cleaner,
    payment status and booking history.
-   See who changed the booking and when.

Preserve the agreed lifecycle where compatible with the existing
application:

`PENDING_REVIEW → CONFIRMED → CANCELLED / REJECTED`

Treat job completion as a separate operational lifecycle, not as a booking-lifecycle status. Preserve legacy values through a reviewed backward-compatible mapping; do not expose duplicate or ambiguous approval states.

Do not silently invent or rename statuses. Inspect existing
enum/constants, frontend logic, database constraints and API validation
first. Define allowed transitions centrally and reject invalid
transitions on the backend.

**24-hour manager-review rule:** A booking enters `PENDING_REVIEW` only after Stripe payment has been verified. The 24-hour review clock starts at that point. A manager must approve or reject it within 24 hours, including overnight, weekends and holidays. If no decision is made, the system automatically rejects it and initiates a full Stripe refund. The customer must be notified of rejection and refund processing. Do not treat an unpaid checkout attempt as a manager-review booking. Implement this with a
reliable server-side scheduled mechanism or equivalent---not a browser
timer. Make it idempotent, timezone-aware and safe if the worker runs
more than once. Record the automatic action in the audit history.

### 5.3 Dispatch & assignments

-   Show unassigned and urgent jobs prominently.
-   Support manual assignment and reassignment.
-   Retain nearest-cleaner matching if it is already supported and
    valid.
-   Show relevant cleaner availability, skills, service area and
    existing jobs.
-   Check schedule overlap, working hours, time off and any configured
    travel buffer before assignment.
-   Explain why a cleaner is unavailable.
-   Require confirmation when overriding a warning; block hard conflicts
    such as overlapping jobs unless a deliberately designed exception
    process exists.
-   Avoid one staff-options API call per booking.

### 5.4 Staff schedule

Provide daily and weekly calendar views with filters by cleaner and
status.

Managers can:

-   Create, edit, move and delete shifts.
-   Set recurring weekly working hours.
-   Record one-off availability/unavailability.
-   Review, approve or reject time-off requests.
-   Move and reschedule bookings.
-   See assigned jobs and travel buffers.
-   Detect overlapping shifts and bookings.

Backend validation is mandatory. Prevent conflicting shifts and bookings
in server-side business logic and, where appropriate, database
constraints/transactions. Handle concurrent manager edits safely.

Staff should be able to see their own relevant schedule and submit
time-off requests if that workflow is added; they must not edit another
cleaner's schedule.

### 5.5 Cleaners & staff management

Manager capabilities:

-   Create and edit staff profiles/accounts.
-   Manage contact details and emergency contact details where
    collected.
-   Manage skills, service areas and availability.
-   Manage hourly rates where applicable.
-   Activate, deactivate, suspend and reactivate accounts.
-   View booking/work history.
-   View compliance status and documents.

Collect only necessary personal data. Restrict access to sensitive
documents and emergency contacts. Do not expose private staff details in
customer-facing APIs.

### 5.6 Vetting & compliance

-   Display DBS and right-to-work verification status.
-   Record who reviewed a document and when.
-   Support document upload/view only if secure storage and access
    controls are in place.
-   Track expiry dates where applicable and surface upcoming/overdue
    checks.
-   Distinguish "not provided", "pending review", "verified", "rejected"
    and "expired" where the data model supports these states.
-   Never treat a checkbox as proof that a document was actually
    reviewed.
-   Restrict document access to authorized managers and protect files
    from public URL exposure.

### 5.7 Payments & finance

Provide:

-   Paid, unpaid, overdue and refunded payment views.
-   Stripe payment history linked to each booking.
-   Outstanding and failed Stripe payment monitoring.
-   Refund review and execution through the Stripe integration only.
-   Reconciliation of Stripe payment events against booking records.
-   Invoice/receipt viewing and generation where supported.
-   Date-filtered finance reports and export.

**First-release payment policy: Stripe only.** All customer payments must pass through the configured Stripe integration. Do not support cash, bank transfer, manual/off-platform collection or a second payment provider. Staff must not collect or record payments and must not edit payment status. Managers may inspect Stripe transaction records, investigate exceptions and initiate refunds through Stripe using an authorised backend workflow. A manager must never manually mark an unverified payment as paid. Payment success/refund state must be based on trusted Stripe responses/webhooks and recorded separately from booking and cleaning-job status. The current manager payment schema/service must be reviewed because it presently allows methods such as CASH, CARD, BANK_TRANSFER, REFUND and OTHER; legacy options must not remain available in the first-release UI/API.

**Financial correctness:**

-   Separate booking value, amount due, amount collected, refunds and
    net collected revenue.
-   Define whether reports use booking date, service date or payment
    date.
-   Store money as decimal/fixed-point values, never binary
    floating-point.
-   Record Stripe payment/refund identifiers, amount, currency, event/status, timestamps and related booking; record the authorised manager actor for refund initiation or manual reconciliation notes.
-   Prevent duplicate payment recording with idempotency/unique
    constraints where appropriate.
-   Do not claim that a refund was processed if the system only records
    a refund request.
-   Stripe is the only approved payment provider for the first release. Do not add cash, bank transfer, manual payment marking or another gateway. Use secure Stripe integration and trusted webhook/session verification.

### 5.8 Customer support

-   Search/view customer profiles and their own booking history.
-   View customer requests and authorized conversation history.
-   Handle complaints and service issues.
-   Assign complaint ownership and track `open`, `in progress` and
    `resolved` states (adapt to existing conventions).
-   Record outcome and follow-up notes.
-   Link support issues to relevant bookings.
-   Restrict conversation access to authorized roles.
-   Do not expose one customer's information to another customer or
    unrelated cleaner.

### 5.9 Reviews & quality

-   View reviews and ratings.
-   Filter by date, rating, service and cleaner where data supports it.
-   Link feedback to the relevant booking.
-   Track follow-up actions and complaints.
-   Show performance metrics only when sample size and calculation are
    clear.
-   Do not fabricate ratings or infer a cleaner's performance from
    incomplete data.

### 5.10 Reports & analytics

Advanced reports requested:

-   Revenue and collected payments.
-   Booking volume and status breakdown.
-   Cancellations and rejection reasons.
-   Cleaner performance and completed work.
-   Staff working hours.
-   Customer growth and retention.
-   Popular cleaning services.
-   Expenses and profit summaries.

Requirements:

-   Date-range filters and clear date semantics.
-   Useful filters (service, cleaner, booking status, payment status)
    where data supports them.
-   CSV and Excel exports.
-   Server-side authorization and validation for exports.
-   Large reports should be generated efficiently; paginate or stream
    where appropriate.
-   Show "not available" when expense data is not recorded. Do not
    calculate profit from revenue alone. Profit requires a defined
    expense/cost model.
-   Label estimates and incomplete data honestly.

### 5.11 Business settings

Manager can configure, subject to backend validation:

-   Business name, logo and contact information.
-   Services, descriptions and prices.
-   Hourly rates and additional charges.
-   Booking rules and cancellation policies.
-   Business hours, holidays and service areas.
-   In-app/email notification preferences.
-   Staff role/permission assignments within the permitted role model.

Validate prices, dates, contact information and configuration values
server-side. Keep secrets and provider credentials out of frontend code
and database-readable settings screens.

### 5.12 Central notification centre

Provide:

-   New booking notifications.
-   Pending bookings approaching 24-hour expiry.
-   Unassigned bookings.
-   Cleaner absence and scheduling conflict alerts.
-   Unpaid/overdue booking alerts.
-   New complaints and reviews.
-   Payment and system alerts.

Include unread count, read/unread state, timestamp, priority and a deep
link to the relevant record. Notifications must be scoped to the
authorized recipient. In-app notifications are required; email is
optional. Avoid duplicate notifications when scheduled jobs retry.

### 5.13 Activity & audit log

Record important actions with:

-   Actor/user ID and role.
-   Action name.
-   Entity type and entity ID.
-   Timestamp (stored consistently, displayed in the configured local
    timezone).
-   Relevant before/after values, excluding secrets and unnecessary
    personal data.
-   Reason/comment for sensitive actions where appropriate.
-   Request/correlation ID where available.

Audit booking changes, assignment changes, shift changes, vetting
decisions, payment updates/refunds, staff account changes and
business-setting changes. Log relevant authentication and authorization
failures without storing passwords, tokens or other secrets.

Audit records must not be editable/deletable through normal manager UI.
Protect audit endpoints and avoid logging sensitive message contents or
document data unnecessarily.

------------------------------------------------------------------------

## 6. Design system and interaction behaviour

### Visual direction

-   Professional, light interface.
-   Fixed/collapsible left sidebar with icons and readable labels.
-   Neutral background, clear typography and restrained accent colour.
-   Consistent spacing, cards, tables, forms and status badges.
-   Responsive desktop, tablet and mobile layouts.
-   Accessible contrast, keyboard navigation and focus indicators.
-   Clear confirmation dialogs for destructive or high-impact actions.

Avoid a single very long manager page. Each major section should have a
distinct route/view while reusing shared layout components.

### Loading and feedback rules

Use the correct loading pattern for the task:

  -----------------------------------------------------------------------
  Situation                           Required UI
  ----------------------------------- -----------------------------------
  Whole page or major content is      Skeleton layout matching the
  loading                             expected content

  Short action with unknown duration  Indeterminate spinner

  Upload/download with measurable     Progress bar with real progress
  bytes or steps                      

  Button action after click           Immediate button loading state;
                                      disable repeat submission

  Empty result                        Helpful empty state and relevant
                                      next action

  API failure                         Clear error state and retry where
                                      safe
  -----------------------------------------------------------------------

Do not show fake percentages or progress bars for tasks whose progress
cannot be measured. Preserve existing content during background refresh
where possible. Prevent duplicate submissions and handle failures by
restoring controls and showing a useful message.

### Tables and forms

-   Search, filters, sorting and pagination where needed.
-   Server-side pagination for large datasets.
-   Clear validation messages beside fields.
-   Server-side validation remains authoritative.
-   Confirm destructive actions and show the consequences.
-   Preserve form values after recoverable validation/API errors.

------------------------------------------------------------------------

## 7. Backend, database and API implementation principles

Before writing code:

1.  Inspect the current local branch, working tree and recent commits.
2.  Read the actual SQL schema/migrations and database access layer.
3.  Map each current manager endpoint to its frontend caller and
    response shape.
4.  Inspect authentication, role checks, session/token handling and
    route dependencies.
5.  Identify existing tables and columns before proposing new ones.
6.  Run the current tests and record the baseline.

### Reuse-first policy

-   Reuse current tables, models, services and endpoints when they
    already satisfy the requirement.
-   Extend existing endpoints compatibly where practical.
-   Add a migration only when a required field/entity cannot be
    represented safely in the existing schema.
-   Never drop or rename existing columns/tables as part of a visual
    redesign.
-   Back up the database before migrations and provide rollback
    guidance.
-   Do not use destructive seed scripts against real data.
-   Keep secrets in environment variables/secret storage, not source
    code.

### Potential backend capabilities to verify

The following are **candidate gaps**, not claims that these tables or
APIs are definitely absent. Confirm the actual schema first:

-   Shift/working-hours and time-off request persistence.
-   Payment transaction/receipt/refund records.
-   Expense records and cost categories (required for meaningful profit
    reporting).
-   Customer support cases and conversation authorization.
-   Notification persistence/read state.
-   Audit log persistence.
-   Service-area and staff-skill relationships.
-   Business settings/configuration persistence.
-   Report/export endpoints or safe query services.

Only implement the missing pieces that are required and agreed. Do not
create duplicate tables for data already represented in the existing
schema.

### API requirements

-   Enforce authorization on every protected backend endpoint.
-   Validate request bodies, path parameters and query filters using
    FastAPI/Pydantic.
-   Use parameterized SQL queries.
-   Use transactions for multi-step booking/payment/schedule updates.
-   Return consistent error responses and appropriate HTTP status codes.
-   Add pagination and bounded date ranges for list/report endpoints.
-   Apply rate limiting to sensitive/authentication endpoints as
    appropriate.
-   Never trust a role, user ID, price or payment status supplied by the
    browser.
-   Keep CORS restrictive and use secure cookies/CSRF protections
    according to the app's authentication architecture.
-   Add tests for unauthorized access and cross-customer/cross-staff
    data access.

Do not invent endpoint names or database columns before inspecting the
current implementation. Document the final route contract after
implementation.

------------------------------------------------------------------------

## 8. Suggested implementation phases

### Phase 0 --- Baseline and safety

-   Inspect local working tree and repository structure.
-   Confirm current database schema and environment configuration.
-   Run existing tests and note failures.
-   Create a backup and migration/rollback plan.
-   Record existing user journeys that must remain working.

### Phase 1 --- Manager shell and navigation

-   Build shared manager layout and responsive sidebar.
-   Add page routing/navigation without changing business logic.
-   Move existing manager widgets into appropriate sections.
-   Add consistent loading, empty and error states.

### Phase 2 --- Existing manager workflows

-   Improve overview KPIs and their calculations.
-   Improve booking table, filters and assignment workflow.
-   Remove avoidable N+1 requests.
-   Improve current schedule timeline and vetting UI.
-   Add backend tests for existing manager operations.

### Phase 3 --- Scheduling and staff management

-   Implement missing shift/time-off workflows only after schema review.
-   Add conflict detection and server-side validation.
-   Improve staff profile and compliance management.

### Phase 4 --- Finance and support

-   Correct payment/revenue definitions and enforce Stripe-only payment policy.
-   Complete Stripe transaction reconciliation, payment history and refund workflows.
-   Add refunds/invoices only where supported.
-   Add customer support and review workflows based on verified data.

### Phase 5 --- Notifications, audit and settings

-   Add central notifications and deep links.
-   Add immutable-through-UI audit history.
-   Complete business settings and role-protected controls.

### Phase 6 --- Reports and exports

-   Add advanced reports using verified source data.
-   Add CSV/Excel exports.
-   Clearly identify unavailable expense/profit metrics until expense
    data exists.

### Phase 7 --- Security, accessibility and regression testing

-   Test role permissions on backend routes.
-   Test CSRF/session/CORS/security-header behaviour against the current
    architecture.
-   Test responsive layout and keyboard navigation.
-   Run unit, integration and end-to-end regression tests.
-   Confirm customer and cleaner workflows still work.

Implement incrementally. Do not attempt all phases in one large
code-generation pass.

------------------------------------------------------------------------

## 9. Acceptance criteria

The redesign is not complete until:

-   The manager has a visible, working left sidebar and separate
    management sections.
-   Existing customer and cleaner journeys still work.
-   Manager APIs enforce authorization server-side.
-   Staff and customers cannot access other users' private records.
-   Booking status transitions and the 24-hour expiry rule are reliable
    and tested.
-   Assignment and scheduling prevent conflicting allocations.
-   Finance distinguishes booking value from collected payments.
-   No profit figure is shown without expense data and a defined
    calculation.
-   Notification links lead to the correct authorized record.
-   Audit events are created for sensitive actions.
-   Loading indicators follow the rules in Section 6 and do not show
    fake progress.
-   Forms validate on the server.
-   Database migrations are reversible or have a documented recovery
    plan.
-   Existing tests pass, and new tests cover added functionality.
-   Desktop, tablet and mobile layouts are usable.

## 10. Instructions to the coding agent

1.  **Do not start coding immediately.** First inspect the current local
    repository and compare it with this document.
2.  Produce a short implementation audit: existing feature, partially
    supported feature, missing feature, relevant files/routes/tables,
    and risk.
3.  Identify the smallest safe first phase and implement only that
    phase.
4.  Ask before introducing a payment provider, changing authentication
    architecture, adding a new role, or making destructive schema
    changes.
5.  Do not fabricate data, progress, revenue, profit, staff availability
    or compliance status.
6.  Preserve existing functionality and explain any unavoidable
    behaviour change.
7.  After each phase, run relevant tests and report changed files,
    migrations, API changes and remaining gaps.
8.  Keep this specification updated if implementation decisions change.

**Primary objective:** a dependable, secure, modern manager workspace
built on the existing LondonCleanService application---not a visually
impressive redesign that breaks the booking system or misrepresents
business data.


## First-release payment policy — authoritative cross-dashboard rule

Stripe is the sole payment provider in the first release. Customers pay through Stripe during booking; a verified payment moves the booking to PENDING_REVIEW, not CONFIRMED. Manager approval is required to confirm the booking. Stripe may present cards and eligible wallet methods supported by the configured account, but there is no cash, bank transfer, manual/off-platform collection or alternative gateway. Staff have no payment-collection or payment-editing permissions. Managers can review Stripe transactions, investigate failed/pending payments and initiate refunds through Stripe; they cannot mark a payment successful without verified provider evidence. Refund state is tracked independently from booking status and job progress. The same policy must be enforced in frontend controls, API schemas, backend services, database rules where appropriate, tests and all three role-based interfaces. This section supersedes older cash-handling statements in this document or the repository.


## Cross-dashboard lifecycle clarification

Use `CROSS_DASHBOARD_INTEGRATION.md` as the authoritative integration contract for the customer, staff and manager dashboards. It defines the separate booking, payment, slot-reservation, assignment and job-progress lifecycles; event ownership; permissions; notifications; and end-to-end acceptance scenarios. If this redesign document conflicts with that integration contract, the integration contract takes precedence until the documents are deliberately revised together.
