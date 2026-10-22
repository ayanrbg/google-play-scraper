from playtrend.play.client import _linked_app_id


def test_top_search_card_app_id_comes_from_its_store_links():
    """Google's top card for an exact title (as seen 2026-10-22): the id sits only in nested store links."""
    card = [None, None, [None] * 41 + [[[None, None, "https://play.google.com/store/apps/details?id=com.cyphergames.royalsmash"]]],
            "Royal Smash! - Physics Puzzle"]
    assert _linked_app_id(card) == "com.cyphergames.royalsmash"
    assert _linked_app_id([None, ["no link here", 4.6]]) is None


def test_research_searches_again_keywords_that_lost_their_first_place(monkeypatch):
    from datetime import date, datetime
    from sqlalchemy import select
    from playtrend.db import session_scope
    from playtrend.models import App, Keyword, KeywordRank
    from playtrend.pipeline import keywords

    with session_scope() as s:
        s.add(App(app_id="hit", title="Royal Smash!", is_game=True, details_at=datetime.utcnow(), status="active"))
        s.add(App(app_id="other", title="Royal Match", is_game=True, details_at=datetime.utcnow(), status="active"))
        lost = Keyword(term="royal smash", lang="en", country="us", demand=60, analyzed_at=datetime.utcnow())
        fine = Keyword(term="match", lang="en", country="us", demand=60, analyzed_at=datetime.utcnow())
        s.add_all([lost, fine])
        s.flush()
        s.add_all([KeywordRank(keyword_id=lost.id, app_id="other", rank=2, date=date.today()),
                   KeywordRank(keyword_id=fine.id, app_id="other", rank=1, date=date.today())])
        lost_id = lost.id
    searched = []

    def search(term, lang, country, n):
        searched.append(term)
        return [{"app_id": "hit", "title": "Royal Smash!", "developer": "c", "genre": None, "score": 4.6,
                 "min_installs": 10_000_000, "rank": 1},
                {"app_id": "other", "title": "Royal Match", "developer": "d", "genre": None, "score": 4.7,
                 "min_installs": 100_000_000, "rank": 2}]
    monkeypatch.setattr(keywords.client, "search", search)
    monkeypatch.setattr(keywords, "refresh", lambda *a, **k: None)
    monkeypatch.setattr(keywords, "add_result_stubs", lambda *a, **k: [])
    stats = keywords.research_lost_first()
    assert searched == ["royal smash"] and stats["searched"] == 1
    with session_scope() as s:
        ranks = dict(s.execute(select(KeywordRank.app_id, KeywordRank.rank).where(KeywordRank.keyword_id == lost_id)).all())
    assert ranks == {"hit": 1, "other": 2}
