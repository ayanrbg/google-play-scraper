"""Static catalog: countries, game categories, chart collections."""

# Largest Android markets, covering every region. Charts are scanned for each.
COUNTRIES = [
    # North America
    "us", "ca", "mx",
    # Latin America
    "br", "ar", "co", "cl", "pe",
    # Europe
    "gb", "de", "fr", "it", "es", "nl", "pl", "se", "tr", "ru", "ua",
    # Asia
    "jp", "kr", "tw", "hk", "in", "id", "ph", "vn", "th", "my", "sg", "pk",
    # Middle East & Africa
    "sa", "ae", "eg", "za", "ng",
    # Oceania
    "au",
]

GAME_CATEGORIES = [
    "GAME",
    "GAME_ACTION", "GAME_ADVENTURE", "GAME_ARCADE", "GAME_BOARD", "GAME_CARD",
    "GAME_CASINO", "GAME_CASUAL", "GAME_EDUCATIONAL", "GAME_MUSIC", "GAME_PUZZLE",
    "GAME_RACING", "GAME_ROLE_PLAYING", "GAME_SIMULATION", "GAME_SPORTS",
    "GAME_STRATEGY", "GAME_TRIVIA", "GAME_WORD",
]

GENRE_NAMES_RU = {
    "GAME_ACTION": "Экшен", "GAME_ADVENTURE": "Приключения", "GAME_ARCADE": "Аркады",
    "GAME_BOARD": "Настольные", "GAME_CARD": "Карточные", "GAME_CASINO": "Казино",
    "GAME_CASUAL": "Казуальные", "GAME_EDUCATIONAL": "Обучающие", "GAME_MUSIC": "Музыкальные",
    "GAME_PUZZLE": "Головоломки", "GAME_RACING": "Гонки", "GAME_ROLE_PLAYING": "Ролевые",
    "GAME_SIMULATION": "Симуляторы", "GAME_SPORTS": "Спорт", "GAME_STRATEGY": "Стратегии",
    "GAME_TRIVIA": "Викторины", "GAME_WORD": "Словесные",
}

# Our name -> Google Play internal cluster name
COLLECTIONS = {
    "top_new_free": "topselling_new_free",   # hidden "Top New Free" chart: only fresh games
    "trending": "movers_shakers",            # fastest risers
    "top_free": "topselling_free",
    "top_grossing": "topgrossing",
}

CHART_SIZE = 200

# Keyword markets (lang, country). Autocomplete and search are language-specific.
KEYWORD_MARKETS = [("en", "us")]
