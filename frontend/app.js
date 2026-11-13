// ==========================================================
// CleanLondon Vanilla JS Client
// End-to-end dynamic frontend logic for 3 distinct user roles
// ==========================================================

const API_BASE = ""; // Relative to FastAPI host

let state = {
    token: null,
    user: {
        id: 4,
        email: "oliver.smith@example.co.uk",
        full_name: "Oliver Smith",
        role: "customer"
    },
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
    activeJobForMap: null
};

// ==========================================================
// INITIALIZATION
// ==========================================================
document.addEventListener("DOMContentLoaded", async () => {
    // Set default booking date to tomorrow
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const dateInput = document.getElementById("book-date");
    if (dateInput) {
        dateInput.value = tomorrow.toISOString().split("T")[0];
    }

    // Initialize with Customer role token
    await switchRole("customer");
    recalculateQuote();
});

// ==========================================================
// ROLE SWITCHING & AUTH
// ==========================================================
async function switchRole(roleName) {
    // Update active button state
    document.querySelectorAll(".role-btn").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.role === roleName);
    });

    try {
        const response = await fetch(`${API_BASE}/api/auth/demo-switch`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ role: roleName })
        });
        const data = await response.json();
        if (response.ok) {
            state.token = data.access_token;
            state.user = data.user;
            localStorage.setItem("cleanlondon_token", data.access_token);
            updateUserHeaderDisplay();

            // Automatically navigate to relevant view
            if (roleName === "customer") {
                switchView("customer-dashboard");
                loadCustomerBookings();
            } else if (roleName === "staff") {
                switchView("staff-dashboard");
                loadStaffJobs();
            } else if (roleName === "manager") {
                switchView("manager-dashboard");
                loadManagerData();
            }
        }
    } catch (err) {
        console.error("Role switch error:", err);
    }
}

function updateUserHeaderDisplay() {
    const displayEl = document.getElementById("current-user-display");
    const authBtn = document.getElementById("auth-btn");
    const greetingEl = document.getElementById("customer-greeting-name");
    const staffProfileEl = document.getElementById("staff-profile-name");

    if (state.user) {
        const roleLabel = state.user.role.charAt(0).toUpperCase() + state.user.role.slice(1);
        displayEl.textContent = `Logged in as: ${state.user.full_name} (${roleLabel})`;
        if (authBtn) authBtn.textContent = `Sign Out (${state.user.full_name.split(' ')[0]})`;
        if (greetingEl) greetingEl.textContent = state.user.full_name.split(' ')[0];
        if (staffProfileEl) staffProfileEl.textContent = state.user.full_name;
    }
}

function switchView(viewName) {
    document.querySelectorAll(".view-panel").forEach(panel => panel.classList.remove("active"));
    const target = document.getElementById(`${viewName}-view`);
    if (target) {
        target.classList.add("active");
        window.scrollTo({ top: 0, behavior: "smooth" });
    }
}

function handleDashboardClick() {
    if (state.user.role === "customer") {
        switchView("customer-dashboard");
        loadCustomerBookings();
    } else if (state.user.role === "staff") {
        switchView("staff-dashboard");
        loadStaffJobs();
    } else if (state.user.role === "manager") {
        switchView("manager-dashboard");
        loadManagerData();
    }
}

function scrollToQuote() {
    switchView("landing");
    setTimeout(() => {
        document.getElementById("quote-section").scrollIntoView({ behavior: "smooth" });
    }, 100);
}

// ==========================================================
// DYNAMIC PRICING ENGINE
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
// CUSTOMER BOOKING FLOW & MODALS
// ==========================================================
function openBookingModal() {
    const bookPostcode = document.getElementById("book-postcode");
    if (bookPostcode) {
        bookPostcode.value = state.quote.postcode;
    }
    document.getElementById("booking-modal").classList.add("active");
}

function closeBookingModal() {
    document.getElementById("booking-modal").classList.remove("active");
}

async function submitNewBooking(e) {
    e.preventDefault();
    const addressLine1 = document.getElementById("book-address1").value;
    const addressLine2 = document.getElementById("book-address2").value;
    const postcode = document.getElementById("book-postcode").value;
    const scheduledDate = document.getElementById("book-date").value;
    const scheduledTime = document.getElementById("book-timeslot").value;
    const keyHandling = document.getElementById("book-key-handling").value;
    const notes = document.getElementById("book-access-notes").value;

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
        scheduled_time_slot: scheduledTime
    };

    try {
        const res = await fetch(`${API_BASE}/api/bookings`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${state.token}`
            },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (res.ok) {
            closeBookingModal();
            alert(`🎉 Booking Confirmed! Ref: ${data.reference_code}. Total: £${data.total_price_gbp.toFixed(2)}`);
            switchView("customer-dashboard");
            loadCustomerBookings();
        } else {
            alert(`Error: ${data.detail || "Could not complete booking"}`);
        }
    } catch (err) {
        alert("Booking submission failed. Please try again.");
    }
}

async function loadCustomerBookings() {
    const listBody = document.getElementById("customer-bookings-list");
    listBody.innerHTML = `<tr><td colspan="8" class="text-center">Loading your London bookings...</td></tr>`;

    try {
        const res = await fetch(`${API_BASE}/api/bookings/my`, {
            headers: { "Authorization": `Bearer ${state.token}` }
        });
        const data = await res.json();
        if (res.ok) {
            if (!data.bookings || data.bookings.length === 0) {
                listBody.innerHTML = `<tr><td colspan="8" class="text-center">No bookings found. Click "Book a Clean" to schedule one!</td></tr>`;
                return;
            }

            listBody.innerHTML = data.bookings.map(b => {
                let actionBtn = "";
                if (b.status === "COMPLETED" && !b.review_rating) {
                    actionBtn = `<button class="btn btn-sm btn-primary" onclick="openReviewModal(${b.id})"><i class="fa-solid fa-star"></i> Review</button>`;
                } else if (b.review_rating) {
                    actionBtn = `<span class="text-gold">★ ${b.review_rating}/5 Rated</span>`;
                } else {
                    actionBtn = `<span class="text-muted"><i class="fa-solid fa-clock"></i> Active</span>`;
                }

                return `
                    <tr>
                        <td><strong>${b.reference_code}</strong></td>
                        <td>${b.service_name}</td>
                        <td>${b.scheduled_date}<br><small class="text-muted">${b.scheduled_time_slot}</small></td>
                        <td>${b.address_line1}, ${b.postcode}</td>
                        <td>${b.staff_name ? b.staff_name : '<em class="text-muted">Allocating...</em>'}</td>
                        <td><strong>£${parseFloat(b.total_price_gbp).toFixed(2)}</strong></td>
                        <td><span class="status-badge ${b.status}">${b.status.replace('_', ' ')}</span></td>
                        <td>${actionBtn}</td>
                    </tr>
                `;
            }).join("");
        }
    } catch (err) {
        console.error("Load customer bookings err:", err);
    }
}

// ==========================================================
// REVIEWS
// ==========================================================
function openReviewModal(bookingId) {
    document.getElementById("review-booking-id").value = bookingId;
    document.getElementById("review-modal").classList.add("active");
}

function closeReviewModal() {
    document.getElementById("review-modal").classList.remove("active");
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
        const res = await fetch(`${API_BASE}/api/bookings/${bookingId}/review`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${state.token}`
            },
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
        alert("Failed to save review.");
    }
}

// ==========================================================
// STAFF / CLEANER WORKFLOW & MAP
// ==========================================================
async function loadStaffJobs() {
    const container = document.getElementById("staff-jobs-container");
    container.innerHTML = `<div class="p-4 text-center">Loading assigned tasks...</div>`;

    try {
        const res = await fetch(`${API_BASE}/api/staff/jobs`, {
            headers: { "Authorization": `Bearer ${state.token}` }
        });
        const data = await res.json();
        if (res.ok) {
            if (!data.jobs || data.jobs.length === 0) {
                container.innerHTML = `<div class="p-4 text-center text-muted">No jobs assigned today. Stand by for dispatch.</div>`;
                return;
            }

            container.innerHTML = data.jobs.map(j => {
                // Next valid status
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

                return `
                    <div class="job-card ${state.activeJobForMap?.id === j.id ? 'active-selected' : ''}" onclick="selectJobForMap(${JSON.stringify(j).replace(/"/g, '&quot;')})">
                        <div class="job-card-header">
                            <span class="job-card-title">${j.reference_code} • ${j.service_name}</span>
                            <span class="status-badge ${j.status}">${j.status.replace('_', ' ')}</span>
                        </div>
                        <div class="job-card-address">
                            <i class="fa-solid fa-location-dot text-emerald"></i> ${j.address_line1}, ${j.postcode} (${j.bedrooms} Bed, ${j.bathrooms} Bath)
                        </div>
                        <div style="font-size:0.8rem; color:#64748b; margin-bottom:8px;">
                            <strong>Customer:</strong> ${j.customer_name} (${j.customer_phone})<br>
                            <strong>Key Handover:</strong> ${j.key_handling_type} (${j.access_notes || 'No special notes'})
                        </div>
                        <div class="job-actions-row">
                            ${nextActionBtn}
                            <button class="btn btn-sm btn-outline" onclick="selectJobForMap(${JSON.stringify(j).replace(/"/g, '&quot;')})"><i class="fa-solid fa-map-pin"></i> View Route</button>
                        </div>
                    </div>
                `;
            }).join("");

            // Select first job for map
            if (data.jobs.length > 0 && !state.activeJobForMap) {
                selectJobForMap(data.jobs[0]);
            }
        }
    } catch (err) {
        console.error("Staff jobs error:", err);
    }
}

async function advanceJobStatus(bookingId, targetStatus) {
    try {
        const res = await fetch(`${API_BASE}/api/staff/jobs/${bookingId}/status`, {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${state.token}`
            },
            body: JSON.stringify({ status: targetStatus, notes: `Status updated by cleaner` })
        });
        const data = await res.json();
        if (res.ok) {
            alert(`Job status progressed to: ${targetStatus}`);
            loadStaffJobs();
        } else {
            alert(`Could not update status: ${data.detail}`);
        }
    } catch (err) {
        alert("Failed to advance status.");
    }
}

function selectJobForMap(job) {
    state.activeJobForMap = job;
    document.getElementById("pin-postcode-text").textContent = `${job.postcode}`;
    document.getElementById("map-active-job-info").innerHTML = `
        <h4>${job.reference_code}: ${job.customer_name}</h4>
        <p><i class="fa-solid fa-location-dot"></i> ${job.address_line1}, London ${job.postcode}</p>
        <p><i class="fa-solid fa-key"></i> Key: ${job.key_handling_type} — "${job.access_notes || 'Handover in person'}"</p>
    `;
    document.getElementById("transit-summary").innerHTML = `
        <i class="fa-solid fa-train-subway"></i> <strong>TfL Transit:</strong> Estimated ~15-20 mins travel from base to <strong>${job.postcode}</strong>.
    `;
    loadStaffJobs();
}

// ==========================================================
// MANAGER DASHBOARD & DISPATCH OPERATIONS
// ==========================================================
async function loadManagerData() {
    loadManagerKPIs();
    loadManagerBookings();
}

async function loadManagerKPIs() {
    try {
        const res = await fetch(`${API_BASE}/api/manager/dashboard-stats`, {
            headers: { "Authorization": `Bearer ${state.token}` }
        });
        const data = await res.json();
        if (res.ok) {
            document.getElementById("kpi-daily-rev").textContent = `£${data.kpis.daily_revenue_gbp.toFixed(2)}`;
            document.getElementById("kpi-monthly-rev").textContent = `£${data.kpis.total_revenue_gbp.toFixed(2)}`;
            document.getElementById("kpi-utilization").textContent = `${data.kpis.staff_utilization_pct}%`;
            document.getElementById("kpi-active-cleaners").textContent = data.kpis.active_cleaners_today;
            document.getElementById("kpi-unassigned-count").textContent = data.kpis.unassigned_jobs;
        }
    } catch (err) {
        console.error("Manager KPIs error:", err);
    }
}

async function loadManagerBookings() {
    const filter = document.getElementById("manager-status-filter").value;
    const tableBody = document.getElementById("manager-bookings-list");
    tableBody.innerHTML = `<tr><td colspan="9" class="text-center">Loading platform bookings...</td></tr>`;

    try {
        const res = await fetch(`${API_BASE}/api/manager/bookings?status_filter=${filter}`, {
            headers: { "Authorization": `Bearer ${state.token}` }
        });
        const data = await res.json();
        if (res.ok) {
            if (!data.bookings || data.bookings.length === 0) {
                tableBody.innerHTML = `<tr><td colspan="9" class="text-center">No bookings found for filter: ${filter}</td></tr>`;
                return;
            }

            tableBody.innerHTML = data.bookings.map(b => {
                let actionControls = "";
                if (!b.staff_id) {
                    actionControls = `
                        <button class="btn btn-sm btn-primary" onclick="autoMatchCleaner(${b.id})" title="Auto-match nearest cleaner">
                            <i class="fa-solid fa-bolt"></i> Auto-Match
                        </button>
                    `;
                } else {
                    actionControls = `
                        <select onchange="manuallyReassign(${b.id}, this.value)" style="font-size:0.75rem; padding:4px;">
                            <option value="">Reassign...</option>
                            <option value="2">Elena Petrova (SE1)</option>
                            <option value="3">Marcus Sterling (NW1)</option>
                        </select>
                    `;
                }

                return `
                    <tr>
                        <td><strong>${b.reference_code}</strong></td>
                        <td>${b.customer_name}<br><small class="text-muted">${b.customer_phone}</small></td>
                        <td><span class="badge-trust" style="margin:0; padding:2px 6px;">${b.postcode}</span></td>
                        <td>${b.service_name}</td>
                        <td>${b.scheduled_date}<br><small>${b.scheduled_time_slot}</small></td>
                        <td><strong>£${parseFloat(b.total_price_gbp).toFixed(2)}</strong></td>
                        <td><span class="status-badge ${b.status}">${b.status.replace('_', ' ')}</span></td>
                        <td>${b.staff_name ? b.staff_name : '<span style="color:#e11d48; font-weight:700;"><i class="fa-solid fa-circle-exclamation"></i> Unassigned</span>'}</td>
                        <td>${actionControls}</td>
                    </tr>
                `;
            }).join("");
        }
    } catch (err) {
        console.error("Manager bookings load error:", err);
    }
}

async function autoMatchCleaner(bookingId) {
    try {
        const res = await fetch(`${API_BASE}/api/manager/bookings/${bookingId}/auto-match`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${state.token}` }
        });
        const data = await res.json();
        if (res.ok) {
            alert(`⚡ ${data.message} (${data.distance_miles} miles away, ★${data.rating})`);
            loadManagerData();
        } else {
            alert(`Auto-match error: ${data.detail}`);
        }
    } catch (err) {
        alert("Failed to auto-match cleaner.");
    }
}

async function manuallyReassign(bookingId, staffId) {
    if (!staffId) return;
    try {
        const res = await fetch(`${API_BASE}/api/manager/bookings/${bookingId}/assign`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${state.token}`
            },
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
        alert("Manual assignment failed.");
    }
}

// ==========================================================
// GOOGLE OAUTH 2.0 PROTOCOL & MOCK SIGN-IN
// ==========================================================
function toggleAuthModal() {
    const modal = document.getElementById("auth-modal");
    modal.classList.toggle("active");
}

async function triggerGoogleSignIn() {
    try {
        const res = await fetch(`${API_BASE}/api/auth/google/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                id_token: "mock-google-id-token-" + Date.now(),
                email: "london.resident@googlemail.com",
                name: "London Resident"
            })
        });
        const data = await res.json();
        if (res.ok) {
            state.token = data.access_token;
            state.user = data.user;
            toggleAuthModal();
            updateUserHeaderDisplay();
            alert(`👋 Signed in via Google OAuth 2.0 as ${data.user.full_name} (${data.is_mock ? 'Mock Mode' : 'Live'})`);
            switchView("customer-dashboard");
            loadCustomerBookings();
        }
    } catch (err) {
        alert("Google Sign-In failed.");
    }
}

async function handleManualLogin(e) {
    e.preventDefault();
    const email = document.getElementById("login-email").value;
    const password = document.getElementById("login-password").value;

    try {
        const res = await fetch(`${API_BASE}/api/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password })
        });
        const data = await res.json();
        if (res.ok) {
            state.token = data.access_token;
            state.user = data.user;
            toggleAuthModal();
            updateUserHeaderDisplay();
            alert(`Welcome back, ${data.user.full_name}!`);
            handleDashboardClick();
        } else {
            alert(`Login failed: ${data.detail || "Invalid credentials"}`);
        }
    } catch (err) {
        alert("Authentication error.");
    }
}
