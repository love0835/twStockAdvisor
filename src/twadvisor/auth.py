"""Authentication helpers for family accounts."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import sessionmaker

from twadvisor.storage.db import create_session_factory
from twadvisor.storage.models_orm import Base, UserRecord, UserSessionRecord

SESSION_COOKIE_NAME = "twadvisor_session"
SESSION_DAYS = 30
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,32}$")
PBKDF2_ITERATIONS = 210_000


@dataclass(frozen=True)
class CurrentUser:
    """Authenticated user context."""

    id: int
    username: str
    display_name: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def hash_password(password: str, *, salt: str | None = None) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256."""

    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a stored PBKDF2 hash."""

    try:
        algo, iterations, salt, expected = password_hash.split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations))
    return hmac.compare_digest(digest.hex(), expected)


def hash_session_token(token: str) -> str:
    """Hash an opaque session token for storage."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthService:
    """Manage users and login sessions."""

    def __init__(self, db_path: str) -> None:
        self.session_factory = create_session_factory(db_path)
        Base.metadata.create_all(self.session_factory.kw["bind"])

    def user_count(self) -> int:
        with self.session_factory() as session:
            return int(session.scalar(select(func.count(UserRecord.id))) or 0)

    def has_admin(self) -> bool:
        with self.session_factory() as session:
            return session.scalar(select(UserRecord).where(UserRecord.role == "admin")) is not None

    def create_user(
        self,
        *,
        username: str,
        password: str,
        display_name: str | None = None,
        role: str = "member",
    ) -> CurrentUser:
        username = normalize_username(username)
        if role not in {"admin", "member"}:
            raise ValueError("role must be admin or member")
        if len(password) < 8:
            raise ValueError("password must be at least 8 characters")
        now = datetime.utcnow().isoformat()
        record = UserRecord(
            username=username,
            display_name=display_name or username,
            password_hash=hash_password(password),
            role=role,
            is_active=1,
            created_at=now,
            updated_at=now,
        )
        with self.session_factory() as session:
            if session.scalar(select(UserRecord).where(UserRecord.username == username)):
                raise ValueError(f"user already exists: {username}")
            session.add(record)
            session.commit()
            session.refresh(record)
            return _current_user(record)

    def create_initial_admin_from_env(self) -> CurrentUser | None:
        if self.has_admin():
            return None
        username = os.environ.get("TWADVISOR_ADMIN_USERNAME")
        password = os.environ.get("TWADVISOR_ADMIN_PASSWORD")
        display_name = os.environ.get("TWADVISOR_ADMIN_DISPLAY_NAME")
        if not username or not password:
            return None
        return self.create_user(username=username, password=password, display_name=display_name, role="admin")

    def authenticate(self, username: str, password: str) -> CurrentUser | None:
        username = normalize_username(username)
        with self.session_factory() as session:
            user = session.scalar(select(UserRecord).where(UserRecord.username == username))
            if user is None or not user.is_active:
                return None
            if not verify_password(password, user.password_hash):
                return None
            return _current_user(user)

    def create_session(self, user_id: int) -> tuple[str, datetime]:
        token = secrets.token_urlsafe(32)
        now = datetime.utcnow()
        expires_at = now + timedelta(days=SESSION_DAYS)
        with self.session_factory() as session:
            session.add(
                UserSessionRecord(
                    user_id=user_id,
                    session_token_hash=hash_session_token(token),
                    expires_at=expires_at.isoformat(),
                    created_at=now.isoformat(),
                    last_seen_at=now.isoformat(),
                )
            )
            session.commit()
        return token, expires_at

    def get_user_by_session(self, token: str | None) -> CurrentUser | None:
        if not token:
            return None
        token_hash = hash_session_token(token)
        now = datetime.utcnow()
        with self.session_factory() as session:
            record = session.scalar(select(UserSessionRecord).where(UserSessionRecord.session_token_hash == token_hash))
            if record is None:
                return None
            if datetime.fromisoformat(record.expires_at) <= now:
                session.delete(record)
                session.commit()
                return None
            user = session.get(UserRecord, record.user_id)
            if user is None or not user.is_active:
                session.delete(record)
                session.commit()
                return None
            record.last_seen_at = now.isoformat()
            session.commit()
            return _current_user(user)

    def delete_session(self, token: str | None) -> None:
        if not token:
            return
        with self.session_factory() as session:
            session.execute(delete(UserSessionRecord).where(UserSessionRecord.session_token_hash == hash_session_token(token)))
            session.commit()

    def change_password(self, user_id: int, current_password: str, new_password: str) -> None:
        if len(new_password) < 8:
            raise ValueError("password must be at least 8 characters")
        with self.session_factory() as session:
            user = session.get(UserRecord, user_id)
            if user is None or not verify_password(current_password, user.password_hash):
                raise ValueError("current password is incorrect")
            user.password_hash = hash_password(new_password)
            user.updated_at = datetime.utcnow().isoformat()
            session.commit()

    def reset_password(self, username: str, new_password: str) -> None:
        if len(new_password) < 8:
            raise ValueError("password must be at least 8 characters")
        username = normalize_username(username)
        with self.session_factory() as session:
            user = session.scalar(select(UserRecord).where(UserRecord.username == username))
            if user is None:
                raise KeyError(username)
            user.password_hash = hash_password(new_password)
            user.updated_at = datetime.utcnow().isoformat()
            session.execute(delete(UserSessionRecord).where(UserSessionRecord.user_id == user.id))
            session.commit()

    def list_users(self) -> list[dict[str, object]]:
        with self.session_factory() as session:
            users = session.scalars(select(UserRecord).order_by(UserRecord.username.asc()))
            return [
                {
                    "id": user.id,
                    "username": user.username,
                    "display_name": user.display_name,
                    "role": user.role,
                    "is_active": bool(user.is_active),
                    "created_at": user.created_at,
                }
                for user in users
            ]

    def set_user_active(self, username: str, active: bool) -> None:
        username = normalize_username(username)
        with self.session_factory() as session:
            user = session.scalar(select(UserRecord).where(UserRecord.username == username))
            if user is None:
                raise KeyError(username)
            user.is_active = 1 if active else 0
            user.updated_at = datetime.utcnow().isoformat()
            if not active:
                session.execute(delete(UserSessionRecord).where(UserSessionRecord.user_id == user.id))
            session.commit()


def normalize_username(username: str) -> str:
    """Normalize and validate usernames."""

    value = username.strip().lower()
    if not USERNAME_PATTERN.match(value):
        raise ValueError("username must be 3-32 chars: letters, numbers, underscore")
    return value


def _current_user(record: UserRecord) -> CurrentUser:
    return CurrentUser(
        id=record.id,
        username=record.username,
        display_name=record.display_name,
        role=record.role,
    )
