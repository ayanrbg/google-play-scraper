"""Grow the candidate pool beyond charts:

- similar games of today's strongest non-brand candidates (snowball around a hit),
- developer portfolios (brand signal + fresh releases/pre-registrations of proven studios),
- Google Play's pre-registration collection.
"""

from datetime import datetime, timedelta

from sqlalchemy import func, or_, select, update

from gpi.catalog import COUNTRIES
from gpi.db import session_scope, upsert
from gpi.models import App, Developer, GameMetrics
from gpi.pipeline.common import job_run, log, parallel
from gpi.pipeline.details import add_stubs
from gpi.play import client
from gpi.play.http import NotFound
from gpi.settings import get_settings

BRAND_FLAGS = {"major", "hc_publisher", "franchise"}
DEV_PAGE_LIMIT = 60


def expand_similar(limit: int) -> dict:
    cutoff = datetime.utcnow() - timedelta(days=7)
    with session_scope() as s:
        rows = s.execute(
            select(GameMetrics.app_id, GameMetrics.brand_flags)
            .join(App, App.app_id == GameMetrics.app_id)
            .where(or_(App.similar_at.is_(None), App.similar_at < cutoff))
            .order_by(GameMetrics.trend_score.desc()).limit(limit * 3)
        ).all()
    seeds = [r.app_id for r in rows if not (set(r.brand_flags or []) & BRAND_FLAGS)][:limit]
    found: list[str] = []
    done: list[str] = []
    for app_id, ids, err in parallel(client.similar_ids, seeds, label="similar"):
        if err and not isinstance(err, NotFound):
            continue
        found += ids or []
        done.append(app_id)
    with session_scope() as s:
        if done:
            s.execute(update(App).where(App.app_id.in_(done)).values(similar_at=datetime.utcnow()))
    return {"seeds": len(seeds), "found": len(set(found)), "new": add_stubs(found, "similar")}


def expand_developers() -> dict:
    """Refresh developer pages for studios of tracked games."""
    cfg = get_settings()
    stale = datetime.utcnow() - timedelta(days=cfg.developer_refresh_days)
    with session_scope() as s:
        dev_rows = s.execute(
            select(App.developer_id, func.max(App.developer))
            .where(App.tracked.is_(True), App.developer_id.is_not(None))
            .group_by(App.developer_id)
        ).all()
        fresh = set(s.scalars(select(Developer.developer_id).where(Developer.fetched_at >= stale)).all())
    todo = {d: name for d, name in dev_rows if d not in fresh}

    found: list[str] = []
    rows = []
    for dev_id, ids, err in parallel(client.developer_ids, list(todo), label="developers"):
        if err and not isinstance(err, NotFound):
            continue
        ids = ids or []
        found += ids[:DEV_PAGE_LIMIT]
        rows.append({"developer_id": dev_id, "name": todo[dev_id], "app_ids": ids,
                     "app_count": len(ids), "fetched_at": datetime.utcnow()})
    with session_scope() as s:
        upsert(s, Developer, rows, key=["developer_id"])
    new = add_stubs(found, "developer")
    refresh_developer_stats()
    return {"developers": len(rows), "new": new}


def refresh_developer_stats():
    with session_scope() as s:
        stats = s.execute(
            select(App.developer_id, func.max(App.real_installs), func.sum(App.real_installs))
            .where(App.developer_id.is_not(None)).group_by(App.developer_id)
        ).all()
        known = set(s.scalars(select(Developer.developer_id)).all())
        for dev_id, mx, total in stats:
            if dev_id in known:
                s.execute(update(Developer).where(Developer.developer_id == dev_id)
                          .values(max_installs=mx, total_installs=total))


def expand_prereg() -> dict:
    ids: list[str] = []
    for country in COUNTRIES[:12]:
        try:
            ids += client.prereg_collection_ids(country)
        except Exception as e:
            log.warning("prereg %s: %s", country, e)
    return {"found": len(set(ids)), "new": add_stubs(ids, "prereg")}


def run():
    cfg = get_settings()
    with job_run("expand") as stats:
        stats["prereg"] = expand_prereg()
        stats["similar"] = expand_similar(cfg.similar_expand_top)
        stats["developers"] = expand_developers()
    return stats
