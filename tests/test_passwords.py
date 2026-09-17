import pytest

from personal_agent_memory.services.users import (
    hash_password,
    normalize_username,
    verify_password,
)


def test_argon2id_round_trip_and_random_salts() -> None:
    password = " Mixed-Case 密碼 "
    first = hash_password(password)
    second = hash_password(password)

    assert first.startswith("$argon2id$")
    assert first != second
    assert verify_password(password, first)
    assert verify_password(password, second)
    assert not verify_password(password.lower(), first)
    assert not verify_password(password.strip(), first)


@pytest.mark.parametrize("encoded", [None, "", "invalid", "$argon2id$broken"])
def test_missing_or_malformed_hash_fails_closed(encoded: str | None) -> None:
    assert not verify_password("password", encoded)


def test_empty_password_cannot_be_created() -> None:
    with pytest.raises(ValueError, match="^password_required$"):
        hash_password("")


@pytest.mark.parametrize("username", ["Admin", "ADMIN", "admin"])
def test_username_is_case_insensitive(username: str) -> None:
    assert normalize_username(username) == "admin"


@pytest.mark.parametrize("username", ["", " ", "\t\n"])
def test_blank_username_is_rejected(username: str) -> None:
    with pytest.raises(ValueError, match="^username_required$"):
        normalize_username(username)
