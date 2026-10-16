import type { ReactNode } from 'react';
import { confLabel, Pill } from './ui';
import type { CoverageKey, Defense, Pair, Player } from './types';

/*
 * "How they cover vs how he produces", as three head-to-head cards that mirror how coverage fit works:
 * Man vs Zone, Single-high vs Two-high, and the zone family (Cover 2/3/4/6). Each card shows which way
 * this defense leans compared with the league, how he does on each side (index vs league), and a
 * one-line verdict with how confident we are his gap is real.
 */

type Tone = 'good' | 'bad' | 'neutral';
const TONE_BAR: Record<Tone, string> = { good: 'bg-edge-good', bad: 'bg-edge-bad', neutral: 'bg-ink-3/70' };
const TONE_TEXT: Record<Tone, string> = { good: 'text-edge-good', bad: 'text-edge-bad', neutral: 'text-ink-2' };

interface Side { key: CoverageKey; label: string; share: number; league: number; idx: number; routes: number }

/** Share of each side within the card's coverages, for this defense and the league (normalised to 100%). */
function sides(p: Player, d: Defense, keys: [CoverageKey, string][], metric: 'YPRR' | 'WIN_RATE'): Side[] {
  const cov = new Map(d.coverage.map((c) => [c.key, c]));
  const tot = keys.reduce((s, [k]) => s + (cov.get(k)?.pct ?? 0), 0) || 1;
  const ltot = keys.reduce((s, [k]) => s + (cov.get(k)?.league ?? 0), 0) || 1;
  return keys.map(([k, label]) => {
    const s = p.splits[k];
    return {
      key: k,
      label,
      share: (cov.get(k)?.pct ?? 0) / tot,
      league: (cov.get(k)?.league ?? 0) / ltot,
      idx: s.metrics[metric]?.index ?? 1,
      routes: metric === 'YPRR' ? s.routes : (s.sep_routes ?? s.routes),
    };
  });
}

const pctTxt = (v: number) => `${Math.round(v * 100)}%`;

/** A 100% bar of this defense's mix, with the league's mix underneath for comparison. */
function MixBars({ team, ss, lean }: { team: string; ss: Side[]; lean: CoverageKey | null }) {
  const row = (label: string, get: (s: Side) => number, strong: boolean) => (
    <div className="grid grid-cols-[3.25rem_minmax(0,1fr)] items-center gap-2">
      <span className={`text-[10.5px] font-semibold uppercase tracking-wider ${strong ? 'text-ink' : 'text-ink-3'}`}>{label}</span>
      <div className={`flex overflow-hidden rounded ${strong ? 'h-6' : 'h-3'}`}>
        {ss.map((s, i) => (
          <div
            key={s.key}
            title={`${label}: ${s.label} ${pctTxt(get(s))}`}
            style={{ width: `${get(s) * 100}%` }}
            className={`flex items-center justify-center overflow-hidden whitespace-nowrap text-[11px] font-semibold ${i > 0 ? 'border-l-2 border-panel' : ''} ${
              strong ? (s.key === lean ? 'bg-accent/80 text-bg' : 'bg-raise text-ink-2') : s.key === lean ? 'bg-accent/35' : 'bg-line-2'
            }`}
          >
            {strong && get(s) >= 0.14 ? `${s.label} ${pctTxt(get(s))}` : ''}
          </div>
        ))}
      </div>
    </div>
  );
  return (
    <div className="space-y-1">
      {row(team, (s) => s.share, true)}
      {row('League', (s) => s.league, false)}
    </div>
  );
}

/** His index on each side: bar from 0 to 2.0x with a line at league average (1.00). */
function IndexBars({ name, ss, tones, unit }: { name: string; ss: Side[]; tones: Record<string, Tone>; unit: string }) {
  return (
    <div className="space-y-1.5">
      <div className="grid grid-cols-[5.5rem_minmax(0,1fr)_3rem] gap-2 text-[10.5px] uppercase tracking-wider text-ink-3">
        <span className="truncate">{name}</span>
        <span className="relative">
          {unit}
          <span className="absolute left-1/2 -translate-x-1/2 normal-case tracking-normal">league</span>
        </span>
        <span />
      </div>
      {ss.map((s) => (
        <div key={s.key} className="grid grid-cols-[5.5rem_minmax(0,1fr)_3rem] items-center gap-2">
          <span className="truncate text-[12px]">
            {s.label} <span className="text-[10.5px] text-ink-3">{s.routes}</span>
          </span>
          <span className="relative block h-4 rounded bg-panel-2" role="img" aria-label={`${s.label}: ${s.idx.toFixed(2)}x league`} title={`${s.label}: ${s.idx.toFixed(2)}x league ${unit} on ${s.routes} routes`}>
            <span className={`absolute inset-y-0 left-0 rounded ${TONE_BAR[tones[s.key] ?? 'neutral']}`} style={{ width: `${Math.min(s.idx / 2, 1) * 100}%` }} />
            <span aria-hidden className="absolute -inset-y-0.5 left-1/2 w-px bg-ink-2" />
          </span>
          <span className={`num text-right text-[13px] font-semibold ${TONE_TEXT[tones[s.key] ?? 'neutral']}`}>{s.idx.toFixed(2)}x</span>
        </div>
      ))}
    </div>
  );
}

function Verdict({ tone, delta }: { tone: Tone; delta: string }) {
  const label = tone === 'good' ? 'Edge' : tone === 'bad' ? 'Concern' : 'Neutral';
  return (
    <span className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-[12px] font-semibold ${tone === 'good' ? 'border-edge-good/50 bg-edge-good/10 text-edge-good' : tone === 'bad' ? 'border-edge-bad/50 bg-edge-bad/10 text-edge-bad' : 'border-line-2 text-ink-2'}`}>
      {label} <span className="num font-normal opacity-90">{delta}</span>
    </span>
  );
}

function Card({ title, verdict, children, footer }: { title: string; verdict: ReactNode; children: ReactNode; footer: ReactNode }) {
  return (
    <section className="flex flex-col rounded-md border border-line bg-panel">
      <header className="flex items-center justify-between gap-2 border-b border-line px-3 py-2">
        <h3 className="text-[13px] font-semibold">{title}</h3>
        {verdict}
      </header>
      <div className="flex-1 space-y-3 p-3">{children}</div>
      <footer className="border-t border-line px-3 py-2 text-[12px] leading-snug text-ink-2">{footer}</footer>
    </section>
  );
}

function AxisCard({ p, d, pair, axis, title, keys }: { p: Player; d: Defense; pair: Pair | null; axis: string; title: string; keys: [CoverageKey, string][] }) {
  const ss = sides(p, d, keys, 'YPRR');
  const [a, b] = ss;
  const leanSide = a.share - a.league >= b.share - b.league ? a : b;
  const other = leanSide === a ? b : a;
  const leanPts = (leanSide.share - leanSide.league) * 100;
  const flat = Math.abs(leanPts) < 2;
  const fit = pair?.axes[axis]?.fit ?? 1;
  const delta = (fit - 1) * 100;
  const tone: Tone = !pair || Math.abs(delta) < 1 ? 'neutral' : delta > 0 ? 'good' : 'bad';
  const better = leanSide.idx >= other.idx;
  const e = p.edges[leanSide.key];
  const cl = e ? confLabel(e.conf) : null;
  const tones: Record<string, Tone> = { [leanSide.key]: flat ? 'neutral' : better ? 'good' : 'bad' };
  const lastName = p.name.split(' ').slice(-1)[0];
  return (
    <Card
      title={title}
      verdict={<Verdict tone={tone} delta={`${delta >= 0 ? '+' : '−'}${Math.abs(delta).toFixed(0)}% yds/rte`} />}
      footer={
        flat ? (
          <>{d.team} splits these like an average defense, so this barely moves his matchup.</>
        ) : (
          <>
            {d.team} leans <b className="text-ink">{leanSide.label.toLowerCase()}</b> ({pctTxt(leanSide.share)} vs league {pctTxt(leanSide.league)}). That's his{' '}
            <b className={better ? 'text-edge-good' : 'text-edge-bad'}>{better ? 'better' : 'weaker'}</b> side: {leanSide.idx.toFixed(2)}x vs {other.idx.toFixed(2)}x league yards/route.
            {e && cl && (
              <span className="mt-1 flex items-center gap-1.5 text-[11.5px] text-ink-3">
                <Pill tone={cl.tone}>{cl.label}</Pill> {Math.round(e.conf * 100)}% sure the gap is real
              </span>
            )}
          </>
        )
      }
    >
      <MixBars team={d.team} ss={ss} lean={flat ? null : leanSide.key} />
      <IndexBars name={lastName} ss={ss} tones={tones} unit="yds/route" />
    </Card>
  );
}

function ZoneCard({ p, d, pair }: { p: Player; d: Defense; pair: Pair | null }) {
  const ss = sides(p, d, [['C2', 'Cover 2'], ['C3', 'Cover 3'], ['C4', 'Cover 4'], ['C6', 'Cover 6']], 'WIN_RATE');
  // His own zone average: his win-rate indexes weighted by the league's zone mix.
  const base = ss.reduce((s, x) => s + x.league * x.idx, 0);
  const tones: Record<string, Tone> = {};
  for (const s of ss) {
    if (s.share - s.league > 0.02) tones[s.key] = s.idx >= base ? 'good' : 'bad';
  }
  const lean = [...ss].sort((x, y) => y.share - y.league - (x.share - x.league))[0];
  const zf = pair?.zone_fit ?? 1;
  const delta = (zf - 1) * 100;
  const tone: Tone = !pair || Math.abs(delta) < 2 ? 'neutral' : delta > 0 ? 'good' : 'bad';
  const e = p.edges[lean.key];
  const cl = e ? confLabel(e.conf) : null;
  return (
    <Card
      title="Zone looks: Cover 2 / 3 / 4 / 6"
      verdict={<Verdict tone={tone} delta={`${delta >= 0 ? '+' : '−'}${Math.abs(delta).toFixed(0)}% win rate`} />}
      footer={
        <>
          Within its zone, {d.team} plays the most extra <b className="text-ink">{lean.label}</b> ({pctTxt(lean.share)} vs league {pctTxt(lean.league)}). His {lean.label} win rate:{' '}
          <b className={lean.idx >= base ? 'text-edge-good' : 'text-edge-bad'}>{lean.idx.toFixed(2)}x</b> league (his zone average {base.toFixed(2)}x).
          {e && cl && (
            <span className="mt-1 flex items-center gap-1.5 text-[11.5px] text-ink-3">
              <Pill tone={cl.tone}>{cl.label}</Pill> {Math.round(e.conf * 100)}% sure the gap is real · small weight in the score
            </span>
          )}
        </>
      }
    >
      <MixBars team={d.team} ss={ss} lean={lean.share - lean.league > 0.02 ? lean.key : null} />
      <IndexBars name={p.name.split(' ').slice(-1)[0]} ss={ss} tones={tones} unit="win rate" />
    </Card>
  );
}

export function CoverageMatchup({ p, d, pair }: { p: Player; d: Defense; pair: Pair | null }) {
  return (
    <section>
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-ink-2">
          How {d.team} covers vs how {p.name} produces
        </h2>
        <span className="text-[11px] text-ink-3">
          Top bar: {d.team}'s mix (highlighted = the side it plays more than the league). Bars: his rate vs league (line = league average). Small number = routes.
        </span>
      </div>
      <div className="grid gap-3 lg:grid-cols-3">
        <AxisCard p={p} d={d} pair={pair} axis="man_zone" title="Man vs Zone" keys={[['MAN', 'Man'], ['ZONE', 'Zone']]} />
        <AxisCard p={p} d={d} pair={pair} axis="shell" title="Single-high vs Two-high" keys={[['SINGLE_HIGH', 'Single-high'], ['TWO_HIGH', 'Two-high']]} />
        <ZoneCard p={p} d={d} pair={pair} />
      </div>
    </section>
  );
}
