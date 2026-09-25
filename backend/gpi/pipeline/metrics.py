"""Daily metrics and Trend Score for tracked games.

Google Play refreshes the install counter with a lag and in steps: a value often
stays flat for 1-3 days and then jumps. Taken literally that gives "0 installs"
days followed by fake spikes. We therefore:
  * compress the series to change points (the first day each new value appeared),
  * measure velocity between change points spanning the window,
  * linearly interpolate between change points for the daily sparkline.
"""

import math
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import delete, func, select

from gpi.db import session_scope, upsert
from gpi.models import App, ChartDaily, Developer, GameMetrics, Keyword, KeywordRank, ScoreHistory, Snapshot
from gpi.pipeline import brand
from gpi.pipeline.common import job_run

HISTORY_DAYS = 45
SPARK_DAYS = 30

# "Hidden gem": what manual browsing of the stores and big charts would not surface
GEM_MAX_AGE = 90
GEM_MIN_VELOCITY = 1000        # installs/day
GEM_MIN_INSTALLS = 50_000
GEM_MAX_CHART_COUNTRIES = 5    # charts in at most this many of our 60 countries...
GEM_MIN_BEST_RANK = 30         # ...and never high: best position below #30
BRAND = {"major", "hc_publisher", "franchise"}


def is_hidden_gem(age, v, installs, flags, chart_countries, best_any_rank, revival) -> bool:
    if revival or age is None or age > GEM_MAX_AGE or set(flags) & BRAND:
        return False
    if (v or 0) < GEM_MIN_VELOCITY or (installs or 0) < GEM_MIN_INSTALLS:
        return False
    return chart_countries <= GEM_MAX_CHART_COUNTRIES and (best_any_rank is None or best_any_rank > GEM_MIN_BEST_RANK)


# ----------------------------- series math -----------------------------

def change_points(series: list[tuple[date, int]]) -> list[tuple[date, int]]:
    """Keep the first day of every distinct value; drop decreases (Google noise)."""
    out: list[tuple[date, int]] = []
    for d, v in series:
        if v is None:
            continue
        if not out or v > out[-1][1]:
            out.append((d, v))
    return out


def velocity(points: list[tuple[date, int]], end: date, window: int) -> float | None:
    """Average per-day growth over ~window days ending at `end`, using change points."""
    pts = [p for p in points if p[0] <= end]
    if len(pts) < 2:
        return None
    last = pts[-1]
    start_target = end - timedelta(days=window)
    # Latest change point at or before the window start; else the earliest we have.
    before = [p for p in pts if p[0] <= start_target]
    first = before[-1] if before else pts[0]
    if first[0] >= last[0]:
        return None
    days = (last[0] - first[0]).days
    # A window measured on less than half its length is too noisy to report.
    if days < max(2, window // 2):
        return None
    return (last[1] - first[1]) / days


def interpolate_daily(points: list[tuple[date, int]], start: date, end: date) -> list[int | None]:
    """Daily increments between start..end, spreading each jump over the flat days before it."""
    if len(points) < 2:
        return []
    values: dict[date, float] = {}
    for (d0, v0), (d1, v1) in zip(points, points[1:]):
        span = (d1 - d0).days
        for i in range(span):
            values[d0 + timedelta(days=i)] = v0 + (v1 - v0) * i / span
    values[points[-1][0]] = points[-1][1]
    # None = unknown: before our first reading, or after the last counter update
    # (Google has not refreshed the number yet - not a real drop to zero).
    out: list[int | None] = []
    d = start
    while d <= end:
        cur, prev = values.get(d), values.get(d - timedelta(days=1))
        out.append(int(round(cur - prev)) if cur is not None and prev is not None and d <= points[-1][0] else None)
        d += timedelta(days=1)
    return out


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def trend_score(age_days, v7, accel, new_c, top_c, trending_c, score, ratings) -> tuple[float, dict]:
    parts = {}
    parts["growth"] = 40 * clamp(math.log10((v7 or 0) + 1) / 5)          # 100k/day -> 40
    parts["accel"] = 15 * clamp(math.log2(accel) / 2) if accel and accel > 1 else 0.0  # x4 -> 15
    if age_days is None:
        parts["youth"] = 0.0
    else:
        parts["youth"] = next((pts for limit, pts in [(14, 15), (30, 12), (60, 9), (90, 6), (180, 3)]
                               if age_days <= limit), 0.0)
    parts["charts"] = 15 * clamp((new_c + top_c) / 20) + 5 * clamp(trending_c / 5)
    parts["quality"] = 10 * clamp(((score or 0) - 3.8) / 1.0) if (ratings or 0) >= 30 else 0.0
    parts = {k: round(v, 1) for k, v in parts.items()}
    return round(min(100.0, sum(parts.values())), 1), parts


def rank_weight(rank: int) -> float:
    return max(0.0, (21 - rank) / 20)


# ----------------------------- job -----------------------------

def run(today: date | None = None):
    today = today or date.today()
    since = today - timedelta(days=HISTORY_DAYS)
    with job_run("metrics") as stats, session_scope() as s:
        apps = s.execute(select(App).where(App.tracked.is_(True), App.status == "active")).scalars().all()
        ids = [a.app_id for a in apps]

        snaps: dict[str, list] = defaultdict(list)
        for row in s.execute(select(Snapshot.app_id, Snapshot.date, Snapshot.real_installs, Snapshot.ratings)
                             .where(Snapshot.date >= since).order_by(Snapshot.date)):
            snaps[row.app_id].append(row)

        chart_date = s.scalar(select(func.max(ChartDaily.date)))
        charts_now: dict[str, dict[str, int]] = defaultdict(dict)
        charts_before: dict[str, int] = defaultdict(int)
        best_rank: dict[str, int] = {}
        best_any: dict[str, int] = {}                     # best position in any chart
        chart_ccs: dict[str, set] = defaultdict(set)      # countries across all charts
        if chart_date:
            for r in s.execute(select(ChartDaily).where(ChartDaily.date == chart_date)).scalars():
                charts_now[r.app_id][r.collection] = r.n_countries
                chart_ccs[r.app_id].update((r.countries or {}).keys())
                if r.best_rank:
                    best_any[r.app_id] = min(best_any.get(r.app_id, 10**6), r.best_rank)
                if r.collection in ("top_free", "top_new_free") and r.best_rank:
                    best_rank[r.app_id] = min(best_rank.get(r.app_id, 10**6), r.best_rank)
            week_ago = s.scalar(select(func.max(ChartDaily.date)).where(ChartDaily.date <= chart_date - timedelta(days=7)))
            if week_ago:
                for r in s.execute(select(ChartDaily.app_id, ChartDaily.n_countries).where(
                        ChartDaily.date == week_ago, ChartDaily.collection.in_(["top_free", "top_new_free"]))):
                    charts_before[r.app_id] += r.n_countries

        # Search visibility from keyword ranks
        visibility: dict[str, float] = defaultdict(float)
        kw_count: dict[str, int] = defaultdict(int)
        for r in s.execute(select(KeywordRank.app_id, KeywordRank.rank, Keyword.demand)
                           .join(Keyword, Keyword.id == KeywordRank.keyword_id)):
            visibility[r.app_id] += (r.demand or 0) * rank_weight(r.rank)
            if r.rank <= 10 and (r.demand or 0) >= 20:
                kw_count[r.app_id] += 1

        # Developer portfolio: best installs among the developer's *other* known apps
        dev_ids = {a.developer_id for a in apps if a.developer_id}
        devs = {d.developer_id: d for d in s.execute(select(Developer).where(Developer.developer_id.in_(dev_ids))).scalars()} if dev_ids else {}
        dev_top: dict[str, list[tuple[int, str]]] = defaultdict(list)
        if dev_ids:
            for r in s.execute(select(App.developer_id, App.app_id, App.real_installs)
                               .where(App.developer_id.in_(dev_ids), App.real_installs.is_not(None))):
                dev_top[r.developer_id].append((r.real_installs, r.app_id))
        rules = brand.Rules.load(s)

        metrics_rows, history_rows = [], []
        for a in apps:
            pts = change_points([(r.date, r.real_installs) for r in snaps.get(a.app_id, [])])
            rpts = change_points([(r.date, r.ratings) for r in snaps.get(a.app_id, [])])
            v7 = velocity(pts, today, 7)
            v7_prev = velocity(pts, today - timedelta(days=7), 7)
            accel = (v7 / v7_prev) if (v7 is not None and v7_prev and v7_prev > 0) else None
            age = (today - a.released).days if a.released else None
            installs = a.real_installs
            revival = a.track_reason == "revival"
            v_life = (installs / max(age, 1)) if (installs is not None and age is not None and not a.pre_register) else None
            # Not enough history for a 7-day window yet (just discovered): use lifetime average -
            # except after a soft launch (installs predate the global release date) and for old
            # revived games (years of installs say nothing about the current surge).
            v_eff = v7 if v7 is not None else (None if (a.soft_launch or revival) else v_life)

            cn = charts_now.get(a.app_id, {})
            new_c, top_c = cn.get("top_new_free", 0), cn.get("top_free", 0)
            trending_c, gross_c = cn.get("trending", 0), cn.get("top_grossing", 0)

            others = sorted((v for v in dev_top.get(a.developer_id, []) if v[1] != a.app_id), reverse=True)
            dev = devs.get(a.developer_id)
            dev_other_max = others[0][0] if others else None
            dev_count = dev.app_count if dev else None
            flags = brand.classify(a.title, a.developer, a.developer_id, dev_other_max, dev_count, rules)

            total, parts = trend_score(age, v_eff, accel, new_c, top_c, trending_c, a.score, a.ratings)
            parts["estimated"] = v7 is None and v_eff is not None
            vis = visibility.get(a.app_id, 0.0)
            spark = interpolate_daily(pts, today - timedelta(days=SPARK_DAYS - 1), today) if len(pts) >= 2 else []

            n_chart_cc = len(chart_ccs.get(a.app_id, ()))
            gem = is_hidden_gem(age, v_eff, installs, flags, n_chart_cc, best_any.get(a.app_id), revival)

            metrics_rows.append({
                "app_id": a.app_id, "computed_at": datetime.utcnow(), "age_days": age, "installs": installs,
                "revival": revival, "hidden_gem": gem, "chart_countries_any": n_chart_cc,
                "v7": v_eff, "v7_prev": v7_prev, "accel": accel, "v_life": v_life,
                "ratings_v7": velocity(rpts, today, 7),
                "new_countries": new_c, "top_countries": top_c, "trending_countries": trending_c,
                "grossing_countries": gross_c, "breadth_delta7": (new_c + top_c) - charts_before.get(a.app_id, 0),
                "best_rank": best_rank.get(a.app_id),
                "search_visibility": round(100 * (1 - math.exp(-vis / 150)), 1),
                "search_keywords": kw_count.get(a.app_id, 0),
                "brand_flags": flags, "dev_max_installs": dev_other_max, "dev_app_count": dev_count,
                **{f"flag_{f}": f in flags for f in brand.FLAG_LABELS},
                "trend_score": total, "score_parts": parts, "spark": spark,
                "data_days": len(snaps.get(a.app_id, [])),
            })
            history_rows.append({"app_id": a.app_id, "date": today, "trend_score": total, "v7": v_eff})

        upsert(s, GameMetrics, metrics_rows, key=["app_id"])
        upsert(s, ScoreHistory, history_rows, key=["app_id", "date"])
        # Drop metrics of games no longer tracked so the radar only shows live candidates.
        if ids:
            s.execute(delete(GameMetrics).where(GameMetrics.app_id.not_in(select(App.app_id).where(App.tracked.is_(True)))))
        stats.update(games=len(metrics_rows), chart_date=str(chart_date) if chart_date else None)
    return stats
