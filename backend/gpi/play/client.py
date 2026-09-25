"""Google Play data sources.

- charts():   real top charts via the internal batchexecute RPC (vyAe2), 200 per chart.
              Request template adapted from facundoolano/google-play-scraper (MIT).
- suggest():  search autocomplete (IJ4APc) - our demand signal for keywords.
- details():  app page fetched by us (gzip, proxies), parsed by google-play-scraper.
- search():   search page fetched by us (proxies), parsed like google-play-scraper.
- page links: similar games, developer portfolio, pre-registration collection (HTML).
"""

import json
import re
import urllib.parse
from datetime import date, datetime
from pathlib import Path

from google_play_scraper.constants.element import ElementSpecs
from google_play_scraper.constants.regex import Regex
from google_play_scraper.constants.request import Formats
from google_play_scraper.features.app import parse_dom as gps_parse_dom

from gpi.play.http import NotFound, request

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


# Classic soft-launch markets. Google shows no release date there for a game that was
# available in that country before its global launch.
SOFT_LAUNCH_MARKETS = ["ph", "id", "au", "nz"]


def soft_launch_markets(app_id: str) -> list[str]:
    """Markets where the page has no release date although the game is out: soft launch there."""
    found = []
    for cc in SOFT_LAUNCH_MARKETS:
        url = f"{BASE}/store/apps/details?id={app_id}&hl=en&gl={cc}"
        try:
            raw = gps_parse_dom(dom=request("GET", url).text, app_id=app_id, url=url)
        except NotFound:
            continue  # not available in that country at all
        if not raw.get("released") and raw.get("installs"):
            found.append(cc)
    return found


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
    """Search results page, fetched through the route pool (proxies) and parsed like
    google-play-scraper does. The search page is the one Google throttles first."""
    q = urllib.parse.quote(term)
    url = Formats.Searchresults.build(query=q, lang=lang, country=country)
    try:
        dom = request("GET", url).text
    except NotFound:
        dom = request("GET", Formats.Searchresults.fallback_build(query=q, lang=lang)).text
    out = []
    for rank, r in enumerate(parse_search(dom, n), 1):
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


def parse_search(dom: str, n_hits: int) -> list[dict]:
    """Same extraction as google_play_scraper.features.search, minus its own HTTP call."""
    dataset = {}
    for match in Regex.SCRIPT.findall(dom):
        key, value = Regex.KEY.findall(match), Regex.VALUE.findall(match)
        if key and value:
            dataset[key[0]] = json.loads(value[0])
    if "ds:4" not in dataset:
        return []
    try:
        top_result = dataset["ds:4"][0][1][0][23][16]
    except (IndexError, TypeError):
        top_result = None
    apps = None
    for block in dataset["ds:4"][0][1]:
        try:
            apps = block[22][0]
        except (IndexError, TypeError):
            continue
    if apps is None:
        return []
    results = ([{k: spec.extract_content(top_result) for k, spec in ElementSpecs.SearchResultOnTop.items()}]
               if top_result else [])
    for i in range(min(len(apps), n_hits) - len(results)):
        results.append({k: spec.extract_content(apps[i]) for k, spec in ElementSpecs.SearchResult.items()})
    return results


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
