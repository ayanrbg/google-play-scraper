export class ApiError extends Error {
  constructor(public status: number, public code: string) {
    super(code);
  }
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; params?: Record<string, any> } = {}): Promise<T> {
  let url = `/api${path}`;
  if (opts.params) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(opts.params)) {
      if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
    }
    const s = qs.toString();
    if (s) url += `?${s}`;
  }
  const res = await fetch(url, {
    method: opts.method || "GET",
    credentials: "same-origin",
    headers: opts.body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    let code = String(res.status);
    try {
      const j = await res.json();
      code = typeof j.detail === "string" ? j.detail : code;
    } catch {}
    throw new ApiError(res.status, code);
  }
  return res.json();
}

export type Me = {
  id: number;
  email: string;
  name: string | null;
  role: "owner" | "member";
  is_superadmin: boolean;
  workspace: { id: number; name: string; plan: string };
  plan: { label: string; keywords: boolean; export: boolean; max_rows: number | null; seats: number };
};

export type Game = {
  app_id: string;
  title: string | null;
  developer: string | null;
  developer_id: string | null;
  icon_url: string | null;
  genre_id: string | null;
  genre: string | null;
  released: string | null;
  age_days: number | null;
  pre_register: boolean;
  soft_launch: boolean;
  soft_launch_markets: string[];
  revival: boolean;
  hidden_gem: boolean;
  chart_countries_any: number;
  installs: number | null;
  v7: number | null;
  v7_prev: number | null;
  accel: number | null;
  v_life: number | null;
  rating: number | null;
  ratings: number | null;
  new_countries: number;
  top_countries: number;
  trending_countries: number;
  grossing_countries: number;
  breadth_delta7: number;
  best_rank: number | null;
  search_visibility: number;
  search_keywords: number;
  trend_score: number;
  score_parts: Record<string, number | boolean>;
  brand_flags: string[];
  dev_max_installs: number | null;
  dev_app_count: number | null;
  contains_ads: boolean;
  offers_iap: boolean;
  spark: (number | null)[];
  data_days: number;
  mark: string | null;
  note: string | null;
};

export type Keyword = {
  id: number;
  term: string;
  country: string;
  seed: string | null;
  demand: number;
  competition: number | null;
  opportunity: number | null;
  top_median_installs: number | null;
  top_avg_rating: number | null;
  young_share: number | null;
  young_best_installs: number | null;
  brand_share: number | null;
  title_match_share: number | null;
  games_share: number | null;
  analyzed_at: string | null;
};

export type Page<T> = { total: number; page: number; page_size: number; items: T[]; limited_to?: number | null };
