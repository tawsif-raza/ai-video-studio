import pytest
from config import settings
from project_manager.manager import ProjectManager
from shared_core.contracts.project import ProjectState


def test_create_project_records_owner_user_id(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()

    project = manager.create_project(owner_user_id="user_alpha")

    assert project.owner_user_id == "user_alpha"

    # Reload from disk and verify persistence
    loaded = manager.load_project(project.project_id)
    assert loaded.owner_user_id == "user_alpha"


def test_load_project_authorization(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()

    project = manager.create_project(owner_user_id="user_alpha")

    # Access by the owner succeeds
    loaded = manager.load_project(project.project_id, owner_user_id="user_alpha")
    assert loaded.project_id == project.project_id

    # Access by another user raises PermissionError
    with pytest.raises(PermissionError) as exc_info:
        manager.load_project(project.project_id, owner_user_id="user_beta")
    assert "not authorized" in str(exc_info.value)

    # Access without owner_user_id (e.g. internal/CLI/unauthenticated) succeeds
    unauth_loaded = manager.load_project(project.project_id)
    assert unauth_loaded.project_id == project.project_id


def test_load_unassigned_project_accessible_to_any_user(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()

    legacy_project = manager.create_project()  # owner_user_id is None
    assert legacy_project.owner_user_id is None

    # Any user can access legacy/unassigned projects
    loaded_alpha = manager.load_project(legacy_project.project_id, owner_user_id="user_alpha")
    assert loaded_alpha.project_id == legacy_project.project_id

    loaded_beta = manager.load_project(legacy_project.project_id, owner_user_id="user_beta")
    assert loaded_beta.project_id == legacy_project.project_id


def test_list_projects_filters_by_owner_user_id(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()

    p_alpha1 = manager.create_project(owner_user_id="user_alpha")
    p_alpha2 = manager.create_project(owner_user_id="user_alpha")
    p_beta = manager.create_project(owner_user_id="user_beta")
    p_unassigned = manager.create_project()

    # Alpha's list only has Alpha's projects
    alpha_projects = manager.list_projects(owner_user_id="user_alpha")
    alpha_ids = [p.project_id for p in alpha_projects]
    assert set(alpha_ids) == {p_alpha1.project_id, p_alpha2.project_id}
    assert p_beta.project_id not in alpha_ids
    assert p_unassigned.project_id not in alpha_ids

    # Beta's list only has Beta's project
    beta_projects = manager.list_projects(owner_user_id="user_beta")
    beta_ids = [p.project_id for p in beta_projects]
    assert beta_ids == [p_beta.project_id]

    # Alpha's list with include_unassigned includes unassigned
    alpha_with_unassigned = manager.list_projects(owner_user_id="user_alpha", include_unassigned=True)
    alpha_unassigned_ids = [p.project_id for p in alpha_with_unassigned]
    assert set(alpha_unassigned_ids) == {p_alpha1.project_id, p_alpha2.project_id, p_unassigned.project_id}

    # Listing with owner_user_id=None returns all projects
    all_projects = manager.list_projects()
    all_ids = [p.project_id for p in all_projects]
    assert set(all_ids) == {p_alpha1.project_id, p_alpha2.project_id, p_beta.project_id, p_unassigned.project_id}


def test_delete_project_enforces_ownership(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()

    project = manager.create_project(owner_user_id="user_alpha")

    # Unauthorized delete raises PermissionError and does NOT delete files
    with pytest.raises(PermissionError):
        manager.delete_project(project.project_id, owner_user_id="user_beta")

    # Project still exists
    assert manager.load_project(project.project_id).project_id == project.project_id

    # Authorized delete removes project
    manager.delete_project(project.project_id, owner_user_id="user_alpha")
    with pytest.raises(FileNotFoundError):
        manager.load_project(project.project_id)
