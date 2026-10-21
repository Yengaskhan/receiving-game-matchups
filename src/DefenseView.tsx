import { useMemo } from 'react';
import type { Core } from './data';
import { DefenseContext } from './PlayerView';
import { n1, n2, pct, rankPhrase, signed } from './format';
import type { HashState } from './ReceivingApp';
import { TeamLogo } from './TeamLogo';
import type { Defense, SlateRow, WeekFile } from './types';
import { Panel, ScoreBadge, Select } from './ui';
import { Card, MixBars, type Tone } from './CoverageMatchup';

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

      <h2 className="text-[11px] font-semibold uppercase tracking-wider text-ink-2">How {d.team} covers, and what it allows against each look</h2>
      <div className="grid gap-3 lg:grid-cols-3">
        <AxisCard d={d} title="Man vs Zone" keys={[['MAN', 'Man', 'MAN'], ['ZONE', 'Zone', 'ZONE']]} />
        <AxisCard d={d} title="Single-high vs Two-high" keys={[['SINGLE_HIGH', 'Single-high', 'SINGLE_HIGH'], ['TWO_HIGH', 'Two-high', 'TWO_HIGH']]} />
        <FamilyCard d={d} />
      </div>

      <Panel title="FP allowed by alignment" note="PPR points per game · rank 1 = allows the most">
        <AllowedTable rows={d.alignment.map((a) => ({ label: a.label, value: n1(a.fpg), league: n1(a.league), rank: a.rank, ratio: a.fpg / a.league }))} />
      </Panel>

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
                  {r.name} <span className="font-normal text-ink-3">{r.role ?? r.pos} · {r.team} · {n1(r.proj)} proj</span>
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

const TONE_BAR: Record<Tone, string> = { good: 'bg-edge-good', bad: 'bg-edge-bad', neutral: 'bg-ink-3/70' };
const TONE_TEXT: Record<Tone, string> = { good: 'text-edge-good', bad: 'text-edge-bad', neutral: 'text-ink' };
/** Allowing more is good for receivers (green), less is bad (orange): the same colours as the slate. */
const allowTone = (ratio: number): Tone => (ratio > 1.1 ? 'good' : ratio < 0.9 ? 'bad' : 'neutral');

/** One coverage pair: this defense's mix vs the league's, and FP per dropback it allows against each side. */
function AxisCard({ d, title, keys }: { d: Defense; title: string; keys: [string, string, string][] }) {
  const cov = new Map(d.coverage.map((c) => [c.key, c]));
  const fp = new Map(d.fp_db.map((f) => [f.key, f]));
  const tot = keys.reduce((s, [k]) => s + (cov.get(k)?.pct ?? 0), 0) || 1;
  const ltot = keys.reduce((s, [k]) => s + (cov.get(k)?.league ?? 0), 0) || 1;
  const ss = keys.map(([k, label]) => ({ key: k, label, share: (cov.get(k)?.pct ?? 0) / tot, league: (cov.get(k)?.league ?? 0) / ltot }));
  const lean = [...ss].sort((a, b) => b.share - b.league - (a.share - a.league))[0];
  const pts = (lean.share - lean.league) * 100;
  const flat = Math.abs(pts) < 2;
  const leanFp = fp.get(keys.find(([k]) => k === lean.key)![2]);
  const tone: Tone = flat || !leanFp ? 'neutral' : allowTone(leanFp.value / leanFp.league);
  return (
    <Card
      title={title}
      verdict={<LeanTag text={flat ? 'about like the league' : `leans ${lean.label.toLowerCase()} +${pts.toFixed(0)} pts`} />}
      footer={
        flat ? (
          <>{d.team} splits these about like the league does.</>
        ) : (
          <>
            {d.team} plays <b className="text-ink">{lean.label.toLowerCase()}</b> on {Math.round(lean.share * 100)}% (league {Math.round(lean.league * 100)}%)
            {leanFp && (
              <>
                {' '}and allows <b className={TONE_TEXT[tone]}>{leanFp.value.toFixed(2)}</b> PPR per dropback against it (league {leanFp.league.toFixed(2)}, {rankPhrase(leanFp.rank)}).
              </>
            )}
          </>
        )
      }
    >
      <MixBars team={d.team} ss={ss} lean={flat ? null : lean.key} />
      <div className="space-y-1.5">
        <div className="grid grid-cols-[7rem_minmax(0,1fr)_3rem] gap-2 text-[10.5px] uppercase tracking-wider text-ink-3">
          <span>FP / dropback</span>
          <span className="relative">
            <span className="absolute left-1/2 -translate-x-1/2 normal-case tracking-normal">league</span>
          </span>
          <span />
        </div>
        {keys.map(([k, label, fk]) => {
          const f = fp.get(fk);
          if (!f) return null;
          const t = allowTone(f.value / f.league);
          return (
            <div key={k} className="grid grid-cols-[7rem_minmax(0,1fr)_3rem] items-center gap-2">
              <span className="truncate text-[12px]">
                vs {label} <span className="text-[10.5px] text-ink-3">#{f.rank}</span>
              </span>
              <span className="relative block h-4 rounded bg-panel-2" role="img" aria-label={`vs ${label}: ${f.value.toFixed(2)} (league ${f.league.toFixed(2)})`} title={`vs ${label}: ${f.value.toFixed(2)} PPR per dropback, league ${f.league.toFixed(2)}, ${rankPhrase(f.rank)}`}>
                <span className={`absolute inset-y-0 left-0 rounded ${TONE_BAR[t]}`} style={{ width: `${Math.min(f.value / f.league / 2, 1) * 100}%` }} />
                <span aria-hidden className="absolute -inset-y-0.5 left-1/2 w-px bg-ink-2" />
              </span>
              <span className={`num text-right text-[13px] font-semibold ${TONE_TEXT[t]}`}>{f.value.toFixed(2)}</span>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

/** Every specific coverage: the full mix vs the league's, and the biggest differences. */
function FamilyCard({ d }: { d: Defense }) {
  const keys: [string, string][] = [['C0', 'C0'], ['C1', 'C1'], ['C2M', 'C2M'], ['C2', 'C2'], ['C3', 'C3'], ['C4', 'C4'], ['C6', 'C6']];
  const names: Record<string, string> = { C0: 'Cover 0', C1: 'Cover 1', C2M: 'Cover 2 Man', C2: 'Cover 2', C3: 'Cover 3', C4: 'Cover 4', C6: 'Cover 6' };
  const cov = new Map(d.coverage.map((c) => [c.key, c]));
  const tot = keys.reduce((s, [k]) => s + (cov.get(k)?.pct ?? 0), 0) || 1;
  const ltot = keys.reduce((s, [k]) => s + (cov.get(k)?.league ?? 0), 0) || 1;
  const ss = keys.map(([k, label]) => ({ key: k, label, share: (cov.get(k)?.pct ?? 0) / tot, league: (cov.get(k)?.league ?? 0) / ltot }));
  const diffs = keys
    .map(([k]) => ({ k, c: cov.get(k)! }))
    .filter((x) => x.c)
    .map((x) => ({ ...x, diff: x.c.pct - x.c.league }))
    .sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff));
  const top = diffs[0];
  return (
    <Card
      title="Coverage types"
      verdict={top ? <LeanTag text={`biggest gap: ${names[top.k]} ${signed(top.diff, 0)} pts`} /> : null}
      footer={<>No FP split by coverage type in the exports; the player page shows how each receiver wins against them.</>}
    >
      <MixBars team={d.team} ss={ss} lean={top && top.diff > 0 ? top.k : null} minLabel={0.1} />
      <div className="space-y-1">
        {diffs.map(({ k, c, diff }) => (
          <div key={k} className="grid grid-cols-[6.5rem_minmax(0,1fr)_3.5rem] items-center gap-2 text-[12px]">
            <span>
              {names[k]}
              {c.rank != null && <span className="ml-1 text-[10.5px] text-ink-3">#{c.rank}</span>}
            </span>
            <span className="num text-ink-2">
              {pct(c.pct)} <span className="text-ink-3">vs lg {pct(c.league)}</span>
            </span>
            <span className={`num text-right font-semibold ${Math.abs(diff) < 2 ? 'text-ink-3' : 'text-ink'}`}>{signed(diff, 0)}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function LeanTag({ text }: { text: string }) {
  return <span className="whitespace-nowrap rounded border border-accent/40 bg-accent/10 px-2 py-0.5 text-[12px] font-semibold text-accent">{text}</span>;
}
