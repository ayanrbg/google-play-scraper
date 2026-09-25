import json
from datetime import date, timedelta

from gpi.pipeline import brand
from gpi.pipeline.charts import aggregate
from gpi.pipeline.keywords import competition_metrics, demand_from_observation, opportunity
from gpi.pipeline.metrics import change_points, interpolate_daily, trend_score, velocity
from gpi.play.client import normalize_details, parse_charts

D0 = date(2026, 9, 1)


def series(values):
    return [(D0 + timedelta(days=i), v) for i, v in enumerate(values)]


def test_change_points_skip_flat_and_decreases():
    pts = change_points(series([100, 100, 100, 400, 400, 390, 700]))
    assert pts == [(D0, 100), (D0 + timedelta(days=3), 400), (D0 + timedelta(days=6), 700)]


def test_velocity_is_not_fooled_by_google_lag():
    # True rate 100/day, but Google updates the counter every 3 days.
    lagged = [1000 + 100 * (i - i % 3) for i in range(15)]
    pts = change_points(series(lagged))
    v = velocity(pts, D0 + timedelta(days=14), 7)
    assert 90 <= v <= 110


def test_velocity_needs_enough_span():
    pts = change_points(series([100, 200]))
    assert velocity(pts, D0 + timedelta(days=1), 7) is None


def test_interpolation_spreads_jumps_and_marks_unknown_tail():
    pts = change_points(series([0, 0, 300, 300, 300]))
    daily = interpolate_daily(pts, D0 + timedelta(days=1), D0 + timedelta(days=4))
    assert daily[:2] == [150, 150]
    assert daily[2:] == [None, None]  # counter not refreshed yet - unknown, not zero


def test_trend_score_bounds_and_youth():
    hot, parts = trend_score(age_days=10, v7=100_000, accel=4, new_c=20, top_c=5, trending_c=5, score=4.8, ratings=5000)
    assert hot == 100.0
    cold, _ = trend_score(age_days=900, v7=10, accel=None, new_c=0, top_c=0, trending_c=0, score=3.0, ratings=10)
    assert cold < 10
    assert parts["youth"] == 15


def test_brand_classification():
    from gpi.db import session_scope
    with session_scope() as s:
        rules = brand.Rules.load(s)
    assert brand.classify("Subway Surfers City", "SYBO Games", None, None, None, rules) == ["major", "franchise"]
    assert "hc_publisher" in brand.classify("Paper.io 3", "VOODOO", None, None, None, rules)
    assert brand.classify("Meowdoku", "Oakever Games", "1", None, 3, rules) == []
    # "King" must not match inside another word
    assert brand.classify("Kingdom Clash", "Kingsoft Office", None, None, None, rules) == []
    assert brand.classify("Candy Crush Saga", "King", None, None, None, rules) == ["major", "franchise"]
    assert "big_dev" in brand.classify("New Game", "Studio", None, 80_000_000, 5, rules)


def test_demand_prefers_short_prefixes():
    assert demand_from_observation("bl", "block blast", 1) > demand_from_observation("block bl", "block blast", 1)
    assert demand_from_observation("sort puzzle", "sort puzzle", 1) == 15


def test_opportunity_rewards_young_winners():
    base = {"competition": 40, "young_share": 0.0, "young_best_installs": 0}
    young = {"competition": 40, "young_share": 0.5, "young_best_installs": 5_000_000}
    assert opportunity(80, young) > opportunity(80, base)


def test_competition_metrics_counts_brands_and_titles():
    from gpi.db import session_scope
    with session_scope() as s:
        rules = brand.Rules.load(s)
    results = [{"app_id": f"a{i}", "title": "Screw Jam" if i < 5 else "Other", "developer": "VOODOO" if i == 0 else "X",
                "score": 4.5, "min_installs": 1_000_000, "rank": i + 1} for i in range(10)]
    m = competition_metrics("screw jam", results, {}, rules, date.today())
    assert m["title_match_share"] == 0.5
    assert m["brand_share"] == 0.1
    assert m["top_median_installs"] == 1_000_000


def _chart_payload(ids):
    items = [[[[i], None, None, f"T {i}"] + [None] * 10 + [f"Dev {i}"]] for i in ids]
    data = [[None, [[None] * 28 + [[items]]]]]
    envelope = [["wrb.fr", "vyAe2", json.dumps(data)]]
    return ")]}'\n\n123\n" + json.dumps(envelope) + "\n"


def test_parse_charts():
    out = parse_charts(_chart_payload(["a.b", "c.d"]))
    assert [o["app_id"] for o in out] == ["a.b", "c.d"]
    assert out[1]["rank"] == 2 and out[0]["developer"] == "Dev a.b"


def test_aggregate_keeps_best_rank_per_country():
    res = [
        ("top_new_free", "GAME", "us", [{"app_id": "x", "title": "X", "developer": "D", "rank": 5}]),
        ("top_new_free", "GAME_PUZZLE", "us", [{"app_id": "x", "title": "X", "developer": "D", "rank": 2}]),
        ("top_new_free", "GAME", "br", [{"app_id": "x", "title": "X", "developer": "D", "rank": 9}]),
    ]
    agg, stubs = aggregate(res)
    a = agg[("x", "top_new_free")]
    assert a["countries"] == {"us": 2, "br": 9}
    assert a["best_rank"] == 2 and a["best_category"] == "GAME_PUZZLE"
    assert stubs["x"]["via"] == "chart:top_new_free"


def test_prereg_detection():
    d = normalize_details({"appId": "x", "title": "X", "genreId": "GAME_RPG", "released": None,
                           "installs": None, "realInstalls": 7839})
    assert d["pre_register"] is True and d["is_game"] is True
    d = normalize_details({"appId": "y", "title": "Y", "genreId": "TOOLS", "released": "Apr 24, 2026",
                           "installs": "10,000+", "realInstalls": 12000})
    assert d["pre_register"] is False and d["is_game"] is False and d["released"] == date(2026, 4, 24)


def test_throttling_is_counted_and_logged(caplog):
    from gpi.play import http
    route = http.Route(name="сервер", limiter=http.RateLimiter(100))
    http.reset_throttle_count()
    with caplog.at_level("WARNING", logger="gpi"):
        http._last_warned = 0.0
        http.note_throttled(route, "429", 30)
        http.note_throttled(route, "429", 30)
    assert http.throttle_count() == 2
    assert sum("ограничивает" in r.message for r in caplog.records) == 1  # one journal line a minute


def test_proxy_routes(caplog):
    from gpi.play import http
    assert http.parse_proxy("1.2.3.4:8080:user:pw") == "http://user:pw@1.2.3.4:8080"
    assert http.parse_proxy("http://u:p@h:1") == "http://u:p@h:1"
    rs = http.build_routes(2.0, ["1.2.3.4:8080:u:p", "5.6.7.8:9090:u:p", "garbage"], 0.7)
    assert [r.name for r in rs] == ["сервер", "1.2.3.4", "5.6.7.8"]
    assert "u:p@" not in rs[1].name  # credentials never end up in names/logs
    http._routes = rs
    try:
        assert http.pick(heavy=True) is rs[0]          # charts always go direct
        with caplog.at_level("WARNING", logger="gpi"):
            for _ in range(http.BENCH_AFTER_FAILS):
                rs[1].failed("ProxyError")
        assert rs[1].bench_until > 0 and "1.2.3.4" in caplog.text
        for _ in range(5):                              # benched proxy is skipped
            assert http.pick() is not rs[1]
        rs[0].failed("x"); rs[0].failed("x"); rs[0].failed("x")
        assert rs[0].bench_until == 0                   # the server itself is never benched
    finally:
        http._routes = None


def test_soft_launch_markets(monkeypatch):
    """Google hides the release date where a game was out before its global launch."""
    from gpi.play import client

    class R:
        def __init__(self, text): self.text = text

    pages = {"ph": {"released": None, "installs": "1,000,000+"},   # soft launch here
             "id": {"released": None, "installs": "1,000,000+"},
             "au": {"released": "Sep 16, 2026", "installs": "1,000,000+"},
             "nz": None}                                             # not available at all
    def fake_request(method, url, **kw):
        cc = url.rsplit("gl=", 1)[1]
        if pages[cc] is None:
            raise client.NotFound(url)
        return R(cc)
    monkeypatch.setattr(client, "request", fake_request)
    monkeypatch.setattr(client, "gps_parse_dom", lambda dom, app_id, url: pages[dom])
    assert client.soft_launch_markets("x") == ["ph", "id"]
