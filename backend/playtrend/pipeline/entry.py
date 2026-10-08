"""Can a new game still get into a search query's top 10?

Looked at from the query side: who holds the top-10 places and whether a newcomer could take
one of them. A place is takeable when it is held by a game a decent new release can match - a
fresh game (proof Google lets newcomers in right now), a young game that got there with few
installs, a small or poorly rated game, or an abandoned one. Brands' places never count.

Also how fast the newcomers in the top grow (a top full of stalled young games has room but
little traffic) and, once search results have history, how many games entered the top 10
during the last week.

Reads the database only, so the web API can use the slot classification too.
"""

from datetime import date, timedelta
from statistics import median

from sqlalchemy import select

from playtrend.models import App, GameMetrics, Keyword, KeywordSerp
from playtrend.pipeline import brand

TOP_N = 10
FRESH_DAYS = 90             # in the top this young: Google lets newcomers in right now
YOUNG_DAYS = 365
SMALL_YOUNG = 1_000_000     # a young game that made the top with fewer installs leaves its place takeable
WEAK_INSTALLS = 100_000
WEAK_RATING = 3.8
STALE_DAYS = 365            # no update for a year
GROWING_V7 = 500            # installs/day of a newcomer that counts as growing
CHURN_DAYS = 6              # results this much older are compared to see who entered the top


def slot(app: App | None, m: GameMetrics | None, branded: bool, today: date) -> dict:
    """What holds one top-10 place, and whether a new game could take it."""
    if app is None or app.details_at is None:     # card not fetched yet: age and size unknown
        return {"kind": "unknown", "takeable": False}
    age = (today - app.released).days if app.released else None
    installs = app.real_installs or app.min_installs or 0
    reasons = []
    if branded:
        return {"kind": "brand", "takeable": False, "age": age}
    if age is not None and age <= FRESH_DAYS:
        reasons.append("fresh")
    elif age is not None and age <= YOUNG_DAYS and installs < SMALL_YOUNG:
        reasons.append("young_small")
    if installs < WEAK_INSTALLS:
        reasons.append("small")
    if app.score and app.ratings and app.ratings >= 50 and app.score < WEAK_RATING:
        reasons.append("low_rating")
    if app.last_updated and (today - app.last_updated).days > STALE_DAYS and installs < 10_000_000:
        reasons.append("abandoned")
    return {"kind": reasons[0] if reasons else "strong", "takeable": bool(reasons), "reasons": reasons, "age": age,
            "v7": m.v7 if m else None}


def branded_ids(s, apps: dict[str, App], metrics: dict[str, GameMetrics], rules: brand.Rules) -> set[str]:
    out = set()
    for a in apps.values():
        m = metrics.get(a.app_id)
        flags = set(m.brand_flags or []) if m else set(brand.classify(a.title, a.developer, a.developer_id, None, None, rules))
        if flags & {"major", "hc_publisher", "franchise"}:
            out.add(a.app_id)
    return out


def measure(top: list[str], apps: dict, metrics: dict, branded: set, today: date) -> dict:
    slots = [slot(apps.get(t), metrics.get(t), t in branded, today) for t in top[:TOP_N]]
    if not slots:
        return {}
    known = [x for x in slots if x["kind"] != "unknown"]
    takeable = [i + 1 for i, x in enumerate(slots) if x["takeable"]]
    young = [x for x in known if x.get("age") is not None and x["age"] <= YOUNG_DAYS and x["kind"] != "brand"]
    speeds = [x["v7"] for x in young if x.get("v7")]
    fresh = sum(1 for x in known if "fresh" in x.get("reasons", []))
    growing = sum(1 for v in speeds if v >= GROWING_V7)
    room = len(takeable)
    best = takeable[0] if takeable else None
    # 0-100: how many places are takeable and how high, plus proof that newcomers get in and get traffic
    score = (40 * room / TOP_N + (20 * (TOP_N + 1 - best) / TOP_N if best else 0)
             + 20 * min(fresh, 3) / 3 + 20 * min(growing, 3) / 3)
    if len(known) < TOP_N // 2:      # most of the top unknown yet: no verdict
        score = None
    return {"fresh_count": fresh, "entrants_growing": growing, "entrants_v7": round(median(speeds)) if speeds else None,
            "room": room, "room_best": best, "entry_score": round(score, 1) if score is not None else None}


def churn(s, keyword_ids: list[int], today: date) -> dict[int, int]:
    """Games now in the top 10 that were not there a week ago (needs results history)."""
    rows = s.execute(select(KeywordSerp).where(KeywordSerp.keyword_id.in_(keyword_ids))
                     .order_by(KeywordSerp.keyword_id, KeywordSerp.date)).scalars().all()
    by_kw: dict[int, list[KeywordSerp]] = {}
    for r in rows:
        by_kw.setdefault(r.keyword_id, []).append(r)
    out = {}
    for kw, serps in by_kw.items():
        last = serps[-1]
        old = [x for x in serps if x.date <= last.date - timedelta(days=CHURN_DAYS)]
        if old:
            out[kw] = len(set(last.apps[:TOP_N]) - set(old[-1].apps[:TOP_N]))
    return out


def update_keywords(s, keyword_ids: list[int] | None = None, today: date | None = None) -> int:
    """Recompute entry metrics of the given analyzed keywords (all of them when None)."""
    today = today or date.today()
    q = select(Keyword).where(Keyword.analyzed_at.is_not(None))
    if keyword_ids is not None:
        q = q.where(Keyword.id.in_(keyword_ids))
    rules = brand.Rules.load(s)
    n = 0
    kws = s.scalars(q).all()
    for i in range(0, len(kws), 500):
        chunk = kws[i:i + 500]
        ids = list({t for k in chunk for t in (k.top_apps or [])[:TOP_N]})
        apps = {a.app_id: a for a in s.scalars(select(App).where(App.app_id.in_(ids)))} if ids else {}
        metrics = {m.app_id: m for m in s.scalars(select(GameMetrics).where(GameMetrics.app_id.in_(ids)))} if ids else {}
        branded = branded_ids(s, apps, metrics, rules)
        moved = churn(s, [k.id for k in chunk], today)
        for k in chunk:
            m = measure(k.top_apps or [], apps, metrics, branded, today)
            for field in ("fresh_count", "entrants_growing", "entrants_v7", "room", "room_best", "entry_score"):
                setattr(k, field, m.get(field))
            k.churn7 = moved.get(k.id)
            n += 1
    return n


def run():
    from playtrend.db import session_scope
    from playtrend.pipeline.common import job_run
    with job_run("entry") as stats:
        with session_scope() as s:
            stats["keywords"] = update_keywords(s)
    return stats
