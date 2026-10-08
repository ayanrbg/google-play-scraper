"""The "to build" section: games picked by hand for the team, with live metrics next to the reasoning."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from playtrend.api.deps import Ctx, current, get_db
from playtrend.api.games import row_payload
from playtrend.models import App, GameMetrics, Keyword, Mark, Pick

router = APIRouter(prefix="/api")


@router.get("/picks")
def picks(ctx: Ctx = Depends(current), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Pick, App, GameMetrics, Mark.status, Mark.note)
        .join(App, App.app_id == Pick.app_id)
        .outerjoin(GameMetrics, GameMetrics.app_id == Pick.app_id)
        .outerjoin(Mark, (Mark.app_id == Pick.app_id) & (Mark.workspace_id == ctx.workspace.id))
        .where(Pick.workspace_id == ctx.workspace.id).order_by(Pick.position)).all()
    rival_ids = {r for p, *_ in rows for r in p.rivals or []}
    rivals = {a.app_id: {"app_id": a.app_id, "title": a.title, "icon_url": a.icon_url, "installs": a.real_installs,
                         "v7": m.v7 if m else None, "age_days": m.age_days if m else None}
              for a, m in db.execute(select(App, GameMetrics).outerjoin(GameMetrics, GameMetrics.app_id == App.app_id)
                                     .where(App.app_id.in_(rival_ids)))} if rival_ids else {}
    pairs = {(k["term"], k["country"]) for p, *_ in rows for k in p.keys or []}
    live = {(k.term, k.country): k for k in db.scalars(select(Keyword).where(
        Keyword.term.in_({t for t, _ in pairs}), Keyword.analyzed_at.is_not(None)))} if pairs else {}

    def with_entry(key: dict) -> dict:
        k = live.get((key["term"], key["country"]))
        return {**key, "keyword_id": k.id if k else None, "room": k.room if k else None,
                "room_best": k.room_best if k else None, "fresh": k.fresh_count if k else None,
                "entry_score": k.entry_score if k else None}

    items = []
    for p, app, m, status, note in rows:
        game = row_payload(app, m, status, note) if m else {
            "app_id": app.app_id, "title": app.title, "developer": app.developer, "icon_url": app.icon_url,
            "installs": app.real_installs, "rating": app.score, "brand_flags": [], "mark": status, "note": note}
        items.append({**game, "pick": {
            "tier": p.tier, "niche": p.niche, "why": p.why, "entry": p.entry, "risks": p.risks, "keys": [with_entry(k) for k in p.keys or []],
            "rivals": [rivals[r] for r in p.rivals or [] if r in rivals],
            "added_at": p.added_at, "updated_at": p.updated_at}})
    return {"items": items, "updated_at": max((p.updated_at for p, *_ in rows), default=None)}
