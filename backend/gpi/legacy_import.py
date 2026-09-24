"""One-off import of the old Streamlit monitor's SQLite database (data/monitor.db).

Takes games only and their install history (installs are global, so the US series is used).
Imported apps come in as stubs; the next `enrich` refreshes their cards.
"""

import sqlite3
from datetime import datetime

from sqlalchemy import select

from gpi.db import session_scope, upsert
from gpi.models import App, Snapshot


def _date(text):
    for fmt in ("%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except (TypeError, ValueError):
            continue
    return None


def import_legacy(path: str) -> dict:
    src = sqlite3.connect(path)
    src.row_factory = sqlite3.Row
    apps = src.execute("SELECT * FROM apps WHERE genre_id LIKE 'GAME%'").fetchall()
    ids = [a["app_id"] for a in apps]
    with session_scope() as s:
        known = set(s.scalars(select(App.app_id).where(App.app_id.in_(ids))).all())
        rows = [{
            "app_id": a["app_id"], "title": a["title"], "developer": a["developer"],
            "developer_id": a["developer_id"], "genre_id": a["genre_id"], "icon_url": a["icon_url"],
            "released": _date(a["released_date"]), "is_game": True, "status": "active", "tracked": False,
            "free": bool(a["free"]), "price": 0, "contains_ads": bool(a["contains_ads"]),
            "offers_iap": bool(a["offers_iap"]), "pre_register": False, "error_count": 0,
            "discovered_via": "legacy", "first_seen": datetime.strptime(a["first_seen_date"], "%Y-%m-%d"),
        } for a in apps if a["app_id"] not in known]
        upsert(s, App, rows, key=["app_id"], update=[])

        snaps = src.execute(
            "SELECT app_id, date, real_installs, ratings_count, reviews_count, score FROM snapshots "
            "WHERE region = 'us' AND app_id IN (SELECT app_id FROM apps WHERE genre_id LIKE 'GAME%')"
        ).fetchall()
        snap_rows = [{"app_id": r["app_id"], "date": _date(r["date"]), "real_installs": r["real_installs"],
                      "ratings": r["ratings_count"], "reviews": r["reviews_count"], "score": r["score"]}
                     for r in snaps]
        upsert(s, Snapshot, snap_rows, key=["app_id", "date"], update=[])
    return {"games": len(rows), "snapshots": len(snap_rows)}
