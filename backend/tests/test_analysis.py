from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from playtrend import analysis
from playtrend.api.main import app as api_app
from playtrend.db import session_scope
from playtrend.models import App, ChartDaily, DiscoveryEvent, Keyword, KeywordRank, KeysReport, SimilarLink, Snapshot
from playtrend.pipeline import app_keys, charts, details, discovery, metrics

from test_api import TODAY, add_game, client  # noqa: F401  (fixture)

D = date(2026, 9, 1)


def pts(*values, step=1):
    return [(D + timedelta(days=i * step), v) for i, v in enumerate(values)]


# ----------------------------- install curve -----------------------------

def test_updates_are_version_changes_after_the_first_reading():
    series = [(D, "1.0"), (D + timedelta(1), "1.0"), (D + timedelta(2), None), (D + timedelta(3), "1.1"),
              (D + timedelta(4), "Varies with device"), (D + timedelta(5), "1.2")]
    assert analysis.detect_updates(series) == [(D + timedelta(3), "1.1"), (D + timedelta(5), "1.2")]


def test_spike_causes():
    curve = pts(0, 1000, 2000, 3000, 13000, 14000)          # +1000/day, then +10000 in a day
    upd = [(D + timedelta(3), "2.0")]
    assert analysis.detect_spikes(curve, {}, upd)[0]["cause"] == "update"
    charts_jump = {D + timedelta(2): 1, D + timedelta(4): 9}
    s = analysis.detect_spikes(curve, charts_jump, [])[0]
    assert s["cause"] == "charts" and s["countries"] == 8
    s = analysis.detect_spikes(curve, {}, [])[0]
    assert s["cause"] == "external" and s["ratio"] == 10 and s["rate"] == 10000
    # small absolute jumps are noise
    assert analysis.detect_spikes(pts(0, 10, 20, 30, 300), {}, []) == []


def test_update_effect_compares_weeks_around_the_update():
    curve = pts(*[i * 1000 for i in range(8)], *[7000 + i * 3000 for i in range(1, 9)])
    eff = analysis.update_effects(curve, [(D + timedelta(7), "3.0")])[0]
    assert eff["before"] == 1000 and eff["after"] == 3000 and eff["ratio"] == 3
    # too early to judge
    assert analysis.update_effects(curve, [(D + timedelta(14), "3.1")])[0]["ratio"] is None


# ----------------------------- drivers -----------------------------

def test_invisible_fast_growth_points_outside_the_store():
    r = analysis.growth_drivers(analysis.Inputs(v7=8000, installs=300_000, flags=["hc_publisher"]))
    top = r["drivers"][0]
    assert top["key"] == "external" and top["level"] == 3
    assert "трафик извне стора" in r["verdict"] and "закупка трафика" in r["verdict"]


def test_search_and_charts_drivers():
    hits = [{"id": 1, "term": "screw sort", "country": "us", "demand": 80, "rank": 2},
            {"id": 2, "term": "nuts", "country": "br", "demand": 30, "rank": 25}]
    x = analysis.Inputs(v7=20000, installs=900_000, search_visibility=45, keyword_hits=hits,
                        charts_now={"top_new_free": {"n": 20, "best_rank": 4, "best_country": "br",
                                                     "countries": {f"c{i}": 4 + i for i in range(20)}}})
    r = analysis.growth_drivers(x)
    levels = {d["key"]: d["level"] for d in r["drivers"]}
    assert levels["search"] == 3 and levels["charts"] == 3 and levels["external"] == 0
    search = next(d for d in r["drivers"] if d["key"] == "search")
    assert [k["term"] for k in search["keywords"]] == ["screw sort"]
    assert r["verdict"].startswith("Главное: поиск в Google Play, чарты")


def test_russian_plurals():
    assert [analysis.plural(n, "страна", "страны", "стран") for n in (1, 3, 5, 11, 21, 22, 112)] ==         ["страна", "страны", "стран", "стран", "страна", "страны", "стран"]


def test_low_chart_places_do_not_explain_growth():
    """1.2M installs in 6 weeks, Movers & Shakers in 21 countries, Top Free only #51 and lower,
    not in any search top-30, 17x fewer ratings than the genre: the installs come from ads."""
    x = analysis.Inputs(v7=28000, installs=1_200_000, ratings_per_k=0.2, genre_ratings_per_k=3.4, charts_now={
        "trending": {"n": 21, "best_rank": 4, "best_country": "gr", "countries": {"gr": 4, "fr": 11}},
        "top_free": {"n": 18, "best_rank": 51, "best_country": "ec", "countries": {"ec": 51, "ar": 57}}})
    r = analysis.growth_drivers(x)
    levels = {d["key"]: d["level"] for d in r["drivers"]}
    assert levels["charts"] == 1 and levels["external"] == 3 and levels["paid"] == 2
    assert r["verdict"] == "Главное: трафик извне стора, закупка трафика."
    x.studio_games, x.studio_installs, x.studio_ratings_per_k = 9, 27_000_000, 0.9
    paid = analysis.paid_driver(x)
    assert paid["level"] == 3 and any("ещё 9 игр на 27 млн" in e and "дёшево" in e for e in paid["evidence"])


def test_developer_page_keeps_form_encoded_ids(monkeypatch):
    from playtrend.play import client as play
    urls = []
    monkeypatch.setattr(play, "_links", lambda url: urls.append(url) or [])
    play.developer_ids("Happy+Run")
    play.developer_ids("A&B Games")
    play.developer_ids("5700313618786177705")
    assert urls[0].endswith("developer?id=Happy+Run&hl=en&gl=us")
    assert "id=A%26B%20Games" in urls[1] and "/dev?id=5700313618786177705" in urls[2]


def test_low_ratings_rate_is_a_paid_signal():
    x = analysis.Inputs(v7=3000, installs=200_000, ratings_per_k=1.0, genre_ratings_per_k=6.0)
    paid = analysis.paid_driver(x)
    assert paid["level"] == 2 and "медиане жанра 6,0 (в 6 раз меньше)" in paid["evidence"][0]
    x.ratings_per_k = 2.5
    assert analysis.paid_driver(x)["level"] == 1
    assert analysis.paid_driver(analysis.Inputs(installs=200_000, ratings_per_k=5.0, genre_ratings_per_k=6.0))["level"] == 0


# ----------------------------- discovery -----------------------------

def test_stubs_and_charts_record_how_a_game_was_found(monkeypatch):
    details.add_stubs(["new.one", "new.two"], "similar", {"new.one": {"parent": "hit.game"}})
    details.add_stubs(["new.one"], "developer", {"new.one": {"developer_id": "x"}})   # known: no new event
    monkeypatch.setattr(charts.client, "charts", lambda coll, cat, cc, n: [
        {"app_id": "new.one", "title": "One", "developer": "Dev", "rank": 5 if cc == "br" else 40},
        {"app_id": "fresh.chart", "title": "Fresh", "developer": "Dev", "rank": 1}])
    charts.run(countries=["us", "br"], categories=["GAME"], collections={"top_new_free": "x"})
    charts.run(countries=["us"], categories=["GAME"], collections={"top_new_free": "x"})   # first date kept
    with session_scope() as s:
        ev = {(e.app_id, e.source): e for e in s.scalars(select(DiscoveryEvent))}
    assert set(ev) == {("new.one", "similar"), ("new.two", "similar"), ("new.one", "chart:top_new_free"),
                       ("fresh.chart", "chart:top_new_free")}
    assert ev[("new.one", "similar")].first and ev[("new.one", "similar")].detail == {"parent": "hit.game"}
    chart = ev[("new.one", "chart:top_new_free")]
    assert not chart.first and chart.detail == {"country": "br", "rank": 5, "category": "GAME", "countries": 2}
    assert ev[("fresh.chart", "chart:top_new_free")].first


def test_backfill_from_existing_history():
    add_game("old.hit", "Old Hit", "Dev", 30, [1000, 2000])
    with session_scope() as s:
        s.get(App, "old.hit").discovered_via = "chart:top_free"
        s.get(App, "old.hit").first_seen = datetime(2026, 8, 1)
        s.add(ChartDaily(app_id="old.hit", date=D, collection="top_free", n_countries=3, best_rank=7,
                         best_country="de", best_category="GAME_PUZZLE", countries={}))
        s.add(ChartDaily(app_id="old.hit", date=D + timedelta(3), collection="top_free", n_countries=9,
                         best_rank=2, best_country="us", best_category="GAME", countries={}))
    assert discovery.backfill() == 1
    assert discovery.backfill() == 0      # only once
    with session_scope() as s:
        e = s.get(DiscoveryEvent, ("old.hit", "chart:top_free"))
        assert e.first and e.date == D and e.detail["country"] == "de"


# ----------------------------- keys (reverse ASO) -----------------------------

def test_candidate_phrases_prefer_title_and_skip_stopwords():
    got = app_keys.candidates("Screw Sort: Nuts & Bolts", "Sort the screws in this relaxing puzzle!",
                              "Screw puzzle fans love it. Screw puzzle levels. Relaxing screw puzzle for you.",
                              "en", 12)
    terms = dict(got)
    assert terms["screw sort"] == "title" and terms["screw puzzle"] == "description"
    assert not any(t.split()[0] in app_keys.STOPWORDS["en"] or t.split()[-1] in app_keys.STOPWORDS["en"]
                   for t in terms)
    assert app_keys.occurrences("screw puzzle", "Screw puzzle! screw puzzles, a screw puzzle") == 2


def test_demand_from_the_shortest_prefix(monkeypatch):
    calls = []

    def suggest(q, lang, cc):
        calls.append(q)
        return ["screw sort 3d"] if q in ("scre", "screw sort 3d") else []
    monkeypatch.setattr(app_keys.client, "suggest", suggest)
    d, plen, pos = app_keys.measure_demand("screw sort 3d", "en", "us")
    assert plen == 4 and pos == 1 and d > 50 and calls == ["sc", "scre"]
    assert app_keys.measure_demand("nobody types this", "en", "us") == (0.0, None, None)


def fake_store(monkeypatch):
    listings = {
        "en": {"title": "Screw Sort: Nuts Puzzle", "summary": "Relaxing screw puzzle",
               "description": "Screw puzzle with nuts. Screw puzzle again. Nuts and bolts sorting."},
        "ru": {"title": "Винты: головоломка", "summary": "Сортировка винтов",
               "description": "Головоломка с винтами. Головоломка с гайками."},
    }

    def listing(app_id, lang, cc):
        if lang == "ja":
            raise app_keys.NotFound(cc)
        return listings.get(lang, listings["en"])

    def suggest(q, lang, cc):
        return {"screw sort": ["screw sort", "screw sort 3d"], "screw puzzle": ["screw puzzle"],
                "sc": ["screw puzzle"]}.get(q, [q] if len(q) > 6 else [])

    def search(term, lang, cc, n):
        ids = ["rival.game", "my.game"] if "screw" in term else ["rival.game"]
        return [{"app_id": a, "title": a, "developer": "d", "genre": "Puzzle", "score": 4.5, "min_installs": 1000,
                 "rank": i} for i, a in enumerate(ids, 1)]
    monkeypatch.setattr(app_keys.client, "listing", listing)
    monkeypatch.setattr(app_keys.client, "suggest", suggest)
    monkeypatch.setattr(app_keys.client, "search", search)


def test_keys_popular_markets(client):  # noqa: F811
    """Countries join the keys report by estimated downloads: store size x chart place, over two weeks."""
    add_game("pop.game", "Pop", "Tiny", 20, [i * 20_000 for i in range(1, 16)])
    with session_scope() as s:
        for d in range(7):
            s.add(ChartDaily(app_id="pop.game", date=TODAY - timedelta(days=d), collection="top_free", n_countries=6,
                             countries={"pe": 1, "co": 5, "ar": 6, "cl": 3, "in": 40, "hu": 2}))
        s.add(ChartDaily(app_id="pop.game", date=TODAY, collection="trending", n_countries=2,
                         countries={"de": 190, "pe": 4}))
        s.add(ChartDaily(app_id="pop.game", date=TODAY - timedelta(days=30), collection="top_free", n_countries=1,
                         countries={"fr": 1}))             # a month ago: outside the window
        pop = app_keys.popularity(s, "pop.game")
    assert "fr" not in pop and {k: pop["pe"][k] for k in ("rank", "collection", "days")} == {"rank": 1, "collection": "top_free", "days": 7}
    assert pop["in"]["score"] > pop["hu"]["score"]           # #40 in India brings more players than #2 in Hungary
    picked = [m.country for m in app_keys.popular_markets(pop)]
    assert picked[:2] == ["in", "pe"] and "co" in picked and len([c for c in picked if c in ("pe", "co", "ar", "cl")]) == 2
    assert "de" not in picked                                 # one day at #190 in movers is noise


def test_keys_report_end_to_end(client, monkeypatch):  # noqa: F811
    fake_store(monkeypatch)
    add_game("my.game", "Screw Sort", "Tiny", 20, [i * 20_000 for i in range(1, 16)],
             charts={"top_free": 2})    # add_game puts it at #3 in the US, already a keyword market
    with session_scope() as s:
        s.add(ChartDaily(app_id="my.game", date=TODAY, collection="trending", n_countries=1, best_rank=2,
                         best_country="gb", countries={"gb": 2}))
    anon = TestClient(api_app)
    assert client.get("/api/games/my.game/keys").json() == {"status": None}
    r = anon.post("/api/games/my.game/keys").json()          # guests may order a report too
    assert r["status"] == "pending" and r["queue_ahead"] == 0
    assert client.post("/api/games/my.game/keys").json()["status"] == "pending"   # already queued

    assert app_keys.process_next() is True
    assert app_keys.process_next() is False
    rep = anon.get("/api/games/my.game/keys").json()
    assert rep["status"] == "done", rep["error"]
    markets = {m["country"]: m for m in rep["result"]["markets"]}
    assert markets["jp"]["available"] is False
    assert markets["mx"]["localized"] is False          # English listing served in Mexico
    assert markets["gb"]["label"].startswith("en · GB") and markets["gb"]["localized"]   # a chart country
    assert markets["gb"]["popular"] == {"rank": 2, "collection": "trending", "days": 1}
    assert [m["country"] for m in rep["result"]["markets"]][:2] == ["us", "gb"]   # tabs follow the players
    us = {t["term"]: t for t in markets["us"]["terms"]}
    assert us["screw sort"]["rank"] == 2 and us["screw sort"]["in_title"] and us["screw sort"]["demand"] == 15 and us["screw sort 3d"]["source"] == "suggest"
    assert us["screw puzzle"]["demand"] > 80            # suggested after two letters
    assert us["screw sort"]["top"][0]["app_id"] == "rival.game"
    assert rep["result"]["summary"]["ranked_top10"] >= 2
    assert any(t["term"].startswith("головоломк") or "винт" in t["term"] for t in markets["ru"]["terms"])

    # the phrases joined the shared keyword tables and feed the game page
    with session_scope() as s:
        kw = s.scalar(select(Keyword).where(Keyword.term == "screw sort", Keyword.country == "us"))
        assert kw.seed == "игра: Screw Sort" and kw.analyzed_at is not None
        assert s.get(KeywordRank, (kw.id, "my.game")).rank == 2
    d = client.get("/api/games/my.game").json()
    assert any(k["term"] == "screw sort" for k in d["keywords"])
    search = next(x for x in d["analysis"]["drivers"] if x["key"] == "search")
    assert search["keywords"]

    # a fresh report is not rebuilt for regular users; superadmins may force it
    with session_scope() as s:
        s.get(KeysReport, "my.game").finished_at = datetime.utcnow() - timedelta(hours=1)
    from playtrend.models import User
    with session_scope() as s:
        s.scalar(select(User)).is_superadmin = False
    assert client.post("/api/games/my.game/keys").status_code == 409


def test_keys_requests_are_limited_per_ip():
    from playtrend.api import ratelimit
    for i in range(5):
        assert ratelimit.check("1.2.3.4", f"/api/games/g{i}/keys", "POST", now=100) is None
    assert ratelimit.check("1.2.3.4", "/api/games/g9/keys", "POST", now=100) > 0
    assert ratelimit.check("1.2.3.4", "/api/games/g9/mark", "PUT", now=100) is None
    assert ratelimit.check("1.2.3.4", "/api/games/g9/keys", "GET", now=100) is None


def test_game_page_analysis_and_timeline(client):  # noqa: F811
    add_game("hit.game", "Meow Sort", "Tiny", 20, [i * 20_000 for i in range(1, 16)],
             charts={"top_new_free": 12})
    add_game("wave.game", "Meow Merge", "Other", 30, [i * 30_000 for i in range(1, 16)])
    with session_scope() as s:
        s.add(DiscoveryEvent(app_id="hit.game", source="similar", date=TODAY - timedelta(days=10),
                             detail={"parent": "wave.game"}, first=True))
        s.add(SimilarLink(app_id="wave.game", similar_id="hit.game", position=1, date=TODAY))
        for sn in s.scalars(select(Snapshot).where(Snapshot.app_id == "hit.game")):
            sn.version = "1.0" if sn.date < TODAY - timedelta(days=5) else "1.1"
    metrics.run(TODAY)
    a = client.get("/api/games/hit.game").json()["analysis"]
    kinds = [i["kind"] for i in a["timeline"]]
    assert kinds[0] == "release" and "update" in kinds
    found = next(i for i in a["timeline"] if i["kind"] == "found")
    assert found["detail"]["parent_title"] == "Meow Merge"
    wave = next(d for d in a["drivers"] if d["key"] == "wave")
    assert [x["app_id"] for x in wave["apps"]] == ["wave.game"]
    assert a["verdict"] and a["facts"]
