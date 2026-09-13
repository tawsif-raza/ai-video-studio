import uuid
from datetime import UTC, datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class UserBase(BaseModel):
    email: str = Field(..., min_length=3, description="User primary email address")
    full_name: str = Field(..., min_length=1, description="User full display name")
    is_active: bool = Field(default=True, description="Whether account is active")
    preferences: dict[str, str] = Field(default_factory=dict, description="User preferences like dark_mode or aspect_ratio")
    api_keys: dict[str, str] = Field(default_factory=dict, description="User-provided API key overrides")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if "@" not in clean or "." not in clean.split("@")[-1]:
            raise ValueError("Invalid email format")
        return clean

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Full name cannot be blank")
        return clean


class UserCreate(UserBase):
    password: str = Field(..., min_length=6, description="Plaintext password for registration")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Password cannot be empty or whitespace only")
        return v


class User(UserBase):
    id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UserResponse(UserBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    @classmethod
    def from_user(cls, user: UserBase) -> "UserResponse":
        return cls(
            id=getattr(user, "id", ""),
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            preferences=getattr(user, "preferences", {}),
            api_keys=getattr(user, "api_keys", {}),
            created_at=getattr(user, "created_at", datetime.now(UTC)),
            updated_at=getattr(user, "updated_at", None),
        )


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1)
    preferences: Optional[dict[str, str]] = None
    api_keys: Optional[dict[str, str]] = None

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip()
            if not clean:
                raise ValueError("Full name cannot be blank")
            return clean
        return v


class UserPasswordUpdate(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Password cannot be empty or whitespace only")
        if len(clean) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v


class UserInDB(UserBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    hashed_password: str
    salt: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_user(self) -> User:
        return User(
            id=self.id,
            email=self.email,
            full_name=self.full_name,
            is_active=self.is_active,
            preferences=self.preferences,
            api_keys=self.api_keys,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    def to_response(self) -> UserResponse:
        return UserResponse(
            id=self.id,
            email=self.email,
            full_name=self.full_name,
            is_active=self.is_active,
            preferences=self.preferences,
            api_keys=self.api_keys,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
