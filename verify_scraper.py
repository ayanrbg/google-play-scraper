"""Step 0: Verify that the google-play-scraper library works correctly.

Run this before writing any other code to confirm API availability and response fields.
"""

import time
import re
import requests
from google_play_scraper import app, search


def verify_app_details():
    """Test fetching app details for a well-known app."""
    print("=" * 60)
    print("TEST 1: Fetch app details (Clash of Clans)")
    print("=" * 60)

    start = time.time()
    try:
        result = app("com.supercell.clashofclans", lang="en", country="us")
        elapsed = time.time() - start

        key_fields = [
            "title", "developer", "developerId", "genre", "genreId",
            "icon", "score", "ratings", "reviews", "realInstalls",
            "minInstalls", "free", "containsAds", "offersIAP",
            "contentRating", "released", "updated", "version",
            "histogram", "price", "currency", "preRegister",
        ]

        print(f"  Response time: {elapsed:.2f}s")
        print(f"  Title: {result.get('title')}")
        print(f"  Developer: {result.get('developer')}")
        print(f"  Real Installs: {result.get('realInstalls'):,}")
        print(f"  Min Installs: {result.get('minInstalls'):,}")
        print(f"  Score: {result.get('score')}")
        print(f"  Ratings: {result.get('ratings'):,}")
        print(f"  Reviews: {result.get('reviews'):,}")
        print(f"  Histogram: {result.get('histogram')}")
        print(f"  Free: {result.get('free')}")
        print(f"  Pre-register: {result.get('preRegister')}")
        print(f"  Price: {result.get('price')} {result.get('currency')}")

        print("\n  Field availability:")
        for field in key_fields:
            val = result.get(field)
            status = "OK" if val is not None else "MISSING"
            print(f"    {field:20s} -> {status} ({type(val).__name__}: {str(val)[:60]})")

        print(f"\n  RESULT: SUCCESS ({len(result)} fields returned)")
        return True
    except Exception as e:
        print(f"  RESULT: FAILED — {e}")
        return False


def verify_search():
    """Test the search functionality."""
    print("\n" + "=" * 60)
    print("TEST 2: Search apps")
    print("=" * 60)

    start = time.time()
    try:
        results = search("new game", lang="en", country="us", n_hits=5)
        elapsed = time.time() - start

        print(f"  Response time: {elapsed:.2f}s")
        print(f"  Results count: {len(results)}")
        for i, r in enumerate(results):
            title = r.get('title', '?')[:50]
            app_id = r.get('appId', '?')
            try:
                print(f"    [{i+1}] {title} -- {app_id}")
            except UnicodeEncodeError:
                print(f"    [{i+1}] (unicode title) -- {app_id}")

        print(f"\n  RESULT: SUCCESS ({len(results)} results)")
        return True
    except Exception as e:
        print(f"  RESULT: FAILED — {e}")
        return False


def verify_chart_html():
    """Test fetching and parsing chart HTML from Google Play."""
    print("\n" + "=" * 60)
    print("TEST 3: Fetch chart HTML (Top Free Games US)")
    print("=" * 60)

    url = "https://play.google.com/store/apps/category/GAME?hl=en&gl=US"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    start = time.time()
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        elapsed = time.time() - start

        print(f"  Response time: {elapsed:.2f}s")
        print(f"  Status code: {resp.status_code}")
        print(f"  Content length: {len(resp.text):,} chars")

        pattern = r'/store/apps/details\?id=([\w\.]+)'
        app_ids = list(dict.fromkeys(re.findall(pattern, resp.text)))

        print(f"  App IDs found: {len(app_ids)}")
        for i, aid in enumerate(app_ids[:10]):
            print(f"    [{i+1}] {aid}")
        if len(app_ids) > 10:
            print(f"    ... and {len(app_ids) - 10} more")

        success = len(app_ids) > 0
        print(f"\n  RESULT: {'SUCCESS' if success else 'FAILED (no app IDs found)'}")
        return success
    except Exception as e:
        print(f"  RESULT: FAILED — {e}")
        return False


def main():
    print("Google Play Scraper — Library Verification")
    print("=" * 60)

    results = {}
    results["app_details"] = verify_app_details()
    time.sleep(1)
    results["search"] = verify_search()
    time.sleep(1)
    results["chart_html"] = verify_chart_html()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    all_pass = True
    for test, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {test:20s} -> {status}")
        if not passed:
            all_pass = False

    if all_pass:
        print("\nAll tests passed. Ready to build the scraper.")
    else:
        print("\nSome tests failed. Check the output above for details.")

    return all_pass


if __name__ == "__main__":
    main()
