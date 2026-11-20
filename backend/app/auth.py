"""Password hashing, signed login tokens, and a small login throttle.

Passwords use scrypt from the standard library (memory-hard, no extra dependency).
Tokens are short-lived signed JWTs (HS256) that carry only the user id; the API
re-reads the user on every request, so deactivating an account takes effect at once.
"""
import base64
import hashlib
import hmac
import os
import time
from collections import defaultdict, deque
from typing import Optional

import jwt

_N, _R, _P = 2**14, 8, 1
MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    b64 = lambda b: base64.b64encode(b).decode()
    return f"scrypt${_N}${_R}${_P}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(digest_b64)
        actual = hashlib.scrypt(password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Verified against when the email is unknown, so "no such user" and "wrong password"
# take about the same time and give the same answer.
_DUMMY_HASH = hash_password("not-a-real-password")


def verify_against_dummy(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def check_password_policy(password: str) -> Optional[str]:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"password must be at least {MIN_PASSWORD_LENGTH} characters"
    if password.lower() == password or not any(c.isdigit() for c in password):
        return "password must mix upper and lower case and include a digit"
    return None


def create_token(user_id: int, secret: str, ttl_hours: float) -> str:
    now = int(time.time())
    return jwt.encode({"sub": str(user_id), "iat": now, "exp": now + int(ttl_hours * 3600)}, secret, algorithm="HS256")


def decode_token(token: str, secret: str) -> Optional[int]:
    """Return the user id, or None if the token is invalid or expired."""
    try:
        claims = jwt.decode(token, secret, algorithms=["HS256"], options={"require": ["exp", "sub"]})
        return int(claims["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        return None


class LoginThrottle:
    """Allow `limit` failed logins per key in `window_s` seconds. In memory, so it resets on restart
    and is per process; a shared store would be needed to run several API instances."""

    def __init__(self, limit: int = 5, window_s: int = 900):
        self.limit, self.window_s = limit, window_s
        self._fails: dict[str, deque] = defaultdict(deque)

    def _prune(self, key: str) -> deque:
        q = self._fails[key]
        cutoff = time.monotonic() - self.window_s
        while q and q[0] < cutoff:
            q.popleft()
        return q

    def blocked(self, key: str) -> bool:
        return len(self._prune(key)) >= self.limit

    def record_failure(self, key: str) -> None:
        self._prune(key).append(time.monotonic())

    def reset(self, key: str) -> None:
        self._fails.pop(key, None)
