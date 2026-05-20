# Инструкция: Сервис мониторинга предрегистраций Google Play

## Что мы строим

Автоматический сервис, который:
- Каждые несколько часов сканирует Google Play на новые приложения и игры
- Находит те, что находятся в статусе предрегистрации
- Хранит историю установок и считает daily installs (как asospy.com)
- Показывает всё в удобной таблице с фильтрами

---

## Стек технологий

| Компонент | Технология | Стоимость |
|---|---|---|
| Парсинг данных | Python + google-play-scraper | Бесплатно |
| База данных | SQLite (локально) или Google Sheets | Бесплатно |
| Расписание задач | GitHub Actions или cron на VPS | Бесплатно / ~$5/мес |
| Веб-интерфейс | Streamlit | Бесплатно |
| Хостинг | Streamlit Cloud или VPS | Бесплатно / ~$5/мес |

Минимальный вариант (всё бесплатно): GitHub Actions + SQLite + Streamlit Cloud.

---

## Часть 1. Структура проекта

Создать папку `prereg-monitor` со следующей структурой:

```
prereg-monitor/
├── crawler.py          # Парсер — собирает новые приложения
├── tracker.py          # Трекер — обновляет installs каждый день
├── database.py         # Работа с базой данных
├── app.py              # Веб-интерфейс на Streamlit
├── requirements.txt    # Зависимости
└── .github/
    └── workflows/
        ├── crawl.yml   # Расписание краулера (каждые 6 часов)
        └── track.yml   # Расписание трекера (раз в сутки)
```

---

## Часть 2. Установка зависимостей

Файл `requirements.txt`:

```
google-play-scraper==1.2.7
requests==2.31.0
pandas==2.1.0
streamlit==1.29.0
schedule==1.2.0
```

Установка:
```bash
pip install -r requirements.txt
```

---

## Часть 3. База данных (`database.py`)

```python
import sqlite3
import os
from datetime import datetime

DB_PATH = "prereg.db"

def init_db():
    """Создаём таблицы при первом запуске"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Таблица приложений
    c.execute("""
        CREATE TABLE IF NOT EXISTS apps (
            app_id          TEXT PRIMARY KEY,
            title           TEXT,
            developer       TEXT,
            genre           TEXT,
            icon_url        TEXT,
            summary         TEXT,
            pre_register    INTEGER DEFAULT 0,
            first_seen      TEXT,
            released        TEXT,
            url             TEXT
        )
    """)

    # Таблица снапшотов installs (история по дням)
    c.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id          TEXT,
            date            TEXT,
            installs        INTEGER DEFAULT 0,
            ratings         INTEGER DEFAULT 0,
            score           REAL,
            UNIQUE(app_id, date)
        )
    """)

    conn.commit()
    conn.close()
    print("База данных инициализирована")


def save_app(app_data: dict):
    """Сохраняем или обновляем приложение"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO apps
            (app_id, title, developer, genre, icon_url, summary, pre_register, first_seen, released, url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        app_data.get("app_id"),
        app_data.get("title"),
        app_data.get("developer"),
        app_data.get("genre"),
        app_data.get("icon_url"),
        app_data.get("summary"),
        1 if app_data.get("pre_register") else 0,
        app_data.get("first_seen", datetime.now().strftime("%Y-%m-%d")),
        app_data.get("released"),
        app_data.get("url"),
    ))
    conn.commit()
    conn.close()


def save_snapshot(app_id: str, installs: int, ratings: int, score: float):
    """Сохраняем дневной снапшот installs"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("""
        INSERT OR REPLACE INTO snapshots (app_id, date, installs, ratings, score)
        VALUES (?, ?, ?, ?, ?)
    """, (app_id, today, installs, ratings, score))
    conn.commit()
    conn.close()


def get_all_apps():
    """Все приложения с последним снапшотом и расчётом daily installs"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("""
        SELECT
            a.*,
            s1.installs      AS installs_today,
            s1.ratings       AS ratings_today,
            s1.score         AS score_today,
            s1.date          AS snapshot_date,
            -- daily installs = разница между сегодня и вчера
            (s1.installs - COALESCE(s2.installs, 0)) AS daily_installs
        FROM apps a
        LEFT JOIN snapshots s1
            ON a.app_id = s1.app_id
            AND s1.date = (
                SELECT MAX(date) FROM snapshots WHERE app_id = a.app_id
            )
        LEFT JOIN snapshots s2
            ON a.app_id = s2.app_id
            AND s2.date = (
                SELECT MAX(date) FROM snapshots
                WHERE app_id = a.app_id AND date < s1.date
            )
        ORDER BY daily_installs DESC
    """)

    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows


def get_app_history(app_id: str):
    """История installs по дням для конкретного приложения"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT date, installs, ratings, score
        FROM snapshots
        WHERE app_id = ?
        ORDER BY date ASC
    """, (app_id,))
    rows = c.fetchall()
    conn.close()
    return rows


def get_all_app_ids():
    """Список всех app_id для обновления снапшотов"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT app_id FROM apps")
    ids = [row[0] for row in c.fetchall()]
    conn.close()
    return ids
```

---

## Часть 4. Краулер новых приложений (`crawler.py`)

Этот скрипт запускается каждые 6 часов и ищет новые приложения в предрегистрации.

```python
import time
import re
import requests
from datetime import datetime
from google_play_scraper import app as gps_app
from database import init_db, save_app, save_snapshot

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# URL коллекций предрегистраций Google Play
COLLECTION_URLS = [
    "https://play.google.com/store/apps/collection/promotion_3000000d51_pre_registration_games?hl=en&gl=US",
    "https://play.google.com/store/apps/collection/promotion_3000000d52_pre_registration_apps?hl=en&gl=US",
    "https://play.google.com/store/apps/collection/cluster?clp=pre_registration&hl=en&gl=US",
]

# Дополнительно ищем через поиск по ключевым словам
SEARCH_QUERIES = [
    "pre-register 2025",
    "coming soon pre-register game",
    "pre-registration reward android",
]


def extract_app_ids(html: str) -> list:
    pattern = r"/store/apps/details\?id=([\w\.]+)"
    ids = re.findall(pattern, html)
    return list(dict.fromkeys(ids))


def crawl_collections() -> list:
    """Парсим официальные коллекции предрегистраций"""
    found = []
    for url in COLLECTION_URLS:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                ids = extract_app_ids(resp.text)
                print(f"  Collection: {len(ids)} ids from {url[:60]}...")
                found.extend(ids)
        except Exception as e:
            print(f"  Error fetching {url[:60]}: {e}")
        time.sleep(1)
    return list(dict.fromkeys(found))


def crawl_search(queries: list) -> list:
    """Ищем через Google Search как запасной метод"""
    found = []
    hdrs = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    for query in queries:
        full_query = f"site:play.google.com/store/apps/details {query}"
        for page in range(2):
            params = {"q": full_query, "start": page * 10, "num": 10}
            try:
                r = requests.get("https://www.google.com/search", params=params, headers=hdrs, timeout=10)
                ids = extract_app_ids(r.text)
                found.extend(ids)
                print(f"  Search '{query}' page {page+1}: {len(ids)} ids")
                time.sleep(2)
            except Exception as e:
                print(f"  Search error: {e}")
    return list(dict.fromkeys(found))


def enrich_and_save(app_ids: list):
    """Получаем детали и сохраняем в БД"""
    saved = 0
    for i, app_id in enumerate(app_ids):
        try:
            d = gps_app(app_id, lang="en", country="us")

            # Сохраняем только предрегистрации (или 0 installs — тоже интересно)
            is_prereg = d.get("preRegister", False)
            real_installs = d.get("realInstalls", 0) or 0

            if is_prereg or real_installs == 0:
                app_data = {
                    "app_id":       app_id,
                    "title":        d.get("title", ""),
                    "developer":    d.get("developer", ""),
                    "genre":        d.get("genre", ""),
                    "icon_url":     d.get("icon", ""),
                    "summary":      (d.get("summary") or "")[:200],
                    "pre_register": is_prereg,
                    "first_seen":   datetime.now().strftime("%Y-%m-%d"),
                    "released":     d.get("released", ""),
                    "url":          f"https://play.google.com/store/apps/details?id={app_id}",
                }
                save_app(app_data)

                # Сразу сохраняем первый снапшот
                save_snapshot(
                    app_id=app_id,
                    installs=real_installs,
                    ratings=d.get("ratings") or 0,
                    score=d.get("score") or 0.0,
                )
                saved += 1
                print(f"  [{i+1}/{len(app_ids)}] SAVED: {d.get('title', app_id)[:40]}")
            else:
                print(f"  [{i+1}/{len(app_ids)}] SKIP (has installs): {d.get('title', app_id)[:40]}")

        except Exception as e:
            print(f"  [{i+1}/{len(app_ids)}] ERROR {app_id}: {e}")

        time.sleep(0.5)

    return saved


def run():
    print(f"\n=== Crawler started: {datetime.now()} ===")
    init_db()

    # 1. Парсим коллекции
    print("\n[1] Crawling collections...")
    ids = crawl_collections()

    # 2. Если мало — добавляем из поиска
    if len(ids) < 10:
        print("\n[2] Fallback to Google Search...")
        ids += crawl_search(SEARCH_QUERIES)
        ids = list(dict.fromkeys(ids))

    print(f"\nTotal unique app ids: {len(ids)}")

    # 3. Обогащаем и сохраняем
    print("\n[3] Enriching and saving...")
    saved = enrich_and_save(ids)

    print(f"\n=== Done. Saved/updated: {saved} apps ===")


if __name__ == "__main__":
    run()
```

---

## Часть 5. Трекер installs (`tracker.py`)

Запускается раз в сутки и обновляет installs для всех уже известных приложений. Именно из этих данных считается daily installs.

```python
import time
from datetime import datetime
from google_play_scraper import app as gps_app
from database import init_db, save_snapshot, get_all_app_ids

def run():
    print(f"\n=== Tracker started: {datetime.now()} ===")
    init_db()

    app_ids = get_all_app_ids()
    print(f"Updating {len(app_ids)} apps...\n")

    updated = 0
    for i, app_id in enumerate(app_ids):
        try:
            d = gps_app(app_id, lang="en", country="us")
            save_snapshot(
                app_id=app_id,
                installs=d.get("realInstalls") or 0,
                ratings=d.get("ratings") or 0,
                score=d.get("score") or 0.0,
            )
            title = d.get("title", app_id)[:40]
            installs = d.get("realInstalls") or 0
            print(f"  [{i+1}/{len(app_ids)}] {title} — installs: {installs:,}")
            updated += 1
        except Exception as e:
            print(f"  [{i+1}/{len(app_ids)}] ERROR {app_id}: {e}")

        time.sleep(0.5)

    print(f"\n=== Done. Updated: {updated} apps ===")


if __name__ == "__main__":
    run()
```

---

## Часть 6. Веб-интерфейс (`app.py`)

```python
import streamlit as st
import pandas as pd
from database import init_db, get_all_apps, get_app_history

st.set_page_config(
    page_title="Pre-reg Monitor",
    page_icon="🎮",
    layout="wide"
)

st.title("🎮 Google Play — Мониторинг предрегистраций")

init_db()
data = get_all_apps()

if not data:
    st.warning("Данных нет. Запусти сначала `python crawler.py`")
    st.stop()

df = pd.DataFrame(data)

# ── Боковая панель: фильтры ──────────────────────────────────────────────────
with st.sidebar:
    st.header("Фильтры")

    only_prereg = st.checkbox("Только предрегистрации", value=True)
    if only_prereg:
        df = df[df["pre_register"] == 1]

    genres = ["Все"] + sorted(df["genre"].dropna().unique().tolist())
    selected_genre = st.selectbox("Жанр", genres)
    if selected_genre != "Все":
        df = df[df["genre"] == selected_genre]

    min_daily = st.number_input("Минимум daily installs", min_value=0, value=0)
    if min_daily > 0:
        df = df[df["daily_installs"] >= min_daily]

    sort_by = st.selectbox("Сортировка", ["daily_installs", "installs_today", "ratings_today", "first_seen"])
    df = df.sort_values(sort_by, ascending=False)

# ── Метрики вверху ────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
col1.metric("Всего приложений", len(df))
col2.metric("Предрегистраций", int(df["pre_register"].sum()))
col3.metric("Суммарно daily installs", f"{int(df['daily_installs'].fillna(0).sum()):,}")
col4.metric("Дата обновления", df["snapshot_date"].dropna().max() or "—")

st.divider()

# ── Таблица ───────────────────────────────────────────────────────────────────
for _, row in df.iterrows():
    with st.container():
        cols = st.columns([0.5, 3, 1.5, 1, 1, 1, 1, 1])

        # Иконка
        if row.get("icon_url"):
            cols[0].image(row["icon_url"], width=48)

        # Название + разработчик
        with cols[1]:
            st.markdown(f"**[{row['title']}]({row['url']})**")
            st.caption(f"{row.get('developer','')} · {row.get('genre','')}")

        # Метрики
        cols[2].metric("Daily installs", f"{int(row.get('daily_installs') or 0):,}")
        cols[3].metric("Всего installs", f"{int(row.get('installs_today') or 0):,}")
        cols[4].metric("Рейтинг", f"{row.get('score_today') or 0:.1f} ⭐" if row.get('score_today') else "—")
        cols[5].metric("Отзывов", f"{int(row.get('ratings_today') or 0):,}")

        status = "🔔 Pre-reg" if row.get("pre_register") else "🕐 New"
        cols[6].metric("Статус", status)
        cols[7].caption(f"Добавлен:\n{row.get('first_seen','')}")

    st.divider()

# ── График истории для выбранного приложения ──────────────────────────────────
st.subheader("📈 История installs")
app_titles = {row["title"]: row["app_id"] for row in data if row.get("title")}
selected_title = st.selectbox("Выбери приложение", list(app_titles.keys()))

if selected_title:
    app_id = app_titles[selected_title]
    history = get_app_history(app_id)
    if history:
        hist_df = pd.DataFrame(history, columns=["date", "installs", "ratings", "score"])
        hist_df["daily_installs"] = hist_df["installs"].diff().fillna(0).clip(lower=0)
        st.line_chart(hist_df.set_index("date")[["installs", "daily_installs"]])
    else:
        st.info("История пока пустая — нужно несколько дней данных")
```

---

## Часть 7. Автозапуск через GitHub Actions

### Файл `.github/workflows/crawl.yml` (краулер каждые 6 часов)

```yaml
name: Crawl new pre-reg apps

on:
  schedule:
    - cron: "0 */6 * * *"   # каждые 6 часов
  workflow_dispatch:          # или вручную

jobs:
  crawl:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Restore database
        uses: actions/cache@v3
        with:
          path: prereg.db
          key: prereg-db-${{ github.run_id }}
          restore-keys: prereg-db-

      - name: Run crawler
        run: python crawler.py

      - name: Save database
        uses: actions/cache@v3
        with:
          path: prereg.db
          key: prereg-db-${{ github.run_id }}
```

### Файл `.github/workflows/track.yml` (трекер раз в сутки)

```yaml
name: Track daily installs

on:
  schedule:
    - cron: "0 9 * * *"    # каждый день в 9:00 UTC
  workflow_dispatch:

jobs:
  track:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Restore database
        uses: actions/cache@v3
        with:
          path: prereg.db
          key: prereg-db-${{ github.run_id }}
          restore-keys: prereg-db-

      - name: Run tracker
        run: python tracker.py

      - name: Save database
        uses: actions/cache@v3
        with:
          path: prereg.db
          key: prereg-db-${{ github.run_id }}
```

> **Важно:** GitHub Actions cache — временное хранилище. Для продакшена лучше хранить `prereg.db` в отдельном репозитории или на VPS.

---

## Часть 8. Запуск веб-интерфейса

### Локально (для тестирования)

```bash
streamlit run app.py
# Откроется браузер на http://localhost:8501
```

### В облаке (бесплатно через Streamlit Cloud)

1. Загрузить проект на GitHub
2. Зайти на [share.streamlit.io](https://share.streamlit.io)
3. Подключить репозиторий → указать `app.py` как главный файл
4. Нажать Deploy

---

## Часть 9. Пошаговый запуск (с нуля)

```bash
# 1. Клонируем / создаём репозиторий
git clone https://github.com/YOUR_USERNAME/prereg-monitor
cd prereg-monitor

# 2. Устанавливаем зависимости
pip install -r requirements.txt

# 3. Создаём базу и запускаем первый краул
python crawler.py

# 4. После краула — обновляем installs
python tracker.py

# 5. Запускаем интерфейс
streamlit run app.py
```

---

## Часть 10. Как расширить сервис

| Что добавить | Как |
|---|---|
| Уведомления в Telegram | Бот на `python-telegram-bot`, отправлять при daily_installs > N |
| App Store (iOS) | Библиотека `itunes-app-scraper` или `app-store-scraper` |
| Экспорт в Google Sheets | Библиотека `gspread` |
| Фильтр по странам | Параметр `country="ru"` в `gps_app()` |
| Поиск по ключевым словам | `google_play_scraper.search("pre-register rpg")` |
| VPS вместо GitHub Actions | Любой Ubuntu VPS + `crontab -e` для расписания |

---

## Примечания

- **Точность daily installs** — Google Play показывает installs округлённо (`realInstalls`). У новых приложений с малым числом установок данные могут быть неточными.
- **Лимиты запросов** — `google-play-scraper` делает запросы к Google Play. При слишком частых запросах может прийти временный бан по IP. Паузы `time.sleep(0.5)` в коде это смягчают.
- **GitHub Actions** — бесплатный план даёт 2000 минут в месяц. Краулер на 50 приложений занимает ~3 минуты. При расписании каждые 6 часов = 4 запуска × 3 мин × 30 дней = ~360 минут. Укладываемся.
