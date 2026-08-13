from core import auth as auth_module
from core.database import hash_password, verify_password
from core.rate_limiter import SlidingWindowRateLimiter


def test_password_hash_roundtrip():
    stored = hash_password("admin123")
    assert verify_password("admin123", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("admin123", "not-a-valid-format")


def test_login_never_falls_back_to_env_admin(monkeypatch):
    """数据库查不到用户时，不能再用默认管理员凭据绕过用户表。"""
    monkeypatch.setattr(auth_module, "get_user", lambda username: None)
    monkeypatch.setattr(auth_module, "get_user_by_email", lambda email: None)
    monkeypatch.setattr(auth_module, "purge_expired_tokens", lambda: None)

    assert auth_module.login("admin", "admin123") is None


def test_sliding_window_rate_limiter():
    limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60)
    assert limiter.allow("127.0.0.1")
    assert limiter.allow("127.0.0.1")
    assert not limiter.allow("127.0.0.1")
    assert limiter.allow("other-host")
