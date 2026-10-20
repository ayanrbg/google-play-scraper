"""Runtime configuration, read from environment variables (or a .env file)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PLAYTREND_", extra="ignore")

    # Postgres in production, e.g. postgresql+psycopg://playtrend:secret@db:5432/playtrend
    database_url: str = "sqlite:///./data/playtrend.db"

    # Auth
    secret_key: str = "dev-secret-change-me"
    session_days: int = 30
    # "invite" - only via invite link (default for a private team),
    # "open"   - anyone can sign up (public SaaS mode)
    registration: str = "invite"
    default_plan: str = "team"         # plan for workspaces created by open sign-up
    public_url: str = "http://localhost:5173"
    # First admin, created on startup if no users exist
    admin_email: str | None = None
    admin_password: str | None = None
    cookie_secure: bool = False
    # Keys reports guests (not signed in) may order per day, all IPs together: each costs ~500 proxy requests
    guest_keys_per_day: int = 40
    # Fast young games whose keys the daily run queues by itself (~7 min each without proxies)
    keys_auto_per_day: int = 25
    keys_auto_refresh_days: int = 30

    # Scraping pace. Google throttles by IP, so keep this polite.
    requests_per_second: float = 2.0   # from the server's own IP
    # Optional proxies for light requests, comma/newline separated:
    # http://user:pass@host:port  or Webshare-style host:port:user:pass
    proxies: str = ""
    proxy_rps: float = 0.7             # per proxy; keep low for shared proxies
    proxy_heavy: bool = False          # also send chart requests (~1.2 MB each) through proxies
    workers: int = 4
    http_timeout: float = 20.0

    # Tracking policy
    track_max_age_days: int = 365      # games older than this are not tracked daily
    untrack_after_days: int = 120      # stop daily tracking of games that fell out of all charts
    developer_refresh_days: int = 30
    developer_refresh_hot_days: int = 7   # studios with a fast-growing game are re-checked weekly
    # Old games (> track_max_age_days) re-enter tracking when they surge in Movers & Shakers
    revival_min_countries: int = 3
    revival_top_rank: int = 20
    revival_max_installs: int = 50_000_000
    revival_keep_days: int = 30
    keyword_refresh_per_run: int = 300    # English/US market
    keyword_seeds_per_run: int = 15
    keyword_local_refresh_per_run: int = 150   # each additional language market
    keyword_local_seeds_per_run: int = 8
    # Queries with room for a newcomer are searched again weekly: who entered and left the top
    keyword_watch_per_run: int = 60
    keyword_local_watch_per_run: int = 30
    similar_expand_top: int = 100
    # New-queries detector: autocomplete prefixes typed per market a day, new queries searched,
    # three-letter word starts of game titles/queries kept per market, and when it runs (UTC hour)
    new_queries_prefixes_per_market: int = 900
    new_queries_search_per_market: int = 40
    new_queries_game_prefixes: int = 700
    new_queries_hour_utc: int = 12

    # Scheduler (UTC hour of the daily pipeline)
    daily_hour_utc: int = 3

    # Retention
    chart_retention_days: int = 400


@lru_cache
def get_settings() -> Settings:
    return Settings()
