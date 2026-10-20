import { Link, useNavigate } from "react-router-dom";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ApiError, NewQuery, Page, api } from "../api";
import { Chips, FGroup, FilterPanel, LazyInput, Seg, SortSelect, activeCount, useFiltersOpen, useUrlFilters } from "../components/filters";
import { CardStat, Empty, Flags, Loader, Meter, PageSub, Pager, SortTh } from "../components/ui";
import { COUNTRY_NAMES, fmtAge, fmtDate, fmtN } from "../format";
import { roomText } from "./Niches";

const SORTS: [string, string, string][] = [
  ["score", "Оценка", "desc"], ["first_seen", "Появился", "desc"], ["phrase_birth", "Возраст фразы", "desc"],
  ["relevant_top", "Игр с фразой в выдаче", "asc"], ["leader_v7", "Лидер, в день", "desc"], ["term", "Запрос", "asc"],
];

const DEFAULTS: Record<string, string> = {
  country: "", kind: "all", hide_paid: "true", q: "", max_relevant: "", sort: "score", dir: "desc", page: "1",
};

type Data = Page<NewQuery> & { markets: { country: string; lang: string }[]; started: string | null };

export default function NewQueries() {
  const f = useUrlFilters(DEFAULTS);
  const navigate = useNavigate();
  const params = f.all();
  const panel = useFiltersOpen();
  const active = activeCount(params, DEFAULTS);
  const data = useQuery({
    queryKey: ["new-queries", params],
    queryFn: () => api<Data>("/new-queries", { params }),
    placeholderData: keepPreviousData,
    retry: false,
  });
  const sort = f.get("sort");
  const dir = f.get("dir");
  const sortBy = (field: string) => {
    if (sort === field) f.set({ dir: dir === "desc" ? "asc" : "desc" });
    else f.set({ sort: field, dir: field === "relevant_top" || field === "term" ? "asc" : "desc" });
  };
  const open = (n: NewQuery) => n.keyword && navigate(`/niches/${n.keyword.id}`);

  if (data.error instanceof ApiError && data.error.status === 402) {
    return <Empty title="Новые запросы доступны на тарифе Pro">Обновите тариф, чтобы видеть новые запросы в поиске.</Empty>;
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Новые запросы</h1>
          <PageSub>
            Что Google Play недавно начал подсказывать в поиске. Каждый день детектор вводит в автодополнение короткие начала
            слов в 7 странах. <b>Новый</b> — запрос, которого раньше в подсказках не было. <b>Возраст фразы</b> — сколько
            прошло с выхода первой игры, в названии которой есть все слова запроса: так видны и молодые запросы, которые мы
            застали с первого дня. <b>Волна клонов</b> — фразу за месяц поставили в названия три студии и больше: так
            Bomb Chip выглядел в феврале, ещё до хитов. Кроме коротких начал детектор вводит слова и пары слов из названий
            свежих игр («bomb chip», «bomb chip …»): короткие начала занимают Booking и Boom Beach. <b>С фразой в выдаче</b> —
            сколько игр из топ-10 по этому запросу действительно про него: если мало, новая игра с этой фразой в названии
            легко встаёт наверх.
            {data.data?.started && <> Детектор работает с {fmtDate(data.data.started)}: в первые дни все запросы считаются исходными, новые появятся со второго обхода.</>}
          </PageSub>
        </div>
      </div>
      <div className={`radar ${panel.open ? "" : "collapsed"}`}>
        <FilterPanel panel={panel} onReset={f.reset} result={data.data ? `${data.data.total.toLocaleString("ru-RU")} запросов` : "запросы"}>
          <FGroup title="Страна">
            <div className="chips">
              <button type="button" className={`chip ${!f.get("country") ? "on" : ""}`} onClick={() => f.set({ country: "" })}>Все</button>
              {(data.data?.markets || []).map((m) => (
                <button key={m.country} type="button" className={`chip ${f.get("country") === m.country ? "on" : ""}`}
                        onClick={() => f.set({ country: m.country })}>
                  {COUNTRY_NAMES[m.country] || m.country.toUpperCase()}
                </button>
              ))}
            </div>
          </FGroup>
          <FGroup title="Какие запросы">
            <Seg options={[["all", "Все"], ["new", "Новые в подсказках"], ["young", "Молодые фразы"], ["wave", "Волна клонов"]]}
                 value={f.get("kind")} onChange={(v) => f.set({ kind: v })} />
          </FGroup>
          <FGroup title="Лидер на закупке" hint="признаки закупки, а в поиске и чартах почти не виден; взрывной старт только помечается">
            <Seg options={[["true", "Скрыть"], ["false", "Показать"]]} value={f.get("hide_paid")} onChange={(v) => f.set({ hide_paid: v })} />
          </FGroup>
          <FGroup title="Игр с фразой в топ-10 выдачи" hint="меньше — свободнее">
            <Chips options={[["0", "0"], ["1", "≤ 1"], ["3", "≤ 3"]]} value={f.get("max_relevant")} onChange={(v) => f.set({ max_relevant: v })} />
          </FGroup>
          <FGroup title="Поиск">
            <LazyInput value={f.get("q")} onCommit={(v) => f.set({ q: v })} placeholder="запрос" />
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
              <Empty title="Запросов пока нет">Детектор обходит подсказки раз в день; разобранные игровые запросы появятся здесь после первого обхода.</Empty>
            </div>
          ) : panel.mobile ? (
            <div className="cards">
              {data.data.items.map((n) => (
                <div key={n.id} className={`card ${n.keyword ? "clickable" : ""}`} onClick={() => open(n)}>
                  <div className="card-top">
                    <b className="grow">{n.term}</b>
                    <span className="faint">{n.country.toUpperCase()}</span>
                  </div>
                  <div className="card-stats">
                    <CardStat label="Появился">{seenText(n)}</CardStat>
                    <CardStat label="Фраза">{fmtAge(n.phrase_age)}</CardStat>
                    <CardStat label="С фразой">{n.relevant_top ?? "—"}/10</CardStat>
                    <CardStat label="Оценка">{n.score !== null ? Math.round(n.score) : "—"}</CardStat>
                  </div>
                  {n.leader && <LeaderCell n={n} />}
                </div>
              ))}
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <SortTh label="Запрос" field="term" sort={sort} dir={dir} onSort={sortBy} />
                    <SortTh label="Оценка" field="score" sort={sort} dir={dir} onSort={sortBy} title="Новый игровой запрос, мало игр с фразой в выдаче, его ищут, и на нём уже растёт игра: 0–100" />
                    <SortTh label="Появился" field="first_seen" sort={sort} dir={dir} onSort={sortBy} title="Когда Google впервые подсказал запрос («с начала» — был уже на первом обходе)" />
                    <SortTh label="Фраза" field="phrase_birth" sort={sort} dir={dir} onSort={sortBy} right title="Сколько прошло с выхода первой игры со всеми словами запроса в названии" />
                    <th className="r" title="Игр со словами запроса в названии: всего и вышедших за 30 дней (от скольких студий)">Игр с фразой</th>
                    <SortTh label="В выдаче" field="relevant_top" sort={sort} dir={dir} onSort={sortBy} right title="Сколько из топ-10 выдачи по запросу действительно про него (фраза в названии)" />
                    <th className="r" title="Мест в топ-10, которые новичок может занять, и самое высокое из них">Места</th>
                    <SortTh label="Лидер фразы" field="leader_v7" sort={sort} dir={dir} onSort={sortBy} title="Самая быстрая игра с фразой в названии" />
                  </tr>
                </thead>
                <tbody>
                  {data.data.items.map((n, i) => (
                    <tr key={n.id} className={n.keyword ? "clickable" : ""} style={{ animationDelay: `${Math.min(i, 20) * 18}ms` }} onClick={() => open(n)}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{n.term}</div>
                        <div className="faint" style={{ fontSize: 12 }}>
                          {COUNTRY_NAMES[n.country] || n.country.toUpperCase()}
                          {n.prefix && <> · подсказка на «{n.prefix}»</>}
                          {n.rising && <span className="good"> · ↑ поднимается</span>}
                        </div>
                      </td>
                      <td>
                        <div className="row">
                          <span className="num" style={{ width: 26 }}>{n.score !== null ? Math.round(n.score) : "—"}</span>
                          <Meter value={n.score} />
                        </div>
                      </td>
                      <td className={n.is_new ? "good" : "muted"}>{seenText(n)}</td>
                      <td className={`r num ${(n.phrase_age ?? 9999) <= 150 ? "good" : ""}`}>{fmtAge(n.phrase_age)}</td>
                      <td className="r num">
                        {n.phrase_titles ?? "—"}
                        {n.phrase_titles_30d ? (
                          <span className={(n.phrase_devs_30d ?? 0) >= 3 ? "good" : "faint"} title="вышло за 30 дней · студий">
                            {" "}(+{n.phrase_titles_30d} · {n.phrase_devs_30d} студ.)
                          </span>
                        ) : null}
                      </td>
                      <td className={`r num ${(n.relevant_top ?? 10) <= 1 ? "good" : ""}`}>{n.relevant_top ?? "—"}/10</td>
                      <td className="r num">{n.keyword ? roomText(n.keyword) : "—"}</td>
                      <td onClick={(e) => e.stopPropagation()}>{n.leader ? <LeaderCell n={n} /> : <span className="muted">игр с фразой нет</span>}</td>
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

function seenText(n: NewQuery) {
  if (n.baseline) return "с начала";
  return fmtDate(n.first_seen) + (n.days_seen > 1 ? ` · ${n.days_seen} дн` : "");
}

function LeaderCell({ n }: { n: NewQuery }) {
  const l = n.leader!;
  return (
    <Link to={`/game/${encodeURIComponent(l.app_id)}`} className="app-cell">
      {l.icon_url ? <img className="app-icon" src={l.icon_url} alt="" loading="lazy" /> : <div className="app-icon" />}
      <div className="app-meta">
        <div className="app-title">{l.title || l.app_id}</div>
        <div className="app-dev">
          {fmtN(l.v7)}/день · {fmtAge(l.age_days)} <Flags flags={[]} traffic={l.traffic} />
          {n.leader_explosive && (
            <span className="flag traffic-mixed" title="Больше 1 млн установок за первые 2 месяца: закупка или вирусное видео. Вирусный спрос — то, на чём растут клоны в поиске (так было с Bomb Chip), поэтому не скрываем">взрывной старт</span>
          )}
        </div>
      </div>
    </Link>
  );
}
