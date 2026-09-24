"""Runtime configuration, read from environment variables (or a .env file)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="GPI_", extra="ignore")

    # Postgres in production, e.g. postgresql+psycopg://gpi:secret@db:5432/gpi
    database_url: str = "sqlite:///./data/gpi.db"

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

    # Scraping pace. Google throttles by IP, so keep this polite.
    requests_per_second: float = 2.0
    workers: int = 4
    http_timeout: float = 20.0

    # Tracking policy
    track_max_age_days: int = 365      # games older than this are not tracked daily
    untrack_after_days: int = 120      # stop daily tracking of games that fell out of all charts
    developer_refresh_days: int = 30
    keyword_refresh_per_run: int = 300
    keyword_seeds_per_run: int = 15
    similar_expand_top: int = 100

    # Scheduler (UTC hour of the daily pipeline)
    daily_hour_utc: int = 3

    # Retention
    chart_retention_days: int = 400


@lru_cache
def get_settings() -> Settings:
    return Settings()
