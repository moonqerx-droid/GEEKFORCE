from app.core.security import hash_password, hash_token, new_token, verify_password


def test_password_hash_is_argon2_and_verifies_only_original():
    encoded = hash_password("StrongPassword7")

    assert encoded.startswith("$argon2id$")
    assert verify_password(encoded, "StrongPassword7") is True
    assert verify_password(encoded, "WrongPassword7") is False


def test_tokens_are_random_and_only_hash_is_stable():
    first, second = new_token(), new_token()

    assert first != second
    assert len(first) >= 43
    assert hash_token(first) == hash_token(first)
    assert hash_token(first) != hash_token(second)
