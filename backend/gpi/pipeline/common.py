"""Helpers shared by pipeline jobs."""

import logging
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime
from typing import Callable, Iterable

from gpi.db import session_scope
from gpi.models import JobRun
from gpi.settings import get_settings

log = logging.getLogger("gpi")


@contextmanager
def job_run(name: str):
    """Record a job in job_runs; yields a dict the job fills with stats."""
    with session_scope() as s:
        run = JobRun(job=name, started_at=datetime.utcnow(), status="running", stats={})
        s.add(run)
        s.flush()
        run_id = run.id
    stats: dict = {}
    log.info("job %s started", name)
    try:
        yield stats
    except Exception as e:
        with session_scope() as s:
            run = s.get(JobRun, run_id)
            run.status, run.finished_at, run.stats = "error", datetime.utcnow(), stats
            run.error = "".join(traceback.format_exception(e))[-4000:]
        log.exception("job %s failed", name)
        raise
    with session_scope() as s:
        run = s.get(JobRun, run_id)
        run.status, run.finished_at, run.stats = "ok", datetime.utcnow(), stats
    log.info("job %s done: %s", name, stats)


def parallel(fn: Callable, items: Iterable, workers: int | None = None, progress_every: int = 200, label: str = ""):
    """Run fn over items in threads (the rate limiter keeps the global pace).

    Yields (item, result, error) as they complete.
    """
    items = list(items)
    workers = workers or get_settings().workers
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn, it): it for it in items}
        for fut in as_completed(futures):
            it = futures[fut]
            done += 1
            if progress_every and done % progress_every == 0:
                log.info("%s %d/%d", label, done, len(items))
            try:
                yield it, fut.result(), None
            except Exception as e:
                yield it, None, e
