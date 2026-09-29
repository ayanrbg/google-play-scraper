"""How each game was found: the first time every channel (a chart, "similar games", a studio page,
the pre-registration collection, a search result) surfaced it. Shown as a timeline on the game page.
"""

from datetime import date

from sqlalchemy import and_, func, select

from playtrend.db import session_scope, upsert
from playtrend.models import App, ChartDaily, DiscoveryEvent


def record(session, events: list[dict]):
    """Insert events; a channel that already surfaced the game keeps its first date."""
    rows = [{"app_id": e["app_id"], "source": e["source"], "date": e.get("date") or date.today(),
             "detail": e.get("detail") or {}, "first": bool(e.get("first"))} for e in events]
    upsert(session, DiscoveryEvent, rows, key=["app_id", "source"], update=[])


def chart_events(agg: dict, new_apps: dict[str, str], today: date) -> list[dict]:
    """agg from charts.aggregate(); new_apps maps app_id -> the chart it was found in."""
    return [{"app_id": app_id, "source": f"chart:{coll}", "date": today,
             "first": new_apps.get(app_id) == f"chart:{coll}",
             "detail": {"country": a["best_country"], "rank": a["best_rank"], "category": a["best_category"],
                        "countries": len(a["countries"])}}
            for (app_id, coll), a in agg.items()]


def backfill() -> int:
    """One-time fill for games found before events existed: the channel that brought each game in,
    and the first day in every chart we still have history for."""
    with session_scope() as s:
        if s.scalar(select(DiscoveryEvent.app_id).limit(1)):
            return 0
        first_day = select(ChartDaily.app_id, ChartDaily.collection, func.min(ChartDaily.date).label("d")) \
            .group_by(ChartDaily.app_id, ChartDaily.collection).subquery()
        charts = s.execute(select(ChartDaily).join(first_day, and_(
            ChartDaily.app_id == first_day.c.app_id, ChartDaily.collection == first_day.c.collection,
            ChartDaily.date == first_day.c.d))).scalars().all()
        apps = {a.app_id: a for a in s.execute(select(App.app_id, App.discovered_via, App.first_seen)).all()}
        events = []
        for c in charts:
            if c.app_id not in apps:
                continue
            events.append({"app_id": c.app_id, "source": f"chart:{c.collection}", "date": c.date,
                           "first": apps[c.app_id].discovered_via == f"chart:{c.collection}",
                           "detail": {"country": c.best_country, "rank": c.best_rank,
                                      "category": c.best_category, "countries": c.n_countries}})
        charted = {(e["app_id"], e["source"]) for e in events}
        for a in apps.values():
            if a.discovered_via and (a.app_id, a.discovered_via) not in charted:
                events.append({"app_id": a.app_id, "source": a.discovered_via, "first": True,
                               "date": a.first_seen.date() if a.first_seen else date.today()})
        for i in range(0, len(events), 5000):
            record(s, events[i:i + 5000])
        return len(events)
