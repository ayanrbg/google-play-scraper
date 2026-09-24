"""Helpers shared by pipeline jobs: run bookkeeping, live progress, a DB log for the site."""

import logging
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta
from typing import Callable, Iterable

from sqlalchemy import delete

from gpi.db import session_scope
from gpi.models import JobRun, LogEntry
from gpi.settings import get_settings

log = logging.getLogger("gpi")

_current_run: ContextVar[int | None] = ContextVar("current_run", default=None)
_current_job: ContextVar[str | None] = ContextVar("current_job", default=None)


@contextmanager
def job_run(name: str):
    """Record a job in job_runs; yields a dict the job fills with stats."""
    with session_scope() as s:
        run = JobRun(job=name, started_at=datetime.utcnow(), status="running", stats={})
        s.add(run)
        s.flush()
        run_id = run.id
    run_token, job_token = _current_run.set(run_id), _current_job.set(name)
    stats: dict = {}
    log.info("этап %s начат", name)
    try:
        yield stats
    except Exception as e:
        with session_scope() as s:
            run = s.get(JobRun, run_id)
            run.status, run.finished_at, run.stats = "error", datetime.utcnow(), stats
            run.error = "".join(traceback.format_exception(e))[-4000:]
        log.exception("этап %s упал: %s", name, e)
        raise
    finally:
        _current_run.reset(run_token)
        _current_job.reset(job_token)
    with session_scope() as s:
        run = s.get(JobRun, run_id)
        run.status, run.finished_at, run.stats = "ok", datetime.utcnow(), stats
    log.info("этап %s завершён: %s", name, stats)


def report_progress(label: str, done: int, total: int, started: float):
    """Store live progress on the running job so the site can show a progress bar and ETA."""
    run_id = _current_run.get()
    if not run_id:
        return
    elapsed = time.monotonic() - started
    rate = done / elapsed if elapsed > 0 else 0
    progress = {"label": label, "done": done, "total": total, "rate": round(rate, 2),
                "eta_sec": int((total - done) / rate) if rate > 0 else None,
                "at": datetime.utcnow().isoformat()}
    try:
        with session_scope() as s:
            run = s.get(JobRun, run_id)
            if run is not None:
                run.stats = {**(run.stats or {}), "progress": progress}
    except Exception:  # progress is best-effort, never break the job
        pass


def parallel(fn: Callable, items: Iterable, workers: int | None = None, progress_every: int = 200, label: str = ""):
    """Run fn over items in threads (the rate limiter keeps the global pace).

    Yields (item, result, error) as they complete.
    """
    items = list(items)
    workers = workers or get_settings().workers
    done = 0
    started = time.monotonic()
    report_progress(label, 0, len(items), started)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn, it): it for it in items}
        for fut in as_completed(futures):
            it = futures[fut]
            done += 1
            if progress_every and done % progress_every == 0:
                log.info("%s %d/%d", label, done, len(items))
            if done % 50 == 0 or done == len(items):
                report_progress(label, done, len(items), started)
            try:
                yield it, fut.result(), None
            except Exception as e:
                yield it, None, e


class DBLogHandler(logging.Handler):
    """Mirror the worker's log into the database, so the site can show it (no SSH needed)."""

    def emit(self, record: logging.LogRecord):
        if record.name.startswith("sqlalchemy"):
            return
        try:
            msg = record.getMessage()
            if record.exc_info:
                msg += "\n" + "".join(traceback.format_exception(*record.exc_info))[-2000:]
            with session_scope() as s:
                s.add(LogEntry(ts=datetime.utcfromtimestamp(record.created), level=record.levelname,
                               job=_current_job.get(), message=msg[:4000]))
        except Exception:
            pass


def install_db_logging():
    handler = DBLogHandler(level=logging.INFO)
    log.addHandler(handler)
    return handler


def prune_logs(days: int = 30):
    with session_scope() as s:
        s.execute(delete(LogEntry).where(LogEntry.ts < datetime.utcnow() - timedelta(days=days)))
