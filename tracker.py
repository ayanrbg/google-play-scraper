"""Tracker module: daily snapshots of installs/ratings for all tracked apps.

Run daily at 06:00 UTC via GitHub Actions.
"""

import time
from datetime import datetime

from config import REGIONS, REGION_LANG
from database import (
    init_db, get_active_app_ids_sorted, save_snapshot, increment_app_errors,
    save_crawl_log,
)
from scraper_utils import fetch_app_details


def run():
    print(f"\n{'=' * 60}")
    print(f"Tracker started: {datetime.utcnow().isoformat()}")
    print(f"{'=' * 60}")

    init_db()
    app_ids = get_active_app_ids_sorted()
    print(f"Tracking {len(app_ids)} active apps across {len(REGIONS)} regions\n")

    for region in REGIONS:
        start = time.time()
        lang = REGION_LANG.get(region, "en")
        processed = 0
        failed = 0
        errors = []

        print(f"--- Region: {region.upper()} ({len(app_ids)} apps) ---")

        for i, app_id in enumerate(app_ids):
            details = fetch_app_details(app_id, lang=lang, country=region)

            if details:
                save_snapshot(app_id, region, details)
                processed += 1
            else:
                failed += 1
                increment_app_errors(app_id)
                errors.append(app_id)

            if (i + 1) % 100 == 0:
                print(f"  [{region}] {i + 1}/{len(app_ids)} processed...")

        duration = time.time() - start
        save_crawl_log("tracker", region, processed, failed, errors, duration)
        print(f"  [{region}] Done: {processed} ok, {failed} failed, {duration:.1f}s")

    print(f"\n{'=' * 60}")
    print(f"Tracker completed: {datetime.utcnow().isoformat()}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    run()
