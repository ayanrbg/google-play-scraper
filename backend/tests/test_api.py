from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from playtrend.api.main import app
from playtrend.auth import create_user
from playtrend.db import session_scope
from playtrend.models import App, ChartDaily, Snapshot
from playtrend.pipeline import metrics

TODAY = date.today()


@pytest.fixture
def client():
    with session_scope() as s:
        create_user(s, "owner@test.io", "password123", workspace_name="Team", superadmin=True)
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": "owner@test.io", "password": "password123"})
    assert r.status_code == 200
    return c


def add_game(app_id, title, developer, age, installs_by_day, genre="GAME_PUZZLE", charts=None):
    with session_scope() as s:
        s.add(App(app_id=app_id, title=title, developer=developer, developer_id=developer, genre_id=genre,
                  released=TODAY - timedelta(days=age), tracked=True, status="active", is_game=True,
                  real_installs=installs_by_day[-1], score=4.6, ratings=1000, details_at=datetime.utcnow()))
        s.flush()
        n = len(installs_by_day)
        for i, v in enumerate(installs_by_day):
            s.add(Snapshot(app_id=app_id, date=TODAY - timedelta(days=n - 1 - i), real_installs=v, ratings=100 + i))
        for coll, n_c in (charts or {}).items():
            s.add(ChartDaily(app_id=app_id, date=TODAY, collection=coll, n_countries=n_c, best_rank=3,
                             best_country="us", countries={"us": 3}))


def seed_radar():
    add_game("indie.hit", "Meow Sort", "Tiny Studio", 20, [i * 20_000 for i in range(1, 16)],
             charts={"top_new_free": 12, "trending": 3})
    add_game("brand.game", "Subway Surfers City", "SYBO Games", 30, [i * 90_000 for i in range(1, 16)])
    add_game("slow.game", "Quiet Farm", "Solo Dev", 300, [5000 + i for i in range(15)], genre="GAME_SIMULATION")
    metrics.run(TODAY)


def test_guests_read_everything_but_change_nothing():
    seed_radar()
    anon = TestClient(app)
    assert anon.get("/api/me").status_code == 401
    r = anon.get("/api/games").json()
    assert r["items"][0]["app_id"] == "indie.hit" and r["limited_to"] is None
    d = anon.get("/api/games/indie.hit").json()
    assert d["mark"] is None and len(d["daily"]) == 14
    for path in ["/api/genres", "/api/studios", "/api/status", "/api/games/export.csv", "/api/keywords",
                 "/api/keyword-markets", "/api/meta"]:
        assert anon.get(path).status_code == 200, path
    assert anon.put("/api/games/indie.hit/mark", json={"status": "rejected"}).status_code == 401
    assert anon.get("/api/views", params={"page": "games"}).status_code == 401
    assert anon.post("/api/views", json={"page": "games", "name": "x", "params": {}}).status_code == 401
    assert anon.get("/api/team").status_code == 401
    assert anon.post("/api/admin/run").status_code == 401
    assert anon.get("/api/logs").status_code == 401
    assert anon.post("/api/brand-rules", json={"kind": "major", "pattern": "Foo"}).status_code == 401
    assert anon.get("/api/admin/workspaces").status_code == 401


def test_team_marks_stay_private(client):
    seed_radar()
    client.put("/api/games/indie.hit/mark", json={"status": "rejected", "note": "clone"})
    anon = TestClient(app)
    items = {g["app_id"]: g for g in anon.get("/api/games").json()["items"]}
    assert items["indie.hit"]["mark"] is None and items["indie.hit"]["note"] is None
    assert anon.get("/api/games/indie.hit").json()["mark"] is None
    assert "clone" not in anon.get("/api/games/export.csv", params={"marks": "all"}).text
    assert "clone" in client.get("/api/games/export.csv", params={"marks": "all"}).text


def test_status_hides_run_errors_from_guests(client):
    from playtrend.models import JobRun
    with session_scope() as s:
        s.add(JobRun(job="daily", status="error", error="proxy 1.2.3.4 refused", started_at=datetime.utcnow()))
    assert "1.2.3.4" not in TestClient(app).get("/api/status").text
    assert "1.2.3.4" in client.get("/api/status").text


def test_api_never_loads_the_scraping_network_layer():
    """Visitors must not be able to make the server fetch from Google through the proxy pool:
    the web API reads the database only, and only the worker talks to the network."""
    import subprocess
    import sys
    code = ("import sys, playtrend.api.main; "
            "print(','.join(m for m in sys.modules if m.startswith('playtrend.play') or m == 'google_play_scraper'))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == ""


def test_rate_limit_per_ip():
    from playtrend.api import ratelimit
    for i in range(10):
        assert ratelimit.check("1.1.1.1", "/api/auth/login", "POST", now=float(i)) is None
    assert ratelimit.check("1.1.1.1", "/api/auth/login", "POST", now=11.0) > 0
    assert ratelimit.check("2.2.2.2", "/api/auth/login", "POST", now=11.0) is None     # other IPs unaffected
    assert ratelimit.check("1.1.1.1", "/api/games", "GET", now=11.0) is None           # separate budget
    assert ratelimit.check("1.1.1.1", "/api/auth/login", "POST", now=15 * 60 + 1.0) is None  # window slides

    anon = TestClient(app)
    codes = [anon.post("/api/auth/login", json={"email": "a@b.c", "password": "wrongpass"}).status_code
             for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429


def test_registration_is_invite_only(client):
    anon = TestClient(app)
    assert anon.post("/api/auth/register", json={"email": "x@y.z", "password": "password123"}).status_code == 403
    token = client.post("/api/team/invites", json={}).json()["token"]
    r = anon.post("/api/auth/register", json={"email": "new@y.z", "password": "password123", "invite": token})
    assert r.status_code == 200
    assert anon.get("/api/me").json()["workspace"]["name"] == "Team"
    # invite is single-use
    assert TestClient(app).post("/api/auth/register", json={"email": "b@y.z", "password": "password123",
                                                             "invite": token}).status_code == 400


def test_radar_hides_brands_by_default(client):
    seed_radar()
    items = client.get("/api/games").json()["items"]
    ids = [g["app_id"] for g in items]
    assert ids[0] == "indie.hit"
    assert "brand.game" not in ids
    all_ids = [g["app_id"] for g in client.get("/api/games", params={"hide_flags": ""}).json()["items"]]
    assert "brand.game" in all_ids


def test_radar_filters_and_sorting(client):
    seed_radar()
    r = client.get("/api/games", params={"genres": "GAME_SIMULATION"}).json()
    assert [g["app_id"] for g in r["items"]] == ["slow.game"]
    r = client.get("/api/games", params={"max_age": 60, "sort": "v7", "dir": "asc"}).json()
    assert [g["app_id"] for g in r["items"]] == ["indie.hit"]
    r = client.get("/api/games", params={"charts": "top_new"}).json()
    assert r["total"] == 1
    hit = client.get("/api/games").json()["items"][0]
    assert 19_000 <= hit["v7"] <= 21_000
    assert hit["new_countries"] == 12 and hit["spark"]


def test_marks_hide_rejected(client):
    seed_radar()
    assert client.put("/api/games/indie.hit/mark", json={"status": "rejected", "note": "clone"}).status_code == 200
    ids = [g["app_id"] for g in client.get("/api/games").json()["items"]]
    assert "indie.hit" not in ids
    r = client.get("/api/games", params={"marks": "rejected"}).json()
    assert r["items"][0]["note"] == "clone"


def test_game_detail_and_views(client):
    seed_radar()
    d = client.get("/api/games/indie.hit").json()
    assert d["app"]["title"] == "Meow Sort"
    assert len(d["daily"]) == 14
    assert d["charts_latest"]["top_new_free"]["countries"] == {"us": 3}
    v = client.post("/api/views", json={"page": "games", "name": "Puzzles", "params": {"genres": "GAME_PUZZLE"}})
    assert v.status_code == 200
    assert client.get("/api/views", params={"page": "games"}).json()[0]["name"] == "Puzzles"


def test_overviews_and_status(client):
    seed_radar()
    genres = client.get("/api/genres").json()
    assert genres[0]["genre_id"] == "GAME_PUZZLE"
    studios = client.get("/api/studios", params={"min_trend": 0}).json()
    assert "SYBO Games" not in [s["developer"] for s in studios]
    st = client.get("/api/status").json()
    assert st["tracked"] == 3 and st["radar"] == 3
    csv = client.get("/api/games/export.csv")
    assert csv.status_code == 200 and "indie.hit" in csv.text


def test_brand_rules_admin(client):
    n = len(client.get("/api/brand-rules").json())
    r = client.post("/api/brand-rules", json={"kind": "hc_publisher", "pattern": "Tiny Studio"})
    assert r.status_code == 200
    assert len(client.get("/api/brand-rules").json()) == n + 1
    seed_radar()
    flags = client.get("/api/games", params={"hide_flags": ""}).json()["items"]
    assert "hc_publisher" in next(g for g in flags if g["app_id"] == "indie.hit")["brand_flags"]


def test_daily_steps_progress_and_logs(client, monkeypatch):
    from playtrend import cli
    from playtrend.pipeline.common import install_db_logging, job_run, log, parallel

    def fake_charts():
        with job_run("charts") as stats:
            for _ in parallel(lambda x: x, range(120), workers=2, label="charts"):
                pass
            stats["requests"] = 120
        return stats

    def broken():
        raise RuntimeError("google said no")

    registry = {name: (lambda: {}) for name in set(cli.DAILY_ORDER)}
    registry.update(charts=fake_charts, keywords=broken)
    monkeypatch.setattr(cli, "jobs", lambda: registry)
    handler = install_db_logging()
    try:
        cli.daily()
    finally:
        log.removeHandler(handler)

    st = client.get("/api/status").json()
    run = st["history"][0]
    assert run["status"] == "error"
    steps = {s["step"]: s for s in run["stats"]["steps"]}
    assert steps["charts"]["status"] == "ok" and steps["charts"]["stats"]["requests"] == 120
    assert steps["keywords"]["status"] == "error" and "google said no" in steps["keywords"]["error"]
    assert st["runs"]["charts"]["status"] == "ok"
    logs = client.get("/api/logs").json()
    assert any("суточный прогон завершён" in l["message"] for l in logs)
    warn = client.get("/api/logs", params={"level": "warning"}).json()
    assert all(l["level"] in ("WARNING", "ERROR", "CRITICAL") for l in warn) and warn


def test_soft_launch_games_get_no_lifetime_estimate(client):
    add_game("soft.game", "Last Echo", "Glaciers", 8, [1_155_000], charts={"top_new_free": 2})
    add_game("fresh.game", "Real New", "Indie", 8, [800_000], charts={"top_new_free": 2})
    with session_scope() as s:
        g = s.get(App, "soft.game")
        g.soft_launch, g.soft_launch_markets = True, ["ph", "id"]
    metrics.run(TODAY)
    items = {g["app_id"]: g for g in client.get("/api/games").json()["items"]}
    # installs include the soft-launch months, so installs/age would be wildly inflated
    assert items["soft.game"]["v7"] is None and items["soft.game"]["soft_launch"] is True
    assert items["fresh.game"]["v7"] == 100_000
    only = client.get("/api/games", params={"soft_launch": "only"}).json()["items"]
    assert [g["app_id"] for g in only] == ["soft.game"]
    assert client.get("/api/games/soft.game").json()["app"]["soft_launch_markets"] == ["ph", "id"]


def test_revivals_are_tracked_while_surging_and_dropped_after(client):
    from playtrend.pipeline.details import select_revivals, untrack_stale
    old = TODAY - timedelta(days=900)
    with session_scope() as s:
        for app_id, installs, n_c, rank in [("old.surge", 3_000_000, 4, 80),    # 4 countries -> revival
                                            ("old.top", 2_000_000, 1, 5),       # top-5 somewhere -> revival
                                            ("old.giant", 900_000_000, 9, 3),   # evergreen giant -> no
                                            ("old.meh", 1_000_000, 1, 150)]:    # one country, low -> no
            s.add(App(app_id=app_id, title=app_id, released=old, is_game=True, status="active", tracked=False,
                      real_installs=installs, details_at=datetime.utcnow(), last_trending=TODAY))
            s.add(ChartDaily(app_id=app_id, date=TODAY, collection="trending", n_countries=n_c, best_rank=rank,
                             countries={"us": rank}))
    assert select_revivals(TODAY) == 2
    with session_scope() as s:
        assert {a.app_id for a in s.query(App).filter(App.tracked.is_(True))} == {"old.surge", "old.top"}
        assert s.get(App, "old.surge").track_reason == "revival"
    untrack_stale(TODAY, 365, 120)                       # still surging -> kept
    with session_scope() as s:
        assert s.get(App, "old.surge").tracked
        s.get(App, "old.surge").last_trending = TODAY - timedelta(days=45)
    untrack_stale(TODAY, 365, 120)                       # quiet for 45 days -> dropped
    with session_scope() as s:
        assert not s.get(App, "old.surge").tracked and s.get(App, "old.top").tracked
    metrics.run(TODAY)
    r = client.get("/api/games", params={"revival": "only"}).json()["items"]
    assert [g["app_id"] for g in r] == ["old.top"] and r[0]["revival"] is True
    assert r[0]["v7"] is None     # no lifetime average for a years-old game


def test_hidden_gems(client):
    # fresh, growing, not a brand, charts in 2 countries at #45 -> hidden gem
    add_game("gem", "Quiet Hit", "Tiny", 20, [i * 20_000 for i in range(1, 16)])
    # same growth but charts high in many countries -> anyone would see it
    add_game("loud", "Loud Hit", "Other", 20, [i * 20_000 for i in range(1, 16)])
    with session_scope() as s:
        s.add(ChartDaily(app_id="gem", date=TODAY, collection="top_new_free", n_countries=2, best_rank=45,
                         countries={"ph": 45, "id": 60}))
        s.add(ChartDaily(app_id="loud", date=TODAY, collection="top_free", n_countries=30, best_rank=2,
                         countries={c: 2 for c in ["us", "gb", "de", "br", "in", "jp", "kr"]}))
    metrics.run(TODAY)
    items = {g["app_id"]: g for g in client.get("/api/games").json()["items"]}
    assert items["gem"]["hidden_gem"] and not items["loud"]["hidden_gem"]
    assert items["gem"]["chart_countries_any"] == 2
    only = client.get("/api/games", params={"hidden": "true"}).json()["items"]
    assert [g["app_id"] for g in only] == ["gem"]


def test_guest_keys_limits(client, monkeypatch):
    from playtrend.api import ratelimit
    from playtrend.models import KeysReport
    from playtrend.settings import get_settings
    for i in range(8):
        add_game(f"g{i}", f"Game {i}", "Dev", 20, [1000, 2000])
    anon = TestClient(app)
    # only queued reports count: re-ordering one that is already in the queue is free
    for _ in range(3):
        assert anon.post("/api/games/g0/keys").status_code == 200
    codes = [anon.post(f"/api/games/g{i}/keys").status_code for i in range(1, 6)]
    assert codes == [200, 200, 200, 200, 429]                           # 5 per hour from one IP
    assert client.post("/api/games/g5/keys").status_code == 200        # signed-in users are not limited
    assert ratelimit.guest_keys_wait("testclient", now=10**9) is None   # the hour passes...
    ratelimit._hits.clear()
    monkeypatch.setattr(get_settings(), "guest_keys_per_day", 5)        # ...but all guests share a daily budget
    assert anon.post("/api/games/g6/keys").json()["detail"] == "keys_guest_budget"
    with session_scope() as s:
        for r in s.query(KeysReport).filter(KeysReport.requested_by.is_(None)):
            r.requested_at -= timedelta(days=2)
    assert anon.post("/api/games/g6/keys").status_code == 200


def test_picks_are_private_to_the_team(client):
    from playtrend import picks
    from playtrend.models import Workspace
    seed_radar()
    assert client.get("/api/me").json()["picks"] == 0
    item = {"app_id": "indie.hit", "niche": "sort", "why": "grows on search", "rivals": ["slow.game", "gone.game"],
            "keys": [{"term": "sort puzzle", "country": "us", "demand": 70, "rank": 3, "young": 4}]}
    with session_scope() as s:
        ws = s.scalar(select(Workspace))
        with pytest.raises(ValueError):
            picks.load(s, ws.id, [{"app_id": "nope"}])
        picks.load(s, ws.id, [item, {"app_id": "slow.game", "tier": "more"}])
    r = client.get("/api/picks").json()
    assert [g["app_id"] for g in r["items"]] == ["indie.hit", "slow.game"]
    top = r["items"][0]
    assert top["v7"] and top["pick"]["tier"] == "top" and top["pick"]["keys"][0]["term"] == "sort puzzle"
    assert [x["app_id"] for x in top["pick"]["rivals"]] == ["slow.game"]
    assert client.get("/api/me").json()["picks"] == 2
    assert TestClient(app).get("/api/picks").status_code == 401

    with session_scope() as s:   # a new list replaces the old one
        assert picks.load(s, s.scalar(select(Workspace)).id, [item]) == {"loaded": 1, "removed": 1}
    assert [g["app_id"] for g in client.get("/api/picks").json()["items"]] == ["indie.hit"]
