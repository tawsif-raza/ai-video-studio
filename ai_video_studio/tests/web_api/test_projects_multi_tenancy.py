import uuid
import pytest
from fastapi.testclient import TestClient

from auth.security import create_access_token
from auth.user_store import LocalUserStore, set_user_store
from config import settings
from shared_core.contracts.user import UserCreate
from tests.web_api.conftest import (
    FakeLLMClient,
    SucceedingDirectorController,
    post_with_controller,
)
from web_api import create_app
from web_api.dependencies import (
    get_director_controller_factory,
    get_llm_client_factory,
    get_project_manager,
)


@pytest.fixture
def multi_tenant_env(tmp_path, monkeypatch):
    """Sets up an isolated environment with two registered users: Alpha and Beta."""
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    store = LocalUserStore(tmp_path / "users")
    set_user_store(store)

    user_alpha = store.create_user(
        UserCreate(email="alpha@example.com", full_name="User Alpha", password="password123")
    )
    user_beta = store.create_user(
        UserCreate(email="beta@example.com", full_name="User Beta", password="password123")
    )

    token_alpha = create_access_token({"sub": user_alpha.id, "email": user_alpha.email})
    token_beta = create_access_token({"sub": user_beta.id, "email": user_beta.email})

    app = create_app()
    app.dependency_overrides[get_llm_client_factory] = lambda: FakeLLMClient
    app.dependency_overrides[get_director_controller_factory] = lambda: SucceedingDirectorController

    client = TestClient(app)

    yield {
        "client": client,
        "app": app,
        "user_alpha": user_alpha,
        "user_beta": user_beta,
        "headers_alpha": {"Authorization": f"Bearer {token_alpha}"},
        "headers_beta": {"Authorization": f"Bearer {token_beta}"},
    }

    set_user_store(None)


def test_create_project_associates_owner(multi_tenant_env):
    client = multi_tenant_env["client"]
    headers_alpha = multi_tenant_env["headers_alpha"]
    user_alpha = multi_tenant_env["user_alpha"]

    response = client.post("/projects", json={"idea": "Alpha's great video"}, headers=headers_alpha)
    assert response.status_code == 202
    project_id = response.json()["project_id"]

    # Verify project has owner_user_id
    get_resp = client.get(f"/projects/{project_id}", headers=headers_alpha)
    assert get_resp.status_code == 200
    assert get_resp.json()["owner_user_id"] == user_alpha.id


def test_cross_user_project_isolation(multi_tenant_env):
    client = multi_tenant_env["client"]
    headers_alpha = multi_tenant_env["headers_alpha"]
    headers_beta = multi_tenant_env["headers_beta"]

    # User Alpha creates a project
    create_resp = client.post("/projects", json={"idea": "Secret Alpha Project"}, headers=headers_alpha)
    assert create_resp.status_code == 202
    project_id = create_resp.json()["project_id"]

    # User Alpha can access it
    assert client.get(f"/projects/{project_id}", headers=headers_alpha).status_code == 200

    # User Beta receives 404 (IDOR prevention)
    assert client.get(f"/projects/{project_id}", headers=headers_beta).status_code == 404

    # Unauthenticated caller receives 404
    assert client.get(f"/projects/{project_id}").status_code == 404


def test_list_projects_multi_tenant_isolation(multi_tenant_env):
    client = multi_tenant_env["client"]
    headers_alpha = multi_tenant_env["headers_alpha"]
    headers_beta = multi_tenant_env["headers_beta"]

    # Alpha creates 2 projects
    p_a1 = client.post("/projects", json={"idea": "Alpha 1"}, headers=headers_alpha).json()["project_id"]
    p_a2 = client.post("/projects", json={"idea": "Alpha 2"}, headers=headers_alpha).json()["project_id"]

    # Beta creates 1 project
    p_b1 = client.post("/projects", json={"idea": "Beta 1"}, headers=headers_beta).json()["project_id"]

    # Alpha lists projects -> only Alpha's projects
    alpha_list = client.get("/projects", headers=headers_alpha).json()
    alpha_ids = [p["project_id"] for p in alpha_list]
    assert set(alpha_ids) == {p_a1, p_a2}

    # Beta lists projects -> only Beta's project
    beta_list = client.get("/projects", headers=headers_beta).json()
    beta_ids = [p["project_id"] for p in beta_list]
    assert beta_ids == [p_b1]

    # Unauthenticated list -> returns all projects
    unauth_list = client.get("/projects").json()
    unauth_ids = [p["project_id"] for p in unauth_list]
    assert set(unauth_ids) == {p_a1, p_a2, p_b1}


def test_delete_project_isolation(multi_tenant_env):
    client = multi_tenant_env["client"]
    headers_alpha = multi_tenant_env["headers_alpha"]
    headers_beta = multi_tenant_env["headers_beta"]

    p_a = client.post("/projects", json={"idea": "Alpha To Delete"}, headers=headers_alpha).json()["project_id"]

    # Beta tries to delete Alpha's project -> 404
    assert client.delete(f"/projects/{p_a}", headers=headers_beta).status_code == 404
    # Project still exists
    assert client.get(f"/projects/{p_a}", headers=headers_alpha).status_code == 200

    # Unauthenticated tries to delete -> 404
    assert client.delete(f"/projects/{p_a}").status_code == 404
    assert client.get(f"/projects/{p_a}", headers=headers_alpha).status_code == 200

    # Alpha deletes their project -> 204
    assert client.delete(f"/projects/{p_a}", headers=headers_alpha).status_code == 204
    assert client.get(f"/projects/{p_a}", headers=headers_alpha).status_code == 404


def test_media_and_package_endpoints_enforce_isolation(multi_tenant_env):
    client = multi_tenant_env["client"]
    headers_alpha = multi_tenant_env["headers_alpha"]
    headers_beta = multi_tenant_env["headers_beta"]

    p_a = client.post("/projects", json={"idea": "Alpha Media Project"}, headers=headers_alpha).json()["project_id"]

    # Beta cannot view media
    assert client.get(f"/projects/{p_a}/media", headers=headers_beta).status_code == 404
    # Beta cannot upload media
    files = {"file": ("test.png", b"fake png bytes", "image/png")}
    assert client.post(f"/projects/{p_a}/media", files=files, headers=headers_beta).status_code == 404
    # Beta cannot delete media
    assert client.delete(f"/projects/{p_a}/media/images/test.png", headers=headers_beta).status_code == 404
    # Beta cannot bulk delete media
    bulk_payload = {"items": [{"category": "images", "filename": "test.png"}]}
    assert client.post(f"/projects/{p_a}/media/bulk-delete", json=bulk_payload, headers=headers_beta).status_code == 404
    # Beta cannot get production package
    assert client.get(f"/projects/{p_a}/production-package", headers=headers_beta).status_code == 404
    # Beta cannot get producer package
    assert client.get(f"/projects/{p_a}/producer-package", headers=headers_beta).status_code == 404


def test_legacy_unassigned_project_accessible_without_auth(multi_tenant_env):
    client = multi_tenant_env["client"]
    headers_alpha = multi_tenant_env["headers_alpha"]

    # Create unassigned project without headers
    resp = client.post("/projects", json={"idea": "Legacy Unassigned Project"})
    assert resp.status_code == 202
    p_id = resp.json()["project_id"]

    # Accessible without auth
    unauth_get = client.get(f"/projects/{p_id}")
    assert unauth_get.status_code == 200
    assert unauth_get.json()["owner_user_id"] is None

    # Also accessible with auth
    auth_get = client.get(f"/projects/{p_id}", headers=headers_alpha)
    assert auth_get.status_code == 200
