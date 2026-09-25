from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from gpi.api.main import app
from gpi.auth import create_user
from gpi.db import session_scope
from gpi.models import App, ChartDaily, Snapshot
from gpi.pipeline import metrics

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


def test_auth_required():
    assert TestClient(app).get("/api/games").status_code == 401


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
    from gpi import cli
    from gpi.pipeline.common import install_db_logging, job_run, log, parallel

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
