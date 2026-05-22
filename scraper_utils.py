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


def check_prereg_html(app_id: str, lang: str = "en", country: str = "us") -> bool:
    """Check if an app is in pre-registration by parsing its Google Play HTML.

    Pre-reg apps lack the ["Install"] button in the ds:5 data block
    and have a pre-registration count like [null,null,N] instead of install stats.
    """
    gl = country.upper()
    url = f"https://play.google.com/store/apps/details?id={app_id}&hl={lang}&gl={gl}"
    try:
        _rate_limit()
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return False
        ds5 = re.search(
            r"AF_initDataCallback\(\{key:\s*'ds:5'.*?data:(.*?)\}\);",
            resp.text, re.DOTALL,
        )
        if not ds5:
            return False
        data = ds5.group(1)
        has_install_btn = bool(re.search(r'\["Install"\]', data))
        has_installs = bool(re.search(r'\["\d[\d,]*\+?",[1-9]', data))
        if not has_install_btn and not has_installs:
            return True
        return False
    except Exception:
        return False


def fetch_prereg_collection_ids(country: str = "us") -> list[str]:
    """Fetch app IDs from Google Play's official pre-registration collection."""
    gl = country.upper()
    url = (
        "https://play.google.com/store/apps/collection/"
        f"promotion_3000000d51_pre_registration_games?hl=en&gl={gl}"
    )
    try:
        _rate_limit()
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
        pattern = r'/store/apps/details\?id=([\w\.]+)'
        return list(dict.fromkeys(re.findall(pattern, resp.text)))
    except Exception:
        return []


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


def fetch_developer_app_ids(developer_id: str, country: str = "us") -> list[str]:
    """Fetch all app IDs from a developer's Google Play page."""
    gl = country.upper()
    url = f"https://play.google.com/store/apps/dev?id={developer_id}&hl=en&gl={gl}"
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


def fetch_similar_app_ids(app_id: str, lang: str = "en", country: str = "us") -> list[str]:
    """Fetch similar app IDs from a Google Play app page."""
    gl = country.upper()
    url = f"https://play.google.com/store/apps/details?id={app_id}&hl={lang}&gl={gl}"
    try:
        _rate_limit()
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
        pattern = r'/store/apps/details\?id=([\w\.]+)'
        all_ids = list(dict.fromkeys(re.findall(pattern, resp.text)))
        # Remove the app itself from similar list
        return [aid for aid in all_ids if aid != app_id]
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
