// ==========================================================
// CleanLondon Vanilla JS Client
// Authentication, State Management & Role-Based SPA Routing
// ==========================================================

const API_BASE = ""; // Relative to FastAPI host
const TOKEN_KEY = "cleanlondon_token";

let state = {
    token: null,
    user: null, // Populated from /api/auth/me or login
    quote: {
        postcode: "SW1A 1AA",
        service_id: 1,
        property_type: "Flat/Apartment",
        bedrooms: 2,
        bathrooms: 1,
        has_pets: false,
        deep_clean: false,
        eco_products: true,
        calculatedPrice: 58.50,
        estimatedHours: 3.0
    },
    activeJobForMap: null,
    managerBookings: []
};

function showToast(message, type = "info") {
    const region = document.getElementById("toast-region");
    if (!region) return;
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<i class="fa-solid ${type === "success" ? "fa-circle-check" : type === "error" ? "fa-circle-exclamation" : "fa-circle-info"}"></i><span>${message}</span>`;
    region.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add("visible"));
    setTimeout(() => {
        toast.classList.remove("visible");
        setTimeout(() => toast.remove(), 220);
    }, 4200);
}

window.alert = (message) => showToast(String(message), /error|failed|could not/i.test(String(message)) ? "error" : "info");

function setButtonBusy(button, busy, label = "Working...") {
    if (!button) return;
    if (busy) {
        button.dataset.originalLabel = button.innerHTML;
        button.disabled = true;
        button.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> ${label}`;
    } else {
        button.disabled = false;
        button.innerHTML = button.dataset.originalLabel || button.innerHTML;
    }
}

// ==========================================================
// 1. INITIALIZATION & AUTH STATE ROUTER
// ==========================================================
document.addEventListener("DOMContentLoaded", async () => {
    // Set default booking date to tomorrow
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const dateInput = document.getElementById("book-date");
    if (dateInput) {
        dateInput.value = tomorrow.toISOString().split("T")[0];
    }

    // Initialize instant quote calculations for public view
    recalculateQuote();

    // Check authentication state on page load
    await checkAuthState();
    restoreRoute();
});

/**
 * JWT Expiration Inspector
 */
function isJwtExpired(token) {
    if (!token) return true;
    try {
        const parts = token.split(".");
        if (parts.length !== 3) return true;
        const payloadJson = atob(parts[1].replace(/-/g, "+").replace(/_/g, "/"));
        const payload = JSON.parse(payloadJson);
        if (!payload.exp) return false;
        return (Date.now() / 1000) > payload.exp;
    } catch (e) {
        return true;
    }
}

/**
 * Graceful Session Expiration Handler
 * Automatically wipes localStorage, resets UI views, displays friendly prompt, and opens login dialog
 */
function handleSessionExpired(customMsg) {
    console.warn("CleanLondon session expired. Resetting authentication state.");
    localStorage.removeItem(TOKEN_KEY);
    state.token = null;
    state.user = null;

    // Reset active role preview button highlights
    document.querySelectorAll(".role-btn").forEach(btn => btn.classList.remove("active"));

    // Switch view back to Public Landing Page
    applyUnauthenticatedView();

    const msg = customMsg || "Your CleanLondon session has expired for your security. Please log in again.";

    // Show friendly session expiration banner in login modal
    const alertEl = document.getElementById("login-error-alert");
    if (alertEl) {
        alertEl.textContent = msg;
        alertEl.classList.remove("hidden");
    }

    // Automatically open login modal for instant re-authentication
    openLoginModal();
}

/**
 * Centralized Authenticated Fetch Wrapper
 * Intercepts all API calls: adds Bearer token, checks local expiration, and catches 401 responses
 */
async function authFetch(url, options = {}) {
    options.headers = options.headers || {};
    if (state.token) {
        if (isJwtExpired(state.token)) {
            handleSessionExpired("Your session has expired. Please sign in to continue.");
            throw new Error("Session expired");
        }
        options.headers["Authorization"] = `Bearer ${state.token}`;
    }

    const response = await fetch(url, options);
    if (response.status === 401) {
        console.warn("API returned 401 Unauthorized for:", url);
        handleSessionExpired("Your session has expired for your security. Please log in again.");
    }
    return response;
}

/**
 * Core Auth State Verifier:
 * Inspects localStorage for JWT token. Checks expiry and validates against /api/auth/me.
 * Controls whether the Public Landing Page or Private Dashboard is shown.
 */
async function checkAuthState() {
    const storedToken = localStorage.getItem(TOKEN_KEY);

    if (!storedToken) {
        // --- UNAUTHENTICATED STATE ---
        state.token = null;
        state.user = null;
        applyUnauthenticatedView();
        return;
    }

    // Pre-flight check: token expiration
    if (isJwtExpired(storedToken)) {
        handleSessionExpired("Your previous session has expired. Please sign in to access your CleanLondon account.");
        return;
    }

    // Validate token with backend
    try {
        const response = await fetch(`${API_BASE}/api/auth/me`, {
            headers: { "Authorization": `Bearer ${storedToken}` }
        });

        if (response.ok) {
            const data = await response.json();
            state.token = storedToken;
            state.user = data.user;
            applyAuthenticatedView();
        } else if (response.status === 401) {
            handleSessionExpired("Your previous session has expired. Please sign in to access your CleanLondon account.");
        } else {
            localStorage.removeItem(TOKEN_KEY);
            state.token = null;
            state.user = null;
            applyUnauthenticatedView();
        }
    } catch (err) {
        console.error("Network or auth check error:", err);
        applyUnauthenticatedView();
    }
}

/**
 * Configures DOM for Unauthenticated Guests
 */
function applyUnauthenticatedView() {
    // 1. View Management: Show Landing Page, Hide Private Dashboard
    document.getElementById("landing-view").classList.add("active");
    document.getElementById("dashboard-view").classList.add("hidden");

    // Hide any dashboard sub-views
    document.getElementById("customer-dashboard-view").classList.remove("active");
    document.getElementById("staff-dashboard-view").classList.remove("active");
    document.getElementById("manager-dashboard-view").classList.remove("active");

    // 2. Navigation Elements
    document.getElementById("nav-unauth-actions").classList.remove("hidden");
    document.getElementById("nav-auth-actions").classList.add("hidden");
    document.getElementById("nav-dashboard-link").classList.add("hidden");

    // 3. Top Demo Bar Display
    const userDisplay = document.getElementById("current-user-display");
    if (userDisplay) {
        userDisplay.textContent = "Status: Guest (Unauthenticated)";
        userDisplay.style.color = "#94a3b8";
    }

    // Clear active highlight on role switcher
    document.querySelectorAll(".role-btn").forEach(btn => btn.classList.remove("active"));
}

/**
 * Configures DOM for Authenticated Users (Customer, Staff, Manager)
 */
function applyAuthenticatedView() {
    if (!state.user) return;

    const user = state.user;
    const role = user.role.toLowerCase();

    // 1. View Management: Hide Public Landing Page, Reveal Private Dashboard Wrapper
    document.getElementById("landing-view").classList.remove("active");
    document.getElementById("dashboard-view").classList.remove("hidden");

    // 2. Navigation Bar Updates
    document.getElementById("nav-unauth-actions").classList.add("hidden");
    document.getElementById("nav-auth-actions").classList.remove("hidden");
    document.getElementById("nav-dashboard-link").classList.remove("hidden");

    const firstName = user.full_name ? user.full_name.split(" ")[0] : "User";
    document.getElementById("navbar-user-greeting").innerHTML = `<i class="fa-solid fa-circle-user"></i> Hi, ${firstName}!`;

    // 3. Top Demo Bar Status Display
    const userDisplay = document.getElementById("current-user-display");
    if (userDisplay) {
        const roleLabel = role.charAt(0).toUpperCase() + role.slice(1);
        userDisplay.textContent = `Logged in: ${user.full_name} (${roleLabel})`;
        userDisplay.style.color = "#38bdf8";
    }

    // Highlight active role preview button if matched
    document.querySelectorAll(".role-btn").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.role === role);
    });

    // 4. Role-Specific Sub-Dashboard Routing
    document.getElementById("customer-dashboard-view").classList.remove("active");
    document.getElementById("staff-dashboard-view").classList.remove("active");
    document.getElementById("manager-dashboard-view").classList.remove("active");

    if (role === "customer") {
        document.getElementById("customer-dashboard-view").classList.add("active");
        const greetingEl = document.getElementById("customer-greeting-name");
        if (greetingEl) greetingEl.textContent = firstName;
        loadCustomerBookings();
    } else if (role === "staff") {
        document.getElementById("staff-dashboard-view").classList.add("active");
        const staffNameEl = document.getElementById("staff-profile-name");
        if (staffNameEl) staffNameEl.textContent = user.full_name;
        loadStaffJobs();
        loadStaffSchedule();
        loadStaffEarnings();
    } else if (role === "manager") {
        document.getElementById("manager-dashboard-view").classList.add("active");
        loadManagerData();
    }

    window.scrollTo({ top: 0, behavior: "smooth" });
}

// ==========================================================
// 2. AUTHENTICATION FORMS & SIGN OUT
// ==========================================================

/**
 * Handle Manual Email/Password Login
 */
async function handleManualLogin(e) {
    e.preventDefault();
    const email = document.getElementById("login-email").value.trim();
    const password = document.getElementById("login-password").value;
    const errorAlert = document.getElementById("login-error-alert");
    const submitBtn = document.getElementById("login-submit-btn");

    errorAlert.classList.add("hidden");
    submitBtn.disabled = true;
    submitBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Signing in...`;

    try {
        const response = await fetch(`${API_BASE}/api/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password })
        });

        const data = await response.json();

        if (response.ok) {
            // Save JWT in localStorage
            localStorage.setItem(TOKEN_KEY, data.access_token);
            closeLoginModal();
            await checkAuthState();
        } else {
            errorAlert.textContent = data.detail || "Invalid email or password.";
            errorAlert.classList.remove("hidden");
        }
    } catch (err) {
        errorAlert.textContent = "Unable to connect to server. Please verify your connection.";
        errorAlert.classList.remove("hidden");
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = `Sign In <i class="fa-solid fa-arrow-right"></i>`;
    }
}

/**
 * Handle Account Registration
 */
async function handleRegistration(e) {
    e.preventDefault();
    const fullName = document.getElementById("register-name").value.trim();
    const email = document.getElementById("register-email").value.trim();
    const phone = document.getElementById("register-phone").value.trim();
    const password = document.getElementById("register-password").value;
    const role = document.getElementById("register-role").value || "customer";
    const errorAlert = document.getElementById("register-error-alert");
    const submitBtn = document.getElementById("register-submit-btn");

    errorAlert.classList.add("hidden");
    submitBtn.disabled = true;
    submitBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Creating account...`;

    try {
        const response = await fetch(`${API_BASE}/api/auth/register`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                full_name: fullName,
                email: email,
                phone: phone,
                password: password,
                role: role
            })
        });

        const data = await response.json();

        if (response.ok) {
            // Automatically log in by storing returned JWT
            localStorage.setItem(TOKEN_KEY, data.access_token);
            closeRegisterModal();
            await checkAuthState();
        } else {
            errorAlert.textContent = data.detail || "Registration failed. Please check inputs.";
            errorAlert.classList.remove("hidden");
        }
    } catch (err) {
        errorAlert.textContent = "Server error during registration. Please try again.";
        errorAlert.classList.remove("hidden");
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = `Create Account & Log In <i class="fa-solid fa-check"></i>`;
    }
}

/**
 * Sign Out: Clears session and redirects to public landing page
 */
function handleSignOut() {
    localStorage.removeItem(TOKEN_KEY);
    state.token = null;
    state.user = null;
    setRoute("home", null, true);

    // Reset customer bookings list in DOM
    const customerList = document.getElementById("customer-bookings-list");
    if (customerList) customerList.innerHTML = "";

    // Re-evaluate auth state to bring user to Public Landing Page
    checkAuthState();
}

/**
 * Google OAuth 2.0 Sign-In Prototype (Mock Fallback)
 */
async function triggerGoogleSignIn() {
    try {
        const res = await fetch(`${API_BASE}/api/auth/google/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                id_token: "google-oauth-token-" + Date.now(),
                email: "london.client@gmail.com",
                name: "London Google User"
            })
        });
        const data = await res.json();
        if (res.ok) {
            localStorage.setItem(TOKEN_KEY, data.access_token);
            closeLoginModal();
            closeRegisterModal();
            await checkAuthState();
        } else {
            alert(`Google login error: ${data.detail}`);
        }
    } catch (err) {
        alert("Google OAuth prototype could not connect.");
    }
}

// ==========================================================
// 3. STEP D: DEMO ROLE SWITCHER (ONE-CLICK PREVIEW)
// ==========================================================
/**
 * Injects a valid JWT for the chosen demo account directly into localStorage
 * and forcefully re-evaluates the authentication state.
 */
async function handleDemoRoleSwitch(roleName) {
    try {
        const response = await fetch(`${API_BASE}/api/auth/demo-switch`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ role: roleName })
        });
        const data = await response.json();
        if (response.ok) {
            // Save mock token to localStorage
            localStorage.setItem(TOKEN_KEY, data.access_token);
            // Re-evaluate state
            await checkAuthState();
        } else {
            alert(`Could not switch role to ${roleName}: ${data.detail}`);
        }
    } catch (err) {
        console.error("Demo role switch error:", err);
    }
}

// ==========================================================
// 4. NAVIGATION & MODAL CONTROLLERS
// ==========================================================
function setRoute(view, modal = null, replace = false) {
    const url = new URL(window.location.href);
    url.hash = "";
    url.search = "";
    if (view && view !== "home") url.searchParams.set("view", view);
    if (modal) url.searchParams.set("modal", modal);
    const method = replace ? "replaceState" : "pushState";
    window.history[method]({ view, modal }, "", `${url.pathname}${url.search}`);
}

function navigateToSection(event, sectionId) {
    if (event) event.preventDefault();
    setRoute("home");
    document.getElementById("landing-view").classList.add("active");
    document.getElementById("dashboard-view").classList.add("hidden");
    setTimeout(() => document.getElementById(sectionId)?.scrollIntoView({ behavior: "smooth" }), 0);
}

function restoreRoute() {
    const params = new URLSearchParams(window.location.search);
    const view = params.get("view") || "home";
    const modal = params.get("modal");
    if (window.location.hash) {
        window.history.replaceState({ view: "home" }, "", `${window.location.pathname}?view=home`);
    }

    if (view === "dashboard" && state.token && state.user) {
        applyAuthenticatedView();
    } else if (view !== "dashboard") {
        navigateToHome(null);
    } else {
        openLoginModal();
    }

    if (modal === "login") openLoginModal();
    if (modal === "register") openRegisterModal();
    if (modal === "booking") openBookingModal();
    if (modal === "reschedule") {
        document.getElementById("reschedule-modal")?.classList.add("active");
    }
    if (modal === "review") {
        document.getElementById("review-modal")?.classList.add("active");
    }
}

window.addEventListener("popstate", restoreRoute);

function openLoginModal() {
    document.getElementById("login-error-alert").classList.add("hidden");
    document.getElementById("login-modal").classList.add("active");
    setRoute(state.user ? "dashboard" : "home", "login", true);
}

function closeLoginModal() {
    document.getElementById("login-modal").classList.remove("active");
    setRoute(state.user ? "dashboard" : "home", null, true);
}

function openRegisterModal() {
    document.getElementById("register-error-alert").classList.add("hidden");
    document.getElementById("register-modal").classList.add("active");
    setRoute(state.user ? "dashboard" : "home", "register", true);
}

function closeRegisterModal() {
    document.getElementById("register-modal").classList.remove("active");
    setRoute(state.user ? "dashboard" : "home", null, true);
}

function switchToRegister(e) {
    if (e) e.preventDefault();
    closeLoginModal();
    openRegisterModal();
}

function switchToLogin(e) {
    if (e) e.preventDefault();
    closeRegisterModal();
    openLoginModal();
}

function navigateToHome(e) {
    if (e) e.preventDefault();
    setRoute("home");
    document.getElementById("landing-view").classList.add("active");
    document.getElementById("dashboard-view").classList.add("hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });
}

function navigateToDashboard(e) {
    if (e) e.preventDefault();
    if (state.token && state.user) {
        setRoute("dashboard");
        applyAuthenticatedView();
    } else {
        openLoginModal();
    }
}

function scrollToQuote() {
    // If on dashboard, switch to landing view first
    setRoute("home");
    document.getElementById("landing-view").classList.add("active");
    document.getElementById("dashboard-view").classList.add("hidden");

    setTimeout(() => {
        const quoteEl = document.getElementById("quote-section");
        if (quoteEl) quoteEl.scrollIntoView({ behavior: "smooth" });
    }, 50);
}

function handleBookCleanClick() {
    if (!state.token || !state.user) {
        // Prompt guest to log in or create an account before reserving
        openLoginModal();
    } else {
        openBookingModal();
    }
}

// ==========================================================
// 5. DYNAMIC PRICING ENGINE
// ==========================================================
function adjustCount(type, delta) {
    if (type === "bedrooms") {
        state.quote.bedrooms = Math.max(1, Math.min(10, state.quote.bedrooms + delta));
        document.getElementById("bedrooms-val").textContent = state.quote.bedrooms;
    } else if (type === "bathrooms") {
        state.quote.bathrooms = Math.max(1, Math.min(6, state.quote.bathrooms + delta));
        document.getElementById("bathrooms-val").textContent = state.quote.bathrooms;
    }
    recalculateQuote();
}

async function recalculateQuote() {
    const postcodeInput = document.getElementById("quote-postcode").value.trim() || "SW1A 1AA";
    const serviceSelect = document.getElementById("quote-service").value;
    const hasPets = document.getElementById("quote-pets").checked;
    const deepClean = document.getElementById("quote-deep").checked;

    state.quote.postcode = postcodeInput;
    state.quote.service_id = parseInt(serviceSelect);
    state.quote.has_pets = hasPets;
    state.quote.deep_clean = deepClean;

    try {
        const response = await fetch(`${API_BASE}/api/pricing/calculate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                postcode: postcodeInput,
                service_id: state.quote.service_id,
                bedrooms: state.quote.bedrooms,
                bathrooms: state.quote.bathrooms,
                has_pets: hasPets,
                deep_clean: deepClean,
                eco_products: true
            })
        });

        if (response.ok) {
            const data = await response.json();
            state.quote.calculatedPrice = data.total_price_gbp;
            state.quote.estimatedHours = data.estimated_duration_hours;

            document.getElementById("quote-price-display").textContent = `£${data.total_price_gbp.toFixed(2)}`;
            document.getElementById("quote-meta-display").textContent =
                `Estimated ~${data.estimated_duration_hours} hrs • £${data.hourly_equivalent_gbp.toFixed(2)}/hr`;

            const modalTotal = document.getElementById("modal-total-display");
            if (modalTotal) modalTotal.textContent = `£${data.total_price_gbp.toFixed(2)}`;
        }
    } catch (err) {
        console.error("Quote calculate error:", err);
    }
}

async function lookupPostcodeArea() {
    const postcodeInput = document.getElementById("quote-postcode").value.trim();
    const statusEl = document.getElementById("postcode-status");
    statusEl.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Checking TfL Area...`;

    try {
        const res = await fetch(`${API_BASE}/api/maps/geocode`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ postcode: postcodeInput })
        });
        const data = await res.json();
        if (res.ok) {
            statusEl.innerHTML = `<span style="color: #16a34a"><i class="fa-solid fa-check"></i> Covered: ${data.neighborhood} (${data.outcode})</span>`;
            recalculateQuote();
        }
    } catch (err) {
        statusEl.textContent = "Valid London postcode";
    }
}

// ==========================================================
// 6. CUSTOMER BOOKING FLOW
// ==========================================================
function openBookingModal() {
    const bookPostcode = document.getElementById("book-postcode");
    if (bookPostcode) {
        bookPostcode.value = state.quote.postcode;
    }
    document.getElementById("booking-modal").classList.add("active");
    setRoute("home", "booking", true);
}

function closeBookingModal() {
    document.getElementById("booking-modal").classList.remove("active");
    setRoute(state.user ? "dashboard" : "home", null, true);
}

async function submitNewBooking(e) {
    e.preventDefault();
    if (!state.token) {
        openLoginModal();
        return;
    }

    if (state.isSubmittingBooking) return;
    state.isSubmittingBooking = true;

    const submitBtn = document.querySelector("#create-booking-form button[type='submit']");
    const origBtnHtml = submitBtn ? submitBtn.innerHTML : "Confirm Booking & Proceed to Payment";
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Securing Your Slot...';
    }

    const addressLine1 = document.getElementById("book-address1").value;
    const addressLine2 = document.getElementById("book-address2").value;
    const postcode = document.getElementById("book-postcode").value;
    const scheduledDate = document.getElementById("book-date").value;
    const scheduledTime = document.getElementById("book-timeslot").value;
    const keyHandling = document.getElementById("book-key-handling").value;
    const notes = document.getElementById("book-access-notes").value;

    // Client-side idempotency key to prevent double charge / duplicate submission
    const idempotencyKey = "CL-IDEM-" + Date.now() + "-" + Math.random().toString(36).substring(2, 9);

    const payload = {
        service_id: state.quote.service_id,
        property_type: state.quote.property_type,
        bedrooms: state.quote.bedrooms,
        bathrooms: state.quote.bathrooms,
        has_pets: state.quote.has_pets,
        deep_clean_requested: state.quote.deep_clean,
        eco_cleaning_products: true,
        address_line1: addressLine1,
        address_line2: addressLine2,
        city: "London",
        postcode: postcode,
        key_handling_type: keyHandling,
        access_notes: notes,
        scheduled_date: scheduledDate,
        scheduled_time_slot: scheduledTime,
        idempotency_key: idempotencyKey
    };

    try {
        const res = await authFetch(`${API_BASE}/api/bookings`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Idempotency-Key": idempotencyKey
            },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (res.ok) {
            closeBookingModal();
            // Automatically launch Stripe Hosted Checkout for the customer
            await initiateStripeCheckout(data.booking_id);
        } else {
            alert(`Booking Error: ${data.detail || "Could not complete booking"}`);
        }
    } catch (err) {
        if (err.message !== "Session expired") {
            alert("Booking submission failed. Please try again.");
        }
    } finally {
        state.isSubmittingBooking = false;
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = origBtnHtml;
        }
    }
}

/**
 * Initiates Stripe Hosted Checkout Session and redirects user
 */
async function initiateStripeCheckout(bookingId) {
    try {
        const paymentKeyStorage = `cleanlondon_payment_idempotency_${bookingId}`;
        const paymentIdempotencyKey = localStorage.getItem(paymentKeyStorage)
            || (crypto.randomUUID ? crypto.randomUUID() : `CL-PAY-${bookingId}-${Date.now()}`);
        localStorage.setItem(paymentKeyStorage, paymentIdempotencyKey);
        const payRes = await authFetch(`${API_BASE}/api/payments/create-checkout-session`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Idempotency-Key": paymentIdempotencyKey
            },
            body: JSON.stringify({ booking_id: parseInt(bookingId) })
        });
        const payData = await payRes.json();
        if (payRes.ok && payData.checkout_url) {
            // Secure Redirect to Stripe Hosted Checkout
            window.location.href = payData.checkout_url;
        } else {
            alert(`Payment initialization failed: ${payData.detail || "Unable to reach Stripe"}`);
            applyAuthenticatedView();
        }
    } catch (err) {
        if (err.message !== "Session expired") {
            console.error("Stripe Checkout error:", err);
            alert("Payment gateway error. Please try again from your dashboard.");
            applyAuthenticatedView();
        }
    }
}

async function loadCustomerBookings() {
    if (!state.token) return;
    const listBody = document.getElementById("customer-bookings-list");
    listBody.innerHTML = `<tr><td colspan="8" class="text-center">Loading your London bookings...</td></tr>`;

    try {
        const res = await authFetch(`${API_BASE}/api/bookings/my`);
        if (!res.ok) return;
        const data = await res.json();
        if (data.bookings) {
            state.customerBookings = data.bookings;
            if (data.bookings.length === 0) {
                listBody.innerHTML = `<tr><td colspan="8" class="text-center">No bookings found. Click "Book a Clean" to schedule one!</td></tr>`;
                return;
            }

            function renderProgressStepper(status) {
                const steps = ["SCHEDULED", "EN_ROUTE", "IN_PROGRESS", "COMPLETED"];
                const active = steps.indexOf(status);
                if (active < 0) return "";
                return `<div class="progress-stepper">${steps.map((step, index) =>
                    `<span class="${index <= active ? "done" : ""}"><i class="fa-solid ${index <= active ? "fa-check" : "fa-circle"}"></i>${step.replace("_", " ")}</span>`
                ).join("")}</div>`;
            }

            function renderCustomerProgress(bookings) {
                const panel = document.getElementById("customer-booking-progress");
                const active = bookings.find(b => ["EN_ROUTE", "IN_PROGRESS"].includes(b.status));
                if (!panel || !active) {
                    panel?.classList.add("hidden");
                    return;
                }
                panel.classList.remove("hidden");
                panel.innerHTML = `<strong>${active.reference_code}</strong> is currently ${active.status.replace("_", " ")} ${renderProgressStepper(active.status)}`;
            }

            function showBookingInstructions(bookingId) {
                const booking = state.customerBookings?.find(b => b.id === bookingId);
                if (!booking) return;
                showToast(`Access instructions: ${booking.access_notes || "Handover in person"}`, "info");
            }

            function downloadReceipt(bookingId) {
                const booking = state.customerBookings?.find(b => b.id === bookingId);
                if (!booking) return;
                const receipt = `CleanLondon receipt\n${booking.reference_code}\n${booking.service_name}\n£${Number(booking.total_price_gbp).toFixed(2)}\n${booking.scheduled_date} ${booking.scheduled_time_slot}`;
                const link = document.createElement("a");
                link.href = URL.createObjectURL(new Blob([receipt], { type: "text/plain" }));
                link.download = `${booking.reference_code}-receipt.txt`;
                link.click();
                URL.revokeObjectURL(link.href);
                showToast("Receipt downloaded.", "success");
            }

            listBody.innerHTML = data.bookings.map(b => {
                let actionBtn = "";
                if (b.status === "CANCELLED") {
                    const penaltyText = b.cancellation_fee_gbp > 0 ? ` (50% fee: £${parseFloat(b.cancellation_fee_gbp).toFixed(2)})` : ' (Full refund)';
                    actionBtn = `<span class="badge-cancelled" style="background:#fee2e2; color:#b91c1c; font-size:0.75rem; padding:4px 8px; border-radius:12px; font-weight:700;" title="${b.cancellation_reason || 'Cancelled'}"><i class="fa-solid fa-ban"></i> Cancelled${penaltyText}</span>`;
                } else if (b.status === "COMPLETED" && !b.review_rating) {
                    actionBtn = `<button class="btn btn-sm btn-primary" onclick="openReviewModal(${b.id})"><i class="fa-solid fa-star"></i> Review</button>`;
                } else if (b.review_rating) {
                    actionBtn = `<span class="text-gold">★ ${b.review_rating}/5 Rated</span>`;
                } else if (b.status === "SCHEDULED") {
                    let payPart = "";
                    if (b.payment_status === "PENDING") {
                        payPart = `<button class="btn btn-sm btn-primary" onclick="initiateStripeCheckout(${b.id})" style="background:#635bff; border-color:#635bff; margin-bottom:4px; font-size:0.75rem; padding:3px 7px;"><i class="fa-brands fa-stripe"></i> Pay £${parseFloat(b.total_price_gbp).toFixed(2)}</button><br>`;
                    }
                    actionBtn = `
                        ${payPart}
                        <div style="display:flex; gap:4px; flex-wrap:wrap;">
                            <button class="btn btn-sm btn-outline-primary" onclick="openRescheduleModal(${b.id}, '${b.reference_code}', '${b.scheduled_date}', '${b.scheduled_time_slot}')" title="Reschedule Appointment" style="font-size:0.75rem; padding:3px 7px;"><i class="fa-solid fa-calendar-days"></i> Reschedule</button>
                            <button class="btn btn-sm btn-outline-danger" onclick="cancelCustomerBooking(${b.id}, '${b.reference_code}', '${b.scheduled_date}', '${b.scheduled_time_slot}', ${b.total_price_gbp})" title="Cancel Booking" style="font-size:0.75rem; padding:3px 7px;"><i class="fa-solid fa-ban"></i> Cancel</button>
                        </div>
                    `;
                } else {
                    actionBtn = `
                        <div class="customer-actions">
                            <button class="btn btn-sm btn-outline" onclick="showBookingInstructions(${b.id})"><i class="fa-solid fa-key"></i> View Instructions</button>
                            <button class="btn btn-sm btn-outline-primary" onclick="openRescheduleModal(${b.id}, '${b.reference_code}', '${b.scheduled_date}', '${b.scheduled_time_slot}')"><i class="fa-solid fa-calendar-days"></i> Reschedule</button>
                            <button class="btn btn-sm btn-outline-danger" onclick="cancelCustomerBooking(${b.id}, '${b.reference_code}', '${b.scheduled_date}', '${b.scheduled_time_slot}', ${b.total_price_gbp})"><i class="fa-solid fa-ban"></i> Cancel</button>
                            <button class="btn btn-sm btn-outline" onclick="downloadReceipt(${b.id})"><i class="fa-solid fa-download"></i> Receipt</button>
                        </div>`;
                }

                let paymentBadge = "";
                if (b.payment_status === "PAID") {
                    paymentBadge = `<span style="color:#15803d; font-weight:700;"><i class="fa-solid fa-check"></i> Paid</span>`;
                } else if (b.payment_status === "REFUNDED") {
                    paymentBadge = `<span style="color:#64748b; font-weight:700;"><i class="fa-solid fa-rotate-left"></i> Refunded</span>`;
                } else {
                    paymentBadge = `<span style="color:#b45309; font-weight:700;"><i class="fa-solid fa-clock"></i> Pending</span>`;
                }

                return `
                    <tr>
                        <td data-label="Reference"><strong>${b.reference_code}</strong></td>
                        <td data-label="Service">${b.service_name}</td>
                        <td data-label="Date & time">${b.scheduled_date}<br><small class="text-muted">${b.scheduled_time_slot}</small></td>
                        <td data-label="Address">${b.address_line1}, ${b.postcode}</td>
                        <td data-label="Cleaner">${b.staff_name ? `<div class="cleaner-profile"><img src="${b.staff_avatar_url || '/static/logo.jpg'}" alt="${b.staff_name}"><span><strong>${b.staff_name}</strong><small>★ ${Number(b.staff_rating || 4.92).toFixed(2)} <b>DBS Verified</b></small></span></div>` : '<em class="text-muted">Allocating...</em>'}</td>
                        <td data-label="Price"><strong>£${parseFloat(b.total_price_gbp).toFixed(2)}</strong><br><small>${paymentBadge}</small></td>
                        <td data-label="Status"><span class="status-badge ${b.status}">${b.status.replace('_', ' ')}</span>${renderProgressStepper(b.status)}</td>
                        <td data-label="Actions">${actionBtn}</td>
                    </tr>
                `;
            }).join("");
            renderCustomerProgress(data.bookings);
        }
    } catch (err) {
        if (err.message !== "Session expired") {
            console.error("Load customer bookings err:", err);
        }
    }
}

// ==========================================================
// CANCELLATION & RESCHEDULING ACTIONS (CUSTOMER)
// ==========================================================
async function cancelCustomerBooking(bookingId, refCode, scheduledDate, scheduledTimeSlot, totalPrice) {
    // Check cancellation notice window
    const now = new Date();
    const startTimeStr = (scheduledTimeSlot.match(/\d{1,2}:\d{2}/) || ["09:00"])[0];
    const serviceDate = new Date(`${scheduledDate}T${startTimeStr}:00`);
    const hoursDiff = (serviceDate - now) / (1000 * 60 * 60);

    let feeWarning = "";
    if (hoursDiff >= 24) {
        feeWarning = "Notice: Over 24 hours until appointment. 100% Free cancellation with full refund.";
    } else {
        const fee = (totalPrice * 0.5).toFixed(2);
        const refund = (totalPrice - fee).toFixed(2);
        feeWarning = `Late Cancellation Notice (<24 hours):\nA 50% late fee (£${fee}) applies. Refund issued: £${refund}.`;
    }

    const confirmMsg = `Are you sure you want to cancel booking ${refCode}?\n\n${feeWarning}`;
    if (!confirm(confirmMsg)) return;

    try {
        const res = await authFetch(`${API_BASE}/api/bookings/${bookingId}/cancel`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ reason: "Customer requested cancellation via portal" })
        });
        const data = await res.json();
        if (res.ok) {
            alert(`Booking ${refCode} Cancelled:\n${data.policy_note}`);
            loadCustomerBookings();
        } else {
            alert(`Cancellation Error: ${data.detail || "Could not cancel booking"}`);
        }
    } catch (err) {
        if (err.message !== "Session expired") {
            alert("Failed to communicate with cancellation server.");
        }
    }
}

function openRescheduleModal(bookingId, refCode, currentDate, currentTimeSlot) {
    document.getElementById("reschedule-booking-id").value = bookingId;
    document.getElementById("reschedule-booking-ref-text").textContent = `Rescheduling booking ${refCode} (Current: ${currentDate} at ${currentTimeSlot})`;
    
    // Set min date to tomorrow
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    document.getElementById("reschedule-date").min = tomorrow.toISOString().split("T")[0];
    document.getElementById("reschedule-date").value = tomorrow.toISOString().split("T")[0];

    document.getElementById("reschedule-modal").classList.add("active");
    setRoute("dashboard", "reschedule", true);
}

function closeRescheduleModal() {
    document.getElementById("reschedule-modal").classList.remove("active");
    setRoute("dashboard", null, true);
}

async function submitReschedule(e) {
    e.preventDefault();
    const bookingId = document.getElementById("reschedule-booking-id").value;
    const newDate = document.getElementById("reschedule-date").value;
    const newTimeslot = document.getElementById("reschedule-timeslot").value;

    const submitBtn = document.getElementById("reschedule-submit-btn");
    const origText = submitBtn.innerHTML;
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Rescheduling...';

    try {
        const res = await authFetch(`${API_BASE}/api/bookings/${bookingId}/reschedule`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                new_date: newDate,
                new_time_slot: newTimeslot,
                reason: "Customer changed appointment slot via dashboard"
            })
        });

        const data = await res.json();
        if (res.ok) {
            alert(data.message);
            closeRescheduleModal();
            loadCustomerBookings();
        } else {
            alert(`Rescheduling Failed: ${data.detail || "Could not reschedule"}`);
        }
    } catch (err) {
        if (err.message !== "Session expired") {
            alert("Error submitting reschedule request.");
        }
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = origText;
    }
}

// ==========================================================
// 7. REVIEWS
// ==========================================================
function openReviewModal(bookingId) {
    document.getElementById("review-booking-id").value = bookingId;
    document.getElementById("review-modal").classList.add("active");
    setRoute("dashboard", "review", true);
}

function closeReviewModal() {
    document.getElementById("review-modal").classList.remove("active");
    setRoute("dashboard", null, true);
}

function setRating(rating) {
    document.getElementById("review-stars-val").value = rating;
    const stars = document.querySelectorAll(".star-rating-input .star-opt");
    stars.forEach((s, idx) => {
        s.classList.toggle("active", idx < rating);
    });
}

async function submitReview(e) {
    e.preventDefault();
    const bookingId = document.getElementById("review-booking-id").value;
    const rating = parseInt(document.getElementById("review-stars-val").value);
    const comment = document.getElementById("review-comment").value;

    try {
        const res = await authFetch(`${API_BASE}/api/bookings/${bookingId}/review`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                rating: rating,
                comment: comment,
                punctuality_score: 5,
                thoroughness_score: 5
            })
        });
        const data = await res.json();
        if (res.ok) {
            closeReviewModal();
            alert("🌟 Thank you! Your review has been saved.");
            loadCustomerBookings();
        } else {
            alert(`Error: ${data.detail}`);
        }
    } catch (err) {
        if (err.message !== "Session expired") {
            alert("Failed to save review.");
        }
    }
}

// ==========================================================
// 8. STAFF / CLEANER WORKFLOW & MAP
// ==========================================================
async function loadStaffJobs() {
    if (!state.token) return;
    const container = document.getElementById("staff-jobs-container");
    container.innerHTML = `<div class="p-4 text-center">Loading assigned tasks...</div>`;

    try {
        const res = await authFetch(`${API_BASE}/api/staff/jobs`);
        if (!res.ok) return;
        const data = await res.json();
        if (data.jobs) {
            if (data.jobs.length === 0) {
                container.innerHTML = `<div class="p-4 text-center text-muted">No jobs assigned today. Stand by for dispatch.</div>`;
                return;
            }

            const today = new Date().toISOString().slice(0, 10);
            container.innerHTML = data.jobs.map((j, index) => {
                let nextActionBtn = "";
                if (j.status === "SCHEDULED") {
                    nextActionBtn = `<button class="btn btn-sm btn-primary" onclick="advanceJobStatus(${j.id}, 'EN_ROUTE')"><i class="fa-solid fa-person-walking"></i> Start: En Route</button>`;
                } else if (j.status === "EN_ROUTE") {
                    nextActionBtn = `<button class="btn btn-sm btn-primary" onclick="advanceJobStatus(${j.id}, 'IN_PROGRESS')"><i class="fa-solid fa-play"></i> Arrived: Begin Clean</button>`;
                } else if (j.status === "IN_PROGRESS") {
                    nextActionBtn = `<button class="btn btn-sm btn-primary" onclick="advanceJobStatus(${j.id}, 'COMPLETED')"><i class="fa-solid fa-circle-check"></i> Complete & Sign Off</button>`;
                } else {
                    nextActionBtn = `<span class="text-emerald"><i class="fa-solid fa-check"></i> Clean Completed</span>`;
                }

                // UK GDPR Access Note Display: highlight unlocked key vs masked notice
                const isUnlocked = (j.status === "EN_ROUTE" || j.status === "IN_PROGRESS");
                const accessNoteHtml = isUnlocked
                    ? `<span style="color:#047857; font-weight:600;"><i class="fa-solid fa-key"></i> ${j.access_notes || 'Handover in person'}</span>`
                    : `<span style="color:#b45309; font-size:0.75rem;"><i class="fa-solid fa-shield-halved"></i> ${j.access_notes || 'Protected'}</span>`;

                const heading = index === 0 ? `<h4 class="job-section-heading">${j.scheduled_date === today ? "Today's Shift" : "Upcoming"}</h4>` :
                    (data.jobs[index - 1].scheduled_date !== j.scheduled_date && j.scheduled_date !== today ? `<h4 class="job-section-heading">Upcoming</h4>` : "");
                return `${heading}
                    <div class="job-card ${state.activeJobForMap?.id === j.id ? 'active-selected' : ''}" onclick="selectJobForMap(${JSON.stringify(j).replace(/"/g, '&quot;')})">
                        <div class="job-card-header">
                            <span class="job-card-title">${j.reference_code} • ${j.service_name}</span>
                            <span class="status-badge ${j.status}">${j.status.replace('_', ' ')}</span>
                        </div>
                        <div class="job-card-address">
                            <i class="fa-solid fa-location-dot text-emerald"></i> ${j.address_line1}, ${j.postcode} (${j.bedrooms} Bed, ${j.bathrooms} Bath)
                        </div>
                        <div class="access-alert">
                            <strong>Customer:</strong> ${j.customer_name} (${j.customer_phone})<br>
                            <strong>Key Handover:</strong> ${j.key_handling_type} — ${accessNoteHtml}
                        </div>
                        <div class="job-actions-row">
                            <div class="primary-job-action">${nextActionBtn}</div>
                            <button class="btn btn-outline map-action" onclick="event.stopPropagation(); openGoogleMaps('${j.postcode}')"><i class="fa-solid fa-map-location-dot"></i> Open in Google Maps</button>
                        </div>
                    </div>
                `;
            }).join("");

            if (data.jobs.length > 0 && !state.activeJobForMap) {
                selectJobForMap(data.jobs[0]);
            }
        }
    } catch (err) {
        if (err.message !== "Session expired") {
            console.error("Staff jobs error:", err);
        }
    }
}

async function advanceJobStatus(bookingId, targetStatus) {
    try {
        const res = await authFetch(`${API_BASE}/api/staff/jobs/${bookingId}/status`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status: targetStatus, notes: `Status updated by cleaner` })
        });
        const data = await res.json();
        if (res.ok) {
            alert(`Job status progressed to: ${targetStatus}`);
            loadStaffJobs();
        } else {
            alert(`Could not update status: ${data.detail}`);
        }

        const STAFF_WEEKDAYS_FALLBACK_2 = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

        async function loadStaffScheduleLegacy() {
            const form = document.getElementById("staff-schedule-form");
            if (!form) return;
            try {
                const res = await authFetch(`${API_BASE}/api/staff/schedule`);
                if (!res.ok) return;
                const data = await res.json();
                const shifts = Object.fromEntries((data.weekly_availability || []).map(s => [s.day_of_week, s]));
                form.innerHTML = STAFF_WEEKDAYS.map((day, index) => {
                    const shift = shifts[index];
                    return `<div class="form-row-2" style="align-items:center; margin:4px 0;">
                        <label><input type="checkbox" class="staff-day-enabled" data-day="${index}" ${shift ? "checked" : ""}> ${day}</label>
                        <span><input type="time" class="staff-day-start" data-day="${index}" value="${shift?.start_time || "09:00"}">
                        &ndash; <input type="time" class="staff-day-end" data-day="${index}" value="${shift?.end_time || "17:00"}"></span>
                    </div>`;
                }).join("");
                document.getElementById("staff-holidays-list").innerHTML =
                    (data.holidays || []).map(h => `${h.holiday_date}: ${h.reason || "Unavailable"} ` +
                        `<button class="btn btn-sm btn-outline" onclick="removeStaffHoliday('${h.holiday_date}')">Remove</button>`).join("<br>");
            } catch (err) {
                if (err.message !== "Session expired") console.error("Schedule load error:", err);
            }
        }

        async function saveStaffScheduleLegacy() {
            const schedule = [...document.querySelectorAll(".staff-day-enabled:checked")].map(input => {
                const day = input.dataset.day;
                return {
                    day_of_week: Number(day),
                    start_time: document.querySelector(`.staff-day-start[data-day="${day}"]`).value,
                    end_time: document.querySelector(`.staff-day-end[data-day="${day}"]`).value
                };
            });
            const res = await authFetch(`${API_BASE}/api/staff/schedule`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(schedule)
            });
            const data = await res.json();
            showToast(res.ok ? "Working hours saved." : (data.detail || "Could not save working hours."), res.ok ? "success" : "error");
        }

        async function loadStaffEarningsLegacy() {
            try {
                const res = await authFetch(`${API_BASE}/api/staff/earnings`);
                if (!res.ok) return;
                const data = await res.json();
                document.getElementById("staff-earnings-total").textContent = `£${Number(data.cleaner_earnings_gbp).toFixed(2)}`;
                document.getElementById("staff-today-earnings").textContent = `£${Number(data.today_earnings_gbp || 0).toFixed(2)}`;
                document.getElementById("staff-completed-hours").textContent = `${Number(data.completed_hours || 0).toFixed(1)}h`;
                document.getElementById("staff-earnings-meta").textContent = `Completed jobs: ${data.completed_jobs} (70% cleaner share)`;
            } catch (err) {
                if (err.message !== "Session expired") console.error("Earnings load error:", err);
            }
        }

        async function addStaffHolidayLegacy() {
            const holidayDate = document.getElementById("staff-holiday-date").value;
            const reason = document.getElementById("staff-holiday-reason").value;
            if (!holidayDate) return showToast("Choose a holiday or sick-day date.", "error");
            const res = await authFetch(`${API_BASE}/api/staff/holidays`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ holiday_date: holidayDate, reason })
            });
            const data = await res.json();
            if (!res.ok) return showToast(data.detail || "Could not save holiday.", "error");
            showToast("Holiday saved.", "success");
            await loadStaffSchedule();
        }

        async function removeStaffHolidayLegacy(holidayDate) {
            const res = await authFetch(`${API_BASE}/api/staff/holidays/${holidayDate}`, { method: "DELETE" });
            if (res.ok) await loadStaffSchedule();
        }

        const STAFF_WEEKDAYS_FALLBACK_3 = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

        async function loadStaffScheduleLegacy2() {
            const form = document.getElementById("staff-schedule-form");
            if (!form) return;
            try {
                const res = await authFetch(`${API_BASE}/api/staff/schedule`);
                if (!res.ok) return;
                const data = await res.json();
                const shifts = Object.fromEntries((data.weekly_availability || []).map(s => [s.day_of_week, s]));
                form.innerHTML = STAFF_WEEKDAYS.map((day, index) => {
                    const shift = shifts[index];
                    return `<div class="form-row-2" style="align-items:center; margin:4px 0;">
                        <label><input type="checkbox" class="staff-day-enabled" data-day="${index}" ${shift ? "checked" : ""}> ${day}</label>
                        <span><input type="time" class="staff-day-start" data-day="${index}" value="${shift?.start_time || "09:00"}">
                        &ndash; <input type="time" class="staff-day-end" data-day="${index}" value="${shift?.end_time || "17:00"}"></span>
                    </div>`;
                }).join("");
                document.getElementById("staff-holidays-list").innerHTML =
                    (data.holidays || []).map(h => `${h.holiday_date}: ${h.reason || "Unavailable"} ` +
                        `<button class="btn btn-sm btn-outline" onclick="removeStaffHoliday('${h.holiday_date}')">Remove</button>`).join("<br>");
            } catch (err) {
                if (err.message !== "Session expired") console.error("Schedule load error:", err);
            }
        }

        async function saveStaffScheduleLegacy2() {
            const schedule = [...document.querySelectorAll(".staff-day-enabled:checked")].map(input => {
                const day = input.dataset.day;
                return {
                    day_of_week: Number(day),
                    start_time: document.querySelector(`.staff-day-start[data-day="${day}"]`).value,
                    end_time: document.querySelector(`.staff-day-end[data-day="${day}"]`).value
                };
            });
            const res = await authFetch(`${API_BASE}/api/staff/schedule`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(schedule)
            });
            const data = await res.json();
            alert(res.ok ? "Working hours saved." : (data.detail || "Could not save working hours."));
        }

        async function loadStaffEarningsLegacy2() {
            try {
                const res = await authFetch(`${API_BASE}/api/staff/earnings`);
                if (!res.ok) return;
                const data = await res.json();
                document.getElementById("staff-earnings-total").textContent = `£${Number(data.cleaner_earnings_gbp).toFixed(2)}`;
                document.getElementById("staff-today-earnings").textContent = `£${Number(data.today_earnings_gbp || 0).toFixed(2)}`;
                document.getElementById("staff-completed-hours").textContent = `${Number(data.completed_hours || 0).toFixed(1)}h`;
                document.getElementById("staff-earnings-meta").textContent =
                    `Completed jobs: ${data.completed_jobs} (70% cleaner share)`;
            } catch (err) {
                if (err.message !== "Session expired") console.error("Earnings load error:", err);
            }
        }

        async function addStaffHolidayLegacy2() {
            const holidayDate = document.getElementById("staff-holiday-date").value;
            const reason = document.getElementById("staff-holiday-reason").value;
            if (!holidayDate) return alert("Choose a holiday or sick-day date.");
            const res = await authFetch(`${API_BASE}/api/staff/holidays`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ holiday_date: holidayDate, reason })
            });
            const data = await res.json();
            if (!res.ok) return alert(data.detail || "Could not save holiday.");
            await loadStaffSchedule();
        }

        async function removeStaffHolidayLegacy2(holidayDate) {
            const res = await authFetch(`${API_BASE}/api/staff/holidays/${holidayDate}`, { method: "DELETE" });
            if (res.ok) await loadStaffSchedule();
        }
    } catch (err) {
        if (err.message !== "Session expired") {
            alert("Failed to advance status.");
        }
    }
}

const STAFF_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

async function loadStaffSchedule() {
    const form = document.getElementById("staff-schedule-form");
    if (!form) return;
    const res = await authFetch(`${API_BASE}/api/staff/schedule`);
    if (!res.ok) return;
    const data = await res.json();
    const shifts = Object.fromEntries((data.weekly_availability || []).map(s => [s.day_of_week, s]));
    form.innerHTML = STAFF_WEEKDAYS.map((day, index) => {
        const shift = shifts[index];
        return `<div class="form-row-2" style="align-items:center; margin:4px 0;">
            <label><input type="checkbox" class="staff-day-enabled" data-day="${index}" ${shift ? "checked" : ""}> ${day}</label>
            <span><input type="time" class="staff-day-start" data-day="${index}" value="${shift?.start_time || "09:00"}">
            &ndash; <input type="time" class="staff-day-end" data-day="${index}" value="${shift?.end_time || "17:00"}"></span>
        </div>`;
    }).join("");
    document.getElementById("staff-holidays-list").innerHTML =
        (data.holidays || []).map(h => `${h.holiday_date}: ${h.reason || "Unavailable"} ` +
            `<button class="btn btn-sm btn-outline" onclick="removeStaffHoliday('${h.holiday_date}')">Remove</button>`).join("<br>");
}

async function saveStaffSchedule() {
    const schedule = [...document.querySelectorAll(".staff-day-enabled:checked")].map(input => {
        const day = input.dataset.day;
        return {
            day_of_week: Number(day),
            start_time: document.querySelector(`.staff-day-start[data-day="${day}"]`).value,
            end_time: document.querySelector(`.staff-day-end[data-day="${day}"]`).value
        };
    });
    const res = await authFetch(`${API_BASE}/api/staff/schedule`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(schedule)
    });
    showToast(res.ok ? "Working hours saved." : "Could not save working hours.", res.ok ? "success" : "error");
}

async function loadStaffEarnings() {
    const res = await authFetch(`${API_BASE}/api/staff/earnings`);
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById("staff-earnings-total").textContent = `£${Number(data.cleaner_earnings_gbp).toFixed(2)}`;
    document.getElementById("staff-today-earnings").textContent = `£${Number(data.today_earnings_gbp || 0).toFixed(2)}`;
    document.getElementById("staff-completed-hours").textContent = `${Number(data.completed_hours || 0).toFixed(1)}h`;
    document.getElementById("staff-earnings-meta").textContent = `Completed jobs: ${data.completed_jobs} (70% cleaner share)`;
}

async function addStaffHoliday() {
    const holidayDate = document.getElementById("staff-holiday-date").value;
    if (!holidayDate) return showToast("Choose a holiday or sick-day date.", "error");
    const res = await authFetch(`${API_BASE}/api/staff/holidays`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ holiday_date: holidayDate, reason: document.getElementById("staff-holiday-reason").value })
    });
    if (res.ok) {
        showToast("Holiday saved.", "success");
        await loadStaffSchedule();
    } else {
        showToast("Could not save holiday.", "error");
    }
}

async function removeStaffHoliday(holidayDate) {
    const res = await authFetch(`${API_BASE}/api/staff/holidays/${holidayDate}`, { method: "DELETE" });
    if (res.ok) await loadStaffSchedule();
}

function selectJobForMap(job) {
    state.activeJobForMap = job;
    document.getElementById("pin-postcode-text").textContent = `${job.postcode}`;
    const isUnlocked = (job.status === "EN_ROUTE" || job.status === "IN_PROGRESS");
    const accessText = isUnlocked
        ? `<span style="color:#047857; font-weight:600;"><i class="fa-solid fa-key"></i> Key: ${job.key_handling_type} — "${job.access_notes || 'Handover in person'}"</span>`
        : `<span style="color:#b45309; font-size:0.8rem;"><i class="fa-solid fa-shield-halved"></i> Key: ${job.key_handling_type} — "${job.access_notes || 'Protected'}"</span>`;

    document.getElementById("map-active-job-info").innerHTML = `
        <h4>${job.reference_code}: ${job.customer_name}</h4>
        <p><i class="fa-solid fa-location-dot"></i> ${job.address_line1}, London ${job.postcode}</p>
        <p>${accessText}</p>
    `;
    document.getElementById("transit-summary").innerHTML = `
        <i class="fa-solid fa-train-subway"></i> <strong>TfL Transit:</strong> Estimated ~15-20 mins travel from base to <strong>${job.postcode}</strong>.
    `;
    loadStaffJobs();
}

function openGoogleMaps(postcode) {
    window.open(`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(postcode + ", London")}`, "_blank", "noopener");
}

// ==========================================================
// 9. MANAGER DASHBOARD & DISPATCH
// ==========================================================
async function loadManagerData() {
    if (!state.token) return;
    loadManagerKPIs();
    loadManagerBookings();
    loadManagerStaffVetting();
}

async function loadManagerStaffVetting() {
    const table = document.getElementById("manager-staff-vetting-list");
    if (!table) return;
    const res = await authFetch(`${API_BASE}/api/manager/staff`);
    if (!res.ok) return;
    const data = await res.json();
    table.innerHTML = (data.staff || []).map(staff => `
        <tr>
            <td>${staff.full_name}<br><small>${staff.email}</small></td>
            <td><input type="checkbox" id="dbs-${staff.id}" ${staff.verified_dbs ? "checked" : ""}></td>
            <td><input type="checkbox" id="rtw-${staff.id}" ${staff.right_to_work_verified ? "checked" : ""}></td>
            <td>${staff.vetting_status || "PENDING"}</td>
            <td><button class="btn btn-sm btn-primary" onclick="updateStaffVetting(${staff.id})">Save & Activate</button></td>
        </tr>`).join("");
}

async function updateStaffVetting(staffId) {
    const dbs = document.getElementById(`dbs-${staffId}`).checked;
    const rtw = document.getElementById(`rtw-${staffId}`).checked;
    const res = await authFetch(`${API_BASE}/api/manager/staff/${staffId}/vetting`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            verified_dbs: dbs,
            right_to_work_verified: rtw,
            vetting_status: dbs && rtw ? "APPROVED" : "PENDING"
        })
    });
    const data = await res.json();
    alert(res.ok ? "Vetting record saved." : (data.detail || "Could not save vetting."));
    if (res.ok) loadManagerStaffVetting();
}

async function loadManagerKPIs() {
    try {
        const res = await authFetch(`${API_BASE}/api/manager/dashboard-stats`);
        if (!res.ok) return;
        const data = await res.json();
        if (data.kpis) {
            document.getElementById("kpi-daily-rev").textContent = `£${data.kpis.daily_revenue_gbp.toFixed(2)}`;
            document.getElementById("kpi-monthly-rev").textContent = `£${data.kpis.total_revenue_gbp.toFixed(2)}`;
            document.getElementById("kpi-utilization").textContent = `${data.kpis.staff_utilization_pct}%`;
            document.getElementById("kpi-active-cleaners").textContent = data.kpis.active_cleaners_today;
            document.getElementById("kpi-unassigned-count").textContent = data.kpis.unassigned_jobs;
        }
    } catch (err) {
        if (err.message !== "Session expired") {
            console.error("Manager KPIs error:", err);
        }
    }
}

async function loadManagerBookings() {
    const filter = document.getElementById("manager-status-filter").value;
    const tableBody = document.getElementById("manager-bookings-list");
    tableBody.innerHTML = `<tr><td colspan="9" class="text-center">Loading platform bookings...</td></tr>`;

    try {
        const res = await authFetch(`${API_BASE}/api/manager/bookings?status_filter=${filter}`);
        if (!res.ok) return;
        const data = await res.json();
        if (data.bookings) {
            const today = new Date().toISOString().slice(0, 10);
            const visibleBookings = state.managerQuickFilter === "UNASSIGNED"
                ? data.bookings.filter(b => !b.staff_id)
                : state.managerQuickFilter === "TODAY"
                    ? data.bookings.filter(b => b.scheduled_date === today && !["COMPLETED", "CANCELLED"].includes(b.status))
                    : data.bookings;
            state.managerBookings = visibleBookings;
            renderManagerTimeline(visibleBookings);
            if (visibleBookings.length === 0) {
                tableBody.innerHTML = `<tr><td colspan="9" class="text-center">No bookings found for filter: ${filter}</td></tr>`;
                return;
            }

            const staffByBooking = Object.fromEntries(await Promise.all(visibleBookings.map(async b => {
                const staffRes = await authFetch(`${API_BASE}/api/manager/staff?postcode=${encodeURIComponent(b.postcode)}&scheduled_date=${encodeURIComponent(b.scheduled_date)}`);
                return [b.id, staffRes.ok ? (await staffRes.json()).staff : []];
            })));
            tableBody.innerHTML = visibleBookings.map(b => {
                let actionControls = "";
                if (!b.staff_id) {
                    actionControls = `
                        <button class="btn btn-sm btn-primary" onclick="autoMatchCleaner(${b.id})" title="Auto-match nearest cleaner">
                            <i class="fa-solid fa-bolt"></i> Auto-Match
                        </button>
                        <button class="btn btn-sm btn-outline-primary" onclick="openManualAssignment(${b.id})"><i class="fa-solid fa-user-check"></i> Assign</button>
                    `;
                } else {
                    const staffOptions = (staffByBooking[b.id] || []).map(staff =>
                        `<option value="${staff.id}">${staff.full_name} — ${staff.base_postcode} (${staff.distance_miles ?? "—"} mi) • ${staff.jobs_today} jobs today</option>`
                    ).join("");
                    actionControls = `
                    <select onchange="manuallyReassign(${b.id}, this.value)" class="assignment-select">
                            <option value="">Reassign...</option>
                        ${staffOptions}
                        </select>
                    `;
                }

                return `
                    <tr data-booking-id="${b.id}" data-search="${`${b.reference_code} ${b.postcode}`.toLowerCase()}">
                        <td data-label="Reference"><strong>${b.reference_code}</strong></td>
                        <td data-label="Customer">${b.customer_name}<br><small class="text-muted">${b.customer_phone}</small></td>
                        <td data-label="Postcode"><span class="badge-trust" style="margin:0; padding:2px 6px;">${b.postcode}</span></td>
                        <td data-label="Service">${b.service_name}</td>
                        <td data-label="Date & slot">${b.scheduled_date}<br><small>${b.scheduled_time_slot}</small></td>
                        <td data-label="Value"><strong>£${parseFloat(b.total_price_gbp).toFixed(2)}</strong></td>
                        <td data-label="Status"><span class="status-badge ${b.status}">${b.status.replace('_', ' ')}</span></td>
                        <td data-label="Cleaner">${b.staff_name ? b.staff_name : '<span style="color:#e11d48; font-weight:700;"><i class="fa-solid fa-circle-exclamation"></i> Unassigned</span>'}</td>
                        <td data-label="Actions">${actionControls}</td>
                    </tr>
                `;
            }).join("");
        }

        function setManagerFilter(filter) {
            document.querySelectorAll(".filter-pill").forEach(button => button.classList.toggle("active", button.dataset.filter === filter));
            const select = document.getElementById("manager-status-filter");
            if (filter === "UNASSIGNED" || filter === "TODAY") {
                state.managerQuickFilter = filter;
                select.value = "ALL";
            } else {
                state.managerQuickFilter = null;
                select.value = filter;
            }
            loadManagerData();
        }

        function filterManagerBookings() {
            const query = (document.getElementById("manager-booking-search")?.value || "").toLowerCase();
            document.querySelectorAll("#manager-bookings-list tr[data-search]").forEach(row => {
                row.hidden = !row.dataset.search.includes(query);
            });
        }

        function renderManagerTimeline(bookings) {
            const timeline = document.getElementById("manager-schedule-timeline");
            if (!timeline) return;
            const grouped = {};
            bookings.filter(b => b.staff_name && b.status !== "CANCELLED").forEach(b => {
                grouped[b.staff_name] ||= [];
                grouped[b.staff_name].push(b);
            });
            timeline.innerHTML = `<h3><i class="fa-solid fa-timeline"></i> Daily Cleaner Schedule</h3>` +
                Object.entries(grouped).map(([name, jobs]) =>
                    `<div class="timeline-row"><strong>${name}</strong><div>${jobs.map(b =>
                        `<span class="timeline-job ${b.status}" title="${b.reference_code}">${b.scheduled_date} · ${b.scheduled_time_slot}<small>${b.reference_code}</small></span>`
                    ).join("")}</div></div>`
                ).join("") || `<p class="text-muted">No assigned jobs in this view.</p>`;
        }

        function openManualAssignment(bookingId) {
            const row = document.querySelector(`#manager-bookings-list tr[data-booking-id="${bookingId}"]`);
            row?.querySelector(".assignment-select")?.focus();
            showToast("Choose a cleaner from the assignment dropdown.", "info");
        }
    } catch (err) {
        if (err.message !== "Session expired") {
            console.error("Manager bookings load error:", err);
        }
    }
}

async function autoMatchCleaner(bookingId) {
    try {
        const res = await authFetch(`${API_BASE}/api/manager/bookings/${bookingId}/auto-match`, {
            method: "POST"
        });
        const data = await res.json();
        if (res.ok) {
            alert(`⚡ ${data.message} (${data.distance_miles} miles away, ★${data.rating})`);
            loadManagerData();
        } else {
            alert(`Auto-match error: ${data.detail}`);
        }
    } catch (err) {
        if (err.message !== "Session expired") {
            alert("Failed to auto-match cleaner.");
        }
    }
}

async function manuallyReassign(bookingId, staffId) {
    if (!staffId) return;
    try {
        const res = await authFetch(`${API_BASE}/api/manager/bookings/${bookingId}/reassign`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ staff_id: parseInt(staffId) })
        });
        const data = await res.json();
        if (res.ok) {
            alert("Staff assigned successfully!");
            loadManagerData();
        } else {
            alert(`Assign error: ${data.detail}`);
        }
    } catch (err) {
        if (err.message !== "Session expired") {
            alert("Manual assignment failed.");
        }
    }
}
