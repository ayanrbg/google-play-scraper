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


@dataclass
class Ctx:
    user: User
    workspace: Workspace

    @property
    def plan(self) -> dict:
        return plan(self.workspace.plan)


def current(request: Request, db: Session = Depends(get_db)) -> Ctx:
    token = request.cookies.get(COOKIE)
    user_id = read_token(token) if token else None
    user = db.get(User, user_id) if user_id else None
    if not user or not user.is_active:
        raise HTTPException(401, "not_authenticated")
    return Ctx(user=user, workspace=db.get(Workspace, user.workspace_id))


def owner(ctx: Ctx = Depends(current)) -> Ctx:
    if ctx.user.role != "owner" and not ctx.user.is_superadmin:
        raise HTTPException(403, "owner_only")
    return ctx


def superadmin(ctx: Ctx = Depends(current)) -> Ctx:
    if not ctx.user.is_superadmin:
        raise HTTPException(403, "superadmin_only")
    return ctx


def feature(name: str):
    def check(ctx: Ctx = Depends(current)) -> Ctx:
        if not ctx.plan.get(name):
            raise HTTPException(402, f"plan_feature:{name}")
        return ctx
    return check
