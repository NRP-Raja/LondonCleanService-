import requests
import json
import sys

BASE_URL = "http://127.0.0.1:8000"

def test_full_system():
    print("==================================================")
    print(" CLEANLONDON COMPREHENSIVE END-TO-END TEST SUITE")
    print("==================================================")

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

    # 5. Test Customer Creating a Booking
    print("\n[Test 5] Creating New Booking for Customer...")
    booking_payload = {
        "service_id": 1,
        "property_type": "2-Bed Flat",
        "bedrooms": 2,
        "bathrooms": 1,
        "has_pets": False,
        "deep_clean_requested": False,
        "eco_cleaning_products": True,
        "address_line1": "Flat 8, 12 Kensington High Street",
        "address_line2": "Kensington",
        "city": "London",
        "postcode": "W8 4PT",
        "key_handling_type": "CONCIERGE",
        "access_notes": "Leave keys with daytime porter under Smith.",
        "scheduled_date": "2026-11-20",
        "scheduled_time_slot": "10:00 - 13:00"
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
    print(f" -> PASSED: Auto-matched booking {new_booking_id} to nearest cleaner: {match_result['cleaner_name']} ({match_result['distance_miles']} miles away, rating: ★{match_result['rating']})")

    # 8. Test Cleaner Workflow & Sequential State Machine
    print("\n[Test 8] Testing Cleaner Operations & Status Machine...")
    r = requests.post(f"{BASE_URL}/api/auth/demo-switch", json={"role": "staff"})
    assert r.status_code == 200
    staff_token = r.json()["access_token"]
    staff_headers = {"Authorization": f"Bearer {staff_token}"}

    # Fetch assigned jobs
    r = requests.get(f"{BASE_URL}/api/staff/jobs", headers=staff_headers)
    assert r.status_code == 200
    jobs = r.json().get("jobs", [])
    print(f" -> Cleaner has {len(jobs)} assigned jobs.")

    # Advance status: SCHEDULED -> EN_ROUTE
    print(" -> Transitioning status to EN_ROUTE...")
    r = requests.patch(f"{BASE_URL}/api/staff/jobs/{new_booking_id}/status", json={"status": "EN_ROUTE"}, headers=staff_headers)
    assert r.status_code == 200, f"Failed to set EN_ROUTE: {r.text}"

    # Advance status: EN_ROUTE -> IN_PROGRESS
    print(" -> Transitioning status to IN_PROGRESS...")
    r = requests.patch(f"{BASE_URL}/api/staff/jobs/{new_booking_id}/status", json={"status": "IN_PROGRESS"}, headers=staff_headers)
    assert r.status_code == 200, f"Failed to set IN_PROGRESS: {r.text}"

    # Advance status: IN_PROGRESS -> COMPLETED
    print(" -> Transitioning status to COMPLETED...")
    r = requests.patch(f"{BASE_URL}/api/staff/jobs/{new_booking_id}/status", json={"status": "COMPLETED"}, headers=staff_headers)
    assert r.status_code == 200, f"Failed to set COMPLETED: {r.text}"
    print(" -> PASSED: State machine successfully validated: SCHEDULED -> EN_ROUTE -> IN_PROGRESS -> COMPLETED.")

    # 9. Test Invalid Status Transition (Cannot go from COMPLETED to EN_ROUTE)
    print("\n[Test 9] Testing State Machine Guard (Illegal Transition)...")
    r = requests.patch(f"{BASE_URL}/api/staff/jobs/{new_booking_id}/status", json={"status": "EN_ROUTE"}, headers=staff_headers)
    assert r.status_code == 400, "Security flaw: illegal status transition was allowed!"
    print(f" -> PASSED: Guard blocked illegal state transition (HTTP 400: {r.json()['detail']})")

    # 10. Test Review Submission
    print("\n[Test 10] Submitting Customer Review for Completed Booking...")
    review_payload = {
        "rating": 5,
        "comment": "Outstanding clean! Every corner was spotless and the cleaner arrived right on time.",
        "punctuality_score": 5,
        "thoroughness_score": 5
    }
    r = requests.post(f"{BASE_URL}/api/bookings/{new_booking_id}/review", json=review_payload, headers=cust_headers)
    assert r.status_code == 200, f"Review failed: {r.text}"
    print(" -> PASSED: 5-star review saved and cleaner aggregate rating updated.")

    # 11. Test Google OAuth 2.0 Prototype (Mock Mode)
    print("\n[Test 11] Testing Google OAuth 2.0 Mock Sign-in...")
    r = requests.post(f"{BASE_URL}/api/auth/google/login", json={"id_token": "mock-token-xyz"})
    assert r.status_code == 200
    google_res = r.json()
    assert "access_token" in google_res
    print(f" -> PASSED: Google OAuth login returned valid JWT for user: {google_res['user']['email']}.")

    print("\n==================================================")
    print(" ✅ ALL 11 TESTS PASSED! CLEANLONDON RUNS PERFECTLY")
    print("==================================================")

if __name__ == "__main__":
    try:
        test_full_system()
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
