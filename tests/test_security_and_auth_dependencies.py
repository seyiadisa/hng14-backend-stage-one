from starlette.requests import Request

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_token,
    verify_refresh_token,
)
from app.dependencies.auth import verify_api_version_header, verify_csrf_token


def make_request(headers=None, cookies=None) -> Request:
    cookie_header = ""
    if cookies:
        cookie_header = "; ".join(f"{key}={value}" for key, value in cookies.items())

    raw_headers = []
    for key, value in (headers or {}).items():
        raw_headers.append((key.lower().encode(), value.encode()))
    if cookie_header:
        raw_headers.append((b"cookie", cookie_header.encode()))

    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": raw_headers,
        }
    )


def test_hash_token_and_verify_refresh_token():
    token = "refresh-token"
    token_hash = hash_token(token)

    assert token_hash != token
    assert verify_refresh_token(token, token_hash) is True
    assert verify_refresh_token("other-token", token_hash) is False


def test_create_and_decode_access_token_roundtrip():
    get_settings.cache_clear()

    token = create_access_token("user-123")
    payload = decode_access_token(token)

    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"


def test_verify_api_version_header_accepts_version_one():
    request = make_request(headers={"X-API-Version": "1"})

    assert verify_api_version_header(request) is None


def test_verify_csrf_token_accepts_matching_cookie_and_header():
    request = make_request(
        headers={"X-CSRF-Token": "csrf-token"},
        cookies={"csrf_token": "csrf-token"},
    )

    assert verify_csrf_token(request) is None
