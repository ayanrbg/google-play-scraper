"""SQLite database: schema, CRUD, queries for the Google Play monitor."""

import json
import sqlite3
from datetime import datetime

from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS apps (
            app_id          TEXT PRIMARY KEY,
            title           TEXT,
            developer       TEXT,
            developer_id    TEXT,
            genre           TEXT,
            genre_id        TEXT,
            icon_url        TEXT,
            free            INTEGER DEFAULT 1,
            contains_ads    INTEGER DEFAULT 0,
            offers_iap      INTEGER DEFAULT 0,
            content_rating  TEXT,
            first_seen_date TEXT,
            released_date   TEXT,
            updated_date    TEXT,
            status          TEXT DEFAULT 'active',
            last_crawled    TEXT,
            consecutive_errors INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id          TEXT NOT NULL,
            region          TEXT NOT NULL,
            date            TEXT NOT NULL,
            real_installs   INTEGER DEFAULT 0,
            min_installs    INTEGER DEFAULT 0,
            ratings_count   INTEGER DEFAULT 0,
            score           REAL,
            histogram       TEXT,
            reviews_count   INTEGER DEFAULT 0,
            price           REAL DEFAULT 0,
            currency        TEXT DEFAULT 'USD',
            UNIQUE(app_id, region, date)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS chart_positions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id          TEXT NOT NULL,
            region          TEXT NOT NULL,
            date            TEXT NOT NULL,
            chart_type      TEXT NOT NULL,
            category        TEXT,
            position        INTEGER NOT NULL,
            UNIQUE(app_id, region, date, chart_type, category)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS crawl_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT NOT NULL,
            job_type        TEXT NOT NULL,
            region          TEXT,
            apps_processed  INTEGER DEFAULT 0,
            apps_failed     INTEGER DEFAULT 0,
            errors          TEXT,
            duration_sec    REAL
        )
    """)

    # Indexes for common queries
    c.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_app_region_date ON snapshots(app_id, region, date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_chart_pos_app_date ON chart_positions(app_id, region, date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_apps_status ON apps(status)")

    conn.commit()
    conn.close()


def save_app(app_data: dict):
    """Insert or update an app's metadata."""
    conn = get_conn()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    conn.execute("""
        INSERT INTO apps (app_id, title, developer, developer_id, genre, genre_id,
                         icon_url, free, contains_ads, offers_iap, content_rating,
                         first_seen_date, released_date, updated_date, status, last_crawled)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
        ON CONFLICT(app_id) DO UPDATE SET
            title=excluded.title, developer=excluded.developer,
            developer_id=excluded.developer_id, genre=excluded.genre,
            genre_id=excluded.genre_id, icon_url=excluded.icon_url,
            free=excluded.free, contains_ads=excluded.contains_ads,
            offers_iap=excluded.offers_iap, content_rating=excluded.content_rating,
            updated_date=excluded.updated_date, status='active',
            last_crawled=excluded.last_crawled, consecutive_errors=0
    """, (
        app_data.get("app_id"),
        app_data.get("title"),
        app_data.get("developer"),
        app_data.get("developer_id"),
        app_data.get("genre"),
        app_data.get("genre_id"),
        app_data.get("icon_url"),
        1 if app_data.get("free", True) else 0,
        1 if app_data.get("contains_ads") else 0,
        1 if app_data.get("offers_iap") else 0,
        app_data.get("content_rating"),
        app_data.get("first_seen_date", today),
        app_data.get("released_date"),
        app_data.get("updated_date"),
        today,
    ))
    conn.commit()
    conn.close()


def save_snapshot(app_id: str, region: str, data: dict):
    """Save a daily snapshot for an app in a specific region."""
    conn = get_conn()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    histogram = json.dumps(data.get("histogram")) if data.get("histogram") else None
    conn.execute("""
        INSERT OR REPLACE INTO snapshots
            (app_id, region, date, real_installs, min_installs, ratings_count,
             score, histogram, reviews_count, price, currency)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        app_id, region, today,
        data.get("real_installs", 0),
        data.get("min_installs", 0),
        data.get("ratings_count", 0),
        data.get("score"),
        histogram,
        data.get("reviews_count", 0),
        data.get("price", 0),
        data.get("currency", "USD"),
    ))
    conn.commit()
    conn.close()


def save_chart_position(app_id: str, region: str, chart_type: str, category: str, position: int):
    """Save a chart position entry."""
    conn = get_conn()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    conn.execute("""
        INSERT OR REPLACE INTO chart_positions (app_id, region, date, chart_type, category, position)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (app_id, region, today, chart_type, category or "OVERALL", position))
    conn.commit()
    conn.close()


def save_crawl_log(job_type: str, region: str, apps_processed: int, apps_failed: int,
                   errors: list, duration_sec: float):
    """Log a crawl run for auditing."""
    conn = get_conn()
    conn.execute("""
        INSERT INTO crawl_log (timestamp, job_type, region, apps_processed, apps_failed, errors, duration_sec)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.utcnow().isoformat(),
        job_type, region, apps_processed, apps_failed,
        json.dumps(errors[:20]) if errors else None,
        round(duration_sec, 2),
    ))
    conn.commit()
    conn.close()


def increment_app_errors(app_id: str):
    """Increment consecutive error count; mark as removed after 3."""
    conn = get_conn()
    conn.execute("""
        UPDATE apps SET consecutive_errors = consecutive_errors + 1
        WHERE app_id = ?
    """, (app_id,))
    conn.execute("""
        UPDATE apps SET status = 'removed'
        WHERE app_id = ? AND consecutive_errors >= 3
    """, (app_id,))
    conn.commit()
    conn.close()


def get_active_app_ids():
    """Get all active app_ids for tracking."""
    conn = get_conn()
    rows = conn.execute("SELECT app_id FROM apps WHERE status = 'active'").fetchall()
    conn.close()
    return [r["app_id"] for r in rows]


def get_all_apps_with_latest(region: str = "us"):
    """Get all apps joined with their latest snapshot and daily installs for a region."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT
            a.*,
            s1.real_installs   AS installs_today,
            s1.min_installs    AS min_installs_today,
            s1.ratings_count   AS ratings_today,
            s1.score           AS score_today,
            s1.reviews_count   AS reviews_today,
            s1.date            AS snapshot_date,
            s1.price           AS price_today,
            s1.currency        AS currency_today,
            CASE WHEN s2.real_installs IS NOT NULL
                 THEN s1.real_installs - s2.real_installs
                 ELSE NULL END AS daily_installs,
            CASE WHEN s2.ratings_count IS NOT NULL
                 THEN s1.ratings_count - s2.ratings_count
                 ELSE NULL END AS daily_ratings,
            cp.chart_type      AS latest_chart_type,
            cp.category        AS latest_chart_category,
            cp.position        AS latest_chart_position
        FROM apps a
        LEFT JOIN snapshots s1
            ON a.app_id = s1.app_id AND s1.region = ?
            AND s1.date = (SELECT MAX(date) FROM snapshots WHERE app_id = a.app_id AND region = ?)
        LEFT JOIN snapshots s2
            ON a.app_id = s2.app_id AND s2.region = ?
            AND s2.date = (SELECT MAX(date) FROM snapshots WHERE app_id = a.app_id AND region = ? AND date < s1.date)
        LEFT JOIN (
            SELECT app_id, region, chart_type, category, MIN(position) AS position
            FROM chart_positions
            WHERE region = ?
            GROUP BY app_id, region
            HAVING date = (SELECT MAX(date) FROM chart_positions cp2 WHERE cp2.app_id = chart_positions.app_id AND cp2.region = ?)
        ) cp ON a.app_id = cp.app_id
        ORDER BY daily_installs DESC NULLS LAST
    """, (region, region, region, region, region, region)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_app_history(app_id: str, region: str = "us"):
    """Get snapshot history for an app in a region."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT date, real_installs, min_installs, ratings_count, score, reviews_count, price
        FROM snapshots
        WHERE app_id = ? AND region = ?
        ORDER BY date ASC
    """, (app_id, region)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_app_chart_history(app_id: str, region: str = "us"):
    """Get chart position history for an app."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT date, chart_type, category, position
        FROM chart_positions
        WHERE app_id = ? AND region = ?
        ORDER BY date ASC
    """, (app_id, region)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_app_details(app_id: str):
    """Get metadata for a single app."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM apps WHERE app_id = ?", (app_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_crawl_logs(limit: int = 50):
    """Get recent crawl logs."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM crawl_log ORDER BY timestamp DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_regions_with_data():
    """Get list of regions that have snapshot data."""
    conn = get_conn()
    rows = conn.execute("SELECT DISTINCT region FROM snapshots ORDER BY region").fetchall()
    conn.close()
    return [r["region"] for r in rows]


def get_total_apps_count():
    """Get count of apps by status."""
    conn = get_conn()
    rows = conn.execute("SELECT status, COUNT(*) as cnt FROM apps GROUP BY status").fetchall()
    conn.close()
    return {r["status"]: r["cnt"] for r in rows}


def get_new_apps_since(date_str: str):
    """Get apps first seen since a given date."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM apps WHERE first_seen_date >= ? ORDER BY first_seen_date DESC
    """, (date_str,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
