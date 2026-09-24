"""Daily scan of real top charts in every country and game category."""

import itertools
from datetime import date

from sqlalchemy import select, update

from gpi.catalog import CHART_SIZE, COLLECTIONS, COUNTRIES, GAME_CATEGORIES
from gpi.db import session_scope, upsert
from gpi.models import App, ChartDaily
from gpi.pipeline.common import job_run, log, parallel
from gpi.play import client


def aggregate(results: list[tuple[str, str, str, list[dict]]]) -> tuple[dict, dict]:
    """(collection, category, country, entries) -> per (app, collection) aggregate + app stubs."""
    agg: dict[tuple[str, str], dict] = {}
    stubs: dict[str, dict] = {}
    for collection, category, country, entries in results:
        for e in entries:
            key = (e["app_id"], collection)
            a = agg.setdefault(key, {"countries": {}, "best_rank": None, "best_country": None, "best_category": None})
            prev = a["countries"].get(country)
            if prev is None or e["rank"] < prev:
                a["countries"][country] = e["rank"]
            # Overall GAME chart outranks a sub-genre chart at equal rank.
            better = (a["best_rank"] is None or e["rank"] < a["best_rank"]
                      or (e["rank"] == a["best_rank"] and category == "GAME"))
            if better:
                a.update(best_rank=e["rank"], best_country=country, best_category=category)
            stubs.setdefault(e["app_id"], {"title": e["title"], "developer": e["developer"],
                                           "via": f"chart:{collection}"})
    return agg, stubs


def run(countries: list[str] | None = None, categories: list[str] | None = None,
        collections: dict[str, str] | None = None):
    countries = countries or COUNTRIES
    categories = categories or GAME_CATEGORIES
    collections = collections or COLLECTIONS
    today = date.today()

    with job_run("charts") as stats:
        tasks = list(itertools.product(collections.items(), categories, countries))
        results, failed = [], 0
        fetch = lambda t: client.charts(t[0][1], t[1], t[2], CHART_SIZE)
        for (coll, category, country), entries, err in parallel(fetch, tasks, label="charts"):
            if err:
                failed += 1
                log.warning("chart %s/%s/%s failed: %s", coll[0], category, country, err)
                continue
            results.append((coll[0], category, country, entries))

        agg, stubs = aggregate(results)
        rows = [{
            "app_id": app_id, "date": today, "collection": coll,
            "n_countries": len(a["countries"]), "best_rank": a["best_rank"],
            "best_country": a["best_country"], "best_category": a["best_category"],
            "countries": a["countries"],
        } for (app_id, coll), a in agg.items()]

        with session_scope() as s:
            known = set(s.scalars(select(App.app_id).where(App.app_id.in_(list(stubs)))).all()) if stubs else set()
            new = [{"app_id": aid, "title": st["title"], "developer": st["developer"],
                    "discovered_via": st["via"], "is_game": True, "status": "active", "tracked": False,
                    "free": True, "price": 0, "contains_ads": False, "offers_iap": False,
                    "pre_register": False, "error_count": 0}
                   for aid, st in stubs.items() if aid not in known]
            upsert(s, App, new, key=["app_id"], update=[])
            upsert(s, ChartDaily, rows, key=["app_id", "date", "collection"])
            ids = list(stubs)
            for i in range(0, len(ids), 5000):
                s.execute(update(App).where(App.app_id.in_(ids[i:i + 5000])).values(last_charted=today))

        stats.update(requests=len(tasks), failed=failed, charted_apps=len(stubs),
                     new_apps=len(new), rows=len(rows))
        if tasks and failed > len(tasks) * 0.5:
            raise RuntimeError(f"{failed}/{len(tasks)} chart requests failed - blocked by Google?")
    return stats
