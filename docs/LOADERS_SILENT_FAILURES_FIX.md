# Fix: Loaders fail silently

**Scope:** Customer, Staff, and Manager booking/job loaders  
**Target functions:** `loadCustomerBookings`, `loadStaffJobs`, and `loadManagerBookings`  
**Repository:** `NRP-Raja/LondonCleanService-`  
**Branch:** `refactor/mvc-project-structure`  
**Type:** Frontend reliability and loading-state UX  
**Guidance only:** Follow the project's AI collaboration rule. Do not write or replace full function implementations unless the user explicitly asks for that specific code.

---

## 1. Problem

All three loaders currently contain the equivalent of:

```js
if (!res.ok) return;
```

When an API request returns a non-2xx response, the loader exits without updating the UI. The page can remain stuck showing **“Loading...”** indefinitely.

Network failures are another case to handle: if `fetch()` rejects because the backend is unavailable or the connection drops, the loader must not leave the interface in its loading state.

## 2. Required outcome

Apply the same predictable loading lifecycle independently to each of the three loaders:

1. **Loading:** show skeleton rows while the request is in progress.
2. **Success:** render the returned bookings/jobs and remove the skeleton rows.
3. **HTTP error:** show a clear error message and a **Retry** button.
4. **Network error:** catch the rejected request, show the same recoverable error state, and provide **Retry**.
5. **Retry:** run the relevant loader again, show skeleton rows while retrying, and remove the previous error state.

Do not silently return from a failed response.

## 3. Implementation scope

### A. Customer — `loadCustomerBookings`

- Replace the plain “Loading...” row with skeleton rows.
- Check the HTTP response status before treating the request as successful.
- On a non-OK response, transition to the customer bookings error state.
- Catch network/request errors and show the same recoverable state.
- Add a Retry button that calls `loadCustomerBookings` again.
- On success, render the customer bookings normally and clear any previous error UI.

### B. Staff — `loadStaffJobs`

- Replace the plain “Loading...” row with skeleton rows.
- Check the HTTP response status before rendering jobs.
- Handle both non-OK HTTP responses and network errors.
- Show a staff-specific, understandable error message with a Retry button.
- Retry by calling `loadStaffJobs` again.
- On success, render the staff job cards/list normally and clear the error UI.

### C. Manager — `loadManagerBookings`

- Replace the plain “Loading...” row with skeleton rows.
- Check the HTTP response status before updating the manager bookings list.
- Handle both non-OK HTTP responses and network errors.
- Show a manager bookings error state with a Retry button.
- Retry by calling `loadManagerBookings` again.
- On success, render the manager bookings normally and clear the error UI.

Keep the three states independent. A failure in one role's loader must not leave another role's dashboard stuck or overwrite its content.

## 4. Skeleton row styling

Add **one reusable CSS class** for the loading skeleton rows, with a shimmer animation.

Requirements:

- Use the same class for customer bookings, staff jobs, and manager bookings.
- Make the skeleton shape fit the relevant row/card layout without displaying misleading real booking details.
- Use a subtle shimmer animation that is visible but not distracting.
- Keep the styling compatible with the existing frontend CSS and responsive layouts.
- Respect reduced-motion preferences so the animation can be disabled for users who request reduced motion.
- Remove skeleton elements when loading finishes, whether the request succeeds or fails.

Do not add a separate shimmer class for each dashboard.

## 5. Error and retry behaviour

- Use plain, user-friendly UK English. Example: **“We couldn't load your bookings. Please try again.”**
- Do not expose raw server exception details or internal API information in the page.
- Keep the Retry button within the relevant list/card area.
- Disable or otherwise prevent accidental repeated submissions while a retry is already in progress.
- On retry, return to the loading skeleton state and hide the previous error message.
- Ensure the retry action is bound after the error UI is rendered, and does not create duplicate event handlers.
- If the project already has a shared API/error-handling helper, follow its established conventions rather than introducing an unrelated pattern.

## 6. Project constraints

- Keep the frontend as native HTML, CSS, and ES6 JavaScript modules. Do not introduce React, Vue, Vite, Webpack, or a build step.
- Preserve the existing role separation and API endpoints.
- Keep the current visual design and responsive behaviour consistent with the CleanLondon dashboards.
- Do not change backend routes or API response contracts for this frontend-only fix.
- Avoid unrelated refactoring.
- Follow the repository's existing Git workflow and make changes on the feature/refactor branch, not directly on `main`.

## 7. Verification checklist

### Customer loader
- [ ] With the API responding successfully, customer bookings render and skeletons disappear.
- [ ] With a non-2xx response, a readable error and Retry button appear.
- [ ] With the backend stopped or network unavailable, the error state appears instead of endless loading.
- [ ] Retry sends a new request and restores the loading skeletons.

### Staff loader
- [ ] Successful requests render staff jobs and remove skeletons.
- [ ] Non-2xx responses show a staff error state and Retry button.
- [ ] Network failures are caught and do not leave “Loading...” on screen.
- [ ] Retry reloads the staff jobs successfully after the API becomes available.

### Manager loader
- [ ] Successful requests render manager bookings and remove skeletons.
- [ ] Non-2xx responses show a manager error state and Retry button.
- [ ] Network failures are caught and do not leave “Loading...” on screen.
- [ ] Retry reloads manager bookings successfully after the API becomes available.

### Shared UI and regression checks
- [ ] All three views use the same single skeleton CSS class.
- [ ] Skeleton shimmer is disabled when reduced motion is requested.
- [ ] Skeletons and error UI are removed/replaced correctly after success.
- [ ] Retry does not create duplicate requests or duplicate event handlers.
- [ ] Existing booking filters, role permissions, and dashboard interactions still work.
- [ ] No plain “Loading...” placeholder remains as the only response to a failed request.

## 8. Completion summary

When finished, report:

1. Which files were changed.
2. How each loader handles HTTP and network errors.
3. Where the shared skeleton class and shimmer animation are defined.
4. Which verification steps were run and their results.
5. Any remaining issue that could not be verified.

**Do not claim tests passed unless they were actually run.**
