from fastapi import HTTPException

from app.services.payments import parse_stripe_webhook


def test_mock_webhook_accepts_json_payload():
    event = parse_stripe_webhook(
        b'{"type":"checkout.session.completed","data":{"object":{"id":"cs_test","metadata":{"booking_id":"7"}}}}',
        None,
    )
    assert event["type"] == "checkout.session.completed"


def test_mock_webhook_rejects_malformed_payload():
    try:
        parse_stripe_webhook(b"not-json", None)
        assert False, "Malformed webhook payload should be rejected"
    except HTTPException as exc:
        assert exc.status_code == 400
