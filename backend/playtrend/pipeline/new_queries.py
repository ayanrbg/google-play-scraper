"""New search queries: what Google Play autocomplete starts suggesting, day by day.

Every day the detector types short prefixes into autocomplete in several markets: all two-letter
ones and the three-letter starts of words that game titles and game queries use ("mem" brings up
"meme mix challenge" in Brazil). A query a prefix suggests now but did not on its earlier crawls is
new, or has just grown popular enough to make the five suggestions. A prefix crawled for the first
time only sets the baseline: what it shows may have existed for years.

Each new query is then searched once: is it a game query, who ranks, and how many of the top
results actually carry the phrase - few means a gap a new game with the phrase in its title can
fill. The phrase's birth (release of the first app with all its words in the title) also flags
queries we saw from day one that are only months old: that is how "bomb chip challenge" looked
when it was worth building for.
"""

import math
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select

from playtrend.db import session_scope, upsert
from playtrend.models import App, GameMetrics, Keyword, SuggestPrefix, SuggestTerm
from playtrend.pipeline.common import job_run, log, parallel
from playtrend.pipeline.details import refresh
from playtrend.pipeline.keyword_markets import DETECTOR_MARKETS as MARKETS
from playtrend.pipeline.keyword_markets import NEW_QUERY_DAYS as NEW_DAYS
from playtrend.pipeline.keyword_markets import YOUNG_PHRASE_DAYS
from playtrend.pipeline.keyword_markets import DetectorMarket as DMarket
from playtrend.pipeline.keywords import add_result_stubs, demand_from_observation, save_search_results
from playtrend.play import client
from playtrend.settings import get_settings

RECHECK_DAYS = 7         # search results of a candidate are refreshed this often
SEEN_RECENTLY = 3        # only queries autocomplete still suggests are worth a search
PAID_YOUNG_DAYS = 60     # a game past 1M installs this young exploded: usually bought or viral traffic
PAID_YOUNG_INSTALLS = 1_000_000
SEED = "новые запросы"

# Words that say nothing about what the game is: left out of the phrase
GENERIC = set("""game games jogo jogos juego juegos jeu jeux oyun oyunu oyunlar oyunları oyunlari игра игры игру
    игре игр permainan gioco giochi spiel spiele the of a an and or for to in on with de da do la el los las le les
    del por para com sem player players two jugadores jogadores pemain игрока двоих 2p 1v1 pvp offline online
    internet internetsiz 3d 2d free gratis new nuevo novo baru simulator simulador simülatör симулятор simulation
    sim 2024 2025 2026 challenge mini apk mod real best fun app play kids android version download update wala
    jugar jogar oyna oynamak sin sem tanpa без для на с и в""".split())


def words(text: str | None) -> list[str]:
    return re.findall(r"\w+", (text or "").lower())


def phrase_of(term: str) -> tuple[str, ...]:
    """Core words of a query: what it is about, without "game", "offline", "2 player" and the like."""
    return tuple(sorted({w for w in words(term) if w not in GENERIC and len(w) >= 3 and not w.isdigit()}))


# ----------------------------- prefixes -----------------------------

def game_prefixes(s, mk: DMarket, limit: int) -> list[str]:
    """Three-letter starts of the words game titles and game queries of this market use, commonest first."""
    letters = set(mk.alphabet)
    counts: Counter = Counter()
    since = date.today() - timedelta(days=365)
    for (title,) in s.execute(select(App.title).where(App.is_game.is_(True), App.released >= since)):
        for w in set(words(title)):
            if len(w) >= 3 and all(c in letters for c in w[:3]):
                counts[w[:3]] += 1
    for (term,) in s.execute(select(Keyword.term).where(Keyword.lang == mk.lang, Keyword.country == mk.country,
                                                        Keyword.games_share >= 0.6)):
        for w in set(words(term)):
            if len(w) >= 3 and all(c in letters for c in w[:3]):
                counts[w[:3]] += 3      # what players type weighs more than what studios name
    return [p for p, _ in counts.most_common(limit)]


def ensure_prefixes(s, mk: DMarket, game_limit: int):
    two = [a + b for a in mk.alphabet for b in mk.alphabet]
    rows = [{"prefix": p, "lang": mk.lang, "country": mk.country} for p in two + game_prefixes(s, mk, game_limit)]
    upsert(s, SuggestPrefix, rows, key=["prefix", "lang", "country"], update=[])


# ----------------------------- observations -----------------------------

def record(s, mk: DMarket, seen: dict[str, list[str]], first_crawl: set[str], today: date) -> dict:
    """Store what each prefix suggested. A query is baseline when only first-crawled prefixes showed it."""
    obs: dict[str, dict] = {}
    for prefix, terms in seen.items():
        for pos, term in enumerate(terms, 1):
            term = term.strip().lower()
            if len(term) < 3 or len(term) > 120:
                continue
            o = obs.setdefault(term, {"prefix": prefix, "pos": pos, "old_prefix": False})
            if (len(prefix), pos) < (len(o["prefix"]), o["pos"]):
                o.update(prefix=prefix, pos=pos)
            o["old_prefix"] |= prefix not in first_crawl
    existing = {t.term: t for t in s.scalars(select(SuggestTerm).where(
        SuggestTerm.lang == mk.lang, SuggestTerm.country == mk.country, SuggestTerm.term.in_(list(obs))))} if obs else {}
    new = 0
    for term, o in obs.items():
        t = existing.get(term)
        if t is None:
            s.add(SuggestTerm(term=term, lang=mk.lang, country=mk.country, first_seen=today, last_seen=today,
                              days_seen=1, baseline=not o["old_prefix"], prefix=o["prefix"], prefix_len=len(o["prefix"]),
                              position=o["pos"], first_prefix_len=len(o["prefix"])))
            new += int(o["old_prefix"])
            continue
        if t.last_seen < today:
            t.days_seen += 1
            t.last_seen = today
        if (len(o["prefix"]), o["pos"]) < (t.prefix_len or 99, t.position or 99):
            t.prefix, t.prefix_len, t.position = o["prefix"], len(o["prefix"]), o["pos"]
    return {"terms": len(obs), "new": new}


def crawl(mk: DMarket, budget: int, today: date) -> dict:
    with session_scope() as s:
        rows = s.execute(select(SuggestPrefix.prefix, SuggestPrefix.first_crawled).where(
            SuggestPrefix.lang == mk.lang, SuggestPrefix.country == mk.country)
            .order_by(SuggestPrefix.crawled_at.is_not(None), SuggestPrefix.crawled_at).limit(budget)).all()
    first_crawl = {p for p, first in rows if first is None or first == today}
    seen: dict[str, list[str]] = {}
    for prefix, terms, err in parallel(lambda p: client.suggest(p, mk.lang, mk.country), [p for p, _ in rows],
                                       workers=4, progress_every=100, label="prefixes"):
        if not err:
            seen[prefix] = terms
    now = datetime.utcnow()
    with session_scope() as s:
        stats = record(s, mk, seen, first_crawl, today)
        for p in s.scalars(select(SuggestPrefix).where(SuggestPrefix.lang == mk.lang, SuggestPrefix.country == mk.country,
                                                       SuggestPrefix.prefix.in_(list(seen)))):
            p.crawled_at = now
            p.first_crawled = p.first_crawled or today
    return {"prefixes": len(seen), "failed": len(rows) - len(seen), **stats}


# ----------------------------- phrases -----------------------------

class TitleIndex:
    """Words of every app title we know -> apps, to date a phrase by its first game."""

    def __init__(self, s, today: date):
        self.today = today
        self.apps: dict[str, tuple] = {}
        self.by_word: dict[str, set[str]] = defaultdict(set)
        rows = s.execute(select(App.app_id, App.title, App.released, App.is_game, App.real_installs,
                                GameMetrics.v7, GameMetrics.traffic, GameMetrics.brand_flags)
                         .outerjoin(GameMetrics, GameMetrics.app_id == App.app_id)
                         .where(App.released.is_not(None))).all()
        for app_id, title, released, is_game, installs, v7, traffic, flags in rows:
            self.apps[app_id] = (released, is_game, installs or 0, v7 or 0, traffic, set(flags or []))
            for w in set(words(title)):
                if len(w) >= 3:
                    self.by_word[w].add(app_id)

    def matching(self, phrase: tuple[str, ...]) -> set[str]:
        sets = [self.by_word.get(w) for w in phrase]
        if not phrase or not all(sets):
            return set()
        return set.intersection(*sorted(sets, key=len))

    def stats(self, phrase: tuple[str, ...]) -> dict:
        ids = self.matching(phrase)
        if not ids:
            return {"phrase_birth": None, "phrase_titles": 0, "phrase_titles_30d": 0, "leader_app_id": None,
                    "leader_paid": False}
        released = [self.apps[i][0] for i in ids]
        games = [i for i in ids if self.apps[i][1] and not self.apps[i][5] & {"major", "franchise"}]
        leader = max(games, key=lambda i: self.apps[i][3], default=None)
        return {
            "phrase_birth": min(released),
            "phrase_titles": len(ids),
            "phrase_titles_30d": sum(1 for r in released if (self.today - r).days <= 30),
            "leader_app_id": leader,
            "leader_paid": bool(leader) and self.looks_paid(leader),
        }

    def looks_paid(self, app_id: str) -> bool:
        released, _, installs, _, traffic, _ = self.apps[app_id]
        exploded = (self.today - released).days <= PAID_YOUNG_DAYS and installs >= PAID_YOUNG_INSTALLS
        return traffic in ("paid", "mixed") or exploded


def score(t: SuggestTerm, k: Keyword | None, leader_v7: float, today: date) -> float | None:
    """0-100: a game query that is new (or a young phrase), with few results carrying it, that people
    search, and that a growing game already proves. None until the query is searched."""
    if k is None or k.analyzed_at is None or k.games_share is None:
        return None
    if k.games_share < 0.5:
        return 0.0
    if not t.baseline and (today - t.first_seen).days <= NEW_DAYS:
        fresh = 1.0
    elif t.phrase_birth:
        age = (today - t.phrase_birth).days
        fresh = 1.0 if age <= 120 else 0.6 if age <= 240 else 0.25
    else:
        fresh = 0.4
    rel = t.relevant_top if t.relevant_top is not None else 10
    gap = 1.0 if rel <= 1 else 0.75 if rel <= 3 else 0.45 if rel <= 5 else 0.2
    demand = min(1.0, (k.demand or 0) / 80)
    proof = 0.4 + 0.6 * min(1.0, math.log10(leader_v7 + 1) / 5) if leader_v7 else 0.4
    return round(100 * fresh * gap * (0.5 + 0.5 * demand) * proof, 1)


# ----------------------------- analysis -----------------------------

def relevant_count(top: list[str], phrase: tuple[str, ...], titles: dict[str, str]) -> int | None:
    if not phrase:
        return None
    return sum(1 for a in top[:10] if set(phrase) <= set(words(titles.get(a))))


def analyze(mk: DMarket, index: TitleIndex, budget: int, today: date) -> dict:
    """Date the phrases of recently suggested queries, search the best candidates, score them."""
    recent = today - timedelta(days=SEEN_RECENTLY)
    with session_scope() as s:
        terms = s.scalars(select(SuggestTerm).where(SuggestTerm.lang == mk.lang, SuggestTerm.country == mk.country,
                                                    SuggestTerm.last_seen >= recent)).all()
        for t in terms:
            p = phrase_of(t.term)
            t.phrase = " ".join(p) or None
            for field, value in index.stats(p).items():
                setattr(t, field, value)
        stale = datetime.utcnow() - timedelta(days=RECHECK_DAYS)
        young = today - timedelta(days=YOUNG_PHRASE_DAYS)

        def wanted(t):
            if t.checked_at and t.checked_at >= stale:
                return None
            if not t.baseline and (today - t.first_seen).days <= NEW_DAYS:
                return (0, -t.first_seen.toordinal())
            if t.phrase_birth and t.phrase_birth >= young and t.leader_app_id:
                return (1, -index.apps[t.leader_app_id][3])
            return None
        queue = sorted((w, t.id) for t in terms if (w := wanted(t)) is not None)[:budget]
        ids = {i for _, i in queue}
        cand = [t for t in terms if t.id in ids]
        known = {k.term: k for k in s.scalars(select(Keyword).where(
            Keyword.lang == mk.lang, Keyword.country == mk.country, Keyword.term.in_([t.term for t in cand])))} if cand else {}
        to_search = {}
        for t in cand:
            k = known.get(t.term)
            if k is None:
                k = Keyword(term=t.term, lang=mk.lang, country=mk.country, seed=SEED,
                            demand=round(demand_from_observation(t.prefix or t.term, t.term, t.position or 1), 1),
                            suggest_prefix_len=t.prefix_len, suggest_rank=t.position)
                s.add(k)
                s.flush()
            t.keyword_id = k.id
            if not k.analyzed_at or k.analyzed_at < stale:
                to_search[k.id] = k.term
    results: dict[int, list[dict]] = {}
    for kw_id, res, err in parallel(lambda i: client.search(to_search[i], mk.lang, mk.country, 20), list(to_search),
                                    workers=4, label="new-search"):
        if not err:
            results[kw_id] = res
    if results:
        top_ids = add_result_stubs(results, to_search, mk.lang, mk.country)
        with session_scope() as s:
            missing = s.scalars(select(App.app_id).where(App.app_id.in_(top_ids), App.details_at.is_(None))).all()
        if missing:
            refresh(list(missing), "keyword-cards", set_tracked=True)
        with session_scope() as s:
            save_search_results(s, results, today)
    with session_scope() as s:
        scored = 0
        terms = s.scalars(select(SuggestTerm).where(SuggestTerm.lang == mk.lang, SuggestTerm.country == mk.country,
                                                    SuggestTerm.keyword_id.is_not(None))).all()
        kws = {k.id: k for k in s.scalars(select(Keyword).where(Keyword.id.in_([t.keyword_id for t in terms])))} if terms else {}
        top = {a for k in kws.values() for a in (k.top_apps or [])[:10]}
        titles = dict(s.execute(select(App.app_id, App.title).where(App.app_id.in_(top))).all()) if top else {}
        now = datetime.utcnow()
        for t in terms:
            k = kws.get(t.keyword_id)
            if k is None or not k.analyzed_at:
                continue
            t.relevant_top = relevant_count(k.top_apps or [], phrase_of(t.term), titles)
            leader_v7 = index.apps[t.leader_app_id][3] if t.leader_app_id in index.apps else 0
            t.score = score(t, k, leader_v7, today)
            if t.id in ids:
                t.checked_at = now
            scored += 1
    return {"candidates": len(ids), "searched": len(results), "scored": scored}


def run():
    cfg = get_settings()
    today = date.today()
    with job_run("newqueries") as stats:
        with session_scope() as s:
            for mk in MARKETS:
                ensure_prefixes(s, mk, cfg.new_queries_game_prefixes)
        for mk in MARKETS:
            try:
                stats.setdefault("markets", {})[mk.country] = crawl(mk, cfg.new_queries_prefixes_per_market, today)
            except Exception as e:  # one market failing must not cost the others
                log.warning("новые запросы %s-%s: %s", mk.lang, mk.country, e)
        with session_scope() as s:
            index = TitleIndex(s, today)
        for mk in MARKETS:
            try:
                stats["markets"].setdefault(mk.country, {}).update(
                    analyze(mk, index, cfg.new_queries_search_per_market, today))
            except Exception as e:
                log.warning("новые запросы, разбор %s-%s: %s", mk.lang, mk.country, e)
        m = stats.get("markets", {})
        stats["new"] = sum(x.get("new", 0) for x in m.values())
        stats["searched"] = sum(x.get("searched", 0) for x in m.values())
    return stats
