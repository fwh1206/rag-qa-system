from core.database import hash_password, verify_password


def test_password_hash_roundtrip():
    stored = hash_password("admin123")
    assert verify_password("admin123", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("admin123", "not-a-valid-format")
