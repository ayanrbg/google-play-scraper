import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../api";
import { Meter } from "./ui";
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
  popular?: { rank: number; collection: string; days: number };   // where the game gets its players, by charts
};

const popularText = (p: NonNullable<KeyMarket["popular"]>) =>
  `#${p.rank} в ${COLLECTION_LABELS[p.collection] || p.collection}, в чартах ${p.days} дн. из последних 14`;

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
  title: "из названия",
  summary: "из краткого описания",
  description: "из описания",
  suggest: "из подсказок Google",
  known: "игра уже в выдаче",
};

const KEYS_ERRORS: Record<string, string> = {
  keys_fresh: "Отчёт свежий: пересобрать можно через сутки",
  keys_queue_full: "Очередь переполнена, попробуйте позже",
  "plan_feature:keywords": "Ключи недоступны на вашем тарифе",
  rate_limited: "С вашего адреса уже было много сборов, попробуйте позже или войдите в аккаунт",
  keys_guest_budget: "Гостевые сборы на сегодня закончились: попробуйте завтра или войдите в аккаунт",
};

/** The keys report of a game: shared by the overview card and the "Search & keys" tab (one query, one cache). */
function useKeys(appId: string) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["keys", appId],
    queryFn: () => api<KeysReport>(`/games/${encodeURIComponent(appId)}/keys`),
    refetchInterval: (query) => (["pending", "running"].includes(query.state.data?.status || "") ? 5000 : false),
  });
  const run = useMutation({
    mutationKey: ["keys-run", appId],
    mutationFn: () => api<KeysReport>(`/games/${encodeURIComponent(appId)}/keys`, { method: "POST" }),
    onSuccess: (data) => qc.setQueryData(["keys", appId], data),
  });
  const rep = q.data;
  const busy = rep?.status === "pending" || rep?.status === "running";
  const markets = rep?.result?.markets || [];
  const error = run.error ? (run.error instanceof ApiError ? KEYS_ERRORS[run.error.code] || "Не получилось" : "Сервер недоступен") : null;
  return { q, run, rep, busy, markets, error };
}

type Found = { term: string; country: string; rank: number; demand: number | null };

/** The phrases a game is found by best, one chip per phrase with the countries where it is that high. */
function topPhrases(found: Found[], n: number) {
  const by = new Map<string, Found[]>();
  for (const f of [...found].sort((a, b) => a.rank - b.rank || (b.demand || 0) - (a.demand || 0))) {
    by.set(f.term, [...(by.get(f.term) || []), f]);
  }
  return [...by.values()].slice(0, n).map((fs) => ({
    term: fs[0].term,
    rank: fs[0].rank,
    countries: fs.filter((f) => f.rank === fs[0].rank).map((f) => f.country),
  }));
}

const reportFound = (markets: KeyMarket[]): Found[] =>
  markets.flatMap((m) => (m.terms || []).filter((t) => t.rank).map((t) => ({ term: t.term, country: m.country, rank: t.rank!, demand: t.demand })));

/** Phrase x country pairs where the game is in the top 10: from the report when there is one. */
export function useKeysTop10(appId: string, known: { rank: number }[]) {
  const { markets } = useKeys(appId);
  return markets.length ? reportStats(markets).top10 : known.filter((k) => k.rank <= 10).length;
}

function reportStats(markets: KeyMarket[]) {
  const terms = markets.flatMap((m) => m.terms || []);
  return {
    terms: terms.length,
    top3: terms.filter((t) => t.rank && t.rank <= 3).length,
    top10: terms.filter((t) => t.rank && t.rank <= 10).length,
    markets: markets.filter((m) => m.available !== false && !m.error).length,
  };
}

export function RankBadge({ rank, searched = true }: { rank: number | null; searched?: boolean }) {
  if (!rank) return <span className="rank none" title={searched ? "Игры нет в первых 30 результатах" : "Не проверяли"}>{searched ? "нет" : "—"}</span>;
  const tone = rank <= 3 ? "r3" : rank <= 10 ? "r10" : "r30";
  return <span className={`rank ${tone}`}>#{rank}</span>;
}

function Progress({ rep }: { rep: KeysReport }) {
  const done = rep.progress?.done || 0;
  const total = rep.progress?.total || 0;
  return (
    <div className="keys-progress">
      <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", fontSize: 13 }}>
        <span>
          {rep.status === "pending"
            ? <>В очереди{rep.queue_ahead ? `, перед нами ${rep.queue_ahead}` : ""}…</>
            : <>Собираем: {rep.progress?.market || "…"}{total ? ` (${done + 1} из ${total})` : ""}</>}
        </span>
        <span className="faint" style={{ fontSize: 12 }}>обычно 3–10 минут, страницу можно закрыть</span>
      </div>
      <div className="meter"><i className={rep.status === "pending" ? "pulse" : ""} style={{ width: total ? `${Math.max(4, (done / total) * 100)}%` : "4%" }} /></div>
    </div>
  );
}

const SearchIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
    <circle cx="10.5" cy="10.5" r="6.5" />
    <path d="M15.5 15.5L21 21" />
  </svg>
);

function KwChips({ found }: { found: Found[] }) {
  const items = topPhrases(found, 5);
  if (!items.length) return null;
  return (
    <div className="kw-chips">
      {items.map((t) => (
        <span key={t.term} className="kw-chip" title={t.countries.map(cc).join(", ")}>
          {t.term}<b>#{t.rank}</b>
          <small>{t.countries.slice(0, 3).map((c) => c.toUpperCase()).join(" ")}{t.countries.length > 3 ? ` +${t.countries.length - 3}` : ""}</small>
        </span>
      ))}
    </div>
  );
}

/** The overview's pointer to the keys report: what it already shows, or what one click will collect. */
export function KeysTeaser({ appId, known, onOpen }: {
  appId: string;
  known: { term: string; country: string; rank: number; demand: number }[];
  onOpen: () => void;
}) {
  const { rep, busy, markets, run, error } = useKeys(appId);
  let body;
  let action;
  if (markets.length && !busy) {
    const s = reportStats(markets);
    body = (
      <>
        <p>
          Проверили {s.terms} фраз в {s.markets} странах: игра в топ-10 по <b>{s.top10}</b>, в топ-3 по <b>{s.top3}</b>.
          {rep?.finished_at && <span className="faint"> Собрано {fmtDateTime(rep.finished_at)}.</span>}
        </p>
        <KwChips found={reportFound(markets)} />
      </>
    );
    action = <button className="btn primary" onClick={onOpen}>Открыть отчёт по ключам →</button>;
  } else if (busy && rep) {
    body = <Progress rep={rep} />;
    action = <button className="btn" onClick={onOpen}>Смотреть →</button>;
  } else {
    const top = known.filter((k) => k.rank <= 10);
    const phrases = new Set(top.map((k) => k.term)).size;
    const countries = new Set(top.map((k) => k.country)).size;
    body = (
      <>
        <p>
          {top.length
            ? <>По ежедневному мониторингу игра в топ-10 по {phrases} запросам в {countries} {countries === 1 ? "стране" : "странах"}. </>
            : <>Пока не знаем, по каким запросам её находят. </>}
          Отчёт проверит все фразы из карточки и подсказок Google по 10+ странам: спрос, место игры и кто выше.
        </p>
        <KwChips found={top} />
      </>
    );
    action = (
      <button className="btn primary" disabled={run.isPending} onClick={() => { run.mutate(); onOpen(); }}>
        Собрать отчёт по ключам
      </button>
    );
  }
  return (
    <div className="keys-cta">
      <div className="keys-cta-icon"><SearchIcon /></div>
      <div className="keys-cta-body">
        <h3>Как игру находят в поиске Google Play</h3>
        {body}
        {error && <div className="error" style={{ marginBottom: 0 }}>{error}</div>}
      </div>
      {action}
    </div>
  );
}

export function KeysPanel({ appId }: { appId: string }) {
  const qc = useQueryClient();
  const { q, run, rep, busy, markets, error } = useKeys(appId);
  const [tab, setTab] = useState(0);
  const m = markets[Math.min(tab, markets.length - 1)];
  const wasDone = rep?.status === "done" || (busy && !!rep?.result);

  // a finished report brings new keywords (and search positions) to the rest of the game page
  const wasBusy = useRef(false);
  useEffect(() => {
    if (wasBusy.current && rep?.status === "done") qc.invalidateQueries({ queryKey: ["game", appId] });
    wasBusy.current = busy;
  }, [rep?.status]);

  const s = reportStats(markets);
  return (
    <div className="panel panel-pad" style={{ marginBottom: 16 }}>
      <div className="panel-head">
        <div>
          <h3 className="panel-title">Отчёт по ключам</h3>
          <p>По каким запросам игру ищут в Google Play, насколько они популярны и на каком месте игра в выдаче.</p>
        </div>
        {(wasDone || busy) && (
          <div className="row" style={{ flexWrap: "wrap" }}>
            {rep?.finished_at && rep.status === "done" && <span className="faint" style={{ fontSize: 12 }}>собрано {fmtDateTime(rep.finished_at)}</span>}
            <button className="btn sm" disabled={busy || run.isPending} onClick={() => run.mutate()}>
              {busy ? "Собираем…" : "Пересобрать"}
            </button>
          </div>
        )}
      </div>
      {error && <div className="banner" style={{ fontSize: 13 }}>{error}</div>}
      {busy && rep && <Progress rep={rep} />}
      {rep?.status === "error" && <div className="banner">Сбор не удался: {rep.error}</div>}
      {!markets.length ? (
        !busy && !q.isLoading && (
          <div className="keys-intro">
            <div className="keys-steps">
              <div className="keys-step"><b>1. Фразы</b>Берём название и описания игры на языке каждой страны и добавляем подсказки Google.</div>
              <div className="keys-step"><b>2. Спрос</b>Меряем, насколько часто ищут каждую фразу: чем раньше Google её подсказывает, тем выше спрос.</div>
              <div className="keys-step"><b>3. Позиции</b>Ищем фразу в Google Play и смотрим место игры и кто стоит выше.</div>
            </div>
            <button className="btn primary lg" disabled={run.isPending} onClick={() => run.mutate()}>Собрать отчёт по ключам</button>
            <span className="faint" style={{ fontSize: 12 }}>Займёт 3–10 минут. Кроме основных рынков — страны, где игра популярна по чартам.</span>
          </div>
        )
      ) : (
        <>
          <div className="stats" style={{ marginBottom: 16 }}>
            <div className="stat"><div className="stat-label">Фраз проверено</div><div className="stat-value">{s.terms}</div></div>
            <div className="stat"><div className="stat-label">В топ-3</div><div className="stat-value good">{s.top3}</div></div>
            <div className="stat"><div className="stat-label">В топ-10</div><div className="stat-value accent">{s.top10}</div></div>
            <div className="stat"><div className="stat-label">Стран</div><div className="stat-value">{s.markets}</div></div>
          </div>
          <div className="tabs" style={{ overflowX: "auto" }}>
            {markets.map((mk, i) => {
              const top = (mk.terms || []).filter((t) => t.rank && t.rank <= 10).length;
              return (
                <button key={mk.country} className={i === tab ? "on" : ""} onClick={() => setTab(i)}
                  title={cc(mk.country) + (top ? `: в топ-10 по ${top}` : "") + (mk.popular ? `. Популярна: ${popularText(mk.popular)}` : "")}>
                  {mk.country.toUpperCase()} {mk.available === false ? "—" : top ? <span className="pill">{top}</span> : null}
                </button>
              );
            })}
          </div>
          {m && <KeyMarketView key={m.country} m={m} appId={appId} />}
        </>
      )}
    </div>
  );
}

type TermFilter = "all" | "top" | "missed";

function KeyMarketView({ m, appId }: { m: KeyMarket; appId: string }) {
  const [filter, setFilter] = useState<TermFilter>("all");
  const [showNoDemand, setShowNoDemand] = useState(false);
  if (m.error) return <p className="muted">{m.label}: не удалось собрать ({m.error}).</p>;
  if (m.available === false) return <p className="muted">{m.label}: игра недоступна в этой стране.</p>;
  const terms = m.terms || [];
  const hasDemand = (t: KeyTerm) => (t.demand || 0) > 0 || !!t.rank;
  const top = terms.filter((t) => t.rank && t.rank <= 10);
  const missed = terms.filter((t) => t.searched && (t.demand || 0) >= 20 && (!t.rank || t.rank > 30));
  const noDemand = terms.filter((t) => !hasDemand(t));
  const rows = filter === "top" ? top : filter === "missed" ? missed
    : showNoDemand ? terms.filter(hasDemand).concat(noDemand) : terms.filter(hasDemand);
  return (
    <div className="stack">
      <div>
        <div className="muted" style={{ fontSize: 12.5 }}>
          {m.label}{m.localized === false && " · описание не переведено"}
          {m.popular && <> · игра популярна здесь: {popularText(m.popular)}</>}
        </div>
        <div><b>{m.title}</b>{m.summary && <span className="muted"> — {m.summary}</span>}</div>
      </div>
      <div className="chips">
        <button className={`chip ${filter === "all" ? "on" : ""}`} onClick={() => setFilter("all")}>Все фразы</button>
        <button className={`chip ${filter === "top" ? "on" : ""}`} onClick={() => setFilter("top")}>Игра в топ-10 · {top.length}</button>
        <button className={`chip ${filter === "missed" ? "on" : ""}`} onClick={() => setFilter("missed")}
          title="Запросы со спросом, по которым игры нет в первых 30 результатах: точки роста для ASO">
          Есть спрос, игры нет · {missed.length}
        </button>
      </div>
      {rows.length ? (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Запрос</th>
                <th className="r" title="Место игры в поиске Google Play по этому запросу (проверяем первые 30)">Место</th>
                <th className="r" title="Как часто ищут: 100 — Google подсказывает запрос уже после пары букв">Спрос</th>
                <th title="Где фраза встречается в карточке игры">В карточке</th>
                <th>Кто в топе</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.term}>
                  <td title={SOURCE_LABELS[t.source]}>
                    {t.keyword_id ? <Link className="link" to={`/niches/${t.keyword_id}`}>{t.term}</Link> : t.term}
                  </td>
                  <td className="r"><RankBadge rank={t.rank} searched={t.searched} /></td>
                  <td className="r">
                    <div className="demand">
                      <Meter value={t.demand} />
                      <span className="num">{t.demand === null ? "—" : Math.round(t.demand)}</span>
                    </div>
                  </td>
                  <td className="muted">
                    {[t.in_title && "название", t.in_summary && "кратко", t.in_desc ? `описание ×${t.in_desc}` : null].filter(Boolean).join(", ") || <span className="faint">нет</span>}
                  </td>
                  <td className="muted" style={{ maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis" }}>
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
      ) : (
        <p className="muted">{filter === "top" ? "В этой стране игра не в топ-10 ни по одной фразе." : "Таких фраз нет."}</p>
      )}
      {filter === "all" && !showNoDemand && noDemand.length > 0 && (
        <button className="btn ghost sm wrap" style={{ alignSelf: "flex-start" }} onClick={() => setShowNoDemand(true)}>
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
