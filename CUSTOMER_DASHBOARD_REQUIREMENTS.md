# Customer Dashboard Requirements

**Project:** LondonCleaningService / CleanLondon  
**Document:** Customer Dashboard Functional and Technical Specification  
**Status:** Approved requirements baseline for implementation planning  
**Prepared:** 20 November 2026  
**Reference implementation branch:** feature/backend-modular-refactor  
**Scope:** Customer-facing web experience, supporting APIs, database changes, integrations, security and acceptance tests

---

## 1. Purpose

Build a complete, reliable customer self-service experience for the cleaning booking platform. Customers must be able to discover services, obtain a clear price, book and pay, manage appointments, track progress, communicate with the assigned cleaner, access receipts, manage their account and obtain support.

This is a functional product specification, not a visual-only dashboard redesign. Every visible control must connect to a real, authorised workflow. Do not add decorative controls, fake data, dead-end pages or placeholder messages such as “This area is not available yet”.

The implementation must reuse and improve existing backend capabilities where appropriate. Do not duplicate existing business logic or introduce parallel booking/payment flows without first understanding the existing service layer.

## 2. Product principles

1. **Customer self-service:** customers can complete normal tasks without contacting the manager.
2. **Accurate information:** booking, payment, availability and cleaner details must come from the backend, not hard-coded frontend state.
3. **Payment integrity:** a booking is not confirmed merely because the customer clicked Pay or returned to a success page. Confirmation requires verified payment-provider evidence.
4. **Privacy by default:** customers can access only their own profile, bookings, addresses, payments, notifications, messages and support cases.
5. **Responsive experience:** desktop, tablet and mobile must all be fully usable.
6. **Operational consistency:** manager and cleaner actions must update the same booking records and customer timeline.
7. **Resilience:** retries, duplicate requests, interrupted checkout and temporary connection failures must not create duplicate bookings or payments.
8. **Accessibility:** use semantic HTML, keyboard support, visible focus, readable contrast, labels and accessible status announcements.
9. **No feature creep:** implement the agreed scope below. Do not add loyalty points, favourites, promotional gamification or unrelated features unless separately approved.

## 3. Repository baseline and verified existing implementation

The repository was inspected on 20 November 2026.

- The reference branch, feature/backend-modular-refactor, was 13 commits ahead of main and 0 commits behind main at inspection time.
- The branch includes a modular FastAPI structure: app/core, app/database, app/routes, app/schemas, app/services and app/utils.
- BACKEND_ARCHITECTURE.md describes app/main.py as the lightweight application composition entry point.
- The frontend is currently a vanilla JavaScript single-page experience in frontend/index.html and frontend/app.js.
- Existing customer-facing API capabilities include registration, login, current-user lookup, service listing, quote calculation, customer booking list, booking creation, cancellation, rescheduling, reviews, Stripe checkout/session verification and a basic notification-list endpoint.
- Existing booking creation currently creates a SCHEDULED booking with payment_status PENDING before the separate Stripe checkout flow. This does not meet the newly agreed pay-during-booking and confirm-only-after-payment workflow.
- Existing cancellation logic applies a 50% late-cancellation fee and refunds the other 50% inside 24 hours. This conflicts with the approved target policy in this document.
- Existing Stripe checkout code explicitly configures card payments. Apple Pay, Google Pay and other methods must be enabled only where supported by the Stripe account, currency, domain, device and provider configuration.
- Existing receipt download code creates a plain-text file, not a PDF receipt.
- The notification route currently exposes a read/list operation only. The notification service and database migration definitions must be reconciled before extending it; their current column/status naming is not fully consistent.
- The existing booking schema includes service, property, bedroom/bathroom, pet, deep-clean, eco-product, address, access, date and time-slot fields. Booking creation already uses an idempotency key and encrypts access notes at rest.
- The existing booking API requires an authenticated customer or manager. Guest booking is therefore a new capability, not an existing completed workflow.

These observations are a starting point for implementation, not proof that all existing code paths are production-ready. The coding agent must inspect the current branch and run the actual test suite before changing code.

## 4. Customer dashboard information architecture

### 4.1 Navigation

Implement the same destinations across device sizes:

- Home
- My Bookings
- New Booking
- Payments & Receipts
- Messages
- Reviews
- Support
- Notifications
- Profile & Security

Navigation behaviour:

- Desktop: left sidebar with icons and text labels.
- Desktop sidebar: customer can collapse or expand it. Persist the preference for that customer/browser in a safe, non-sensitive preference store.
- Mobile: fixed or safely inset bottom navigation with the most important destinations. Less frequently used destinations must remain accessible through an accessible More/Profile destination; do not hide functionality.
- Tablet: responsive layout based on available width.
- Preserve the active destination and sensible browser history/navigation behaviour.
- Respect safe-area insets on mobile devices.
- Do not copy the manager sidebar or expose manager/staff navigation to customers.

### 4.2 Personalised home page

The home page must prioritise the most relevant action:

- If the customer has an upcoming booking, show the next appointment, its current status, date/time, service, assigned cleaner (if assigned), payment state and a link to booking details.
- If no upcoming booking exists, make Book a Cleaning the primary action.
- Also show concise booking overview, recent payment activity, unread notifications and unread messages where applicable.
- Provide quick actions for New Booking, My Bookings, Payments and Support.
- Do not display fabricated metrics, fake reviews or demo customer data to a real authenticated user.
- Handle loading, empty, partial-data and error states clearly.

### 4.3 Booking list

Show one combined booking list, newest appointment first, with optional basic filters:

- All bookings (default)
- Upcoming
- Completed
- Cancelled

Each item must show booking reference, service, appointment date/time, booking status, payment status and a link to details. Actions must depend on the booking state and cancellation/rescheduling policy. Do not show actions that the backend would reject.

The list must support pagination or sensible incremental loading if the number of bookings becomes large. Empty states must provide a clear New Booking action.

### 4.4 Booking detail page

Use one detailed booking page with clearly grouped sections and a progress timeline near the top.

Display, where applicable:

- Booking reference and creation date
- Service and selected extras
- Property details
- Appointment date and time
- Address, shown only to the authenticated customer and authorised operational staff
- Estimated/confirmed duration and final price
- Booking progress timeline
- Assigned cleaner profile: name, profile photo and assigned role
- Payment status, transaction reference and receipt
- Customer special instructions and uploaded property photos
- Booking-specific conversation with the assigned cleaner
- Review status and review action after completion
- Available reschedule/cancel actions and applicable policy explanation

Before a cleaner is assigned, show “Cleaner not yet assigned”. Reveal the basic cleaner profile immediately after manager assignment. If the manager reassigns the job, update the customer-visible assignment and notify the customer.

Do not expose a cleaner's private phone number, home address, personal email or other unnecessary personal information.

## 5. Customer registration, login and guest access

### 5.1 Registered customers

Support:

- Customer registration using name, email, phone and password.
- Email verification before full account access.
- Login and logout.
- Secure password recovery using a unique, expiring, one-time reset link sent to the verified email address.
- Session management described in section 12.
- Existing Google sign-in may remain if configured and securely verified.

Public registration must always assign the customer role on the server. Never trust a role supplied by the browser.

### 5.2 Guest booking

Allow both registered and guest checkout.

Guest booking fields:

- Full name
- Email address
- Phone number
- Booking and property details required for the service

Guest users must verify their email before accessing private booking information. Provide:

- Booking reference
- Secure email tracking link
- Email verification before revealing private booking details
- Payment confirmation and important booking updates by email

The tracking link must use a cryptographically secure, high-entropy token. Store only a hash of the token where practical. Apply expiry/rotation and rate limits. Do not rely on an easily guessable booking reference as authentication. Verify access without revealing whether an email or booking reference exists to unauthorised callers.

### 5.3 Convert guest booking to an account

Allow a guest to create a password and convert to a registered customer account after email verification. Link the guest's existing bookings to the new account only after proving control of the verified email and completing server-side ownership checks. Prevent account takeover or linking bookings based only on a submitted reference code.

## 6. Booking creation wizard

Use a clear, step-by-step wizard with progress indication, back/continue controls, validation and a final review.

Recommended steps:

1. Select cleaning service.
2. Enter property details: property type/size, bedrooms and bathrooms.
3. Select available extras and relevant options, including pet-related information and cleaning products where applicable.
4. Select a saved address or enter a new address.
5. Select appointment date and available time slot.
6. Add special instructions and optionally upload property photos.
7. Review the booking and server-calculated estimated price.
8. Continue to secure payment and confirm after verified payment.

Requirements:

- Show the estimated price before the customer submits/pays.
- Price calculations must be performed or verified by the backend. Never trust a client-submitted total.
- Show itemised service/extras/adjustments where the pricing model supports it.
- Clearly identify the final payable amount in GBP.
- Validate all inputs server-side and client-side.
- Save incomplete progress as a customer draft.
- Drafts expire after 30 days.
- Saving a draft must not reserve an appointment slot.
- Customers can resume or delete their own drafts.
- Do not expose another customer's draft.

### 6.1 Availability

- Customers can book up to 30 days ahead.
- The customer chooses a date and sees only genuinely available time slots.
- Unavailable slots are visibly disabled and cannot be submitted.
- Availability must account for existing bookings, cleaner capacity, staff schedules, service duration, travel/operational buffers and manager-defined availability rules.
- Availability must be rechecked on the server when the customer begins checkout and again when the booking is committed.
- Prevent double-booking using database transactions/locking or an equivalent concurrency-safe reservation mechanism. Frontend checks alone are insufficient.
- Display dates and times in the service's local timezone (London), and store timestamps consistently in the database.

### 6.2 Saved addresses

Customers can:

- Save multiple addresses.
- Add, edit and delete their own addresses.
- Set a default address.
- Select an address during booking.
- Enter a one-time address without saving it.

Validate and normalise addresses/postcodes server-side. Never allow one customer to read or modify another customer's saved addresses.

### 6.3 Special instructions and property photos

- Allow optional free-text instructions for parking, access, pets and cleaning preferences.
- Make clear that instructions are visible to the manager and assigned cleaner.
- Encrypt sensitive access instructions at rest using the existing encryption approach or an approved equivalent.
- Allow optional photo uploads for relevant rooms/areas.
- Photos are visible only to the customer, manager and assigned cleaner/authorised operational roles.
- Validate actual file content/type, size and dimensions; do not trust filename or browser MIME type.
- Store uploads outside executable/public web paths, use non-guessable identifiers and enforce authorisation on every download.
- Apply malware scanning where supported, image processing/metadata stripping where appropriate, and retention/deletion rules.
- Do not permit arbitrary executable or document uploads in the booking photo field.

## 7. Payment and booking confirmation

### 7.1 Payment timing and methods

Payment takes place during the booking wizard before manager approval. A successful Stripe payment means **payment is paid**, not that the booking is yet manager-confirmed. The booking enters `PENDING_REVIEW` after trusted Stripe verification and becomes `CONFIRMED` only when a manager approves it.

**First-release payment policy: Stripe only.** All customer payments must be processed through the configured Stripe integration. The checkout may offer card and Stripe-supported wallet/payment methods (such as Apple Pay or Google Pay) only when enabled and eligible in the Stripe account and checkout configuration. Do not offer cash, bank transfer, manual/off-platform payment, or a second payment provider in this release. Do not promise a Stripe method unavailable for the current device, region, domain or provider account.

- Use provider-hosted or provider-secure payment collection.
- Never store raw card numbers, CVCs or full payment credentials in the application database.
- Optional saved payment methods must use Stripe customer/payment-method references and provider-managed setup flows. Customers can remove a saved method.
- Use GBP and validate the payable amount against the server-side booking quote. Stripe is the sole payment provider for the first release; no cash collection or manual payment marking is permitted.
- Use idempotency keys for checkout/session creation and payment fulfilment.

### 7.2 Ten-minute slot reservation

When the customer enters checkout:

- Create a temporary reservation for the selected slot.
- The reservation lasts 10 minutes.
- Display a visible countdown, for example 09:45 remaining.
- Keep the slot unavailable to other customers during the valid reservation.
- If payment fails, show a clear error and allow retry or another payment method while the reservation remains valid.
- If the 10-minute reservation expires, release the slot and require the customer to select a new available slot.
- Do not keep a slot reserved merely because a customer has an incomplete draft.
- Handle late provider webhooks safely: if the 10-minute reservation expired, do not silently double-book. If the slot cannot be safely reacquired, initiate a full Stripe refund and notify the customer; record the payment/refund outcome for manager review.

### 7.3 Confirmation authority

A booking is eligible for manager review only after the backend has verified successful payment through Stripe's trusted server-side event/session verification. Successful payment changes the payment lifecycle to `PAID` and the booking lifecycle to `PENDING_REVIEW`; it does not itself set the booking to `CONFIRMED`. The manager's approval action is the only normal transition from `PENDING_REVIEW` to `CONFIRMED`.

- Do not confirm based solely on a browser redirect, query parameter, client callback or screenshot.
- Verify webhook signature in production.
- Make webhook handling idempotent and safe against duplicate/out-of-order events.
- Persist payment and booking state changes transactionally.
- Send a payment-received / awaiting-manager-review update after successful verification. Send booking-confirmed only after manager approval.
- If payment remains pending, show a pending payment state and do not tell the customer that the appointment is confirmed. After payment succeeds, show 'Payment received — awaiting manager approval' until the manager approves.
- Keep booking status and payment status as separate concepts.

### 7.4 Payment failure and expiry

- Keep the booking unconfirmed while payment is unsuccessful or pending.
- Allow retry during the 10-minute reservation.
- Explain when the slot reservation expires.
- Release the slot after expiry.
- Keep an auditable record of payment attempts and provider references without storing sensitive card data.
- Avoid duplicate charges and duplicate booking creation.

## 8. Cancellation, rescheduling and company changes

### 8.1 Customer cancellation policy

Approved customer policy:

- Cancellation with at least 24 hours' notice: full refund of the amount paid, returned through Stripe to the original payment method.
- Cancellation with less than 24 hours' notice: no automatic refund.
- A customer may submit a late cancellation request for manager review/exception handling; the system must not automatically issue a refund in this case. Any approved exception is refunded through Stripe.
- Explain the applicable policy and expected refund before the customer confirms cancellation.
- Do not cancel jobs already completed or already in progress through the ordinary customer cancellation action.
- Record cancellation reason, actor, timestamp, policy applied, refund decision and provider refund reference.
- Show refund status separately (for example requested, processing, refunded, rejected/failed).
- Notify the customer when the cancellation and any refund state changes.

This approved policy replaces the current repository implementation that automatically retains a 50% fee and refunds 50% for cancellations inside 24 hours. Do not silently preserve the old rule.

### 8.2 Rescheduling

- At least 24 hours before the appointment: customer can reschedule through self-service, subject to live availability.
- Less than 24 hours before the appointment: customer submits a reschedule request for manager approval.
- Show the customer the current appointment and proposed replacement slot.
- Do not change the confirmed appointment until the new slot is validated and the operation succeeds.
- Prevent double-booking and ensure the old slot is released only when the new slot is safely committed.
- Notify the customer of approval/rejection and show the final appointment time.
- Keep an audit history of previous and new dates/times.

### 8.3 Company-initiated changes

If the company must change or cancel an appointment:

- Notify the customer in-app and by email.
- Explain the reason in clear language.
- Offer available alternative slots.
- Allow the customer to accept an alternative or request a full refund.
- Do not silently move the customer to a different appointment.
- Record the manager/authorised actor and decision in the audit log.

## 9. Booking tracking and cleaner communication

### 9.1 Live progress

Show a customer-friendly timeline based on authoritative backend events. Show the booking/payment stages before the cleaner's operational stages. At minimum map the relevant states to:

1. Payment received — awaiting manager approval
2. Booking confirmed (after manager approval)
3. Cleaner assigned
4. Cleaner accepted (optional customer-facing detail)
5. Cleaner on the way
6. Cleaner arrived (optional customer-facing detail)
7. Cleaning started
8. Cleaning completed

The timeline must update automatically without requiring a page refresh. Use an appropriate real-time mechanism (WebSocket, Server-Sent Events or another maintainable option) and provide a polling/reconnect fallback. Do not invent live location tracking if the backend/device does not provide it.

Show the latest update time and handle disconnected/reconnecting states gracefully. Every status transition must be authorised, validated and audited.

### 9.2 Cleaner profile

After assignment, display only:

- Cleaner name
- Profile photo
- Assigned role

Before assignment, display “Cleaner not yet assigned”. Update the information after reassignment. Do not expose private phone numbers or personal contact details.

### 9.3 Booking-specific messaging

Implement a modern chat interface, with a separate conversation for each booking.

- Access chat from the relevant booking details.
- Show message bubbles, sender, timestamp, delivery/read state where supported and conversation history.
- Customer can message the assigned cleaner; the assigned cleaner can reply.
- Enforce booking membership and role authorisation on every request.
- Do not allow a customer to message an unassigned cleaner or another customer's cleaner.
- Manager/support access, if needed for operational escalation, must be role-controlled and auditable.
- Preserve conversation history according to the platform retention policy.
- Do not expose personal phone numbers or move the conversation to private channels.

### 9.4 Chat photo attachments

Allow photos only.

- Validate image content, dimensions and size server-side.
- Use secure private storage and authorised download URLs/endpoints.
- Strip unnecessary image metadata where appropriate.
- Do not allow HTML, scripts, executable files or arbitrary documents.
- Show an image preview and accessible alternative text/caption where available.

## 10. Recurring bookings

Support one-time bookings and recurring schedules:

- Weekly
- Fortnightly
- Monthly

Customers can manage a recurring schedule:

- Pause
- Resume
- Change schedule
- Cancel future schedule
- Skip one individual appointment

Support both scheduling modes:

- Fixed day/time for each occurrence.
- Flexible time selection for individual occurrences.

Every occurrence must be checked against current availability. Do not silently substitute a different slot. If an occurrence cannot be scheduled, clearly show the affected date and ask the customer to choose another slot or skip that occurrence.

Each occurrence is a separate booking with its own reference, status, payment and receipt. Charge separately for each appointment. Do not automatically charge a saved payment method for future occurrences. Each occurrence must go through its own customer-authorised payment flow.

## 11. Payments, receipts and reviews

### 11.1 Payment history

Provide a customer payment history linked to the relevant booking. Show:

- Booking reference
- Service
- Payment date
- Amount and currency
- Payment method label (never full card details)
- Payment status
- Refund status, if applicable
- Provider transaction/reference identifier where safe to display

Customers must see only their own payment records.

### 11.2 Receipts

After verified payment:

- Generate a professional PDF receipt.
- Email the receipt to the verified customer email.
- Make the receipt viewable/downloadable from the dashboard.
- Include business identity/contact details from configured company settings, receipt number, booking reference, service, appointment details, amount, tax/VAT fields only where legally/configurationally applicable, payment date, payment method label and transaction status.
- Do not invent VAT registration details or tax claims.
- Ensure receipt access is authorised and does not expose another customer's information.
- Keep a receipt record/audit trail; regenerated PDFs must represent the original transaction accurately.

### 11.3 Reviews

- Allow one customer review per completed booking.
- Review includes a 1–5 star rating and written comment.
- Review action becomes available only after the booking is completed.
- Prevent duplicate reviews and validate comment length/content server-side.
- Show the customer's submitted review and allow only the explicitly supported edit/moderation workflow.
- Do not permit reviews for cancelled, rejected, unpaid or incomplete bookings.

## 12. Customer profile and security

### 12.1 Profile management

Customers can update their own:

- Full name
- Phone number
- Verified email through a secure email-change verification flow
- Password
- Saved addresses
- Notification preferences

Validate and normalise data server-side. Require re-authentication for sensitive changes such as password, email and payment-method changes.

### 12.2 Advanced session management

Provide a security section where customers can:

- View active sessions/devices and recent login activity.
- See useful session metadata such as device/browser label, approximate location only if safely available, last active time and creation time.
- Log out an individual session.
- Log out all other sessions.
- Change password.
- Understand session expiry.

Implement server-side session identifiers/revocation. A stateless JWT that cannot be revoked is not sufficient for the requested remote logout behaviour unless backed by a revocation/session strategy. Never store raw passwords or session secrets in logs. Avoid overstating device/location accuracy.

### 12.3 Account deletion request

Customers submit an account deletion request; this is not an instant destructive delete.

- Confirm the request and explain that a manager will review it.
- Manager can approve, reject or request clarification, with reason and audit history.
- Preserve records that must be retained for legal, accounting, fraud-prevention or legitimate business requirements.
- Delete or anonymise data that is no longer required, according to an approved retention policy.
- Revoke active sessions when the request is approved and account access is closed.
- Notify the customer of the decision and completion.
- Do not cascade-delete financial/booking records that must legally be retained.

## 13. Notifications

### 13.1 Notification centre

Provide:

- Bell icon with unread count.
- Dropdown containing recent notifications.
- Dedicated full notification history page.
- Mark one notification as read.
- Mark all as read.
- Deep links to the relevant booking, payment, message or support case.
- Pagination or incremental loading for long histories.

### 13.2 Channels and preferences

Use in-app and email notifications for important transactional events. Use browser push for new chat messages when the customer grants browser permission.

Notification categories:

- Booking confirmation and important booking changes.
- Appointment reminders.
- Payment and refund updates.
- Cleaner messages.
- Reviews/feedback.
- Optional marketing communications, disabled by default and subject to consent.

Professional default behaviour:

- Essential booking/payment/security notifications cannot be fully disabled where required to deliver the service or meet legal obligations. Use the appropriate necessary channel and clearly explain this.
- Appointment reminders are configurable.
- Chat browser push is opt-in and can be disabled.
- In-app notification history remains available for relevant account events.
- Marketing is separate, optional and off by default.
- Do not send email for every chat message by default; the approved chat notification choice is in-app plus browser push.
- If browser permission is denied or unsupported, in-app notifications continue to work.
- Avoid duplicate browser notifications while the customer is actively viewing the relevant conversation.

Implement browser push with explicit permission, secure service-worker handling, subscription lifecycle management and unsubscribe support. Do not request notification permission on first page load; ask contextually when the customer enables browser notifications or uses messaging.

### 13.3 Notification reliability

Use a consistent notification event/outbox design with delivery status, retries, deduplication, channel, recipient, read state and deep link. Reconcile the existing notification table and queue utility before adding features: the current migration and notification utility appear to use different recipient/status column conventions. Add tests for schema compatibility and delivery failure handling.

## 14. Customer support

Provide three support routes:

1. In-app support request/case.
2. Phone contact using the business's configured public support number.
3. FAQ/help content.

In-app support requests should capture a subject, description, optional related booking and attachments only where explicitly supported. Customers can view their own case status and manager replies/updates. Do not invent a phone number; read it from business configuration.

## 15. Data model and backend design guidance

The coding agent must inspect the live schema and existing services before designing migrations. Reuse existing entities where suitable. The following are logical capabilities, not a mandate to create one table per bullet:

- Customer profile and verification state.
- Customer addresses.
- Booking drafts.
- Booking records and status history.
- Slot reservations with expiry and concurrency protection.
- Recurring schedule parent and individual booking occurrences.
- Payment attempts/transactions/refunds and provider identifiers.
- Receipts.
- Customer notification preferences.
- Notification events/outbox/delivery records.
- Browser push subscriptions.
- Booking conversations, messages and private image attachments.
- Support cases and case messages.
- Customer session/device records and revocation state.
- Account deletion requests and decisions.
- Audit records for sensitive actions.

Database requirements:

- Use foreign keys and indexes for ownership, status, booking date, notification history and conversation lookup.
- Use transactions for booking confirmation, slot reservation, payment fulfilment, rescheduling and cancellation/refund state changes.
- Add migrations incrementally and make them safe for existing Docker/MySQL volumes.
- Never drop or recreate production tables to implement this work.
- Do not store raw payment credentials, passwords, reset tokens, guest access tokens or push secrets in plaintext.
- Keep booking status, payment status, refund status and slot reservation status distinct.
- Use UTC timestamps for persisted event times where appropriate and convert to London local time for customer presentation.

## 16. API design guidance

The existing endpoints should be reviewed and extended rather than duplicated. Existing relevant routes include:

- Authentication: POST /api/auth/register, POST /api/auth/login, GET /api/auth/me
- Services/pricing: GET /api/services, POST /api/pricing/calculate
- Bookings: POST /api/bookings, GET /api/bookings/my, POST /api/bookings/{id}/cancel, POST /api/bookings/{id}/reschedule, POST /api/bookings/{id}/review
- Payments: POST /api/payments/create-checkout-session, POST /api/payments/webhook, GET /api/payments/session/{session_id}/verify
- Notifications: GET /api/notifications/my

New API capabilities will be required for some or all of the following:

- Email verification and resend verification.
- Password reset request and completion.
- Profile update and secure email change.
- Customer session listing/revocation.
- Account deletion request/status.
- Saved address CRUD.
- Booking draft CRUD.
- Availability search and temporary slot reservation/release.
- Checkout creation integrated with a temporary slot reservation.
- Payment history and authorised PDF receipt access.
- Refund status.
- Guest booking creation, email verification and secure guest tracking.
- Recurring schedule CRUD and individual occurrence management.
- Booking progress event retrieval/streaming.
- Cleaner assignment details with customer-safe fields only.
- Booking conversation list, message history, send message and photo upload.
- Notification preferences, mark-read and mark-all-read.
- Browser push subscription registration/removal.
- Support case creation and customer case history.

Endpoint names and payloads are implementation decisions. Keep routes REST-consistent, use Pydantic schemas, enforce role/ownership checks, validate server-side, document OpenAPI and avoid leaking internal errors. Every state-changing operation must be authorised and audited where appropriate.

## 17. Security and privacy requirements

Apply the existing security audit principles and verify them against every new route.

- Enforce HTTPS in production.
- Keep secrets in environment variables/secret management; never commit API keys.
- Hash passwords using a modern password-hashing algorithm with safe parameters.
- Use parameterised SQL queries.
- Validate and constrain all request fields, uploads and identifiers.
- Escape untrusted content on output and prevent stored/reflected XSS.
- Apply CSRF protection where cookie-based authentication is used; use secure SameSite/HttpOnly/Secure cookie settings where applicable.
- Restrict CORS to configured trusted origins.
- Apply security headers and sensible content security policy.
- Rate-limit registration, login, email verification, password reset, guest lookup, booking, checkout, messaging and uploads.
- Prevent IDOR by checking customer ownership on every booking, receipt, address, message, attachment, support case, notification and session request.
- Use secure, single-use, expiring verification/reset/guest access tokens.
- Do not reveal whether an email address or booking reference exists in public recovery/guest flows.
- Verify Stripe webhooks and make payment fulfilment idempotent.
- Use least-privilege access for cleaner, manager and customer roles.
- Keep sensitive access notes encrypted and expose them only to authorised operational roles.
- Log security-relevant events without logging passwords, tokens, card details or private message content unnecessarily.
- Apply retention and deletion rules to profile data, chat, photos, notifications and audit records.
- Ensure production builds do not expose demo role switching or test credentials. Demo authentication must remain disabled in production.

## 18. Non-functional requirements

- Responsive and usable at common mobile, tablet and desktop widths.
- Keyboard navigable and screen-reader friendly.
- Clear loading, empty, success, validation, retry and error states.
- No silent failure or fake success messages.
- Avoid full-page reloads for ordinary dashboard navigation where the existing SPA architecture supports it.
- Paginate potentially large lists.
- Use efficient database queries and avoid N+1 query patterns.
- Real-time features must reconnect and fall back safely.
- Uploads and PDFs must not block the main application thread for excessive periods.
- Preserve existing public landing page, quote flow, staff dashboard and manager dashboard functionality.
- Keep UI components and business logic maintainable; do not add all new functionality to one large JavaScript file or FastAPI entry point.

## 19. Implementation phases

Implement in small, independently testable stages:

**Phase 0 – Discovery and baseline**
- Confirm current branch and working tree.
- Read existing route/service/schema/database/frontend code.
- Run the existing tests and record the baseline.
- Map current customer UI controls to real endpoints.
- Identify migrations and conflicts before editing.

**Phase 1 – Customer dashboard shell**
- Responsive sidebar/bottom navigation.
- Personalised home page.
- Combined booking list and basic filters.
- Detailed booking view.
- Loading/empty/error states and accessibility.

**Phase 2 – Account and customer data**
- Profile management.
- Saved addresses.
- Email verification.
- Password reset.
- Session management.
- Account deletion requests.

**Phase 3 – Booking wizard and availability**
- Step-by-step wizard.
- Quote and itemised price.
- Draft save/resume/expiry.
- Availability API and 30-day window.
- Special instructions and secure photo uploads.
- Concurrency-safe slot reservation.

**Phase 4 – Checkout and payment integrity**
- Ten-minute slot hold and visible countdown.
- Retry/expiry handling.
- Supported Stripe payment methods.
- Webhook verification/idempotency.
- Instant confirmation only after verified payment.
- Payment history and PDF/email receipts.

**Phase 5 – Booking management**
- Customer booking list/details.
- Cancellation/refund policy update.
- Rescheduling rules.
- Company-initiated changes and alternatives.
- Recurring schedule and individual occurrences.

**Phase 6 – Tracking, messaging and notifications**
- Customer-safe cleaner profile.
- Live booking progress with fallback.
- Booking-specific chat and photo-only attachments.
- Notification centre and preferences.
- Browser push for chat messages.

**Phase 7 – Reviews and support**
- Post-completion review flow.
- In-app support cases.
- FAQ and configured phone support.

**Phase 8 – Regression, security and release readiness**
- Full regression suite.
- Cross-role and cross-device tests.
- Payment/webhook tests.
- Security and privacy tests.
- Accessibility review.
- Operational documentation and release checklist.

The coding agent may adjust phase order when dependencies require it, but must explain the reason and preserve the acceptance criteria.

## 20. Acceptance criteria

The customer dashboard is not complete until all applicable criteria pass:

### Navigation and dashboard
- Desktop sidebar expands/collapses and remembers preference.
- Mobile bottom navigation works and does not cover content.
- Home page prioritises the next appointment or New Booking appropriately.
- No customer route exposes manager/staff-only content.

### Booking
- Customer can complete the wizard with valid data and see a server-calculated price before payment.
- Customer can save, resume and delete a draft; drafts expire after 30 days.
- Availability only shows valid slots up to 30 days ahead.
- Concurrent attempts cannot book the same capacity/slot.
- Special instructions and photos are securely stored and visible only to authorised roles.

### Checkout
- Slot is reserved for 10 minutes with a visible countdown.
- Failed payment allows retry while the reservation remains valid.
- Expired reservation is released.
- Duplicate checkout/webhook requests do not duplicate bookings or charges.
- Booking confirmation occurs only after trusted provider verification.
- Payment methods shown are actually enabled for the provider/account.

### Booking management
- Combined booking list and Upcoming/Completed/Cancelled filters work.
- Booking detail shows accurate timeline, payment state and assigned cleaner.
- Full refund applies at 24 hours or more.
- Less-than-24-hour cancellation does not automatically refund; late requests follow manager review.
- Self-service rescheduling works at least 24 hours ahead; late requests require manager approval.
- Company-initiated changes notify the customer and offer alternatives or a full refund.

### Account and guest access
- Email verification is required before full private account access.
- Password reset links are single-use and expire.
- Guest booking is possible without a registered account.
- Guest private tracking requires secure email verification and a secure token/reference flow.
- Guest bookings can be linked to a new account only after verified ownership.
- Customers can revoke sessions and request account deletion.

### Messaging and notifications
- Chat is scoped to a booking and only available to authorised participants.
- Only valid image attachments can be uploaded.
- New chat messages create in-app notifications and browser push when permission exists.
- Notification centre supports unread count, history and read actions.
- Preferences are respected without suppressing essential transactional/security messages.

### Payments, receipts and reviews
- Customer sees only their own payments and receipts.
- PDF receipt can be downloaded and is emailed after successful payment.
- Refund status is visible.
- One 1–5 star written review can be submitted only for a completed booking.

### Quality and security
- Existing manager, staff and public website workflows continue to work.
- All new API routes have authentication/authorisation and server-side validation appropriate to their use.
- No known critical/high security issue is introduced.
- Tests cover ownership/IDOR, role escalation, invalid state transitions, payment verification, slot races, expiry, upload validation and notification permissions.
- No placeholder controls or fake success states remain in the delivered customer dashboard.

## 21. Git and coding-agent execution rules

These rules are mandatory:

1. Do not work directly on main.
2. Before implementation, fetch the latest remote state and create a new feature branch from the correct up-to-date integration branch. Do not assume this documentation branch is the coding branch.
3. Keep changes focused and commit in logical stages.
4. Before each stage, inspect the relevant code and tests. Do not rewrite working modules blindly.
5. Run targeted tests after each stage and the full regression suite before declaring completion.
6. Do not merge automatically. Merge only after all required tests pass and the user explicitly approves.
7. Never use destructive database resets, drop production tables, remove existing features or overwrite user work.
8. Additive migrations must be backward-compatible with existing data and Docker/MySQL volumes.
9. If an existing implementation conflicts with this specification, document the conflict and implement the approved target behaviour with tests.
10. Report exactly what changed, files touched, migrations added, tests actually run and results. Never claim a test passed if it was not run.
11. If a requirement cannot be implemented safely because of missing provider configuration, credentials, business data or external service support, explain the blocker and provide a safe fallback rather than faking success.

## 22. Out of scope unless separately approved

- Loyalty points, rewards and referral schemes.
- Customer favourites or promotional gamification.
- Automatic recurring charges for future appointments.
- Direct sharing of customer/cleaner personal phone numbers.
- Unverified live GPS tracking.
- Storing card numbers or CVCs in the application database.
- Guest access based only on a predictable booking reference.
- Automatic late-cancellation refunds inside 24 hours.
- Marketing notifications enabled by default.

---

**Definition of done:** the customer dashboard is a connected, secure, responsive self-service product backed by real APIs and tested business workflows—not merely a redesigned collection of frontend screens.


## 15. First-release payment policy clarification

Stripe is the sole payment provider for the first release. Customers pay through Stripe checkout/payment flows before booking confirmation. Only verified Stripe events/session results can mark a payment successful. Do not support cash, bank transfer, manual/off-platform payment collection, or a second provider. Refunds must be initiated through Stripe and their provider-confirmed status must be reflected separately from booking status. Managers may review Stripe transactions and authorised refund outcomes; staff cannot view sensitive payment details, initiate refunds, or alter payment status. This policy overrides any older cash-payment wording elsewhere in the repository or earlier specifications.


## Cross-dashboard lifecycle clarification

The authoritative cross-dashboard workflow is defined in `CROSS_DASHBOARD_INTEGRATION.md`. In particular:

- A verified Stripe payment moves the booking to `PENDING_REVIEW`; it does not automatically confirm the appointment.
- The manager must approve the paid booking within 24 hours. Approval moves it to `CONFIRMED`.
- If the manager rejects the booking or the 24-hour review deadline expires, the booking is rejected and a full Stripe refund is initiated. The customer is told the refund is processing; the dashboard must not claim it is complete until Stripe confirms it.
- Cleaner assignment is made only after manager approval. Cleaner acceptance is a separate assignment state and does not change the booking's confirmed state.
- Booking lifecycle, payment lifecycle, assignment lifecycle, job progress and temporary slot reservation are independent state dimensions.
