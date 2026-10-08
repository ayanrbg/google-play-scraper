import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Keyword, api } from "../api";
import { BackLink, Empty, Flags, Loader, PageSub, Stat } from "../components/ui";
import { fmtAge, fmtN, fmtPct, fmtRating } from "../format";

type Detail = {
  keyword: Keyword;
  results: { rank: number; app_id: string; title: string; developer: string; icon_url: string; genre: string; released: string | null;
    installs: number | null; rating: number | null; trend_score: number | null; brand_flags: string[]; v7: number | null;
    slot: { kind: string; takeable: boolean; reasons?: string[] } | null }[];
  related: Keyword[];
};

// Why a top-10 place could go to a new game (or why not)
const SLOT_LABELS: Record<string, [string, string]> = {
  fresh: ["свежая", "Моложе 3 месяцев: Google пускает новичков сюда прямо сейчас"],
  young_small: ["новичок", "Молодая игра попала сюда с небольшими установками: так может и наша"],
  small: ["маленькая", "Меньше 100 тыс. установок"],
  low_rating: ["низкий рейтинг", "Рейтинг ниже 3.8: хорошая игра её обойдёт"],
  abandoned: ["заброшена", "Не обновлялась больше года"],
  brand: ["бренд", "Издатель или франшиза: это место не взять"],
  strong: ["сильная", "Большая, живая игра: обойти трудно"],
  unknown: ["?", "Карточку игры ещё не скачали"],
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
      <BackLink to="/niches" label="Ниши" />
      <div className="page-head">
        <div>
          <h1 className="page-title">«{k.term}»</h1>
          <PageSub>Выдача Google Play ({k.country.toUpperCase()}), от сида «{k.seed}».</PageSub>
        </div>
        <a className="btn sm" target="_blank" rel="noreferrer" href={`https://play.google.com/store/search?q=${encodeURIComponent(k.term)}&c=apps&gl=${k.country}`}>
          Открыть выдачу ↗
        </a>
      </div>
      <div className="stats" style={{ marginBottom: 16 }}>
        <Stat label="Вход для новичка" value={k.entry_score !== null ? Math.round(k.entry_score) : "—"}
              note={k.room !== null ? `мест ${k.room}/10${k.room_best ? `, лучшее #${k.room_best}` : ""}` : "ещё не посчитано"} />
        <Stat label="Свежие в топ-10" value={k.fresh_count ?? "—"} note="моложе 3 месяцев" />
        <Stat label="Новички растут" value={k.entrants_growing ?? "—"} note={k.entrants_v7 ? `медиана ${fmtN(k.entrants_v7)}/день` : "скорость молодых в топе"} />
        <Stat label="Вошли за неделю" value={k.churn7 ?? "—"} note={k.churn7 === null ? "история выдачи копится" : "новых игр в топ-10"} />
        <Stat label="Возможность" value={k.opportunity !== null ? Math.round(k.opportunity) : "—"} />
        <Stat label="Спрос" value={Math.round(k.demand)} />
        <Stat label="Конкуренция" value={k.competition !== null ? Math.round(k.competition) : "—"} />
        <Stat label="Молодые в топ-10" value={fmtPct(k.young_share)} note={`лучший: ${fmtN(k.young_best_installs)}`} />
        <Stat label="Медиана топ-10" value={fmtN(k.top_median_installs)} note={`рейтинг ${fmtRating(k.top_avg_rating)}`} />
        <Stat label="Бренды в топе" value={fmtPct(k.brand_share)} note={`точных названий ${fmtPct(k.title_match_share)}`} />
      </div>
      <div className="grid-2 wide-left">
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>#</th>
                <th>Игра</th>
                <th className="r">Возраст</th>
                <th className="r">Установки</th>
                <th className="r" title="Установок в день за 7 дней">В день</th>
                <th className="r">★</th>
                <th title="Может ли новая игра занять это место">Место</th>
              </tr>
            </thead>
            <tbody>
              {q.data.results.map((r) => (
                <tr key={r.app_id} className={r.slot?.takeable ? "slot-open" : ""}>
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
                  <td className="r num">{fmtN(r.v7)}</td>
                  <td className="r num">{fmtRating(r.rating)}</td>
                  <td>{r.slot && <SlotTag slot={r.slot} />}</td>
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

function SlotTag({ slot }: { slot: { kind: string; takeable: boolean; reasons?: string[] } }) {
  const kinds = slot.reasons?.length ? slot.reasons : [slot.kind];
  return (
    <span className={`slot ${slot.takeable ? "open" : slot.kind}`} title={kinds.map((x) => SLOT_LABELS[x]?.[1] || x).join(". ")}>
      {slot.takeable ? "✓ " : ""}
      {kinds.map((x) => SLOT_LABELS[x]?.[0] || x).join(", ")}
    </span>
  );
}
