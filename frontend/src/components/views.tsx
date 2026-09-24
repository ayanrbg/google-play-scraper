import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../api";
import { ERROR_TEXT } from "../format";

type View = { id: number; name: string; params: Record<string, string> };

/** Saved filter presets, shared by the whole workspace. */
export function SavedViews({ page, current, onApply }: {
  page: string; current: () => Record<string, string>; onApply: (p: Record<string, string>) => void;
}) {
  const qc = useQueryClient();
  const views = useQuery({ queryKey: ["views", page], queryFn: () => api<View[]>("/views", { params: { page } }) });
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () => api("/views", { method: "POST", body: { page, name, params: current() } }),
    onSuccess: () => {
      setNaming(false);
      setName("");
      qc.invalidateQueries({ queryKey: ["views", page] });
    },
    onError: (e) => setError(e instanceof ApiError ? ERROR_TEXT[e.code] || e.code : "Ошибка"),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api(`/views/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["views", page] }),
  });

  return (
    <div>
      <div className="chips" style={{ marginBottom: 8 }}>
        {(views.data || []).map((v) => (
          <span key={v.id} className="chip" style={{ display: "inline-flex", alignItems: "center", gap: 6 }} onClick={() => onApply(v.params)}>
            {v.name}
            <span
              className="faint"
              title="Удалить"
              onClick={(e) => {
                e.stopPropagation();
                if (confirm(`Удалить фильтр «${v.name}»?`)) remove.mutate(v.id);
              }}
            >
              ×
            </span>
          </span>
        ))}
        {!views.data?.length && <span className="faint" style={{ fontSize: 12 }}>Пока нет сохранённых</span>}
      </div>
      {naming ? (
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) save.mutate();
          }}
        >
          <input className="input" autoFocus placeholder="Название" value={name} onChange={(e) => setName(e.target.value)} />
          <button className="btn sm primary">OK</button>
        </form>
      ) : (
        <button className="btn sm" onClick={() => setNaming(true)}>
          + Сохранить текущий
        </button>
      )}
      {error && <div className="error">{error}</div>}
    </div>
  );
}
