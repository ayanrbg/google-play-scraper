"""App cards: enrich newly discovered stubs, and daily tracking of young games.

Installs in Google Play are worldwide, so one reading per app per day is enough.
"""

from datetime import date, datetime, timedelta

from sqlalchemy import or_, select, update

from gpi.db import session_scope, upsert
from gpi.models import App, GameMetrics, Snapshot
from gpi.pipeline.common import job_run, log, parallel
from gpi.play import client
from gpi.play.http import NotFound
from gpi.settings import get_settings

APP_FIELDS = [
    "title", "developer", "developer_id", "genre_id", "is_game", "icon_url", "summary",
    "content_rating", "released", "last_updated", "version", "free", "price", "contains_ads",
    "offers_iap", "pre_register", "real_installs", "min_installs", "ratings", "reviews", "score",
]


def should_track(d: dict, today: date) -> bool:
    if not d.get("is_game"):
        return False
    if d.get("pre_register"):
        return True
    released = d.get("released")
    return released is not None and (today - released).days <= get_settings().track_max_age_days


def _fetch(app_id: str):
    try:
        return client.details(app_id)
    except NotFound:
        return "not_found"


def refresh(app_ids: list[str], label: str, set_tracked: bool) -> dict:
    """Fetch cards for app_ids, update apps, write today's snapshot for tracked games."""
    today = date.today()
    now = datetime.utcnow()
    ok = missing = failed = tracked_new = 0
    batch_apps, batch_snaps, gone = [], [], []

    def flush():
        with session_scope() as s:
            for row in batch_apps:
                s.execute(update(App).where(App.app_id == row.pop("app_id_key")).values(**row))
            upsert(s, Snapshot, batch_snaps, key=["app_id", "date"])
            for app_id in gone:
                s.execute(update(App).where(App.app_id == app_id).values(
                    error_count=App.error_count + 1, details_at=now))
                s.execute(update(App).where(App.app_id == app_id, App.error_count >= 3)
                          .values(status="removed", tracked=False))
        batch_apps.clear(); batch_snaps.clear(); gone.clear()

    for app_id, d, err in parallel(_fetch, app_ids, label=label):
        if err is not None:
            failed += 1
            log.debug("details %s failed: %s", app_id, err)
            continue
        if d == "not_found":
            missing += 1
            gone.append(app_id)
            continue
        row = {k: d.get(k) for k in APP_FIELDS}
        row.update(app_id_key=app_id, details_at=now, error_count=0, status="active")
        track = should_track(d, today)
        if set_tracked:
            row["tracked"] = track
            tracked_new += int(track)
        if track and d.get("real_installs") is not None:
            batch_snaps.append({"app_id": app_id, "date": today, "real_installs": d["real_installs"],
                                "ratings": d.get("ratings"), "reviews": d.get("reviews"), "score": d.get("score")})
        batch_apps.append(row)
        ok += 1
        if len(batch_apps) >= 200:
            flush()
    flush()
    return {"ok": ok, "missing": missing, "failed": failed, "tracked": tracked_new}


def enrich():
    """Cards for stubs discovered by charts/similar/developer/keywords."""
    with job_run("enrich") as stats:
        with session_scope() as s:
            ids = s.scalars(select(App.app_id).where(App.details_at.is_(None), App.status == "active")).all()
        stats.update(candidates=len(ids), **refresh(list(ids), "enrich", set_tracked=True))
    return stats


def track():
    """Daily reading for every tracked game (young or pre-registration)."""
    cfg = get_settings()
    today = date.today()
    with job_run("track") as stats:
        with session_scope() as s:
            ids = s.scalars(select(App.app_id).where(
                App.tracked.is_(True), App.status == "active",
                or_(App.details_at.is_(None), App.details_at < datetime.combine(today, datetime.min.time())),
            )).all()
        stats.update(candidates=len(ids), **refresh(list(ids), "track", set_tracked=False))
        stats["untracked"] = untrack_stale(today, cfg.track_max_age_days, cfg.untrack_after_days)
    return stats


def untrack_stale(today: date, max_age: int, idle_days: int) -> int:
    """Stop daily tracking of games that got old, or vanished from charts long ago and stalled."""
    too_old = today - timedelta(days=max_age)
    idle = today - timedelta(days=idle_days)
    with session_scope() as s:
        r1 = s.execute(update(App).where(App.tracked.is_(True), App.pre_register.is_(False),
                                         App.released < too_old).values(tracked=False))
        stalled = select(GameMetrics.app_id).where(GameMetrics.v7 < 50)
        r2 = s.execute(update(App).where(
            App.tracked.is_(True), App.pre_register.is_(False),
            or_(App.last_charted.is_(None), App.last_charted < idle),
            App.first_seen < datetime.combine(idle, datetime.min.time()),
            App.app_id.in_(stalled)).values(tracked=False))
        return (r1.rowcount or 0) + (r2.rowcount or 0)


def add_stubs(ids: list[str], via: str) -> int:
    """Insert unknown app ids as stubs; enrich() fills them in."""
    if not ids:
        return 0
    with session_scope() as s:
        known = set()
        for i in range(0, len(ids), 5000):
            known |= set(s.scalars(select(App.app_id).where(App.app_id.in_(ids[i:i + 5000]))).all())
        new = [{"app_id": a, "discovered_via": via, "is_game": True, "status": "active", "tracked": False,
                "free": True, "price": 0, "contains_ads": False, "offers_iap": False,
                "pre_register": False, "error_count": 0}
               for a in dict.fromkeys(ids) if a not in known]
        upsert(s, App, new, key=["app_id"], update=[])
    return len(new)
