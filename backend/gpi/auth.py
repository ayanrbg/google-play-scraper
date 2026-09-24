"""Users, password hashing and session tokens."""

import secrets
from datetime import datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gpi.models import Invite, User, Workspace
from gpi.settings import get_settings

_ph = PasswordHasher()
COOKIE = "gpi_session"


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(hash_: str, password: str) -> bool:
    try:
        return _ph.verify(hash_, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def normalize_email(email: str) -> str:
    return email.strip().lower()


def create_user(db: Session, email: str, password: str, workspace_id: int | None = None,
                workspace_name: str | None = None, role: str = "member", superadmin: bool = False,
                name: str | None = None) -> User:
    email = normalize_email(email)
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise ValueError("email_taken")
    if workspace_id is None:
        ws = Workspace(name=workspace_name or email.split("@")[0])
        db.add(ws)
        db.flush()
        workspace_id = ws.id
        role = "owner"
    user = User(email=email, password_hash=hash_password(password), workspace_id=workspace_id,
                role=role, is_superadmin=superadmin, name=name)
    db.add(user)
    db.flush()
    return user


def issue_token(user: User) -> str:
    cfg = get_settings()
    payload = {"sub": str(user.id), "exp": datetime.utcnow() + timedelta(days=cfg.session_days)}
    return jwt.encode(payload, cfg.secret_key, algorithm="HS256")


def read_token(token: str) -> int | None:
    try:
        data = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
        return int(data["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def new_invite(db: Session, workspace_id: int, created_by: int, email: str | None, role: str = "member",
               days: int = 14) -> Invite:
    inv = Invite(token=secrets.token_urlsafe(24), workspace_id=workspace_id, email=email, role=role,
                 created_by=created_by, expires_at=datetime.utcnow() + timedelta(days=days))
    db.add(inv)
    db.flush()
    return inv
