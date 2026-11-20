# Staff Dashboard Requirements

**Project:** LondonCleanService  
**Repository:** `NRP-Raja/LondonCleanService-`  
**Document type:** Product requirements, workflow rules, UX and implementation specification  
**Status:** Staff workflow decisions consolidated; implementation must begin with a code/schema audit  
**Architecture baseline:** FastAPI, MySQL 8.0, HTML/CSS and Vanilla JavaScript; modular backend under `app/routes/`, `app/services/`, `app/schemas/`  
**Related specification:** `CUSTOMER_DASHBOARD_REQUIREMENTS.md`

---

## 1. Purpose and product principle

Build a dependable, mobile-first workspace that helps cleaners carry out the jobs assigned to them. The staff dashboard is one role-specific interface in a single connected cleaning operations platform.

The platform has three interfaces:

1. **Customer:** books and manages cleaning appointments.
2. **Staff/Cleaner:** accepts assigned work and records the real progress of a cleaning job.
3. **Manager:** controls bookings, staff, schedules, assignments, finance and customer support.

All three interfaces must use the same booking, assignment, customer, staff, payment and notification records. A cleaner's update must flow through the backend to the customer and manager views. Do not build independent dashboard-only data or duplicate workflows.

**Staff are responsible for carrying out assigned work. Managers retain operational control.** Staff must not independently allocate jobs, change confirmed shifts, change prices, manage payments or edit customer accounts.

## 2. Repository inspection: confirmed starting point

The following observations were made from the repository's `docs/customer-dashboard-requirements` branch and its modular backend files. They describe the inspected code, not proof that every workflow is currently working in a deployed environment.

| Area | Existing implementation observed | Required decision |
|---|---|---|
| Backend structure | Staff routes, schemas and services exist under `app/routes/staff.py`, `app/schemas/staff.py` and `app/services/staff.py`. | Extend these modules; do not recreate a parallel staff backend. |
| Assigned jobs | `GET /api/staff/jobs` returns bookings where `staff_id` matches the signed-in staff member. | Keep ownership restriction and return a deliberately limited staff-safe response, not every column from `bookings`. |
| Job status | Existing transitions include `SCHEDULED → EN_ROUTE → IN_PROGRESS → COMPLETED`, alongside booking states such as `PENDING`, `APPROVED` and `CONFIRMED`. | Reconcile the existing state model with the agreed operational progress below. Do not silently break existing customer or manager workflows. |
| Status audit | Status changes are inserted into `booking_status_logs`. | Preserve and extend auditable history for assignment and job progress events. |
| Schedule | Staff endpoints currently allow a cleaner to edit their weekly availability and add/remove holidays. | This conflicts with the agreed manager-controlled schedule. Staff schedule must become read-only in the staff interface; managers own edits. |
| Earnings | `GET /api/staff/earnings` calculates a 70% share of completed booking value and exposes earnings data to staff. | Do not show staff earnings, revenue or performance reports in this dashboard. Do not assume the 70% formula is an approved pay policy. |
| Payment integrity | The inspected status update service sets `payment_status = 'PAID'` when a job becomes `COMPLETED`. | This is incorrect. Completing cleaning must never mark a payment as paid. Payment state is controlled by verified payment/cash-recording workflows and remains independent of job completion. |
| Customer data | The current jobs query selects `b.*` and customer phone details; access notes are masked by status. | Restrict returned fields to what the cleaner needs for their assigned job. Preserve access-note protection and review all personal-data exposure. |
| Scheduling conflicts | The staff service already contains cleaner overlap and travel-buffer checks, plus weekly availability/holiday checks. | Reuse and test these checks in manager assignment workflows. Staff cannot override conflicts. |
| Frontend | The existing shared frontend contains a staff dashboard view and calls job, schedule and earnings loaders. | Improve the existing staff area and shared navigation carefully; do not replace the whole application or break customer/manager routing. |

### Critical implementation risks

1. The current booking status field mixes customer booking lifecycle states and cleaner operational progress. These are different concepts and must be separated logically.
2. The current completion/payment coupling can create false paid records and must be corrected before relying on job completion.
3. Staff self-editable availability conflicts with manager-controlled scheduling.
4. The current job response may expose more customer or booking data than the staff role needs.
5. Assignment acceptance, arrival, work timer, completion photos and booking-specific staff chat are not established by the inspected staff route contract. Verify the full schema and frontend before implementation; do not claim these capabilities already exist.

## 3. Staff dashboard scope and navigation

Keep the staff workspace focused. It should not become a second manager dashboard.

Recommended sections:

1. **Today** — today's jobs, next appointment and urgent actions.
2. **My Jobs** — assigned jobs, upcoming work and job history.
3. **My Schedule** — read-only assigned shifts and upcoming days off/availability information.
4. **Notifications** — assignment, schedule and job-related alerts.
5. **Profile & Security** — basic staff profile, password and session security.

Use a simple responsive navigation appropriate to the existing application. On mobile, prioritise a compact navigation pattern and large touch targets. Do not add manager-only sections, financial reports, staff-wide calendars or business analytics.

## 4. Staff homepage

The default landing page after staff login must answer three questions immediately:

- What jobs do I have today?
- What is my next action?
- Has anything changed that I need to know?

Display:

- Today's assigned jobs, ordered by appointment time.
- The next appointment with time, service and current job state.
- A clear action for the next required step (review assignment, accept, travel, arrive, start or complete).
- Assignment responses awaiting action and their response deadlines.
- Important unread notifications.
- A simple upcoming-shifts preview.

If there are no jobs today, show a useful empty state and the next scheduled shift/job. Do not show fabricated statistics or empty KPI cards.

## 5. Assignment workflow

### 5.1 Manager creates the assignment

- A manager selects a cleaner and assigns an eligible booking.
- The backend validates staff account status, working schedule, time off, service suitability where applicable, booking status, time overlap and configured travel buffer.
- The assignment is saved against the shared booking record and is visible to the assigned cleaner only.
- The cleaner receives an in-app notification and a browser notification when permission is available.

### 5.2 Cleaner accepts or declines

Assignment acceptance is required.

- Cleaner opens the assignment and reviews the appointment, service, date/time, property/task details and relevant instructions.
- Cleaner can **Accept** or **Decline**.
- Declining requires an optional short reason and immediately notifies the manager.
- The cleaner cannot choose a replacement or reassign the job.
- A declined or expired assignment returns to the manager's dispatch queue for review/reassignment. It does not cancel the customer's booking.

### 5.3 Response deadline

- Default response window: **2 hours** from assignment creation.
- The manager can configure the response window.
- Show the deadline clearly to the cleaner.
- If no response is received before expiry, expire that assignment, notify the manager and make the booking available for manager reassignment.
- Expiry must be enforced server-side, not by a browser-only countdown.
- Expiry processing must be idempotent and safe if a scheduled task runs more than once.

### 5.4 Reassignment

- Only a manager can reassign a job.
- The previous assignment and its acceptance/decline/expiry history remain auditable.
- The previous cleaner loses access to job-specific customer information after reassignment, except records they are authorised to retain for audit or completed work.
- The new cleaner receives a new assignment notification and acceptance deadline.
- Notify the customer when the assigned cleaner changes, using the customer notification rules.

## 6. Job progress and status rules

### 6.1 Staff-facing operational sequence

After accepting an assignment, the cleaner progresses through these steps in order:

1. **Assigned** — manager has created the assignment.
2. **Accepted** — cleaner has accepted it.
3. **On the way** — cleaner is travelling to the appointment.
4. **Arrived** — cleaner has reached the property.
5. **Cleaning started** — cleaner has begun the service; work timer starts.
6. **Cleaning completed** — cleaner has finished; work timer stops and completion is recorded immediately.

Rules:

- Required stages cannot be skipped.
- Each state change is timestamped and attributed to the acting user/system.
- Customer and manager views receive the relevant updates from the same event.
- A completed job cannot be silently reopened.
- If a correction is genuinely necessary, a manager uses a controlled correction action with a reason and audit event.
- A cleaner must not be able to mark an unrelated booking as complete or update another cleaner's job.

### 6.2 Separate booking lifecycle from job progress

The existing application uses booking status values for both customer booking decisions and cleaner job progress. The target design must keep these concepts distinct:

- **Booking lifecycle:** customer request, approval/confirmation, cancellation/rejection and other customer-facing booking outcomes.
- **Assignment lifecycle:** assigned, accepted, declined, expired, reassigned.
- **Job progress:** on the way, arrived, cleaning started, cleaning completed.
- **Payment lifecycle:** pending, paid, failed, refund pending, refunded or refund failed, based only on verified Stripe/provider events. No cash or manual payment states are supported in the first release.

Do not solve this by blindly replacing existing enum values or changing every status in one pass. Inspect all existing database constraints, API contracts, frontend conditions, customer timelines, manager filters and tests. Introduce a backward-compatible mapping/migration strategy and update all role views together.

### 6.3 Exceptional status correction

- Staff contact the manager if they make a mistake or cannot progress.
- Managers can correct an exceptional state with a mandatory reason.
- Preserve the original event and corrected event in history.
- Do not offer staff a generic ability to jump backwards or skip stages.

## 7. Work timer and duration recording

The timer records actual cleaning duration.

- Start automatically when the cleaner selects **Cleaning started**.
- Stop automatically when the cleaner selects **Cleaning completed**.
- Persist the start timestamp, end timestamp and calculated elapsed duration on the server.
- Use server timestamps as the source of truth; browser clocks must not determine the official duration.
- Prevent duplicate active timers for the same booking.
- Prevent completion without a valid active work session unless a manager records an audited exception.
- If the network drops, show the action's pending/saved state clearly and retry safely without creating duplicate events.
- Manager can review and correct an exceptional timing record with a reason and audit history.

**No break tracking:** record the full elapsed time between cleaning start and cleaning completion. Do not add pause, break, deduction or break-duration controls.

Keep estimated service duration separate from actual recorded duration. Do not overwrite the original estimate with the timer result.

## 8. Completion evidence: photos and notes

At completion, the cleaner must provide:

- Before-cleaning photos.
- After-cleaning photos.
- Written completion notes.

Requirements:

- Provide clear camera/upload actions suitable for mobile.
- Validate image MIME type, file signature, file size and allowed formats server-side.
- Store files privately with access checks; do not expose public predictable file URLs.
- Link evidence to the relevant booking and uploader.
- Preserve upload timestamps and metadata needed for audit, while avoiding unnecessary personal metadata.
- Manager can review the evidence after job completion.
- Completion is immediate; manager review does not block the booking from becoming completed.
- Customer visibility is not automatic. Only expose photos to the customer through an explicitly authorised customer-facing evidence flow; the safe default is manager review/approval before customer display.
- Do not allow a cleaner to edit or replace evidence silently after completion. Any permitted correction must be recorded.

## 9. Problems during a job and communication

Use the existing booking-specific conversation as the single communication channel.

- Cleaner can contact the manager through the relevant booking conversation or the configured business phone contact.
- Customer and assigned cleaner can communicate within the same booking conversation.
- Authorised managers can access that conversation to coordinate support and resolve issues.
- Do not create a separate staff-to-manager chat system, duplicate inbox or independent incident-reporting form.
- A cleaner must contact the manager when a job cannot proceed, the customer is unavailable, access fails, the property/task differs materially from the booking or an issue requires a decision.
- The manager decides whether to resolve, amend, pause, cancel or reassign the job.
- Relevant information can be recorded in booking notes or the existing conversation.

Chat permissions must be enforced server-side and scoped to the booking and its authorised participants. Preserve conversation history according to the platform's retention policy.

## 10. Staff schedule and availability

Scheduling is manager-controlled.

Staff can:

- View their own assigned shifts and upcoming appointments.
- See schedule changes and the manager's instructions.
- See their own relevant availability/time-off information where appropriate.

Staff cannot:

- Edit or delete confirmed shifts.
- Change their weekly working schedule directly in the dashboard.
- Add or remove holidays in a way that changes dispatch availability without manager review.
- Assign themselves to a booking.
- Override an overlap, travel buffer, time-off or working-hours conflict.

Managers create, edit, move, approve and delete shifts and control availability. A manager schedule change must notify affected staff. The backend must prevent conflicting assignments and enforce working schedules even if a browser submits a forged request.

The current `PUT /api/staff/schedule`, `POST /api/staff/holidays` and `DELETE /api/staff/holidays/{holiday_date}` staff self-service routes conflict with this agreed model. Replace or restrict them only after checking all callers and manager workflows. Keep a read-only staff schedule view.

## 11. Staff job history

Provide a simple personal history of completed and cancelled jobs.

Show only useful operational details:

- Booking reference.
- Service name.
- Appointment date.
- Job outcome/status.
- Actual duration where recorded.

Do not provide business-wide staff comparisons, revenue reports, cleaner rankings, customer lifetime value, profit figures or financial performance dashboards.

The current staff earnings endpoint and frontend earnings panel must be reviewed. Remove staff-facing earnings/revenue reporting from the dashboard and avoid presenting the existing 70% calculation as an approved wage or commission rule. Do not delete historical payment or payroll data that the manager/business may need.

## 12. Notifications

In-app notifications are required. Browser notifications should be used when the staff member grants permission.

Notify staff about:

- New job assignments requiring acceptance.
- Assignment expiry reminders where useful.
- Assignment changes, reassignment or cancellation.
- Upcoming appointments and relevant reminders.
- Shift creation or schedule changes.
- New messages in a booking conversation.
- Important manager updates.

Requirements:

- Show unread count and notification history.
- Link each notification to the relevant authorised booking, shift or conversation.
- Avoid duplicate notifications when background jobs retry.
- Do not block core dashboard use if browser notifications are denied or unsupported.
- Do not repeatedly prompt for browser permission on page load.
- Do not send unnecessary email for every chat message; in-app and browser notifications are the default for staff chat.

## 13. Profile, account and access security

### 13.1 Staff profile

Show a basic profile:

- Name and profile photo.
- Assigned role.
- Relevant work contact details.
- Upcoming shifts.
- Account status.

Staff can update their own password and manage their own session security. The manager controls employment information, roles, permissions and account status.

### 13.2 Account lifecycle

- Manager creates staff accounts and assigns roles.
- Staff receive a secure account activation process.
- Manager can suspend and reactivate staff accounts.
- Suspended staff cannot access the dashboard or call staff APIs.
- Historical work and audit records remain available to authorised managers.
- Do not allow public self-registration to grant a user the staff role.

### 13.3 Least-privilege access

A cleaner can access only:

- Their own profile and permitted security controls.
- Jobs currently assigned to them.
- Their own relevant schedule.
- Booking conversations for jobs where they are an authorised participant.
- Their own relevant notifications and job history.
- Property instructions and customer information strictly needed to carry out an assigned job.

A cleaner cannot access:

- Other cleaners' jobs, schedules, private profiles or personal details.
- Unassigned customer bookings.
- Customer account management.
- Business-wide reports or financial management.
- Pricing configuration, payment processing, refunds or payment status editing.
- Staff management, vetting decisions or business settings.
- Manager-only audit records.

Preserve the existing protection that masks sensitive access instructions until the cleaner is travelling to the assigned property. Review the exact unlock/lock rules against the new progress states. Re-mask sensitive access information when the job is completed, cancelled or reassigned, unless an authorised operational need requires otherwise.

All permissions must be enforced in backend routes/services, not merely by hiding frontend buttons.

## 14. Late arrival and location privacy

### Late-arrival handling

- Use the appointment's expected time and the job's progress events to detect a potentially late cleaner.
- If the cleaner has not marked **On the way** or **Arrived** by the configured threshold, flag the booking and notify the manager.
- The threshold must be configurable by the manager/business; do not hard-code an arbitrary grace period.
- The cleaner can still update their status.
- The manager decides whether to contact the customer, investigate or reassign.
- Do not automatically penalise staff or cancel a customer booking based only on this alert.

### Location privacy

- Do not continuously track staff GPS.
- Do not collect background location.
- Record only the **On the way** and **Arrived** event timestamps, plus any location data the user explicitly supplies as part of a separate approved feature.
- Do not add a map that implies live tracking when no live location is collected.

## 15. Connected-system behaviour

The staff dashboard must be connected to the customer and manager workflows.

| Staff action | Customer experience | Manager experience |
|---|---|---|
| Accept assignment | Assigned cleaner can be shown where appropriate. | Assignment marked accepted. |
| Decline or fail to respond | Customer booking remains active; customer is not told the booking is cancelled. | Alert and reassignment action appear. |
| On the way | Customer sees the progress update. | Manager sees the latest job state/time. |
| Arrived | Customer sees arrival update where appropriate. | Manager sees arrival timestamp. |
| Cleaning started | Customer sees cleaning has started. | Manager sees active work session and timer. |
| Cleaning completed | Customer sees completed booking and can access the normal review flow. | Manager sees completion, duration, notes and evidence for review. |
| Manager reassigns cleaner | Customer receives an appropriate assignment-change notification. | Previous and new assignment history remain visible. |
| New booking chat message | Relevant participant sees the message and notification. | Authorised manager can follow the same booking conversation. |

Use a single source of truth and reliable event/notification handling. If live updates are unavailable, refresh or retry safely; never show a success state before the backend confirms the action.

## 16. Technical and data requirements

Before adding tables or fields, inspect `init.sql`, `app/database/migrations.py`, all current booking/staff tables, route contracts and existing audit/notification mechanisms.

Likely logical capabilities to verify (not an instruction to create duplicate tables):

- Staff assignment records and assignment response deadline/state.
- Assignment history.
- Job progress event history.
- Work session start/end timestamps and actual duration.
- Completion notes and private photo evidence metadata.
- Booking conversation membership and image attachments.
- Staff notifications and delivery/read state.
- Manager-controlled shifts, availability and time off.
- Audit records for manager corrections and staff-sensitive actions.

Implementation rules:

- Reuse current booking and staff entities where appropriate.
- Separate booking, assignment, job-progress and payment lifecycles logically.
- Use transactions for assignment changes, status transitions and timer completion.
- Use database constraints/locking or equivalent concurrency controls to prevent duplicate active assignments and duplicate active timers.
- Use UTC for persisted event timestamps where appropriate and display them in the configured London timezone.
- Use decimal/fixed-point money values; staff dashboard must not calculate or display wages.
- Do not store secrets or private photo URLs in public frontend code.
- Do not expose all columns from `bookings` to staff by returning `SELECT b.*`.
- Keep API contracts documented with Pydantic schemas and OpenAPI.
- Additive migrations only. Never drop/recreate existing production tables or reset existing Docker/MySQL data to implement this dashboard.

## 17. Suggested implementation phases

### Phase 0 — Baseline and reconciliation

- Confirm the correct coding branch and clean working tree.
- Inspect current staff frontend, route/service/schema files, manager assignment workflow, customer booking timeline and database schema.
- Run existing tests and record baseline failures.
- Map current status values and all callers.
- Identify the exact payment-status bug and staff data exposure before feature work.

### Phase 1 — Staff workspace foundation

- Improve the existing staff dashboard layout.
- Build the Today, My Jobs, My Schedule, Notifications and Profile sections.
- Make the homepage mobile-first.
- Remove staff-facing earnings/reporting UI.
- Make staff schedule read-only.

### Phase 2 — Assignment acceptance

- Add accept/decline workflow and configurable two-hour default deadline.
- Add server-side expiry and manager notifications.
- Preserve assignment history and safe reassignment.
- Test conflict handling and ownership.

### Phase 3 — Job progress and connected timeline

- Reconcile booking and operational statuses.
- Add Arrived and the agreed sequential progress flow.
- Publish customer/manager updates from shared events.
- Preserve access-note masking and audit history.

### Phase 4 — Timer and completion evidence

- Add automatic server-side work timer.
- Add before/after photos and completion notes.
- Correct the payment-status coupling so job completion cannot mark payment as paid.
- Add secure upload and evidence access tests.

### Phase 5 — Communication and notifications

- Connect staff to the existing booking-specific conversation.
- Add required in-app and browser notifications.
- Add reliable retries, deduplication and fallback refresh behaviour.

### Phase 6 — Security and regression

- Verify staff ownership and least-privilege access.
- Test all status transitions, assignment expiry, timers, uploads and notifications.
- Test customer and manager workflows after every shared-state change.
- Verify desktop, tablet and mobile layouts.

The coding agent may adjust phase order where dependencies require it, but must explain why and preserve the requirements.

## 18. Acceptance criteria

The staff dashboard is not complete until all applicable checks pass:

### Navigation and homepage

- Staff can access a clear, responsive dashboard after authentication.
- Today's jobs and next action are immediately visible.
- Empty, loading, retry and error states are real and useful.
- The dashboard works on common mobile, tablet and desktop sizes.

### Assignments

- Staff see only their own active assignments.
- New assignment requires accept/decline.
- Two-hour default response deadline is configurable.
- Expiry is enforced server-side and notifies the manager.
- Declined/expired assignments do not cancel the customer's booking.
- Reassignment preserves history and updates the customer appropriately.

### Job progress and timer

- Staff cannot skip required job stages or update another cleaner's job.
- All progress events are timestamped and audited.
- Customer and manager views reflect the same progress.
- Timer starts at Cleaning started and stops at Cleaning completed.
- Duplicate timers and duplicate completion actions are prevented.
- No break/pause controls exist.
- Actual duration is stored separately from estimated duration.
- Completion does not change payment status.

### Evidence and communication

- Before/after photos and completion notes are linked to the correct booking.
- Uploads are validated and private.
- Manager can review evidence after instant completion.
- Customer photos are hidden unless explicitly authorised for display.
- Staff can communicate through the existing booking conversation.
- No duplicate staff-only messaging or incident-reporting workflow is introduced.

### Schedule and role permissions

- Staff schedule is read-only.
- Staff cannot change confirmed shifts or self-assign jobs.
- Manager schedule changes notify affected staff.
- Staff APIs reject access to other cleaners' jobs and private records.
- Suspended staff cannot access staff dashboard routes.
- Sensitive property access information remains protected.

### Notifications and privacy

- Required in-app notifications work without browser permission.
- Browser notifications work only when permission is granted.
- Notifications link to authorised records and do not duplicate on retry.
- No continuous/background GPS tracking is introduced.
- No staff-facing business revenue, wage calculation or performance analytics are displayed.

### Regression and security

- Existing customer booking, payment, manager dispatch and staff job workflows remain functional.
- API role checks and ownership checks are tested server-side.
- Payment status is controlled only by the payment workflow.
- Migrations preserve existing data and are safe for existing database volumes.
- Tests cover assignment expiry, reassignment, invalid transitions, timer concurrency, upload validation, IDOR, role escalation and notification retries.
- No placeholder controls or fake success states remain.

## 19. Git and coding-agent rules

1. Do not implement directly on `main`.
2. Fetch the latest remote state and create a focused feature branch from the correct integration branch.
3. This document branch is a requirements branch, not automatically the coding branch.
4. Inspect the actual local repository, database schema, frontend and tests before coding.
5. Reuse existing working code and preserve public, customer and manager workflows.
6. Do not rewrite the backend or frontend wholesale.
7. Do not perform destructive database resets or remove existing data.
8. Implement one phase at a time and run targeted tests after each phase.
9. Run the full regression suite before declaring completion.
10. Do not merge automatically. Merge only after tests pass and the project owner explicitly approves.
11. Report exact files changed, migrations, API changes, tests actually run and remaining risks. Never claim a test passed if it was not run.
12. If existing implementation conflicts with this specification, document the conflict and implement the agreed target safely with regression tests.

---

**Definition of done:** a cleaner can securely accept and complete only their assigned jobs, record accurate progress and completion evidence, communicate through the correct booking conversation and view their own schedule—while the manager remains in control and customers see consistent updates from the same underlying booking.


## First-release payment boundary — Stripe only

The first release uses Stripe as the sole payment provider. Customers complete payment through the secure Stripe flow; booking confirmation requires trusted server-side Stripe verification. **Staff do not collect cash, record cash received, accept bank transfers, process payments, issue refunds, or edit payment status.** Staff may see only the minimum customer-safe payment state needed to understand the assigned job (for example, whether the booking is confirmed/paid if operationally necessary). They must not see card data, full payment credentials, Stripe secrets, or manager-only financial records. Job completion must never mark a payment as paid. Payment state is updated only by verified Stripe events and authorised manager refund/reconciliation workflows. This policy overrides any legacy cash-handling behaviour in the codebase.


## Cross-dashboard lifecycle clarification

See `CROSS_DASHBOARD_INTEGRATION.md` for the authoritative state model. Staff access begins only after a manager-approved (`CONFIRMED`) booking has an active assignment to that cleaner. Assignment acceptance does not itself confirm a booking or change payment status. A decline or assignment timeout leaves the customer booking confirmed and returns it to manager dispatch. Staff job progress updates the shared operational timeline; it never changes payment status. On reassignment, the previous cleaner loses active access to customer/property details and the new cleaner receives a new assignment with a fresh response deadline. The booking conversation remains the single conversation; participant access is updated according to the active assignment.
