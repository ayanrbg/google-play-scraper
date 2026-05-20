"""Data validation and daily installs estimation with confidence levels."""

from config import ROUNDING_THRESHOLDS


def validate_snapshot(current: dict, previous: dict | None) -> dict:
    """Validate a snapshot against the previous one.

    Returns dict with 'valid' (bool), 'warnings' (list of strings).
    """
    warnings = []

    score = current.get("score")
    if score is not None and (score < 0 or score > 5):
        warnings.append(f"Invalid score: {score}")

    real_installs = current.get("real_installs", 0)
    if real_installs < 0:
        warnings.append(f"Negative installs: {real_installs}")

    if previous:
        prev_installs = previous.get("real_installs", 0)
        if real_installs < prev_installs:
            warnings.append(f"Installs decreased: {prev_installs} -> {real_installs}")

        prev_ratings = previous.get("ratings_count", 0)
        curr_ratings = current.get("ratings_count", 0)
        if curr_ratings < prev_ratings:
            warnings.append(f"Ratings decreased: {prev_ratings} -> {curr_ratings}")

        if prev_installs > 0 and real_installs > prev_installs * 10:
            warnings.append(f"Installs spike >10x: {prev_installs} -> {real_installs}")

    return {
        "valid": len(warnings) == 0,
        "warnings": warnings,
    }


def estimate_daily_installs(snapshots: list[dict]) -> list[dict]:
    """Estimate daily installs from a list of snapshots (sorted by date ASC).

    Each result has: date, daily_installs, confidence (high/medium/low), method.
    """
    if len(snapshots) < 2:
        return []

    results = []
    for i in range(1, len(snapshots)):
        curr = snapshots[i]
        prev = snapshots[i - 1]

        curr_installs = curr.get("real_installs", 0)
        prev_installs = prev.get("real_installs", 0)
        delta_installs = curr_installs - prev_installs

        curr_ratings = curr.get("ratings_count", 0)
        prev_ratings = prev.get("ratings_count", 0)
        delta_ratings = curr_ratings - prev_ratings

        if delta_installs > 0:
            is_rounding = _is_rounding_artifact(prev_installs, curr_installs)
            if is_rounding:
                confidence = "low"
                method = "delta_installs (rounding artifact detected)"
            elif delta_ratings > 0:
                confidence = "high"
                method = "delta_installs (confirmed by rating growth)"
            else:
                confidence = "medium"
                method = "delta_installs"
            daily = delta_installs
        elif delta_installs == 0 and delta_ratings > 0:
            daily = delta_ratings * 100
            confidence = "low"
            method = "ratings_ratio (1 rating ~ 100 installs)"
        else:
            daily = 0
            confidence = "medium"
            method = "no_change"

        results.append({
            "date": curr.get("date"),
            "daily_installs": max(daily, 0),
            "confidence": confidence,
            "method": method,
            "delta_installs_raw": delta_installs,
            "delta_ratings": delta_ratings,
        })

    return results


def _is_rounding_artifact(prev: int, curr: int) -> bool:
    """Check if the jump matches a Google Play rounding threshold exactly."""
    delta = curr - prev
    for i in range(1, len(ROUNDING_THRESHOLDS)):
        threshold = ROUNDING_THRESHOLDS[i]
        if delta == threshold or delta == threshold - ROUNDING_THRESHOLDS[i - 1]:
            return True
    return False


def cross_validate_regions(region_snapshots: dict[str, dict]) -> list[str]:
    """Cross-validate installs across regions.

    region_snapshots: {region: snapshot_dict}
    Returns list of warning strings.
    """
    warnings = []
    if "us" not in region_snapshots:
        return warnings

    us_installs = region_snapshots["us"].get("real_installs", 0)
    for region, snap in region_snapshots.items():
        if region == "us":
            continue
        region_installs = snap.get("real_installs", 0)
        if region_installs > us_installs > 0:
            warnings.append(
                f"{region} installs ({region_installs:,}) > US installs ({us_installs:,})"
            )

    return warnings


def detect_rounding_artifacts(history: list[dict]) -> list[dict]:
    """Identify days where install jumps exactly match Google rounding thresholds."""
    artifacts = []
    for i in range(1, len(history)):
        prev = history[i - 1].get("real_installs", 0)
        curr = history[i].get("real_installs", 0)
        if _is_rounding_artifact(prev, curr):
            artifacts.append({
                "date": history[i].get("date"),
                "prev_installs": prev,
                "curr_installs": curr,
                "delta": curr - prev,
            })
    return artifacts
