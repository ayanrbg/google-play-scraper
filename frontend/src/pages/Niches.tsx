import { useNavigate } from "react-router-dom";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ApiError, Keyword, Page, api } from "../api";
import { Chips, FGroup, FilterPanel, LazyInput, Seg, SortSelect, activeCount, useFiltersOpen, useUrlFilters } from "../components/filters";
import { CardStat, Empty, Loader, Meter, PageSub, Pager, SortTh } from "../components/ui";
import { SavedViews } from "../components/views";
import { useMe } from "../App";
import { fmtN, fmtPct } from "../format";

const SORTS: [string, string, string][] = [
  ["entry_score", "Вход для новичка", "desc"], ["room", "Свободных мест", "desc"], ["fresh_count", "Свежих в топе", "desc"],
  ["opportunity", "Возможность", "desc"], ["demand", "Спрос", "desc"], ["competition", "Конкуренция", "asc"],
  ["young_share", "Доля молодых", "desc"], ["young_best_installs", "Лучший новичок", "desc"],
  ["top_median_installs", "Медиана топа", "desc"], ["term", "Запрос", "asc"],
];

type Market = { country: string; lang: string; label: string; analyzed: number };

const DEFAULTS: Record<string, string> = {
  country: "us", min_games_share: "0.6",
  q: "", min_demand: "", max_competition: "", min_opportunity: "", min_young_share: "", max_brand_share: "",
  min_room: "", min_fresh: "",
  sort: "entry_score", dir: "desc", page: "1",
};

export default function Niches() {
  const me = useMe();
  const f = useUrlFilters(DEFAULTS);
  const navigate = useNavigate();
  const params = f.all();
  const panel = useFiltersOpen();
  const active = activeCount(params, DEFAULTS);
  const data = useQuery({
    queryKey: ["keywords", params],
    queryFn: () => api<Page<Keyword>>("/keywords", { params }),
    placeholderData: keepPreviousData,
    retry: false,
  });
  const markets = useQuery({ queryKey: ["keyword-markets"], queryFn: () => api<Market[]>("/keyword-markets"), retry: false });
  const sortBy = (field: string) => {
    if (f.get("sort") === field) f.set({ dir: f.get("dir") === "desc" ? "asc" : "desc" });
    else f.set({ sort: field, dir: field === "competition" ? "asc" : "desc" });
  };
  const sort = f.get("sort");
  const dir = f.get("dir");

  if (data.error instanceof ApiError && data.error.status === 402) {
    return <Empty title="Ниши доступны на тарифе Pro">Обновите тариф, чтобы видеть спрос в поиске.</Empty>;
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Ниши в поиске</h1>
          <PageSub>
            Запросы Google Play, которые люди реально ищут. <b>Спрос</b> — по автодополнению: чем короче префикс, при котором
            Google подсказывает запрос, тем он популярнее. <b>Конкуренция</b> — по выдаче: размеры топа, доля брендов, точные
            совпадения в названиях. <b>Вход</b> — есть ли в топ-10 место для новой игры: сколько мест держат игры, которые
            новичок может обойти (свежие, молодые с небольшими установками, маленькие, с низким рейтингом, заброшенные; бренды
            не в счёт), насколько высоко такое место, и растут ли уже пробившиеся новички.
          </PageSub>
        </div>
      </div>
      <div className={`radar ${panel.open ? "" : "collapsed"}`}>
        <FilterPanel panel={panel} onReset={f.reset} result={data.data ? `${data.data.total.toLocaleString("ru-RU")} запросов` : "запросы"}>
          <FGroup title="Язык поиска" hint="рынок Google Play">
            <div className="chips">
              {(markets.data || []).map((m) => (
                <button key={m.country} type="button" className={`chip ${f.get("country") === m.country ? "on" : ""}`}
                        onClick={() => f.set({ country: m.country })} title={`разобрано запросов: ${m.analyzed}`}>
                  {m.label}
                </button>
              ))}
            </div>
          </FGroup>
          <FGroup title="Поиск">
            <LazyInput value={f.get("q")} onCommit={(v) => f.set({ q: v })} placeholder="запрос" />
          </FGroup>
          <FGroup title="Только игровые запросы" hint="доля игр в топ-10 выдачи">
            <Seg
              options={[["0.6", "60%+"], ["0.8", "80%+"], ["", "Все"]]}
              value={f.get("min_games_share")}
              onChange={(v) => f.set({ min_games_share: v })}
            />
          </FGroup>
          {me && (
            <FGroup title="Мои фильтры">
              <SavedViews page="keywords" current={() => f.all()} onApply={(p) => f.replaceAll(p)} />
            </FGroup>
          )}
          <FGroup title="Свободных мест в топ-10" hint="которые новичок может занять">
            <Chips options={[["2", "2+"], ["3", "3+"], ["5", "5+"]]} value={f.get("min_room")} onChange={(v) => f.set({ min_room: v })} />
          </FGroup>
          <FGroup title="Свежие игры в топ-10" hint="моложе 3 месяцев">
            <Chips options={[["1", "1+"], ["2", "2+"], ["3", "3+"]]} value={f.get("min_fresh")} onChange={(v) => f.set({ min_fresh: v })} />
          </FGroup>
          <FGroup title="Спрос от">
            <Chips options={[["20", "20+"], ["40", "40+"], ["60", "60+"], ["80", "80+"]]} value={f.get("min_demand")} onChange={(v) => f.set({ min_demand: v })} />
          </FGroup>
          <FGroup title="Конкуренция до">
            <Chips options={[["30", "≤ 30"], ["45", "≤ 45"], ["60", "≤ 60"]]} value={f.get("max_competition")} onChange={(v) => f.set({ max_competition: v })} />
          </FGroup>
          <FGroup title="Возможность от">
            <Chips options={[["20", "20+"], ["35", "35+"], ["50", "50+"]]} value={f.get("min_opportunity")} onChange={(v) => f.set({ min_opportunity: v })} />
          </FGroup>
          <FGroup title="Молодые игры в топ-10" hint="моложе года">
            <Chips options={[["0.1", "10%+"], ["0.3", "30%+"], ["0.5", "50%+"]]} value={f.get("min_young_share")} onChange={(v) => f.set({ min_young_share: v })} />
          </FGroup>
          <FGroup title="Доля брендов в топ-10 до">
            <Chips options={[["0", "0%"], ["0.2", "≤ 20%"], ["0.4", "≤ 40%"]]} value={f.get("max_brand_share")} onChange={(v) => f.set({ max_brand_share: v })} />
          </FGroup>
        </FilterPanel>
        <section style={{ minWidth: 0 }}>
          <div className="toolbar">
            <button className={`btn sm ${active ? "primary" : ""}`} onClick={panel.toggle}>
              {panel.open ? "← Скрыть фильтры" : `Фильтры${active ? ` · ${active}` : ""}`}
            </button>
            {panel.mobile && <SortSelect options={SORTS} sort={sort} dir={dir} onChange={(s, d) => f.set({ sort: s, dir: d })} />}
            <span className="count">{data.data ? `${data.data.total.toLocaleString("ru-RU")} запросов` : "…"}</span>
          </div>
          {data.isLoading ? (
            <Loader />
          ) : !data.data?.items.length ? (
            <div className="panel">
              <Empty title="Запросов пока нет">Каждый день разбирается порция запросов: база ниш наполняется постепенно.</Empty>
            </div>
          ) : panel.mobile ? (
            <div className="cards">
              {data.data.items.map((k) => (
                <div key={k.id} className="card clickable" onClick={() => navigate(`/niches/${k.id}`)}>
                  <div className="card-top">
                    <b className="grow">{k.term}</b>
                  </div>
                  <div className="card-meters">
                    <MeterStat label="Вход" value={k.entry_score} />
                    <MeterStat label="Спрос" value={k.demand} />
                    <MeterStat label="Конкуренция" value={k.competition} tone={(k.competition || 0) > 60 ? "bad" : (k.competition || 0) > 40 ? "warn" : undefined} />
                  </div>
                  <div className="card-stats">
                    <CardStat label="Места">{roomText(k)}</CardStat>
                    <CardStat label="Свежие">{k.fresh_count ?? "—"}</CardStat>
                    <CardStat label="Медиана">{fmtN(k.top_median_installs)}</CardStat>
                    <CardStat label="Бренды">{fmtPct(k.brand_share)}</CardStat>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <SortTh label="Запрос" field="term" sort={sort} dir={dir} onSort={sortBy} />
                    <SortTh label="Вход" field="entry_score" sort={sort} dir={dir} onSort={sortBy} title="Есть ли место для новой игры в топ-10, 0–100" />
                    <SortTh label="Места" field="room" sort={sort} dir={dir} onSort={sortBy} right title="Мест в топ-10, которые новичок может занять, и самое высокое из них" />
                    <SortTh label="Свежие" field="fresh_count" sort={sort} dir={dir} onSort={sortBy} right title="Игр моложе 3 месяцев в топ-10" />
                    <SortTh label="Новички/день" field="entrants_v7" sort={sort} dir={dir} onSort={sortBy} right title="Медианная скорость молодых игр в топ-10, установок в день (растущих из них)" />
                    <SortTh label="Возможность" field="opportunity" sort={sort} dir={dir} onSort={sortBy} />
                    <SortTh label="Спрос" field="demand" sort={sort} dir={dir} onSort={sortBy} />
                    <SortTh label="Конкуренция" field="competition" sort={sort} dir={dir} onSort={sortBy} />
                    <SortTh label="Молодые" field="young_share" sort={sort} dir={dir} onSort={sortBy} right title="Доля игр моложе года в топ-10" />
                    <SortTh label="Лучший новичок" field="young_best_installs" sort={sort} dir={dir} onSort={sortBy} right title="Установки самой успешной молодой игры в топ-10" />
                    <SortTh label="Медиана топа" field="top_median_installs" sort={sort} dir={dir} onSort={sortBy} right />
                    <th className="r">Бренды</th>
                  </tr>
                </thead>
                <tbody>
                  {data.data.items.map((k, i) => (
                    <tr key={k.id} className="clickable" style={{ animationDelay: `${Math.min(i, 20) * 18}ms` }} onClick={() => navigate(`/niches/${k.id}`)}>
                      <td style={{ fontWeight: 600 }}>{k.term}</td>
                      <td>
                        <div className="row">
                          <span className="num" style={{ width: 26 }}>{k.entry_score !== null ? Math.round(k.entry_score) : "—"}</span>
                          <Meter value={k.entry_score} />
                        </div>
                      </td>
                      <td className="r num">{roomText(k)}</td>
                      <td className="r num">{k.fresh_count ?? "—"}</td>
                      <td className="r num">
                        {fmtN(k.entrants_v7)}
                        {k.entrants_growing ? <span className="faint"> ({k.entrants_growing})</span> : null}
                      </td>
                      <td>
                        <div className="row">
                          <span className="num" style={{ width: 26 }}>{k.opportunity !== null ? Math.round(k.opportunity) : "—"}</span>
                          <Meter value={k.opportunity} />
                        </div>
                      </td>
                      <td>
                        <div className="row">
                          <span className="num" style={{ width: 26 }}>{Math.round(k.demand)}</span>
                          <Meter value={k.demand} />
                        </div>
                      </td>
                      <td>
                        <div className="row">
                          <span className="num" style={{ width: 26 }}>{k.competition !== null ? Math.round(k.competition) : "—"}</span>
                          <Meter value={k.competition} tone={(k.competition || 0) > 60 ? "bad" : (k.competition || 0) > 40 ? "warn" : undefined} />
                        </div>
                      </td>
                      <td className="r num">{fmtPct(k.young_share)}</td>
                      <td className="r num">{fmtN(k.young_best_installs)}</td>
                      <td className="r num">{fmtN(k.top_median_installs)}</td>
                      <td className="r num">{fmtPct(k.brand_share)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {data.data && <Pager page={Number(f.get("page")) || 1} pageSize={data.data.page_size} total={data.data.total} onPage={(p) => f.set({ page: String(p) }, false)} />}
        </section>
      </div>
    </>
  );
}

export function roomText(k: { room: number | null; room_best: number | null }) {
  if (k.room === null) return "—";
  return k.room ? `${k.room}/10 · #${k.room_best}` : "0/10";
}

function MeterStat({ label, value, tone }: { label: string; value: number | null; tone?: "warn" | "bad" }) {
  return (
    <div className="cs">
      <div className="cs-label">{label}</div>
      <div className="row">
        <span className="cs-value num" style={{ width: 26 }}>{value !== null ? Math.round(value) : "—"}</span>
        <Meter value={value} tone={tone} />
      </div>
    </div>
  );
}
