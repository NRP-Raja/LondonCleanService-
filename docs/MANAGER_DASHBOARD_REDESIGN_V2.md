# CleanLondon Manager Dashboard — Redesign Specification v2

**Repository:** `NRP-Raja/LondonCleanService-`  
**Branch containing this specification:** `docs/manager-dashboard-redesign-v2`  
**Implementation branch:** create a fresh branch from the latest `origin/main`, e.g. `feature/manager-dashboard-minimal-saas`  
**Primary scope:** manager-only dashboard UI and its existing manager workflows.

---

## 1. The actual problem to solve

The current manager page still looks like the general website/dashboard shell with a large generic top navigation. The manager workspace is not given its own clear layout. The current page also contains too much visual noise and content that does not help a manager complete daily work.

This redesign must make a visible, structural change — not merely recolour the existing cards.

### Non-negotiable design outcome

**When a manager signs in, the manager experience must have a left-hand vertical sidebar with icons and labels. The current public/global horizontal navbar must not remain as the manager's primary navigation.**

The manager page should feel like a focused, modern, minimal SaaS admin product: calm, spacious, useful, and easy to scan.

The public landing page, customer dashboard and cleaner/staff dashboard must retain their own existing navigation and appearance. Apply the new shell only when the authenticated user's role is `manager`.

## 2. Verified current implementation on `main`

This specification was prepared after inspecting the latest `main` commit:

- Commit: `3a50b74072e0de8c29845375f461e3c020e0d006`
- Commit message: `merge: enable demo auth in development compose`

Relevant files and current structure:

### `frontend/index.html`

- The global `.demo-bar` is at the top of the document.
- The global `.navbar` contains the CleanLondon brand, public links (Services, Instant Quote, Reviews, Dashboard), account controls and Book a Clean.
- The manager section is `#manager-dashboard-view` (around lines 368–476).
- It currently has the heading “CleanLondon Executive Operations”.
- It currently displays four KPI cards with sample defaults:
  - `#kpi-daily-rev` initial value `£88.00`
  - `#kpi-monthly-rev` initial value `£336.50`
  - `#kpi-utilization` initial value `50.0%`
  - `#kpi-unassigned-count`
- The dispatch area includes quick filter pills, a search field, a status dropdown, a schedule timeline and a nine-column booking table.
- Cleaner vetting appears as a second large table underneath.

### `frontend/app.js`

The role routing is in `applyAuthenticatedView()`. It adds `.active` to `#manager-dashboard-view` when `state.user.role` is `manager`, then calls `loadManagerData()`.

Existing manager functions include:

- `loadManagerData()`
- `loadManagerKPIs()`
- `loadManagerBookings()`
- `loadManagerStaffVetting()`
- `renderManagerTimeline()`
- `setManagerFilter()`
- `filterManagerBookings()`
- `autoMatchCleaner()`
- `manuallyReassign()`
- `updateStaffVetting()`

Keep and reuse working API and business logic where possible. Inspect the complete current functions before editing; do not assume this document contains every implementation detail.

### `frontend/style.css`

The application uses CSS variables such as `--primary`, `--navy`, `--slate-bg`, `--card-bg`, `--text-main`, `--text-muted`, and `--border-color`. Reuse or refine these rather than creating an unrelated design system.

### Existing manager API routes in `app/main.py`

- `GET /api/manager/dashboard-stats`
- `GET /api/manager/bookings`
- `GET /api/manager/staff`
- `POST /api/manager/bookings/{booking_id}/auto-match`
- `POST /api/manager/bookings/{booking_id}/assign` (verify current frontend/backend assignment route naming before changing anything)
- `POST /api/manager/bookings/{booking_id}/reassign` (currently used by frontend)
- `PATCH /api/manager/staff/{staff_id}/vetting`

Preserve manager-only authorization and the current authenticated request helper.

---

## 3. Required visual layout

### Desktop shell

Use a two-part application layout:

1. **Left sidebar** — persistent vertical navigation, approximately 230–250px wide.
2. **Main workspace** — flexible content area occupying the remaining width.

The sidebar should be visually distinct from the content canvas but not heavy. Use a white or very lightly tinted surface, a subtle right border, and a small CleanLondon brand mark at the top.

The main workspace should use a very light neutral background, with content aligned to a sensible maximum width and consistent horizontal padding.

Do not leave the old public horizontal navbar visible above this manager workspace. Do not show two competing navigation systems.

### Sidebar structure

Show only sections that exist and work in this project:

1. **Overview** — icon: `fa-house` or `fa-gauge-high`
2. **Bookings & Dispatch** — icon: `fa-calendar-check` or `fa-clipboard-list`
3. **Cleaner Vetting** — icon: `fa-user-shield`

At the bottom of the sidebar, show the authenticated manager identity (only if available) and a sign-out action. A compact profile row is enough.

Navigation behaviour:

- Overview selects the overview section.
- Bookings & Dispatch scrolls to or selects the actual booking/dispatch section.
- Cleaner Vetting scrolls to or selects the actual vetting section.
- Active navigation item has a restrained teal/green accent, soft background and clear text/icon state.
- All navigation controls must be real buttons or links with working destinations and keyboard support.
- Do not show non-functional items such as Analytics, Reports, Payments, Customers, Messages, Settings, Fleet, Maps, or Live Dispatch as fake menu pages. Those features can be added only when implemented end-to-end.

### Manager top bar

Keep a small content header, not another full navigation bar:

- Page title: **Overview** (or the active section title).
- One short subtitle: “Your cleaning operations at a glance”.
- A small refresh button.
- Optional manager avatar/name if present in authenticated state.

Remove public/customer-specific calls to action such as “Book a Clean”, public Services/Reviews links and the large public navbar from the manager view.

Do not show a live indicator unless live polling or streaming is actually implemented. Do not show a search bar unless it is connected to a real search workflow.

### Demo controls

The global demo role-switcher bar is a development convenience, not a manager operational feature. It must not dominate the manager UI.

Prefer hiding `.demo-bar` while a manager session is active, without removing its functionality from development testing or changing how customer/staff demo preview works. If hiding it would make local role testing impossible, keep it behind an explicit development-only preview mode, not as a permanent manager toolbar.

---

## 4. Overview page — intentionally minimal

The overview should answer the manager's immediate questions without turning into an analytics wall.

### KPI cards: maximum four

Use a compact row/grid of no more than four cards:

1. **Unassigned bookings** — number of bookings that need a cleaner.
2. **Bookings today** — use a verified today count, if the existing response provides it or it can be accurately derived from loaded booking records.
3. **Cleaners assigned today** — show assigned cleaner count and total cleaner count only if both are reliably available.
4. **Booking value today** — optional. If shown, label it as booking value, not collected revenue.

Do not show “Staff Utilization” unless its calculation genuinely measures utilisation. The current `staff_utilization_pct` is based on distinct cleaners assigned to today's active bookings divided by total cleaners; it is not a measure of hours worked or actual capacity utilisation.

Do not show a monthly revenue card based on the current all-time total. The current `total_revenue_gbp` calculation is an all-time non-cancelled booking-value total, not monthly revenue.

Remove hard-coded placeholder numbers such as `£88.00`, `£336.50`, and `50.0%`. Use skeletons while loading and a clear error state if data fails. Never present sample values as live data.

If reliable data is unavailable for a suggested card, omit the card. Do not add a new API endpoint just to fill empty space.

### Priority panel

Below the KPI row, show a small **Needs attention** panel only when there is something actionable, such as unassigned bookings or pending vetting records.

- Use real counts.
- Clicking an item should navigate to the relevant existing section and apply a relevant filter if supported.
- Hide the panel or show a quiet “You're all caught up” message when there are no items.
- Do not create fictional urgency, deadlines or notifications.

### Today's work / booking queue

The booking queue is the core of the manager workspace and should be the largest useful component on the overview.

Use a clean table/card with:
- Booking reference
- Customer name
- Postcode (avoid exposing full residential address unnecessarily)
- Service
- Date and time slot
- Assigned cleaner or “Unassigned”
- Booking status
- Booking value only if useful
- One contextual action

Keep filters compact:
- All
- Unassigned
- Today
- Scheduled
- Completed

Keep the existing status filter/search only if each control works. Avoid multiple redundant filter bars and excessive badge colours.

Actions:
- Unassigned eligible booking: Auto-match and/or Assign.
- Assigned booking: show cleaner name; provide reassignment only if current flow supports it.
- Do not add unimplemented cancel, reschedule, approve/reject or payment controls.
- Use existing busy-state helper and toast system.
- Refresh affected data after successful actions.

On mobile, use compact booking cards or a controlled horizontal table scroll with clear labels.

### Cleaner vetting

Cleaner vetting is a secondary management task. It should be a distinct section reached from the left sidebar, not another large unrelated block competing with the booking queue.

Use a calm table with:
- Cleaner name and email
- DBS check
- Right-to-work check
- Vetting state
- Save action

Keep the existing backend rule: cleaner activation depends on both DBS and right-to-work verification. Use explicit text labels as well as status colours. Save should have a busy state and clear error/success feedback.

### Schedule timeline

The existing schedule timeline may remain as a compact optional “Today's assignments” panel only if it helps the manager understand assigned jobs. It must not dominate the overview.

Remove unsupported claims such as “45 min TfL buffer after each job”. The current frontend renders that as a static label; it is not evidence of a calculated journey buffer.

Do not add a map, GPS view, live fleet, route optimisation or travel-time metrics. Those are not verified features of the current manager API.

---

## 5. What must be removed or simplified

The redesign is not complete if these elements remain in the manager view:

- The global horizontal public navigation as the manager's primary menu.
- The large “CleanLondon Executive Operations” heading and promotional copy.
- Public landing-page links and the “Book a Clean” CTA.
- The oversized dispatch console title and multiple competing filter controls.
- Hard-coded example KPI values.
- Misleading “Live tracking”, “Gross Platform Revenue” or “Staff Utilization” claims.
- Static “45 min TfL buffer” text.
- Unnecessary icon tiles, coloured cards, gradients and decorative charts.
- Duplicate navigation or duplicated account/profile controls.
- Placeholder menu items for functionality that does not exist.

The visual result should be simpler than the existing page, not just a rearranged copy of every current component.

---

## 6. Implementation guidance

### Role-specific shell without affecting other roles

The global `.navbar` and `.demo-bar` are outside `#manager-dashboard-view` in the current HTML. Use a role-specific state/class on the document root (for example, `body.manager-mode`) from the existing role-routing code.

When role is manager:
- Add the manager-mode class.
- Hide the public horizontal `.navbar` and, by default, the demo role bar.
- Display the manager sidebar and manager content shell.
- Ensure the manager layout begins at the top of the viewport without an empty gap from hidden navigation.

When role is customer, staff or unauthenticated:
- Remove manager-mode.
- Restore the existing public navbar/demo bar behaviour.
- Do not alter customer/staff layouts.

On sign-out or role switch, always clear the previous role's layout class so the manager shell cannot leak into another role.

### HTML

- Keep the manager shell scoped to `#manager-dashboard-view`.
- Use semantic `<aside>`, `<nav>`, `<main>`, `<section>`, headings and buttons.
- Use unique IDs and update all JS references if elements are moved.
- Do not duplicate an existing ID.
- Do not create dead `href="#" ` navigation.
- Keep all manager-only content within the manager view.

### CSS

- Add manager-specific styles in `frontend/style.css`, scoped under `body.manager-mode` or `#manager-dashboard-view`.
- Do not globally restyle shared buttons, tables, forms or navigation in ways that affect customer/staff.
- Use the existing Plus Jakarta Sans font and existing CSS variables where appropriate.
- Suggested layout: fixed/sticky sidebar on desktop; main workspace with max-width and generous padding.
- At tablet/mobile widths, collapse the sidebar into a compact top/overlay navigation with an accessible menu button. Do not allow the sidebar to cover the booking content permanently.
- Provide visible focus states, semantic labels, keyboard operation and reduced-motion support.
- Keep shadows subtle and borders low-contrast. Avoid gradients and animation except small purposeful transitions.

### JavaScript

- Update `applyAuthenticatedView()` and unauthenticated/sign-out/role-switch flows to set and clear manager-mode correctly.
- Keep existing manager API calls and business rules.
- Implement sidebar navigation to actual page sections.
- Ensure refresh, filters, assignment and vetting continue working.
- Do not use fake KPI fallback values.
- Keep the existing error/skeleton behaviour; improve it if necessary, but do not silently swallow failures.
- Ensure loading one manager section does not trigger duplicate requests unnecessarily.

### Backend

Do not change backend behaviour just for visual redesign. Only propose a small API change if a required, meaningful manager data point cannot be derived from current responses. Explain the need before implementing a new endpoint or changing response contracts.

---

## 7. Acceptance criteria — must be visually verified

### Manager navigation and shell
- [ ] Manager login displays a left-hand vertical sidebar with icons and text labels.
- [ ] The public horizontal navbar is hidden in manager mode.
- [ ] Public Services/Reviews/Book a Clean navigation is not visible in manager mode.
- [ ] Sidebar has only Overview, Bookings & Dispatch, Cleaner Vetting (plus manager profile/sign-out).
- [ ] Each sidebar item navigates to a real section.
- [ ] The manager shell is cleared on sign-out and does not affect customer/staff views.

### Design quality
- [ ] The page looks visibly different from the old manager page.
- [ ] The visual style is modern, minimal SaaS, not a dense enterprise dashboard.
- [ ] There is generous whitespace and a restrained teal/neutral palette.
- [ ] KPI cards are compact and limited to four.
- [ ] No decorative or unsupported analytics widgets.
- [ ] No fake data or misleading KPI labels.
- [ ] No unwanted top navigation, duplicate controls or placeholder menu items.

### Functionality
- [ ] Manager overview loads real values.
- [ ] Booking search and filters work.
- [ ] Auto-match and manual assignment work as before.
- [ ] Cleaner vetting can be saved.
- [ ] Refresh works.
- [ ] Error, empty, loading and busy states are present.
- [ ] Customer and staff dashboards are unchanged.

### Responsive and accessibility
- [ ] Desktop sidebar remains usable and content is not cramped.
- [ ] Tablet/mobile navigation is accessible and does not obscure content.
- [ ] All controls are keyboard accessible with visible focus.
- [ ] Status is communicated with text, not colour alone.
- [ ] No horizontal overflow except intentional table scrolling.
- [ ] No new console errors.

**Do not mark the redesign complete based only on code edits. Capture or inspect the manager page at desktop and mobile widths and verify that the left sidebar is actually visible and the old top navbar is gone.**

---

## 8. Mandatory Git workflow

This is a documentation-only branch. Do not implement the redesign on this branch.

For implementation:

1. Fetch latest `origin/main`.
2. Check `git status`. If there are uncommitted changes, stop and ask; never discard, reset or stash the user's work without permission.
3. Create a fresh branch from latest `origin/main`: `feature/manager-dashboard-minimal-saas`.
4. Make all redesign changes only on that feature branch.
5. Run relevant tests and inspect the actual manager UI in a browser.
6. Check customer and staff dashboards for regressions.
7. Review the diff and report actual test results.
8. Do not merge automatically. Wait for explicit user approval.
9. Merge through a Pull Request only after approval and successful verification.
10. Verify `main` after merge.

Never commit directly to `main`.

## 9. Codex completion report

Report:
- Files changed.
- How the manager-only left sidebar was implemented.
- Confirmation that the global navbar is hidden only for manager role.
- Screenshots or clear visual verification at desktop and mobile sizes.
- Which existing manager workflows were tested.
- Which API endpoints were reused and whether any API changes were necessary.
- Test results (only tests actually run).
- Any remaining issue.
- Feature branch and Pull Request URL, if created.

**Definition of done:** a manager signs in and immediately sees a clean SaaS workspace with a left icon sidebar, a minimal overview and only the operational tools the manager actually needs. The old global top menu is absent in manager mode, existing booking/assignment/vetting features work, and customer/staff/public pages remain unchanged.
