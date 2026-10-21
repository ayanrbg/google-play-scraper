from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from playtrend.api.main import app
from playtrend.db import session_scope
from playtrend.models import App, GameMetrics, Keyword, SuggestPrefix, SuggestTerm
from playtrend.pipeline import new_queries
from playtrend.pipeline.keyword_markets import LATIN
from playtrend.pipeline.new_queries import DMarket, TitleIndex, phrase_of, record

TODAY = date.today()
US = DMarket("en", "us", LATIN)


def test_phrase_leaves_out_words_that_say_nothing():
    assert phrase_of("boom chip challenge 2 player game") == ("boom", "chip")
    assert phrase_of("jogo de imitar memes") == ("imitar", "memes")
    assert phrase_of("offline games") == ()


def test_only_queries_shown_by_an_already_crawled_prefix_are_new():
    with session_scope() as s:
        s.add(SuggestTerm(term="steal an egg", lang="en", country="us", first_seen=TODAY - timedelta(days=5),
                          last_seen=TODAY - timedelta(days=1), days_seen=3, baseline=True, prefix="stea",
                          prefix_len=4, position=2, first_prefix_len=4))
        s.flush()
        stats = record(s, US, {
            "mem": ["meme mix challenge", "meme"],      # crawled before: what it shows now is new
            "zq": ["zquest legends"],                   # first crawl: only the baseline
            "st": ["steal an egg"],                     # known query, now from a shorter prefix
        }, first_crawl={"zq"}, today=TODAY)
    assert stats == {"terms": 4, "new": 2}
    with session_scope() as s:
        t = {x.term: x for x in s.scalars(select(SuggestTerm))}
        assert not t["meme mix challenge"].baseline and t["zquest legends"].baseline
        egg = t["steal an egg"]
        assert (egg.days_seen, egg.last_seen, egg.prefix, egg.prefix_len) == (4, TODAY, "st", 2)
        assert egg.first_prefix_len == 4 and egg.baseline


def add_app(app_id, title, age, installs=10_000, v7=0, traffic="organic", is_game=True, dev=None, ads=True):
    with session_scope() as s:
        s.add(App(app_id=app_id, title=title, released=TODAY - timedelta(days=age), is_game=is_game, contains_ads=ads,
                  real_installs=installs, details_at=datetime.utcnow(), status="active", developer_id=dev or app_id))
        s.add(GameMetrics(app_id=app_id, v7=v7, traffic=traffic, brand_flags=[]))


def test_phrase_is_dated_by_its_first_game_and_led_by_the_fastest():
    add_app("a.first", "Bomb Chip Challenge", 90, v7=500)
    add_app("a.hit", "Boom Chip: Bomb Chip Party", 40, installs=3_000_000, v7=90_000)
    add_app("a.clone", "Bomb Chip 2 Player", 10, v7=50)
    add_app("a.other", "Chip Maker", 900)
    with session_scope() as s:
        st = TitleIndex(s, TODAY).stats(phrase_of("bomb chip game"))
    assert st["phrase_birth"] == TODAY - timedelta(days=90)
    assert (st["phrase_titles"], st["phrase_titles_30d"], st["leader_app_id"]) == (3, 1, "a.hit")
    # 3M installs at 40 days: bought or viral - marked, but not hidden, since viral demand is what clones live on
    assert st["leader_explosive"] and not st["leader_paid"]


def test_fresh_title_phrases_catch_a_clone_wave_early():
    """February 2026: three tiny "Bomb Chip" games from three studios, no hit yet. The pair is fresh;
    "chip" alone is old (poker and potato chip games), and one studio's own name is no wave."""
    add_app("hd.bomb", "Bomb Chip Challenge", 75, installs=3_000, dev="hd")
    add_app("cl.bomb", "Bomb Chip Challenge Game", 60, installs=900, dev="cleidimar")
    add_app("tasc.bomb", "Bomb Chips Duo: Bomb Chip Party", 14, installs=200, dev="tasc")
    add_app("solo.one", "Zorbix Quest", 20, dev="solo")
    add_app("solo.two", "Zorbix Quest 2", 10, dev="solo")
    for i in range(8):
        add_app(f"old.chip{i}", f"Poker Chip Master {i}", 900 + i, dev=f"old{i}")
    with session_scope() as s:
        index = TitleIndex(s, TODAY)
    phrases = index.fresh_phrases(50)
    assert phrases[0] == "bomb chip"
    assert "chip" not in phrases and "zorbix" not in phrases
    assert new_queries.word_queries(["bomb chip"]) == ["bomb chip", "bomb chip "]
    st = index.stats(phrase_of("bomb chip challenge"))
    assert (st["phrase_titles"], st["phrase_devs_30d"]) == (3, 1)    # "challenge" says nothing: phrase is "bomb chip"


def test_a_clone_wave_counts_as_proof_before_anyone_grows():
    k = Keyword(term="x", demand=60, games_share=1.0, analyzed_at=datetime.utcnow())
    base = dict(term="x", first_seen=TODAY, baseline=True, phrase_birth=TODAY - timedelta(days=70), relevant_top=2)
    lone = new_queries.score(SuggestTerm(**base, phrase_devs_30d=1), k, 0, TODAY)
    wave = new_queries.score(SuggestTerm(**base, phrase_devs_30d=3), k, 0, TODAY)
    assert abs(wave - 2 * lone) < 0.2      # proof 0.8 instead of 0.4


def test_score_wants_a_new_game_query_with_a_gap():
    k = Keyword(term="x", demand=70, games_share=0.9, analyzed_at=datetime.utcnow())
    new = SuggestTerm(term="x", first_seen=TODAY - timedelta(days=3), baseline=False, relevant_top=1)
    crowded = SuggestTerm(term="x", first_seen=TODAY - timedelta(days=3), baseline=False, relevant_top=8)
    old = SuggestTerm(term="x", first_seen=TODAY, baseline=True, phrase_birth=TODAY - timedelta(days=2000), relevant_top=1)
    a, b, c = (new_queries.score(t, k, 20_000, TODAY) for t in (new, crowded, old))
    assert a > b and a > c
    assert new_queries.score(new, Keyword(term="x", demand=70, games_share=0.2, analyzed_at=datetime.utcnow()), 0, TODAY) == 0
    assert new_queries.score(new, Keyword(term="x", demand=70), 0, TODAY) is None


def test_new_queries_api_can_hide_paid_leaders():
    add_app("lead.ok", "Egg Speed Escape", 30, v7=20_000)
    add_app("lead.ads", "Meme Mix Party", 30, installs=5_000_000, v7=300_000, traffic="mixed")
    with session_scope() as s:
        s.add(SuggestPrefix(prefix="egg", lang="en", country="us", first_crawled=TODAY - timedelta(days=4)))
        for term, leader, paid in (("egg speed", "lead.ok", False), ("meme mix", "lead.ads", True)):
            k = Keyword(term=term, lang="en", country="us", demand=60, games_share=1.0, room=8, room_best=2,
                        analyzed_at=datetime.utcnow())
            s.add(k)
            s.flush()
            s.add(SuggestTerm(term=term, lang="en", country="us", first_seen=TODAY - timedelta(days=2), last_seen=TODAY,
                              baseline=False, keyword_id=k.id, leader_app_id=leader, leader_paid=paid,
                              phrase=term, relevant_top=1, score=50))
    c = TestClient(app)
    assert c.get("/api/new-queries").json()["total"] == 2      # nothing hidden unless asked: not to miss anything
    r = c.get("/api/new-queries", params={"hide_paid": "true"}).json()
    assert [i["term"] for i in r["items"]] == ["egg speed"]
    item = r["items"][0]
    assert item["is_new"] and item["leader"]["app_id"] == "lead.ok" and item["keyword"]["room"] == 8
    assert r["started"] == (TODAY - timedelta(days=4)).isoformat()
    both = c.get("/api/new-queries", params={"hide_paid": "false", "kind": "new"}).json()
    assert both["total"] == 2


def test_detector_end_to_end(monkeypatch):
    """Day 1 sets the baseline; on day 2 a query the same prefix did not show is new, gets searched and scored."""
    add_app("egg.lead", "Steal Escape: Egg Speed", 30, installs=400_000, v7=25_000)
    add_app("other.app", "Calculator", 3000, is_game=False)
    shown = {"egg": ["egg games"]}
    monkeypatch.setattr(new_queries.client, "suggest", lambda p, lang, country: shown.get(p, []))
    monkeypatch.setattr(new_queries.client, "search", lambda term, lang, country, n: [
        {"app_id": "egg.lead", "title": "Steal Escape: Egg Speed", "developer": "x", "genre": None, "score": 4.5,
         "min_installs": 100_000, "rank": 1},
        {"app_id": "other.app", "title": "Calculator", "developer": "y", "genre": None, "score": 4.0,
         "min_installs": 1_000_000, "rank": 2}])
    monkeypatch.setattr(new_queries, "refresh", lambda *a, **k: None)
    monkeypatch.setattr(new_queries, "add_result_stubs", lambda *a, **k: [])
    with session_scope() as s:
        s.add(SuggestPrefix(prefix="egg", lang="en", country="us"))
    day1 = TODAY - timedelta(days=1)
    assert new_queries.crawl(US, 10, day1)["new"] == 0
    shown["egg"] = ["egg games", "egg speed escape"]
    assert new_queries.crawl(US, 10, TODAY)["new"] == 1
    with session_scope() as s:
        index = TitleIndex(s, TODAY)
    stats = new_queries.analyze(US, index, 10, TODAY)
    assert stats["searched"] == 2     # plus "egg games": seen from day one, but its phrase is a month old
    with session_scope() as s:
        t = s.scalar(select(SuggestTerm).where(SuggestTerm.term == "egg speed escape"))
        assert t.leader_app_id == "egg.lead" and t.relevant_top == 1 and t.score > 0
        assert s.get(Keyword, t.keyword_id).seed == new_queries.SEED


def test_run_types_fresh_title_phrases(monkeypatch):
    """Short prefixes never show "bomb chip challenge" (Booking and Boom Beach win there); the word query does."""
    add_app("hd.bomb", "Bomb Chip Challenge", 75, installs=3_000, dev="hd")
    add_app("cl.bomb", "Bomb Chip Game", 20, installs=900, dev="cleidimar")
    typed = []

    def suggest(p, lang, country):
        typed.append(p)
        return ["bomb chip challenge", "bomb chip challenge 2 player"] if p == "bomb chip " else ["booking", "boom beach"]
    monkeypatch.setattr(new_queries, "MARKETS", [US])
    monkeypatch.setattr(new_queries.client, "suggest", suggest)
    monkeypatch.setattr(new_queries.client, "search", lambda *a, **k: [])
    stats = new_queries.run()
    assert "bomb chip" in stats["title_phrases"] and stats["markets"]["us"]["word_queries"] >= 2
    assert {"bomb chip", "bomb chip "} <= set(typed)
    with session_scope() as s:
        t = s.scalar(select(SuggestTerm).where(SuggestTerm.term == "bomb chip challenge"))
        assert t.prefix == "bomb chip " and t.phrase == "bomb chip" and t.phrase_titles == 2
        assert s.get(SuggestPrefix, ("bomb chip ", "en", "us")).kind == "word"


def test_betting_is_not_a_game_idea():
    for t in ("81cc play", "1xbet", "goldbet app", "rummy circle", "fortune tiger", "dream slot 777 online",
              "holland casino nl", "betano"):
        assert new_queries.BETTING.search(t), t
    for t in ("alphabet lore", "bomb chip challenge", "3d tower", "4x4 offroad", "lucky scoop", "steal an egg"):
        assert not new_queries.BETTING.search(t), t
    k = Keyword(term="x", demand=70, games_share=1.0, analyzed_at=datetime.utcnow())
    assert new_queries.score(SuggestTerm(term="81cc play", first_seen=TODAY, baseline=False, relevant_top=0), k, 0, TODAY) == 0
    add_app("b1", "777WZ Slots Game", 20, dev="x1")
    add_app("b2", "777WZ Party", 15, dev="x2")
    add_app("b3", "Goldbet Royal", 10, dev="x3")
    add_app("b4", "Goldbet Arena", 12, dev="x4")
    with session_scope() as s:
        assert TitleIndex(s, TODAY).fresh_phrases(50) == []


def test_shell_apps_without_ads_or_purchases_lend_no_title_phrases():
    """Betting shells (AAAMXSimons, AAAMX Sort...) carry no ads and no purchases: they earn elsewhere."""
    for i in range(4):
        add_app(f"shell{i}", f"AAAMX Throne {i}", 10 + i, installs=50, dev=f"shell{i}", ads=False)
    add_app("w1", "Bomb Chip Challenge", 30, dev="a")
    add_app("w2", "Bomb Chip Party", 20, dev="b")
    with session_scope() as s:
        phrases = TitleIndex(s, TODAY).fresh_phrases(50)
    assert "bomb chip" in phrases and not any("aaamx" in p or "throne" in p for p in phrases)
