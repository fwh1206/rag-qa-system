"""数据统计接口测试。"""

import pytest
from fastapi.testclient import TestClient

from core.database import create_user, delete_user
from main import app

TEST_ADMIN = "pytest_stats_admin"
TEST_ADMIN_PASS = "pytest_stats_admin_123"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _admin_token(client: TestClient) -> str:
    delete_user(TEST_ADMIN)
    create_user(TEST_ADMIN, TEST_ADMIN_PASS, "admin")
    resp = client.post(
        "/auth/login", json={"username": TEST_ADMIN, "password": TEST_ADMIN_PASS}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def _headers(token: str) -> dict:
    return {"X-Auth-Token": token}


def test_stats_overview_requires_auth(client):
    assert client.get("/stats/overview").status_code == 401


def test_stats_overview_shape(client):
    token = _admin_token(client)
    resp = client.get("/stats/overview", headers=_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    for key in ("files", "chunks", "chats", "sessions", "users", "categories"):
        assert key in data
        assert isinstance(data[key], int)


def test_stats_recent_shape(client):
    token = _admin_token(client)
    resp = client.get("/stats/recent?limit=3", headers=_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)


def test_stats_trend_shape(client):
    token = _admin_token(client)
    resp = client.get("/stats/trend?days=7", headers=_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["days"] == 7
    assert len(data["labels"]) == 7
    assert len(data["values"]) == 7
    assert data["total"] == sum(data["values"])


def test_stats_me_shape(client):
    token = _admin_token(client)
    resp = client.get("/stats/me", headers=_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    for key in ("sessions", "chats", "files", "chunks", "recent"):
        assert key in data


def test_email_config_shape(client):
    token = _admin_token(client)
    resp = client.get("/config/email", headers=_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    for key in ("host", "port", "user", "from_address", "use_ssl", "has_password", "configured"):
        assert key in data


def test_llm_config_shape(client):
    token = _admin_token(client)
    resp = client.get("/config/llm", headers=_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    for key in ("url", "model", "has_api_key", "configured"):
        assert key in data


def test_page_routes_serve_html(client):
    """多页面路由应返回对应 HTML。"""
    for path, marker in [
        ("/", "data-page=\"chat\""),
        ("/login", "data-page=\"login\""),
        ("/kb", "data-page=\"kb\""),
        ("/stats", "data-page=\"stats\""),
        ("/history", "data-page=\"history\""),
        ("/settings", "data-page=\"settings\""),
        ("/profile", "data-page=\"profile\""),
    ]:
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} -> {resp.status_code}"
        assert marker in resp.text, f"{path} 未包含 {marker}"


def test_stats_page_bundles_chart_library(client):
    resp = client.get("/stats")
    assert resp.status_code == 200
    assert "/static/vendor/chart.umd.min.js" in resp.text
    assert 'id="trendChart"' in resp.text


def test_config_reset_restores_defaults(client):
    token = _admin_token(client)
    resp = client.post("/config/reset", headers=_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["config"]["top_k"] >= 1
