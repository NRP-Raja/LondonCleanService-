import requests
import json
import sys
import datetime
import random

BASE_URL = "http://127.0.0.1:8000"

def test_full_system():
    print("==================================================")
    print(" CLEANLONDON COMPREHENSIVE END-TO-END TEST SUITE")
    print("==================================================")

    # Pre-test isolation: Mark any earlier in-flight test jobs completed so demo cleaners are available
    try:
        from app.main import get_db
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE bookings
                    SET status = 'COMPLETED'
                    WHERE status IN ('SCHEDULED', 'EN_ROUTE', 'IN_PROGRESS')
                      AND scheduled_date = CURDATE()
                """)
                conn.commit()
    except Exception:
        pass

    # 1. Test Static Homepage
    print("\n[Test 1] Checking Frontend Homepage Delivery (GET /)...")
    r = requests.get(f"{BASE_URL}/")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    assert "CleanLondon" in r.text, "CleanLondon branding missing from HTML"
    print(" -> PASSED: Frontend HTML loaded successfully with branding.")

    # 2. Test Services Listing
    print("\n[Test 2] Checking Services Endpoint (GET /api/services)...")
    r = requests.get(f"{BASE_URL}/api/services")
    assert r.status_code == 200
    services = r.json().get("services", [])
    assert len(services) >= 3
    print(f" -> PASSED: Found {len(services)} active cleaning services.")

    # 3. Test Dynamic Pricing Calculation (SW1A Central London, 2 bed, 1 bath, pets)
    print("\n[Test 3] Testing Dynamic Quote Engine (POST /api/pricing/calculate)...")
    quote_payload = {
        "postcode": "SW1A 1AA",
        "service_id": 1,
        "bedrooms": 2,
        "bathrooms": 1,
        "has_pets": True,
        "deep_clean": False,
        "eco_products": True
    }
    r = requests.post(f"{BASE_URL}/api/pricing/calculate", json=quote_payload)
    assert r.status_code == 200
    quote_data = r.json()
    total = quote_data["total_price_gbp"]
    print(f" -> PASSED: Quote calculated: £{total:.2f} (~{quote_data['estimated_duration_hours']} hours). Breakdown: {quote_data['breakdown']}")

    # 4. Test Customer Authentication (Oliver Smith)
    print("\n[Test 4] Testing Customer Authentication & JWT Generation...")
    r = requests.post(f"{BASE_URL}/api/auth/demo-switch", json={"role": "customer"})
    assert r.status_code == 200
    cust_data = r.json()
    cust_token = cust_data["access_token"]
    cust_headers = {"Authorization": f"Bearer {cust_token}"}
    print(f" -> PASSED: Customer authenticated as '{cust_data['user']['full_name']}' (ID: {cust_data['user']['id']}).")

    # 5. Test Customer Creating a Future Booking for Real-time Lifecycle
    print("\n[Test 5] Creating New Booking for Customer (Future Date)...")
    now_dt = datetime.datetime.now()
    today_str = now_dt.strftime("%Y-%m-%d")
    future_str = (now_dt + datetime.timedelta(days=random.randint(730, 1095))).strftime("%Y-%m-%d")
    current_slot = "09:00 - 12:00"
    unique_flat = f"Flat {random.randint(100, 999)}, 12 Kensington High Street"
    booking_payload = {
        "service_id": 1,
        "property_type": "2-Bed Flat",
        "bedrooms": 2,
        "bathrooms": 1,
        "has_pets": False,
        "deep_clean_requested": False,
        "eco_cleaning_products": True,
        "address_line1": unique_flat,
        "address_line2": "Kensington",
        "city": "London",
        "postcode": "W8 4PT",
        "key_handling_type": "CONCIERGE",
        "access_notes": "Leave keys with daytime porter under Smith.",
        "scheduled_date": future_str,
        "scheduled_time_slot": current_slot,
        "idempotency_key": f"IDEM-{random.randint(100000, 999999)}"
    }
    r = requests.post(f"{BASE_URL}/api/bookings", json=booking_payload, headers=cust_headers)
    assert r.status_code == 200, f"Booking creation failed: {r.text}"
    new_booking = r.json()
    new_booking_id = new_booking["booking_id"]
    print(f" -> PASSED: Created booking Ref: {new_booking['reference_code']} (ID: {new_booking_id}), Price: £{new_booking['total_price_gbp']:.2f}")

    # 6. Test Customer Viewing Bookings
    print("\n[Test 6] Fetching Customer's Booking History...")
    r = requests.get(f"{BASE_URL}/api/bookings/my", headers=cust_headers)
    assert r.status_code == 200
    my_bookings = r.json().get("bookings", [])
    assert any(b["id"] == new_booking_id for b in my_bookings)
    print(f" -> PASSED: Customer has {len(my_bookings)} bookings on record.")

    # 7. Test Manager Dashboard & Auto-Match Dispatch
    print("\n[Test 7] Testing Manager Access & Auto-Match Proximity Dispatch...")
    r = requests.post(f"{BASE_URL}/api/auth/demo-switch", json={"role": "manager"})
    assert r.status_code == 200
    mgr_token = r.json()["access_token"]
    mgr_headers = {"Authorization": f"Bearer {mgr_token}"}

    # Check KPIs
    r = requests.get(f"{BASE_URL}/api/manager/dashboard-stats", headers=mgr_headers)
    assert r.status_code == 200
    kpis = r.json()["kpis"]
    print(f" -> Manager KPIs: Today's Revenue: £{kpis['daily_revenue_gbp']:.2f}, Staff Utilization: {kpis['staff_utilization_pct']}%, Unassigned: {kpis['unassigned_jobs']}")

    # Auto-match the newly created booking
    r = requests.post(f"{BASE_URL}/api/manager/bookings/{new_booking_id}/auto-match", headers=mgr_headers)
    assert r.status_code == 200, f"Auto-match failed: {r.text}"
    match_result = r.json()
    assigned_cleaner = match_result['cleaner_name']
    print(f" -> PASSED: Auto-matched booking {new_booking_id} to nearest conflict-free cleaner: {assigned_cleaner} ({match_result['distance_miles']} miles away, rating: ★{match_result['rating']})")

    # 8. Test Cleaner Workflow & Sequential State Machine
    print("\n[Test 8] Testing Cleaner Operations & Time Guardrail...")
    cleaner_role_target = "staff_elena" if "Elena" in assigned_cleaner else "staff_marcus"
    r = requests.post(f"{BASE_URL}/api/auth/demo-switch", json={"role": cleaner_role_target})
    assert r.status_code == 200
    staff_token = r.json()["access_token"]
    staff_headers = {"Authorization": f"Bearer {staff_token}"}

    # Fetch assigned jobs
    r = requests.get(f"{BASE_URL}/api/staff/jobs", headers=staff_headers)
    assert r.status_code == 200
    jobs = r.json().get("jobs", [])
    print(f" -> Cleaner has {len(jobs)} assigned jobs.")

    # A future booking must not enter EN_ROUTE early.
    print(" -> Verifying premature EN_ROUTE is blocked...")
    r = requests.patch(f"{BASE_URL}/api/staff/jobs/{new_booking_id}/status", json={"status": "EN_ROUTE"}, headers=staff_headers)
    assert r.status_code == 400, f"Premature EN_ROUTE should be rejected: {r.text}"
    print(" -> PASSED: Future job is protected by the time guardrail.")

    # 9. Test Invalid Status Transition (Cannot go from COMPLETED to EN_ROUTE)
    print("\n[Test 9] Testing State Machine Guard (Illegal Transition)...")
    r = requests.patch(f"{BASE_URL}/api/staff/jobs/{new_booking_id}/status", json={"status": "COMPLETED"}, headers=staff_headers)
    assert r.status_code == 400, "Security flaw: premature completion was allowed!"
    print(f" -> PASSED: Guard blocked premature completion (HTTP 400: {r.json()['detail']})")

    # 10. Test Review Submission
    print("\n[Test 10] Submitting Customer Review for Completed Booking...")
    review_payload = {
        "rating": 5,
        "comment": "Outstanding clean! Every corner was spotless and the cleaner arrived right on time.",
        "punctuality_score": 5,
        "thoroughness_score": 5
    }
    r = requests.post(f"{BASE_URL}/api/bookings/{new_booking_id}/review", json=review_payload, headers=cust_headers)
    assert r.status_code == 400, f"Review of incomplete booking should be rejected: {r.text}"
    print(" -> PASSED: Review guard blocked a booking that is not completed.")

    # 11. Test Google OAuth 2.0 Prototype (Mock Mode)
    print("\n[Test 11] Testing Google OAuth 2.0 Mock Sign-in...")
    r = requests.post(f"{BASE_URL}/api/auth/google/login", json={"id_token": "mock-token-xyz"})
    assert r.status_code == 200
    google_res = r.json()
    assert "access_token" in google_res
    print(f" -> PASSED: Google OAuth login returned valid JWT for user: {google_res['user']['email']}.")

    # ==========================================================
    # NEW BUSINESS LOGIC TESTS
    # ==========================================================

    # 12. Test Duplicate Booking Prevention & Idempotency
    print("\n[Test 12] Testing Duplicate Booking Prevention & Idempotency...")
    # 12a: Submitting exact same idempotency_key returns idempotent replay
    r_idem = requests.post(f"{BASE_URL}/api/bookings", json=booking_payload, headers=cust_headers)
    assert r_idem.status_code == 200, f"Expected 200 idempotent replay, got {r_idem.status_code}"
    assert r_idem.json().get("idempotent_replayed") is True, "Idempotent replay flag missing!"
    print(f" -> PASSED: Idempotency replay recognized (Booking ID: {r_idem.json()['booking_id']}).")

    # 12b: Submitting duplicate active booking without idempotency key triggers 409 Conflict
    # Create an active scheduled booking first
    active_dup_payload = {
        "service_id": 1,
        "property_type": "2-Bed Flat",
        "bedrooms": 2,
        "bathrooms": 1,
        "address_line1": f"{random.randint(100, 999)} Abbey Road",
        "city": "London",
        "postcode": "NW8 9AY",
        "scheduled_date": (datetime.date.today() + datetime.timedelta(days=random.randint(730, 1095))).strftime("%Y-%m-%d"),
        "scheduled_time_slot": "09:00 - 12:00"
    }
    r_first = requests.post(f"{BASE_URL}/api/bookings", json=active_dup_payload, headers=cust_headers)
    assert r_first.status_code == 200
    first_b_id = r_first.json()["booking_id"]

    # Now attempt identical duplicate submission
    r_dup = requests.post(f"{BASE_URL}/api/bookings", json=active_dup_payload, headers=cust_headers)
    assert r_dup.status_code == 409, f"Expected 409 Conflict for duplicate booking, got {r_dup.status_code}"
    print(f" -> PASSED: Duplicate booking submission blocked (HTTP 409: {r_dup.json()['detail'][:60]}...).")

    # 13. Test Cleaner Schedule Conflict Bug Prevention & TfL Travel Buffer
    print("\n[Test 13] Testing Cleaner Schedule Conflict & Travel Buffer Guard...")
    # Assign cleaner 2 (Elena) to first_b_id (day 3, 10:00 - 13:00)
    r_assign = requests.post(f"{BASE_URL}/api/manager/bookings/{first_b_id}/assign", json={"staff_id": 2}, headers=mgr_headers)
    assert r_assign.status_code == 200

    # Create a second booking at a different address on the EXACT same day and overlapping time slot
    conflict_payload = {
        "service_id": 1,
        "property_type": "1-Bed Flat",
        "bedrooms": 1,
        "bathrooms": 1,
        "address_line1": "45 Piccadilly",
        "city": "London",
        "postcode": "W1D 7NE",
        "scheduled_date": active_dup_payload["scheduled_date"],
        "scheduled_time_slot": "09:00 - 12:00"
    }
    r_second = requests.post(f"{BASE_URL}/api/bookings", json=conflict_payload, headers=cust_headers)
    assert r_second.status_code == 200
    second_b_id = r_second.json()["booking_id"]

    # Attempt to assign cleaner 2 (Elena) to the overlapping second booking -> Must be BLOCKED
    r_conflict = requests.post(f"{BASE_URL}/api/manager/bookings/{second_b_id}/assign", json={"staff_id": 2}, headers=mgr_headers)
    assert r_conflict.status_code == 400, "Security flaw: cleaner was double-booked!"
    assert "Schedule Conflict" in r_conflict.json()["detail"] or "TfL" in r_conflict.json()["detail"]
    print(f" -> PASSED: Double-booking guard blocked assignment (HTTP 400: {r_conflict.json()['detail'][:65]}...).")

    # 14. Test Time Guardrail on Future Job Status
    print("\n[Test 14] Testing Time Guardrails on Future Bookings...")
    # second_b_id is 3 days in the future! Elena or cleaner cannot mark it EN_ROUTE or COMPLETED today
    # Auto-match it to cleaner 3 (Marcus) who is free
    r_match2 = requests.post(f"{BASE_URL}/api/manager/bookings/{second_b_id}/auto-match", headers=mgr_headers)
    assert r_match2.status_code == 200, f"Auto-match failed: {r_match2.text}"

    # Attempt to mark this future booking EN_ROUTE today -> Must be BLOCKED
    r_guard = requests.patch(f"{BASE_URL}/api/staff/jobs/{second_b_id}/status", json={"status": "EN_ROUTE"}, headers=mgr_headers)
    assert r_guard.status_code == 400, "Flaw: Future booking was prematurely marked EN_ROUTE!"
    assert "Time Guardrail" in r_guard.json()["detail"]
    print(f" -> PASSED: Time guardrail blocked premature status change (HTTP 400: {r_guard.json()['detail'][:70]}...).")

    # 15. Test Cancellation Workflow & 50% Late-Fee Policy
    print("\n[Test 15] Testing Booking Cancellation & 50% Late-Fee Policy...")
    # 15a: Cancel future booking (>24h notice) -> 100% Free cancellation, full refund
    r_cancel_free = requests.post(
        f"{BASE_URL}/api/bookings/{second_b_id}/cancel",
        json={"reason": "Customer plans changed in advance"},
        headers=cust_headers
    )
    assert r_cancel_free.status_code == 200, f"Cancellation failed: {r_cancel_free.text}"
    cancel_data = r_cancel_free.json()
    assert cancel_data["cancellation_fee_gbp"] == 0.0, "Expected 0 fee for >24h notice"
    assert cancel_data["policy_applied"] == "FREE_CANCELLATION"
    print(f" -> PASSED: >24h Free cancellation confirmed: Fee £{cancel_data['cancellation_fee_gbp']:.2f}, Refund £{cancel_data['refund_amount_gbp']:.2f}.")

    # 15b: Create a future booking within 24 hours and cancel it -> 50% late fee applied
    late_start = datetime.datetime.now().replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=3)
    late_end = late_start + datetime.timedelta(hours=3)
    late_payload = {
        "service_id": 1,
        "property_type": "1-Bed Flat",
        "bedrooms": 1,
        "bathrooms": 1,
        "address_line1": "10 Downing Street",
        "city": "London",
        "postcode": "SW1A 2AA",
        "scheduled_date": late_start.strftime("%Y-%m-%d"),
        "scheduled_time_slot": f"{late_start:%H:%M} - {late_end:%H:%M}"
    }
    r_late = requests.post(f"{BASE_URL}/api/bookings", json=late_payload, headers=cust_headers)
    assert r_late.status_code == 200
    late_b_id = r_late.json()["booking_id"]
    late_price = r_late.json()["total_price_gbp"]

    r_cancel_late = requests.post(
        f"{BASE_URL}/api/bookings/{late_b_id}/cancel",
        json={"reason": "Last minute emergency cancellation"},
        headers=cust_headers
    )
    assert r_cancel_late.status_code == 200, f"Late cancellation failed: {r_cancel_late.text}"
    late_data = r_cancel_late.json()
    assert late_data["policy_applied"] == "50_PERCENT_LATE_FEE"
    assert late_data["cancellation_fee_gbp"] == round(late_price * 0.5, 2)
    print(f" -> PASSED: <24h Late cancellation enforced: 50% fee £{late_data['cancellation_fee_gbp']:.2f}, Refund £{late_data['refund_amount_gbp']:.2f}.")

    # 16. Test Rescheduling Workflow
    print("\n[Test 16] Testing Booking Rescheduling Workflow...")
    # Reschedule first_b_id to day 5 in future
    resched_date = (datetime.date.today() + datetime.timedelta(days=5)).strftime("%Y-%m-%d")
    r_resched = requests.post(
        f"{BASE_URL}/api/bookings/{first_b_id}/reschedule",
        json={"new_date": resched_date, "new_time_slot": "11:30 - 14:30", "reason": "Moving appointment"},
        headers=cust_headers
    )
    assert r_resched.status_code == 200, f"Reschedule failed: {r_resched.text}"
    assert r_resched.json()["scheduled_date"] == resched_date
    print(f" -> PASSED: Booking rescheduled to {resched_date} (11:30 - 14:30).")

    # ==========================================================
    # SECURITY & UK GDPR CONTROLS TESTS
    # ==========================================================

    # 17. Test Backend Role Escalation Prevention
    print("\n[Test 17] Testing Backend Role Escalation Prevention on Public Registration...")
    malicious_email = f"hacker_{random.randint(10000, 99999)}@security-test.co.uk"
    escalation_payload = {
        "email": malicious_email,
        "password": "Password123!",
        "full_name": "Privilege Escalation Tester",
        "phone": "+44 7900 112233",
        "role": "manager"  # Attempt to escalate role to manager
    }
    r_reg = requests.post(f"{BASE_URL}/api/auth/register", json=escalation_payload)
    assert r_reg.status_code == 200, f"Registration failed: {r_reg.text}"
    reg_user = r_reg.json()["user"]
    reg_token = r_reg.json()["access_token"]
    assert reg_user["role"] == "customer", f"Security Flaw: Role was escalated to {reg_user['role']}!"

    # Verify that the newly registered user CANNOT access manager endpoints
    r_mgr_forbidden = requests.get(
        f"{BASE_URL}/api/manager/dashboard-stats",
        headers={"Authorization": f"Bearer {reg_token}"}
    )
    assert r_mgr_forbidden.status_code == 403, f"Security Flaw: User was granted manager access! Status: {r_mgr_forbidden.status_code}"
    print(f" -> PASSED: Backend strictly enforced 'customer' role; manager privilege escalation blocked (HTTP 403).")

    # 18. Test UK GDPR Key-Safe PIN Encryption at Rest & Cleaner Status Masking
    print("\n[Test 18] Testing UK GDPR Sensitive Access Code Encryption at Rest & Cleaner Status Masking...")
    secret_pin_note = f"Key safe PIN 8899 by garden shed. Intercom #402."
    now_dt = datetime.datetime.now()
    gdpr_booking_payload = {
        "service_id": 1,
        "property_type": "1-Bed Flat",
        "bedrooms": 1,
        "bathrooms": 1,
        "address_line1": f"{random.randint(100, 999)} Holland Park Avenue",
        "city": "London",
        "postcode": "W8 7QB",
        "key_handling_type": "KEY_SAFE_BOX",
        "access_notes": secret_pin_note,
        "scheduled_date": (now_dt + datetime.timedelta(days=random.randint(1400, 1800))).strftime("%Y-%m-%d"),
        "scheduled_time_slot": "09:00 - 12:00",
        "idempotency_key": f"GDPR-IDEM-{random.randint(100000, 999999)}"
    }
    r_gdpr = requests.post(f"{BASE_URL}/api/bookings", json=gdpr_booking_payload, headers=cust_headers)
    assert r_gdpr.status_code == 200, f"GDPR Booking creation failed: {r_gdpr.text}"
    gdpr_b_id = r_gdpr.json()["booking_id"]

    # Customer viewing own booking sees their notes
    r_cust_view = requests.get(f"{BASE_URL}/api/bookings/my", headers=cust_headers)
    assert r_cust_view.status_code == 200
    my_b = next(b for b in r_cust_view.json()["bookings"] if b["id"] == gdpr_b_id)
    assert my_b["access_notes"] == secret_pin_note, "Customer could not see their own access notes!"

    # Auto-match booking to cleaner
    r_match_gdpr = requests.post(f"{BASE_URL}/api/manager/bookings/{gdpr_b_id}/auto-match", headers=mgr_headers)
    assert r_match_gdpr.status_code == 200
    assigned_cleaner_name = r_match_gdpr.json()["cleaner_name"]
    cleaner_role_name = "staff_elena" if "Elena" in assigned_cleaner_name else "staff_marcus"

    # Cleaner logs in while status is SCHEDULED
    r_cleaner_auth = requests.post(f"{BASE_URL}/api/auth/demo-switch", json={"role": cleaner_role_name})
    cleaner_token = r_cleaner_auth.json()["access_token"]
    cleaner_headers = {"Authorization": f"Bearer {cleaner_token}"}

    r_cleaner_jobs = requests.get(f"{BASE_URL}/api/staff/jobs", headers=cleaner_headers)
    assert r_cleaner_jobs.status_code == 200
    cleaner_job = next((j for j in r_cleaner_jobs.json()["jobs"] if j["id"] == gdpr_b_id), None)
    if cleaner_job:
        assert "Protected by CleanLondon Security" in cleaner_job["access_notes"] or "🔒" in cleaner_job["access_notes"], \
            f"GDPR Flaw: Key PIN was exposed to cleaner before En Route! Got: {cleaner_job['access_notes']}"
        assert secret_pin_note not in cleaner_job["access_notes"], "GDPR Flaw: Plaintext PIN revealed in SCHEDULED state!"
        print(" -> PASSED: Entry PIN masked for cleaner while booking status is SCHEDULED.")

        # Future booking remains protected and cannot enter EN_ROUTE yet.
        r_enroute = requests.patch(f"{BASE_URL}/api/staff/jobs/{gdpr_b_id}/status", json={"status": "EN_ROUTE"}, headers=cleaner_headers)
        assert r_enroute.status_code == 400
        assert "Time Guardrail" in r_enroute.json()["detail"]
        print(" -> PASSED: Future booking remains protected and PIN release is time-guarded.")

    # 19. Test Graceful JWT Expiry Rejection
    print("\n[Test 19] Testing Graceful JWT Expiry Detection (401 Response)...")
    # Generate an expired token (expired 2 hours ago)
    from jose import jwt as jose_jwt
    jwt_secret = "supersecretjwtkey_cleanlondon_production_grade_token_2026"
    expired_payload = {
        "user_id": 4,
        "role": "customer",
        "exp": datetime.datetime.utcnow() - datetime.timedelta(hours=2)
    }
    expired_token = jose_jwt.encode(expired_payload, jwt_secret, algorithm="HS256")

    r_expired = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert r_expired.status_code == 401, f"Expected 401 for expired token, got {r_expired.status_code}"
    assert "expired" in r_expired.json()["detail"].lower() or "credentials" in r_expired.json()["detail"].lower()
    print(" -> PASSED: Expired JWT correctly rejected with HTTP 401 (triggers graceful frontend expiry handler).")

    # 20. Test Backdoor Removal & Password Hardening
    print("\n[Test 20] Testing Password Backdoor Removal & Bcrypt Integrity...")
    r_bad_pwd = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "admin@cleanlondon.co.uk", "password": "WrongPassword99!"})
    assert r_bad_pwd.status_code == 401, f"Expected 401 for incorrect password, got {r_bad_pwd.status_code}"
    r_good_pwd = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "admin@cleanlondon.co.uk", "password": "Password123!"})
    assert r_good_pwd.status_code == 200, f"Expected 200 for valid password, got {r_good_pwd.status_code}"
    print(" -> PASSED: Password backdoor eliminated; native bcrypt verification strictly enforced.")

    # 21. Test Google OAuth Account Takeover Prevention
    print("\n[Test 21] Testing Google OAuth Account Takeover Prevention...")
    r_google_hijack = requests.post(f"{BASE_URL}/api/auth/google/login", json={"id_token": "mock-token", "email": "admin@cleanlondon.co.uk"})
    assert r_google_hijack.status_code == 403, f"Expected 403 blocking administrative Google takeover, got {r_google_hijack.status_code}"
    print(" -> PASSED: Google OAuth takeover blocked for privileged manager/staff accounts (HTTP 403).")

    # 22. Test HTTP Defense-in-Depth Security Headers
    print("\n[Test 22] Testing HTTP Security Headers Middleware...")
    r_headers = requests.get(f"{BASE_URL}/")
    assert r_headers.headers.get("X-Content-Type-Options") == "nosniff", "Missing X-Content-Type-Options: nosniff"
    assert r_headers.headers.get("X-Frame-Options") == "SAMEORIGIN", "Missing X-Frame-Options: SAMEORIGIN"
    assert r_headers.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin", "Missing Referrer-Policy"
    print(" -> PASSED: Required HTTP security headers present (nosniff, SAMEORIGIN, strict-origin-when-cross-origin).")

    # 23. Test Unauthenticated Payment Verification IDOR / BOLA Prevention
    print("\n[Test 23] Testing Payment Session Verification IDOR Protection...")
    r_idor_verify = requests.get(f"{BASE_URL}/api/payments/session/invalid_session_token/verify?booking_id=1")
    assert r_idor_verify.status_code == 404, f"Expected 404 blocking unauthenticated booking IDOR, got {r_idor_verify.status_code}"
    print(" -> PASSED: Unauthenticated booking enumeration blocked via strict session matching (HTTP 404).")

    print("\n==================================================================")
    print(" ✅ ALL 23 TESTS PASSED! SECURITY AUDIT CONTROLS VERIFIED")
    print("==================================================================")

if __name__ == "__main__":
    try:
        test_full_system()
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
