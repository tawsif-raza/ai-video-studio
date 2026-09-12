import json
import shutil
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path
from typing import List, Optional

from auth.security import create_password_hash, verify_password
from config import settings
from shared_core.contracts.user import UserCreate, UserInDB
from utils.logger import get_logger

logger = get_logger("app")


class UserAlreadyExistsError(ValueError):
    """Raised when creating a user with an email that is already registered."""
    pass


class UserNotFoundError(ValueError):
    """Raised when an operation references a user that does not exist."""
    pass


class UserStore(ABC):
    """
    Abstract user storage contract defining user lifecycle and query methods.
    """

    @abstractmethod
    def create_user(self, user_create: UserCreate) -> UserInDB:
        """
        Create and persist a new user.
        Raises UserAlreadyExistsError if email is already registered.
        """
        pass

    @abstractmethod
    def get_by_id(self, user_id: str) -> Optional[UserInDB]:
        """
        Retrieve a user by their unique identifier.
        """
        pass

    @abstractmethod
    def get_by_email(self, email: str) -> Optional[UserInDB]:
        """
        Retrieve a user by their primary email address (case-insensitive).
        """
        pass

    @abstractmethod
    def update_user(self, user: UserInDB) -> UserInDB:
        """
        Update and persist modifications to an existing user record.
        """
        pass

    @abstractmethod
    def update_password(self, user_id: str, new_password: str) -> UserInDB:
        """
        Update a user's password, generating a new salt and hash.
        """
        pass

    @abstractmethod
    def authenticate_user(self, email: str, password: str) -> Optional[UserInDB]:
        """
        Authenticate credentials against stored hash and salt.
        Returns UserInDB on match, None on invalid credentials or inactive account.
        """
        pass

    @abstractmethod
    def list_users(self) -> List[UserInDB]:
        """
        List all users, sorted by creation date descending.
        """
        pass

    @abstractmethod
    def delete_user(self, user_id: str) -> bool:
        """
        Delete a user by ID. Returns True if deleted, False if not found.
        """
        pass


class LocalUserStore(UserStore):
    """
    Local filesystem JSON user store.
    Stores user records under base_dir / <user_id> / "user.json",
    following the established ProjectManager file storage discipline.
    """

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = Path(base_dir) if base_dir is not None else (settings.OUTPUT_DIR / "users")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._email_index: Optional[dict[str, str]] = None

    def _user_dir(self, user_id: str) -> Path:
        # Prevent directory traversal attacks
        safe_id = Path(user_id).name
        return self.base_dir / safe_id

    def _user_file(self, user_id: str) -> Path:
        return self._user_dir(user_id) / "user.json"

    def _write_user_file(self, user: UserInDB) -> None:
        user_dir = self._user_dir(user.id)
        user_dir.mkdir(parents=True, exist_ok=True)
        self._user_file(user.id).write_text(user.model_dump_json(indent=2), encoding="utf-8")
        if self._email_index is not None:
            self._email_index[user.email.strip().lower()] = user.id

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
        self._write_user_file(user)
        logger.info(f"User {user.id} ({user.email}) successfully created")
        return user

    def get_by_id(self, user_id: str) -> Optional[UserInDB]:
        file_path = self._user_file(user_id)
        if not file_path.is_file():
            return None
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            return UserInDB(**data)
        except Exception as exc:
            logger.warning(f"Failed to parse user file {file_path}: {exc}")
            return None

    def get_by_email(self, email: str) -> Optional[UserInDB]:
        normalized = email.strip().lower()
        if self._email_index is None:
            self._email_index = {}
            for user in self.list_users():
                self._email_index[user.email.strip().lower()] = user.id
        
        user_id = self._email_index.get(normalized)
        if user_id:
            return self.get_by_id(user_id)
        return None

    def update_user(self, user: UserInDB) -> UserInDB:
        file_path = self._user_file(user.id)
        if not file_path.is_file():
            raise UserNotFoundError(f"User {user.id} not found")

        updated = user.model_copy(update={"updated_at": datetime.now(UTC)})
        self._write_user_file(updated)
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
        self._write_user_file(updated)
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
        if not self.base_dir.exists():
            return []
        users: List[UserInDB] = []
        for user_dir in self.base_dir.iterdir():
            if not user_dir.is_dir():
                continue
            user_file = user_dir / "user.json"
            if not user_file.is_file():
                continue
            try:
                data = json.loads(user_file.read_text(encoding="utf-8"))
                users.append(UserInDB(**data))
            except Exception as exc:
                logger.warning(f"Skipping invalid user file {user_file}: {exc}")
                continue
        return sorted(users, key=lambda u: u.created_at, reverse=True)

    def delete_user(self, user_id: str) -> bool:
        user_dir = self._user_dir(user_id)
        if not user_dir.is_dir():
            return False
            
        user = self.get_by_id(user_id)
        shutil.rmtree(user_dir)
        if user and self._email_index is not None:
            self._email_index.pop(user.email.strip().lower(), None)
            
        logger.info(f"User directory {user_dir} deleted")
        return True


_user_store_instance: Optional[UserStore] = None


def get_user_store() -> UserStore:
    """
    Singleton getter for process-wide UserStore.
    """
    global _user_store_instance
    if _user_store_instance is None:
        _user_store_instance = LocalUserStore()
    return _user_store_instance


def set_user_store(store: Optional[UserStore]) -> None:
    """
    Setter for dependency injection or test overrides.
    """
    global _user_store_instance
    _user_store_instance = store
