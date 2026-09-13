import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator

from auth.security import (
    ExpiredTokenError,
    InvalidTokenError,
    create_access_token,
    create_password_reset_token,
    decode_password_reset_token,
    verify_password,
)
from auth.user_store import UserAlreadyExistsError, UserStore
from shared_core.contracts.user import UserCreate, UserResponse, UserUpdate, UserPasswordUpdate
from utils.logger import get_logger
from web_api.dependencies import get_current_user, get_user_store

logger = get_logger("web_api.auth")


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, description="User email address")
    password: str = Field(..., min_length=1, description="Account password")


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class MessageResponse(BaseModel):
    status: str = "ok"
    message: str


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=3, description="User email address")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if "@" not in clean or "." not in clean.split("@")[-1]:
            raise ValueError("Invalid email format")
        return clean


class ForgotPasswordResponse(BaseModel):
    status: str = "ok"
    message: str
    reset_token: Optional[str] = None


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=1, description="Password reset recovery token")
    new_password: str = Field(..., min_length=6, description="New plaintext password")

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Password cannot be empty or whitespace only")
        if len(clean) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
def register(
    body: UserCreate,
    response: Response,
    user_store: UserStore = Depends(get_user_store),
) -> AuthResponse:
    try:
        user = user_store.create_user(body)
    except UserAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    token = create_access_token(
        data={
            "sub": user.id,
            "email": user.email,
            "name": user.full_name,
        }
    )
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=86400,
        path="/",
    )
    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user=user.to_response(),
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and return access token",
)
def login(
    body: LoginRequest,
    response: Response,
    user_store: UserStore = Depends(get_user_store),
) -> AuthResponse:
    user = user_store.authenticate_user(email=body.email, password=body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(
        data={
            "sub": user.id,
            "email": user.email,
            "name": user.full_name,
        }
    )
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=86400,
        path="/",
    )
    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user=user.to_response(),
    )


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current user profile",
)
def get_me(
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    return current_user


@router.patch(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update current user profile, preferences, or API keys",
)
def update_me(
    body: UserUpdate,
    current_user: UserResponse = Depends(get_current_user),
    user_store: UserStore = Depends(get_user_store),
) -> UserResponse:
    user = user_store.get_by_id(current_user.id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return user.to_response()

    updated = user.model_copy(update=updates)
    user_store.update_user(updated)
    return updated.to_response()


@router.patch(
    "/me/password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Update current user password",
)
def update_password(
    body: UserPasswordUpdate,
    current_user: UserResponse = Depends(get_current_user),
    user_store: UserStore = Depends(get_user_store),
) -> MessageResponse:
    user = user_store.get_by_id(current_user.id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Verify current password
    if not verify_password(body.current_password, user.hashed_password, user.salt):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Current password is incorrect",
        )

    try:
        user_store.update_password(user.id, body.new_password)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return MessageResponse(
        status="ok",
        message="Password has been successfully updated.",
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Log out and clear auth cookies",
)
def logout(
    response: Response,
) -> MessageResponse:
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="session_token", path="/")
    return MessageResponse(
        status="ok",
        message="Successfully logged out",
    )


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    status_code=status.HTTP_200_OK,
    summary="Request a password reset link",
)
def forgot_password(
    body: ForgotPasswordRequest,
    user_store: UserStore = Depends(get_user_store),
) -> ForgotPasswordResponse:
    clean_email = body.email.strip().lower()
    user = user_store.get_by_email(clean_email)
    reset_token: Optional[str] = None

    if user is not None and user.is_active:
        reset_token = create_password_reset_token(
            user_id=user.id,
            email=user.email,
            password_fingerprint=user.hashed_password[:12],
        )
        logger.info(f"Password reset token generated for user {user.id} ({user.email})")

    # Neutral response to prevent account enumeration
    env = os.getenv("ENVIRONMENT", "development").lower()
    include_token = env != "production" or os.getenv("AUTH_DEV_MODE", "false").lower() == "true"

    return ForgotPasswordResponse(
        status="ok",
        message="If an account exists with that email, a password reset link has been sent.",
        reset_token=reset_token if include_token else None,
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset user password using a recovery token",
)
def reset_password(
    body: ResetPasswordRequest,
    user_store: UserStore = Depends(get_user_store),
) -> MessageResponse:
    try:
        payload = decode_password_reset_token(body.token)
    except ExpiredTokenError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset token has expired",
        )
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid password reset token: {exc}",
        )

    user_id = payload.get("sub")
    token_fp = payload.get("pwd_fp")

    user = user_store.get_by_id(user_id) if user_id else None
    if user is None and payload.get("email"):
        user = user_store.get_by_email(payload["email"])

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User associated with reset token not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot reset password for inactive user",
        )

    # Enforce single-use: if user's password hash changed after token was issued, reject
    if token_fp and user.hashed_password[:12] != token_fp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset token has already been used or invalidated",
        )

    try:
        user_store.update_password(user.id, body.new_password)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return MessageResponse(
        status="ok",
        message="Password has been successfully reset.",
    )

