import pytest

from auth.user_store import UserAlreadyExistsError, UserNotFoundError
from db.postgres_user_store import PostgresUserStore
from shared_core.contracts.user import UserCreate


@pytest.fixture
def store(db_session):
    return PostgresUserStore()


def test_create_and_get_by_id(store):
    user = store.create_user(UserCreate(email="pg@example.com", full_name="PG User", password="password123"))

    fetched = store.get_by_id(user.id)

    assert fetched is not None
    assert fetched.email == "pg@example.com"
    assert fetched.full_name == "PG User"
    assert fetched.hashed_password  # real hash was computed and stored, not the plaintext


def test_get_by_email_is_case_insensitive(store):
    store.create_user(UserCreate(email="CaseTest@Example.com", full_name="Case Test", password="password123"))

    assert store.get_by_email("casetest@example.com") is not None
    assert store.get_by_email("CASETEST@EXAMPLE.COM") is not None


def test_create_duplicate_email_raises(store):
    store.create_user(UserCreate(email="dup@example.com", full_name="First", password="password123"))

    with pytest.raises(UserAlreadyExistsError):
        store.create_user(UserCreate(email="dup@example.com", full_name="Second", password="password456"))


def test_authenticate_user_success_and_failure(store):
    store.create_user(UserCreate(email="auth@example.com", full_name="Auth User", password="correctpassword"))

    assert store.authenticate_user("auth@example.com", "correctpassword") is not None
    assert store.authenticate_user("auth@example.com", "wrongpassword") is None
    assert store.authenticate_user("doesnotexist@example.com", "anything") is None


def test_update_password_changes_authentication(store):
    user = store.create_user(UserCreate(email="changepw@example.com", full_name="User", password="oldpassword"))

    store.update_password(user.id, "newpassword")

    assert store.authenticate_user("changepw@example.com", "oldpassword") is None
    assert store.authenticate_user("changepw@example.com", "newpassword") is not None


def test_update_password_unknown_user_raises(store):
    with pytest.raises(UserNotFoundError):
        store.update_password("does-not-exist", "newpassword")


def test_update_user_persists_preferences_and_api_keys(store):
    user = store.create_user(UserCreate(email="prefs@example.com", full_name="Prefs User", password="password123"))
    updated = user.model_copy(update={"preferences": {"dark_mode": "true"}, "api_keys": {"gemini": "key123"}})

    store.update_user(updated)
    reloaded = store.get_by_id(user.id)

    assert reloaded.preferences == {"dark_mode": "true"}
    assert reloaded.api_keys == {"gemini": "key123"}


def test_update_unknown_user_raises(store):
    user = store.create_user(UserCreate(email="ghost@example.com", full_name="Ghost", password="password123"))
    store.delete_user(user.id)

    with pytest.raises(UserNotFoundError):
        store.update_user(user)


def test_list_users_sorted_newest_first(store):
    first = store.create_user(UserCreate(email="first@example.com", full_name="First", password="password123"))
    second = store.create_user(UserCreate(email="second@example.com", full_name="Second", password="password123"))

    users = store.list_users()

    ids = [u.id for u in users]
    assert ids.index(second.id) < ids.index(first.id)


def test_delete_user(store):
    user = store.create_user(UserCreate(email="deleteme@example.com", full_name="Delete Me", password="password123"))

    assert store.delete_user(user.id) is True
    assert store.get_by_id(user.id) is None
    assert store.delete_user(user.id) is False  # already gone
