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
  ['slate', 'Slate Rankings'],
  ['player', 'Player vs Defense'],
  ['defense', 'Defense Profiles'],
];

/** The view lives in the URL hash so a link goes straight to it. */
export type HashState = Partial<Record<'tab' | 'player' | 'opp' | 'week' | 'team' | 'pos' | 'min' | 'filter' | 'edges' | 'basis', string>>;

function readHash(): HashState {
  return Object.fromEntries(new URLSearchParams(window.location.hash.slice(1))) as HashState;
}

export default function ReceivingApp() {
  const index = useMemo(latestIndex, []);
  const [hash, setHash] = useState<HashState>(readHash);
  const [core, setCore] = useState<Core | null>(null);
  const [error, setError] = useState<string | null>(null);
  const tab = (TABS.some(([t]) => t === hash.tab) ? hash.tab : 'slate') as Tab;
  // Which data the numbers come from: the current season (default), a prior season, or all combined.
  const basis = index?.bases.some((b) => b.key === hash.basis) ? hash.basis! : (index?.default_basis ?? '');
  const basisMeta = index?.bases.find((b) => b.key === basis);

  const update = (patch: HashState) => {
    setHash((h) => ({ ...h, ...patch }));
    // Switching views (e.g. clicking a row far down the slate) starts the new view at the top.
    if (patch.tab) window.scrollTo({ top: 0 });
  };

  useEffect(() => {
    const p = new URLSearchParams(Object.entries(hash).filter(([, v]) => v != null && v !== '') as [string, string][]);
    history.replaceState(null, '', `#${p}`);
  }, [hash]);

  useEffect(() => {
    if (!index || !basis) return;
    let live = true;
    setCore(null);
    loadCore(index.season, basis)
      .then((c) => live && (setCore(c), setError(null)))
      .catch((e) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [index, basis]);

  // The current week's slate is needed by the player and defense tabs too (this week's opponent, best/worst).
  const [currentWeek, setCurrentWeek] = useState<WeekFile | null>(null);
  useEffect(() => {
    const w = index?.weeks.find((x) => x.week === index.current_week);
    setCurrentWeek(null);
    if (w && index && w.bases.includes(basis)) loadWeek(index.season, basis, w.file).then(setCurrentWeek).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [index, basis]);

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

      <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-5">
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
              {index.bases.length > 1 && (
                <div className="flex flex-col gap-1">
                  <span className="text-[10.5px] font-medium uppercase tracking-wider text-ink-3">Data</span>
                  <div role="radiogroup" aria-label="Which seasons' data" className="inline-flex rounded border border-line-2 bg-panel-2 p-0.5">
                    {index.bases.map((b) => (
                      <button
                        key={b.key}
                        type="button"
                        role="radio"
                        aria-checked={basis === b.key}
                        title={b.note}
                        onClick={() => update({ basis: b.key === index.default_basis ? undefined : b.key })}
                        className={`h-7 rounded px-3 text-[12.5px] ${basis === b.key ? 'bg-accent/15 font-semibold text-accent' : 'text-ink-2 hover:text-ink'}`}
                      >
                        {b.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
            {basisMeta && basis !== index.default_basis && (
              <p className="mt-3 rounded-md border border-line-2 bg-panel-2 px-3 py-2 text-[12px] text-ink-2">
                <span className="font-semibold text-ink">Showing {basisMeta.note}.</span> This week's {index.season} matchups, scored with that data. Players are on their {index.season} teams;
                projections use their {index.season} routes per game. Players with no data in it aren't listed.
              </p>
            )}
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
                <PlayerView core={core} season={index.season} basis={basis} week={currentWeek} hash={hash} update={update} />
              ) : tab === 'slate' ? (
                <SlateView index={index} basis={basis} hash={hash} update={update} />
              ) : (
                <DefenseView core={core} week={currentWeek} hash={hash} update={update} />
              )}
            </div>
          </>
        )}
      </main>

      <footer className="border-t border-line px-4 py-3 text-[11.5px] text-ink-3">
        <div className="mx-auto max-w-[1600px]">
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
                  <li>Coverage fit = his expected yards per route given this defense's coverage mix, vs given the league's mix. Yards per route (not FP) because it counts the routes where the QB doesn't look his way and doesn't swing on touchdowns.</li>
                  <li>Coverage edge (“Is it real?”): how confident we can be that a player's gap between two coverages isn't luck, given how many routes it's based on. 90%+ = real. The slate flags real edges or weaknesses in a coverage this week's opponent plays at a top-5 rate.</li>
                  <li>Defense side: FP allowed where he lines up (outside or slot WRs; TEs for TEs), and FP per dropback allowed to WRs and TEs combined given its coverage mix, each shrunk toward average by games played.</li>
                  <li>Matchup Score blends three parts, each standardized: coverage fit 45%, FP allowed where he lines up 35%, FP per dropback allowed 20%. No part counts for more than 2 SDs. It's ranked within position (WRs vs WRs, TEs vs TEs) among this week's matchups for players with {core.meta.model.score_ref_min_routes}+ routes. 50 = neutral. It measures the matchup, not the player.</li>
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
