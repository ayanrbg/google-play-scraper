from dataclasses import dataclass
from typing import Iterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from gpi.auth import COOKIE, read_token
from gpi.db import SessionLocal
from gpi.models import User, Workspace
from gpi.plans import plan


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# The site is public: anonymous visitors read everything with this plan. Signing in only adds
# what belongs to a team (marks, saved views, settings) and admin tools.
GUEST_PLAN = "team"


@dataclass
class Ctx:
    user: User | None
    workspace: Workspace | None

    @property
    def plan(self) -> dict:
        return plan(self.workspace.plan if self.workspace else GUEST_PLAN)

    @property
    def workspace_id(self) -> int:
        """0 for guests: joins against per-workspace tables (marks) then match nothing."""
        return self.workspace.id if self.workspace else 0

    @property
    def is_superadmin(self) -> bool:
        return bool(self.user and self.user.is_superadmin)


def viewer(request: Request, db: Session = Depends(get_db)) -> Ctx:
    """The signed-in user, or a guest. For read-only endpoints."""
    token = request.cookies.get(COOKIE)
    user_id = read_token(token) if token else None
    user = db.get(User, user_id) if user_id else None
    if not user or not user.is_active:
        return Ctx(user=None, workspace=None)
    return Ctx(user=user, workspace=db.get(Workspace, user.workspace_id))


def current(ctx: Ctx = Depends(viewer)) -> Ctx:
    """A signed-in user. For anything that writes or is private to a team."""
    if not ctx.user:
        raise HTTPException(401, "not_authenticated")
    return ctx


def owner(ctx: Ctx = Depends(current)) -> Ctx:
    if ctx.user.role != "owner" and not ctx.user.is_superadmin:
        raise HTTPException(403, "owner_only")
    return ctx


def superadmin(ctx: Ctx = Depends(current)) -> Ctx:
    if not ctx.user.is_superadmin:
        raise HTTPException(403, "superadmin_only")
    return ctx


def feature(name: str):
    def check(ctx: Ctx = Depends(viewer)) -> Ctx:
        if not ctx.plan.get(name):
            raise HTTPException(402, f"plan_feature:{name}")
        return ctx
    return check
