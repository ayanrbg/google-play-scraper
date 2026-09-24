import { useNavigate } from "react-router-dom";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ApiError, Keyword, Page, api } from "../api";
import { Chips, FGroup, LazyInput, activeCount, useFiltersOpen, useUrlFilters } from "../components/filters";
import { Empty, Loader, Meter, Pager, SortTh } from "../components/ui";
import { SavedViews } from "../components/views";
import { fmtN, fmtPct } from "../format";

const DEFAULTS: Record<string, string> = {
  q: "", min_demand: "", max_competition: "", min_opportunity: "", min_young_share: "", max_brand_share: "",
  sort: "opportunity", dir: "desc", page: "1",
};

export default function Niches() {
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
          <p className="page-sub">
            Запросы Google Play, которые люди реально ищут. <b>Спрос</b> — по автодополнению: чем короче префикс, при котором
            Google подсказывает запрос, тем он популярнее. <b>Конкуренция</b> — по выдаче: размеры топа, доля брендов, точные
            совпадения в названиях. <b>Возможность</b> выше, когда в топе уже есть молодые игры: новичок может туда пробиться.
          </p>
        </div>
      </div>
      <div className={`radar ${panel.open ? "" : "collapsed"}`}>
        {panel.open && (
        <aside className="panel filters">
          <FGroup title="Поиск">
            <LazyInput value={f.get("q")} onCommit={(v) => f.set({ q: v })} placeholder="запрос" />
          </FGroup>
          <FGroup title="Мои фильтры">
            <SavedViews page="keywords" current={() => f.all()} onApply={(p) => f.replaceAll(p)} />
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
          <div className="fgroup">
            <button className="btn sm ghost" onClick={f.reset}>Сбросить всё</button>
          </div>
        </aside>
        )}
        <section style={{ minWidth: 0 }}>
          <div className="toolbar">
            <button className={`btn sm ${active ? "primary" : ""}`} onClick={panel.toggle}>
              {panel.open ? "← Скрыть фильтры" : `Фильтры${active ? ` · ${active}` : ""}`}
            </button>
            <span className="count">{data.data ? `${data.data.total.toLocaleString("ru-RU")} запросов` : "…"}</span>
          </div>
          {data.isLoading ? (
            <Loader />
          ) : !data.data?.items.length ? (
            <div className="panel">
              <Empty title="Запросов пока нет">Каждый день разбирается порция запросов: база ниш наполняется постепенно.</Empty>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <SortTh label="Запрос" field="term" sort={sort} dir={dir} onSort={sortBy} />
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
