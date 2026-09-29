"""Why a game grows, and how we found it: the analytics block of the game page.

Google does not disclose where installs come from, so each growth driver is an estimate built
from what we observe: search positions x demand, chart presence, jumps in the install curve and
what happened around them (an update, a chart entry, nothing visible in the store), publisher
signals typical of paid user acquisition, and similar young games growing at the same time.

Reads the database only - the web API must never talk to Google.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from playtrend.models import App, ChartDaily, DiscoveryEvent, GameMetrics, KeywordRank, SimilarLink
from playtrend.pipeline.metrics import change_points, rank_weight, velocity

SPIKE_RATIO = 2.5          # a segment this many times faster than the ones before it is a jump
SPIKE_MIN_RATE = 1000      # installs/day; smaller jumps are noise
UPDATE_EFFECT = 1.5        # velocity after/before an update that counts as "the update worked"
STUDIO_AUDIENCE = 5_000_000  # installs across the studio's other games: enough to cross-promote
TOP_PLACES = 20           # chart places that bring installs by themselves
WAVE_MAX_AGE = 180
WAVE_MIN_TREND = 40
MIN_GENRE_SAMPLE = 20

LEVELS = {3: "сильный", 2: "заметный", 1: "слабый", 0: "не видно"}
DRIVER_NAMES = {
    "search": "поиск в Google Play", "charts": "чарты", "external": "трафик извне стора",
    "paid": "закупка трафика", "wave": "волна похожих игр", "updates": "обновления",
}


def fmt_n(v: float | None) -> str:
    if v is None:
        return "—"
    v = float(v)
    for div, unit in ((1e6, " млн"), (1e3, " тыс.")):
        if abs(v) >= div:
            return f"{v / div:.1f}".rstrip("0").rstrip(".").replace(".", ",") + unit
    return str(int(round(v)))


def fmt_f(v: float) -> str:
    return f"{v:.1f}".replace(".", ",")


def plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    return few if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else many


def fmt_d(d: date) -> str:
    return d.strftime("%d.%m")


# ----------------------------- install curve -----------------------------

def detect_updates(series: list[tuple[date, str | None]]) -> list[tuple[date, str]]:
    """Days the version changed. The first version we saw is not an update we witnessed."""
    out, prev = [], None
    for d, v in series:
        if not v or v.lower().startswith("varies"):
            continue
        if prev is not None and v != prev:
            out.append((d, v))
        prev = v
    return out


def update_effects(points: list[tuple[date, int]], updates: list[tuple[date, str]]) -> list[dict]:
    """Velocity for the week before vs the week after each update."""
    last = points[-1][0] if points else None
    out = []
    for d, v in updates:
        before = velocity(points, d, 7)
        after = velocity(points, min(d + timedelta(days=7), last), 7) if last and last >= d + timedelta(days=4) else None
        ratio = round(after / before, 2) if after is not None and before else None
        out.append({"date": d, "version": v, "before": before, "after": after, "ratio": ratio})
    return out


def detect_spikes(points: list[tuple[date, int]], chart_counts: dict[date, int],
                  updates: list[tuple[date, str]]) -> list[dict]:
    """Jumps in the install rate, and what the store shows around them."""
    segs = [(d0, d1, (v1 - v0) / (d1 - d0).days)
            for (d0, v0), (d1, v1) in zip(points, points[1:]) if (d1 - d0).days > 0]
    chart_days = sorted(chart_counts)
    out: list[dict] = []
    for i, (d0, d1, rate) in enumerate(segs):
        prev = [r for _, _, r in segs[max(0, i - 4):i]]
        if len(prev) < 2:
            continue
        base = median(prev)
        if rate < SPIKE_MIN_RATE or base <= 0 or rate < SPIKE_RATIO * base:
            continue
        if out and out[-1]["end"] == d0:           # a jump spread over two counter updates
            out[-1].update(end=d1, rate=max(out[-1]["rate"], round(rate)))
            continue
        before = [chart_counts[d] for d in chart_days if d < d0]
        during = [chart_counts[d] for d in chart_days if d0 <= d <= d1]
        chart_jump = (max(during) if during else 0) - (before[-1] if before else 0)
        upd = [v for d, v in updates if d0 - timedelta(days=3) <= d <= d1]
        spike = {"start": d0, "end": d1, "rate": round(rate), "base": round(base), "ratio": round(rate / base, 1)}
        if upd:
            spike.update(cause="update", version=upd[-1])
        elif chart_jump >= 3:
            spike.update(cause="charts", countries=chart_jump)
        else:
            spike["cause"] = "external"
        out.append(spike)
    return out


# ----------------------------- drivers -----------------------------

@dataclass
class Inputs:
    v7: float | None = None
    installs: int | None = None
    age: int | None = None
    search_visibility: float = 0
    keyword_hits: list[dict] = field(default_factory=list)   # {id, term, country, demand, rank}
    charts_now: dict[str, dict] = field(default_factory=dict)  # collection -> {n, best_rank, best_country}
    chart_peak: tuple[date, int] | None = None
    breadth_delta7: int = 0
    flags: list[str] = field(default_factory=list)
    soft_launch: bool = False
    ratings_per_k: float | None = None
    genre_ratings_per_k: float | None = None
    spikes: list[dict] = field(default_factory=list)
    effects: list[dict] = field(default_factory=list)
    versions_seen: int = 0
    studio_games: int = 0                    # the studio's other games we know
    studio_installs: int = 0
    studio_ratings_per_k: float | None = None
    neighbours: list[dict] = field(default_factory=list)       # growing young games nearby


def driver(key: str, level: int, evidence: list[str], **extra) -> dict:
    return {"key": key, "name": DRIVER_NAMES[key], "level": level, "level_label": LEVELS[level],
            "evidence": evidence, **extra}


def search_driver(x: Inputs) -> dict:
    hits = sorted((h for h in x.keyword_hits if h["rank"] <= 10),
                  key=lambda h: -(h["demand"] or 0) * rank_weight(h["rank"]))
    strong = any((h["demand"] or 0) >= 60 and h["rank"] <= 3 for h in hits)
    medium = any((h["demand"] or 0) >= 40 and h["rank"] <= 5 for h in hits)
    level = (3 if x.search_visibility >= 60 or strong else 2 if x.search_visibility >= 30 or medium
             else 1 if any((h["demand"] or 0) >= 20 for h in hits) else 0)
    by_term: dict[str, list[dict]] = {}
    for h in hits:
        by_term.setdefault(h["term"], []).append(h)
    ev = [f"«{term}» — " + ", ".join(f"#{h['rank']} {h['country'].upper()}" for h in hs[:4])
          + f", спрос {round(max(h['demand'] or 0 for h in hs))}" for term, hs in list(by_term.items())[:5]]
    if not hits:
        ev.append("В топ-10 по известным нам запросам не попадает")
    return driver("search", level, ev, keywords=hits[:8])


def charts_driver(x: Inputs) -> dict:
    # Installs come from high places: #150 in a dozen countries brings little. Movers & Shakers
    # lists games that already grow fast - a consequence of growth more than its source.
    main = [x.charts_now[c] for c in ("top_new_free", "top_free") if c in x.charts_now]
    n = sum(c["n"] for c in main)
    ranks: dict[str, int] = {}
    for c in main:
        for cc, r in (c.get("countries") or {}).items():
            ranks[cc] = min(r, ranks.get(cc, r))
    top20 = sum(1 for r in ranks.values() if r <= TOP_PLACES)
    best = min((c["best_rank"] for c in main if c.get("best_rank")), default=None)
    trending = x.charts_now.get("trending", {}).get("n", 0)
    level = (3 if top20 >= 10 or (best and best <= 3) else 2 if top20 >= 3 or (best and best <= 10)
             else 1 if n or trending else 0)
    labels = {"top_new_free": "Top New Free", "top_free": "Top Free", "trending": "Movers & Shakers",
              "top_grossing": "Top Grossing"}
    ev = [f"{labels.get(k, k)}: {c['n']} {plural(c['n'], 'страна', 'страны', 'стран')}, "
          f"лучшее место #{c['best_rank']} ({(c.get('best_country') or '').upper()})"
          for k, c in x.charts_now.items() if c["n"]]
    if top20:
        ev.append(f"В топ-{TOP_PLACES} Top Free / Top New Free: {top20} {plural(top20, 'страна', 'страны', 'стран')}")
    elif n or trending:
        ev.append("Высоких мест нет: Movers & Shakers и нижняя часть чартов — скорее следствие роста, чем его источник")
    if x.breadth_delta7:
        d = x.breadth_delta7
        ev.append(f"За неделю {'+' if d > 0 else ''}{d} {plural(d, 'страна', 'страны', 'стран')} в чартах")
    if x.chart_peak and x.chart_peak[1] > n:
        ev.append(f"Пик: {x.chart_peak[1]} {plural(x.chart_peak[1], 'страна', 'страны', 'стран')} ({fmt_d(x.chart_peak[0])})")
        level = max(level, 1)
    if not ev:
        ev.append("В чартах не замечена")
    return driver("charts", level, ev)


def external_driver(x: Inputs, search_level: int, charts_level: int) -> dict:
    v = x.v7 or 0
    ev, level = [], 0
    if v >= 1000 and search_level <= 1 and charts_level <= 1:
        level = 3 if v >= 5000 else 2
        ev.append(f"Растёт на {fmt_n(v)}/день, но почти не видна в поиске и чартах: установки приходят "
                  "из рекламы, соцсетей (TikTok, YouTube) или подборок Google")
    unexplained = [s for s in x.spikes if s["cause"] == "external"]
    for s in unexplained[-3:]:
        ev.append(f"{fmt_d(s['start'])}–{fmt_d(s['end'])}: скачок до {fmt_n(s['rate'])}/день (×{s['ratio']:g} к обычному), "
                  "в сторе причины не видно")
    if unexplained:
        level = max(level, 2 if max(s["ratio"] for s in unexplained) >= 4 else 1)
    return driver("external", level, ev)


def paid_driver(x: Inputs) -> dict:
    points, ev = 0, []
    if "hc_publisher" in x.flags:
        points += 2
        ev.append("Паблишер гиперказуала: такие игры растут на закупке рекламы")
    if "big_portfolio" in x.flags:
        points += 1
        ev.append("У студии 40+ игр: конвейер тестов под закупку")
    if "big_dev" in x.flags:
        points += 1
        ev.append("У студии уже есть хит 50M+: есть бюджет и опыт закупки")
    if x.studio_installs >= STUDIO_AUDIENCE:
        points += 1
        low = (x.studio_ratings_per_k is not None and x.genre_ratings_per_k
               and x.studio_ratings_per_k < 0.5 * x.genre_ratings_per_k)
        ev.append(f"У студии ещё {x.studio_games} {plural(x.studio_games, 'игра', 'игры', 'игр')} на {fmt_n(x.studio_installs)} "
                  "установок: своя аудитория, которую можно перегонять рекламой из игры в игру"
                  + (f"; и у них тоже мало оценок ({fmt_f(x.studio_ratings_per_k)} на 1000) — модель «купить трафик "
                     "дёшево, заработать на рекламе»" if low else ""))
    if x.soft_launch:
        points += 1
        ev.append("Прошла софт-лонч: так проверяют метрики перед масштабированием закупки")
    if (x.ratings_per_k is not None and x.genre_ratings_per_k and (x.installs or 0) >= 50_000
            and x.ratings_per_k < 0.5 * x.genre_ratings_per_k):
        times = x.genre_ratings_per_k / max(x.ratings_per_k, 0.01)
        points += 2 if times >= 5 else 1
        ev.append(f"Оценок на 1000 установок {fmt_f(x.ratings_per_k)} при медиане жанра {fmt_f(x.genre_ratings_per_k)}"
                  f" (в {round(times)} раз меньше): много случайных игроков, типично для рекламного трафика")
    return driver("paid", min(3, points), ev)


def updates_driver(x: Inputs) -> dict:
    worked = [e for e in x.effects if e["ratio"] and e["ratio"] >= UPDATE_EFFECT]
    level = 3 if any(e["ratio"] >= 2.5 for e in worked) else 2 if worked else 0
    ev = [f"После {e['version']} ({fmt_d(e['date'])}) скорость ×{e['ratio']:g}: {fmt_n(e['before'])} → {fmt_n(e['after'])}/день"
          for e in worked]
    for s in x.spikes:
        if s["cause"] == "update" and not any(e["version"] == s["version"] for e in worked):
            ev.append(f"Скачок до {fmt_n(s['rate'])}/день рядом с обновлением {s['version']} ({fmt_d(s['start'])})")
            level = max(level, 2)
    if not ev:
        ev.append(f"Обновлений при нас: {len(x.effects)}, заметного влияния на скорость нет" if x.effects
                  else "История версий копится" if x.versions_seen < 7 else "Обновлений при нас не было")
    return driver("updates", level, ev)


def wave_driver(x: Inputs) -> dict:
    n = len(x.neighbours)
    level = 3 if n >= 5 else 2 if n >= 2 else 1 if n else 0
    ev = [f"Рядом {plural(n, 'растёт', 'растут', 'растут')} ещё {n} {plural(n, 'молодая игра', 'молодые игры', 'молодых игр')}: "
          "похожие по Google и конкуренты по тем же запросам"] if n else \
         ["Похожие игры сейчас не растут: игра выделяется одна"]
    return driver("wave", level, ev, apps=x.neighbours[:8])


def growth_drivers(x: Inputs) -> dict:
    search = search_driver(x)
    charts = charts_driver(x)
    drivers = [search, charts, external_driver(x, search["level"], charts["level"]), paid_driver(x),
               updates_driver(x), wave_driver(x)]
    order = list(DRIVER_NAMES)
    drivers.sort(key=lambda d: (-d["level"], order.index(d["key"])))
    main = [d["name"] for d in drivers if d["level"] >= 2]
    if x.v7 is None and not x.installs:
        verdict = "Данных о росте пока мало."
    elif main:
        verdict = "Главное: " + ", ".join(main[:3]) + "."
    elif (x.v7 or 0) < 300:
        verdict = "Рост слабый, явного драйвера нет."
    else:
        verdict = "Явного драйвера не видно: соберите ключи игры, чтобы проверить поиск."
    return {"verdict": verdict, "drivers": drivers}


# ----------------------------- loading -----------------------------

def genre_ratings_per_k(db: Session, genre_id: str | None) -> float | None:
    """Median ratings per 1000 installs among tracked games of the genre."""
    if not genre_id:
        return None
    rows = db.execute(select(App.ratings, App.real_installs).join(GameMetrics, GameMetrics.app_id == App.app_id)
                      .where(App.genre_id == genre_id, App.real_installs >= 10_000, App.ratings.is_not(None))).all()
    rates = [r * 1000 / i for r, i in rows if i]
    return round(median(rates), 2) if len(rates) >= MIN_GENRE_SAMPLE else None


def neighbours(db: Session, app: App, keyword_ids: list[int]) -> list[dict]:
    """Young games growing right now next to this one: Google's similar lists (both ways) and
    rivals in the top 10 of the same searches. Same studio does not count."""
    ids = set(db.scalars(select(SimilarLink.similar_id).where(SimilarLink.app_id == app.app_id)))
    ids |= set(db.scalars(select(SimilarLink.app_id).where(SimilarLink.similar_id == app.app_id)))
    if keyword_ids:
        ids |= set(db.scalars(select(KeywordRank.app_id).where(KeywordRank.keyword_id.in_(keyword_ids),
                                                               KeywordRank.rank <= 10)))
    ids.discard(app.app_id)
    if not ids:
        return []
    rows = db.execute(select(App, GameMetrics).join(GameMetrics, GameMetrics.app_id == App.app_id).where(
        App.app_id.in_(ids), GameMetrics.age_days <= WAVE_MAX_AGE, GameMetrics.trend_score >= WAVE_MIN_TREND,
        or_(App.developer_id.is_(None), App.developer_id != (app.developer_id or "")),
        GameMetrics.flag_major.is_(False), GameMetrics.flag_franchise.is_(False),
    ).order_by(GameMetrics.trend_score.desc()).limit(20)).all()
    return [{"app_id": a.app_id, "title": a.title, "icon_url": a.icon_url, "trend_score": m.trend_score,
             "v7": m.v7, "age_days": m.age_days} for a, m in rows]


def timeline(db: Session, app: App, updates: list[dict], spikes: list[dict]) -> list[dict]:
    events = db.scalars(select(DiscoveryEvent).where(DiscoveryEvent.app_id == app.app_id)).all()
    parents = {e.detail.get("parent") for e in events if e.source == "similar" and e.detail}
    titles = dict(db.execute(select(App.app_id, App.title).where(App.app_id.in_(parents))).all()) if parents else {}
    items: list[dict] = []
    if app.released:
        items.append({"date": app.released, "kind": "release", "soft_launch": app.soft_launch_markets or []})
    for e in events:
        detail = dict(e.detail or {})
        if detail.get("parent"):
            detail["parent_title"] = titles.get(detail["parent"])
        items.append({"date": e.date, "kind": "found", "source": e.source, "first": e.first, "detail": detail})
    if not any(e.first for e in events) and app.first_seen:
        items.append({"date": app.first_seen.date(), "kind": "found", "source": app.discovered_via or "unknown",
                      "first": True, "detail": {}})
    for u in updates:
        items.append({"date": u["date"], "kind": "update", "version": u["version"], "ratio": u["ratio"],
                      "before": u["before"], "after": u["after"]})
    for s in spikes:
        items.append({"date": s["start"], "kind": "spike", **s})
    order = {"release": 0, "found": 1, "update": 2, "spike": 3}
    items.sort(key=lambda i: (i["date"], order[i["kind"]], not i.get("first", False)))
    return items


def analyze(db: Session, app: App, m: GameMetrics | None, snaps: list, chart_rows: list,
            keyword_hits: list[dict], genre_rate: float | None) -> dict:
    """snaps: Snapshot rows by date; chart_rows: ChartDaily rows by date; keyword_hits: the game's ranks."""
    points = change_points([(s.date, s.real_installs) for s in snaps])
    updates = detect_updates([(s.date, s.version) for s in snaps])
    chart_counts: dict[date, int] = {}
    for c in chart_rows:
        if c.collection in ("top_new_free", "top_free", "trending"):
            chart_counts[c.date] = chart_counts.get(c.date, 0) + c.n_countries
    main_counts: dict[date, int] = {}
    for c in chart_rows:
        if c.collection in ("top_new_free", "top_free"):
            main_counts[c.date] = main_counts.get(c.date, 0) + c.n_countries
    # "Now" is the latest chart scan overall: a game that dropped out has no row that day
    latest = db.scalar(select(func.max(ChartDaily.date)))
    charts_now = {c.collection: {"n": c.n_countries, "best_rank": c.best_rank, "best_country": c.best_country,
                                 "countries": c.countries or {}}
                  for c in chart_rows if c.date == latest}
    peak = max(main_counts.items(), key=lambda kv: (kv[1], kv[0]), default=None)

    effects = update_effects(points, updates)
    spikes = detect_spikes(points, chart_counts, updates)
    ratings_per_k = round(app.ratings * 1000 / app.real_installs, 2) \
        if app.ratings is not None and app.real_installs and not app.pre_register else None
    studio = (0, 0, 0)
    if app.developer_id:
        studio = db.execute(select(func.count(), func.coalesce(func.sum(App.real_installs), 0),
                                   func.coalesce(func.sum(App.ratings), 0))
                            .where(App.developer_id == app.developer_id, App.app_id != app.app_id,
                                   App.real_installs > 0, App.pre_register.is_(False))).one()
    x = Inputs(
        v7=m.v7 if m else None, installs=app.real_installs, age=m.age_days if m else None,
        search_visibility=m.search_visibility if m else 0, keyword_hits=keyword_hits,
        charts_now=charts_now, chart_peak=peak, breadth_delta7=m.breadth_delta7 if m else 0,
        flags=list(m.brand_flags or []) if m else [], soft_launch=bool(app.soft_launch),
        ratings_per_k=ratings_per_k, genre_ratings_per_k=genre_rate, spikes=spikes, effects=effects,
        versions_seen=sum(1 for s in snaps if s.version),
        studio_games=studio[0], studio_installs=int(studio[1]),
        studio_ratings_per_k=round(studio[2] * 1000 / studio[1], 2) if studio[1] else None,
        neighbours=neighbours(db, app, [h["id"] for h in keyword_hits if h["rank"] <= 10 and (h["demand"] or 0) >= 20]),
    )
    out = growth_drivers(x)

    facts = []
    if ratings_per_k is not None:
        facts.append(f"Оценок на 1000 установок: {fmt_f(ratings_per_k)}"
                     + (f" (медиана жанра {fmt_f(genre_rate)})" if genre_rate else ""))
    monet = [w for w, on in (("реклама", app.contains_ads), ("покупки в игре", app.offers_iap)) if on]
    facts.append("Монетизация: " + (" + ".join(monet) if monet else "без рекламы и покупок"))
    if app.last_updated:
        facts.append(f"Последнее обновление: {app.last_updated.strftime('%d.%m.%Y')}")
    if app.released and app.first_seen and not app.pre_register:
        lag = (app.first_seen.date() - app.released).days
        if lag >= 0:
            facts.append("Заметили в день релиза" if lag == 0 else f"Заметили через {lag} дн. после релиза")
    out.update(facts=facts, spikes=spikes, updates=effects, timeline=timeline(db, app, effects, spikes))
    return out
