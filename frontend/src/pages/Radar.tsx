import { useNavigate } from "react-router-dom";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Game, Page, api } from "../api";
import { useMe } from "../App";
import { Chips, FGroup, LazyInput, Seg, activeCount, useFiltersOpen, useUrlFilters } from "../components/filters";
import { Empty, Flags, Loader, Pager, Score, SortTh, Sparkline } from "../components/ui";
import { SavedViews } from "../components/views";
import { fmtAccel, fmtAge, fmtN, fmtRating } from "../format";

export const GAME_DEFAULTS: Record<string, string> = {
  q: "", genres: "", max_age: "180", min_v7: "", min_accel: "", min_trend: "", min_installs: "", max_installs: "",
  min_rating: "", min_countries: "", min_search: "", hide_flags: "major,hc_publisher,franchise", max_dev_installs: "",
  ads: "", iap: "", prereg: "include", soft_launch: "include", charts: "", marks: "hide_rejected", sort: "trend_score", dir: "desc", page: "1",
};

const GENRES: [string, string][] = [
  ["GAME_PUZZLE", "Головоломки"], ["GAME_CASUAL", "Казуальные"], ["GAME_SIMULATION", "Симуляторы"],
  ["GAME_ARCADE", "Аркады"], ["GAME_ACTION", "Экшен"], ["GAME_STRATEGY", "Стратегии"],
  ["GAME_ROLE_PLAYING", "Ролевые"], ["GAME_ADVENTURE", "Приключения"], ["GAME_RACING", "Гонки"],
  ["GAME_SPORTS", "Спорт"], ["GAME_BOARD", "Настольные"], ["GAME_CARD", "Карточные"], ["GAME_WORD", "Словесные"],
  ["GAME_TRIVIA", "Викторины"], ["GAME_EDUCATIONAL", "Обучающие"], ["GAME_MUSIC", "Музыкальные"], ["GAME_CASINO", "Казино"],
];

const FLAG_OPTIONS: [string, string, string][] = [
  ["major", "Крупные издатели", "Tencent, Playrix, Ubisoft…"],
  ["hc_publisher", "Паблишеры гиперказуала", "Voodoo, SayGames, Azur — рост на закупке"],
  ["franchise", "Франшизы и бренды", "Marvel, Pokémon, Subway Surfers…"],
  ["big_dev", "Студии с хитом 50M+", "уже есть аудитория"],
  ["big_portfolio", "Портфель 40+ игр", "фабрики приложений"],
];

export default function Radar() {
  const me = useMe();
  const f = useUrlFilters(GAME_DEFAULTS);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const params = f.all();
  const panel = useFiltersOpen();
  const active = activeCount(params, GAME_DEFAULTS);

  const data = useQuery({
    queryKey: ["games", params],
    queryFn: () => api<Page<Game>>("/games", { params }),
    placeholderData: keepPreviousData,
  });

  const mark = useMutation({
    mutationFn: ({ id, status, note }: { id: string; status: string | null; note: string | null }) =>
      api(`/games/${encodeURIComponent(id)}/mark`, { method: "PUT", body: { status, note } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["games"] }),
  });

  const sortBy = (field: string) => {
    if (f.get("sort") === field) f.set({ dir: f.get("dir") === "desc" ? "asc" : "desc" });
    else f.set({ sort: field, dir: field === "age_days" || field === "best_rank" ? "asc" : "desc" });
  };
  const hidden = new Set(f.get("hide_flags").split(",").filter(Boolean));
  const toggleFlag = (flag: string) => {
    hidden.has(flag) ? hidden.delete(flag) : hidden.add(flag);
    f.set({ hide_flags: [...hidden].join(",") });
  };
  const exportUrl = `/api/games/export.csv?${new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "")).toString()}`;
  const sort = f.get("sort");
  const dir = f.get("dir");

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Радар игр</h1>
          <p className="page-sub">
            Молодые игры, которые растут прямо сейчас. Trend Score учитывает скорость установок за 7 дней, ускорение, возраст,
            охват чартов по странам и рейтинг. Бренды и закупщики трафика по умолчанию скрыты.
          </p>
        </div>
      </div>

      <div className={`radar ${panel.open ? "" : "collapsed"}`}>
        {panel.open && (
        <aside className="panel filters">
          <FGroup title="Поиск">
            <LazyInput value={f.get("q")} onCommit={(v) => f.set({ q: v })} placeholder="название, студия, id" />
          </FGroup>
          <FGroup title="Мои фильтры">
            <SavedViews page="games" current={() => f.all()} onApply={(p) => f.replaceAll(p)} />
          </FGroup>
          <FGroup title="Возраст игры" hint="с даты релиза">
            <Chips
              options={[["14", "≤ 2 нед"], ["30", "≤ 30 дн"], ["60", "≤ 60"], ["90", "≤ 90"], ["180", "≤ 180"], ["365", "≤ 1 года"]]}
              value={f.get("max_age")}
              onChange={(v) => f.set({ max_age: v })}
            />
          </FGroup>
          <FGroup title="Скрыть" hint="бренд ≠ спрос">
            {FLAG_OPTIONS.map(([flag, label, hint]) => (
              <label key={flag} className="check" title={hint}>
                <input type="checkbox" checked={hidden.has(flag)} onChange={() => toggleFlag(flag)} />
                <span>
                  {label}
                  <br />
                  <span className="faint" style={{ fontSize: 11 }}>{hint}</span>
                </span>
              </label>
            ))}
          </FGroup>
          <FGroup title="Жанры">
            <Chips multi options={GENRES} value={f.get("genres")} onChange={(v) => f.set({ genres: v })} />
          </FGroup>
          <FGroup title="Скорость" hint="установок в день, 7 дн">
            <Chips
              options={[["100", "100+"], ["1000", "1K+"], ["10000", "10K+"], ["50000", "50K+"]]}
              value={f.get("min_v7")}
              onChange={(v) => f.set({ min_v7: v })}
            />
          </FGroup>
          <FGroup title="Ускорение" hint="неделя к неделе">
            <Chips
              options={[["1.2", "×1.2+"], ["1.5", "×1.5+"], ["2", "×2+"], ["3", "×3+"]]}
              value={f.get("min_accel")}
              onChange={(v) => f.set({ min_accel: v })}
            />
          </FGroup>
          <FGroup title="Установки всего">
            <div className="row">
              <LazyInput type="number" value={f.get("min_installs")} onCommit={(v) => f.set({ min_installs: v })} placeholder="от" />
              <LazyInput type="number" value={f.get("max_installs")} onCommit={(v) => f.set({ max_installs: v })} placeholder="до" />
            </div>
          </FGroup>
          <FGroup title="Чарты">
            <Seg
              options={[["", "Все"], ["top_new", "Top New"], ["trending", "Movers"], ["any", "В любом"]]}
              value={f.get("charts")}
              onChange={(v) => f.set({ charts: v })}
            />
            <div style={{ marginTop: 8 }}>
              <Chips
                options={[["3", "3+ стран"], ["10", "10+"], ["20", "20+"]]}
                value={f.get("min_countries")}
                onChange={(v) => f.set({ min_countries: v })}
              />
            </div>
          </FGroup>
          <FGroup title="Органика из поиска" hint="видимость по ключам">
            <Chips
              options={[["10", "10+"], ["30", "30+"], ["60", "60+"]]}
              value={f.get("min_search")}
              onChange={(v) => f.set({ min_search: v })}
            />
          </FGroup>
          <FGroup title="Trend Score">
            <Chips
              options={[["30", "30+"], ["50", "50+"], ["70", "70+"]]}
              value={f.get("min_trend")}
              onChange={(v) => f.set({ min_trend: v })}
            />
          </FGroup>
          <FGroup title="Рейтинг">
            <Chips
              options={[["4", "4.0+"], ["4.3", "4.3+"], ["4.5", "4.5+"]]}
              value={f.get("min_rating")}
              onChange={(v) => f.set({ min_rating: v })}
            />
          </FGroup>
          <FGroup title="Монетизация">
            <div className="stack" style={{ gap: 6 }}>
              <div className="row">
                <span className="muted" style={{ width: 70, fontSize: 12 }}>Реклама</span>
                <Seg options={[["", "Все"], ["yes", "Есть"], ["no", "Нет"]]} value={f.get("ads")} onChange={(v) => f.set({ ads: v })} />
              </div>
              <div className="row">
                <span className="muted" style={{ width: 70, fontSize: 12 }}>Покупки</span>
                <Seg options={[["", "Все"], ["yes", "Есть"], ["no", "Нет"]]} value={f.get("iap")} onChange={(v) => f.set({ iap: v })} />
              </div>
            </div>
          </FGroup>
          <FGroup title="Предрегистрация">
            <Seg
              options={[["include", "Все"], ["only", "Только"], ["exclude", "Без"]]}
              value={f.get("prereg")}
              onChange={(v) => f.set({ prereg: v })}
            />
          </FGroup>
          <FGroup title="Софт-лонч" hint="тест в части стран до релиза">
            <Seg
              options={[["include", "Все"], ["only", "Только"], ["exclude", "Без"]]}
              value={f.get("soft_launch")}
              onChange={(v) => f.set({ soft_launch: v })}
            />
          </FGroup>
          <FGroup title="Отметки команды">
            <Seg
              options={[["hide_rejected", "Без отброш."], ["interesting", "★"], ["in_work", "В работе"], ["unmarked", "Новые"], ["all", "Все"]]}
              value={f.get("marks")}
              onChange={(v) => f.set({ marks: v })}
            />
          </FGroup>
          <div className="fgroup">
            <button className="btn sm ghost" onClick={f.reset}>
              Сбросить всё
            </button>
          </div>
        </aside>
        )}

        <section style={{ minWidth: 0 }}>
          <div className="toolbar">
            <button className={`btn sm ${active ? "primary" : ""}`} onClick={panel.toggle}>
              {panel.open ? "← Скрыть фильтры" : `Фильтры${active ? ` · ${active}` : ""}`}
            </button>
            <span className="count">
              {data.data ? `${data.data.total.toLocaleString("ru-RU")} игр` : "…"}
              {data.isFetching && !data.isLoading ? " · обновление" : ""}
            </span>
            {me.plan.export && (
              <a className="btn sm" href={exportUrl}>
                ↓ CSV
              </a>
            )}
          </div>
          {data.data?.limited_to && data.data.total > data.data.limited_to && (
            <div className="banner">Тариф показывает первые {data.data.limited_to} строк.</div>
          )}
          {data.isLoading ? (
            <Loader />
          ) : !data.data?.items.length ? (
            <div className="panel">
              <Empty title="Ничего не найдено">
                Ослабьте фильтры или подождите: сбор данных идёт каждый день, история копится с первого запуска.
              </Empty>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th />
                    <SortTh label="Игра" field="title" sort={sort} dir={dir} onSort={sortBy} />
                    <SortTh label="Score" field="trend_score" sort={sort} dir={dir} onSort={sortBy} />
                    <th>Жанр</th>
                    <SortTh label="Возраст" field="age_days" sort={sort} dir={dir} onSort={sortBy} right />
                    <SortTh label="Установки" field="installs" sort={sort} dir={dir} onSort={sortBy} right />
                    <SortTh label="В день" field="v7" sort={sort} dir={dir} onSort={sortBy} right title="Среднее за 7 дней, с поправкой на задержку Google" />
                    <th title="Установки по дням за 30 дней. Пунктир — Google ещё не обновил счётчик">30 дней</th>
                    <SortTh label="Ускор." field="accel" sort={sort} dir={dir} onSort={sortBy} right title="Скорость этой недели к прошлой" />
                    <SortTh label="Страны" field="countries" sort={sort} dir={dir} onSort={sortBy} right title="В Top New Free / Top Free по странам" />
                    <SortTh label="Поиск" field="search_visibility" sort={sort} dir={dir} onSort={sortBy} right title="Видимость в поиске по ключевым словам" />
                    <SortTh label="★" field="rating" sort={sort} dir={dir} onSort={sortBy} right />
                  </tr>
                </thead>
                <tbody>
                  {data.data.items.map((g, i) => (
                    <tr key={g.app_id} className="clickable" style={{ animationDelay: `${Math.min(i, 20) * 18}ms` }} onClick={() => navigate(`/game/${encodeURIComponent(g.app_id)}`)}>
                      <td onClick={(e) => e.stopPropagation()}>
                        <MarkButtons game={g} onMark={(status) => mark.mutate({ id: g.app_id, status, note: g.note })} />
                      </td>
                      <td>
                        <div className="app-cell">
                          {g.icon_url ? <img className="app-icon" src={g.icon_url} alt="" loading="lazy" /> : <div className="app-icon" />}
                          <div className="app-meta">
                            <div className="app-title">{g.title || g.app_id}</div>
                            <div className="app-dev">
                              {g.developer}
                              {" "}
                              <Flags flags={g.brand_flags} prereg={g.pre_register} age={g.soft_launch ? null : g.age_days} softLaunch={g.soft_launch_markets} />
                            </div>
                          </div>
                        </div>
                      </td>
                      <td>
                        <Score value={g.trend_score} />
                      </td>
                      <td className="muted">{g.genre}</td>
                      <td className="r num">{g.pre_register ? <span className="accent">скоро</span> : fmtAge(g.age_days)}</td>
                      <td className="r num">{fmtN(g.installs)}</td>
                      <td
                        className="r num"
                        title={
                          g.soft_launch && g.v7 === null
                            ? "Установки включают месяцы софт-лонча, поэтому среднее не считаем — ждём реальную скорость за несколько дней"
                            : g.score_parts?.estimated
                              ? "Оценка: установки ÷ возраст. Реальная скорость появится после нескольких дней наблюдений"
                              : "Реальная скорость за 7 дней"
                        }
                      >
                        {g.score_parts?.estimated ? <span className="faint">~</span> : null}
                        {fmtN(g.v7)}
                      </td>
                      <td>
                        <Sparkline data={g.spark || []} />
                      </td>
                      <td className={`r num ${g.accel && g.accel >= 1.2 ? "delta-up" : g.accel && g.accel < 0.8 ? "delta-down" : ""}`}>{fmtAccel(g.accel)}</td>
                      <td className="r num">
                        {g.new_countries + g.top_countries}
                        {g.trending_countries > 0 && <span className="accent" title="Movers & Shakers"> ↗{g.trending_countries}</span>}
                        {g.breadth_delta7 !== 0 && (
                          <span className={g.breadth_delta7 > 0 ? "delta-up" : "delta-down"} style={{ fontSize: 11 }}>
                            {" "}
                            {g.breadth_delta7 > 0 ? "+" : ""}
                            {g.breadth_delta7}
                          </span>
                        )}
                      </td>
                      <td className="r num">{g.search_visibility ? Math.round(g.search_visibility) : <span className="faint">—</span>}</td>
                      <td className="r num">{fmtRating(g.rating)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {data.data && (
            <Pager page={Number(f.get("page")) || 1} pageSize={data.data.page_size} total={Math.min(data.data.total, data.data.limited_to ?? Infinity)} onPage={(p) => f.set({ page: String(p) }, false)} />
          )}
        </section>
      </div>
    </>
  );
}

export function MarkButtons({ game, onMark }: { game: { mark: string | null }; onMark: (s: string | null) => void }) {
  const btn = (status: string, icon: string, title: string) => (
    <button className={`${status} ${game.mark === status ? "on" : ""}`} title={title} onClick={() => onMark(game.mark === status ? null : status)}>
      {icon}
    </button>
  );
  return (
    <span className="mark-btns">
      {btn("interesting", "★", "Интересно")}
      {btn("in_work", "◐", "В работе")}
      {btn("rejected", "✕", "Отбросить")}
    </span>
  );
}
