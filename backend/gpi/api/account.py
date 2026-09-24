"""Auth, team (workspace members & invites) and saved filter views."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gpi.api.deps import Ctx, current, get_db, owner
from gpi.auth import COOKIE, create_user, issue_token, new_invite, normalize_email, verify_password
from gpi.models import Invite, SavedView, User, Workspace
from gpi.plans import PLANS
from gpi.settings import get_settings

router = APIRouter(prefix="/api")


class LoginIn(BaseModel):
    email: str
    password: str


class RegisterIn(BaseModel):
    email: str
    password: str = Field(min_length=8)
    name: str | None = None
    invite: str | None = None
    workspace_name: str | None = None


def _set_cookie(resp: Response, user: User):
    cfg = get_settings()
    resp.set_cookie(COOKIE, issue_token(user), max_age=cfg.session_days * 86400, httponly=True,
                    samesite="lax", secure=cfg.cookie_secure, path="/")


def me_payload(ctx: Ctx) -> dict:
    return {
        "id": ctx.user.id, "email": ctx.user.email, "name": ctx.user.name, "role": ctx.user.role,
        "is_superadmin": ctx.user.is_superadmin,
        "workspace": {"id": ctx.workspace.id, "name": ctx.workspace.name, "plan": ctx.workspace.plan},
        "plan": ctx.plan,
    }


@router.get("/auth/config")
def auth_config():
    return {"registration": get_settings().registration}


@router.post("/auth/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == normalize_email(body.email)))
    if not user or not user.is_active or not verify_password(user.password_hash, body.password):
        raise HTTPException(401, "invalid_credentials")
    user.last_login = datetime.utcnow()
    _set_cookie(response, user)
    return {"ok": True}


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/invite/{token}")
def invite_info(token: str, db: Session = Depends(get_db)):
    inv = db.get(Invite, token)
    if not inv or inv.used_at or inv.expires_at < datetime.utcnow():
        raise HTTPException(404, "invite_invalid")
    ws = db.get(Workspace, inv.workspace_id)
    return {"workspace": ws.name, "email": inv.email}


@router.post("/auth/register")
def register(body: RegisterIn, response: Response, db: Session = Depends(get_db)):
    cfg = get_settings()
    inv = None
    if body.invite:
        inv = db.get(Invite, body.invite)
        if not inv or inv.used_at or inv.expires_at < datetime.utcnow():
            raise HTTPException(400, "invite_invalid")
        if inv.email and normalize_email(inv.email) != normalize_email(body.email):
            raise HTTPException(400, "invite_email_mismatch")
    elif cfg.registration != "open":
        raise HTTPException(403, "registration_closed")
    try:
        if inv:
            user = create_user(db, body.email, body.password, workspace_id=inv.workspace_id, role=inv.role, name=body.name)
            inv.used_at = datetime.utcnow()
        else:
            user = create_user(db, body.email, body.password, workspace_name=body.workspace_name, name=body.name)
            db.get(Workspace, user.workspace_id).plan = cfg.default_plan
    except ValueError:
        raise HTTPException(400, "email_taken")
    _set_cookie(response, user)
    return {"ok": True}


@router.get("/me")
def me(ctx: Ctx = Depends(current)):
    return me_payload(ctx)


class PasswordIn(BaseModel):
    current: str
    new: str = Field(min_length=8)


@router.post("/me/password")
def change_password(body: PasswordIn, ctx: Ctx = Depends(current), db: Session = Depends(get_db)):
    from gpi.auth import hash_password
    user = db.get(User, ctx.user.id)
    if not verify_password(user.password_hash, body.current):
        raise HTTPException(400, "invalid_credentials")
    user.password_hash = hash_password(body.new)
    return {"ok": True}


# ----------------------------- team -----------------------------

@router.get("/team")
def team(ctx: Ctx = Depends(current), db: Session = Depends(get_db)):
    members = db.scalars(select(User).where(User.workspace_id == ctx.workspace.id).order_by(User.created_at)).all()
    invites = db.scalars(select(Invite).where(Invite.workspace_id == ctx.workspace.id, Invite.used_at.is_(None),
                                              Invite.expires_at > datetime.utcnow())).all() if ctx.user.role == "owner" else []
    return {
        "members": [{"id": u.id, "email": u.email, "name": u.name, "role": u.role, "is_active": u.is_active,
                     "last_login": u.last_login} for u in members],
        "invites": [{"token": i.token, "email": i.email, "expires_at": i.expires_at,
                     "url": f"{get_settings().public_url}/register?invite={i.token}"} for i in invites],
        "seats": ctx.plan["seats"],
    }


class InviteIn(BaseModel):
    email: str | None = None
    role: str = "member"


@router.post("/team/invites")
def create_invite(body: InviteIn, ctx: Ctx = Depends(owner), db: Session = Depends(get_db)):
    seats = db.scalar(select(func.count(User.id)).where(User.workspace_id == ctx.workspace.id, User.is_active.is_(True)))
    if seats >= ctx.plan["seats"]:
        raise HTTPException(402, "plan_limit:seats")
    inv = new_invite(db, ctx.workspace.id, ctx.user.id, body.email, "owner" if body.role == "owner" else "member")
    return {"token": inv.token, "url": f"{get_settings().public_url}/register?invite={inv.token}"}


@router.delete("/team/invites/{token}")
def revoke_invite(token: str, ctx: Ctx = Depends(owner), db: Session = Depends(get_db)):
    inv = db.get(Invite, token)
    if inv and inv.workspace_id == ctx.workspace.id:
        db.delete(inv)
    return {"ok": True}


class MemberIn(BaseModel):
    role: str | None = None
    is_active: bool | None = None


@router.patch("/team/members/{user_id}")
def update_member(user_id: int, body: MemberIn, ctx: Ctx = Depends(owner), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u or u.workspace_id != ctx.workspace.id or u.id == ctx.user.id:
        raise HTTPException(404, "not_found")
    if body.role in ("owner", "member"):
        u.role = body.role
    if body.is_active is not None:
        u.is_active = body.is_active
    return {"ok": True}


# ----------------------------- saved views -----------------------------

class ViewIn(BaseModel):
    page: str
    name: str = Field(min_length=1, max_length=255)
    params: dict


@router.get("/views")
def list_views(page: str, ctx: Ctx = Depends(current), db: Session = Depends(get_db)):
    rows = db.scalars(select(SavedView).where(SavedView.workspace_id == ctx.workspace.id, SavedView.page == page)
                      .order_by(SavedView.created_at)).all()
    return [{"id": v.id, "name": v.name, "params": v.params, "user_id": v.user_id} for v in rows]


@router.post("/views")
def create_view(body: ViewIn, ctx: Ctx = Depends(current), db: Session = Depends(get_db)):
    count = db.scalar(select(func.count(SavedView.id)).where(SavedView.workspace_id == ctx.workspace.id))
    if count >= ctx.plan["saved_views"]:
        raise HTTPException(402, "plan_limit:saved_views")
    v = SavedView(workspace_id=ctx.workspace.id, user_id=ctx.user.id, page=body.page, name=body.name, params=body.params)
    db.add(v)
    db.flush()
    return {"id": v.id}


@router.delete("/views/{view_id}")
def delete_view(view_id: int, ctx: Ctx = Depends(current), db: Session = Depends(get_db)):
    v = db.get(SavedView, view_id)
    if v and v.workspace_id == ctx.workspace.id:
        db.delete(v)
    return {"ok": True}


@router.get("/plans")
def plans():
    return PLANS
