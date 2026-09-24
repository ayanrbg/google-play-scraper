"""Configuration constants for Google Play Scraper."""

REGIONS = ["us", "jp", "kr", "gb", "de", "br", "in", "id", "ru", "tr", "mx", "tw"]

REGION_LANG = {
    "us": "en", "gb": "en", "de": "de", "jp": "ja", "kr": "ko",
    "br": "pt", "in": "en", "id": "id", "ru": "ru", "tr": "tr", "mx": "es", "tw": "zh",
}

CATEGORIES = [
    None, "GAME", "GAME_ACTION", "GAME_STRATEGY", "GAME_ROLE_PLAYING",
    "GAME_CASUAL", "APPLICATION",
    # Games (expanded)
    "GAME_PUZZLE", "GAME_RACING", "GAME_SIMULATION", "GAME_ADVENTURE",
    "GAME_ARCADE", "GAME_BOARD", "GAME_CARD", "GAME_EDUCATIONAL",
    "GAME_MUSIC", "GAME_SPORTS", "GAME_TRIVIA", "GAME_WORD",
    # Apps (expanded)
    "PRODUCTIVITY", "SOCIAL", "HEALTH_AND_FITNESS", "ENTERTAINMENT",
    "EDUCATION", "FINANCE", "TOOLS", "COMMUNICATION", "PHOTOGRAPHY", "SHOPPING",
]

CHART_TYPES = ["top_free", "top_grossing"]

REQUEST_DELAY_SEC = 0.4
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0

DB_PATH = "data/monitor.db"
MAX_TRACKED_APPS = 1000

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

SEARCH_QUERIES = [
    "new game 2026", "new release game", "just launched game",
    "new app 2026", "pre-register game",
]

SEARCH_QUERIES_BY_REGION = {
    "us": ["new game 2026", "new release game", "just launched game", "new app 2026", "pre-register game"],
    "gb": ["new game 2026", "new release game", "just launched game"],
    "ru": ["новая игра 2026", "новая мобильная игра", "топ новых игр", "новое приложение 2026"],
    "jp": ["新作ゲーム 2026", "新しいゲームアプリ", "新作アプリ"],
    "kr": ["새로운 게임 2026", "신작 게임", "새 앱 2026"],
    "br": ["novo jogo 2026", "jogo lançamento", "novo aplicativo 2026"],
    "de": ["neues Spiel 2026", "neue Spiele App", "neue App 2026"],
    "in": ["new game 2026", "new app 2026", "latest game"],
    "id": ["game baru 2026", "aplikasi baru 2026"],
    "tr": ["yeni oyun 2026", "yeni uygulama 2026"],
    "mx": ["juego nuevo 2026", "nueva app 2026", "juegos recientes"],
    "tw": ["新遊戲 2026", "新應用程式 2026"],
}

DISCOVERY_TIME_BUDGET_SEC = 18000  # 5 hours
SIMILAR_APPS_LIMIT = 20

# Google Play rounding thresholds for install counts
ROUNDING_THRESHOLDS = [0, 1000, 5000, 10000, 50000, 100000, 500000, 1000000, 5000000, 10000000]
