"""Command line: `python -m gpi.cli <command>`.

  migrate                 apply DB migrations + seed brand rules + create first admin
  daily                   run the full daily pipeline once
  run <job> [...]         run single jobs: charts expand enrich track metrics keywords cleanup
  worker                  long-running scheduler (runs `daily` once a day at GPI_DAILY_HOUR_UTC)
  create-user <email> <password> [--superadmin]
  import-legacy <path>    import history from the old SQLite monitor.db
"""

import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta

from sqlalchemy import delete, select

from gpi.db import session_scope
from gpi.models import ChartDaily, JobRun, ScoreHistory
from gpi.settings import get_settings

log = logging.getLogger("gpi")


def migrate():
    from alembic import command
    from alembic.config import Config
    from pathlib import Path

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    command.upgrade(cfg, "head")
    bootstrap()


def bootstrap():
    from gpi.auth import create_user
    from gpi.models import User
    from gpi.pipeline.brand import seed_rules

    s = get_settings()
    with session_scope() as db:
        added = seed_rules(db)
        if added:
            log.info("seeded %d brand rules", added)
        if s.admin_email and s.admin_password and not db.scalar(select(User.id).limit(1)):
            create_user(db, s.admin_email, s.admin_password, workspace_name="Main", role="owner", superadmin=True)
            log.info("created admin %s", s.admin_email)


def cleanup():
    from gpi.models import App

    keep = date.today() - timedelta(days=get_settings().chart_retention_days)
    with session_scope() as s:
        s.execute(delete(ChartDaily).where(ChartDaily.date < keep))
        # Chart history matters only for games we track; old hits in Top Free/Grossing are the
        # bulk of chart rows, so keep just two weeks for them (enough for week-over-week deltas).
        s.execute(delete(ChartDaily).where(
            ChartDaily.date < date.today() - timedelta(days=14),
            ChartDaily.app_id.not_in(select(App.app_id).where(App.tracked.is_(True)))))
        s.execute(delete(ScoreHistory).where(ScoreHistory.date < keep))
        s.execute(delete(JobRun).where(JobRun.started_at < datetime.utcnow() - timedelta(days=90)))
    from gpi.pipeline.common import prune_logs
    prune_logs(30)
    return {}


def jobs():
    from gpi.pipeline import charts, details, expand, keywords, metrics
    return {
        "charts": charts.run,
        "expand": expand.run,
        "enrich": details.enrich,
        "track": details.track,
        "metrics": metrics.run,
        "keywords": keywords.run,
        "cleanup": cleanup,
        "softlaunch": details.backfill_soft_launch,
    }


INTERRUPTED = "прервано перезапуском воркера"
DAILY_ORDER = ["charts", "expand", "enrich", "track", "metrics", "keywords", "enrich", "metrics", "cleanup"]


def daily():
    """Full pipeline. A failing step is logged and the rest still runs.

    The run's stats hold a step list the site renders as a checklist:
    [{step, status: pending|running|ok|error, started, finished, stats, error}]
    """
    registry = jobs()
    steps = [{"step": name, "status": "pending"} for name in DAILY_ORDER]

    def save(status="running"):
        with session_scope() as s:
            run = s.get(JobRun, run_id)
            run.stats = {"steps": steps}
            run.status = status
            if status != "running":
                run.finished_at = datetime.utcnow()

    with session_scope() as s:
        run = JobRun(job="daily", status="running", stats={"steps": steps})
        s.add(run)
        s.flush()
        run_id = run.id
    from gpi.play.http import reset_throttle_count, throttle_count
    reset_throttle_count()
    log.info("суточный прогон начат")
    for step in steps:
        step.update(status="running", started=datetime.utcnow().isoformat())
        save()
        try:
            step["stats"] = registry[step["step"]]() or {}
            step["status"] = "ok"
        except Exception as e:
            step.update(status="error", error=f"{type(e).__name__}: {e}"[:500])
        step["finished"] = datetime.utcnow().isoformat()
    failed = [s["step"] for s in steps if s["status"] == "error"]
    throttled = throttle_count()
    if throttled:
        log.warning("за прогон Google ограничивал запросы %d раз: если это повторяется каждый день, "
                    "пора подключать прокси или снизить GPI_REQUESTS_PER_SECOND", throttled)
    save("error" if failed else "ok")
    log.log(logging.WARNING if failed else logging.INFO, "суточный прогон завершён%s",
            f", ошибки в этапах: {', '.join(failed)}" if failed else " без ошибок")


def worker():
    cfg = get_settings()
    from gpi.pipeline.common import install_db_logging
    install_db_logging()
    # Only one worker exists, so anything still "running" was cut off by a restart.
    with session_scope() as s:
        for stuck in s.scalars(select(JobRun).where(JobRun.status == "running")):
            stuck.status, stuck.finished_at, stuck.error = "error", datetime.utcnow(), INTERRUPTED
    log.info("воркер запущен, суточный прогон в %02d:00 UTC", cfg.daily_hour_utc)
    while True:
        now = datetime.utcnow()
        today_start = datetime.combine(now.date(), datetime.min.time())
        with session_scope() as s:
            # A run cut off by a restart does not count: the pipeline resumes the same day.
            done_today = s.scalar(select(JobRun.id).where(
                JobRun.job == "daily", JobRun.started_at >= today_start,
                (JobRun.error.is_(None)) | (JobRun.error != INTERRUPTED)).limit(1))
            # A crashed container leaves a "running" row behind; close it so the next run is not blocked.
            for stuck in s.scalars(select(JobRun).where(JobRun.status == "running",
                                                        JobRun.started_at < now - timedelta(hours=20))):
                stuck.status, stuck.error = "error", "interrupted"
            # "Run now" button in the admin UI
            requested = s.scalars(select(JobRun).where(JobRun.job == "request:daily", JobRun.status == "pending")).all()
            for r in requested:
                r.status, r.finished_at = "ok", now
        if requested:
            log.info("запуск по кнопке «Запустить сейчас»")
        if requested or (not done_today and now.hour >= cfg.daily_hour_utc):
            daily()
        time.sleep(60)


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="gpi")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    sub.add_parser("daily")
    sub.add_parser("worker")
    r = sub.add_parser("run")
    r.add_argument("jobs", nargs="+")
    u = sub.add_parser("create-user")
    u.add_argument("email")
    u.add_argument("password")
    u.add_argument("--superadmin", action="store_true")
    u.add_argument("--workspace", default="Main")
    imp = sub.add_parser("import-legacy")
    imp.add_argument("path")
    args = p.parse_args(argv)

    if args.cmd == "migrate":
        migrate()
    elif args.cmd == "daily":
        from gpi.pipeline.common import install_db_logging
        install_db_logging()
        daily()
    elif args.cmd == "worker":
        worker()
    elif args.cmd == "run":
        from gpi.pipeline.common import install_db_logging
        install_db_logging()
        registry = jobs()
        for name in args.jobs:
            if name not in registry:
                sys.exit(f"unknown job {name}; choose from {', '.join(registry)}")
            registry[name]()
    elif args.cmd == "create-user":
        from gpi.auth import create_user
        from gpi.models import Workspace
        with session_scope() as s:
            ws = s.scalar(select(Workspace).where(Workspace.name == args.workspace))
            create_user(s, args.email, args.password, workspace_id=ws.id if ws else None,
                        workspace_name=args.workspace, role="owner" if not ws else "member",
                        superadmin=args.superadmin)
        print("ok")
    elif args.cmd == "import-legacy":
        from gpi.legacy_import import import_legacy
        print(import_legacy(args.path))


if __name__ == "__main__":
    main()
