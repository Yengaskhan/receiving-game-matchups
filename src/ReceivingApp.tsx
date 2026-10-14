import { useEffect, useMemo, useState } from 'react';
import { latestIndex, loadCore, loadWeek, type Core } from './data';
import { DefenseView } from './DefenseView';
import { formatAsOf } from './format';
import { PlayerView } from './PlayerView';
import { SlateView } from './SlateView';
import type { WeekFile } from './types';

/** True when the page runs inside an iframe (e.g. embedded on a website-builder page). */
const embedded = (() => {
  try {
    return window.self !== window.top;
  } catch {
    return true;
  }
})();

export type Tab = 'player' | 'slate' | 'defense';
const TABS: [Tab, string][] = [
  ['player', 'Player vs Defense'],
  ['slate', 'Slate Rankings'],
  ['defense', 'Defense Profiles'],
];

/** The view lives in the URL hash so a link goes straight to it. */
export type HashState = Partial<Record<'tab' | 'player' | 'opp' | 'week' | 'team' | 'pos' | 'min' | 'filter', string>>;

function readHash(): HashState {
  return Object.fromEntries(new URLSearchParams(window.location.hash.slice(1))) as HashState;
}

export default function ReceivingApp() {
  const index = useMemo(latestIndex, []);
  const [hash, setHash] = useState<HashState>(readHash);
  const [core, setCore] = useState<Core | null>(null);
  const [error, setError] = useState<string | null>(null);
  const tab = (TABS.some(([t]) => t === hash.tab) ? hash.tab : 'player') as Tab;

  const update = (patch: HashState) => setHash((h) => ({ ...h, ...patch }));

  useEffect(() => {
    const p = new URLSearchParams(Object.entries(hash).filter(([, v]) => v != null && v !== '') as [string, string][]);
    history.replaceState(null, '', `#${p}`);
  }, [hash]);

  useEffect(() => {
    if (!index) return;
    loadCore(index.season).then(setCore).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [index]);

  // The current week's slate is needed by the player and defense tabs too (this week's opponent, best/worst).
  const [currentWeek, setCurrentWeek] = useState<WeekFile | null>(null);
  useEffect(() => {
    const w = index?.weeks.find((x) => x.week === index.current_week);
    if (w) loadWeek(w.path).then(setCurrentWeek).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [index]);

  return (
    <div className="flex min-h-full flex-col">
      <header className="border-b border-line bg-bg/95 px-4 py-2">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-sm bg-accent" aria-hidden />
          <span className="text-[13px] font-semibold tracking-tight">
            ClevAnalytics <span className="font-normal text-ink-2">Receiving Game Matchups</span>
          </span>
          {embedded && (
            <a href={window.location.href} target="_blank" rel="noopener" className="ml-auto text-[12px] text-accent hover:underline">
              Open full screen ↗
            </a>
          )}
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1320px] flex-1 px-4 py-5">
        {!index && <p className="text-ink-2">No data yet. Run the pipeline (see README) and commit data/.</p>}
        {error && <p className="rounded-md border border-bad/40 bg-panel px-3 py-2 text-bad">{error}</p>}
        {index && (
          <>
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-3">
                  {index.season} · Week {index.current_week}
                </p>
                <h1 className="text-[22px] font-semibold tracking-tight">Receiving Game Matchup Report</h1>
                <p className="text-[12px] text-ink-2">Each WR and TE against the opposing defense's coverage mix, and what that defense allows.</p>
              </div>
            </div>
            <nav className="mt-4 flex gap-1 overflow-x-auto border-b border-line" aria-label="Views">
              {TABS.map(([t, label]) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => update({ tab: t })}
                  aria-current={tab === t ? 'page' : undefined}
                  className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-[13px] ${tab === t ? 'border-accent font-semibold text-ink' : 'border-transparent text-ink-2 hover:text-ink'}`}
                >
                  {label}
                </button>
              ))}
            </nav>
            <div className="mt-4">
              {!core ? (
                !error && <p className="text-ink-3">Loading…</p>
              ) : tab === 'player' ? (
                <PlayerView core={core} season={index.season} week={currentWeek} hash={hash} update={update} />
              ) : tab === 'slate' ? (
                <SlateView index={index} hash={hash} update={update} />
              ) : (
                <DefenseView core={core} week={currentWeek} hash={hash} update={update} />
              )}
            </div>
          </>
        )}
      </main>

      <footer className="border-t border-line px-4 py-3 text-[11.5px] text-ink-3">
        <div className="mx-auto max-w-[1320px]">
          <p>
            Data as of <span className="text-ink-2">{formatAsOf(core?.meta.data_as_of ?? index?.data_as_of)}</span> · FantasyPoints Data Suite exports, season to date · PPR.
            Projections are matchup-adjusted (his routes per game × matchup-adjusted FP per route), not full projections.
          </p>
          {core && (
            <details className="mt-1.5">
              <summary className="cursor-pointer text-ink-2 hover:text-ink">How the Matchup Score works, and the checks this data passed</summary>
              <div className="mt-2 grid gap-3 md:grid-cols-2">
                <ul className="list-disc space-y-1 pl-5">
                  <li>Each split (man, zone, single-high, two-high, Cover 2/3/4/6) is shrunk toward the player's own overall rate, scaled by how that coverage plays league-wide, so a 15-route split moves him only a little.</li>
                  <li>Splits are compared as an index vs the league rate in that same coverage (1.00 = league average); raw rates are never compared across coverages.</li>
                  <li>Coverage fit = his expected FP per route given this defense's coverage mix, vs given the league's mix.</li>
                  <li>Defense side: FP allowed per dropback given its own coverage mix, and FP allowed to his alignments (TEs: FP allowed to TEs), shrunk toward average by games played.</li>
                  <li>Matchup Score = percentile of the matchup multiplier among this week's scheduled matchups for players with {core.meta.model.score_ref_min_routes}+ routes. 50 = neutral. It measures the matchup, not the player.</li>
                  <li>Splits under {core.meta.model.low_sample_routes} routes are flagged “low n”. SEP MS, ADOR, +1/+2/+3 Rate and Neg Rate aren't defined by the source, so they're shown for reference only.</li>
                </ul>
                <ul className="list-disc space-y-1 pl-5">
                  {core.meta.checks.map((c) => (
                    <li key={c}>✓ {c}</li>
                  ))}
                </ul>
              </div>
            </details>
          )}
        </div>
      </footer>
    </div>
  );
}
