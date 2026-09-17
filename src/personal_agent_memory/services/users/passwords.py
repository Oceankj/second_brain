"""Password primitives; callers must never log passwords or their encoded hashes."""

from argon2 import PasswordHasher, Type
from argon2.exceptions import HashingError, InvalidHashError, VerificationError

_hasher = PasswordHasher(type=Type.ID)


def normalize_username(username: str) -> str:
    if not username.strip():
        raise ValueError("username_required")
    return username.lower()


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("password_required")
    try:
        return _hasher.hash(password)
    except HashingError:
        raise ValueError("password_hash_failed") from None


def verify_password(password: str, password_hash: str | None) -> bool:
    # NULL is intentional for accounts that do not yet support password login.
    if not password or not password_hash or not password_hash.startswith("$argon2id$"):
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError):
        return False
