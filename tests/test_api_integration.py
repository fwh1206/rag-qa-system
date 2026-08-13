"""API 端到端集成测试：用 TestClient 覆盖登录、知识库、问答、会话全链路。

说明：
- 依赖本机 MySQL（RAG_DB_* 环境变量），测试数据用后即清，不污染真实数据；
- 所有 LLM 调用均被 mock，不产生外部请求；
- 若运行环境（如 WorkBuddy 沙箱）拦截磁盘删除，则跳过删除断言，其余用例照常执行。
"""

import os
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from core.database import create_user, delete_user
from main import app

TEST_ADMIN = "pytest_admin"
TEST_ADMIN_PASS = "pytest_admin_123"
TEST_USER = "e2e_test_user"
TEST_PASS = "e2e_pass_123"
TEST_EMAIL = "e2e_test_user@example.com"
TEST_BIND_EMAIL = "e2e_bind_user@example.com"
TEST_SESSION = "e2e-session-001"

# WorkBuddy 沙箱会把 os.remove 替换为回收站删除并可能抛错；检测后跳过磁盘删除断言
_SANDBOX_BLOCKS_DELETE = getattr(os.remove, "__module__", "") == "sitecustomize"


@pytest.fixture(scope="module", autouse=True)
def _clean_test_data():
    delete_user(TEST_USER)
    yield


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(client: TestClient) -> str:
    delete_user(TEST_ADMIN)
    create_user(TEST_ADMIN, TEST_ADMIN_PASS, "admin")
    resp = client.post(
        "/auth/login", json={"username": TEST_ADMIN, "password": TEST_ADMIN_PASS}
    )
    assert resp.status_code == 200
    return resp.json()["token"]


def _headers(token: str) -> dict:
    return {"X-Auth-Token": token}


def _dev_code(client: TestClient, email: str, purpose: str = "register") -> str:
    with (
        patch("api.auth_router.EMAIL_DEV_MODE", True),
        patch("api.auth_router.is_email_configured", return_value=False),
    ):
        resp = client.post(
            "/auth/send-code", json={"email": email, "purpose": purpose}
        )
    assert resp.status_code == 200, resp.text
    return resp.json()["dev_code"]


class TestAuthFlow:
    def test_health(self, client):
        assert client.get("/health").json() == {"status": "ok"}

    def test_login_wrong_password(self, client):
        resp = client.post("/auth/login", json={"username": "admin", "password": "bad"})
        assert resp.status_code == 401

    def test_protected_route_requires_token(self, client):
        assert client.get("/kb/list").status_code == 401

    def test_register_and_login(self, client):
        code = _dev_code(client, TEST_EMAIL, "register")
        resp = client.post(
            "/auth/register",
            json={
                "username": TEST_USER,
                "password": TEST_PASS,
                "email": TEST_EMAIL,
                "code": code,
            },
        )
        assert resp.status_code == 200
        resp = client.post(
            "/auth/login", json={"username": TEST_EMAIL, "password": TEST_PASS}
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "user"

    def test_email_code_login(self, client):
        code = _dev_code(client, TEST_EMAIL, "login")
        resp = client.post(
            "/auth/login-code", json={"email": TEST_EMAIL, "code": code}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["username"] == TEST_USER

    def test_user_can_save_own_llm_config(self, client):
        token = client.post(
            "/auth/login", json={"username": TEST_USER, "password": TEST_PASS}
        ).json()["token"]
        resp = client.put(
            "/auth/me/llm",
            headers=_headers(token),
            json={
                "enabled": True,
                "url": "https://example.com/v1/chat/completions",
                "model": "custom-model",
                "api_key": "sk-test-secret",
            },
        )
        assert resp.status_code == 200, resp.text

        config = client.get("/auth/me/llm", headers=_headers(token)).json()
        assert config["enabled"] is True
        assert config["has_api_key"] is True
        assert "sk-test-secret" not in client.get(
            "/auth/me/llm", headers=_headers(token)
        ).text

        with patch("api.chat_router.llm_chat", return_value="ok") as mock_llm:
            resp = client.post(
                "/chat",
                headers=_headers(token),
                json={"question": "你好", "session_id": "user-llm-session", "mode": "chat"},
            )
        assert resp.status_code == 200
        assert mock_llm.call_args[0][2]["api_key"] == "sk-test-secret"
        client.delete(
            "/history/clear",
            headers=_headers(token),
            params={"session_id": "user-llm-session"},
        )

    def test_register_rejects_used_email(self, client):
        with (
            patch("api.auth_router.EMAIL_DEV_MODE", True),
            patch("api.auth_router.is_email_configured", return_value=False),
        ):
            resp = client.post(
                "/auth/send-code", json={"email": TEST_EMAIL, "purpose": "register"}
            )
        assert resp.status_code == 400

    def test_send_code_without_smtp_returns_500(self, client):
        email = f"nobody_{int(time.time())}@example.com"
        with (
            patch("api.auth_router.EMAIL_DEV_MODE", False),
            patch("api.auth_router.is_email_configured", return_value=False),
        ):
            resp = client.post(
                "/auth/send-code",
                json={"email": email, "purpose": "register"},
            )
        assert resp.status_code == 500
        assert "SMTP" in resp.json()["detail"]

    def test_me(self, client, admin_token):
        resp = client.get("/auth/me", headers=_headers(admin_token))
        assert resp.status_code == 200
        assert resp.json()["username"] == TEST_ADMIN

    def test_me_includes_email(self, client):
        token = client.post(
            "/auth/login", json={"username": TEST_USER, "password": TEST_PASS}
        ).json()["token"]
        resp = client.get("/auth/me", headers=_headers(token))
        assert resp.status_code == 200
        assert resp.json()["email"] == TEST_EMAIL

    def test_normal_user_denied_admin_api(self, client):
        token = client.post(
            "/auth/login", json={"username": TEST_USER, "password": TEST_PASS}
        ).json()["token"]
        resp = client.get("/auth/users", headers=_headers(token))
        assert resp.status_code == 403

    def test_admin_can_list_users(self, client, admin_token):
        resp = client.get("/auth/users", headers=_headers(admin_token))
        assert resp.status_code == 200
        names = {u["username"] for u in resp.json()["users"]}
        assert "admin" in names


class TestKnowledgeBase:
    def test_upload_text_and_list(self, client, admin_token):
        resp = client.post(
            "/upload_text",
            headers=_headers(admin_token),
            json={
                "doc_name": "e2e_测试文档.md",
                "text_content": "端到端测试专用文档内容，用于验证上传、检索与删除全链路。"
                "混合检索使用向量与BM25融合排序。",
                "category": "测试分组",
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["chunk_num"] >= 1

        resp = client.get("/kb/list", headers=_headers(admin_token))
        assert resp.status_code == 200
        names = [f["name"] for f in resp.json()["file_list"]]
        assert "e2e_测试文档.md" in names

    def test_categories(self, client, admin_token):
        resp = client.get("/kb/categories", headers=_headers(admin_token))
        assert resp.status_code == 200
        assert any(c["name"] == "测试分组" for c in resp.json()["categories"])

    def test_user_kb_isolated_from_admin(self, client, admin_token):
        resp = client.post(
            "/upload_text",
            headers=_headers(admin_token),
            json={"doc_name": "e2e_admin_only.md", "text_content": "管理员专属知识库文档。"},
        )
        assert resp.status_code == 200, resp.text

        delete_user(TEST_USER)
        create_user(TEST_USER, TEST_PASS, "user", TEST_EMAIL)
        login = client.post(
            "/auth/login", json={"username": TEST_USER, "password": TEST_PASS}
        )
        user_token = login.json()["token"]
        user_names = [
            f["name"]
            for f in client.get("/kb/list", headers=_headers(user_token)).json()["file_list"]
        ]
        assert "e2e_admin_only.md" not in user_names

        resp = client.post(
            "/upload_text",
            headers=_headers(user_token),
            json={"doc_name": "e2e_user_only.md", "text_content": "用户自己的私有知识库文档。"},
        )
        assert resp.status_code == 200, resp.text
        user_names = [
            f["name"]
            for f in client.get("/kb/list", headers=_headers(user_token)).json()["file_list"]
        ]
        assert "e2e_user_only.md" in user_names

        admin_names = [
            f["name"]
            for f in client.get("/kb/list", headers=_headers(admin_token)).json()["file_list"]
        ]
        assert "e2e_admin_only.md" in admin_names
        assert "e2e_user_only.md" in admin_names

        user_hits = client.get(
            "/kb/test",
            headers=_headers(user_token),
            params={"question": "管理员专属知识库文档", "top_k": 5},
        ).json()["results"]
        assert all(hit["filename"] != "e2e_admin_only.md" for hit in user_hits)

        admin_hits = client.get(
            "/kb/test",
            headers=_headers(admin_token),
            params={"question": "用户自己的私有知识库文档", "top_k": 5},
        ).json()["results"]
        assert any(hit["filename"] == "e2e_user_only.md" for hit in admin_hits)

        forbidden = client.delete(
            "/kb/delete",
            headers=_headers(user_token),
            params={"filename": "e2e_admin_only.md"},
        )
        assert forbidden.status_code == 404

        deleted_user = client.delete(
            "/kb/delete",
            headers=_headers(user_token),
            params={"filename": "e2e_user_only.md"},
        )
        assert deleted_user.status_code == 200
        deleted_admin = client.delete(
            "/kb/delete",
            headers=_headers(admin_token),
            params={"filename": "e2e_admin_only.md"},
        )
        assert deleted_admin.status_code == 200

    def test_kb_test_search(self, client, admin_token):
        resp = client.get(
            "/kb/test",
            headers=_headers(admin_token),
            params={"question": "混合检索", "top_k": 3},
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["results"], list)

    def test_preview(self, client, admin_token):
        resp = client.get(
            "/kb/preview", headers=_headers(admin_token), params={"filename": "e2e_测试文档.md"}
        )
        assert resp.status_code == 200
        assert "端到端测试" in resp.json()["text"]

    def test_kg_extract_and_cache(self, client, admin_token):
        resp = client.post(
            "/upload_text",
            headers=_headers(admin_token),
            json={"doc_name": "e2e_kg_test.txt", "text_content": "知识图谱测试文档，包含产品A与产品B的关系。"},
        )
        assert resp.status_code == 200
        with patch(
            "core.kg_builder.llm_chat",
            return_value='{"entities":[{"id":"a","label":"产品A","type":"产品"},'
            '{"id":"b","label":"产品B","type":"产品"}],'
            '"relations":[{"source":"a","target":"b","label":"依赖"}]}',
        ):
            resp = client.post(
                "/kg/extract",
                headers=_headers(admin_token),
                params={"filename": "e2e_kg_test.txt"},
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "ok"
        assert len(data["entities"]) == 2
        assert len(data["relations"]) == 1

        cached = client.get(
            "/kg/file", headers=_headers(admin_token), params={"filename": "e2e_kg_test.txt"}
        ).json()
        assert cached["status"] == "cached"
        client.delete(
            "/kb/delete",
            headers=_headers(admin_token),
            params={"filename": "e2e_kg_test.txt"},
        )

    @pytest.mark.skipif(
        _SANDBOX_BLOCKS_DELETE,
        reason="沙箱环境拦截磁盘文件删除，删除断言在 CI/真实环境执行",
    )
    def test_cleanup_upload(self, client, admin_token):
        resp = client.delete(
            "/kb/delete", headers=_headers(admin_token), params={"filename": "e2e_测试文档.md"}
        )
        assert resp.status_code == 200


class TestChatAndSession:
    @patch("api.chat_router.llm_chat", return_value="这是模拟的AI回答。")
    def test_chat_general_mode(self, mock_llm, client, admin_token):
        resp = client.post(
            "/chat",
            headers=_headers(admin_token),
            json={"question": "你好", "session_id": TEST_SESSION, "mode": "chat"},
        )
        assert resp.status_code == 200
        assert resp.json()["answer"] == "这是模拟的AI回答。"

    def test_history_list(self, client, admin_token):
        resp = client.get(
            "/history/list", headers=_headers(admin_token), params={"session_id": TEST_SESSION}
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_recent_stats_scoped_by_user(self, client, admin_token):
        with patch("api.chat_router.llm_chat", return_value="管理员专属记录"):
            resp = client.post(
                "/chat",
                headers=_headers(admin_token),
                json={"question": "管理员专属问题", "session_id": "admin-privacy-session", "mode": "chat"},
            )
        assert resp.status_code == 200

        user_token = client.post(
            "/auth/login", json={"username": TEST_USER, "password": TEST_PASS}
        ).json()["token"]
        admin_items = client.get(
            "/stats/recent?limit=20", headers=_headers(admin_token)
        ).json()["items"]
        user_items = client.get(
            "/stats/recent?limit=20", headers=_headers(user_token)
        ).json()["items"]
        assert any("管理员专属问题" in item["question"] for item in admin_items)
        assert all("管理员专属问题" not in item["question"] for item in user_items)

        client.delete(
            "/history/clear",
            headers=_headers(admin_token),
            params={"session_id": "admin-privacy-session"},
        )

    def test_reset_password_by_email_code(self, client):
        code = _dev_code(client, TEST_EMAIL, "reset")
        new_pass = "reset_pass_456"
        resp = client.post(
            "/auth/reset-password",
            json={
                "email": TEST_EMAIL,
                "code": code,
                "new_password": new_pass,
            },
        )
        assert resp.status_code == 200, resp.text
        resp = client.post(
            "/auth/login", json={"username": TEST_USER, "password": new_pass}
        )
        assert resp.status_code == 200

    def test_bind_email(self, client):
        code = _dev_code(client, TEST_BIND_EMAIL, "bind")
        token = client.post(
            "/auth/login", json={"username": TEST_USER, "password": "reset_pass_456"}
        ).json()["token"]
        resp = client.post(
            "/auth/me/email",
            headers=_headers(token),
            json={"email": TEST_BIND_EMAIL, "code": code},
        )
        assert resp.status_code == 200, resp.text

    def test_sessions_list(self, client, admin_token):
        resp = client.get("/sessions/list", headers=_headers(admin_token))
        assert resp.status_code == 200
        ids = [s["session_id"] for s in resp.json()["sessions"]]
        assert TEST_SESSION in ids

    def test_history_export_md(self, client, admin_token):
        resp = client.get(
            "/history/export",
            headers=_headers(admin_token),
            params={"session_id": TEST_SESSION, "format": "md"},
        )
        assert resp.status_code == 200
        assert "text/markdown" in resp.headers["content-type"]

    def test_session_rename(self, client, admin_token):
        resp = client.put(
            "/sessions/rename",
            headers=_headers(admin_token),
            params={"session_id": TEST_SESSION},
            json={"name": "E2E测试会话"},
        )
        assert resp.status_code == 200

    def test_cleanup_session(self, client, admin_token):
        resp = client.delete(
            "/history/clear", headers=_headers(admin_token), params={"session_id": TEST_SESSION}
        )
        assert resp.status_code == 200


class TestCleanup:
    def test_delete_test_user(self, client, admin_token):
        resp = client.delete(f"/auth/users/{TEST_USER}", headers=_headers(admin_token))
        assert resp.status_code == 200

    def test_delete_test_admin(self, client, admin_token):
        delete_user(TEST_ADMIN)
