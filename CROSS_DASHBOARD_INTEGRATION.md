# Cross-Dashboard Integration Contract

**Project:** LondonCleaningService  
**Document:** Shared workflow and integration specification  
**Status:** Consolidated planning baseline — no implementation authorised yet  
**Prepared:** 20 November 2026  
**Applies to:** Customer, Staff/Cleaner and Manager dashboards  
**Precedence:** This document is the shared integration contract. Role-specific dashboard documents describe each interface; this document defines how those interfaces must work together.

---

## 1. Purpose and non-negotiable architecture

The three dashboards are different role-based views of one application, not separate applications or separate copies of business data.

The backend is the single source of truth for:

- Customers, staff and role permissions.
- Bookings and appointment details.
- Temporary slot reservations.
- Stripe payment attempts, transactions and refunds.
- Manager approval decisions.
- Cleaner assignments and assignment history.
- Cleaning progress, work sessions and completion evidence.
- Booking conversations and participants.
- Notifications, delivery state and audit events.

A user action must be authorised and validated by the backend. The backend commits the state change, records the event/audit information and creates notification work. Each dashboard then reads the resulting authoritative state. Frontend state is a presentation/cache only; it must never be treated as the source of truth.

Do not create separate customer, staff and manager versions of a booking or payment record. Do not let one dashboard silently infer or independently mutate another lifecycle.

## 2. The five independent lifecycle dimensions

These dimensions must be represented separately, even if the existing database currently combines some of them.

| Dimension | Illustrative states | What it controls |
|---|---|---|
| Temporary slot reservation | HELD, EXPIRED, CONSUMED, RELEASED | Short-lived availability lock during checkout |
| Booking lifecycle | PAYMENT_PENDING, PENDING_REVIEW, CONFIRMED, REJECTED, CANCELLED, COMPLETED | Whether the appointment request is valid/approved and its business outcome |
| Payment lifecycle | REQUIRES_PAYMENT, PROCESSING, PAID, FAILED, REFUND_PENDING, PARTIALLY_REFUNDED, REFUNDED, REFUND_FAILED | Money movement verified through Stripe |
| Assignment lifecycle | UNASSIGNED, AWAITING_RESPONSE, ACCEPTED, DECLINED, EXPIRED, REASSIGNED, WITHDRAWN | Which cleaner has been offered/assigned the job and their response |
| Job progress | NOT_STARTED, ON_THE_WAY, ARRIVED, CLEANING_STARTED, CLEANING_COMPLETED | Actual execution of the cleaning service |

These are logical concepts, not a demand to create five new tables or use these exact enum strings. Inspect current schema, migrations, enums, API contracts and frontend conditions first. Reuse existing entities where safe, and introduce a backward-compatible migration plan.

Important invariants:

1. Payment success is not manager approval.
2. Manager approval is not cleaner acceptance.
3. Cleaner acceptance is not job commencement.
4. Job completion does not mark payment paid.
5. A refund does not automatically rewrite the historical payment into a failed payment.
6. A declined/expired cleaner assignment does not cancel the customer booking.
7. A temporary checkout hold is not the 24-hour manager-review window.
8. Every dashboard reads the same authoritative state and event history.

## 3. End-to-end customer booking and payment workflow

### 3.1 Booking draft and slot selection

1. Customer creates or resumes a booking draft.
2. Drafts may be saved for up to 30 days but do not reserve a slot.
3. Customer selects an available date/time and reviews the server-calculated GBP quote.
4. On entering checkout, the backend atomically checks availability and creates a temporary 10-minute slot hold.
5. The customer sees the 10-minute countdown. Other customers cannot reserve the held slot.
6. A draft alone never holds capacity.

### 3.2 Stripe payment

1. Customer pays through Stripe; Stripe is the only payment provider in the first release.
2. Cards and eligible wallet/payment methods may appear only when enabled and supported by the Stripe account, currency, domain, device and checkout configuration.
3. No cash, bank transfer, manual/off-platform collection or alternative gateway.
4. The backend validates the amount against its own quote and uses idempotency for checkout and fulfilment.
5. Only verified Stripe webhook/session evidence can mark the payment successful. A browser redirect, client callback or screenshot is never sufficient.
6. If payment fails, the customer may retry while the 10-minute hold remains valid.
7. When payment is verified before hold expiry, consume the hold and move the booking into `PENDING_REVIEW`; payment becomes `PAID`.
8. The customer sees **Payment received — awaiting manager approval**, not Booking confirmed.
9. If the hold expires before payment succeeds, release the slot. A late successful Stripe event must be reconciled safely: never double-book. If the original slot cannot be safely reacquired, initiate a full Stripe refund and notify the customer; record the exception for manager review.
10. Duplicate/out-of-order Stripe events must be idempotent and must not duplicate bookings, charges, refunds, notifications or audit events.

### 3.3 Manager review — 24-hour rule

1. The 24-hour review clock starts when the backend verifies successful payment and the booking enters `PENDING_REVIEW`.
2. It runs continuously across nights, weekends and holidays; it is not a business-hours timer.
3. Manager can approve or reject with an auditable decision.
4. Approval moves the booking to `CONFIRMED`. Only then may the manager assign a cleaner.
5. Rejection or failure to decide within 24 hours moves the booking to `REJECTED` and starts a full Stripe refund.
6. Customer sees a clear rejection/refund-processing message. Do not display REFUNDED until Stripe confirms the refund.
7. The full refund on manager rejection/24-hour expiry is the recommended first-release safeguard because the business cannot fulfil the paid appointment. It must be included in final business-policy sign-off before implementation.
8. The expiry worker must be server-side, idempotent, observable and safe to run more than once. It must not rely on a browser timer.

### 3.4 Confirmed booking

After manager approval:

- Customer sees Booking confirmed.
- Manager sees the confirmed booking in dispatch.
- Customer may see the assigned cleaner only after assignment.
- Staff cannot see or accept a booking that is not actively assigned to them.
- Booking details, address and service instructions are shared only with authorised roles.

## 4. Manager-to-cleaner assignment workflow

1. Manager assigns a cleaner only to an eligible `CONFIRMED` booking.
2. Backend validates staff account status, service suitability, skills, service area, working hours, shifts, time off, overlapping bookings and configured travel buffer.
3. Hard conflicts block assignment. The manager receives a clear explanation rather than a silent override.
4. Assignment is persisted as its own record/history, not merely an overwritten `booking.staff_id`.
5. Cleaner receives an in-app notification and browser notification if permission is available.
6. Default response deadline is two hours from assignment creation; manager may configure the response window.
7. Cleaner accepts or declines. Decline may include a short reason and immediately alerts manager.
8. If declined or expired, the assignment becomes inactive and the booking remains `CONFIRMED` and paid. It returns to the manager's dispatch queue for reassignment.
9. Manager alone can reassign. Previous and new assignments remain in history; a new assignment gets a fresh response deadline.
10. Customer receives an appropriate update when the cleaner is assigned or changed.
11. Previous cleaner loses active access to the booking's customer/property details after reassignment, except records required for authorised audit or completed work.
12. A manager may withdraw an assignment when cancelling/changing a booking. This must be an explicit audited action.

No cleaner can self-assign, choose their replacement, alter another cleaner's assignment or edit the confirmed schedule.

## 5. Cleaner job progress workflow

After accepting an active assignment, the cleaner follows this sequence:

1. `ACCEPTED`
2. `ON_THE_WAY`
3. `ARRIVED`
4. `CLEANING_STARTED`
5. `CLEANING_COMPLETED`

The initial assignment-created state is `AWAITING_RESPONSE`; acceptance is a separate assignment event. Required job stages cannot be skipped. Each event records server timestamp, actor, booking and active assignment.

- On the way and Arrived record timestamps only; do not collect continuous GPS.
- Cleaning started creates one active work session and starts the server-authoritative timer.
- Cleaning completed stops the active timer, records elapsed duration, saves notes/photos and completes the job immediately.
- A duplicate start/complete request must be idempotent.
- Manager corrections require a reason and audit event. Completed work cannot be silently reopened.
- Staff completion never changes Stripe payment state.
- Customer sees customer-safe progress from the same event history.
- Manager sees operational state, late alerts, timer/duration, notes and evidence.
- Customer evidence visibility remains manager-controlled: completion photos are private to manager and authorised staff by default; customer display requires an explicit authorised review/release action.

## 6. Canonical customer-facing progress mapping

The customer timeline must distinguish booking approval from cleaner progress:

| Backend event/state | Customer presentation |
|---|---|
| Payment verified + `PENDING_REVIEW` | Payment received — awaiting manager approval |
| Manager approves + `CONFIRMED` | Booking confirmed |
| Active assignment created | Cleaner assigned |
| Cleaner accepts | Cleaner confirmed the assignment (optional detail) |
| `ON_THE_WAY` | Cleaner on the way |
| `ARRIVED` | Cleaner has arrived (optional detail) |
| `CLEANING_STARTED` | Cleaning started |
| `CLEANING_COMPLETED` | Cleaning completed |

Do not display a cleaner as assigned before the manager has created an active assignment. Do not display an assignment as accepted before the cleaner accepts. Do not show a completed appointment while a required work session is still active.

Customer-facing labels may be simpler than internal state names, but they must be truthful and derived from backend events.

## 7. Booking-specific chat and participant access

There is one conversation per booking. Do not create separate customer-cleaner, cleaner-manager and manager-customer duplicate chat threads.

Authorised participants:

- Customer/verified guest owner of that booking.
- Currently assigned cleaner while the assignment is active.
- Authorised manager/support staff for operational support.

Rules:

- Customer can message only within their own booking.
- Cleaner can access only conversations for their own active assignments.
- Manager access is role-protected and audited.
- On reassignment, update active cleaner membership. The previous cleaner loses ongoing access to customer messages and new property details; preserve records required for audit/operational continuity under the retention policy.
- On assignment decline/expiry, the declined/expired cleaner must not retain active access.
- Customer may continue to see the booking conversation history.
- Photo attachments only, validated server-side and stored privately.
- No personal phone number exchange is required; the configured public business contact remains available.
- Message send, read state and notifications must be reliable and deduplicated.

## 8. Notifications and shared event handling

Use a single backend event/outbox pattern so state changes and notification work cannot drift apart.

Important events include:

- Booking draft/checkout expiry where customer action is needed.
- Stripe payment success/failure/refund state changes.
- Booking enters manager review; review deadline approaching; approval/rejection/expiry.
- New assignment, assignment acceptance, decline, expiry, reassignment and cancellation.
- Cleaner on the way, arrived, cleaning started and completed.
- Schedule changes, time-off decisions and late-cleaner alerts.
- New booking chat messages.
- Customer cancellation/reschedule requests and manager decisions.

Each event must have a stable identifier, event type, entity/booking reference, actor/system source, timestamp and idempotency/deduplication key. Notification delivery records include recipient, channel, status, retry metadata, read state and authorised deep link.

- In-app notifications are the durable baseline.
- Customer transactional notifications use in-app and email according to the customer requirements.
- Staff use in-app and browser notifications; email is not sent for every chat message.
- Browser push requires explicit permission; denial must not break the workflow.
- Manager receives operational alerts in the central notification centre.
- A notification is never the source of truth; opening it must fetch current authorised data.
- Do not send duplicates when jobs retry or a webhook is replayed.

## 9. Role and data access matrix

| Capability/data | Customer | Assigned cleaner | Manager |
|---|---|---|---|
| Own profile and account | Read/update permitted fields | Own permitted profile fields | Manage staff/customer operational records as authorised |
| Booking details | Own bookings | Active assigned jobs only | All business bookings |
| Customer address/access notes | Own booking | Only for active assigned job and at permitted progress stage | Operational need |
| Cleaner personal details | Only customer-safe profile after assignment | Own profile; no other cleaners' private data | Staff-management scope |
| Assignment | View assigned cleaner/status | Accept/decline own assignment | Create, reassign, withdraw |
| Job progress | Read customer-safe timeline | Update own active assignment only | Read; audited correction |
| Completion evidence | Only after explicit manager release | Upload own active job evidence; no silent edits after completion | Review and control release |
| Stripe payment details | Own payment history/receipt, safe display | No financial details; at most a minimal operational payment indicator if required | View transaction and refund operations |
| Payment status mutation | None | None | No manual success override; Stripe-verified updates only |
| Refund | Request/cancel according to policy; see state | None | Initiate through Stripe; no false success |
| Booking chat | Own booking | Active assigned booking | Authorised, audited support access |
| Schedule | Own appointments | Own schedule, read-only | Full schedule control |
| Staff/customer administration | Own account only | No | As authorised |
| Audit log | No | No manager audit access | Read-only audit interface |

All permissions must be checked server-side on every request and object lookup. Hiding a button is not authorisation. Apply least privilege and avoid returning unused personal/payment fields in API payloads.

## 10. Cancellation, rescheduling and refunds

- Customer cancellation at least 24 hours before the appointment: full Stripe refund to the original payment method.
- Customer cancellation under 24 hours: no automatic refund; customer can request a manager exception.
- Customer cannot ordinarily cancel a job already in progress or completed.
- Customer self-service rescheduling is allowed at least 24 hours ahead, subject to live availability. Under 24 hours requires manager approval.
- Company-initiated cancellation/change: notify customer, offer alternatives or a full refund.
- Manager rejection of a paid booking or 24-hour review expiry: recommended full Stripe refund, subject to final policy sign-off in section 3.3.
- A Stripe refund request and a Stripe-confirmed refund are distinct. Show REFUND_PENDING until provider confirmation; handle failures and partial refunds explicitly.
- All cancellation/refund decisions record actor, reason, policy, timestamps, amount, Stripe references and provider outcome.
- Booking status, payment status and refund status remain separate.

## 11. Shared consistency and reliability requirements

- All writes go through backend services and database transactions where multiple records are affected.
- Enforce state transitions centrally; reject illegal transitions.
- Use row locks/constraints or equivalent concurrency protection for slot reservations, duplicate active assignments and active work sessions.
- Use server timestamps; display in Europe/London local time.
- Use Decimal/fixed-point GBP values, never binary floating-point for money.
- Stripe webhook signature verification is mandatory in production; event processing is idempotent.
- Use secure private upload storage and per-request authorisation.
- Preserve an append-only audit trail for sensitive manager/staff actions.
- Real-time updates may use WebSocket/SSE or a maintainable alternative, with polling/reconnect fallback.
- If live delivery fails, dashboards recover by fetching authoritative current state.
- Never show success optimistically before backend confirmation.
- Use consistent error codes and response contracts across all dashboards.
- No dashboard may mutate lifecycle state by directly editing another dashboard's frontend data.

## 12. Repository and implementation audit requirements

Before coding, the agent must inspect and report:

1. Existing booking schema/status enums and all status writers/readers.
2. Existing payment tables, Stripe checkout/webhook/verification flow, refund support and legacy cash endpoints/schemas.
3. Current 10-minute slot hold and whether it is persisted and concurrency-safe.
4. Manager approval and 24-hour expiry support; identify any existing background scheduler.
5. Current manager assignment/auto-match logic and whether it stores assignment history or only overwrites `staff_id`.
6. Staff progress transitions, timer persistence and the bug that currently marks payment paid when cleaning is completed.
7. Customer/manager/staff route and frontend contracts.
8. Chat data model, participant authorisation, attachments and reassignment access revocation.
9. Notification schema/outbox/queue consistency and deduplication.
10. Audit event persistence and manager correction workflows.
11. Existing tests and baseline failures.

The audit must classify each feature as implemented, partially implemented, missing, unsafe or conflicting, with exact file/table/route references. Do not assume a feature works because a route or UI element exists.

## 13. End-to-end acceptance scenarios

The implementation is not ready until automated tests cover at least:

1. Customer starts checkout; 10-minute hold is visible and prevents another customer taking the slot.
2. Payment failure allows retry while hold is valid and does not confirm the booking.
3. Verified Stripe success consumes the hold, sets payment paid and booking pending review—not confirmed.
4. Duplicate/replayed Stripe webhook does not duplicate payment, booking, notification or audit records.
5. Manager approves paid pending-review booking; customer sees confirmed; booking enters dispatch.
6. Manager rejects paid booking; Stripe refund is initiated; customer sees refund pending until provider confirms.
7. Pending-review booking expires after exactly 24 hours, including overnight/weekends; rejection/refund process is idempotent.
8. A payment webhook arrives after slot-hold expiry; no double-booking occurs and payment is reconciled/refunded safely.
9. Manager assigns eligible cleaner; only that cleaner sees the assignment.
10. Cleaner accepts; manager sees accepted; customer sees accurate assignment information.
11. Cleaner declines or does not respond within two hours; manager is alerted; customer booking remains confirmed; cleaner access is revoked and dispatch allows reassignment.
12. Manager reassigns; assignment history is retained; new cleaner receives a new deadline; previous cleaner cannot access current private booking data.
13. Cleaner attempts overlapping/out-of-hours assignment or a forged status update; backend rejects it.
14. Cleaner progress events appear consistently in manager and customer timelines.
15. Timer starts/stops once, records server duration and is unaffected by client clock manipulation or duplicate requests.
16. Job completion saves evidence and never changes Stripe payment status.
17. Customer, active cleaner and manager can use the one authorised booking conversation; unauthorised users and previous cleaner are denied.
18. Notification retries do not create duplicate messages/alerts; deep links recheck authorisation.
19. Customer cancellation/reschedule rules and Stripe refunds match the approved policy.
20. Role-based IDOR tests prove one customer/cleaner cannot read another user's protected records.
21. Manager correction actions require reasons and create audit events.
22. Real-time disconnect/reconnect recovers from backend truth without stale or fabricated status.

## 14. Development boundaries

This is a planning document. It does not authorise immediate coding.

When implementation is later authorised:

- Start with a repository/schema/API audit and baseline tests.
- Work on a new feature branch; never work directly on `main`.
- Make small, reviewable phases and preserve existing functionality.
- Do not merge automatically. Run tests and obtain the project owner's approval before merging.
- Never claim tests passed unless they were actually run.
- Do not perform destructive database resets or drop existing tables.
- Keep all three dashboard specifications and this integration contract updated together when an approved decision changes.
- The final coding-agent prompt must instruct the agent to follow this contract and stop to report any genuinely unresolved business-policy conflict rather than inventing one.

**Primary outcome:** one secure, coherent cleaning-management product where customer, cleaner and manager always see consistent, authorised views of the same real booking, payment, assignment, job-progress and communication records.
