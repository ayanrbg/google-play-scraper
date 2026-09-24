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

from gpi.catalog import KEYWORD_MARKETS
from gpi.db import session_scope, upsert
from gpi.models import App, GameMetrics, Keyword, KeywordRank, SeedState
from gpi.pipeline import brand
from gpi.pipeline.common import job_run, log, parallel
from gpi.pipeline.details import add_stubs, refresh
from gpi.play import client
from gpi.settings import get_settings

GENRE_SEEDS = [
    "puzzle", "sort", "merge", "match", "block", "tile", "idle", "tycoon", "simulator", "survival",
    "zombie", "shooter", "racing", "car", "parking", "drift", "truck", "bus", "city", "farm",
    "cooking", "restaurant", "cafe", "hotel", "hospital", "school", "makeover", "dress up",
    "fashion", "hair", "nail", "baby", "pet", "cat", "dog", "horse", "dinosaur", "dragon", "monster",
    "robot", "ninja", "knight", "magic", "tower defense", "castle", "kingdom", "war", "army",
    "battle", "arena", "io", "snake", "ball", "run", "jump", "stack", "color", "paint", "draw",
    "coloring", "word", "crossword", "trivia", "quiz", "math", "brain", "logic", "escape",
    "hidden object", "mystery", "horror", "scary", "prank", "asmr", "satisfying", "relax", "fidget",
    "slime", "cake", "candy", "fruit", "water", "screw", "nuts bolts", "jam", "traffic", "hexa",
    "2048", "solitaire", "mahjong", "sudoku", "chess", "domino", "bingo", "ludo", "dice",
    "fishing", "hunting", "sniper", "gun", "plane", "train", "ship", "tank", "mining", "craft",
    "building", "sandbox", "open world", "obby", "parkour", "stickman", "ragdoll", "physics",
    "car crash", "mech", "space", "pirate", "fish", "ocean", "garden", "home design", "house",
    "decor", "cleaning", "wash", "repair", "doctor", "dentist", "clicker", "roguelike", "rpg",
    "anime", "gacha", "card battle", "auto battler", "survivor", "platformer", "runner", "arcade",
    "pixel", "offline games", "games for kids", "2 player games", "multiplayer", "simulator games",
]
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


def seed_queries(seed: str) -> list[str]:
    prefixes = [seed[:k] for k in range(2, len(seed)) if seed[k - 1] != " "][:6]
    return list(dict.fromkeys(prefixes + [seed] + [f"{seed} {c}" for c in string.ascii_lowercase]))


def expand_seed(seed: str, lang: str, country: str) -> dict[str, tuple[float, int, int]]:
    """term -> (demand, prefix_len, rank). Only terms that contain the seed's first word are kept."""
    head = seed.split()[0]
    out: dict[str, tuple[float, int, int]] = {}
    for q in seed_queries(seed):
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
        "top_apps": [r["app_id"] for r in top],
    }


def opportunity(demand: float, m: dict) -> float:
    if not m:
        return 0.0
    ease = 1 - m["competition"] / 100
    newcomers = min(1.0, m["young_share"] / 0.3)
    proof = min(1.0, math.log10((m["young_best_installs"] or 0) + 1) / 7)  # a young game with 10M -> 1
    return round(demand * (0.45 * ease + 0.35 * newcomers + 0.20 * proof), 1)


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


def ensure_seeds(session, lang: str, country: str):
    existing = set(session.scalars(select(SeedState.seed).where(SeedState.lang == lang, SeedState.country == country)).all())
    rows = [{"seed": s, "lang": lang, "country": country, "source": "genre"} for s in GENRE_SEEDS if s not in existing]
    rows += [{"seed": s, "lang": lang, "country": country, "source": "title"}
             for s in title_seeds(session) if s not in existing and s not in GENRE_SEEDS]
    upsert(session, SeedState, rows, key=["seed", "lang", "country"], update=[])


def run_market(lang: str, country: str, stats: dict):
    cfg = get_settings()
    today = date.today()

    # 1. Expand a few seeds via autocomplete (never-expanded first, then the stalest)
    with session_scope() as s:
        ensure_seeds(s, lang, country)
        seeds = s.scalars(select(SeedState.seed).where(SeedState.lang == lang, SeedState.country == country)
                          .order_by(SeedState.expanded_at.is_not(None), SeedState.expanded_at)
                          .limit(cfg.keyword_seeds_per_run)).all()
    found: dict[str, tuple[float, int, int, str]] = {}
    for seed, terms, err in parallel(lambda sd: expand_seed(sd, lang, country), seeds, workers=2, label="suggest"):
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
                        .limit(cfg.keyword_refresh_per_run)).all()
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


def run():
    with job_run("keywords") as stats:
        for lang, country in KEYWORD_MARKETS:
            run_market(lang, country, stats)
    return stats
