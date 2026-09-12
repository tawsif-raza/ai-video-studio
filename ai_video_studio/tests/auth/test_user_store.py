import json
from pathlib import Path
import pytest

from auth.user_store import (
    LocalUserStore,
    UserAlreadyExistsError,
    UserNotFoundError,
    get_user_store,
    set_user_store,
)
from shared_core.contracts.user import UserCreate, UserInDB


@pytest.fixture
def temp_user_store(tmp_path: Path):
    return LocalUserStore(base_dir=tmp_path / "users")


def test_create_user_persists_json_file(temp_user_store: LocalUserStore):
    user_create = UserCreate(
        email="Director@Studio.AI",
        full_name="Alex Director",
        password="ValidPassword123!",
    )
    user = temp_user_store.create_user(user_create)

    assert isinstance(user, UserInDB)
    assert user.email == "director@studio.ai"
    assert user.full_name == "Alex Director"
    assert user.is_active is True
    assert user.hashed_password
    assert user.salt
    assert user.hashed_password != "ValidPassword123!"

    # Verify disk persistence under base_dir / <user_id> / user.json
    user_dir = temp_user_store.base_dir / user.id
    assert user_dir.is_dir()
    user_file = user_dir / "user.json"
    assert user_file.is_file()

    saved_data = json.loads(user_file.read_text(encoding="utf-8"))
    assert saved_data["email"] == "director@studio.ai"
    assert saved_data["full_name"] == "Alex Director"
    assert "password" not in saved_data
    assert saved_data["hashed_password"] == user.hashed_password
    assert saved_data["salt"] == user.salt


def test_create_user_duplicate_email_raises_error(temp_user_store: LocalUserStore):
    user_create = UserCreate(
        email="duplicate@studio.ai",
        full_name="First Account",
        password="ValidPassword123!",
    )
    temp_user_store.create_user(user_create)

    # Attempt second registration with same email (different case)
    duplicate = UserCreate(
        email="Duplicate@Studio.AI",
        full_name="Second Account",
        password="AnotherPassword123!",
    )
    with pytest.raises(UserAlreadyExistsError, match="already exists"):
        temp_user_store.create_user(duplicate)


def test_get_by_id_and_email(temp_user_store: LocalUserStore):
    created = temp_user_store.create_user(
        UserCreate(
            email="query@studio.ai",
            full_name="Query User",
            password="ValidPassword123!",
        )
    )

    # Get by ID
    by_id = temp_user_store.get_by_id(created.id)
    assert by_id is not None
    assert by_id.id == created.id
    assert by_id.email == "query@studio.ai"

    # Nonexistent ID
    assert temp_user_store.get_by_id("nonexistent-id") is None

    # Get by Email (case insensitive)
    by_email = temp_user_store.get_by_email("QUERY@Studio.AI")
    assert by_email is not None
    assert by_email.id == created.id

    # Nonexistent Email
    assert temp_user_store.get_by_email("unknown@studio.ai") is None


def test_update_user_and_update_password(temp_user_store: LocalUserStore):
    user = temp_user_store.create_user(
        UserCreate(
            email="update@studio.ai",
            full_name="Original Name",
            password="OldPassword123!",
        )
    )

    # Update metadata
    updated_model = user.model_copy(update={"full_name": "Updated Name"})
    saved = temp_user_store.update_user(updated_model)
    assert saved.full_name == "Updated Name"

    # Verify disk reloaded
    reloaded = temp_user_store.get_by_id(user.id)
    assert reloaded is not None
    assert reloaded.full_name == "Updated Name"

    # Update password
    old_hash = reloaded.hashed_password
    temp_user_store.update_password(user.id, "NewPassword456!")
    after_pw_change = temp_user_store.get_by_id(user.id)
    assert after_pw_change is not None
    assert after_pw_change.hashed_password != old_hash

    # Authenticate with new vs old password
    assert temp_user_store.authenticate_user("update@studio.ai", "NewPassword456!") is not None
    assert temp_user_store.authenticate_user("update@studio.ai", "OldPassword123!") is None


def test_update_nonexistent_user_raises_error(temp_user_store: LocalUserStore):
    ghost_user = UserInDB(
        id="ghost-123",
        email="ghost@studio.ai",
        full_name="Ghost",
        hashed_password="h",
        salt="s",
    )
    with pytest.raises(UserNotFoundError):
        temp_user_store.update_user(ghost_user)

    with pytest.raises(UserNotFoundError):
        temp_user_store.update_password("ghost-123", "newPass123!")


def test_authenticate_user_scenarios(temp_user_store: LocalUserStore):
    temp_user_store.create_user(
        UserCreate(
            email="auth@studio.ai",
            full_name="Auth Tester",
            password="CorrectPassword123!",
        )
    )

    # Successful authentication
    auth_success = temp_user_store.authenticate_user("AUTH@studio.ai", "CorrectPassword123!")
    assert auth_success is not None
    assert auth_success.email == "auth@studio.ai"

    # Bad password
    assert temp_user_store.authenticate_user("auth@studio.ai", "IncorrectPassword!") is None

    # Inactive account
    active_user = temp_user_store.get_by_email("auth@studio.ai")
    assert active_user is not None
    deactivated = active_user.model_copy(update={"is_active": False})
    temp_user_store.update_user(deactivated)

    assert temp_user_store.authenticate_user("auth@studio.ai", "CorrectPassword123!") is None


def test_list_users_and_delete_user(temp_user_store: LocalUserStore):
    u1 = temp_user_store.create_user(UserCreate(email="u1@studio.ai", full_name="User One", password="password1"))
    u2 = temp_user_store.create_user(UserCreate(email="u2@studio.ai", full_name="User Two", password="password2"))

    users = temp_user_store.list_users()
    assert len(users) == 2
    user_ids = [u.id for u in users]
    assert u1.id in user_ids
    assert u2.id in user_ids

    # Delete u1
    assert temp_user_store.delete_user(u1.id) is True
    assert temp_user_store.get_by_id(u1.id) is None
    assert len(temp_user_store.list_users()) == 1

    # Deleting again returns False
    assert temp_user_store.delete_user(u1.id) is False


def test_corrupt_files_handled_gracefully(temp_user_store: LocalUserStore):
    # Add a corrupt json file in a subdirectory
    bad_dir = temp_user_store.base_dir / "bad-user"
    bad_dir.mkdir()
    (bad_dir / "user.json").write_text("invalid json content", encoding="utf-8")

    # Also add a stray file directly in base_dir
    (temp_user_store.base_dir / "stray.txt").write_text("ignored", encoding="utf-8")

    # list_users should skip without crashing
    users = temp_user_store.list_users()
    assert isinstance(users, list)
    assert len(users) == 0

    # get_by_id on corrupt user returns None
    assert temp_user_store.get_by_id("bad-user") is None


def test_singleton_store():
    custom_store = LocalUserStore()
    set_user_store(custom_store)
    assert get_user_store() is custom_store
    set_user_store(None)  # reset
