"""Search-demand niches (organic via search).

Demand comes from Google Play autocomplete: a query that Google suggests after only
a few typed letters is searched a lot. Competition comes from the actual search
results: how big the top apps are, how many belong to brands, and - most important
for us - whether young games manage to rank there (proof a newcomer can get traffic).
"""

import math
import re
import string
from datetime import date, datetime
from statistics import median

from sqlalchemy import delete, select

from gpi.db import session_scope, upsert
from gpi.models import App, GameMetrics, Keyword, KeywordRank, SeedState
from gpi.pipeline import brand
from gpi.pipeline.common import job_run, log, parallel
from gpi.pipeline.details import add_stubs, refresh
from gpi.pipeline.keyword_markets import MARKETS, Market
from gpi.play import client
from gpi.settings import get_settings

STOPWORDS = {"the", "and", "for", "with", "game", "games", "free", "new", "best", "super", "mega",
             "puzzle", "master", "world", "legend", "legends", "story", "saga", "online", "offline",
             "pro", "hd", "lite", "fun", "adventure", "simulator", "idle", "tycoon", "3d", "2d"}
YOUNG_DAYS = 365
TOP_N = 10


# ----------------------------- demand -----------------------------

def demand_from_observation(query: str, term: str, position: int) -> float:
    """Score one autocomplete observation (term suggested at `position` for `query`)."""
    decay = 1 - 0.08 * (position - 1)
    if term.strip().lower() == query.strip().lower():
        return 15 * decay  # Google echoing the query = it is a real query, nothing more
    p = min(1.0, len(query) / max(len(term), 1))
    return (15 + 85 * (1 - p) ** 0.8) * decay


def seed_queries(seed: str, suffixes: list[str] | None = None) -> list[str]:
    suffixes = suffixes if suffixes is not None else list(string.ascii_lowercase)
    prefixes = [seed[:k] for k in range(2, len(seed)) if seed[k - 1] != " "][:6]
    return list(dict.fromkeys(prefixes + [seed] + [f"{seed} {c}" for c in suffixes]))


def expand_seed(seed: str, lang: str, country: str, suffixes: list[str] | None = None) -> dict[str, tuple[float, int, int]]:
    """term -> (demand, prefix_len, rank). Only terms that contain the seed's first word are kept."""
    head = seed.split()[0].lower()
    out: dict[str, tuple[float, int, int]] = {}
    for q in seed_queries(seed, suffixes):
        try:
            terms = client.suggest(q, lang, country)
        except Exception as e:
            log.debug("suggest %r failed: %s", q, e)
            continue
        for pos, term in enumerate(terms, 1):
            term = term.strip().lower()
            if not term or head not in term:
                continue
            d = demand_from_observation(q, term, pos)
            if term not in out or d > out[term][0]:
                out[term] = (round(d, 1), len(q), pos)
    return out


# ----------------------------- competition -----------------------------

def competition_metrics(term: str, results: list[dict], apps: dict[str, App], rules: brand.Rules,
                        today: date) -> dict:
    top = results[:TOP_N]
    if not top:
        return {}
    installs = [r["min_installs"] or 0 for r in top]
    ratings = [r["score"] for r in top if r.get("score")]
    tokens = [t for t in re.findall(r"\w+", term.lower()) if len(t) > 1]
    title_hits = sum(1 for r in top if tokens and all(t in (r.get("title") or "").lower() for t in tokens))

    young, young_best, branded = 0, 0, 0
    known = 0
    carded = [apps[r["app_id"]] for r in top if r["app_id"] in apps and apps[r["app_id"]].details_at]
    # Share of games among the top results: "hair dye app" or "business suite" are not game niches
    games_share = round(sum(1 for a in carded if a.is_game) / len(carded), 2) if carded else None
    for r in top:
        a = apps.get(r["app_id"])
        flags = brand.classify(r.get("title"), r.get("developer"), a.developer_id if a else None, None, None, rules)
        if set(flags) & {"major", "hc_publisher", "franchise"}:
            branded += 1
        if a and a.released:
            known += 1
            if (today - a.released).days <= YOUNG_DAYS:
                young += 1
                young_best = max(young_best, a.real_installs or r["min_installs"] or 0)

    med = int(median(installs))
    young_share = young / max(known, 1) if known else 0.0
    brand_share = branded / len(top)
    title_share = title_hits / len(top)
    avg_rating = sum(ratings) / len(ratings) if ratings else None
    size = min(1.0, math.log10(med + 1) / 8)                     # 100M median -> 1
    comp = 100 * (0.45 * size + 0.25 * title_share + 0.20 * brand_share
                  + 0.10 * min(1.0, max(0.0, ((avg_rating or 4.0) - 3.5) / 1.3)))
    return {
        "competition": round(comp, 1),
        "top_median_installs": med,
        "top_avg_rating": round(avg_rating, 2) if avg_rating else None,
        "young_share": round(young_share, 2),
        "young_best_installs": young_best,
        "brand_share": round(brand_share, 2),
        "title_match_share": round(title_share, 2),
        "games_share": games_share,
        "top_apps": [r["app_id"] for r in top],
    }


def opportunity(demand: float, m: dict) -> float:
    if not m:
        return 0.0
    ease = 1 - m["competition"] / 100
    newcomers = min(1.0, m["young_share"] / 0.3)
    proof = min(1.0, math.log10((m["young_best_installs"] or 0) + 1) / 7)  # a young game with 10M -> 1
    gs = m.get("games_share")
    games = 1.0 if gs is None else min(1.0, gs / 0.6)    # mostly non-game results -> not our niche
    return round(demand * (0.45 * ease + 0.35 * newcomers + 0.20 * proof) * games, 1)


# ----------------------------- job -----------------------------

def title_seeds(session, limit: int = 40) -> list[str]:
    """First meaningful word of the hottest young non-brand games' titles."""
    rows = session.execute(
        select(App.title, GameMetrics.brand_flags)
        .join(GameMetrics, GameMetrics.app_id == App.app_id)
        .order_by(GameMetrics.trend_score.desc()).limit(limit * 3)
    ).all()
    seeds = []
    for title, flags in rows:
        if set(flags or []) & {"major", "franchise"}:
            continue
        words = [w for w in re.findall(r"[a-z][a-z0-9]+", (title or "").lower()) if w not in STOPWORDS and len(w) >= 4]
        if words:
            seeds.append(words[0])
    return list(dict.fromkeys(seeds))[:limit]


def ensure_seeds(session, mk: Market):
    lang, country = mk.lang, mk.country
    existing = set(session.scalars(select(SeedState.seed).where(SeedState.lang == lang, SeedState.country == country)).all())
    rows = [{"seed": s, "lang": lang, "country": country, "source": "genre"} for s in mk.seeds if s not in existing]
    if mk.primary:
        rows += [{"seed": s, "lang": lang, "country": country, "source": "title"}
                 for s in title_seeds(session) if s not in existing and s not in mk.seeds]
    upsert(session, SeedState, rows, key=["seed", "lang", "country"], update=[])


def run_market(mk: Market, stats: dict):
    cfg = get_settings()
    today = date.today()
    lang, country = mk.lang, mk.country
    seeds_budget = cfg.keyword_seeds_per_run if mk.primary else cfg.keyword_local_seeds_per_run
    refresh_budget = cfg.keyword_refresh_per_run if mk.primary else cfg.keyword_local_refresh_per_run
    before = (stats.get("seeds", 0), stats.get("terms", 0), stats.get("analyzed", 0))

    # 1. Expand a few seeds via autocomplete (never-expanded first, then the stalest)
    with session_scope() as s:
        ensure_seeds(s, mk)
        seeds = s.scalars(select(SeedState.seed).where(SeedState.lang == lang, SeedState.country == country)
                          .order_by(SeedState.expanded_at.is_not(None), SeedState.expanded_at)
                          .limit(seeds_budget)).all()
    found: dict[str, tuple[float, int, int, str]] = {}
    for seed, terms, err in parallel(lambda sd: expand_seed(sd, lang, country, mk.suffixes), seeds,
                                     workers=4, label="suggest"):
        if err:
            continue
        for term, (d, plen, pos) in terms.items():
            if term not in found or d > found[term][0]:
                found[term] = (d, plen, pos, seed)
    with session_scope() as s:
        existing = {k.term: k for k in s.scalars(select(Keyword).where(
            Keyword.lang == lang, Keyword.country == country, Keyword.term.in_(list(found)))).all()} if found else {}
        for term, (d, plen, pos, seed) in found.items():
            k = existing.get(term)
            if k is None:
                s.add(Keyword(term=term, lang=lang, country=country, seed=seed, demand=d,
                              suggest_prefix_len=plen, suggest_rank=pos))
            else:
                # Demand is re-measured on every expansion; keep the fresh value.
                k.demand, k.suggest_prefix_len, k.suggest_rank = d, plen, pos
        for seed in seeds:
            st = s.get(SeedState, (seed, lang, country))
            st.expanded_at = datetime.utcnow()
    stats["seeds"] = stats.get("seeds", 0) + len(seeds)
    stats["terms"] = stats.get("terms", 0) + len(found)

    # 2. Analyze competition for never-analyzed (highest demand first), then the stalest
    with session_scope() as s:
        kws = s.execute(select(Keyword.id, Keyword.term, Keyword.demand)
                        .where(Keyword.lang == lang, Keyword.country == country, Keyword.demand >= 10)
                        .order_by(Keyword.analyzed_at.is_not(None), Keyword.analyzed_at, Keyword.demand.desc())
                        .limit(refresh_budget)).all()
    results: dict[int, list[dict]] = {}
    for kw, res, err in parallel(lambda k: client.search(k.term, lang, country, 20), kws, label="search"):
        if not err:
            results[kw.id] = res

    # Make sure the top results have cards (release date is what tells us "young")
    top_ids = list({r["app_id"] for res in results.values() for r in res[:TOP_N]})
    add_stubs(top_ids, "keyword")
    with session_scope() as s:
        missing = s.scalars(select(App.app_id).where(App.app_id.in_(top_ids), App.details_at.is_(None))).all() if top_ids else []
    if missing:
        refresh(list(missing), "keyword-cards", set_tracked=True)

    with session_scope() as s:
        rules = brand.Rules.load(s)
        apps = {a.app_id: a for a in s.scalars(select(App).where(App.app_id.in_(top_ids))).all()} if top_ids else {}
        ranks = []
        for kw in kws:
            res = results.get(kw.id)
            if res is None:
                continue
            m = competition_metrics(kw.term, res, apps, rules, today)
            k = s.get(Keyword, kw.id)
            for field, value in m.items():
                setattr(k, field, value)
            k.opportunity = opportunity(k.demand, m)
            k.analyzed_at = datetime.utcnow()
            s.execute(delete(KeywordRank).where(KeywordRank.keyword_id == kw.id))
            ranks += [{"keyword_id": kw.id, "app_id": r["app_id"], "rank": r["rank"], "date": today} for r in res]
        upsert(s, KeywordRank, ranks, key=["keyword_id", "app_id"])
    stats["analyzed"] = stats.get("analyzed", 0) + len(results)
    stats.setdefault("markets", {})[country] = {
        "seeds": stats["seeds"] - before[0], "terms": stats["terms"] - before[1],
        "analyzed": stats["analyzed"] - before[2]}


def backfill_games_share() -> int:
    """Keywords analyzed before games_share existed: derive it from the stored top-10 ranks."""
    with session_scope() as s:
        kws = s.scalars(select(Keyword).where(Keyword.analyzed_at.is_not(None), Keyword.games_share.is_(None))).all()
        if not kws:
            return 0
        rows = s.execute(select(KeywordRank.keyword_id, App.is_game)
                         .join(App, App.app_id == KeywordRank.app_id)
                         .where(KeywordRank.keyword_id.in_([k.id for k in kws]), KeywordRank.rank <= TOP_N,
                                App.details_at.is_not(None))).all()
        by_kw: dict[int, list[bool]] = {}
        for kid, is_game in rows:
            by_kw.setdefault(kid, []).append(bool(is_game))
        for k in kws:
            flags = by_kw.get(k.id)
            if not flags:
                continue
            k.games_share = round(sum(flags) / len(flags), 2)
            if k.competition is not None:
                k.opportunity = opportunity(k.demand, {
                    "competition": k.competition, "young_share": k.young_share or 0,
                    "young_best_installs": k.young_best_installs or 0, "games_share": k.games_share})
        return len(by_kw)


def run():
    with job_run("keywords") as stats:
        stats["games_share_backfill"] = backfill_games_share()
        for mk in MARKETS:
            try:
                run_market(mk, stats)
            except Exception as e:  # one market failing must not cost the others
                log.warning("ниши %s-%s: %s", mk.lang, mk.country, e)
    return stats
