import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Game, api } from "../api";
import { Empty, Flags, Loader, Meter, Score, Stat } from "../components/ui";
import { MarkButtons } from "./Radar";
import { COLLECTION_LABELS, COUNTRY_NAMES, fmtAccel, fmtAge, fmtDate, fmtFull, fmtN, fmtRating, storeUrl } from "../format";

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
  keywords: { id: number; term: string; demand: number; opportunity: number | null; competition: number | null; rank: number }[];
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

const axis = { stroke: "var(--faint)", fontSize: 11, fontFamily: "var(--font-mono)" };
const tooltipStyle = {
  contentStyle: { background: "var(--bg-2)", border: "1px solid var(--line-strong)", borderRadius: 8, fontSize: 12 },
  labelStyle: { color: "var(--muted)" },
};
const shortDate = (d: string) => new Date(d).toLocaleDateString("ru-RU", { day: "numeric", month: "short" });

export default function GamePage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
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

  if (q.isLoading) return <Loader />;
  if (!q.data) return <Empty title="Игра не найдена" />;
  const { app, metrics: m } = q.data;
  const status = q.data.mark?.status || null;

  return (
    <>
      <p style={{ margin: "0 0 16px" }}>
        <Link className="link" to="/">← Радар</Link>
      </p>
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
            <MarkButtons game={{ mark: status }} onMark={(s) => mark.mutate({ status: s, note: note || null })} />
            {status && <span className="pill">{{ interesting: "Интересно", in_work: "В работе", rejected: "Отброшено" }[status]}</span>}
          </div>
        </div>
        {m && (
          <div className="panel panel-pad" style={{ minWidth: 220 }}>
            <div className="stat-label">Trend Score</div>
            <div style={{ fontSize: 28, marginTop: 4 }}>
              <Score value={m.trend_score} />
            </div>
          </div>
        )}
      </div>

      <div className="stats" style={{ marginBottom: 16 }}>
        <Stat label="Установки" value={fmtN(app.installs)} note={app.pre_register ? "пре-регистраций" : fmtFull(app.installs)} />
        <Stat label="В день (7 дн)" value={fmtN(m?.v7)} note={m?.v7_prev ? `неделей раньше ${fmtN(m.v7_prev)}` : "история копится"} />
        <Stat label="Ускорение" value={fmtAccel(m?.accel)} />
        <Stat label={app.soft_launch ? "С глобального запуска" : "Возраст"} value={app.pre_register ? "пре-рег" : fmtAge(m?.age_days)} note={fmtDate(app.released)} />
        <Stat label="Рейтинг" value={fmtRating(app.rating)} note={`${fmtN(app.ratings)} оценок`} />
        <Stat label="Страны в чартах" value={(m?.new_countries || 0) + (m?.top_countries || 0)} note={m?.trending_countries ? `Movers: ${m.trending_countries}` : undefined} />
      </div>

      <div className="grid-2" style={{ marginBottom: 16 }}>
        <div className="panel panel-pad">
          <h3 className="panel-title">Установки в день</h3>
          {q.data.daily.length > 1 ? (
            <div className="chart-box">
              <ResponsiveContainer>
                <BarChart data={q.data.daily}>
                  <CartesianGrid stroke="var(--line)" vertical={false} />
                  <XAxis dataKey="date" tickFormatter={shortDate} {...axis} />
                  <YAxis tickFormatter={(v) => fmtN(v)} {...axis} width={48} />
                  <Tooltip {...tooltipStyle} labelFormatter={shortDate} formatter={(v: number) => [fmtFull(v), "установок"]} />
                  <Bar dataKey="installs" fill="var(--accent)" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <Empty title="История копится">Нужно хотя бы 2 дня наблюдений.</Empty>
          )}
          <p className="faint" style={{ fontSize: 12, margin: "8px 0 0" }}>
            Google обновляет счётчик с задержкой 1–3 дня: скачки распределены по дням, последние дни без обновления не показаны.
          </p>
        </div>
        <div className="panel panel-pad">
          <h3 className="panel-title">Всего установок</h3>
          {q.data.snapshots.length > 1 ? (
            <div className="chart-box">
              <ResponsiveContainer>
                <AreaChart data={q.data.snapshots}>
                  <CartesianGrid stroke="var(--line)" vertical={false} />
                  <XAxis dataKey="date" tickFormatter={shortDate} {...axis} />
                  <YAxis tickFormatter={(v) => fmtN(v)} {...axis} width={48} />
                  <Tooltip {...tooltipStyle} labelFormatter={shortDate} formatter={(v: number) => [fmtFull(v), "всего"]} />
                  <Area dataKey="installs" stroke="var(--accent)" fill="var(--accent-soft)" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <Empty title="История копится" />
          )}
        </div>
      </div>

      <div className="grid-3" style={{ marginBottom: 16 }}>
        <div className="panel panel-pad">
          <h3 className="panel-title">Из чего Trend Score</h3>
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
        <div className="panel panel-pad">
          <h3 className="panel-title">Динамика Score</h3>
          {q.data.score_history.length > 1 ? (
            <div style={{ height: 160 }}>
              <ResponsiveContainer>
                <LineChart data={q.data.score_history}>
                  <XAxis dataKey="date" tickFormatter={shortDate} {...axis} />
                  <YAxis domain={[0, 100]} {...axis} width={30} />
                  <Tooltip {...tooltipStyle} labelFormatter={shortDate} />
                  <Line dataKey="trend_score" stroke="var(--accent)" dot={false} strokeWidth={2} name="Score" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="muted">Появится через несколько дней наблюдений.</p>
          )}
        </div>
        <div className="panel panel-pad">
          <h3 className="panel-title">Заметка команды</h3>
          <div className="note-box">
            <textarea className="input" rows={5} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Что понравилось, какую механику взять, риски…" />
            <button className="btn sm" onClick={() => mark.mutate({ status, note: note || null })} disabled={mark.isPending}>
              Сохранить
            </button>
          </div>
        </div>
      </div>

      <div className="panel panel-pad" style={{ marginBottom: 16 }}>
        <h3 className="panel-title">
          Где в чартах <span className="faint" style={{ fontWeight: 400 }}>· {fmtDate(q.data.charts_date)}</span>
        </h3>
        {Object.keys(q.data.charts_latest).length ? (
          <div className="stack">
            {Object.entries(q.data.charts_latest).map(([coll, c]) => (
              <div key={coll}>
                <div className="label">
                  {COLLECTION_LABELS[coll] || coll} · {Object.keys(c.countries).length} стран
                </div>
                <div className="country-grid">
                  {Object.entries(c.countries)
                    .sort((a, b) => a[1] - b[1])
                    .map(([cc, rank]) => (
                      <span key={cc} className="cc" title={COUNTRY_NAMES[cc] || cc}>
                        {cc.toUpperCase()}
                        <b>#{rank}</b>
                      </span>
                    ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">Сейчас нет в чартах.</p>
        )}
        {q.data.chart_history.length > 1 && (
          <div style={{ height: 160, marginTop: 16 }}>
            <ResponsiveContainer>
              <LineChart data={q.data.chart_history}>
                <XAxis dataKey="date" tickFormatter={shortDate} {...axis} />
                <YAxis {...axis} width={30} allowDecimals={false} />
                <Tooltip {...tooltipStyle} labelFormatter={shortDate} />
                <Line dataKey="top_new_free" name="Top New" stroke="var(--accent)" dot={false} strokeWidth={2} />
                <Line dataKey="top_free" name="Top Free" stroke="var(--info)" dot={false} strokeWidth={2} />
                <Line dataKey="trending" name="Movers" stroke="var(--warn)" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      <div className="grid-2">
        <div className="panel panel-pad">
          <h3 className="panel-title">Студия: {q.data.developer?.name || "—"}</h3>
          {q.data.developer?.app_count ? <p className="muted" style={{ marginTop: -6 }}>Приложений на странице разработчика: {q.data.developer.app_count}</p> : null}
          {q.data.developer_apps.length ? (
            <table className="data">
              <tbody>
                {q.data.developer_apps.map((a) => (
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
          ) : (
            <p className="muted">Других игр студии пока не видели.</p>
          )}
        </div>
        <div className="panel panel-pad">
          <h3 className="panel-title">Ключевые слова, по которым находится</h3>
          {q.data.keywords.length ? (
            <table className="data">
              <thead>
                <tr>
                  <th>Запрос</th>
                  <th className="r">Позиция</th>
                  <th className="r">Спрос</th>
                  <th className="r">Возможность</th>
                </tr>
              </thead>
              <tbody>
                {q.data.keywords.map((k) => (
                  <tr key={k.id}>
                    <td>
                      <Link className="link" to={`/niches/${k.id}`}>{k.term}</Link>
                    </td>
                    <td className="r num">#{k.rank}</td>
                    <td className="r num">{Math.round(k.demand)}</td>
                    <td className="r num">{k.opportunity !== null ? Math.round(k.opportunity) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="muted">Пока не найдена в поиске по отслеживаемым запросам.</p>
          )}
        </div>
      </div>
    </>
  );
}
