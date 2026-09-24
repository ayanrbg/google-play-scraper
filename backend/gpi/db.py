"""Database engine/session and a dialect-agnostic upsert helper."""

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from gpi.settings import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    if url.startswith("sqlite"):
        path = url.split("///", 1)[-1]
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

        return engine
    return create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=10)


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def upsert(session: Session, model, rows: list[dict], key: list[str], update: list[str] | None = None):
    """INSERT ... ON CONFLICT (key) DO UPDATE for Postgres and SQLite."""
    if not rows:
        return
    # Postgres rejects a statement that touches the same key twice; keep the last row per key.
    rows = list({tuple(r[k] for k in key): r for r in rows}.values())
    dialect = session.bind.dialect.name
    insert = postgresql.insert if dialect == "postgresql" else sqlite.insert
    cols = update if update is not None else [c for c in rows[0] if c not in key]
    # SQLite caps bound parameters per statement; chunk to stay under it.
    chunk = max(1, 30000 // max(1, len(rows[0])))
    for i in range(0, len(rows), chunk):
        stmt = insert(model).values(rows[i:i + chunk])
        if cols:
            stmt = stmt.on_conflict_do_update(
                index_elements=key, set_={c: stmt.excluded[c] for c in cols}
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=key)
        session.execute(stmt)
