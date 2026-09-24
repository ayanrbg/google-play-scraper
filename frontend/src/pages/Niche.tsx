import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Keyword, api } from "../api";
import { Empty, Flags, Loader, Stat } from "../components/ui";
import { fmtAge, fmtN, fmtPct, fmtRating } from "../format";

type Detail = {
  keyword: Keyword;
  results: { rank: number; app_id: string; title: string; developer: string; icon_url: string; genre: string; released: string | null;
    installs: number | null; rating: number | null; trend_score: number | null; brand_flags: string[] }[];
  related: Keyword[];
};

const ageDays = (d: string | null) => (d ? Math.floor((Date.now() - new Date(d).getTime()) / 86400000) : null);

export default function NichePage() {
  const { id } = useParams();
  const q = useQuery({ queryKey: ["keyword", id], queryFn: () => api<Detail>(`/keywords/${id}`) });
  if (q.isLoading) return <Loader />;
  if (!q.data) return <Empty title="Запрос не найден" />;
  const k = q.data.keyword;
  return (
    <>
      <p style={{ margin: "0 0 16px" }}>
        <Link className="link" to="/niches">← Ниши</Link>
      </p>
      <div className="page-head">
        <div>
          <h1 className="page-title">«{k.term}»</h1>
          <p className="page-sub">Выдача Google Play ({k.country.toUpperCase()}), от сида «{k.seed}».</p>
        </div>
        <a className="btn sm" target="_blank" rel="noreferrer" href={`https://play.google.com/store/search?q=${encodeURIComponent(k.term)}&c=apps&gl=${k.country}`}>
          Открыть выдачу ↗
        </a>
      </div>
      <div className="stats" style={{ marginBottom: 16 }}>
        <Stat label="Возможность" value={k.opportunity !== null ? Math.round(k.opportunity) : "—"} />
        <Stat label="Спрос" value={Math.round(k.demand)} />
        <Stat label="Конкуренция" value={k.competition !== null ? Math.round(k.competition) : "—"} />
        <Stat label="Молодые в топ-10" value={fmtPct(k.young_share)} note={`лучший: ${fmtN(k.young_best_installs)}`} />
        <Stat label="Медиана топ-10" value={fmtN(k.top_median_installs)} note={`рейтинг ${fmtRating(k.top_avg_rating)}`} />
        <Stat label="Бренды в топе" value={fmtPct(k.brand_share)} note={`точных названий ${fmtPct(k.title_match_share)}`} />
      </div>
      <div className="grid-2" style={{ gridTemplateColumns: "2fr 1fr" }}>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>#</th>
                <th>Игра</th>
                <th className="r">Возраст</th>
                <th className="r">Установки</th>
                <th className="r">★</th>
                <th className="r">Score</th>
              </tr>
            </thead>
            <tbody>
              {q.data.results.map((r) => (
                <tr key={r.app_id}>
                  <td className="num muted">{r.rank}</td>
                  <td>
                    <Link to={`/game/${encodeURIComponent(r.app_id)}`} className="app-cell">
                      {r.icon_url ? <img className="app-icon" src={r.icon_url} alt="" loading="lazy" /> : <div className="app-icon" />}
                      <div className="app-meta">
                        <div className="app-title">{r.title || r.app_id}</div>
                        <div className="app-dev">
                          {r.developer} <Flags flags={r.brand_flags} age={ageDays(r.released)} />
                        </div>
                      </div>
                    </Link>
                  </td>
                  <td className={`r num ${(ageDays(r.released) ?? 9999) <= 365 ? "good" : ""}`}>{fmtAge(ageDays(r.released))}</td>
                  <td className="r num">{fmtN(r.installs)}</td>
                  <td className="r num">{fmtRating(r.rating)}</td>
                  <td className="r num">{r.trend_score !== null ? Math.round(r.trend_score) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="panel panel-pad">
          <h3 className="panel-title">Соседние запросы</h3>
          {q.data.related.map((r) => (
            <div key={r.id} className="row" style={{ justifyContent: "space-between", padding: "5px 0", borderBottom: "1px solid var(--line)" }}>
              <Link className="link" to={`/niches/${r.id}`}>{r.term}</Link>
              <span className="num muted">
                {Math.round(r.demand)} / {r.opportunity !== null ? Math.round(r.opportunity) : "—"}
              </span>
            </div>
          ))}
          {!q.data.related.length && <p className="muted">Нет</p>}
        </div>
      </div>
    </>
  );
}
