"""Data status, brand rules, platform administration."""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gpi.api.deps import Ctx, current, get_db, superadmin
from gpi.models import App, BrandRule, ChartDaily, GameMetrics, JobRun, Keyword, Snapshot, User, Workspace
from gpi.plans import PLANS

router = APIRouter(prefix="/api")


@router.get("/status")
def status(ctx: Ctx = Depends(current), db: Session = Depends(get_db)):
    last_runs = {}
    for job in ["daily", "charts", "expand", "enrich", "track", "metrics", "keywords"]:
        r = db.scalar(select(JobRun).where(JobRun.job == job).order_by(JobRun.started_at.desc()).limit(1))
        if r:
            last_runs[job] = {"status": r.status, "started_at": r.started_at, "finished_at": r.finished_at,
                              "stats": r.stats, "error": (r.error or "")[-600:] if ctx.user.is_superadmin else None}
    return {
        "apps": db.scalar(select(func.count(App.app_id))),
        "tracked": db.scalar(select(func.count(App.app_id)).where(App.tracked.is_(True))),
        "radar": db.scalar(select(func.count(GameMetrics.app_id))),
        "keywords": db.scalar(select(func.count(Keyword.id)).where(Keyword.analyzed_at.is_not(None))),
        "last_snapshot": db.scalar(select(func.max(Snapshot.date))),
        "last_chart": db.scalar(select(func.max(ChartDaily.date))),
        "runs": last_runs,
        "pending_run": bool(db.scalar(select(JobRun.id).where(JobRun.job == "request:daily", JobRun.status == "pending"))),
    }


@router.post("/admin/run")
def request_run(ctx: Ctx = Depends(superadmin), db: Session = Depends(get_db)):
    """Ask the worker to start the daily pipeline now."""
    if not db.scalar(select(JobRun.id).where(JobRun.job == "request:daily", JobRun.status == "pending")):
        db.add(JobRun(job="request:daily", status="pending", stats={"by": ctx.user.email}))
    return {"ok": True}


# ----------------------------- brand rules -----------------------------

class RuleIn(BaseModel):
    kind: str
    pattern: str = Field(min_length=2, max_length=255)
    note: str | None = None


@router.get("/brand-rules")
def list_rules(ctx: Ctx = Depends(current), db: Session = Depends(get_db)):
    rows = db.scalars(select(BrandRule).order_by(BrandRule.kind, BrandRule.pattern)).all()
    return [{"id": r.id, "kind": r.kind, "pattern": r.pattern, "note": r.note} for r in rows]


@router.post("/brand-rules")
def add_rule(body: RuleIn, ctx: Ctx = Depends(superadmin), db: Session = Depends(get_db)):
    if body.kind not in ("major", "hc_publisher", "franchise"):
        raise HTTPException(400, "bad_kind")
    pattern = body.pattern.strip()
    if db.scalar(select(BrandRule.id).where(BrandRule.kind == body.kind, BrandRule.pattern == pattern)):
        raise HTTPException(400, "exists")
    r = BrandRule(kind=body.kind, pattern=pattern, note=body.note or ctx.user.email)
    db.add(r)
    db.flush()
    return {"id": r.id}


@router.delete("/brand-rules/{rule_id}")
def delete_rule(rule_id: int, ctx: Ctx = Depends(superadmin), db: Session = Depends(get_db)):
    r = db.get(BrandRule, rule_id)
    if r:
        db.delete(r)
    return {"ok": True}


# ----------------------------- platform -----------------------------

@router.get("/admin/workspaces")
def workspaces(ctx: Ctx = Depends(superadmin), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(User.workspace_id, func.count(User.id)).group_by(User.workspace_id)).all())
    return [{"id": w.id, "name": w.name, "plan": w.plan, "created_at": w.created_at, "users": counts.get(w.id, 0)}
            for w in db.scalars(select(Workspace).order_by(Workspace.created_at)).all()]


class PlanIn(BaseModel):
    plan: str


@router.patch("/admin/workspaces/{ws_id}")
def set_plan(ws_id: int, body: PlanIn, ctx: Ctx = Depends(superadmin), db: Session = Depends(get_db)):
    if body.plan not in PLANS:
        raise HTTPException(400, "bad_plan")
    ws = db.get(Workspace, ws_id)
    if not ws:
        raise HTTPException(404, "not_found")
    ws.plan = body.plan
    return {"ok": True}
