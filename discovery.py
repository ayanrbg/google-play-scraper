"""Discovery module: find new apps from charts, search, and categories.

Run every 12 hours via GitHub Actions or manually.
"""

import time
from datetime import datetime

from config import REGIONS, REGION_LANG, CATEGORIES, CHART_TYPES, SEARCH_QUERIES, MAX_TRACKED_APPS
from database import (
    init_db, save_app, save_snapshot, save_chart_position,
    save_crawl_log, get_active_app_ids,
)
from scraper_utils import fetch_app_details, fetch_chart_app_ids, search_apps


def discover_from_charts(region: str) -> dict:
    """Discover apps from chart pages for a region.

    Returns {'app_ids': set, 'chart_data': [(app_id, chart_type, category, position)]}
    """
    lang = REGION_LANG.get(region, "en")
    all_app_ids = set()
    chart_data = []

    for chart_type in CHART_TYPES:
        for category in CATEGORIES:
            cat_label = category or "OVERALL"
            app_ids = fetch_chart_app_ids(chart_type, category, country=region)

            if app_ids:
                print(f"  [{region}] {chart_type}/{cat_label}: {len(app_ids)} apps")
                for pos, app_id in enumerate(app_ids, 1):
                    all_app_ids.add(app_id)
                    chart_data.append((app_id, chart_type, category, pos))

            time.sleep(0.3)

    return {"app_ids": all_app_ids, "chart_data": chart_data}


def discover_from_search(region: str) -> set:
    """Discover apps via search queries."""
    lang = REGION_LANG.get(region, "en")
    found = set()

    for query in SEARCH_QUERIES:
        results = search_apps(query, lang=lang, country=region, n_hits=20)
        for r in results:
            if r.get("app_id"):
                found.add(r["app_id"])
        if results:
            print(f"  [{region}] search '{query}': {len(results)} results")

    return found


def enrich_and_save(app_ids: set, region: str, chart_data: list) -> tuple[int, int, list]:
    """Fetch details for new apps and save them.

    Returns (processed, failed, errors).
    """
    lang = REGION_LANG.get(region, "en")
    existing = set(get_active_app_ids())
    new_ids = app_ids - existing

    # Only fetch details for NEW apps (existing ones are updated by tracker.py)
    to_process = list(new_ids)

    if len(to_process) > MAX_TRACKED_APPS:
        to_process = to_process[:MAX_TRACKED_APPS]

    processed = 0
    failed = 0
    errors = []

    # Save chart positions first
    for app_id, chart_type, category, position in chart_data:
        save_chart_position(app_id, region, chart_type, category, position)

    for i, app_id in enumerate(to_process):
        details = fetch_app_details(app_id, lang=lang, country=region)
        if details:
            save_app(details)
            save_snapshot(app_id, region, details)
            processed += 1
            is_new = app_id in new_ids
            label = "NEW" if is_new else "UPD"
            if is_new or (i < 5):
                print(f"    [{label}] {details.get('title', app_id)[:50]}")
        else:
            failed += 1
            errors.append(f"Failed to fetch: {app_id}")

        if (i + 1) % 50 == 0:
            print(f"    ... processed {i + 1}/{len(to_process)}")

    return processed, failed, errors


def run():
    print(f"\n{'=' * 60}")
    print(f"Discovery started: {datetime.utcnow().isoformat()}")
    print(f"{'=' * 60}")

    init_db()

    for region in REGIONS:
        start = time.time()
        print(f"\n--- Region: {region.upper()} ---")

        # 1. Charts (primary source)
        print(f"  [1] Scanning charts...")
        chart_result = discover_from_charts(region)
        all_ids = chart_result["app_ids"]

        # 2. Search (secondary source, only for US to save time)
        if region == "us":
            print(f"  [2] Searching...")
            search_ids = discover_from_search(region)
            all_ids |= search_ids

        print(f"  Total unique app IDs: {len(all_ids)}")

        # 3. Enrich and save
        print(f"  [3] Enriching and saving...")
        processed, failed, errors = enrich_and_save(all_ids, region, chart_result["chart_data"])

        duration = time.time() - start
        save_crawl_log("discovery", region, processed, failed, errors, duration)
        print(f"  Done: {processed} saved, {failed} failed, {duration:.1f}s")

    print(f"\n{'=' * 60}")
    print(f"Discovery completed: {datetime.utcnow().isoformat()}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    run()
