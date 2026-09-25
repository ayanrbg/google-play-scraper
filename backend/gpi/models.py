"""Database schema.

Market data (apps, snapshots, charts, keywords) is global and shared by every tenant.
Tenant data (marks, saved views) belongs to a workspace, so the same deployment can
serve many customers once it is opened up as a SaaS.
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON, BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from gpi.db import Base


def utcnow() -> datetime:
    return datetime.utcnow()


# ============================ Market data ============================

class App(Base):
    __tablename__ = "apps"

    app_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    title: Mapped[str | None] = mapped_column(String(500))
    developer: Mapped[str | None] = mapped_column(String(500))
    developer_id: Mapped[str | None] = mapped_column(String(255), index=True)
    genre_id: Mapped[str | None] = mapped_column(String(64), index=True)
    icon_url: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    content_rating: Mapped[str | None] = mapped_column(String(100))

    released: Mapped[date | None] = mapped_column(Date, index=True)
    last_updated: Mapped[date | None] = mapped_column(Date)
    version: Mapped[str | None] = mapped_column(String(100))
    free: Mapped[bool] = mapped_column(Boolean, default=True)
    price: Mapped[float] = mapped_column(Float, default=0)
    contains_ads: Mapped[bool] = mapped_column(Boolean, default=False)
    offers_iap: Mapped[bool] = mapped_column(Boolean, default=False)
    pre_register: Mapped[bool] = mapped_column(Boolean, default=False)
    # Available in soft-launch markets before the global "released" date (None = not checked yet).
    # Google hides the release date in countries where the game was out earlier.
    soft_launch: Mapped[bool | None] = mapped_column(Boolean)
    soft_launch_markets: Mapped[list | None] = mapped_column(JSON)
    # young | prereg | revival (an old game surging in Movers & Shakers)
    track_reason: Mapped[str | None] = mapped_column(String(16))
    last_trending: Mapped[date | None] = mapped_column(Date)

    # Latest values (global: Google Play reports installs worldwide, not per country)
    real_installs: Mapped[int | None] = mapped_column(BigInteger)
    min_installs: Mapped[int | None] = mapped_column(BigInteger)
    ratings: Mapped[int | None] = mapped_column(BigInteger)
    reviews: Mapped[int | None] = mapped_column(BigInteger)
    score: Mapped[float | None] = mapped_column(Float)

    is_game: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | removed
    tracked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    discovered_via: Mapped[str | None] = mapped_column(String(50))
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    details_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_charted: Mapped[date | None] = mapped_column(Date)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    similar_at: Mapped[datetime | None] = mapped_column(DateTime)


class Snapshot(Base):
    """One global installs/ratings reading per app per day."""
    __tablename__ = "snapshots"

    app_id: Mapped[str] = mapped_column(String(255), ForeignKey("apps.app_id", ondelete="CASCADE"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    real_installs: Mapped[int | None] = mapped_column(BigInteger)
    ratings: Mapped[int | None] = mapped_column(BigInteger)
    reviews: Mapped[int | None] = mapped_column(BigInteger)
    score: Mapped[float | None] = mapped_column(Float)


class ChartDaily(Base):
    """Per app, per day, per collection: where in the world it charts.

    countries maps country -> best rank across all game categories.
    """
    __tablename__ = "chart_daily"

    app_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    collection: Mapped[str] = mapped_column(String(32), primary_key=True)
    n_countries: Mapped[int] = mapped_column(Integer, default=0)
    best_rank: Mapped[int | None] = mapped_column(Integer)
    best_country: Mapped[str | None] = mapped_column(String(8))
    best_category: Mapped[str | None] = mapped_column(String(64))
    countries: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (Index("ix_chart_daily_date_coll", "date", "collection"),)


class Developer(Base):
    __tablename__ = "developers"

    developer_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(500))
    app_ids: Mapped[list] = mapped_column(JSON, default=list)
    app_count: Mapped[int] = mapped_column(Integer, default=0)
    max_installs: Mapped[int | None] = mapped_column(BigInteger)
    total_installs: Mapped[int | None] = mapped_column(BigInteger)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime)


class BrandRule(Base):
    """Editable list of big publishers / traffic-buying publishers / franchise IP."""
    __tablename__ = "brand_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32))    # major | hc_publisher | franchise
    pattern: Mapped[str] = mapped_column(String(255))  # developer name/id substring, or title word for franchise
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (UniqueConstraint("kind", "pattern"),)


class GameMetrics(Base):
    """Latest computed metrics per game: this is what the radar table reads."""
    __tablename__ = "game_metrics"

    app_id: Mapped[str] = mapped_column(String(255), ForeignKey("apps.app_id", ondelete="CASCADE"), primary_key=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    age_days: Mapped[int | None] = mapped_column(Integer, index=True)
    installs: Mapped[int | None] = mapped_column(BigInteger)
    v7: Mapped[float | None] = mapped_column(Float)        # installs/day, last 7 days
    v7_prev: Mapped[float | None] = mapped_column(Float)   # installs/day, the 7 days before
    accel: Mapped[float | None] = mapped_column(Float)     # v7 / v7_prev
    v_life: Mapped[float | None] = mapped_column(Float)    # installs / age
    ratings_v7: Mapped[float | None] = mapped_column(Float)
    new_countries: Mapped[int] = mapped_column(Integer, default=0)       # in Top New Free
    top_countries: Mapped[int] = mapped_column(Integer, default=0)       # in Top Free
    trending_countries: Mapped[int] = mapped_column(Integer, default=0)  # in Movers & Shakers
    grossing_countries: Mapped[int] = mapped_column(Integer, default=0)
    breadth_delta7: Mapped[int] = mapped_column(Integer, default=0)      # change in chart countries vs a week ago
    best_rank: Mapped[int | None] = mapped_column(Integer)
    search_visibility: Mapped[float] = mapped_column(Float, default=0)   # 0-100
    search_keywords: Mapped[int] = mapped_column(Integer, default=0)
    brand_flags: Mapped[list] = mapped_column(JSON, default=list)
    # Same flags as columns, so filters stay simple and indexable on any database
    flag_major: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_hc_publisher: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_franchise: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_big_dev: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_big_portfolio: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_cash: Mapped[bool] = mapped_column(Boolean, default=False)
    revival: Mapped[bool] = mapped_column(Boolean, default=False)
    # Young, not a brand, growing - yet barely visible in charts: what manual browsing misses
    hidden_gem: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    chart_countries_any: Mapped[int] = mapped_column(Integer, default=0)
    dev_max_installs: Mapped[int | None] = mapped_column(BigInteger)
    dev_app_count: Mapped[int | None] = mapped_column(Integer)
    trend_score: Mapped[float] = mapped_column(Float, default=0, index=True)
    score_parts: Mapped[dict] = mapped_column(JSON, default=dict)
    spark: Mapped[list] = mapped_column(JSON, default=list)   # daily installs, last 30 days
    data_days: Mapped[int] = mapped_column(Integer, default=0)


class ScoreHistory(Base):
    __tablename__ = "score_history"

    app_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    trend_score: Mapped[float] = mapped_column(Float)
    v7: Mapped[float | None] = mapped_column(Float)


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    term: Mapped[str] = mapped_column(String(255))
    lang: Mapped[str] = mapped_column(String(8), default="en")
    country: Mapped[str] = mapped_column(String(8), default="us")
    seed: Mapped[str | None] = mapped_column(String(255))
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # Autocomplete-based demand: how short a prefix still surfaces this term
    suggest_prefix_len: Mapped[int | None] = mapped_column(Integer)
    suggest_rank: Mapped[int | None] = mapped_column(Integer)
    demand: Mapped[float] = mapped_column(Float, default=0, index=True)
    # Search results competition
    competition: Mapped[float | None] = mapped_column(Float)
    opportunity: Mapped[float | None] = mapped_column(Float, index=True)
    top_median_installs: Mapped[int | None] = mapped_column(BigInteger)
    top_avg_rating: Mapped[float | None] = mapped_column(Float)
    young_share: Mapped[float | None] = mapped_column(Float)
    young_best_installs: Mapped[int | None] = mapped_column(BigInteger)
    brand_share: Mapped[float | None] = mapped_column(Float)
    title_match_share: Mapped[float | None] = mapped_column(Float)
    top_apps: Mapped[list] = mapped_column(JSON, default=list)
    games_share: Mapped[float | None] = mapped_column(Float)   # share of games in the top results
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)

    __table_args__ = (UniqueConstraint("term", "lang", "country"),)


class KeywordRank(Base):
    """Latest search position of an app for a keyword."""
    __tablename__ = "keyword_ranks"

    keyword_id: Mapped[int] = mapped_column(Integer, ForeignKey("keywords.id", ondelete="CASCADE"), primary_key=True)
    app_id: Mapped[str] = mapped_column(String(255), primary_key=True, index=True)
    rank: Mapped[int] = mapped_column(Integer)
    date: Mapped[date] = mapped_column(Date)


class SeedState(Base):
    """Which keyword seeds were expanded via autocomplete, and when."""
    __tablename__ = "keyword_seeds"

    seed: Mapped[str] = mapped_column(String(255), primary_key=True)
    lang: Mapped[str] = mapped_column(String(8), primary_key=True)
    country: Mapped[str] = mapped_column(String(8), primary_key=True)
    source: Mapped[str] = mapped_column(String(32), default="genre")  # genre | title | manual
    expanded_at: Mapped[datetime | None] = mapped_column(DateTime)


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | ok | error
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)


class LogEntry(Base):
    """Worker log mirrored into the DB for the "Данные" page."""
    __tablename__ = "log_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    level: Mapped[str] = mapped_column(String(10))
    job: Mapped[str | None] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)


# ============================ Tenants ============================

class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    plan: Mapped[str] = mapped_column(String(32), default="team")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey("workspaces.id"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="member")  # owner | member
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)  # platform operator
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime)


class Invite(Base):
    __tablename__ = "invites"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey("workspaces.id"))
    email: Mapped[str | None] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(20), default="member")
    created_by: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)


class Mark(Base):
    """A workspace's verdict on a game: interesting / in work / rejected, with a note."""
    __tablename__ = "marks"

    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    app_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    status: Mapped[str | None] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SavedView(Base):
    __tablename__ = "saved_views"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(Integer)
    page: Mapped[str] = mapped_column(String(32))  # games | keywords
    name: Mapped[str] = mapped_column(String(255))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
