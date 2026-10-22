from playtrend.play.client import _linked_app_id


def test_top_search_card_app_id_comes_from_its_store_links():
    """Google's top card for an exact title (as seen 2026-10-22): the id sits only in nested store links."""
    card = [None, None, [None] * 41 + [[[None, None, "https://play.google.com/store/apps/details?id=com.cyphergames.royalsmash"]]],
            "Royal Smash! - Physics Puzzle"]
    assert _linked_app_id(card) == "com.cyphergames.royalsmash"
    assert _linked_app_id([None, ["no link here", 4.6]]) is None
