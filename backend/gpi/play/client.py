"""Google Play data sources.

- charts():   real top charts via the internal batchexecute RPC (vyAe2), 200 per chart.
              Request template adapted from facundoolano/google-play-scraper (MIT).
- suggest():  search autocomplete (IJ4APc) - our demand signal for keywords.
- details():  full app card via google-play-scraper.
- search():   search results via google-play-scraper.
- page links: similar games, developer portfolio, pre-registration collection (HTML).
"""

import json
import re
import time
import urllib.parse
from datetime import date, datetime
from pathlib import Path

from google_play_scraper import search as gps_search
from google_play_scraper.constants.request import Formats
from google_play_scraper.exceptions import NotFoundError
from google_play_scraper.features.app import parse_dom as gps_parse_dom

from gpi.play.http import NotFound, note_throttled, request, routes, throttle

BASE = "https://play.google.com"
_LIST_BODY = (Path(__file__).parent / "_list_body.txt").read_text(encoding="utf-8").strip()
_DETAILS_LINK = re.compile(r"/store/apps/details\?id=([\w.]+)")


# ----------------------------- charts -----------------------------

def charts(collection: str, category: str, country: str, num: int = 200) -> list[dict]:
    """Top chart as [{app_id, title, developer, rank}]. collection is the Google cluster name."""
    body = (_LIST_BODY.replace("${num}", str(num))
            .replace("${collection}", collection).replace("${category}", category))
    url = (f"{BASE}/_/PlayStoreUi/data/batchexecute?rpcids=vyAe2&source-path=%2Fstore%2Fapps"
           "&f.sid=-4178618388443751758&bl=boq_playuiserver_20220612.08_p0&authuser=0"
           f"&soc-app=121&soc-platform=1&soc-device=1&_reqid=82003&rt=c&hl=en&gl={country}")
    # heavy: ~1.2 MB uncompressed, always sent from the server's own IP to spare proxy traffic
    resp = request("POST", url, data=body, heavy=True,
                   headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})
    return parse_charts(resp.text)


def parse_charts(text: str) -> list[dict]:
    lines = text.split("\n")
    if len(lines) < 4:
        return []
    envelope = json.loads(lines[3])
    payload = envelope[0][2]
    if not payload:
        return []
    data = json.loads(payload)
    try:
        items = data[0][1][0][28][0]
    except (TypeError, IndexError):
        return []
    out = []
    for rank, item in enumerate(items or [], 1):
        try:
            out.append({
                "app_id": item[0][0][0],
                "title": item[0][3],
                "developer": item[0][14],
                "rank": rank,
            })
        except (TypeError, IndexError):
            continue
    return out


# ----------------------------- suggest -----------------------------

def suggest(term: str, lang: str = "en", country: str = "us") -> list[str]:
    url = (f"{BASE}/_/PlayStoreUi/data/batchexecute?rpcids=IJ4APc&f.sid=-697906427155521722"
           f"&bl=boq_playuiserver_20190903.08_p0&hl={lang}&gl={country}&authuser"
           "&soc-app=121&soc-platform=1&soc-device=1&_reqid=1065213")
    q = urllib.parse.quote(term)
    body = f"f.req=%5B%5B%5B%22IJ4APc%22%2C%22%5B%5Bnull%2C%5B%5C%22{q}%5C%22%5D%2C%5B10%5D%2C%5B2%5D%2C4%5D%5D%22%5D%5D%5D"
    resp = request("POST", url, data=body,
                   headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})
    envelope = json.loads(resp.text[5:])
    payload = envelope[0][2]
    if not payload:
        return []
    data = json.loads(payload)
    if not data:
        return []
    return [s[0] for s in data[0][0]]


# ----------------------------- details / search -----------------------------

def _call_gps(fn, *args, **kwargs):
    last = None
    for attempt in range(4):
        throttle()
        try:
            return fn(*args, **kwargs)
        except NotFoundError:
            raise NotFound(args[0] if args else "")
        except Exception as e:  # google-play-scraper surfaces HTTP errors as generic exceptions
            last = e
            msg = str(e)
            if "429" in msg or "503" in msg:
                direct = routes()[0]
                direct.limiter.back_off(30 * (attempt + 1))
                note_throttled(direct, "429", 30 * (attempt + 1))
            else:
                time.sleep(2 ** attempt)
    raise last


def _parse_date(text) -> date | None:
    if not text:
        return None
    for fmt in ("%b %d, %Y", "%d %b %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def details(app_id: str) -> dict:
    """Normalized app card. Raises NotFound if the app is gone.

    The page is downloaded with our gzip-enabled session (~220 KB instead of ~1.4 MB that
    google-play-scraper's urllib fetch pulls uncompressed) and parsed by the library.
    """
    url = Formats.Detail.build(app_id=app_id, lang="en", country="us")
    try:
        html = request("GET", url).text
    except NotFound:
        url = Formats.Detail.fallback_build(app_id=app_id, lang="en")
        html = request("GET", url).text
    return normalize_details(gps_parse_dom(dom=html, app_id=app_id, url=url))


def normalize_details(raw: dict) -> dict:
    released = _parse_date(raw.get("released"))
    installs_text = raw.get("installs")
    # Pre-registration pages have neither a release date nor an installs bucket;
    # realInstalls then holds the pre-registration count.
    pre_register = released is None and not installs_text
    updated = raw.get("updated")
    genre_id = raw.get("genreId") or ""
    return {
        "app_id": raw.get("appId"),
        "title": raw.get("title"),
        "developer": raw.get("developer"),
        "developer_id": str(raw["developerId"]) if raw.get("developerId") else None,
        "genre_id": genre_id or None,
        "is_game": genre_id.startswith("GAME"),
        "icon_url": raw.get("icon"),
        "summary": raw.get("summary"),
        "content_rating": raw.get("contentRating"),
        "released": released,
        "last_updated": datetime.utcfromtimestamp(updated).date() if isinstance(updated, (int, float)) else None,
        "version": (raw.get("version") or "")[:100] or None,
        "free": bool(raw.get("free", True)),
        "price": float(raw.get("price") or 0),
        "contains_ads": bool(raw.get("containsAds")),
        "offers_iap": bool(raw.get("offersIAP")),
        "pre_register": pre_register,
        "real_installs": raw.get("realInstalls"),
        "min_installs": raw.get("minInstalls"),
        "ratings": raw.get("ratings"),
        "reviews": raw.get("reviews"),
        "score": raw.get("score"),
    }


def search(term: str, lang: str = "en", country: str = "us", n: int = 20) -> list[dict]:
    results = _call_gps(gps_search, term, lang=lang, country=country, n_hits=n)
    out = []
    for rank, r in enumerate(results or [], 1):
        if not r.get("appId"):
            continue
        out.append({
            "app_id": r["appId"],
            "title": r.get("title"),
            "developer": r.get("developer"),
            "genre": r.get("genre"),
            "score": r.get("score"),
            "min_installs": _parse_installs(r.get("installs")),
            "rank": rank,
        })
    return out


def _parse_installs(text) -> int | None:
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", str(text))
    return int(digits) if digits else None


# ----------------------------- HTML pages -----------------------------

def _links(url: str) -> list[str]:
    resp = request("GET", url)
    return list(dict.fromkeys(_DETAILS_LINK.findall(resp.text)))


def similar_ids(app_id: str) -> list[str]:
    ids = _links(f"{BASE}/store/apps/details?id={app_id}&hl=en&gl=us")
    return [i for i in ids if i != app_id]


def developer_ids(developer_id: str) -> list[str]:
    if developer_id.isdigit():
        url = f"{BASE}/store/apps/dev?id={developer_id}&hl=en&gl=us"
    else:
        url = f"{BASE}/store/apps/developer?id={urllib.parse.quote(developer_id)}&hl=en&gl=us"
    return _links(url)


def prereg_collection_ids(country: str = "us") -> list[str]:
    url = f"{BASE}/store/apps/collection/promotion_3000000d51_pre_registration_games?hl=en&gl={country}"
    try:
        return _links(url)
    except NotFound:
        return []
