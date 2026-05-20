"""Configuration constants for Google Play Scraper."""

REGIONS = ["us", "gb", "de", "jp", "kr", "br"]

REGION_LANG = {
    "us": "en",
    "gb": "en",
    "de": "de",
    "jp": "ja",
    "kr": "ko",
    "br": "pt",
}

CATEGORIES = [
    None,
    "GAME",
    "GAME_ACTION",
    "GAME_STRATEGY",
    "GAME_ROLE_PLAYING",
    "GAME_CASUAL",
    "APPLICATION",
    "TOOLS",
    "SOCIAL",
    "COMMUNICATION",
]

CHART_TYPES = ["top_free", "top_grossing"]

REQUEST_DELAY_SEC = 0.6
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0

DB_PATH = "data/monitor.db"
MAX_TRACKED_APPS = 500

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

SEARCH_QUERIES = [
    "new game 2026",
    "new app 2026",
    "best new android game",
    "pre-register game",
]

# Google Play rounding thresholds for install counts
ROUNDING_THRESHOLDS = [0, 1000, 5000, 10000, 50000, 100000, 500000, 1000000, 5000000, 10000000]
