"""Optional password gate.

If APP_PASSWORD is unset, there is no login — no cookie, no screen, nothing to notice.
If it is set, every /api route except the public ones needs a session cookie, which you
get by posting the right password.

The token is an HMAC of the password rather than the password itself, so the cookie is
not the credential in plaintext. This is a lock on your own front door for an instance
you've exposed past localhost — not a multi-user auth system.
"""

import hashlib
import hmac

from fastapi import Request

from . import config

COOKIE_NAME = "civ6_coach_session"


def enabled() -> bool:
    return config.app_password() is not None


def _token() -> str:
    password = config.app_password() or ""
    return hmac.new(password.encode("utf-8"), b"civ6-coach-session", hashlib.sha256).hexdigest()


def check_password(candidate: str) -> bool:
    password = config.app_password()
    if password is None:
        return True
    return hmac.compare_digest(candidate.encode("utf-8"), password.encode("utf-8"))


def issue_token() -> str:
    return _token()


def is_authenticated(request: Request) -> bool:
    if not enabled():
        return True
    cookie = request.cookies.get(COOKIE_NAME, "")
    if not cookie:
        return False
    return hmac.compare_digest(cookie, _token())
