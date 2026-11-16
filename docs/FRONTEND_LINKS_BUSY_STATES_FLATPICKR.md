# Frontend Reliability Fixes — Dead Links, Busy States and Flatpickr

**Repository:** `NRP-Raja/LondonCleanService-`  
**Target branch:** `refactor/mvc-project-structure`  
**Scope:** Follow-up frontend fixes for review items 4, 5 and 6.

## Goal

Remove dead `#` navigation, give every listed asynchronous action clear busy feedback, and add Flatpickr to the booking date field. Keep the changes focused and consistent with the existing frontend patterns.

## 4. Dead `#` links

There are four dead `#` links in `index.html`, at the reported lines 38, 47, 503 and 556. Line numbers may shift as earlier fixes are applied, so identify the elements by their purpose rather than relying only on the original line numbers.

### Required changes

- **Switch-form actions** (for example, switching between login and registration) must be real buttons:
  - Use `<button type="button">`.
  - Preserve their existing link-like visual styling.
  - Remove the placeholder `href="#"` because these controls do not navigate to a document location.
- **Brand/home link:** use a real `href="/"`.
- **Dashboard link:** use a real `href="/#dashboard"`.
- Route the brand and dashboard links through the existing navigation functions. Do not add a second, competing navigation system.
- Where an anchor is handled by an inline `onclick`, call `event.preventDefault()` before invoking the existing navigation function so the browser's default navigation does not race with the app's navigation.
- For the switch-form buttons, use their existing form-switching handlers; do not use `preventDefault()` as a substitute for changing the element to a button.

### Verification

- No switch-form control has `href="#"`.
- Login/register switching still works by mouse and keyboard.
- The brand link navigates to `/`.
- The dashboard link navigates to `/#dashboard`.
- No unwanted page jump to the top occurs.

## 5. Buttons without a busy state

Login, registration and booking already use busy states. Apply the same existing `setButtonBusy` pattern to the following asynchronous actions:

- Cancel booking
- Reschedule booking
- Submit review
- Auto-match
- Assign cleaner
- Advance booking/status
- Save working hours
- Save holiday
- Save vetting

### Required implementation pattern

For each action:

1. Capture the button that initiated the action (the existing handler's button reference, commonly `btn`).
2. Call `setButtonBusy(btn, true)` immediately before starting the asynchronous request.
3. Keep the existing request, response handling and success/error behaviour.
4. Reset the button in a `finally` block with `setButtonBusy(btn, false)`, so it is restored after both successful and failed requests.
5. Ensure the busy state is not left active if the request throws.

Use the existing helper's supported calling convention and preserve its current label/disabled behaviour. Do not create a second busy-state helper or change the already-working login, registration or booking flows unnecessarily.

### Verification

For every action listed above:

- The button visibly enters its busy state while the request is pending.
- Repeated clicks cannot submit duplicate requests while busy.
- The original button state is restored after success.
- The original button state is restored after an HTTP error or network exception.
- Existing success messages, error messages and action results still work.

## 6. Libraries from the project document

### Notyf

Do **not** add Notyf. The application already has its own toast implementation, so continue using that existing system and avoid introducing a duplicate notification library.

### Flatpickr

Add Flatpickr for the booking date field.

1. Add the Flatpickr stylesheet from cdnjs in the document `<head>`.
2. Add the Flatpickr JavaScript from cdnjs in the correct script-loading position so it is available before the application's initialisation code runs.
3. In the existing `DOMContentLoaded` handler, initialise Flatpickr on the booking date input at the point where the current default date is set.
4. Configure the display/input format for UK dates (`d/m/Y`).
5. Preserve the application's existing default-date behaviour and booking validation. Do not silently change the accepted backend date format: if the API currently expects a machine-readable date, use Flatpickr's date formatting or the existing conversion logic to keep the submitted value compatible.
6. Avoid initialising the same input more than once.

Use the established Flatpickr 4.x cdnjs distribution and keep the CSS and JS versions aligned. Do not add a package manager or build step.

### Verification

- Flatpickr loads without console errors.
- The booking date field opens the calendar picker.
- Dates are displayed in UK day/month/year format.
- The existing default date is still selected.
- The value sent to the booking API remains in the format the backend already expects.
- Booking validation and submission continue to work.

## Constraints

- Keep the frontend native HTML, CSS and ES modules; do not introduce React, Vue or build tooling.
- Reuse the existing navigation functions, `setButtonBusy` helper and toast system.
- Preserve existing API endpoints, payloads, role separation and backend contracts.
- Do not perform unrelated refactoring or rewrite entire functions when a focused change is sufficient.
- Work on `refactor/mvc-project-structure`; do not commit directly to `main`.

## Suggested implementation order

1. Fix the `innerHTML` issue (review item 2) first, as it is the security fix.
2. Replace the alerts and remove the override (review item 1).
3. Add error states and skeletons (review item 3).
4. Fix dead links and add busy states (review items 4 and 5).
5. Add Flatpickr (review item 6).

Items 1–3 are included here only to preserve the reviewer's requested sequence; their implementation details belong in their respective task guides.

## Completion report

When finished, report:

- Files changed.
- Which of the four dead links were converted to buttons or real navigation links.
- Which nine actions now use `setButtonBusy` with `finally` cleanup.
- Flatpickr version and UK date-format configuration.
- Tests or manual checks actually performed.
- Any remaining issue or limitation.

Do not claim a check passed unless it was run.
