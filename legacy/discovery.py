"""Discovery module: find new apps from charts, search, similar apps, and developer pages.

Run every 12 hours via GitHub Actions or manually.
"""

import time
from datetime import datetime

from config import (
    REGIONS, REGION_LANG, CATEGORIES, CHART_TYPES, SEARCH_QUERIES_BY_REGION,
    MAX_TRACKED_APPS, DISCOVERY_TIME_BUDGET_SEC, SIMILAR_APPS_LIMIT,
)
from database import (
    init_db, save_app, save_snapshot, save_chart_position,
    save_crawl_log, get_active_app_ids, get_top_heated,
)
from scraper_utils import (
    fetch_app_details, fetch_chart_app_ids, search_apps,
    fetch_developer_app_ids, fetch_similar_app_ids,
    check_prereg_html, fetch_prereg_collection_ids,
)


def _time_remaining(start_time: float) -> float:
    return DISCOVERY_TIME_BUDGET_SEC - (time.time() - start_time)


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
    """Discover apps via localized search queries for a region."""
    lang = REGION_LANG.get(region, "en")
    found = set()

    queries = SEARCH_QUERIES_BY_REGION.get(region, SEARCH_QUERIES_BY_REGION.get("us", []))
    for query in queries:
        results = search_apps(query, lang=lang, country=region, n_hits=20)
        for r in results:
            if r.get("app_id"):
                found.add(r["app_id"])
        if results:
            print(f"  [{region}] search '{query}': {len(results)} results")

    return found


def discover_from_similar(region: str) -> set:
    """Discover apps from 'similar apps' of top-heated apps."""
    lang = REGION_LANG.get(region, "en")
    found = set()

    top_apps = get_top_heated(limit=SIMILAR_APPS_LIMIT)
    if not top_apps:
        return found

    print(f"  [{region}] Checking similar apps for top {len(top_apps)} heated apps...")
    for app_data in top_apps:
        app_id = app_data["app_id"]
        similar = fetch_similar_app_ids(app_id, lang=lang, country=region)
        for sid in similar:
            found.add(sid)
        if similar:
            print(f"    [{region}] {app_data.get('title', app_id)[:30]}: {len(similar)} similar")
        time.sleep(0.3)

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


def discover_prereg_apps(region: str) -> int:
    """Discover pre-registration apps from Google Play's official collection
    and verify via HTML parsing.

    Returns count of new pre-registration apps found.
    """
    lang = REGION_LANG.get(region, "en")
    existing = set(get_active_app_ids())

    # 1. Get app IDs from the official pre-registration collection page
    collection_ids = fetch_prereg_collection_ids(country=region)
    print(f"  Pre-reg collection: {len(collection_ids)} apps")

    # 2. Also scan known developers for new pre-reg apps
    from database import get_conn
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT developer_id FROM apps WHERE developer_id IS NOT NULL AND status = 'active'"
    ).fetchall()
    conn.close()
    developer_ids = [r["developer_id"] for r in rows]

    dev_new_ids = []
    for dev_id in developer_ids:
        dev_app_ids = fetch_developer_app_ids(dev_id, country=region)
        for aid in dev_app_ids:
            if aid not in existing:
                dev_new_ids.append(aid)
        time.sleep(0.2)

    # Combine candidates: collection apps + new developer apps
    candidates = list(dict.fromkeys(collection_ids + dev_new_ids))
    print(f"  Pre-reg candidates: {len(candidates)} ({len(collection_ids)} collection + {len(dev_new_ids)} dev-new)")

    found_prereg = 0
    for app_id in candidates:
        # Verify pre-registration via HTML
        is_prereg = check_prereg_html(app_id, lang=lang, country=region)
        if not is_prereg:
            continue

        details = fetch_app_details(app_id, lang=lang, country=region)
        if details:
            details["pre_register"] = True
            save_app(details)
            save_snapshot(app_id, region, details)
            existing.add(app_id)
            found_prereg += 1
            print(f"    [PRE-REG] {details.get('title', app_id)[:50]}")

    return found_prereg


def run():
    print(f"\n{'=' * 60}")
    print(f"Discovery started: {datetime.utcnow().isoformat()}")
    print(f"{'=' * 60}")

    init_db()
    run_start = time.time()

    # Priority regions for similar apps (top 5 by importance)
    similar_regions = ["us", "jp", "kr", "gb", "de"]

    for region in REGIONS:
        if _time_remaining(run_start) < 300:
            print(f"\nTime budget nearly exhausted, stopping discovery.")
            break

        start = time.time()
        print(f"\n--- Region: {region.upper()} ---")

        # 1. Charts (primary source, expanded categories)
        print(f"  [1] Scanning charts ({len(CATEGORIES)} categories x {len(CHART_TYPES)} types)...")
        chart_result = discover_from_charts(region)
        all_ids = chart_result["app_ids"]

        # 2. Similar apps (top 5 regions only)
        if region in similar_regions and _time_remaining(run_start) > 600:
            print(f"  [2] Discovering from similar apps...")
            similar_ids = discover_from_similar(region)
            all_ids |= similar_ids
            print(f"  Similar apps found: {len(similar_ids)}")

        # 3. Search (all regions, localized queries)
        if _time_remaining(run_start) > 300:
            print(f"  [3] Searching (localized queries)...")
            search_ids = discover_from_search(region)
            all_ids |= search_ids

        print(f"  Total unique app IDs: {len(all_ids)}")

        # 4. Enrich and save
        print(f"  [4] Enriching and saving...")
        processed, failed, errors = enrich_and_save(all_ids, region, chart_result["chart_data"])

        # 5. Discover pre-registration apps (collection + developer scan + HTML check)
        if _time_remaining(run_start) > 600:
            print(f"  [5] Discovering pre-registration apps...")
            prereg_found = discover_prereg_apps(region)
            if prereg_found:
                print(f"  Found {prereg_found} pre-registration app(s)")
        else:
            prereg_found = 0

        duration = time.time() - start
        save_crawl_log("discovery", region, processed + prereg_found, failed, errors, duration)
        print(f"  Done: {processed} saved, {prereg_found} pre-reg, {failed} failed, {duration:.1f}s")

    total_duration = time.time() - run_start
    print(f"\n{'=' * 60}")
    print(f"Discovery completed: {datetime.utcnow().isoformat()} ({total_duration:.0f}s total)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    run()
