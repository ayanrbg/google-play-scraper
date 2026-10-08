import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Game, api } from "../api";
import { CardStat, Empty, Loader, PageSub } from "../components/ui";
import { COUNTRY_NAMES, MARK_LABELS, fmtAccel, fmtAge, fmtDateTime, fmtN, fmtRating } from "../format";
import { MarkButtons } from "./Radar";
import { roomText } from "./Niches";

type PickKey = {
  term: string; country: string; demand: number; rank: number; young: number; proof?: number;
  keyword_id: number | null; room: number | null; room_best: number | null; fresh: number | null; entry_score: number | null;
};
type Rival = { app_id: string; title: string | null; icon_url: string | null; installs: number | null; v7: number | null; age_days: number | null };
type Pick = Game & {
  pick: {
    tier: "top" | "more"; niche: string | null; why: string | null; entry: string | null; risks: string | null;
    keys: PickKey[]; rivals: Rival[]; added_at: string; updated_at: string;
  };
};

export default function Picks() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["picks"], queryFn: () => api<{ items: Pick[]; updated_at: string | null }>("/picks") });
  const mark = useMutation({
    mutationFn: ({ id, status, note }: { id: string; status: string | null; note: string | null }) =>
      api(`/games/${encodeURIComponent(id)}/mark`, { method: "PUT", body: { status, note } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["picks"] });
      qc.invalidateQueries({ queryKey: ["games"] });
    },
  });

  if (q.isLoading) return <Loader />;
  const items = q.data?.items || [];
  const top = items.filter((g) => g.pick.tier === "top");
  const more = items.filter((g) => g.pick.tier !== "top");
  const onMark = (g: Pick) => (s: string | null) => mark.mutate({ id: g.app_id, status: s, note: g.note });

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Под реализацию</h1>
          <PageSub>
            Игры, отобранные вручную по данным базы. <b>Растут органически</b>: нет признаков закупки трафика, издателя
            или бренда. <b>В поиске есть куда зайти</b>: по их запросам со спросом в топ-10 уже пробились молодые игры
            других студий, и не одна, значит Google пускает новичков. Запросы взяты из разных языковых рынков:
            с локализацией можно заходить сразу в несколько. Цифры живые, обновляются каждый день. Текст разбора
            и ключи — на дату подборки{q.data?.updated_at ? ` (${fmtDateTime(q.data.updated_at)})` : ""}.
          </PageSub>
        </div>
      </div>
      {!items.length && <Empty title="Подборка пока пуста" />}
      {top.length > 0 && <div className="picks">{top.map((g, i) => <PickCard key={g.app_id} g={g} n={i + 1} onMark={onMark(g)} />)}</div>}
      {more.length > 0 && (
        <>
          <h2 className="picks-section">
            Ещё кандидаты <span className="faint">{more.length}</span>
          </h2>
          <p className="muted" style={{ margin: "0 0 14px", maxWidth: 720 }}>
            Тоже проходят отбор, но слабее по одному из признаков: рост меньше, ниша уже, топ плотнее или тренд может быстро
            остыть. Разбор свёрнут: нажмите, чтобы открыть.
          </p>
          <div className="picks">{more.map((g, i) => <PickCard key={g.app_id} g={g} n={top.length + i + 1} onMark={onMark(g)} folded />)}</div>
        </>
      )}
    </>
  );
}

function PickCard({ g, n, onMark, folded }: { g: Pick; n: number; onMark: (s: string | null) => void; folded?: boolean }) {
  const p = g.pick;
  const body = (
    <>
      {p.why && <Section title="Почему стоит делать">{p.why}</Section>}
      {(p.entry || p.keys.length > 0) && (
        <Section title="Как зайти в поиск">
          {p.entry}
          {p.keys.length > 0 && <KeysTable keys={p.keys} />}
        </Section>
      )}
      {p.rivals.length > 0 && (
        <Section title="Кто из новичков уже пробился">
          <div className="pick-rivals">
            {p.rivals.map((r) => (
              <Link key={r.app_id} to={`/game/${encodeURIComponent(r.app_id)}`} className="pick-rival" title={r.title || r.app_id}>
                {r.icon_url ? <img className="app-icon" src={r.icon_url} alt="" loading="lazy" /> : <span className="app-icon" />}
                <span className="app-meta">
                  <span className="app-title">{r.title || r.app_id}</span>
                  <span className="app-dev num">
                    {fmtN(r.installs)} · {fmtAge(r.age_days)}
                    {r.v7 ? ` · ${fmtN(r.v7)}/день` : ""}
                  </span>
                </span>
              </Link>
            ))}
          </div>
        </Section>
      )}
      {p.risks && (
        <Section title="Риски" tone="warn">
          {p.risks}
        </Section>
      )}
    </>
  );
  return (
    <article className="panel pick">
      <div className="pick-head">
        <span className="pick-n num">{n}</span>
        <Link to={`/game/${encodeURIComponent(g.app_id)}`} className="pick-app">
          {g.icon_url ? <img className="app-icon" src={g.icon_url} alt="" /> : <span className="app-icon" />}
          <span className="app-meta">
            <span className="app-title">{g.title}</span>
            <span className="app-dev">
              {g.developer}
              {g.genre ? ` · ${g.genre}` : ""}
            </span>
          </span>
        </Link>
        <span className="pick-mark">
          {g.mark && <span className="pill">{MARK_LABELS[g.mark]}</span>}
          <MarkButtons game={g} onMark={onMark} />
        </span>
      </div>
      {p.niche && <div className="pick-niche">{p.niche}</div>}
      <div className="card-stats pick-stats">
        <CardStat label="Возраст">{fmtAge(g.age_days)}</CardStat>
        <CardStat label="Установки">{fmtN(g.installs)}</CardStat>
        <CardStat label="В день, 7д">{fmtN(g.v7)}</CardStat>
        <CardStat label="Ускорение" className={g.accel && g.accel >= 1.1 ? "delta-up" : g.accel && g.accel < 0.9 ? "delta-down" : ""}>
          {fmtAccel(g.accel)}
        </CardStat>
        <CardStat label="Рейтинг">{fmtRating(g.rating)}</CardStat>
      </div>
      {folded ? (
        <details className="pick-more">
          <summary>{p.why ? p.why.split(/(?<=\.)\s/)[0] : "Разбор"}</summary>
          {body}
        </details>
      ) : (
        body
      )}
    </article>
  );
}

function Section({ title, tone, children }: { title: string; tone?: "warn"; children: React.ReactNode }) {
  return (
    <section className={`pick-sec ${tone || ""}`}>
      <h3>{title}</h3>
      <div>{children}</div>
    </section>
  );
}

function KeysTable({ keys }: { keys: PickKey[] }) {
  return (
    <div className="table-wrap pick-keys">
      <table className="data">
        <thead>
          <tr>
            <th>Запрос</th>
            <th>Рынок</th>
            <th className="r" title="Спрос по автодополнению Google Play, 0–100">Спрос</th>
            <th className="r" title="Место этой игры в выдаче">Игра</th>
            <th className="r" title="Молодых игр (до года) других студий в топ-10 выдачи">Новичков в топ-10</th>
            <th className="r" title="Мест в топ-10, которые может занять новая игра, и самое высокое из них (на сегодня)">Место для нас</th>
          </tr>
        </thead>
        <tbody>
          {keys.map((k) => (
            <tr key={`${k.term}|${k.country}`}>
              <td>{k.keyword_id ? <Link className="link" to={`/niches/${k.keyword_id}`}>{k.term}</Link> : k.term}</td>
              <td className="muted" title={COUNTRY_NAMES[k.country] || k.country}>{k.country.toUpperCase()}</td>
              <td className="r num">{Math.round(k.demand)}</td>
              <td className="r num">#{k.rank}</td>
              <td className="r num">{k.young}</td>
              <td className={`r num ${(k.room ?? 0) >= 3 ? "good" : k.room === 0 ? "bad" : ""}`}>{roomText(k)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
