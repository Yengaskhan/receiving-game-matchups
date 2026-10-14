import { useMemo } from 'react';
import type { Core } from './data';
import { DefenseContext } from './PlayerView';
import { n1, n2, pct, rankPhrase, signed } from './format';
import type { HashState } from './ReceivingApp';
import { TeamLogo } from './TeamLogo';
import type { SlateRow, WeekFile } from './types';
import { DivBar, Panel, ScoreBadge, Select } from './ui';

export function DefenseView({ core, week, hash, update }: { core: Core; week: WeekFile | null; hash: HashState; update: (p: HashState) => void }) {
  const defs = core.defenses;
  const d = defs.find((x) => x.team === hash.team) ?? defs[0];
  const minRoutes = 50;

  const vs = useMemo(() => (week?.rows ?? []).filter((r) => r.opponent === d.team && r.routes >= minRoutes).sort((a, b) => b.score - a.score), [week, d.team]);
  // One offense faces this defense, so split its players: the top half (up to 6) and the bottom half.
  const half = Math.min(6, Math.ceil(vs.length / 2));
  const best = vs.slice(0, half);
  const worst = vs.slice(half).reverse().slice(0, 6);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <Select label="Defense" value={d.team} onChange={(v) => update({ team: v })} options={defs.map((x) => [x.team, `${x.team} · ${x.name}`])} />
        <p className="pb-1.5 text-[12px] text-ink-3">
          {Math.round(d.g)} games · {Math.round(d.db)} dropbacks faced
          {week && (d.opponent ? ` · Week ${week.week}: ${d.home ? 'vs' : '@'} ${d.opponent}` : ` · on bye in week ${week.week}`)}
        </p>
      </div>

      <div className="flex items-center gap-3">
        <TeamLogo team={d.team} size={36} />
        <div>
          <h2 className="text-[18px] font-semibold">{d.name} pass defense</h2>
          <p className="text-[12px] text-ink-2">
            Coverage-weighted FP allowed to WR/TE: <span className="num font-semibold text-ink">{n2(d.index.cov_raw)}×</span> league ({rankPhrase(d.index.cov_rank)}); after shrinking by games, {n2(d.index.cov)}×.
          </p>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Coverage mix vs league" note="% of dropbacks">
          <div className="grid grid-cols-[6.5rem_minmax(0,1fr)_6.5rem] items-center gap-x-3 gap-y-1.5 text-[12px]">
            {d.coverage.map((c, i) => (
              <div key={c.key} className={`contents ${i === 4 ? '[&>*]:mt-2' : ''}`}>
                <span className="font-medium">{c.label}</span>
                <DivBar value={c.pct - c.league} max={20} label={`${c.label}: ${pct(c.pct, 1)} vs league ${pct(c.league, 1)}`} />
                <span className="num text-right text-[11.5px]">
                  {pct(c.pct, 1)} <span className="text-ink-3">{signed(c.pct - c.league)}</span>
                </span>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[11px] text-ink-3">Bars show points above (right) or below (left) the league rate. Man + Zone is about 96%; the rest are unusual plays.</p>
        </Panel>

        <div className="space-y-4">
          <Panel title="FP allowed to WR/TE by coverage" note="PPR points per dropback">
            <AllowedTable rows={d.fp_db.map((f) => ({ label: `vs ${f.label}`, value: n2(f.value), league: n2(f.league), rank: f.rank, ratio: f.value / f.league }))} />
          </Panel>
          <Panel title="FP allowed by alignment" note="PPR points per game">
            <AllowedTable rows={d.alignment.map((a) => ({ label: a.label, value: n1(a.fpg), league: n1(a.league), rank: a.rank, ratio: a.fpg / a.league }))} />
          </Panel>
        </div>
      </div>

      <DefenseContext d={d} />

      <div className="grid gap-4 md:grid-cols-2">
        <MatchupList title={`Best WR/TE matchups vs ${d.team} this week`} rows={best} update={update} empty={d.opponent ? 'No opposing players with 50+ routes.' : `${d.team} is on bye this week.`} />
        <MatchupList title={`Toughest WR/TE matchups vs ${d.team} this week`} rows={worst} update={update} empty={d.opponent ? 'No opposing players with 50+ routes.' : `${d.team} is on bye this week.`} />
      </div>
      <p className="text-[11px] text-ink-3">PASS %, PROE and PACE in the team-defense export are left out: it's unclear whether they describe this defense or its opponents' play calling.</p>
    </div>
  );
}

function AllowedTable({ rows }: { rows: { label: string; value: string; league: string; rank: number; ratio: number }[] }) {
  return (
    <table className="num w-full text-[12px]">
      <thead className="text-[10.5px] uppercase tracking-wider text-ink-3">
        <tr className="text-left">
          <th className="py-1 font-medium" />
          <th className="py-1 text-right font-medium">Allowed</th>
          <th className="py-1 text-right font-medium">League</th>
          <th className="py-1 pl-3 font-medium">Rank</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.label} className="border-t border-line/60">
            <td className="py-1.5">{r.label}</td>
            <td className={`py-1.5 text-right font-semibold ${r.ratio > 1.1 ? 'text-edge-good' : r.ratio < 0.9 ? 'text-edge-bad' : ''}`}>{r.value}</td>
            <td className="py-1.5 text-right text-ink-3">{r.league}</td>
            <td className="py-1.5 pl-3 text-ink-2">
              {rankPhrase(r.rank)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function MatchupList({ title, rows, update, empty }: { title: string; rows: SlateRow[]; update: (p: HashState) => void; empty: string }) {
  return (
    <Panel title={title} note="50+ routes">
      {rows.length === 0 ? (
        <p className="text-[12px] text-ink-3">{empty}</p>
      ) : (
        <ul className="space-y-2">
          {rows.map((r) => (
            <li key={r.player} className="flex items-start gap-2.5">
              <ScoreBadge score={r.score} />
              <button type="button" onClick={() => update({ tab: 'player', player: r.player, opp: r.opponent })} className="min-w-0 text-left hover:text-accent">
                <span className="block font-semibold">
                  {r.name} <span className="font-normal text-ink-3">{r.pos} · {r.team} · {n1(r.proj)} proj</span>
                </span>
                <span className="block text-[11.5px] text-ink-2">{(r.reasons.find((x) => x.kind !== 'allowed') ?? r.reasons[0])?.text}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
