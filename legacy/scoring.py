"""Heat Score: automatic 0-100 growth scoring for each app, recalculated daily."""

import math
from datetime import datetime, timedelta

from database import (
    get_conn, get_active_app_ids, get_app_history, get_app_chart_history,
    get_app_details, save_heat_score,
)
from config import REGIONS


def calc_install_velocity(snapshots: list[dict]) -> float:
    """Average daily installs over last 3 days, log-scaled. Max 30 points."""
    if len(snapshots) < 2:
        return 0.0
    recent = snapshots[-4:]  # last 4 snapshots = 3 deltas
    dailies = []
    for i in range(1, len(recent)):
        delta = recent[i].get("real_installs", 0) - recent[i - 1].get("real_installs", 0)
        dailies.append(max(delta, 0))
    if not dailies:
        return 0.0
    avg = sum(dailies) / len(dailies)
    if avg <= 0:
        return 0.0
    # log scale: 10k+/day = 30, 1k/day ~ 22.5, 100/day ~ 15
    score = (math.log10(avg + 1) / math.log10(10001)) * 30
    return min(score, 30.0)


def calc_rating_velocity(snapshots: list[dict]) -> float:
    """Average new ratings/day over last 3 days, log-scaled. Max 15 points."""
    if len(snapshots) < 2:
        return 0.0
    recent = snapshots[-4:]
    dailies = []
    for i in range(1, len(recent)):
        delta = recent[i].get("ratings_count", 0) - recent[i - 1].get("ratings_count", 0)
        dailies.append(max(delta, 0))
    if not dailies:
        return 0.0
    avg = sum(dailies) / len(dailies)
    if avg <= 0:
        return 0.0
    # log scale: 1000+/day = 15, 100/day ~ 11.25
    score = (math.log10(avg + 1) / math.log10(1001)) * 15
    return min(score, 15.0)


def calc_chart_momentum(chart_history: list[dict]) -> float:
    """Chart entry +10, speed of climb up to +10. Max 20 points."""
    if not chart_history:
        return 0.0
    score = 0.0
    # Being in chart at all = +10
    score += 10.0
    # Check position improvement over recent entries
    if len(chart_history) >= 2:
        recent = chart_history[-5:]  # last 5 entries
        positions = [e["position"] for e in recent]
        if len(positions) >= 2:
            improvement = positions[0] - positions[-1]  # positive = climbing
            # Normalize: climbing 50+ positions = +10
            climb_score = min(max(improvement, 0) / 50.0, 1.0) * 10
            score += climb_score
    return min(score, 20.0)


def calc_region_momentum(per_region_velocities: dict[str, float]) -> float:
    """Growth in multiple regions. 6+ regions with growth = 20. Max 20 points."""
    if not per_region_velocities:
        return 0.0
    growing_regions = sum(1 for v in per_region_velocities.values() if v > 0)
    # Scale: 6+ regions = 20, proportional below
    score = min(growing_regions / 6.0, 1.0) * 20
    return score


def calc_newness_bonus(first_seen_date: str | None, released_date: str | None) -> float:
    """Bonus for new apps. <7d=15, 7-14=10, 14-30=5, 30-60=2. Max 15 points."""
    ref_date = first_seen_date or released_date
    if not ref_date:
        return 0.0
    try:
        ref = datetime.strptime(ref_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return 0.0
    days = (datetime.utcnow() - ref).days
    if days < 7:
        return 15.0
    elif days < 14:
        return 10.0
    elif days < 30:
        return 5.0
    elif days < 60:
        return 2.0
    return 0.0


def compute_heat_score(app_id: str) -> dict | None:
    """Compute full heat score for a single app. Returns breakdown dict."""
    app = get_app_details(app_id)
    if not app:
        return None

    # Get snapshots across regions for velocity
    region_velocities = {}
    best_snapshots = []
    best_len = 0

    for region in REGIONS:
        snapshots = get_app_history(app_id, region)
        if len(snapshots) > best_len:
            best_snapshots = snapshots
            best_len = len(snapshots)
        # Calculate per-region install velocity (raw)
        if len(snapshots) >= 2:
            recent = snapshots[-4:]
            dailies = []
            for i in range(1, len(recent)):
                delta = recent[i].get("real_installs", 0) - recent[i - 1].get("real_installs", 0)
                dailies.append(max(delta, 0))
            region_velocities[region] = sum(dailies) / len(dailies) if dailies else 0

    install_vel = calc_install_velocity(best_snapshots)
    rating_vel = calc_rating_velocity(best_snapshots)

    # Chart momentum - aggregate across regions
    chart_score = 0.0
    for region in REGIONS:
        ch = get_app_chart_history(app_id, region)
        if ch:
            chart_score = max(chart_score, calc_chart_momentum(ch))

    region_mom = calc_region_momentum(region_velocities)
    newness = calc_newness_bonus(app.get("first_seen_date"), app.get("released_date"))

    total = install_vel + rating_vel + chart_score + region_mom + newness
    total = min(total, 100.0)

    return {
        "app_id": app_id,
        "heat_score": round(total, 1),
        "install_velocity": round(install_vel, 1),
        "rating_velocity": round(rating_vel, 1),
        "chart_momentum": round(chart_score, 1),
        "region_momentum": round(region_mom, 1),
        "newness_bonus": round(newness, 1),
    }


def compute_all_heat_scores():
    """Compute and save heat scores for all active apps."""
    app_ids = get_active_app_ids()
    print(f"\nComputing heat scores for {len(app_ids)} apps...")
    today = datetime.utcnow().strftime("%Y-%m-%d")
    computed = 0

    for app_id in app_ids:
        result = compute_heat_score(app_id)
        if result:
            save_heat_score(result, today)
            computed += 1

    print(f"Heat scores computed: {computed}/{len(app_ids)}")
