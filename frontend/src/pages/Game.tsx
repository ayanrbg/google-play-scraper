import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Area, AreaChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Game, api } from "../api";
import { Analysis, GrowthDrivers, KeysPanel, KeysTeaser, RankBadge, Timeline, useKeysTop10 } from "../components/insights";
import { BackLink, Empty, Flags, Loader, Meter, Score, Stat } from "../components/ui";
import { MarkButtons } from "./Radar";
import { useMe } from "../App";
import { COLLECTION_LABELS, COUNTRY_NAMES, fmtAccel, fmtAge, fmtDate, fmtFull, fmtN, fmtRating, storeUrl } from "../format";

type KnownKeyword = { id: number; term: string; country: string; demand: number; opportunity: number | null; competition: number | null; rank: number };

type Detail = {
  app: any;
  metrics: Game | null;
  snapshots: { date: string; installs: number; ratings: number; rating: number }[];
  daily: { date: string; installs: number | null }[];
  charts_latest: Record<string, { countries: Record<string, number>; best_rank: number; best_country: string; best_category: string }>;
  charts_date: string | null;
  chart_history: Record<string, any>[];
  score_history: { date: string; trend_score: number; v7: number | null }[];
  developer: { developer_id: string; name: string; app_count: number | null } | null;
  developer_apps: { app_id: string; title: string; icon_url: string; installs: number; released: string; tracked: boolean }[];
  keywords: KnownKeyword[];
  analysis: Analysis;
  mark: { status: string | null; note: string | null } | null;
  flag_labels: Record<string, string>;
};

const PART_LABELS: Record<string, [string, number]> = {
  growth: ["Скорость", 40],
  accel: ["Ускорение", 15],
  youth: ["Свежесть", 15],
  charts: ["Чарты", 20],
  quality: ["Качество", 10],
};

type Tab = "overview" | "keys" | "charts" | "studio";

// ----------------------------- chart styling -----------------------------

const tick = { fill: "var(--faint)", fontSize: 11, fontFamily: "var(--font-mono)" };
const tooltipStyle = {
  contentStyle: { background: "var(--bg-2)", border: "1px solid var(--line-strong)", borderRadius: 8, fontSize: 12, boxShadow: "var(--shadow)" },
  labelStyle: { color: "var(--muted)", marginBottom: 2 },
  itemStyle: { color: "var(--text)", padding: 0 },
  cursor: { fill: "var(--accent-soft)", stroke: "var(--line-strong)" },
};
const shortDate = (d: string) => new Date(d).toLocaleDateString("ru-RU", { day: "numeric", month: "short" }).replace(".", "");
const fmtTick = (v: number) => fmtN(v).replace(/\.$/, "");

const grid = <CartesianGrid stroke="var(--line)" strokeDasharray="2 4" vertical={false} />;
const xAxis = <XAxis dataKey="date" tickFormatter={shortDate} tick={tick} axisLine={false} tickLine={false} minTickGap={28} tickMargin={6} />;
const yAxis = (props: Record<string, any> = {}) => (
  <YAxis tickFormatter={fmtTick} tick={tick} axisLine={false} tickLine={false} width={52} tickCount={4} {...props} />
);
const gradient = (id: string, color: string) => (
  <defs>
    <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stopColor={color} stopOpacity={0.32} />
      <stop offset="100%" stopColor={color} stopOpacity={0} />
    </linearGradient>
  </defs>
);

// ----------------------------- page -----------------------------

export default function GamePage() {
  const { id = "" } = useParams();
  const me = useMe();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "overview";
  const tabsRef = useRef<HTMLDivElement>(null);
  const q = useQuery({ queryKey: ["game", id], queryFn: () => api<Detail>(`/games/${encodeURIComponent(id)}`) });
  const [note, setNote] = useState("");
  useEffect(() => setNote(q.data?.mark?.note || ""), [q.data?.mark?.note]);

  const mark = useMutation({
    mutationFn: (body: { status: string | null; note: string | null }) =>
      api(`/games/${encodeURIComponent(id)}/mark`, { method: "PUT", body }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["game", id] });
      qc.invalidateQueries({ queryKey: ["games"] });
    },
  });

  const top10 = useKeysTop10(id, q.data?.keywords || []);
  const setTab = (t: Tab) => {
    setParams(t === "overview" ? {} : { tab: t }, { replace: true });
    const el = tabsRef.current;
    if (el && el.getBoundingClientRect().top < 0) el.scrollIntoView({ block: "start" });
  };

  if (q.isLoading) return <Loader />;
  if (!q.data) return <Empty title="Игра не найдена" />;
  const d = q.data;
  const { app, metrics: m } = d;
  const status = d.mark?.status || null;
  const chartCountries = new Set(Object.values(d.charts_latest).flatMap((c) => Object.keys(c.countries))).size;

  const tabs: { key: Tab; label: string; badge?: ReactNode; hint?: string }[] = [
    { key: "overview", label: "Обзор" },
    { key: "keys", label: "Поиск и ключи", badge: top10 || undefined, hint: top10 ? `В топ-10 поиска: ${top10} пар запрос × страна` : undefined },
    { key: "charts", label: "Чарты", badge: chartCountries || undefined, hint: chartCountries ? `В чартах ${chartCountries} стран` : undefined },
    { key: "studio", label: "Студия", badge: d.developer_apps.length || undefined },
  ];

  return (
    <>
      <BackLink to="/" label="Радар" />
      <div className="hero">
        {app.icon_url ? <img className="app-icon lg" src={app.icon_url} alt="" /> : <div className="app-icon lg" />}
        <div style={{ flex: 1, minWidth: 0 }}>
          <h1>{app.title}</h1>
          <div className="muted" style={{ marginBottom: 8 }}>
            {app.developer} · {app.genre} · <Flags flags={m?.brand_flags || []} prereg={app.pre_register} age={app.soft_launch ? null : m?.age_days} softLaunch={app.soft_launch_markets} revival={m?.revival} hidden={m?.hidden_gem} />
          </div>
          {app.soft_launch && (
            <div className="banner info" style={{ margin: "0 0 10px", fontSize: 13 }}>
              <b>Была в софт-лонче</b> ({app.soft_launch_markets.map((c: string) => c.toUpperCase()).join(", ")}) до глобального запуска {fmtDate(app.released)}.
              Возраст считается с глобального запуска, а установки включают софт-лонч. Скорость показываем только реальную, по нашим замерам.
              Прошедший софт-лонч — хороший знак: издатель проверил метрики и масштабирует игру.
            </div>
          )}
          <div className="row" style={{ flexWrap: "wrap" }}>
            <a className="btn sm primary" href={storeUrl(app.app_id)} target="_blank" rel="noreferrer">
              Открыть в Google Play ↗
            </a>
            {me && <MarkButtons game={{ mark: status }} onMark={(s) => mark.mutate({ status: s, note: note || null })} />}
            {me && status && <span className="pill">{{ interesting: "Интересно", in_work: "В работе", rejected: "Отброшено" }[status]}</span>}
          </div>
        </div>
        {m && (
          <div className="panel panel-pad hero-score">
            <div className="stat-label">Trend Score</div>
            <div style={{ fontSize: 28, marginTop: 4 }}>
              <Score value={m.trend_score} />
            </div>
          </div>
        )}
      </div>

      <div className="stats" style={{ marginBottom: 8 }}>
        <Stat label="Установки" value={fmtN(app.installs)} note={app.pre_register ? "пре-регистраций" : fmtFull(app.installs)} />
        <Stat label="В день (7 дн)" value={fmtN(m?.v7)} note={m?.v7_prev ? `неделей раньше ${fmtN(m.v7_prev)}` : "история копится"} />
        <Stat label="Ускорение" value={fmtAccel(m?.accel)} />
        <Stat label={app.soft_launch ? "С глобального запуска" : "Возраст"} value={app.pre_register ? "пре-рег" : fmtAge(m?.age_days)} note={fmtDate(app.released)} />
        <Stat label="Рейтинг" value={fmtRating(app.rating)} note={`${fmtN(app.ratings)} оценок`} />
        <Stat label="Страны в чартах" value={(m?.new_countries || 0) + (m?.top_countries || 0)} note={m?.trending_countries ? `Movers: ${m.trending_countries}` : undefined} />
      </div>

      <div className="page-tabs" ref={tabsRef} role="tablist">
        {tabs.map((t) => (
          <button key={t.key} role="tab" aria-selected={tab === t.key} className={tab === t.key ? "on" : ""} onClick={() => setTab(t.key)} title={t.hint}>
            {t.label}
            {t.badge !== undefined && <span className="pill">{t.badge}</span>}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <>
          <KeysTeaser appId={app.app_id} known={d.keywords} onOpen={() => setTab("keys")} />

          <div className="grid-2 wide-left" style={{ marginBottom: 16 }}>
            <Dynamics d={d} />
            <ScoreParts m={m} />
          </div>

          <div className="grid-2" style={{ marginBottom: 16, alignItems: "start" }}>
            <GrowthDrivers analysis={d.analysis} />
            <Timeline items={d.analysis.timeline} />
          </div>

          {me && (
            <div className="panel panel-pad">
              <h3 className="panel-title">Заметка команды</h3>
              <div className="note-box">
                <textarea className="input" rows={4} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Что понравилось, какую механику взять, риски…" />
                <button className="btn sm" style={{ alignSelf: "flex-start" }} onClick={() => mark.mutate({ status, note: note || null })} disabled={mark.isPending}>
                  Сохранить
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {tab === "keys" && (
        <>
          <KeysPanel appId={app.app_id} />
          <KnownPositions keywords={d.keywords} />
        </>
      )}

      {tab === "charts" && <Charts d={d} />}

      {tab === "studio" && <Studio d={d} />}
    </>
  );
}

// ----------------------------- overview -----------------------------

type Metric = "daily" | "total" | "score";

const METRICS: { key: Metric; label: string }[] = [
  { key: "daily", label: "В день" },
  { key: "total", label: "Всего" },
  { key: "score", label: "Trend Score" },
];

/** Installs per day, measured only where Google refreshed the counter: each point is the average since the
 * previous refresh. Days in between have no reading of their own, so the line just connects the points
 * instead of drawing the flat steps a day-by-day split would give. */
function installRates(snapshots: Detail["snapshots"]) {
  let last: { date: string; installs: number } | null = null;
  return snapshots.map((s) => {
    const point = { date: s.date, rate: null as number | null, span: 0 };
    if (!last) last = s;
    else if (s.installs > last.installs) {
      const span = Math.max(1, Math.round((Date.parse(s.date) - Date.parse(last.date)) / 86400000));
      point.rate = Math.round((s.installs - last.installs) / span);
      point.span = span;
      last = s;
    }
    return point;
  });
}

/** One compact chart with a switch instead of a wall of big ones. */
function Dynamics({ d }: { d: Detail }) {
  const [metric, setMetric] = useState<Metric>("daily");
  const rates = useMemo(() => installRates(d.snapshots), [d.snapshots]);
  const enough = { daily: rates.filter((r) => r.rate !== null).length > 1, total: d.snapshots.length > 1, score: d.score_history.length > 1 }[metric];
  return (
    <div className="panel panel-pad">
      <div className="panel-head">
        <div>
          <h3 className="panel-title">Установки</h3>
          <p>{{ daily: "Сколько игру скачивают в день", total: "Счётчик установок в Google Play", score: "Как менялась оценка тренда" }[metric]}</p>
        </div>
        <div className="seg auto">
          {METRICS.map((x) => (
            <button key={x.key} className={metric === x.key ? "on" : ""} onClick={() => setMetric(x.key)}>{x.label}</button>
          ))}
        </div>
      </div>
      {enough ? (
        <div className="chart-box">
          <ResponsiveContainer>
            {metric === "daily" ? (
              <AreaChart data={rates} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                {gradient("g-daily", "var(--accent)")}
                {grid}
                {xAxis}
                {yAxis()}
                <Tooltip {...tooltipStyle} labelFormatter={shortDate}
                  formatter={(v: number, _n: string, item: any) => [fmtFull(v), item.payload.span > 1 ? `в день, в среднем за ${item.payload.span} дн.` : "в день"]} />
                <Area dataKey="rate" type="monotone" connectNulls stroke="var(--accent)" strokeWidth={2} fill="url(#g-daily)"
                  dot={{ r: 3, fill: "var(--accent)", stroke: "var(--bg-2)", strokeWidth: 1.5 }} activeDot={{ r: 4 }} isAnimationActive={false} />
                {d.analysis.updates.map((u) => (
                  <ReferenceLine key={u.date} x={u.date} stroke="var(--info)" strokeDasharray="3 3"
                    label={{ value: u.version, position: "insideTopLeft", fill: "var(--info)", fontSize: 10 }} />
                ))}
              </AreaChart>
            ) : metric === "total" ? (
              <AreaChart data={d.snapshots} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                {gradient("g-total", "var(--accent)")}
                {grid}
                {xAxis}
                {yAxis({ domain: ["auto", "auto"] })}
                <Tooltip {...tooltipStyle} labelFormatter={shortDate} formatter={(v: number) => [fmtFull(v), "всего"]} />
                <Area dataKey="installs" stroke="var(--accent)" strokeWidth={2} fill="url(#g-total)" isAnimationActive={false} />
              </AreaChart>
            ) : (
              <AreaChart data={d.score_history} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                {gradient("g-score", "var(--accent)")}
                {grid}
                {xAxis}
                {yAxis({ domain: [0, 100], ticks: [0, 25, 50, 75, 100], width: 32 })}
                <Tooltip {...tooltipStyle} labelFormatter={shortDate} formatter={(v: number) => [Math.round(v), "Trend Score"]} />
                <Area dataKey="trend_score" stroke="var(--accent)" strokeWidth={2} fill="url(#g-score)" isAnimationActive={false} />
              </AreaChart>
            )}
          </ResponsiveContainer>
        </div>
      ) : (
        <Empty title="История копится">Нужно хотя бы 2 дня наблюдений.</Empty>
      )}
      {metric === "daily" && (
        <p className="faint" style={{ fontSize: 12, margin: "8px 0 0" }}>
          Google обновляет счётчик раз в 1–3 дня. Точки — дни обновления, в каждой средняя скорость с прошлого обновления.
          {d.analysis.updates.length > 0 && " Пунктир — обновления игры."}
        </p>
      )}
    </div>
  );
}

function ScoreParts({ m }: { m: Game | null }) {
  return (
    <div className="panel panel-pad">
      <div className="panel-head">
        <div>
          <h3 className="panel-title">Из чего Trend Score</h3>
          <p>Оценка тренда от 0 до 100</p>
        </div>
        {m && <Score value={m.trend_score} />}
      </div>
      {m ? (
        <div className="parts">
          {Object.entries(PART_LABELS).map(([k, [label, max]]) => (
            <div className="part" key={k}>
              <span className="muted">{label}</span>
              <Meter value={Number(m.score_parts?.[k] || 0)} max={max} />
              <span className="num r">
                {Number(m.score_parts?.[k] || 0).toFixed(0)}/{max}
              </span>
            </div>
          ))}
          {m.score_parts?.estimated && <p className="faint" style={{ fontSize: 12, margin: 0 }}>Скорость оценена по среднему за жизнь игры: недельной истории пока нет.</p>}
        </div>
      ) : (
        <p className="muted">Игра не на радаре (старше года или без роста).</p>
      )}
    </div>
  );
}

// ----------------------------- search -----------------------------

/** Positions the daily keyword monitoring already knows, one row per phrase with all its countries. */
function KnownPositions({ keywords }: { keywords: KnownKeyword[] }) {
  const [all, setAll] = useState(false);
  const groups = useMemo(() => {
    const by = new Map<string, KnownKeyword[]>();
    for (const k of keywords) by.set(k.term, [...(by.get(k.term) || []), k]);
    return [...by.entries()]
      .map(([term, ks]) => ({ term, ks: ks.sort((a, b) => a.rank - b.rank), best: Math.min(...ks.map((k) => k.rank)), demand: Math.max(...ks.map((k) => k.demand)) }))
      .sort((a, b) => a.best - b.best || b.demand - a.demand);
  }, [keywords]);
  const shown = all ? groups : groups.slice(0, 10);
  return (
    <div className="panel panel-pad">
      <div className="panel-head">
        <div>
          <h3 className="panel-title">Позиции из ежедневного мониторинга</h3>
          <p>Запросы, которые мы и так проверяем каждый день, и место игры по ним в каждой стране.</p>
        </div>
      </div>
      {groups.length ? (
        <>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Запрос</th>
                  <th className="r">Лучшее место</th>
                  <th className="r" title="Как часто ищут: 100 — Google подсказывает запрос уже после пары букв">Спрос</th>
                  <th>По странам</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((g) => (
                  <tr key={g.term}>
                    <td><Link className="link" to={`/niches/${g.ks[0].id}`}>{g.term}</Link></td>
                    <td className="r"><RankBadge rank={g.best} /></td>
                    <td className="r">
                      <div className="demand"><Meter value={g.demand} /><span className="num">{Math.round(g.demand)}</span></div>
                    </td>
                    <td>
                      <div className="country-grid" style={{ flexWrap: "nowrap" }}>
                        {g.ks.slice(0, 8).map((k) => (
                          <span key={k.country} className="cc" title={COUNTRY_NAMES[k.country] || k.country}>
                            {k.country.toUpperCase()}<b>#{k.rank}</b>
                          </span>
                        ))}
                        {g.ks.length > 8 && <span className="faint" style={{ fontSize: 12 }}>+{g.ks.length - 8}</span>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {groups.length > shown.length && (
            <button className="btn ghost sm" style={{ marginTop: 10 }} onClick={() => setAll(true)}>
              Показать все запросы ({groups.length})
            </button>
          )}
        </>
      ) : (
        <p className="muted" style={{ margin: 0 }}>По отслеживаемым запросам игру пока не нашли в поиске.</p>
      )}
    </div>
  );
}

// ----------------------------- charts -----------------------------

const LINES: { key: string; name: string; color: string }[] = [
  { key: "top_new_free", name: "Top New", color: "var(--accent)" },
  { key: "top_free", name: "Top Free", color: "var(--info)" },
  { key: "trending", name: "Movers", color: "var(--warn)" },
];

function Charts({ d }: { d: Detail }) {
  const lines = LINES.filter((l) => d.chart_history.some((r) => r[l.key]));
  return (
    <div className="stack">
      <div className="panel panel-pad">
        <div className="panel-head">
          <div>
            <h3 className="panel-title">Где в чартах сейчас</h3>
            <p>Место игры в чартах Google Play по странам{d.charts_date ? `, ${fmtDate(d.charts_date)}` : ""}</p>
          </div>
        </div>
        {Object.keys(d.charts_latest).length ? (
          <div className="stack">
            {Object.entries(d.charts_latest).map(([coll, c]) => (
              <div key={coll}>
                <div className="label">
                  {COLLECTION_LABELS[coll] || coll} · {Object.keys(c.countries).length} стран
                </div>
                <div className="country-grid">
                  {Object.entries(c.countries)
                    .sort((a, b) => a[1] - b[1])
                    .map(([cc, rank]) => (
                      <span key={cc} className={`cc ${rank <= 10 ? "hot" : ""}`} title={COUNTRY_NAMES[cc] || cc}>
                        {cc.toUpperCase()}
                        <b>#{rank}</b>
                      </span>
                    ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted" style={{ margin: 0 }}>Сейчас нет в чартах.</p>
        )}
      </div>
      {d.chart_history.length > 1 && lines.length > 0 && (
        <div className="panel panel-pad">
          <div className="panel-head">
            <div>
              <h3 className="panel-title">В скольких странах в чартах</h3>
              <p>Число стран по дням, отдельно для каждого чарта</p>
            </div>
            <div className="legend">
              {lines.map((l) => <span key={l.key}><i style={{ background: l.color }} />{l.name}</span>)}
            </div>
          </div>
          <div className="chart-box">
            <ResponsiveContainer>
              <LineChart data={d.chart_history} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                {grid}
                {xAxis}
                {yAxis({ width: 32, allowDecimals: false })}
                <Tooltip {...tooltipStyle} cursor={{ stroke: "var(--line-strong)" }} labelFormatter={shortDate} formatter={(v: number, name: string) => [`${v} стран`, name]} />
                {lines.map((l) => (
                  <Line key={l.key} dataKey={l.key} name={l.name} stroke={l.color} dot={false} strokeWidth={2} connectNulls isAnimationActive={false} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}

// ----------------------------- studio -----------------------------

function Studio({ d }: { d: Detail }) {
  return (
    <div className="panel panel-pad">
      <div className="panel-head">
        <div>
          <h3 className="panel-title">Студия: {d.developer?.name || "—"}</h3>
          {d.developer?.app_count ? <p>Приложений на странице разработчика: {d.developer.app_count}</p> : null}
        </div>
      </div>
      {d.developer_apps.length ? (
        <div className="scroll-x">
          <table className="data">
            <thead>
              <tr>
                <th>Игра</th>
                <th className="r">Установки</th>
                <th className="r">Релиз</th>
              </tr>
            </thead>
            <tbody>
              {d.developer_apps.map((a) => (
                <tr key={a.app_id}>
                  <td>
                    <Link to={`/game/${encodeURIComponent(a.app_id)}`} className="app-cell" style={{ minWidth: 0 }}>
                      {a.icon_url ? <img className="app-icon" src={a.icon_url} alt="" loading="lazy" /> : <div className="app-icon" />}
                      <span className="app-title">{a.title}</span>
                    </Link>
                  </td>
                  <td className="r num">{fmtN(a.installs)}</td>
                  <td className="r muted">{fmtDate(a.released)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted" style={{ margin: 0 }}>Других игр студии пока не видели.</p>
      )}
    </div>
  );
}
