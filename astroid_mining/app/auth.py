"""Users, password hashing and API tokens.

Only `POST /api/v1/auth/login` takes a username and password; every other endpoint takes the
bearer token it returns. Tokens are random opaque strings, stored with an expiry, and are valid
for TOKEN_TTL_DAYS days.
"""

import hashlib
import hmac
import secrets

TOKEN_TTL_DAYS = 2
TOKEN_TTL_SECONDS = TOKEN_TTL_DAYS * 24 * 60 * 60
PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algorithm, iterations, salt, digest = stored.split("$")
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
    except ValueError:
        return False
    return hmac.compare_digest(candidate.hex(), digest)


def new_token() -> str:
    return secrets.token_urlsafe(24)


def bearer(header: str | None) -> str | None:
    if header and header.startswith("Bearer "):
        return header[len("Bearer ") :].strip() or None
    return None
