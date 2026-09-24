const compact = new Intl.NumberFormat("ru-RU", { notation: "compact", maximumFractionDigits: 1 });
const full = new Intl.NumberFormat("ru-RU");

export const fmtN = (v: number | null | undefined) => (v === null || v === undefined ? "—" : compact.format(v));
export const fmtFull = (v: number | null | undefined) => (v === null || v === undefined ? "—" : full.format(Math.round(v)));
export const fmtPct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);
export const fmtRating = (v: number | null | undefined) => (v ? v.toFixed(1) : "—");

export function fmtAccel(v: number | null | undefined) {
  if (v === null || v === undefined) return "—";
  return `×${v >= 10 ? Math.round(v) : v.toFixed(1)}`;
}

export function fmtAge(days: number | null | undefined) {
  if (days === null || days === undefined) return "—";
  if (days < 1) return "сегодня";
  if (days < 60) return `${days} дн`;
  if (days < 730) return `${Math.round(days / 30)} мес`;
  return `${(days / 365).toFixed(1)} г`;
}

export function fmtDate(v: string | null | undefined) {
  if (!v) return "—";
  const d = new Date(v);
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric" });
}

export function fmtDateTime(v: string | null | undefined) {
  if (!v) return "—";
  const d = new Date(v.endsWith("Z") || v.includes("+") ? v : v + "Z");
  return d.toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export const storeUrl = (id: string) => `https://play.google.com/store/apps/details?id=${id}`;

export const COUNTRY_NAMES: Record<string, string> = {
  us: "США", ca: "Канада", mx: "Мексика", br: "Бразилия", ar: "Аргентина", co: "Колумбия", cl: "Чили", pe: "Перу",
  gb: "Великобритания", de: "Германия", fr: "Франция", it: "Италия", es: "Испания", nl: "Нидерланды", pl: "Польша",
  se: "Швеция", tr: "Турция", ru: "Россия", ua: "Украина", jp: "Япония", kr: "Корея", tw: "Тайвань", hk: "Гонконг",
  in: "Индия", id: "Индонезия", ph: "Филиппины", vn: "Вьетнам", th: "Таиланд", my: "Малайзия", sg: "Сингапур",
  pk: "Пакистан", sa: "Сауд. Аравия", ae: "ОАЭ", eg: "Египет", za: "ЮАР", ng: "Нигерия", au: "Австралия",
};

export const COLLECTION_LABELS: Record<string, string> = {
  top_new_free: "Top New Free",
  trending: "Movers & Shakers",
  top_free: "Top Free",
  top_grossing: "Top Grossing",
};

export const FLAG_SHORT: Record<string, string> = {
  major: "издатель",
  hc_publisher: "HC-паблишер",
  franchise: "бренд",
  big_dev: "студия 50M+",
  big_portfolio: "40+ игр",
};

export const MARK_LABELS: Record<string, string> = {
  interesting: "Интересно",
  in_work: "В работе",
  rejected: "Отброшено",
};

export const ERROR_TEXT: Record<string, string> = {
  invalid_credentials: "Неверный email или пароль",
  registration_closed: "Регистрация только по приглашению",
  invite_invalid: "Приглашение недействительно или истекло",
  invite_email_mismatch: "Приглашение выписано на другой email",
  email_taken: "Этот email уже зарегистрирован",
  "plan_limit:seats": "Достигнут лимит мест в тарифе",
  "plan_limit:saved_views": "Достигнут лимит сохранённых фильтров",
};
