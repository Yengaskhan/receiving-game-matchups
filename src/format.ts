/** Number formatting. Percentages from the exports are already in percent units (26.6 = 26.6%). */

const dash = '—';
const ok = (v: number | null | undefined): v is number => v != null && Number.isFinite(v);

export const n0 = (v: number | null | undefined) => (ok(v) ? Math.round(v).toLocaleString() : dash);
export const n1 = (v: number | null | undefined) => (ok(v) ? v.toFixed(1) : dash);
export const n2 = (v: number | null | undefined) => (ok(v) ? v.toFixed(2) : dash);
export const n3 = (v: number | null | undefined) => (ok(v) ? v.toFixed(3) : dash);
/** 26.6 -> "27%" (percent units in). */
export const pct = (v: number | null | undefined, digits = 0) => (ok(v) ? `${v.toFixed(digits)}%` : dash);
/** 0.62 -> "62%" (a fraction in). */
export const share = (v: number | null | undefined) => (ok(v) ? `${(v * 100).toFixed(0)}%` : dash);
/** An index vs league: 1.08 -> "1.08". */
export const idx = (v: number | null | undefined) => (ok(v) ? v.toFixed(2) : dash);
/** Signed difference: +4.9 / −2.1. */
export const signed = (v: number | null | undefined, digits = 1, unit = '') =>
  ok(v) ? `${v > 0 ? '+' : v < 0 ? '−' : '±'}${Math.abs(v).toFixed(digits)}${unit}` : dash;

export function ordinal(n: number): string {
  const s = n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th';
  return `${n}${s}`;
}

/** Rank 1 = allows the most. "3rd most" / "2nd fewest". */
export function rankPhrase(rank: number, n = 32): string {
  if (rank <= n / 2) return `${ordinal(rank)} most`;
  return `${ordinal(n - rank + 1)} fewest`;
}

/** "2026-10-14 22:08" (UTC) -> "Oct 14, 2026, 10:08 PM UTC". */
export function formatAsOf(s: string | null | undefined): string {
  if (!s) return dash;
  const d = new Date(`${s.replace(' ', 'T')}:00Z`);
  return `${d.toLocaleString('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })} UTC`;
}

/** "2026-10-18" -> "Sun, Oct 18" (the game's local calendar date, so no time zone shift). */
export function formatDate(iso: string | null, opts: Intl.DateTimeFormatOptions = { weekday: 'short', month: 'short', day: 'numeric' }): string {
  if (!iso) return dash;
  return new Date(`${iso}T12:00:00Z`).toLocaleDateString('en-US', { timeZone: 'UTC', ...opts });
}
