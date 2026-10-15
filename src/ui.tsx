import type { ReactNode } from 'react';

/** Matchup Score bands, the same cut-offs and colours as the Run Edge on the RB report. */
export const BANDS = [
  { key: 'big_edge', label: 'Great matchup', min: 70 },
  { key: 'small_edge', label: 'Good matchup', min: 58 },
  { key: 'neutral', label: 'Neutral', min: 43 },
  { key: 'small_disadvantage', label: 'Tough matchup', min: 31 },
  { key: 'big_disadvantage', label: 'Very tough matchup', min: 0 },
] as const;
type BandKey = (typeof BANDS)[number]['key'];

const BAND_STYLE: Record<BandKey, string> = {
  big_edge: 'bg-edge-good/30 text-edge-good border-edge-good/60',
  small_edge: 'bg-edge-good/10 text-edge-good border-edge-good/30',
  neutral: 'bg-raise text-ink-2 border-line-2',
  small_disadvantage: 'bg-edge-bad/10 text-edge-bad border-edge-bad/30',
  big_disadvantage: 'bg-edge-bad/30 text-edge-bad border-edge-bad/60',
};

export function band(score: number | null | undefined) {
  if (score == null) return BANDS[2];
  return BANDS.find((b) => score >= b.min) ?? BANDS[4];
}

export function ScoreBadge({ score, small, lg }: { score: number | null | undefined; small?: boolean; lg?: boolean }) {
  if (score == null) return <span className="text-ink-3">—</span>;
  const b = band(score);
  return (
    <span
      title={`${b.label}${small ? ' · small sample (under 50 routes)' : ''}`}
      className={`num inline-flex items-center justify-center rounded border font-semibold ${BAND_STYLE[b.key]} ${small ? 'border-dashed' : ''} ${lg ? 'h-10 min-w-[3.5rem] px-2 text-[22px]' : 'h-6 min-w-[2.5rem] px-1.5 text-[12.5px]'}`}
    >
      {score}
    </span>
  );
}

export function Select({ label, value, onChange, options, className = '' }: { label: string; value: string; onChange: (v: string) => void; options: [string, string][]; className?: string }) {
  return (
    <label className={`flex flex-col gap-1 text-[10.5px] font-medium uppercase tracking-wider text-ink-3 ${className}`}>
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)} className="h-8 rounded border border-line-2 px-1.5 text-[13px] normal-case tracking-normal text-ink">
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </label>
  );
}

export function Panel({ title, note, children, className = '' }: { title: ReactNode; note?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-md border border-line bg-panel ${className}`}>
      <header className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 border-b border-line px-3 py-2">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-ink-2">{title}</h2>
        {note && <span className="text-[11px] text-ink-3">{note}</span>}
      </header>
      <div className="p-3">{children}</div>
    </section>
  );
}

export function Card({ label, children, sub }: { label: string; children: ReactNode; sub?: ReactNode }) {
  return (
    <div className="rounded-md border border-line bg-panel px-3 py-2.5">
      <p className="text-[10.5px] font-medium uppercase tracking-wider text-ink-3">{label}</p>
      <div className="mt-1">{children}</div>
      {sub && <p className="mt-1 text-[11.5px] leading-snug text-ink-2">{sub}</p>}
    </div>
  );
}

export function LowSample({ routes }: { routes: number }) {
  return (
    <span title={`Low sample: ${routes} routes (under 20)`} className="ml-1 rounded border border-warn/40 px-1 text-[9.5px] font-semibold uppercase tracking-wide text-warn">
      low n
    </span>
  );
}

export type SortState<K extends string> = { key: K; desc: boolean };

export function SortTh<K extends string>({ k, sort, setSort, children, className = '', textKeys = [] }: {
  k?: K; sort: SortState<K>; setSort: (f: (s: SortState<K>) => SortState<K>) => void; children: ReactNode; className?: string; textKeys?: K[];
}) {
  return (
    <th scope="col" className={`whitespace-nowrap px-3 py-2 text-[10.5px] font-medium uppercase tracking-wider text-ink-3 ${className}`} aria-sort={k && sort.key === k ? (sort.desc ? 'descending' : 'ascending') : undefined}>
      {k ? (
        <button type="button" onClick={() => setSort((s) => ({ key: k, desc: s.key === k ? !s.desc : !textKeys.includes(k) }))} className="inline-flex items-center gap-1 rounded border border-line-2 bg-panel-2 px-1.5 py-0.5 uppercase hover:border-ink-3 hover:text-ink">
          {children}
          <span aria-hidden className={sort.key === k ? 'text-accent' : 'text-ink-3/60'}>{sort.key === k ? (sort.desc ? '▼' : '▲') : '↕'}</span>
        </button>
      ) : (
        children
      )}
    </th>
  );
}

/** A horizontal bar from a centre line: positive right, negative left. Value text is always shown beside it. */
export function DivBar({ value, max, tone = 'neutral', label }: { value: number; max: number; tone?: 'good' | 'bad' | 'neutral'; label: string }) {
  const w = Math.min(Math.abs(value) / max, 1) * 50;
  const color = tone === 'good' ? 'bg-edge-good' : tone === 'bad' ? 'bg-edge-bad' : 'bg-ink-3';
  return (
    <span className="relative block h-3.5 w-full" role="img" aria-label={label} title={label}>
      <span aria-hidden className="absolute inset-y-0 left-1/2 w-px bg-line-2" />
      <span
        aria-hidden
        className={`absolute top-0.5 bottom-0.5 ${color} ${value >= 0 ? 'rounded-r-[4px]' : 'rounded-l-[4px]'}`}
        style={value >= 0 ? { left: '50%', width: `${w}%` } : { right: '50%', width: `${w}%` }}
      />
    </span>
  );
}

export function Pill({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'good' | 'bad' | 'neutral' | 'warn' }) {
  const cls = {
    good: 'border-edge-good/40 text-edge-good',
    bad: 'border-edge-bad/40 text-edge-bad',
    warn: 'border-warn/40 text-warn',
    neutral: 'border-line-2 text-ink-2',
  }[tone];
  return <span className={`inline-flex items-center rounded border px-1.5 py-px text-[10.5px] font-semibold uppercase tracking-wide ${cls}`}>{children}</span>;
}

/** Confidence that a coverage split is real, in words. */
export function confLabel(conf: number): { label: string; tone: 'good' | 'warn' | 'neutral' } {
  if (conf >= 0.9) return { label: 'Real', tone: 'good' };
  if (conf >= 0.75) return { label: 'Leaning', tone: 'warn' };
  return { label: 'Could be noise', tone: 'neutral' };
}

export function EdgeChip({ e }: { e: { label: string; edge: boolean; conf: number; rank: number; text: string } }) {
  return (
    <span title={e.text} className={`inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-px text-[11px] font-semibold ${e.edge ? 'border-edge-good/50 text-edge-good' : 'border-edge-bad/50 text-edge-bad'}`}>
      {e.edge ? '▲' : '▼'} {e.label} · #{e.rank} · {Math.round(e.conf * 100)}%
    </span>
  );
}
