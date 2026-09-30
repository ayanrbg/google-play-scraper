"""Keys of one game (reverse ASO), collected on request from the game page.

For every keyword market: the listing as players there see it -> candidate phrases from the
title, short and full description, plus what autocomplete completes the strongest ones with ->
demand of each phrase (how short a prefix still makes autocomplete suggest it) -> the game's
position in search. Searched phrases also land in the shared keyword tables, so they show up
in niches and count towards the game's search visibility.

The web API only queues a request (it never talks to Google); the worker runs the queue.
"""

import re
from collections import Counter
from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from playtrend.db import session_scope
from playtrend.models import App, ChartDaily, Keyword, KeysReport, KeywordRank
from playtrend.pipeline.common import log, parallel
from playtrend.pipeline.keyword_markets import MARKETS, Market
from playtrend.pipeline.keywords import add_result_stubs, demand_from_observation, save_search_results
from playtrend.play import client
from playtrend.play.http import NotFound

SEARCH_DEPTH = 30               # positions below this count as "not found"
MAX_TERMS = 30                  # English/US market
MAX_TERMS_LOCAL = 18            # a market with a translated listing
MAX_TERMS_UNTRANSLATED = 6      # listing not translated: just the title phrases
EXPAND_TOP = 4                  # strongest phrases completed via autocomplete
MAX_KNOWN = 10                  # queries the game already ranks for, re-checked alongside
PREFIX_LADDER = (2, 4, 7)       # prefixes tried before the full phrase
FRESH_DAYS = 7                  # a keyword searched this recently is not searched again
POPULAR_DAYS = 14               # chart history that tells where the game gets its players
POPULAR_MARKETS = 6             # such countries added beyond the fixed keyword markets
POPULAR_PER_LANG = 2            # ...at most this many per language: one listing, the same phrases
POPULAR_MIN_SHARE = 0.05        # ...and none far below the game's main country (a day at #190 is noise),
POPULAR_ENOUGH = 0.005          # unless big on its own (~#10 every day in Hungary): India can dwarf the rest

# Rough size of each store in game downloads (US = 1): #5 in Peru brings fewer players than #20 in Brazil
COUNTRY_SIZE = {
    "in": 4.0, "br": 1.5, "id": 1.4, "us": 1.0, "mx": 0.7, "ru": 0.6, "pk": 0.5, "tr": 0.45, "ph": 0.45,
    "vn": 0.4, "eg": 0.35, "bd": 0.3, "co": 0.3, "th": 0.25, "ng": 0.25, "ar": 0.25, "iq": 0.2, "de": 0.2,
    "fr": 0.2, "dz": 0.2, "sa": 0.18, "gb": 0.15, "it": 0.15, "es": 0.15, "ma": 0.15, "kr": 0.15, "jp": 0.15,
    "pe": 0.14, "my": 0.14, "ua": 0.13, "pl": 0.11, "za": 0.11, "cl": 0.1, "ve": 0.09, "kz": 0.09, "uz": 0.09,
    "ke": 0.08, "ca": 0.08, "ec": 0.07, "ro": 0.07, "tw": 0.06, "au": 0.05, "ae": 0.05, "nl": 0.05, "pt": 0.04,
    "cz": 0.035, "hu": 0.03, "gr": 0.03, "be": 0.03, "se": 0.03, "il": 0.03, "at": 0.025, "ch": 0.025,
    "hk": 0.02, "sg": 0.02, "dk": 0.018, "no": 0.018, "fi": 0.018, "ie": 0.015, "nz": 0.012,
}
# How much a chart place says about downloads: top charts count installs, movers growth, grossing revenue
COLLECTION_WEIGHT = {"top_free": 1.0, "top_new_free": 0.5, "trending": 0.3, "top_grossing": 0.2}

# Store language of each chart country, for markets added from where the game is popular
COUNTRY_LANG = {
    "us": "en", "ca": "en", "gb": "en", "ie": "en", "au": "en", "nz": "en", "in": "en", "ph": "en", "sg": "en",
    "za": "en", "ng": "en", "ke": "en", "pk": "en", "mx": "es", "es": "es", "ar": "es", "co": "es", "cl": "es",
    "pe": "es", "ve": "es", "ec": "es", "br": "pt", "pt": "pt", "de": "de", "at": "de", "ch": "de", "fr": "fr",
    "be": "fr", "dz": "fr", "ma": "fr", "it": "it", "nl": "nl", "pl": "pl", "se": "sv", "dk": "da", "no": "no",
    "fi": "fi", "tr": "tr", "ru": "ru", "kz": "ru", "uz": "ru", "ua": "uk", "cz": "cs", "ro": "ro", "gr": "el",
    "hu": "hu", "jp": "ja", "kr": "ko", "tw": "zh-TW", "hk": "zh-HK", "id": "id", "vn": "vi", "th": "th",
    "my": "ms", "bd": "bn", "sa": "ar", "ae": "ar", "eg": "ar", "iq": "ar", "il": "iw",
}

STOPWORDS = {
    "en": set("""a about after all also an and any are as at be been best but by can come could do does each
        enjoy even every experience feature features for free from fun game games get go has have how if in into
        is it it's its just let like make many more most much new no not now of on one only or other our out over
        play player players plus so some such than that the their them then there these they this time to top
        up us use very was way we what when where which while who why will with without you your app level
        levels download""".split()),
    "es": set("""de la que el en y a los del se las por un para con no una su al lo como más o pero sus le ya si
        juego juegos tu te es nuevo nueva todos todo cada puedes tus muy sin sobre este esta entre cuando también
        hasta desde nos""".split()),
    "pt": set("""de a o que e do da em um para é com não uma os no se na por mais as dos como mas ao das seu sua
        ou quando muito nos já também só pelo pela até isso entre depois sem mesmo aos seus jogo jogos você novo
        nova todos cada""".split()),
    "ru": set("""и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее мне
        было вот от меня еще нет о из ему когда даже ли если уже или ни быть был до вас вам там себя ей может
        они тут где есть для мы тебя их чем была сам чтобы без чего раз тоже себе под будет кто этот того этого
        какой здесь этом один мой тем при об другой после над больше тот через эти нас про всего них какая много
        эту свою этой перед лучше том такой им более всегда всю между игра игры игру игре ваш ваши свой свои
        каждый новый новые""".split()),
    "tr": set("""ve bir bu da de için ile gibi daha çok en ne o var mı mi ama her şey sen siz ben biz onlar olan
        olarak kadar sonra oyun oyunu oyunlar yeni""".split()),
    "id": set("""dan di yang untuk dengan ini itu ke dari dalam tidak akan ada juga bisa atau kamu anda kami pada
        sebagai game permainan baru semua setiap lebih""".split()),
}
_BREAK = re.compile(r"\s[-–—]\s|[^\w\s'’-]")
_TOKEN = re.compile(r"\w[\w'’-]*")


# ----------------------------- text -----------------------------

def tokens(line: str) -> list[str]:
    return [t.strip("'’-") for t in _TOKEN.findall(line.lower())]


def phrases(text: str, stop: set[str]) -> Counter:
    """1-3 word phrases that neither start nor end with a stopword, not crossing punctuation."""
    out: Counter = Counter()
    for line in _BREAK.sub("\n", text or "").split("\n"):
        toks = tokens(line)
        for n in (1, 2, 3):
            for i in range(len(toks) - n + 1):
                g = toks[i:i + n]
                if g[0] in stop or g[-1] in stop or all(t.isdigit() for t in g):
                    continue
                p = " ".join(g)
                if len(p) >= 3:
                    out[p] += 1
    return out


def stopwords(lang: str) -> set[str]:
    return STOPWORDS["en"] | STOPWORDS.get(lang, set())


def candidates(title: str, summary: str, description: str, lang: str, limit: int) -> list[tuple[str, str]]:
    """Best phrases to check, with where they came from: title > short description > full description."""
    stop = stopwords(lang)
    t, su, d = phrases(title, stop), phrases(summary, stop), phrases(description, stop)
    pool = set(t) | set(su) | {p for p, n in d.items() if n >= (2 if " " in p else 3)}
    scored = []
    for p in pool:
        score = 6 * (p in t) + 3 * (p in su) + min(d[p], 8)
        if " " in p:
            score *= 1.3
        scored.append((score, p))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [(p, "title" if p in t else "summary" if p in su else "description") for _, p in scored[:limit]]


def stem(w: str) -> str:
    """Crude plural folding, enough to match "nuts" with "nut"."""
    return w[:-1] if len(w) > 3 and w.endswith("s") else w


def vocabulary(title: str, summary: str, description: str, lang: str) -> set[str]:
    """Words that tie an autocomplete suggestion to this game."""
    stop = stopwords(lang)
    words = Counter(w for w in tokens(description) if w not in stop)
    return {stem(w) for w in tokens(f"{title} {summary}") if w not in stop and len(w) >= 3} | \
           {stem(w) for w, n in words.items() if n >= 2 and len(w) >= 3}


def relevant(suggestion: str, vocab: set[str]) -> bool:
    """Two of the game's words, or one if that is all the suggestion has ("bolt vpn" is not ours,
    "screw puzzle girl" is)."""
    words = {stem(w) for w in tokens(suggestion) if w not in STOPWORDS["en"]}
    return len(words & vocab) >= min(2, len(words))


def occurrences(phrase: str, text: str) -> int:
    return len(re.findall(rf"(?<!\w){re.escape(phrase)}(?!\w)", (text or "").lower()))


def density(description: str, lang: str, top: int = 12) -> tuple[int, list[list]]:
    words = tokens(description)
    stop = stopwords(lang)
    counts = Counter(w for w in words if w not in stop and len(w) >= 3 and not w.isdigit())
    return len(words), [[w, n] for w, n in counts.most_common(top)]


# ----------------------------- network -----------------------------

def measure_demand(term: str, lang: str, country: str, known: tuple | None = None) -> tuple | None:
    """(demand, prefix_len, rank) from the shortest prefix that still surfaces the term.

    known: an observation made already (from expanding a phrase); only shorter prefixes are tried.
    (0, None, None) = autocomplete never suggests it: nobody searches this. None = requests failed.
    """
    best = known
    limit = known[1] if known else len(term) + 1
    ladder = [n for n in PREFIX_LADDER if n < len(term) and term[n - 1] != " "] + [len(term)]
    failed = 0
    for n in ladder:
        if n >= limit:
            break
        q = term[:n]
        try:
            sugg = [x.strip().lower() for x in client.suggest(q, lang, country)]
        except Exception:
            failed += 1
            continue
        if term in sugg:
            pos = sugg.index(term) + 1
            return round(demand_from_observation(q, term, pos), 1), n, pos
    if best:
        return best
    return None if failed == len(ladder) else (0.0, None, None)


def expand(phrases_: list[str], vocab: set[str], lang: str, country: str) -> dict[str, tuple]:
    """Autocomplete completions of the strongest phrases that share a word with the game's texts."""
    out: dict[str, tuple] = {}
    for p, sugg, err in parallel(lambda x: client.suggest(x, lang, country), phrases_, progress_every=0):
        if err:
            continue
        for pos, s in enumerate(sugg or [], 1):
            s = s.strip().lower()
            if s != p and not relevant(s, vocab):
                continue
            d = (round(demand_from_observation(p, s, pos), 1), len(p), pos)
            if s not in out or d[0] > out[s][0]:
                out[s] = d
    return out


# ----------------------------- report -----------------------------

def analyze_market(app_id: str, game_title: str, mk: Market, en_description: str | None) -> tuple[dict, str | None]:
    entry = {"lang": mk.lang, "country": mk.country, "label": mk.label}
    try:
        lst = client.listing(app_id, mk.lang, mk.country)
    except NotFound:
        return {**entry, "available": False}, None
    title, summary, desc = lst["title"], lst["summary"], lst["description"]
    # English-language stores read the English listing as is; elsewhere an English text means no translation
    localized = mk.lang == "en" or en_description is None or desc.strip() != en_description.strip()
    limit = MAX_TERMS if mk.primary else MAX_TERMS_LOCAL if localized else MAX_TERMS_UNTRANSLATED

    pool: dict[str, str] = {}          # term -> source
    observed: dict[str, tuple] = {}    # term -> (demand, prefix_len, rank) seen while expanding
    own = candidates(title, summary if localized else "", desc if localized else "", mk.lang,
                     limit if not localized else max(6, int(limit * 0.6)))
    for p, src in own:
        pool[p] = src
    if localized:
        # Completions of both the best phrases and the best single words (broad "screw" finds "screw jam")
        multi, single = [p for p, _ in own if " " in p], [p for p, _ in own if " " not in p]
        seeds = multi[:EXPAND_TOP // 2] + single[:EXPAND_TOP - min(len(multi), EXPAND_TOP // 2)]
        observed = expand(seeds, vocabulary(title, summary, desc, mk.lang), mk.lang, mk.country)
        for term, _ in sorted(observed.items(), key=lambda kv: -kv[1][0]):
            if len(pool) >= limit:
                break
            pool.setdefault(term, "suggest")

    with session_scope() as s:
        known_terms = s.execute(
            select(Keyword.term).join(KeywordRank, KeywordRank.keyword_id == Keyword.id)
            .where(KeywordRank.app_id == app_id, Keyword.lang == mk.lang, Keyword.country == mk.country)
            .order_by(KeywordRank.rank, Keyword.demand.desc()).limit(MAX_KNOWN)).scalars().all()
        for term in known_terms:
            pool.setdefault(term, "known")
        existing = {k.term: k for k in s.scalars(select(Keyword).where(
            Keyword.lang == mk.lang, Keyword.country == mk.country, Keyword.term.in_(list(pool))))}
        existing = {t: (k.id, k.demand, k.suggest_prefix_len, k.suggest_rank, k.analyzed_at) for t, k in existing.items()}

    fresh_after = datetime.utcnow() - timedelta(days=FRESH_DAYS)

    def check(term: str):
        ex = existing.get(term)
        if ex and ex[2]:                       # demand measured by the daily keyword job
            demand = (ex[1], ex[2], ex[3])
        else:
            demand = measure_demand(term, mk.lang, mk.country, observed.get(term))
        if ex and ex[4] and ex[4] >= fresh_after:
            return demand, None
        # Autocomplete rarely echoes a bare word ("puzzle"), yet the title's words are worth a position
        if demand is None or (demand[0] <= 0 and pool[term] not in ("title", "known")):
            return demand, None
        return demand, client.search(term, mk.lang, mk.country, SEARCH_DEPTH)

    checked: dict[str, tuple] = {}
    for term, res, err in parallel(check, list(pool), progress_every=0):
        if err:
            log.debug("ключи %s %r: %s", app_id, term, err)
            continue
        checked[term] = res

    # Keywords with a measured demand join the shared table; search results replace their ranks
    ids: dict[str, int] = {}
    with session_scope() as s:
        for term, (demand, _) in checked.items():
            if demand is None:
                continue
            k = s.scalar(select(Keyword).where(Keyword.term == term, Keyword.lang == mk.lang,
                                               Keyword.country == mk.country))
            if k is None:
                k = Keyword(term=term[:255], lang=mk.lang, country=mk.country, seed=f"игра: {game_title}"[:255])
                s.add(k)
            if demand[1] and (not k.suggest_prefix_len or demand[1] <= k.suggest_prefix_len):
                k.demand, k.suggest_prefix_len, k.suggest_rank = demand
            elif not k.suggest_prefix_len:
                k.demand = demand[0]
            s.flush()
            ids[term] = k.id
    results = {ids[t]: res for t, (_, res) in checked.items() if res is not None and t in ids}
    result_titles = {r["app_id"]: r.get("title") for res in results.values() for r in res}
    if results:
        add_result_stubs(results, {i: t for t, i in ids.items()}, mk.lang, mk.country)
        with session_scope() as s:
            save_search_results(s, results, date.today())

    terms = []
    with session_scope() as s:
        kws = {k.id: k for k in s.scalars(select(Keyword).where(Keyword.id.in_(list(ids.values()))))} if ids else {}
        ranks: dict[int, list] = {}
        if ids:
            for kr in s.scalars(select(KeywordRank).where(KeywordRank.keyword_id.in_(list(ids.values())))
                                .order_by(KeywordRank.rank)):
                ranks.setdefault(kr.keyword_id, []).append(kr)
        top_ids = {kr.app_id for rs in ranks.values() for kr in rs[:3]}
        titles = dict(s.execute(select(App.app_id, App.title).where(App.app_id.in_(top_ids))).all()) if top_ids else {}
        for term, src in pool.items():
            if term not in checked:
                continue
            k = kws.get(ids.get(term))
            rs = ranks.get(k.id, []) if k else []
            own_rank = next((kr.rank for kr in rs if kr.app_id == app_id), None)
            terms.append({
                "term": term, "keyword_id": k.id if k else None, "source": src,
                "in_title": occurrences(term, title) > 0, "in_summary": occurrences(term, summary) > 0,
                "in_desc": occurrences(term, desc),
                "demand": k.demand if k else None,
                "rank": own_rank if own_rank and own_rank <= SEARCH_DEPTH else None,
                "searched": bool(rs),
                "competition": k.competition if k else None, "opportunity": k.opportunity if k else None,
                "top": [{"app_id": kr.app_id, "title": titles.get(kr.app_id) or result_titles.get(kr.app_id)}
                        for kr in rs[:3]],
            })
    terms.sort(key=lambda t: -(t["demand"] or 0))
    words, dens = density(desc, mk.lang)
    return {**entry, "available": True, "localized": localized, "title": title, "summary": summary,
            "words": words, "density": dens, "terms": terms}, desc


def popularity(s, app_id: str) -> dict[str, dict]:
    """Where the game gets its players, from its chart places over the last POPULAR_DAYS of its charts.

    score ~ share of downloads: store size x place^-0.8 (the curve of installs down a top chart), the best
    collection each day, averaged over the window so a week at #10 beats one day at #3.
    """
    last = s.scalar(select(func.max(ChartDaily.date)).where(ChartDaily.app_id == app_id))
    if last is None:
        return {}
    daily: dict[tuple[str, date], float] = {}
    out: dict[str, dict] = {}
    for c in s.scalars(select(ChartDaily).where(ChartDaily.app_id == app_id,
                                                ChartDaily.date > last - timedelta(days=POPULAR_DAYS))):
        w = COLLECTION_WEIGHT.get(c.collection, 0.2)
        for cc, rank in (c.countries or {}).items():
            v = w * COUNTRY_SIZE.get(cc, 0.02) * rank ** -0.8
            daily[cc, c.date] = max(v, daily.get((cc, c.date), 0.0))
            p = out.setdefault(cc, {"score": 0.0, "rank": rank, "collection": c.collection, "days": 0, "_best": 0.0})
            if v > p["_best"]:
                p.update(rank=rank, collection=c.collection, _best=v)
    for (cc, _), v in daily.items():
        out[cc]["score"] += v / POPULAR_DAYS
        out[cc]["days"] += 1
    for p in out.values():
        del p["_best"]
        p["score"] = round(p["score"], 4)
    return out


def popular_markets(pop: dict[str, dict]) -> list[Market]:
    """The countries bringing the game most players, beyond the fixed keyword markets."""
    covered = {m.country for m in MARKETS}
    floor = min(POPULAR_MIN_SHARE * max((p["score"] for p in pop.values()), default=0), POPULAR_ENOUGH)
    per_lang: Counter = Counter()
    out = []
    for cc in sorted(pop, key=lambda c: -pop[c]["score"]):
        lang = COUNTRY_LANG.get(cc)
        if pop[cc]["score"] < floor:
            break
        if cc in covered or lang is None or per_lang[lang] >= POPULAR_PER_LANG:
            continue
        per_lang[lang] += 1
        out.append(Market(lang, cc, f"{lang} · {cc.upper()}", []))
        if len(out) >= POPULAR_MARKETS:
            break
    return out


def build_report(app_id: str, progress=lambda p: None) -> dict:
    with session_scope() as s:
        app = s.get(App, app_id)
        if app is None:
            raise ValueError("игра не найдена")
        game_title = app.title or app_id
        pop = popularity(s, app_id)
    # The English/US market first (others compare their listing with it), then by where the players are
    markets = sorted(MARKETS + popular_markets(pop),
                     key=lambda m: (not m.primary, -pop.get(m.country, {}).get("score", 0)))
    out, en_description = [], None
    for i, mk in enumerate(markets):
        progress({"market": mk.label, "done": i, "total": len(markets)})
        try:
            entry, desc = analyze_market(app_id, game_title, mk, en_description)
        except Exception as e:
            log.warning("ключи %s, рынок %s-%s: %s", app_id, mk.lang, mk.country, e)
            entry, desc = {"lang": mk.lang, "country": mk.country, "label": mk.label, "error": str(e)[:300]}, None
        if mk.primary:
            en_description = desc
        if mk.country in pop:
            entry["popular"] = {k: pop[mk.country][k] for k in ("rank", "collection", "days")}
        out.append(entry)
    ranked = [dict(t, country=m["country"]) for m in out for t in m.get("terms", []) if t["rank"] and t["rank"] <= 10]
    ranked.sort(key=lambda t: -(t["demand"] or 0))
    return {"markets": out, "summary": {
        "terms": sum(len(m.get("terms", [])) for m in out),
        "ranked_top10": len(ranked),
        "best": ranked[:8],
    }}


# ----------------------------- queue -----------------------------

def reset_interrupted():
    """A report cut off by a worker restart goes back to the queue."""
    with session_scope() as s:
        for r in s.scalars(select(KeysReport).where(KeysReport.status == "running")):
            r.status = "pending"


def process_next() -> bool:
    """Build the oldest requested report. False when the queue is empty."""
    with session_scope() as s:
        r = s.scalars(select(KeysReport).where(KeysReport.status == "pending")
                      .order_by(KeysReport.requested_at).limit(1)).first()
        if r is None:
            return False
        r.status, r.started_at, r.error, r.progress = "running", datetime.utcnow(), None, {}
        app_id = r.app_id
    log.info("ключи игры %s: сбор начат", app_id)

    def progress(p: dict):
        with session_scope() as s:
            rep = s.get(KeysReport, app_id)
            if rep is not None:
                rep.progress = p

    try:
        result = build_report(app_id, progress)
    except Exception as e:
        log.exception("ключи игры %s: ошибка", app_id)
        with session_scope() as s:
            rep = s.get(KeysReport, app_id)
            rep.status, rep.finished_at, rep.error = "error", datetime.utcnow(), f"{type(e).__name__}: {e}"[:500]
        return True
    with session_scope() as s:
        rep = s.get(KeysReport, app_id)
        rep.status, rep.finished_at, rep.result, rep.progress = "done", datetime.utcnow(), result, {}
    log.info("ключи игры %s: готово, фраз %d, в топ-10 по %d",
             app_id, result["summary"]["terms"], result["summary"]["ranked_top10"])
    return True
