import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { loadWeek } from './data';
import { formatDate, n0, n1, n2, n3 } from './format';
import type { HashState } from './ReceivingApp';
import { TeamLogo, teamName } from './TeamLogo';
import type { SeasonIndex, SlateRow, WeekFile } from './types';
import { BANDS, EdgeChip, ScoreBadge, Select, SortTh, type SortState } from './ui';

type SortKey = 'name' | 'opponent' | 'score' | 'proj' | 'fit' | 'routes_pg';

export function SlateView({ index, basis, hash, update }: { index: SeasonIndex; basis: string; hash: HashState; update: (p: HashState) => void }) {
  const weekNo = Number(hash.week) || index.current_week;
  const avail = index.weeks.filter((w) => w.bases.includes(basis));
  const entry = avail.find((w) => w.week === weekNo) ?? avail[avail.length - 1] ?? index.weeks[index.weeks.length - 1];
  const [week, setWeek] = useState<WeekFile | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    loadWeek(index.season, basis, entry.file)
      .then((w) => live && (setWeek(w), setError(null)))
      .catch((e) => live && setError(String(e)));
    return () => {
      live = false;
    };
  }, [index.season, basis, entry.file]);

  const pos = hash.pos ?? 'all';
  const role = hash.role ?? 'all';
  const team = hash.team ?? 'all';
  const minRoutes = hash.min != null ? Number(hash.min) : 50;
  const query = hash.filter ?? '';
  const edgesOnly = hash.edges === '1';
  const [sort, setSort] = useState<SortState<SortKey>>({ key: 'score', desc: true });

  const teams = useMemo(() => [...new Set(week?.rows.map((r) => r.team) ?? [])].sort(), [week]);
  const rows = useMemo(() => {
    if (!week) return [];
    const q = query.trim().toLowerCase();
    const list = week.rows.filter(
      (r) => (pos === 'all' || r.pos === pos) && roleMatch(r.role, role) && (team === 'all' || r.team === team || r.opponent === team) && r.routes >= minRoutes && (!q || r.name.toLowerCase().includes(q)) && (!edgesOnly || r.coverage_edges.length > 0),
    );
    const val = (r: SlateRow): number | string => (sort.key === 'name' ? r.name : sort.key === 'opponent' ? r.opponent : r[sort.key]);
    return list.sort((a, b) => {
      const va = val(a);
      const vb = val(b);
      const c = typeof va === 'string' ? va.localeCompare(vb as string) : va - (vb as number);
      return sort.desc ? -c : c;
    });
  }, [week, pos, role, team, minRoutes, query, edgesOnly, sort]);

  const download = () => {
    if (!week) return;
    const head = ['Player', 'Pos', 'Role', 'Team', 'Opponent', 'Home', 'Matchup Score', 'Matchup-adjusted projection (PPR)', 'Matchup FP/RR', 'Adj FP/RR', 'Coverage fit', 'Coverage allowed index', 'Alignment allowed index', 'Routes', 'Routes per game', 'Coverage edges', 'Top reason'];
    const esc = (v: string | number) => (typeof v === 'number' || /^-?\d+(\.\d+)?$/.test(v) ? String(v) : `"${v.replace(/"/g, '""')}"`);
    const lines = rows.map((r) =>
      [r.name, r.pos, r.role ?? '', r.team, r.opponent, r.home ? 'Y' : 'N', r.score, r.proj.toFixed(2), r.fp_rr.toFixed(3), r.adj_fp_rr.toFixed(3), r.fit.toFixed(3), r.cov_index.toFixed(3), r.align_index.toFixed(3), r.routes, r.routes_pg.toFixed(1), r.coverage_edges.map((e) => `${e.edge ? 'EDGE' : 'CONCERN'} ${e.text}`).join(' | '), r.reasons[0]?.text ?? '']
        .map(esc)
        .join(','),
    );
    const blob = new Blob([[head.map(esc).join(','), ...lines].join('\n') + '\n'], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `receiving-matchups-${week.season}-week-${String(week.week).padStart(2, '0')}${basis === index.default_basis ? '' : `-data-${basis}`}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };

  const Th = (props: { k?: SortKey; className?: string; children: ReactNode }) => <SortTh sort={sort} setSort={setSort} textKeys={['name', 'opponent']} {...props} />;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <Select label="Week" value={String(entry.week)} onChange={(v) => update({ week: v })} options={avail.map((w) => [String(w.week), `Week ${w.week}${w.week === index.current_week ? ' (current)' : ''}`])} />
        <Select label="Position" value={pos} onChange={(v) => update({ pos: v })} options={[['all', 'WR + TE'], ['WR', 'WR'], ['TE', 'TE']]} />
        <Select label="Role" value={role} onChange={(v) => update({ role: v === 'all' ? undefined : v })} options={ROLE_OPTIONS} />
        <Select label="Team" value={team} onChange={(v) => update({ team: v })} options={[['all', 'All teams'], ...teams.map((t) => [t, t] as [string, string])]} />
        <label className="flex flex-col gap-1 text-[10.5px] font-medium uppercase tracking-wider text-ink-3">
          Min routes
          <input type="number" min={0} step={10} value={minRoutes} onChange={(e) => update({ min: e.target.value })} className="h-8 w-20 rounded border border-line-2 bg-panel-2 px-2 text-[13px] text-ink" />
        </label>
        <label className="flex flex-col gap-1 text-[10.5px] font-medium uppercase tracking-wider text-ink-3">
          Find player
          <input value={query} onChange={(e) => update({ filter: e.target.value })} placeholder="Name" className="h-8 w-36 rounded border border-line-2 bg-panel-2 px-2 text-[13px] normal-case tracking-normal text-ink placeholder:text-ink-3" />
        </label>
        <label className="flex h-8 cursor-pointer items-center gap-2 rounded border border-line-2 bg-panel-2 px-2.5 text-[12.5px] text-ink-2 hover:border-ink-3" title="Players with a real (90%+ confident) edge or weakness in a coverage this week's opponent plays at a top-5 rate">
          <input type="checkbox" checked={edgesOnly} onChange={(e) => update({ edges: e.target.checked ? '1' : undefined })} className="accent-[var(--color-accent)]" />
          Coverage edges only
        </label>
        <button type="button" onClick={download} className="ml-auto h-8 rounded border border-line-2 bg-panel-2 px-3 text-[12.5px] text-ink-2 hover:border-ink-3 hover:text-ink">
          Download CSV ↓
        </button>
      </div>

      {error && <p className="text-bad">{error}</p>}
      {week && (
        <>
          <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-ink-3">
            {BANDS.map((b) => (
              <span key={b.key} className="inline-flex items-center gap-1">
                <ScoreBadge score={b.min === 0 ? 20 : b.min + 5} /> {b.label}
              </span>
            ))}
            <span className="ml-2">
              {week.games.length} games · {formatDate(week.games[0]?.gameday)} – {formatDate(week.games[week.games.length - 1]?.gameday)}
              {week.byes.length > 0 && ` · bye: ${week.byes.join(', ')}`} · {rows.length} players shown · click a row for the full matchup · Matchup = this week vs his normal week (50 = typical), ranked within position · coverage edge: ▲ real edge / ▼ real weakness in a coverage the opponent plays at a top-5 rate (#rank · confidence)
            </span>
          </div>
          <div className="overflow-x-auto rounded-md border border-line bg-panel">
            <table className="num w-full min-w-[880px] border-collapse text-[12.5px]">
              <thead className="border-b border-line bg-panel-2/60">
                <tr className="text-left">
                  <Th k="name" className="sticky left-0 z-10 bg-panel-2">Player</Th>
                  <Th k="opponent" className="hidden sm:table-cell">Opponent</Th>
                  <Th k="score" className="hidden text-center sm:table-cell">Matchup</Th>
                  <Th className="min-w-[11rem]">Coverage edge</Th>
                  <Th k="proj" className="text-right">Proj. (PPR)</Th>
                  <Th k="fit" className="text-right">Cov. fit</Th>
                  <Th className="min-w-[15rem]">Top reason</Th>
                  <Th k="routes_pg" className="text-right">Routes / G</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={r.player}
                    onClick={() => update({ tab: 'player', player: r.player, opp: r.opponent })}
                    onKeyDown={(e) => e.key === 'Enter' && e.target === e.currentTarget && update({ tab: 'player', player: r.player, opp: r.opponent })}
                    tabIndex={0}
                    title={`Open ${r.name} vs ${r.opponent}`}
                    className="group cursor-pointer border-t border-line/60 hover:bg-panel-2/70 focus-visible:bg-panel-2/70"
                  >
                    <td className="sticky left-0 z-10 bg-panel px-3 py-2 group-hover:bg-panel-2">
                      <span className="flex items-center justify-between gap-3">
                        <button type="button" onClick={() => update({ tab: 'player', player: r.player, opp: r.opponent })} className="flex items-center gap-2 text-left hover:text-accent" title="Open in Player vs Defense">
                          <TeamLogo team={r.team} size={22} />
                          <span>
                            <span className="block whitespace-nowrap font-semibold">{r.name}</span>
                            <span className="block text-[11px] text-ink-3">
                              {r.role ?? r.pos} · {r.team}
                              <span className="sm:hidden">
                                {' '}
                                {r.home ? 'vs' : '@'} {r.opponent}
                              </span>
                            </span>
                          </span>
                        </button>
                        <span className="sm:hidden">
                          <ScoreBadge score={r.score} small={r.routes < 50} />
                        </span>
                      </span>
                    </td>
                    <td className="hidden px-3 py-2 text-ink-2 sm:table-cell">
                      <span className="inline-flex items-center gap-1.5" title={teamName(r.opponent)}>
                        {r.home ? 'vs' : '@'} <TeamLogo team={r.opponent} size={18} /> <span className="font-semibold text-ink">{r.opponent}</span>
                      </span>
                    </td>
                    <td className="hidden px-3 py-2 text-center sm:table-cell">
                      <ScoreBadge score={r.score} small={r.routes < 50} />
                    </td>
                    <td className="px-3 py-2">
                      {r.coverage_edges.length ? (
                        <span className="flex flex-col items-start gap-1">
                          {r.coverage_edges.map((e) => (
                            <EdgeChip key={e.cov} e={e} />
                          ))}
                        </span>
                      ) : (
                        <span className="text-ink-3">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right" title={`${n1(r.routes_pg)} routes × ${n3(r.fp_rr)} FP/RR`}>
                      {n1(r.proj)}
                    </td>
                    <td className={`px-3 py-2 text-right ${r.fit > 1.01 ? 'text-edge-good' : r.fit < 0.99 ? 'text-edge-bad' : ''}`}>{n2(r.fit)}</td>
                    <td className="px-3 py-2 text-[12px] text-ink-2">{r.reasons[0]?.text ?? '—'}</td>
                    <td className="px-3 py-2 text-right">
                      {n1(r.routes_pg)}
                      <span className="block text-[10.5px] text-ink-3">{n0(r.routes)} total</span>
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-3 py-6 text-center text-ink-3">
                      No players match these filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

/** Role filter: within-team rank by targets per game this season. */
const ROLE_OPTIONS: [string, string][] = [
  ['all', 'All roles'],
  ['WR1', 'WR1'],
  ['WR2', 'WR2'],
  ['WR3', 'WR3'],
  ['WR1-2', 'WR1 + WR2'],
  ['WR1-3', 'WR1 – WR3'],
  ['WR4+', 'WR4 and below'],
  ['TE1', 'TE1'],
  ['TE2+', 'TE2 and below'],
];

function roleMatch(role: string | null | undefined, filter: string): boolean {
  if (filter === 'all') return true;
  if (!role) return false;
  const pos = role.slice(0, 2);
  const n = Number(role.slice(2));
  const m = filter.match(/^(WR|TE)(\d)(?:-(\d)|(\+))?$/);
  if (!m || m[1] !== pos) return false;
  const lo = Number(m[2]);
  if (m[4]) return n >= lo;
  return n >= lo && n <= Number(m[3] ?? m[2]);
}
