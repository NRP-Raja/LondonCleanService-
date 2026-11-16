# Manager Dashboard Redesign Specification

**Project:** CleanLondon  
**Repository:** `NRP-Raja/LondonCleanService-`  
**Specification branch:** `docs/manager-dashboard-redesign-spec`  
**Implementation target:** dedicated feature branch created from the latest `main`  
**Primary files currently involved:** `frontend/index.html`, `frontend/style.css`, `frontend/app.js`, and existing manager API routes in `app/main.py`

---

## 1. Purpose

Redesign the existing manager dashboard into a clear, practical **Operations Control Centre** for the CleanLondon cleaning-booking and dispatch platform.

Use the supplied Mayfair-style dashboard screenshot as visual inspiration for its hierarchy, spacing, KPI cards, clear status indicators and operational work queue. Do not copy its London fleet telemetry, borough hubs, GPS tracking, contract-retainer figures or audit metrics: those are not established features of this codebase.

The manager should be able to answer these questions quickly:

1. Which bookings need my attention?
2. Which bookings are unassigned and need a cleaner?
3. What is happening with today's jobs?
4. Which cleaners are available candidates for an assignment?
5. Which cleaner vetting records still need review?
6. What is the current booking value and operational workload?

The dashboard must prioritise real operational actions over decorative charts.

## 2. Existing implementation — inspect before changing

The current manager view is inside the authenticated dashboard wrapper in `frontend/index.html`:

- Section ID: `manager-dashboard-view`
- Current heading: “CleanLondon Executive Operations”
- Four KPI cards with IDs:
  - `kpi-daily-rev`
  - `kpi-monthly-rev`
  - `kpi-utilization`
  - `kpi-unassigned-count`
- Dispatch filters: `UNASSIGNED`, `TODAY`, `SCHEDULED`, `COMPLETED`
- Booking status selector and search input
- Cleaner schedule timeline: `manager-schedule-timeline`
- Booking table body: `manager-bookings-list`
- Cleaner vetting table body: `manager-staff-vetting-list`

The manager logic currently lives in the manager section of `frontend/app.js`, including:

- `loadManagerData()`
- `loadManagerKPIs()`
- `loadManagerBookings()`
- `loadManagerStaffVetting()`
- `renderManagerTimeline()`
- `autoMatchCleaner()`
- `manuallyReassign()`
- `updateStaffVetting()`
- `setManagerFilter()`
- `filterManagerBookings()`

Existing manager API routes in `app/main.py` include:

| Endpoint | Current purpose |
|---|---|
| `GET /api/manager/dashboard-stats` | KPI values and booking status counts |
| `GET /api/manager/bookings` | Manager booking list, optionally filtered by status |
| `GET /api/manager/staff` | Cleaner records and assignment-related information; accepts optional postcode/date |
| `POST /api/manager/bookings/{booking_id}/auto-match` | Automatically match an eligible cleaner |
| `POST /api/manager/bookings/{booking_id}/assign` | Manually assign a cleaner |
| `PATCH /api/manager/staff/{staff_id}/vetting` | Save cleaner vetting and activation decision |

These routes use manager-role authorization. Preserve that authorization and use the existing authenticated API helper.

**Important data semantics to preserve and clarify in the UI:**

- The current “Daily Revenue” query sums non-cancelled booking values scheduled for today; it does not establish that the money has been collected.
- The current “Gross Platform Revenue” value is summed across all non-cancelled bookings, not restricted to the current month, despite the current variable/label suggesting monthly revenue.
- The current cleaner-utilization percentage is based on distinct cleaners assigned to today's non-cancelled active bookings divided by the total cleaner count. Do not present it as precise working-time utilisation.
- Booking payment state is separate from booking status. Do not infer “paid” from “completed” or from booking value.
- The current booking list and cleaner vetting data are available. Do not invent GPS positions, live vehicle telemetry, route tracking, customer satisfaction scores, contract renewal rates or other unsupported data.

If a proposed label would be misleading based on the current API calculation, use an accurate label or explicitly identify the required backend change before implementing it.

## 3. Target visual direction

**Chosen style: modern, minimal SaaS — not a dense enterprise/fleet command-centre clone.**

Treat the reference screenshot as inspiration for information hierarchy only. The final interface should feel closer to a contemporary, understated SaaS product:

- Spacious layout with generous whitespace and a restrained number of components per screen.
- Quiet neutral surfaces (off-white/light grey canvas, white cards), thin low-contrast borders and very subtle shadows.
- Strong typography hierarchy with concise headings and muted supporting labels.
- Compact, consistent KPI cards; avoid oversized metric tiles and decorative gradients.
- A slim, unobtrusive sidebar with simple line icons and a clear active state.
- One primary accent colour (CleanLondon teal/green) used sparingly for primary actions and positive states.
- Semantic status colours used only when meaningful: amber for pending, red for blocked/failed, green/teal for successful.
- Simple tables with comfortable row spacing, light dividers, subtle hover states and uncluttered action menus.
- Small, purposeful charts only if they answer an operational question using real data. No chart just to fill space.
- Responsive behaviour that preserves the calm visual hierarchy on tablet and mobile.

Avoid the visual traits that make the reference feel overly busy: many competing badges, dense top-level counters, multiple strong accent colours, crowded toolbars, excessive borders, tiny uppercase text and large blocks of operational telemetry.

Do not add glassmorphism, heavy gradients, neon colours, oversized rounded cards or excessive animation. Aim for polished, understated, practical and easy to scan.

Create a polished, calm, desktop-first SaaS operations interface that remains usable on tablet and mobile.

### Overall shell

- Use a light neutral page background, white content surfaces and subtle borders/shadows.
- Use the existing CleanLondon brand palette and CSS variables where practical:
  - Primary green/teal for main actions and positive states.
  - Navy/dark slate for headings and navigation.
  - Muted grey for secondary text and separators.
  - Amber for pending/attention states.
  - Red/rose for urgent or failed states.
- Use consistent spacing, corner radii, icon sizing and typography.
- Avoid excessive gradients, oversized cards, decorative charts and dense visual clutter.
- Keep the existing application header/authentication shell compatible. If adding a manager-specific sidebar, ensure it appears only in the manager view and does not affect customer or staff navigation.
- Do not create a second global navigation system or duplicate the existing app shell.

### Manager navigation

If the current single manager view is split into in-page sections, use a compact manager sidebar or section navigation with these entries:

1. Overview
2. Bookings & Dispatch
3. Cleaner Vetting

Only make an item navigate to a working section/view. Do not add dead navigation links for features that do not yet exist.

Potential future areas such as shift management, customer management, payments, reports and messaging must not be shown as functional pages unless the relevant routes and workflows exist. They can be proposed separately as future work.

### Top bar

Include:

- Page title: **Operations Overview**
- Short contextual subtitle, such as “Manage bookings, cleaner assignments and daily operations”
- Refresh action
- Current manager identity only if available from the authenticated user state
- Optional date context using the user's local date

Do not invent a live-sync indicator unless the page actually polls or receives live updates.

## 4. Overview page layout

### 4.1 KPI summary

Use a compact responsive grid. Recommended cards:

1. **Bookings today** — only if the current API supplies an accurate today count; otherwise calculate from the loaded booking data without changing backend meaning.
2. **Unassigned bookings** — use `kpis.unassigned_jobs`.
3. **Cleaners assigned today** — show `active_cleaners_today` alongside `total_cleaners`.
4. **Booking value today** — label accurately; the current query sums non-cancelled bookings scheduled today and is not a collected-cash metric.
5. **Total booking value** — only use this label for the current all-time non-cancelled sum; do not call it monthly revenue.

Do not force five cards if the layout becomes cramped. Four well-designed cards are better than five misleading ones.

Requirements:

- Remove hard-coded sample values such as `£88.00`, `£336.50`, `50.0%`, and sample cleaner counts.
- While loading, show skeleton placeholders rather than fake figures.
- On API failure, show a compact error state and a retry action; do not leave stale placeholder numbers that look real.
- Format currency in GBP using a consistent two-decimal format.
- Use explanatory captions for percentages and totals so the meaning is clear.

### 4.2 Priority / attention panel

Place a clear action panel near the top of the page for work that needs manager attention:

- Unassigned scheduled bookings.
- Pending cleaner vetting (only if this can be reliably identified from returned staff records).
- Assignment or data-loading errors.

Each item should link or scroll to its relevant section. Use real counts from loaded data. Do not invent a 24-hour pending approval countdown unless the API exposes booking creation timestamps and the business rule is implemented and verified.

### 4.3 Dispatch queue

This is the most important operational section and should receive the strongest visual priority.

Provide:

- Section heading: **Bookings & Dispatch**
- Quick filters: Unassigned, Today, Scheduled, Completed
- Search by booking reference, customer or postcode
- Status selector using actual backend statuses
- Clear result count
- Refresh control
- Responsive table on desktop and stacked booking cards on narrow screens

Recommended booking information:

| Field | Display |
|---|---|
| Booking | Reference code |
| Customer | Customer name; show contact details only where appropriate |
| Location | Postcode; avoid unnecessarily exposing full residential address |
| Service | Service name |
| Schedule | Date and time slot |
| Value | GBP booking total |
| Payment | Payment status, only when returned by the API |
| Booking status | Clear status badge |
| Cleaner | Assigned cleaner or “Unassigned” |
| Actions | Auto-match / manual assignment where eligible |

Actions:

- Show **Auto-match** and **Assign** only when the booking is eligible and unassigned.
- Show the current assigned cleaner for assigned bookings.
- Preserve existing auto-match and manual assignment API behaviour.
- Use busy/disabled feedback while requests are pending.
- Confirm consequential actions where appropriate.
- Show clear success and failure feedback using the existing toast system.
- Refresh the affected booking/KPI data after a successful assignment.
- Do not add cancel, reschedule, approve or reject controls unless the corresponding manager workflow is confirmed to exist and is implemented end-to-end.

### 4.4 Cleaner schedule overview

Retain and improve the existing `manager-schedule-timeline` only if the data supports it.

- Group scheduled jobs by assigned cleaner.
- Show time slots and booking references with legible status colours.
- Include a clear empty state when no assigned jobs are in the current result set.
- Make horizontal overflow usable on smaller screens.
- Explain that the timeline is based on booking time slots; do not imply GPS or live location.
- Avoid a “45 min travel buffer” visual claim unless that buffer is actually calculated for each displayed transition. A static label must not imply that every gap has been validated.

### 4.5 Cleaner vetting

Retain the existing cleaner vetting workflow as a separate section below the dispatch queue or as a working in-page navigation destination.

Display:

- Cleaner name and email.
- DBS verification state.
- Right-to-work verification state.
- Vetting status.
- Clear Save action.

Requirements:

- Use accessible checkbox labels.
- Show pending/approved states with text as well as colour.
- Make the Save action busy while the PATCH request is running.
- Explain that approval activates the cleaner only when both DBS and right-to-work checks are verified, matching the current backend rule.
- Do not display document previews or claim documents have been verified unless the application actually stores and verifies them.
- Add loading, error and empty states.

## 5. Interaction and accessibility

- Use semantic headings, buttons, labels, tables and navigation.
- All controls must be keyboard accessible and have visible focus states.
- Provide accessible names for icon-only controls.
- Do not communicate booking states using colour alone.
- Maintain readable contrast and comfortable touch targets.
- On mobile, collapse the manager navigation and convert wide tables into readable cards or controlled horizontal scrolling.
- Keep filters usable without causing accidental full-page navigation.
- Preserve existing customer and staff dashboard behaviour.

## 6. Loading, errors and empty states

Every manager data region must have a clear state:

- Initial loading: skeletons.
- Successful data: real content.
- Empty results: helpful empty-state message.
- HTTP/API failure: understandable message and retry.
- Network failure: retryable error.
- Action pending: button busy state.
- Action success/failure: existing toast notification.

Do not silently return on failed API responses. Do not use hard-coded demo KPI values as fallback data.

## 7. Technical and architecture constraints

- Frontend remains native HTML, CSS and vanilla JavaScript / ES modules.
- Backend remains FastAPI and MySQL.
- Do not introduce React, Vue, a bundler, npm dependency or a new UI framework.
- Reuse existing CSS variables, icon library, toast implementation, `authFetch`, `setButtonBusy`, escaping helpers and manager API functions.
- Preserve the current role-based dashboard visibility and manager-only authorization.
- Keep customer and staff views unchanged.
- Do not weaken API authorization or expose private customer addresses/access instructions unnecessarily.
- Avoid putting large inline style blocks into HTML; add scoped styles to `frontend/style.css`.
- Keep DOM IDs and event handlers consistent, or update all references together.
- Avoid unrelated refactoring of the rest of the application.

## 8. Data/API gap handling

The redesign should use the existing manager endpoints first.

If the design requires information that the current API does not return:

1. Identify the exact missing field or endpoint.
2. Explain why it is needed.
3. Propose the smallest safe backend/API change.
4. Preserve existing response fields and consumers where possible.
5. Do not fabricate data in the frontend to make the design look complete.

Do not assume manager access to staff weekly availability, holidays, cash payment reconciliation, booking approval queues, customer messaging, GPS or live tracking unless the relevant manager-authorized API exists and its business rules are verified.

## 9. Suggested implementation sequence

1. Inspect the current manager HTML, CSS, JavaScript and API response shapes on the implementation branch.
2. Map existing DOM IDs and functions before editing.
3. Agree the final information hierarchy and responsive layout.
4. Redesign the manager page structure without changing unrelated role views.
5. Add scoped CSS for the manager workspace, KPI cards, dispatch queue, timeline and vetting section.
6. Update rendering and interactions to match the new structure.
7. Correct misleading KPI labels and remove hard-coded sample values.
8. Add loading, empty, error and retry states for every manager data region.
9. Verify the existing auto-match, manual assignment and vetting actions.
10. Run tests and inspect the complete diff before proposing a merge.

## 10. Acceptance checklist

### Visual quality
- [ ] Manager page has a consistent, professional operations-dashboard layout.
- [ ] Clear visual hierarchy: overview, priority items, dispatch queue, schedule and vetting.
- [ ] No clipped content or overlapping controls at desktop, tablet and mobile widths.
- [ ] Existing CleanLondon visual identity is retained.

### Real data
- [ ] KPI values come from API/database data, not hard-coded examples.
- [ ] KPI labels accurately describe the backend calculations.
- [ ] Booking status and payment status are not confused.
- [ ] No unsupported live maps, GPS, revenue collection or quality metrics are displayed.

### Functionality
- [ ] Manager booking list loads and filters correctly.
- [ ] Search works for the intended booking fields.
- [ ] Auto-match works for eligible unassigned bookings.
- [ ] Manual assignment works and refreshes the displayed data.
- [ ] Cleaner vetting saves and reflects the backend activation rule.
- [ ] Refresh works without duplicating requests or breaking filters.
- [ ] Customer and staff dashboards still work as before.

### Reliability and accessibility
- [ ] Every data region has loading, empty and error states.
- [ ] Failed requests show a retry path.
- [ ] Action buttons show busy state and recover after errors.
- [ ] Keyboard navigation and visible focus work.
- [ ] Status meaning is not conveyed by colour alone.
- [ ] No new browser-console errors.

## 11. Git workflow — mandatory

This document is on a documentation-only branch. Do not implement the redesign on this branch.

For implementation:

1. Fetch the latest remote `main`.
2. Check `git status`; if there are uncommitted changes, stop and ask before switching branches or touching them.
3. Create a new dedicated implementation branch from the latest `origin/main`, for example `feature/manager-dashboard-redesign`.
4. Make the manager redesign changes only on that branch.
5. Run relevant backend tests and manual frontend checks; record actual results.
6. Review the diff for unrelated changes and regressions.
7. Do not merge automatically. Present the change summary, test results and remaining risks, then wait for explicit user approval.
8. Merge through a Pull Request only after approval and successful verification.
9. Verify the merged `main` after merge.

Never commit directly to `main`, discard user work, or claim tests passed unless they were actually run.

## 12. Completion report

When implementation is complete, report:

- Files changed.
- Manager sections redesigned.
- Existing API endpoints reused.
- Any API gaps and whether they were changed.
- KPI label/data-semantic changes.
- Responsive and accessibility checks performed.
- Tests and manual checks actually run, with results.
- Remaining issues and risks.
- Feature branch and Pull Request link, if created.

**Definition of done:** the manager dashboard looks coherent and professional, every displayed number is grounded in real application data, existing manager workflows still work, and the changes are tested on a dedicated feature branch before any merge to `main`.
