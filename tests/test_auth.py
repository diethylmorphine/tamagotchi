import hashlib
import hmac
import json
from datetime import UTC, datetime
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException

from backend.auth import authenticate

TOKEN = "123456:test_token"
NOW = datetime(2026, 9, 10, tzinfo=UTC)


def signed_data(age=0):
    fields = {
        "auth_date": str(int(NOW.timestamp()) - age),
        "user": json.dumps({"id": 123, "first_name": "Tester"}),
        "query_id": "test",
    }
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    fields['hash'] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_signed_user():
    assert authenticate(signed_data(), TOKEN, 3600, NOW) == 123


@pytest.mark.parametrize("data", [signed_data(3601), signed_data(-60), "bad=data"])
def test_expired_future_or_malformed(data):
    with pytest.raises(HTTPException) as exc:
        authenticate(data, TOKEN, 3600, NOW)
    assert exc.value.status_code == 401


def test_tampering():
    with pytest.raises(HTTPException):
        authenticate(signed_data().replace("Tester", "Attacker"), TOKEN, 3600, NOW)

