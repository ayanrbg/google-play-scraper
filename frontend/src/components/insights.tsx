import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../api";
import { Empty } from "./ui";
import { COLLECTION_LABELS, COUNTRY_NAMES, fmtDate, fmtDateTime, fmtN } from "../format";

// ----------------------------- types -----------------------------

export type Driver = {
  key: string;
  name: string;
  level: number;
  level_label: string;
  evidence: string[];
  keywords?: { id: number; term: string; country: string; demand: number; rank: number }[];
  apps?: { app_id: string; title: string | null; icon_url: string | null; trend_score: number; v7: number | null; age_days: number | null }[];
};

export type TimelineItem = {
  date: string;
  kind: "release" | "found" | "update" | "spike";
  source?: string;
  first?: boolean;
  detail?: Record<string, any>;
  soft_launch?: string[];
  version?: string;
  ratio?: number | null;
  before?: number | null;
  after?: number | null;
  rate?: number;
  cause?: "update" | "charts" | "external";
  countries?: number;
};

export type Analysis = {
  verdict: string;
  drivers: Driver[];
  facts: string[];
  timeline: TimelineItem[];
  spikes: { start: string; end: string; rate: number; ratio: number; cause: string }[];
  updates: { date: string; version: string; ratio: number | null }[];
};

type KeyTerm = {
  term: string;
  keyword_id: number | null;
  source: "title" | "summary" | "description" | "suggest" | "known";
  in_title: boolean;
  in_summary: boolean;
  in_desc: number;
  demand: number | null;
  rank: number | null;
  searched: boolean;
  competition: number | null;
  opportunity: number | null;
  top: { app_id: string; title: string | null }[];
};

type KeyMarket = {
  lang: string;
  country: string;
  label: string;
  available?: boolean;
  localized?: boolean;
  error?: string;
  title?: string;
  summary?: string;
  words?: number;
  density?: [string, number][];
  terms?: KeyTerm[];
};

type KeysReport = {
  status: "pending" | "running" | "done" | "error" | null;
  requested_at?: string;
  finished_at?: string | null;
  progress?: { market?: string; done?: number; total?: number };
  error?: string | null;
  queue_ahead?: number | null;
  result?: { markets: KeyMarket[]; summary: { terms: number; ranked_top10: number } } | null;
};

const cc = (c: string) => COUNTRY_NAMES[c] || c.toUpperCase();

// ----------------------------- why it grows -----------------------------

export function GrowthDrivers({ analysis }: { analysis: Analysis }) {
  const [all, setAll] = useState(false);
  const shown = all ? analysis.drivers : analysis.drivers.filter((d) => d.level > 0);
  const hidden = analysis.drivers.length - shown.length;
  return (
    <div className="panel panel-pad">
      <h3 className="panel-title">Почему растёт</h3>
      <p className="verdict">{analysis.verdict}</p>
      <div className="drivers">
        {shown.map((d) => (
          <div className={`driver lvl-${d.level}`} key={d.key}>
            <div className="driver-head">
              <span className="level-dots" title={d.level_label}>
                {[1, 2, 3].map((i) => <i key={i} className={i <= d.level ? "on" : ""} />)}
              </span>
              <b>{d.name[0].toUpperCase() + d.name.slice(1)}</b>
              <span className="faint">{d.level_label}</span>
            </div>
            <ul className="evidence">
              {d.evidence.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
            {d.apps && d.apps.length > 0 && (
              <div className="mini-apps">
                {d.apps.map((a) => (
                  <Link key={a.app_id} to={`/game/${encodeURIComponent(a.app_id)}`} className="mini-app" title={`Trend Score ${Math.round(a.trend_score)}, ${fmtN(a.v7)}/день`}>
                    {a.icon_url ? <img src={a.icon_url} alt="" loading="lazy" /> : <span className="app-icon" />}
                    <span>{a.title || a.app_id}</span>
                  </Link>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
      {hidden > 0 && (
        <button className="btn ghost sm" onClick={() => setAll(true)}>
          Остальные факторы ({hidden}): не видно
        </button>
      )}
      {analysis.facts.length > 0 && (
        <ul className="facts">
          {analysis.facts.map((f, i) => <li key={i}>{f}</li>)}
        </ul>
      )}
      <p className="faint" style={{ fontSize: 12, margin: "10px 0 0" }}>
        Google не раскрывает источники установок: это оценка по тому, что видно снаружи — поиску, чартам, скачкам
        установок, обновлениям и признакам паблишера.
      </p>
    </div>
  );
}

// ----------------------------- how we found it -----------------------------

function foundText(item: TimelineItem) {
  const d = item.detail || {};
  const src = item.source || "";
  if (src.startsWith("chart:")) {
    const coll = COLLECTION_LABELS[src.slice(6)] || src.slice(6);
    const where = d.country ? ` — #${d.rank} в ${cc(d.country)}` : "";
    const wide = d.countries > 1 ? `, всего ${d.countries} стран` : "";
    return <>{item.first ? "Нашли в чарте" : "Впервые в чарте"} <b>{coll}</b>{where}{wide}</>;
  }
  switch (src) {
    case "similar":
      return d.parent ? (
        <>Нашли в «Похожих» у <Link className="link" to={`/game/${encodeURIComponent(d.parent)}`}>{d.parent_title || d.parent}</Link></>
      ) : <>Нашли в «Похожих играх»</>;
    case "developer":
      return <>Нашли на странице студии{d.developer ? <> <b>{d.developer}</b></> : null}</>;
    case "prereg":
      return <>Нашли в подборке пре-регистраций Google{d.country ? ` (${cc(d.country)})` : ""}</>;
    case "keyword":
      return <>Нашли в поиске по «{d.term}»{d.country ? ` (${cc(d.country)})` : ""}{d.rank ? `, #${d.rank}` : ""}</>;
    case "revival":
      return <>Вернули в отслеживание: всплеск в Movers & Shakers{d.countries ? ` (${d.countries} стран)` : ""}</>;
    case "legacy":
      return <>Перенесена из старой версии радара</>;
    default:
      return <>Впервые увидели</>;
  }
}

function itemText(item: TimelineItem) {
  switch (item.kind) {
    case "release":
      return item.soft_launch && item.soft_launch.length
        ? <>Глобальный релиз (до этого софт-лонч: {item.soft_launch.map((c) => c.toUpperCase()).join(", ")})</>
        : <>Релиз в Google Play</>;
    case "found":
      return foundText(item);
    case "update":
      return (
        <>Обновление <b>{item.version}</b>
          {item.ratio ? <> — скорость ×{item.ratio} ({fmtN(item.before)} → {fmtN(item.after)}/день)</> : null}
        </>
      );
    case "spike": {
      const cause = item.cause === "update" ? `рядом с обновлением ${item.version}`
        : item.cause === "charts" ? `вместе с выходом в чарты (+${item.countries} стран)`
        : "в сторе причины не видно: реклама, соцсети или подборка Google";
      return <>Скачок до <b>{fmtN(item.rate)}</b>/день (×{item.ratio}) — {cause}</>;
    }
  }
}

export function Timeline({ items }: { items: TimelineItem[] }) {
  return (
    <div className="panel panel-pad">
      <h3 className="panel-title">Как нашли и что происходило</h3>
      {items.length ? (
        <ol className="timeline">
          {items.map((it, i) => (
            <li key={i} className={`tl-${it.kind}${it.first ? " tl-first" : ""}`}>
              <span className="tl-date">{fmtDate(it.date)}</span>
              <span className="tl-text">{itemText(it)}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">История пока пуста.</p>
      )}
    </div>
  );
}

// ----------------------------- keys -----------------------------

const SOURCE_LABELS: Record<KeyTerm["source"], string> = {
  title: "название",
  summary: "краткое описание",
  description: "описание",
  suggest: "подсказка Google",
  known: "уже в выдаче",
};

const KEYS_ERRORS: Record<string, string> = {
  keys_fresh: "Отчёт свежий: пересобрать можно через сутки",
  keys_queue_full: "Очередь переполнена, попробуйте позже",
  "plan_feature:keywords": "Ключи недоступны на вашем тарифе",
  rate_limited: "Слишком много запусков с вашего адреса, попробуйте через час",
};

export function KeysPanel({ appId }: { appId: string }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["keys", appId],
    queryFn: () => api<KeysReport>(`/games/${encodeURIComponent(appId)}/keys`),
    refetchInterval: (query) => (["pending", "running"].includes(query.state.data?.status || "") ? 5000 : false),
  });
  const run = useMutation({
    mutationFn: () => api<KeysReport>(`/games/${encodeURIComponent(appId)}/keys`, { method: "POST" }),
    onSuccess: (data) => qc.setQueryData(["keys", appId], data),
  });
  const [tab, setTab] = useState(0);
  const [showNoDemand, setShowNoDemand] = useState(false);
  const rep = q.data;
  const busy = rep?.status === "pending" || rep?.status === "running";
  const markets = rep?.result?.markets || [];
  const m = markets[Math.min(tab, markets.length - 1)];
  const wasDone = rep?.status === "done" || (busy && !!rep?.result);

  // a finished report brings new keywords (and search positions) to the rest of the game page
  const wasBusy = useRef(false);
  useEffect(() => {
    if (wasBusy.current && rep?.status === "done") qc.invalidateQueries({ queryKey: ["game", appId] });
    wasBusy.current = busy;
  }, [rep?.status]);

  return (
    <div className="panel panel-pad" style={{ marginBottom: 16 }}>
      <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", marginBottom: 12 }}>
        <h3 className="panel-title" style={{ margin: 0 }}>Ключи игры</h3>
        <div className="row" style={{ flexWrap: "wrap" }}>
          {rep?.finished_at && rep.status === "done" && <span className="faint" style={{ fontSize: 12 }}>собрано {fmtDateTime(rep.finished_at)}</span>}
          <button className="btn sm primary" disabled={busy || run.isPending} onClick={() => run.mutate()}>
            {busy ? "Собираем…" : wasDone ? "Пересобрать" : "Собрать ключи"}
          </button>
        </div>
      </div>
      {run.error && (
        <div className="banner" style={{ fontSize: 13 }}>
          {run.error instanceof ApiError ? KEYS_ERRORS[run.error.code] || "Не получилось" : "Сервер недоступен"}
        </div>
      )}
      {busy && (
        <div className="banner info" style={{ fontSize: 13 }}>
          {rep?.status === "pending"
            ? <>В очереди{rep.queue_ahead ? `, перед нами ${rep.queue_ahead}` : ""}. Сбор идёт на сервере, страницу можно закрыть.</>
            : <>Собираем: {rep?.progress?.market || "…"} ({(rep?.progress?.done || 0) + 1} из {rep?.progress?.total || "?"}). Обычно 3–10 минут.</>}
        </div>
      )}
      {rep?.status === "error" && <div className="banner">Сбор не удался: {rep.error}</div>}
      {!markets.length ? (
        !busy && (
          <Empty title="Ключи ещё не собирали">
            Возьмём название и описания игры на всех языковых рынках, найдём фразы и подсказки Google, измерим
            спрос по каждой и позицию игры в поиске.
          </Empty>
        )
      ) : (
        <>
          <p className="muted" style={{ marginTop: 0 }}>
            Фраз проверено: {rep?.result?.summary.terms}, в топ-10 по {rep?.result?.summary.ranked_top10}.
          </p>
          <div className="tabs" style={{ overflowX: "auto" }}>
            {markets.map((mk, i) => {
              const top = (mk.terms || []).filter((t) => t.rank && t.rank <= 10).length;
              return (
                <button key={mk.country} className={i === tab ? "on" : ""} onClick={() => setTab(i)}>
                  {mk.country.toUpperCase()} {mk.available === false ? "—" : top ? <span className="pill">{top}</span> : null}
                </button>
              );
            })}
          </div>
          {m && <KeyMarketView m={m} appId={appId} showNoDemand={showNoDemand} onShowNoDemand={() => setShowNoDemand(true)} />}
        </>
      )}
    </div>
  );
}

function KeyMarketView({ m, appId, showNoDemand, onShowNoDemand }: { m: KeyMarket; appId: string; showNoDemand: boolean; onShowNoDemand: () => void }) {
  if (m.error) return <p className="muted">{m.label}: не удалось собрать ({m.error}).</p>;
  if (m.available === false) return <p className="muted">{m.label}: игра недоступна в этой стране.</p>;
  const terms = m.terms || [];
  const withDemand = terms.filter((t) => (t.demand || 0) > 0 || t.rank);
  const noDemand = terms.filter((t) => !((t.demand || 0) > 0 || t.rank));
  const rows = showNoDemand ? [...withDemand, ...noDemand] : withDemand;
  return (
    <div className="stack">
      <div>
        <div className="label">{m.label}{m.localized === false && " · описание не переведено"}</div>
        <div><b>{m.title}</b></div>
        {m.summary && <div className="muted">{m.summary}</div>}
      </div>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>Запрос</th>
              <th className="r" title="Как коротко Google подсказывает запрос: 100 — после пары букв">Спрос</th>
              <th className="r">Позиция</th>
              <th title="Где фраза встречается в карточке игры">В карточке</th>
              <th>Откуда</th>
              <th>Кто выше</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((t) => (
              <tr key={t.term}>
                <td>{t.keyword_id ? <Link className="link" to={`/niches/${t.keyword_id}`}>{t.term}</Link> : t.term}</td>
                <td className="r num">{t.demand === null ? "—" : Math.round(t.demand)}</td>
                <td className={`r num ${t.rank && t.rank <= 3 ? "good" : ""}`}>
                  {t.rank ? `#${t.rank}` : t.searched ? <span className="faint">&gt;30</span> : <span className="faint">—</span>}
                </td>
                <td className="muted">
                  {[t.in_title && "название", t.in_summary && "кратко", t.in_desc ? `описание ×${t.in_desc}` : null].filter(Boolean).join(", ") || <span className="faint">нет</span>}
                </td>
                <td className="muted">{SOURCE_LABELS[t.source]}</td>
                <td className="muted" style={{ maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis" }}>
                  {t.top.filter((a) => a.app_id !== appId).slice(0, 2).map((a, i) => (
                    <span key={a.app_id}>
                      {i > 0 && ", "}
                      <Link className="link" to={`/game/${encodeURIComponent(a.app_id)}`}>{a.title || a.app_id}</Link>
                    </span>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!showNoDemand && noDemand.length > 0 && (
        <button className="btn ghost sm" style={{ alignSelf: "flex-start" }} onClick={onShowNoDemand}>
          Показать фразы без спроса ({noDemand.length}): их нет в подсказках Google
        </button>
      )}
      {m.density && m.density.length > 0 && (
        <div>
          <div className="label">Частые слова в описании · всего слов {m.words}</div>
          <div className="country-grid">
            {m.density.map(([w, n]) => (
              <span key={w} className="cc">{w}<b>{n}</b></span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
