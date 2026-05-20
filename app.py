"""Streamlit web dashboard for the Google Play monitor."""

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

from database import (
    init_db, get_all_apps_with_latest, get_app_history, get_app_chart_history,
    get_app_details, get_crawl_logs, get_regions_with_data, get_total_apps_count,
    get_new_apps_since, get_emerging_hits, get_pre_registrations,
)
from accuracy import estimate_daily_installs, cross_validate_regions, detect_rounding_artifacts
from config import REGIONS

st.set_page_config(page_title="Game Ideas Finder", page_icon="🎮", layout="wide")

init_db()

# --- Sidebar ---
available_regions = get_regions_with_data() or ["us"]

with st.sidebar:
    st.header("Filters")
    selected_region = st.selectbox("Region", available_regions, index=0)

# --- Tabs ---
tab_emerging, tab_prereg, tab_all, tab_detail, tab_quality = st.tabs(
    ["Emerging Hits", "Pre-Registrations", "All Apps", "App Detail", "Data Quality"]
)

# ==================== TAB 1: Emerging Hits ====================
with tab_emerging:
    st.title("Emerging Hits")

    with st.sidebar:
        period = st.selectbox("Period", [7, 14, 30], index=2, format_func=lambda x: f"{x} days")

        emerging_data = get_emerging_hits(selected_region, days=period)
        em_df = pd.DataFrame(emerging_data) if emerging_data else pd.DataFrame()

        if not em_df.empty:
            genres_em = ["All"] + sorted(em_df["genre"].dropna().unique().tolist())
            selected_genre_em = st.selectbox("Genre", genres_em, key="em_genre")
            if selected_genre_em != "All":
                em_df = em_df[em_df["genre"] == selected_genre_em]

            free_filter_em = st.radio("Pricing", ["All", "Free", "Paid"], horizontal=True, key="em_free")
            if free_filter_em == "Free":
                em_df = em_df[em_df["free"] == 1]
            elif free_filter_em == "Paid":
                em_df = em_df[em_df["free"] == 0]

    if em_df.empty:
        st.warning("No new apps found for this period. Run `python discovery.py` to find apps.")
    else:
        # Metrics row
        new_count = len(em_df)
        top_app = em_df.iloc[0]
        top_name = top_app.get("title", "N/A")
        avg_installs = int(em_df["installs"].fillna(0).mean())
        prereg_count = int(em_df["pre_register"].fillna(0).sum())

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("New Apps", new_count)
        col2.metric("Top Installs", top_name[:25])
        col3.metric("Avg Installs", f"{avg_installs:,}")
        col4.metric("Pre-Regs Found", prereg_count)

        # Add "Days Ago" column
        today = datetime.utcnow().strftime("%Y-%m-%d")
        em_df["days_ago"] = em_df["first_seen_date"].apply(
            lambda x: (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(x, "%Y-%m-%d")).days
            if pd.notna(x) else None
        )

        em_df["store_url"] = "https://play.google.com/store/apps/details?id=" + em_df["app_id"]

        display_cols = {
            "title": "App",
            "store_url": "Store",
            "developer": "Developer",
            "genre": "Genre",
            "installs": "Installs",
            "daily_installs": "Daily Installs",
            "score": "Rating",
            "chart_position": "Chart Pos",
            "first_seen_date": "First Seen",
            "days_ago": "Days Ago",
        }
        available_cols = [c for c in display_cols if c in em_df.columns]
        display_df = em_df[available_cols].rename(columns=display_cols)

        for col in ["Installs", "Daily Installs"]:
            if col in display_df.columns:
                display_df[col] = display_df[col].fillna(0).astype(int)
        if "Rating" in display_df.columns:
            display_df["Rating"] = display_df["Rating"].apply(
                lambda x: f"{x:.1f}" if pd.notna(x) else "-"
            )
        if "Chart Pos" in display_df.columns:
            display_df["Chart Pos"] = display_df["Chart Pos"].apply(
                lambda x: f"#{int(x)}" if pd.notna(x) else "-"
            )

        st.dataframe(
            display_df, use_container_width=True, height=600,
            column_config={"Store": st.column_config.LinkColumn(display_text="Open")},
        )

# ==================== TAB 2: Pre-Registrations ====================
with tab_prereg:
    st.title("Pre-Registrations")

    prereg_apps = get_pre_registrations()
    if not prereg_apps:
        st.info("No pre-registration apps found yet.")
    else:
        pr_df = pd.DataFrame(prereg_apps)
        pr_df["store_url"] = "https://play.google.com/store/apps/details?id=" + pr_df["app_id"]
        display_cols = {
            "title": "App",
            "store_url": "Store",
            "developer": "Developer",
            "genre": "Genre",
            "first_seen_date": "First Seen",
        }
        available_cols = [c for c in display_cols if c in pr_df.columns]
        st.dataframe(
            pr_df[available_cols].rename(columns=display_cols),
            use_container_width=True, height=500,
            column_config={"Store": st.column_config.LinkColumn(display_text="Open")},
        )

# ==================== TAB 3: All Apps ====================
with tab_all:
    st.subheader(f"All Apps — {selected_region.upper()}")

    data = get_all_apps_with_latest(selected_region)
    if data:
        df = pd.DataFrame(data)

        with st.sidebar:
            st.markdown("---")
            st.subheader("All Apps Filters")
            genres = ["All"] + sorted(df["genre"].dropna().unique().tolist())
            selected_genre = st.selectbox("Genre", genres, key="all_genre")
            if selected_genre != "All":
                df = df[df["genre"] == selected_genre]

            free_filter = st.radio("Pricing", ["All", "Free", "Paid"], horizontal=True, key="all_free")
            if free_filter == "Free":
                df = df[df["free"] == 1]
            elif free_filter == "Paid":
                df = df[df["free"] == 0]

            min_installs = st.number_input("Min installs", min_value=0, value=0, step=1000)
            if min_installs > 0:
                df = df[df["installs_today"].fillna(0) >= min_installs]

            status_filter = st.radio("Status", ["All", "Active", "Removed"], horizontal=True, key="all_status")
            if status_filter != "All":
                df = df[df["status"] == status_filter.lower()]

            sort_options = {
                "Daily Installs": "daily_installs",
                "Total Installs": "installs_today",
                "Rating": "score_today",
                "Ratings Count": "ratings_today",
                "First Seen": "first_seen_date",
                "Chart Position": "latest_chart_position",
            }
            sort_by = st.selectbox("Sort by", list(sort_options.keys()))
            ascending = sort_by == "Chart Position"
            df = df.sort_values(sort_options[sort_by], ascending=ascending, na_position="last")
    else:
        df = pd.DataFrame()

    if df.empty:
        st.info("No apps match the current filters.")
    else:
        df["store_url"] = "https://play.google.com/store/apps/details?id=" + df["app_id"]
        display_cols = {
            "title": "App",
            "store_url": "Store",
            "developer": "Developer",
            "genre": "Genre",
            "installs_today": "Installs",
            "daily_installs": "Daily Installs",
            "score_today": "Rating",
            "ratings_today": "Ratings",
            "latest_chart_position": "Chart Pos",
            "latest_chart_type": "Chart",
            "first_seen_date": "First Seen",
            "status": "Status",
        }
        available_cols = [c for c in display_cols if c in df.columns]
        display_df = df[available_cols].rename(columns=display_cols).head(200)

        for col in ["Installs", "Daily Installs", "Ratings"]:
            if col in display_df.columns:
                display_df[col] = display_df[col].fillna(0).astype(int)
        if "Rating" in display_df.columns:
            display_df["Rating"] = display_df["Rating"].apply(
                lambda x: f"{x:.1f}" if pd.notna(x) else "-"
            )
        if "Chart Pos" in display_df.columns:
            display_df["Chart Pos"] = display_df["Chart Pos"].apply(
                lambda x: f"#{int(x)}" if pd.notna(x) else "-"
            )

        st.dataframe(
            display_df, use_container_width=True, height=600,
            column_config={"Store": st.column_config.LinkColumn(display_text="Open")},
        )

# ==================== TAB 4: App Detail ====================
with tab_detail:
    st.subheader("App Detail")

    detail_data = get_all_apps_with_latest(selected_region)
    detail_df = pd.DataFrame(detail_data) if detail_data else pd.DataFrame()

    if detail_df.empty:
        st.info("No apps available.")
    else:
        app_options = {row["title"]: row["app_id"] for _, row in detail_df.iterrows() if row.get("title")}
        if not app_options:
            st.info("No apps with titles found.")
        else:
            selected_title = st.selectbox("Select app", list(app_options.keys()))
            selected_app_id = app_options[selected_title]

            app_info = get_app_details(selected_app_id)
            if app_info:
                col1, col2, col3 = st.columns([1, 2, 2])
                with col1:
                    if app_info.get("icon_url"):
                        st.image(app_info["icon_url"], width=100)
                with col2:
                    st.markdown(f"**{app_info['title']}**")
                    st.caption(f"{app_info.get('developer', '')} | {app_info.get('genre', '')}")
                    st.caption(f"App ID: `{selected_app_id}`")
                with col3:
                    st.caption(f"First seen: {app_info.get('first_seen_date', '-')}")
                    st.caption(f"Released: {app_info.get('released_date', '-')}")
                    st.caption(f"Status: {app_info.get('status', '-')}")

            # Install & rating history
            st.markdown("---")
            detail_region = st.selectbox("Region for history", available_regions, key="detail_region")
            history = get_app_history(selected_app_id, detail_region)

            if history and len(history) >= 2:
                hist_df = pd.DataFrame(history)

                estimates = estimate_daily_installs(history)
                if estimates:
                    est_df = pd.DataFrame(estimates)
                    hist_df = hist_df.iloc[1:].reset_index(drop=True)
                    hist_df["daily_installs_est"] = est_df["daily_installs"]
                    hist_df["confidence"] = est_df["confidence"]

                col1, col2 = st.columns(2)
                with col1:
                    fig = px.line(hist_df, x="date", y="real_installs", title="Total Installs")
                    st.plotly_chart(fig, use_container_width=True)
                with col2:
                    if "daily_installs_est" in hist_df.columns:
                        color_map = {"high": "green", "medium": "orange", "low": "red"}
                        fig = px.bar(
                            hist_df, x="date", y="daily_installs_est",
                            color="confidence", color_discrete_map=color_map,
                            title="Estimated Daily Installs",
                        )
                        st.plotly_chart(fig, use_container_width=True)

                col1, col2 = st.columns(2)
                with col1:
                    fig = px.line(hist_df, x="date", y="score", title="Rating Over Time")
                    fig.update_yaxes(range=[0, 5])
                    st.plotly_chart(fig, use_container_width=True)
                with col2:
                    fig = px.line(hist_df, x="date", y="ratings_count", title="Ratings Count")
                    st.plotly_chart(fig, use_container_width=True)

                # Rounding artifacts
                artifacts = detect_rounding_artifacts(history)
                if artifacts:
                    st.warning(f"Rounding artifacts detected on {len(artifacts)} day(s)")
                    st.json(artifacts)
            elif history:
                st.info("Only 1 day of data. Need 2+ days for charts.")
                st.json(history[0])
            else:
                st.info(f"No history for {detail_region.upper()} yet.")

            # Chart position history
            chart_hist = get_app_chart_history(selected_app_id, detail_region)
            if chart_hist:
                st.markdown("### Chart Position History")
                ch_df = pd.DataFrame(chart_hist)
                fig = px.line(
                    ch_df, x="date", y="position", color="chart_type",
                    title="Chart Positions (lower = better)",
                )
                fig.update_yaxes(autorange="reversed")
                st.plotly_chart(fig, use_container_width=True)

            # Cross-region comparison
            if len(available_regions) > 1:
                st.markdown("### Cross-Region Comparison")
                region_data = {}
                for r in available_regions:
                    h = get_app_history(selected_app_id, r)
                    if h:
                        region_data[r] = h[-1]

                if region_data:
                    comp_df = pd.DataFrame([
                        {"Region": r.upper(), "Installs": d.get("real_installs", 0),
                         "Rating": d.get("score", 0), "Ratings": d.get("ratings_count", 0)}
                        for r, d in region_data.items()
                    ])
                    st.dataframe(comp_df, use_container_width=True)

                    warnings = cross_validate_regions(region_data)
                    if warnings:
                        for w in warnings:
                            st.warning(w)

# ==================== TAB 5: Data Quality ====================
with tab_quality:
    st.subheader("Data Quality & Crawl Log")

    logs = get_crawl_logs(30)
    if logs:
        log_df = pd.DataFrame(logs)
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Last Crawl", log_df.iloc[0]["timestamp"][:19] if len(log_df) > 0 else "-")
        with col2:
            total_errors = log_df["apps_failed"].sum()
            total_processed = log_df["apps_processed"].sum()
            rate = (1 - total_errors / max(total_processed, 1)) * 100
            st.metric("Success Rate (last 30 runs)", f"{rate:.1f}%")

        display_log = log_df[["timestamp", "job_type", "region", "apps_processed", "apps_failed", "duration_sec"]].copy()
        display_log["timestamp"] = display_log["timestamp"].str[:19]
        st.dataframe(display_log, use_container_width=True, height=400)

        # Freshness by region
        st.markdown("### Data Freshness by Region")
        for region in available_regions:
            region_logs = log_df[log_df["region"] == region]
            if not region_logs.empty:
                last = region_logs.iloc[0]["timestamp"][:19]
                st.caption(f"{region.upper()}: last update {last}")
            else:
                st.caption(f"{region.upper()}: no data")
    else:
        st.info("No crawl logs yet. Run discovery.py or tracker.py first.")
