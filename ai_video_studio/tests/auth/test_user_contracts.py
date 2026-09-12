import pytest
from pydantic import ValidationError

from shared_core.contracts.user import User, UserBase, UserCreate, UserInDB, UserResponse


def test_user_base_validation():
    valid = UserBase(email="creator@example.com", full_name="Jane Director")
    assert valid.email == "creator@example.com"
    assert valid.full_name == "Jane Director"
    assert valid.is_active is True

    # Email case normalization
    mixed_case = UserBase(email="Creator@Example.COM", full_name="Jane")
    assert mixed_case.email == "creator@example.com"

    # Invalid email formats
    with pytest.raises(ValidationError):
        UserBase(email="notanemail", full_name="Jane")

    with pytest.raises(ValidationError):
        UserBase(email="bad@domain", full_name="Jane")

    # Blank name
    with pytest.raises(ValidationError):
        UserBase(email="creator@example.com", full_name="   ")


def test_user_create_validation():
    user_create = UserCreate(
        email="test@studio.ai",
        full_name="Test Creator",
        password="securePassword123",
    )
    assert user_create.password == "securePassword123"

    # Password too short (< 6 chars)
    with pytest.raises(ValidationError):
        UserCreate(email="test@studio.ai", full_name="Test", password="123")

    # Whitespace-only password
    with pytest.raises(ValidationError):
        UserCreate(email="test@studio.ai", full_name="Test", password="      ")


def test_user_in_db_to_user_and_response():
    db_user = UserInDB(
        email="director@studio.ai",
        full_name="Art Director",
        hashed_password="hashed_string_12345",
        salt="salt_abcdef",
    )

    assert db_user.id
    assert db_user.created_at
    assert db_user.updated_at
    assert db_user.hashed_password == "hashed_string_12345"
    assert db_user.salt == "salt_abcdef"

    # Convert to domain User
    user = db_user.to_user()
    assert isinstance(user, User)
    assert user.id == db_user.id
    assert user.email == db_user.email
    assert user.full_name == db_user.full_name
    assert not hasattr(user, "hashed_password")
    assert not hasattr(user, "salt")

    # Convert to UserResponse
    response = db_user.to_response()
    assert isinstance(response, UserResponse)
    assert response.id == db_user.id
    assert response.email == db_user.email
    assert response.full_name == db_user.full_name
    assert not hasattr(response, "hashed_password")
    assert not hasattr(response, "salt")

    # Serialization does not contain sensitive fields
    dump = response.model_dump()
    assert "hashed_password" not in dump
    assert "salt" not in dump
    assert "password" not in dump


def test_user_response_from_user():
    user = User(
        id="usr-1234",
        email="member@studio.ai",
        full_name="Member One",
    )
    response = UserResponse.from_user(user)
    assert response.id == "usr-1234"
    assert response.email == "member@studio.ai"
    assert response.full_name == "Member One"
