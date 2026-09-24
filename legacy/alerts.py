"""Telegram alerts for install spikes, chart entries, milestones, and hot new apps."""

import os
import requests
from datetime import datetime, timedelta

from database import (
    get_conn, get_active_app_ids, get_app_history, get_app_details,
    get_app_chart_history, save_alert_log, was_alert_sent_today,
)
from config import REGIONS

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

SPIKE_THRESHOLD = 2.0  # 200% of 7-day avg
SPIKE_MIN_INSTALLS = 1000
MILESTONES = [10_000, 50_000, 100_000, 500_000, 1_000_000, 5_000_000, 10_000_000]
HOT_NEW_SCORE_MIN = 70
HOT_NEW_DAYS = 7
MAX_ALERTS_PER_RUN = 10


def send_telegram(message: str) -> bool:
    """Send HTML message via Telegram Bot API."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[ALERT] (no Telegram config) {message[:100]}")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"[ALERT] Telegram error: {e}")
        return False


def format_alert(alert_type: str, data: dict) -> str:
    """Format an alert message in HTML for Telegram."""
    app_id = data.get("app_id", "")
    title = data.get("title", app_id)
    store_url = f"https://play.google.com/store/apps/details?id={app_id}"

    if alert_type == "install_spike":
        return (
            f"<b>Install Spike</b>\n"
            f"<a href=\"{store_url}\">{title}</a>\n"
            f"Daily: <b>{data.get('daily', 0):,}</b> "
            f"(avg: {data.get('avg', 0):,}, {data.get('ratio', 0):.1f}x)"
        )
    elif alert_type == "chart_entry":
        return (
            f"<b>New Chart Entry</b>\n"
            f"<a href=\"{store_url}\">{title}</a>\n"
            f"#{data.get('position', '?')} in {data.get('chart_type', '?')} ({data.get('region', '').upper()})"
        )
    elif alert_type == "milestone":
        return (
            f"<b>Milestone Reached</b>\n"
            f"<a href=\"{store_url}\">{title}</a>\n"
            f"Crossed <b>{data.get('milestone', 0):,}</b> installs"
        )
    elif alert_type == "hot_new":
        return (
            f"<b>Hot New App</b>\n"
            f"<a href=\"{store_url}\">{title}</a>\n"
            f"Heat Score: <b>{data.get('heat_score', 0)}</b> | "
            f"First seen: {data.get('first_seen', '?')}"
        )
    return f"Alert: {alert_type} — {title}"


def detect_install_spikes() -> list[dict]:
    """Find apps with daily installs > 200% of 7-day average."""
    alerts = []
    conn = get_conn()
    today = datetime.utcnow().strftime("%Y-%m-%d")

    app_ids = get_active_app_ids()
    for app_id in app_ids:
        snapshots = get_app_history(app_id, "us")
        if len(snapshots) < 3:
            continue
        # Last day delta
        latest = snapshots[-1].get("real_installs", 0)
        prev = snapshots[-2].get("real_installs", 0)
        daily = latest - prev
        if daily < SPIKE_MIN_INSTALLS:
            continue
        # 7-day average
        recent = snapshots[-8:]
        dailies = []
        for i in range(1, len(recent)):
            d = recent[i].get("real_installs", 0) - recent[i - 1].get("real_installs", 0)
            dailies.append(max(d, 0))
        if len(dailies) < 2:
            continue
        avg_7d = sum(dailies[:-1]) / len(dailies[:-1]) if len(dailies) > 1 else daily
        if avg_7d > 0 and daily / avg_7d >= SPIKE_THRESHOLD:
            app = get_app_details(app_id)
            alerts.append({
                "type": "install_spike",
                "app_id": app_id,
                "title": app.get("title", app_id) if app else app_id,
                "daily": daily,
                "avg": int(avg_7d),
                "ratio": daily / avg_7d,
            })
    return alerts


def detect_chart_entries() -> list[dict]:
    """Find apps that entered a chart for the first time today."""
    alerts = []
    today = datetime.utcnow().strftime("%Y-%m-%d")
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    conn = get_conn()
    rows = conn.execute("""
        SELECT DISTINCT cp.app_id, cp.region, cp.chart_type, cp.category, cp.position
        FROM chart_positions cp
        WHERE cp.date = ?
        AND NOT EXISTS (
            SELECT 1 FROM chart_positions cp2
            WHERE cp2.app_id = cp.app_id AND cp2.region = cp.region
            AND cp2.chart_type = cp.chart_type AND cp2.date < ?
        )
    """, (today, today)).fetchall()
    conn.close()

    for r in rows:
        app = get_app_details(r["app_id"])
        alerts.append({
            "type": "chart_entry",
            "app_id": r["app_id"],
            "title": app.get("title", r["app_id"]) if app else r["app_id"],
            "region": r["region"],
            "chart_type": r["chart_type"],
            "position": r["position"],
        })
    return alerts


def detect_milestone_crossings() -> list[dict]:
    """Find apps that crossed install milestones."""
    alerts = []
    app_ids = get_active_app_ids()
    for app_id in app_ids:
        snapshots = get_app_history(app_id, "us")
        if len(snapshots) < 2:
            continue
        prev_installs = snapshots[-2].get("real_installs", 0)
        curr_installs = snapshots[-1].get("real_installs", 0)
        for milestone in MILESTONES:
            if prev_installs < milestone <= curr_installs:
                app = get_app_details(app_id)
                alerts.append({
                    "type": "milestone",
                    "app_id": app_id,
                    "title": app.get("title", app_id) if app else app_id,
                    "milestone": milestone,
                })
    return alerts


def detect_hot_new_apps() -> list[dict]:
    """Find new apps with heat_score >= 70."""
    alerts = []
    cutoff = (datetime.utcnow() - timedelta(days=HOT_NEW_DAYS)).strftime("%Y-%m-%d")
    today = datetime.utcnow().strftime("%Y-%m-%d")
    conn = get_conn()
    rows = conn.execute("""
        SELECT hs.app_id, hs.heat_score, a.title, a.first_seen_date
        FROM heat_scores hs
        JOIN apps a ON hs.app_id = a.app_id
        WHERE hs.date = ? AND hs.heat_score >= ? AND a.first_seen_date >= ?
        ORDER BY hs.heat_score DESC
    """, (today, HOT_NEW_SCORE_MIN, cutoff)).fetchall()
    conn.close()

    for r in rows:
        alerts.append({
            "type": "hot_new",
            "app_id": r["app_id"],
            "title": r["title"] or r["app_id"],
            "heat_score": r["heat_score"],
            "first_seen": r["first_seen_date"],
        })
    return alerts


def run_alerts():
    """Orchestrator: detect all alert types, deduplicate, send up to MAX_ALERTS_PER_RUN."""
    print(f"\n{'=' * 60}")
    print(f"Alerts started: {datetime.utcnow().isoformat()}")
    print(f"{'=' * 60}")

    all_alerts = []
    all_alerts.extend(detect_hot_new_apps())
    all_alerts.extend(detect_install_spikes())
    all_alerts.extend(detect_chart_entries())
    all_alerts.extend(detect_milestone_crossings())

    print(f"Found {len(all_alerts)} potential alerts")

    sent = 0
    for alert in all_alerts:
        if sent >= MAX_ALERTS_PER_RUN:
            print(f"Reached max alerts ({MAX_ALERTS_PER_RUN}), stopping")
            break

        alert_key = f"{alert['type']}:{alert['app_id']}"
        if was_alert_sent_today(alert_key):
            continue

        message = format_alert(alert["type"], alert)
        success = send_telegram(message)
        save_alert_log(alert_key, alert["type"], alert["app_id"])
        sent += 1
        status = "sent" if success else "logged"
        print(f"  [{status}] {alert['type']}: {alert.get('title', alert['app_id'])[:40]}")

    print(f"Alerts completed: {sent} sent")


if __name__ == "__main__":
    from database import init_db
    init_db()
    run_alerts()
