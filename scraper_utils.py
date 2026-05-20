"""Reliable wrapper over google-play-scraper with retry, rate limiting, and validation."""

import re
import time
import random
import requests
from google_play_scraper import app as gps_app, search as gps_search

from config import HEADERS, REQUEST_DELAY_SEC, MAX_RETRIES, RETRY_BACKOFF_BASE

# Global rate limiter
_last_request_time = 0.0


def _rate_limit():
    """Enforce minimum delay between requests."""
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < REQUEST_DELAY_SEC:
        sleep_time = REQUEST_DELAY_SEC - elapsed + random.uniform(0, 0.2)
        time.sleep(sleep_time)
    _last_request_time = time.time()


def _retry(func, *args, **kwargs):
    """Execute func with exponential backoff retry."""
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            _rate_limit()
            return func(*args, **kwargs)
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            if "404" in error_str or "not found" in error_str:
                raise
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF_BASE ** attempt + random.uniform(0, 1)
                time.sleep(wait)
    raise last_error


def _validate_app_data(data: dict) -> bool:
    """Check that essential fields are present and reasonable."""
    if not data:
        return False
    if not data.get("title"):
        return False
    score = data.get("score")
    if score is not None and (score < 0 or score > 5):
        return False
    real_installs = data.get("realInstalls")
    if real_installs is not None and real_installs < 0:
        return False
    return True


def normalize_app_data(data: dict) -> dict:
    """Extract and normalize fields from google-play-scraper response."""
    return {
        "app_id": data.get("appId"),
        "title": data.get("title"),
        "developer": data.get("developer"),
        "developer_id": data.get("developerId"),
        "genre": data.get("genre"),
        "genre_id": data.get("genreId"),
        "icon_url": data.get("icon"),
        "free": data.get("free", True),
        "contains_ads": data.get("containsAds", False),
        "offers_iap": data.get("offersIAP", False),
        "content_rating": data.get("contentRating"),
        "released_date": data.get("released"),
        "updated_date": str(data.get("updated", "")) if data.get("updated") else None,
        "pre_register": data.get("preRegister", False),
        "real_installs": data.get("realInstalls", 0) or 0,
        "min_installs": data.get("minInstalls", 0) or 0,
        "ratings_count": data.get("ratings", 0) or 0,
        "score": data.get("score"),
        "histogram": data.get("histogram"),
        "reviews_count": data.get("reviews", 0) or 0,
        "price": data.get("price", 0) or 0,
        "currency": data.get("currency", "USD"),
    }


def fetch_app_details(app_id: str, lang: str = "en", country: str = "us") -> dict | None:
    """Fetch and validate app details. Returns normalized dict or None."""
    try:
        raw = _retry(gps_app, app_id, lang=lang, country=country)
        if not _validate_app_data(raw):
            return None
        return normalize_app_data(raw)
    except Exception:
        return None


def search_apps(query: str, lang: str = "en", country: str = "us", n_hits: int = 30) -> list[dict]:
    """Search for apps. Returns list of normalized dicts."""
    try:
        results = _retry(gps_search, query, lang=lang, country=country, n_hits=n_hits)
        return [normalize_app_data(r) for r in results if _validate_app_data(r)]
    except Exception:
        return []


def fetch_chart_app_ids(chart_type: str, category: str | None, country: str = "us") -> list[str]:
    """Fetch app IDs from a Google Play chart/category page by parsing HTML.

    chart_type: 'top_free' or 'top_grossing'
    category: e.g. 'GAME', 'GAME_ACTION', or None for overall
    """
    # Google Play URL patterns (as of 2025+):
    #   Overall top:    /store/apps/top?hl=en&gl=US
    #   Category page:  /store/apps/category/GAME?hl=en&gl=US
    #   Games hub:      /store/games?hl=en&gl=US
    gl = country.upper()

    if category:
        url = f"https://play.google.com/store/apps/category/{category}?hl=en&gl={gl}"
    else:
        if chart_type == "top_grossing":
            url = f"https://play.google.com/store/apps/top?hl=en&gl={gl}"
        else:
            url = f"https://play.google.com/store/apps/top?hl=en&gl={gl}"

    try:
        _rate_limit()
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
        pattern = r'/store/apps/details\?id=([\w\.]+)'
        app_ids = list(dict.fromkeys(re.findall(pattern, resp.text)))
        return app_ids
    except Exception:
        return []
