import pytest
from starlette.requests import Request

import main


def make_request(headers=None):
    raw_headers = [
        (key.lower().encode(), value.encode())
        for key, value in (headers or {}).items()
    ]
    return Request({"type": "http", "headers": raw_headers})


def test_header_idempotency_key_takes_precedence():
    request = make_request({"Idempotency-Key": "CL-123"})

    assert main.get_idempotency_key(request, "CL-123") == "CL-123"


def test_mismatched_idempotency_sources_are_rejected():
    request = make_request({"Idempotency-Key": "CL-header"})

    with pytest.raises(main.HTTPException) as error:
        main.get_idempotency_key(request, "CL-body")

    assert error.value.status_code == 400


def test_invalid_idempotency_key_is_rejected():
    request = make_request({"Idempotency-Key": "contains spaces"})

    with pytest.raises(main.HTTPException) as error:
        main.get_idempotency_key(request)

    assert error.value.status_code == 400
