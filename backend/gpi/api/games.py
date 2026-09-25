"""Game radar: filterable list, game card, marks, genre overview, studios to watch."""

import csv
import io
from datetime import date, datetime, timedelta
from statistics import median

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import and_, asc, desc, func, or_, select
from sqlalchemy.orm import Session

from gpi.api.deps import Ctx, current, feature, get_db
from gpi.catalog import GENRE_NAMES_RU
from gpi.models import (
    App, ChartDaily, Developer, GameMetrics, Keyword, KeywordRank, Mark, ScoreHistory, Snapshot,
)
from gpi.pipeline.brand import FLAG_LABELS
from gpi.pipeline.metrics import change_points, interpolate_daily

router = APIRouter(prefix="/api")

SORTS = {
    "trend_score": GameMetrics.trend_score, "v7": GameMetrics.v7, "accel": GameMetrics.accel,
    "installs": GameMetrics.installs, "age_days": GameMetrics.age_days, "released": App.released,
    "rating": App.score, "ratings": App.ratings, "countries": GameMetrics.new_countries + GameMetrics.top_countries,
    "best_rank": GameMetrics.best_rank, "search_visibility": GameMetrics.search_visibility,
    "breadth_delta7": GameMetrics.breadth_delta7, "v_life": GameMetrics.v_life, "title": App.title,
}
FLAG_COLUMNS = {
    "major": GameMetrics.flag_major, "hc_publisher": GameMetrics.flag_hc_publisher,
    "franchise": GameMetrics.flag_franchise, "big_dev": GameMetrics.flag_big_dev,
    "big_portfolio": GameMetrics.flag_big_portfolio,
}


class GameFilters:
    """Query parameters of the radar. Kept in one place so list and CSV export agree."""

    def __init__(
        self,
        q: str | None = None,
        genres: str | None = Query(None, description="comma-separated genre ids"),
        min_age: int | None = None, max_age: int | None = None,
        min_installs: int | None = None, max_installs: int | None = None,
        min_v7: float | None = None, min_accel: float | None = None,
        min_trend: float | None = None, min_rating: float | None = None,
        min_countries: int | None = None, min_search: float | None = None,
        hide_flags: str | None = Query("major,hc_publisher,franchise", description="comma-separated brand flags"),
        max_dev_installs: int | None = None,
        ads: str | None = None, iap: str | None = None,           # yes | no
        prereg: str = "include",                                   # include | only | exclude
        soft_launch: str = "include",                              # include | only | exclude
        charts: str | None = None,                                 # top_new | trending | any
        marks: str = "hide_rejected",                              # all | hide_rejected | interesting | in_work | rejected | unmarked
        sort: str = "trend_score", dir: str = "desc",
        page: int = 1, page_size: int = Query(50, le=200),
    ):
        self.__dict__.update(locals())
        del self.__dict__["self"]


def _split(v: str | None) -> list[str]:
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def build_query(f: GameFilters, ctx: Ctx):
    mark = Mark.__table__.alias("m")
    stmt = (select(App, GameMetrics, mark.c.status.label("mark_status"), mark.c.note.label("mark_note"))
            .join(GameMetrics, GameMetrics.app_id == App.app_id)
            .outerjoin(mark, and_(mark.c.app_id == App.app_id, mark.c.workspace_id == ctx.workspace.id)))
    conds = [App.status == "active"]
    if f.q:
        like = f"%{f.q.lower()}%"
        conds.append(or_(func.lower(App.title).like(like), func.lower(App.developer).like(like), App.app_id.like(like)))
    if genres := _split(f.genres):
        conds.append(App.genre_id.in_(genres))
    if f.min_age is not None:
        conds.append(GameMetrics.age_days >= f.min_age)
    if f.max_age is not None:
        conds.append(or_(GameMetrics.age_days <= f.max_age, GameMetrics.age_days.is_(None)))
    if f.min_installs is not None:
        conds.append(GameMetrics.installs >= f.min_installs)
    if f.max_installs is not None:
        conds.append(GameMetrics.installs <= f.max_installs)
    if f.min_v7 is not None:
        conds.append(GameMetrics.v7 >= f.min_v7)
    if f.min_accel is not None:
        conds.append(GameMetrics.accel >= f.min_accel)
    if f.min_trend is not None:
        conds.append(GameMetrics.trend_score >= f.min_trend)
    if f.min_rating is not None:
        conds.append(App.score >= f.min_rating)
    if f.min_countries is not None:
        conds.append(GameMetrics.new_countries + GameMetrics.top_countries >= f.min_countries)
    if f.min_search is not None:
        conds.append(GameMetrics.search_visibility >= f.min_search)
    for flag in _split(f.hide_flags):
        if flag in FLAG_COLUMNS:
            conds.append(FLAG_COLUMNS[flag].is_(False))
    if f.max_dev_installs is not None:
        conds.append(or_(GameMetrics.dev_max_installs.is_(None), GameMetrics.dev_max_installs <= f.max_dev_installs))
    if f.ads in ("yes", "no"):
        conds.append(App.contains_ads.is_(f.ads == "yes"))
    if f.iap in ("yes", "no"):
        conds.append(App.offers_iap.is_(f.iap == "yes"))
    if f.prereg == "only":
        conds.append(App.pre_register.is_(True))
    elif f.prereg == "exclude":
        conds.append(App.pre_register.is_(False))
    if f.soft_launch == "only":
        conds.append(App.soft_launch.is_(True))
    elif f.soft_launch == "exclude":
        conds.append(or_(App.soft_launch.is_(None), App.soft_launch.is_(False)))
    if f.charts == "top_new":
        conds.append(GameMetrics.new_countries > 0)
    elif f.charts == "trending":
        conds.append(GameMetrics.trending_countries > 0)
    elif f.charts == "any":
        conds.append(GameMetrics.new_countries + GameMetrics.top_countries + GameMetrics.trending_countries > 0)
    status_map = {"interesting": "interesting", "in_work": "in_work", "rejected": "rejected"}
    if f.marks == "hide_rejected":
        conds.append(or_(mark.c.status.is_(None), mark.c.status != "rejected"))
    elif f.marks in status_map:
        conds.append(mark.c.status == status_map[f.marks])
    elif f.marks == "unmarked":
        conds.append(mark.c.status.is_(None))
    stmt = stmt.where(*conds)
    col = SORTS.get(f.sort, GameMetrics.trend_score)
    order = desc(col) if f.dir == "desc" else asc(col)
    stmt = stmt.order_by(order.nulls_last(), App.app_id)
    return stmt


def row_payload(app: App, m: GameMetrics, mark_status, mark_note) -> dict:
    return {
        "app_id": app.app_id, "title": app.title, "developer": app.developer, "developer_id": app.developer_id,
        "icon_url": app.icon_url, "genre_id": app.genre_id, "genre": GENRE_NAMES_RU.get(app.genre_id or "", app.genre_id),
        "released": app.released, "age_days": m.age_days, "pre_register": app.pre_register,
        "soft_launch": bool(app.soft_launch), "soft_launch_markets": app.soft_launch_markets or [],
        "installs": m.installs, "v7": m.v7, "v7_prev": m.v7_prev, "accel": m.accel, "v_life": m.v_life,
        "rating": app.score, "ratings": app.ratings,
        "new_countries": m.new_countries, "top_countries": m.top_countries,
        "trending_countries": m.trending_countries, "grossing_countries": m.grossing_countries,
        "breadth_delta7": m.breadth_delta7, "best_rank": m.best_rank,
        "search_visibility": m.search_visibility, "search_keywords": m.search_keywords,
        "trend_score": m.trend_score, "score_parts": m.score_parts, "brand_flags": m.brand_flags,
        "dev_max_installs": m.dev_max_installs, "dev_app_count": m.dev_app_count,
        "contains_ads": app.contains_ads, "offers_iap": app.offers_iap,
        "spark": m.spark, "data_days": m.data_days,
        "mark": mark_status, "note": mark_note,
    }


@router.get("/games")
def list_games(f: GameFilters = Depends(), ctx: Ctx = Depends(current), db: Session = Depends(get_db)):
    stmt = build_query(f, ctx)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    limit = f.page_size
    max_rows = ctx.plan.get("max_rows")
    offset = (max(f.page, 1) - 1) * limit
    if max_rows is not None:
        limit = max(0, min(limit, max_rows - offset))
    rows = db.execute(stmt.offset(offset).limit(limit)).all() if limit else []
    return {
        "total": total, "page": f.page, "page_size": f.page_size,
        "limited_to": max_rows,
        "items": [row_payload(*r) for r in rows],
    }


@router.get("/games/export.csv")
def export_games(f: GameFilters = Depends(), ctx: Ctx = Depends(feature("export")), db: Session = Depends(get_db)):
    rows = db.execute(build_query(f, ctx).limit(5000)).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    cols = ["app_id", "title", "developer", "genre", "released", "age_days", "installs", "v7", "accel",
            "trend_score", "new_countries", "top_countries", "trending_countries", "search_visibility",
            "rating", "ratings", "brand_flags", "mark", "note"]
    w.writerow(cols + ["url"])
    for r in rows:
        p = row_payload(*r)
        p["brand_flags"] = ",".join(p["brand_flags"] or [])
        w.writerow([p[c] for c in cols] + [f"https://play.google.com/store/apps/details?id={p['app_id']}"])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=games.csv"})


@router.get("/games/{app_id}")
def game_detail(app_id: str, ctx: Ctx = Depends(current), db: Session = Depends(get_db)):
    app = db.get(App, app_id)
    if not app:
        raise HTTPException(404, "not_found")
    m = db.get(GameMetrics, app_id)
    mark = db.get(Mark, (ctx.workspace.id, app_id))

    history_days = ctx.plan.get("history_days")
    since = date.today() - timedelta(days=history_days) if history_days else date(2000, 1, 1)
    snaps = db.execute(select(Snapshot).where(Snapshot.app_id == app_id, Snapshot.date >= since)
                       .order_by(Snapshot.date)).scalars().all()
    pts = change_points([(s.date, s.real_installs) for s in snaps])
    daily = []
    if len(pts) >= 2:
        start = snaps[0].date + timedelta(days=1)
        values = interpolate_daily(pts, start, snaps[-1].date)
        daily = [{"date": start + timedelta(days=i), "installs": v} for i, v in enumerate(values)]

    chart_rows = db.execute(select(ChartDaily).where(ChartDaily.app_id == app_id, ChartDaily.date >= since)
                            .order_by(ChartDaily.date)).scalars().all()
    latest_chart_date = max((c.date for c in chart_rows), default=None)
    charts_latest = {c.collection: {"countries": c.countries, "best_rank": c.best_rank,
                                    "best_country": c.best_country, "best_category": c.best_category}
                     for c in chart_rows if c.date == latest_chart_date}
    chart_history: dict[str, dict] = {}
    for c in chart_rows:
        chart_history.setdefault(str(c.date), {"date": c.date})[c.collection] = c.n_countries

    scores = db.execute(select(ScoreHistory).where(ScoreHistory.app_id == app_id, ScoreHistory.date >= since)
                        .order_by(ScoreHistory.date)).scalars().all()

    dev, dev_apps = None, []
    if app.developer_id:
        d = db.get(Developer, app.developer_id)
        dev = {"developer_id": app.developer_id, "name": app.developer,
               "app_count": d.app_count if d else None, "fetched_at": d.fetched_at if d else None}
        dev_apps = [{"app_id": a.app_id, "title": a.title, "icon_url": a.icon_url, "installs": a.real_installs,
                     "released": a.released, "genre_id": a.genre_id, "tracked": a.tracked}
                    for a in db.scalars(select(App).where(App.developer_id == app.developer_id, App.app_id != app_id,
                                                          App.details_at.is_not(None))
                                        .order_by(App.real_installs.desc().nulls_last()).limit(30))]

    kws = db.execute(select(Keyword, KeywordRank.rank).join(KeywordRank, KeywordRank.keyword_id == Keyword.id)
                     .where(KeywordRank.app_id == app_id).order_by(Keyword.demand.desc()).limit(50)).all()

    return {
        "app": {
            "app_id": app.app_id, "title": app.title, "developer": app.developer, "icon_url": app.icon_url,
            "summary": app.summary, "genre_id": app.genre_id,
            "genre": GENRE_NAMES_RU.get(app.genre_id or "", app.genre_id), "released": app.released,
            "last_updated": app.last_updated, "version": app.version, "content_rating": app.content_rating,
            "free": app.free, "price": app.price, "contains_ads": app.contains_ads, "offers_iap": app.offers_iap,
            "pre_register": app.pre_register, "installs": app.real_installs, "min_installs": app.min_installs,
            "soft_launch": bool(app.soft_launch), "soft_launch_markets": app.soft_launch_markets or [],
            "ratings": app.ratings, "reviews": app.reviews, "rating": app.score, "tracked": app.tracked,
            "first_seen": app.first_seen, "discovered_via": app.discovered_via,
            "url": f"https://play.google.com/store/apps/details?id={app.app_id}",
        },
        "metrics": row_payload(app, m, mark.status if mark else None, mark.note if mark else None) if m else None,
        "snapshots": [{"date": s.date, "installs": s.real_installs, "ratings": s.ratings, "rating": s.score} for s in snaps],
        "daily": daily,
        "charts_latest": charts_latest, "charts_date": latest_chart_date,
        "chart_history": list(chart_history.values()),
        "score_history": [{"date": s.date, "trend_score": s.trend_score, "v7": s.v7} for s in scores],
        "developer": dev, "developer_apps": dev_apps,
        "keywords": [{"id": k.id, "term": k.term, "demand": k.demand, "opportunity": k.opportunity,
                      "competition": k.competition, "rank": rank} for k, rank in kws],
        "mark": {"status": mark.status, "note": mark.note, "updated_at": mark.updated_at} if mark else None,
        "flag_labels": FLAG_LABELS,
    }


class MarkIn(BaseModel):
    status: str | None = None    # interesting | in_work | rejected | None
    note: str | None = None


@router.put("/games/{app_id}/mark")
def set_mark(app_id: str, body: MarkIn, ctx: Ctx = Depends(current), db: Session = Depends(get_db)):
    if body.status not in (None, "interesting", "in_work", "rejected"):
        raise HTTPException(400, "bad_status")
    m = db.get(Mark, (ctx.workspace.id, app_id))
    if body.status is None and not body.note:
        if m:
            db.delete(m)
        return {"ok": True}
    if not m:
        m = Mark(workspace_id=ctx.workspace.id, app_id=app_id)
        db.add(m)
    m.status, m.note, m.user_id, m.updated_at = body.status, body.note, ctx.user.id, datetime.utcnow()
    return {"ok": True}


# ----------------------------- overviews -----------------------------

@router.get("/genres")
def genres(max_age: int = 180, ctx: Ctx = Depends(current), db: Session = Depends(get_db)):
    """Where young non-brand games are winning right now, per genre."""
    rows = db.execute(
        select(App.genre_id, GameMetrics.v7, GameMetrics.trend_score, GameMetrics.flag_major,
               GameMetrics.flag_franchise, GameMetrics.flag_hc_publisher)
        .join(GameMetrics, GameMetrics.app_id == App.app_id)
        .where(App.genre_id.is_not(None), or_(GameMetrics.age_days <= max_age, GameMetrics.age_days.is_(None)))
    ).all()
    by: dict[str, dict] = {}
    for g, v7, ts, major, fr, hc in rows:
        b = by.setdefault(g, {"genre_id": g, "genre": GENRE_NAMES_RU.get(g, g), "games": 0, "indie": 0,
                              "hot": 0, "v7_sum": 0.0, "indie_v7": []})
        b["games"] += 1
        b["v7_sum"] += v7 or 0
        if not (major or fr or hc):
            b["indie"] += 1
            b["indie_v7"].append(v7 or 0)
            if ts >= 50:
                b["hot"] += 1
    out = []
    for b in by.values():
        iv = b.pop("indie_v7")
        b["indie_v7_median"] = median(iv) if iv else 0
        b["indie_v7_sum"] = sum(iv)
        b["indie_share"] = b["indie"] / b["games"] if b["games"] else 0
        out.append(b)
    return sorted(out, key=lambda b: b["indie_v7_sum"], reverse=True)


@router.get("/studios")
def studios(min_trend: float = 40, ctx: Ctx = Depends(current), db: Session = Depends(get_db)):
    """Small studios with several fresh games gaining traction: whom to watch and learn from."""
    rows = db.execute(
        select(App.developer_id, App.developer, App.app_id, App.title, App.icon_url, GameMetrics.trend_score,
               GameMetrics.v7, GameMetrics.installs, GameMetrics.flag_major, GameMetrics.flag_franchise,
               GameMetrics.flag_hc_publisher, GameMetrics.flag_big_dev)
        .join(GameMetrics, GameMetrics.app_id == App.app_id)
        .where(App.developer_id.is_not(None))
    ).all()
    by: dict[str, dict] = {}
    for r in rows:
        b = by.setdefault(r.developer_id, {"developer_id": r.developer_id, "developer": r.developer, "games": [],
                                           "brand": False})
        b["brand"] = b["brand"] or bool(r.flag_major or r.flag_franchise or r.flag_hc_publisher)
        b["games"].append({"app_id": r.app_id, "title": r.title, "icon_url": r.icon_url, "trend_score": r.trend_score,
                           "v7": r.v7, "installs": r.installs, "big_dev": r.flag_big_dev})
    out = []
    for b in by.values():
        hot = [g for g in b["games"] if g["trend_score"] >= min_trend]
        if b["brand"] or not hot:
            continue
        b["games"].sort(key=lambda g: g["trend_score"], reverse=True)
        b["hot_games"] = len(hot)
        b["v7_sum"] = sum(g["v7"] or 0 for g in b["games"])
        b["best_trend"] = b["games"][0]["trend_score"]
        out.append(b)
    out.sort(key=lambda b: (b["hot_games"], b["v7_sum"]), reverse=True)
    return out[:200]


@router.get("/meta")
def meta(ctx: Ctx = Depends(current)):
    return {"genres": GENRE_NAMES_RU, "flags": FLAG_LABELS}
