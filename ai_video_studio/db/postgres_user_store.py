"""PostgresUserStore - the RDS-backed alternative to auth/user_store.py's
LocalUserStore, implementing the exact same UserStore abstract interface
that module already defines. This is a genuine extension point the
existing architecture already provided (UserStore is already an ABC,
constructed via web_api/dependencies.py::get_user_store) - no interface
changes were needed to add this."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import List, Optional

from auth.security import create_password_hash, verify_password
from auth.user_store import UserAlreadyExistsError, UserNotFoundError, UserStore
from db.connection import get_pool
from shared_core.contracts.user import UserCreate, UserInDB
from utils.logger import get_logger

logger = get_logger("db.postgres_user_store")


def _row_to_user(row: tuple) -> UserInDB:
    (
        id_, email, full_name, is_active, hashed_password, salt,
        preferences, api_keys, created_at, updated_at,
    ) = row
    return UserInDB(
        id=id_,
        email=email,
        full_name=full_name,
        is_active=is_active,
        hashed_password=hashed_password,
        salt=salt,
        preferences=preferences or {},
        api_keys=api_keys or {},
        created_at=created_at,
        updated_at=updated_at,
    )


_SELECT_COLUMNS = "id, email, full_name, is_active, hashed_password, salt, preferences, api_keys, created_at, updated_at"


class PostgresUserStore(UserStore):
    def create_user(self, user_create: UserCreate) -> UserInDB:
        normalized_email = user_create.email.strip().lower()
        if self.get_by_email(normalized_email) is not None:
            raise UserAlreadyExistsError(f"User with email '{normalized_email}' already exists")

        hashed_password, salt = create_password_hash(user_create.password)
        now = datetime.now(UTC)
        user = UserInDB(
            email=normalized_email,
            full_name=user_create.full_name.strip(),
            is_active=user_create.is_active,
            hashed_password=hashed_password,
            salt=salt,
            created_at=now,
            updated_at=now,
        )

        with get_pool().connection() as conn:
            conn.execute(
                f"""
                INSERT INTO users (id, email, full_name, is_active, hashed_password, salt,
                                    preferences, api_keys, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user.id, user.email, user.full_name, user.is_active,
                    user.hashed_password, user.salt,
                    json.dumps(user.preferences), json.dumps(user.api_keys),
                    user.created_at, user.updated_at,
                ),
            )
        logger.info(f"User {user.id} ({user.email}) successfully created")
        return user

    def get_by_id(self, user_id: str) -> Optional[UserInDB]:
        with get_pool().connection() as conn:
            row = conn.execute(f"SELECT {_SELECT_COLUMNS} FROM users WHERE id = %s", (user_id,)).fetchone()
        return _row_to_user(row) if row else None

    def get_by_email(self, email: str) -> Optional[UserInDB]:
        normalized = email.strip().lower()
        with get_pool().connection() as conn:
            row = conn.execute(
                f"SELECT {_SELECT_COLUMNS} FROM users WHERE LOWER(email) = %s", (normalized,)
            ).fetchone()
        return _row_to_user(row) if row else None

    def update_user(self, user: UserInDB) -> UserInDB:
        updated = user.model_copy(update={"updated_at": datetime.now(UTC)})
        with get_pool().connection() as conn:
            result = conn.execute(
                """
                UPDATE users SET email = %s, full_name = %s, is_active = %s,
                                  hashed_password = %s, salt = %s,
                                  preferences = %s, api_keys = %s, updated_at = %s
                WHERE id = %s
                """,
                (
                    updated.email, updated.full_name, updated.is_active,
                    updated.hashed_password, updated.salt,
                    json.dumps(updated.preferences), json.dumps(updated.api_keys),
                    updated.updated_at, updated.id,
                ),
            )
            if result.rowcount == 0:
                raise UserNotFoundError(f"User {user.id} not found")
        logger.info(f"User {user.id} updated")
        return updated

    def update_password(self, user_id: str, new_password: str) -> UserInDB:
        user = self.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} not found")

        hashed_password, salt = create_password_hash(new_password)
        updated = user.model_copy(update={
            "hashed_password": hashed_password,
            "salt": salt,
            "updated_at": datetime.now(UTC),
        })
        with get_pool().connection() as conn:
            conn.execute(
                "UPDATE users SET hashed_password = %s, salt = %s, updated_at = %s WHERE id = %s",
                (updated.hashed_password, updated.salt, updated.updated_at, user_id),
            )
        logger.info(f"Password for user {user_id} updated")
        return updated

    def authenticate_user(self, email: str, password: str) -> Optional[UserInDB]:
        user = self.get_by_email(email)
        if user is None:
            return None
        if not user.is_active:
            return None
        if not verify_password(password, user.hashed_password, user.salt):
            return None
        return user

    def list_users(self) -> List[UserInDB]:
        with get_pool().connection() as conn:
            rows = conn.execute(f"SELECT {_SELECT_COLUMNS} FROM users ORDER BY created_at DESC").fetchall()
        return [_row_to_user(row) for row in rows]

    def delete_user(self, user_id: str) -> bool:
        with get_pool().connection() as conn:
            result = conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
        deleted = result.rowcount > 0
        if deleted:
            logger.info(f"User {user_id} deleted")
        return deleted
