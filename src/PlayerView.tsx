import { useEffect, useMemo, useRef, useState } from 'react';
import { CoverageMatchup } from './CoverageMatchup';
import { loadPairs, type Core } from './data';
import { idx, n0, n1, n2, n3, pct, rankPhrase, share, signed } from './format';
import type { HashState } from './ReceivingApp';
import { TeamLogo, teamName } from './TeamLogo';
import type { CoverageKey, Defense, Pair, Player, WeekFile } from './types';
import { Card, confLabel, EdgeChip, LowSample, Panel, Pill, ScoreBadge, Select } from './ui';


export function PlayerView({ core, season, basis, week, hash, update }: { core: Core; season: number; basis: string; week: WeekFile | null; hash: HashState; update: (p: HashState) => void }) {
  const byId = useMemo(() => new Map(core.players.map((p) => [p.id, p])), [core]);
  const defs = useMemo(() => new Map(core.defenses.map((d) => [d.team, d])), [core]);
  const player = byId.get(hash.player ?? '') ?? core.players[0];
  const missing = !!hash.player && !byId.has(hash.player);
  const opp = hash.opp && defs.has(hash.opp) && hash.opp !== player.team ? hash.opp : (player.opponent ?? core.defenses.find((d) => d.team !== player.team)!.team);
  const d = defs.get(opp)!;

  const [pairFile, setPairFile] = useState<{ team: string; basis: string; rows: Map<string, Pair> } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    loadPairs(season, basis, opp)
      .then((f) => live && (setPairFile({ team: opp, basis, rows: new Map(f.rows.map((r) => [r.player, r])) }), setError(null)))
      .catch((e) => live && setError(String(e)));
    return () => {
      live = false;
    };
  }, [season, basis, opp]);
  const pair = pairFile?.team === opp && pairFile.basis === basis ? pairFile.rows.get(player.id) ?? null : null;
  const scheduled = player.opponent === opp;

  return (
    <div className="space-y-4">
      <button type="button" onClick={() => update({ tab: 'slate' })} className="text-[12.5px] text-accent hover:underline">
        ← Back to Slate Rankings
      </button>
      <div className="flex flex-wrap items-end gap-3">
        <PlayerPicker players={core.players} value={player} onChange={(p) => update({ player: p.id, opp: undefined })} />
        <Select
          label="Opponent"
          value={opp}
          onChange={(v) => update({ player: player.id, opp: v })}
          options={core.defenses.filter((x) => x.team !== player.team).map((x) => [x.team, `${x.team} · ${x.name}${x.team === player.opponent ? ' (this week)' : ''}`])}
        />
        <p className="pb-1.5 text-[12px] text-ink-3">
          {player.opponent ? (
            <>
              Week {week?.week}: {player.home ? 'vs' : '@'} {player.opponent}
              {!scheduled && (
                <button type="button" onClick={() => update({ opp: player.opponent! })} className="ml-2 text-accent hover:underline">
                  back to this week's opponent
                </button>
              )}
            </>
          ) : (
            `${player.team} is on bye this week`
          )}
        </p>
      </div>
      {missing && (
        <p className="rounded-md border border-warn/40 bg-panel px-3 py-2 text-[12px] text-ink-2">
          That player has no data in this view (e.g. a rookie in the {basis} data), so {player.name} is shown instead. Switch the Data setting back to see him.
        </p>
      )}
      {error && <p className="text-bad">{error}</p>}

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <TeamLogo team={player.team} size={32} />
        <h2 className="text-[18px] font-semibold">{player.name}</h2>
        <span className="text-[13px] text-ink-2">
          {player.role ?? player.pos} · {player.team} · {n0(player.routes)} routes in {n0(player.g)} games ({n1(player.routes_pg)} per game)
        </span>
        <span className="text-ink-3">vs</span>
        <span className="inline-flex items-center gap-1.5 text-[14px] font-semibold" title={d.name}>
          <TeamLogo team={opp} size={24} /> {teamName(opp)}
        </span>
        {!scheduled && <Pill tone="warn">not this week's game</Pill>}
      </div>

      {pair && <HeaderCards p={player} pair={pair} />}

      <CoverageMatchup p={player} d={d} pair={pair} />

      <div className="grid gap-4 lg:grid-cols-2">
        {pair && <Reasons p={player} pair={pair} />}
        <AlignmentPanel p={player} d={d} pair={pair} />
      </div>

      <RealEdges p={player} d={d} />
      <DetailTable p={player} low={core.meta.model.low_sample_routes} />
      <DefenseContext d={d} />
    </div>
  );
}

// ------------------------------------------------------------------------------------------------

function PlayerPicker({ players, value, onChange }: { players: Player[]; value: Player; onChange: (p: Player) => void }) {
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const matches = useMemo(() => {
    const s = q.trim().toLowerCase();
    const list = s ? players.filter((p) => `${p.name} ${p.team} ${p.pos}`.toLowerCase().includes(s)) : players;
    return list.slice(0, 40);
  }, [q, players]);
  useEffect(() => {
    const close = (e: MouseEvent) => box.current && !box.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);
  const pick = (p: Player) => {
    onChange(p);
    setQ('');
    setOpen(false);
  };
  return (
    <div ref={box} className="relative">
      <label className="flex flex-col gap-1 text-[10.5px] font-medium uppercase tracking-wider text-ink-3">
        Player
        <input
          role="combobox"
          aria-expanded={open}
          aria-controls="player-list"
          value={open ? q : `${value.name} · ${value.team} ${value.pos} · ${n0(value.routes)} rte`}
          onFocus={() => {
            setOpen(true);
            setHi(0);
          }}
          onChange={(e) => {
            setQ(e.target.value);
            setHi(0);
            setOpen(true);
          }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') setHi((h) => Math.min(h + 1, matches.length - 1));
            else if (e.key === 'ArrowUp') setHi((h) => Math.max(h - 1, 0));
            else if (e.key === 'Enter' && matches[hi]) pick(matches[hi]);
            else if (e.key === 'Escape') setOpen(false);
          }}
          placeholder="Search WR / TE or team"
          className="h-8 w-[min(20rem,calc(100vw-2rem))] rounded border border-line-2 bg-panel-2 px-2 text-[13px] normal-case tracking-normal text-ink placeholder:text-ink-3"
        />
      </label>
      {open && (
        <ul id="player-list" role="listbox" className="absolute z-30 mt-1 max-h-80 w-[min(20rem,calc(100vw-2rem))] overflow-y-auto rounded-md border border-line-2 bg-panel-2 py-1 shadow-lg">
          {matches.length === 0 && <li className="px-3 py-2 text-ink-3">No match</li>}
          {matches.map((p, i) => (
            <li key={p.id} role="option" aria-selected={i === hi}>
              <button
                type="button"
                onMouseEnter={() => setHi(i)}
                onClick={() => pick(p)}
                className={`flex w-full items-center gap-2 px-3 py-1.5 text-left ${i === hi ? 'bg-raise' : ''}`}
              >
                <TeamLogo team={p.team} size={18} />
                <span className="flex-1 truncate">{p.name}</span>
                <span className="text-[11px] text-ink-3">
                  {p.team} {p.role ?? p.pos} · {n0(p.routes)} rte
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function HeaderCards({ p, pair }: { p: Player; pair: Pair }) {
  const edge = pair.reasons.find((r) => r.edge);
  const concern = pair.reasons.find((r) => !r.edge);
  const top = edge ?? concern;
  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
      <Card label="Matchup Score" sub={`Expected change in his production vs his normal week. 50 = normal; +5% ≈ 66, +10% ≈ 79, −5% ≈ 34. Ranked among ${p.pos}s this week${p.routes < 50 ? ' · small sample (under 50 routes)' : ''}`}>
        <span className="flex items-center gap-3">
          <ScoreBadge score={pair.score} small={p.routes < 50} lg />
          {pair.delta != null && <span className={`num text-[18px] font-semibold ${pair.delta > 0.01 ? 'text-edge-good' : pair.delta < -0.01 ? 'text-edge-bad' : 'text-ink-2'}`}>{signed(pair.delta * 100, 1, '%')}</span>}
        </span>
      </Card>
      <Card label="Matchup-adjusted projection" sub={`${n1(p.routes_pg)} routes × ${n3(pair.fp_rr)} FP/RR (his adj. ${n3(p.overall.adj_fp_rr)})`}>
        <span className="num text-[22px] font-semibold">{n1(pair.proj)}</span> <span className="text-ink-3">PPR</span>
      </Card>
      <Card label="Coverage fit" sub={`His expected yards per route vs this coverage mix ÷ vs the league's mix (${signed(pair.cov_yards ?? 0, 2)} yds/route). Above 1.00 suits him.`}>
        <span className={`num text-[22px] font-semibold ${pair.fit > 1.01 ? 'text-edge-good' : pair.fit < 0.99 ? 'text-edge-bad' : ''}`}>{n2(pair.fit)}</span>
      </Card>
      <Card label={edge ? 'Top edge' : 'Top concern'}>
        <p className={`text-[12.5px] leading-snug ${top ? (top.edge ? 'text-edge-good' : 'text-edge-bad') : 'text-ink-3'}`}>{top?.text ?? 'No single factor stands out.'}</p>
      </Card>
    </div>
  );
}

function Reasons({ p, pair }: { p: Player; pair: Pair }) {
  return (
    <Panel title="Why" note={`coverage fit ${n2(pair.fit)} · alignment allowed ${n2(pair.align_index)} · ${p.pos} allowed ${n2(pair.pos_index ?? 1)}`}>
      {pair.coverage_edges.length > 0 && (
        <div className="mb-3 space-y-1.5 rounded border border-line bg-panel-2/50 p-2">
          <p className="text-[10.5px] font-medium uppercase tracking-wider text-ink-3">Coverage edge (90%+ confident, coverage this defense plays at a top-5 rate)</p>
          {pair.coverage_edges.map((e) => (
            <div key={e.cov} className="flex flex-wrap items-start gap-2 text-[12px]">
              <EdgeChip e={e} />
              <span className="text-ink-2">{e.text}</span>
            </div>
          ))}
        </div>
      )}
      <ul className="space-y-1.5 text-[12.5px]">
        {pair.reasons.map((r) => (
          <li key={r.text} className="flex gap-2">
            <Pill tone={r.edge ? 'good' : 'bad'}>{r.edge ? 'edge' : 'concern'}</Pill>
            <span className="text-ink">{r.text}</span>
          </li>
        ))}
        {pair.reasons.length === 0 && <li className="text-ink-3">A neutral matchup: no factor moves it much.</li>}
      </ul>
      <p className="mt-3 text-[11px] text-ink-3">
        Each reason shows about how much it moves him. The score adds them up: coverage (man vs zone, single vs two-high, Cover 2/3/4/6), where he lines up, and FP per dropback allowed. Coverage counts only as much as we're confident his gap is real.
      </p>
      {pair.flags.length > 0 && (
        <>
          <p className="mt-3 text-[10.5px] font-medium uppercase tracking-wider text-ink-3">Context (no effect on the score)</p>
          <ul className="mt-1 space-y-1 text-[12px] text-ink-2">
            {pair.flags.map((f) => (
              <li key={f.key}>· {f.text}</li>
            ))}
          </ul>
        </>
      )}
    </Panel>
  );
}

function AlignmentPanel({ p, d, pair }: { p: Player; d: Defense; pair: Pair | null }) {
  const al = new Map(d.alignment.map((a) => [a.key, a]));
  const rows: { label: string; share: number; vs: string; fpg: number; league: number; rank: number }[] = [
    { label: 'Wide', share: p.alignment.WIDE.share, vs: 'outside WRs', ...pick(al.get('OUTER')!) },
    { label: 'Slot', share: p.alignment.SLOT.share, vs: 'slot WRs', ...pick(al.get('SLOT')!) },
    { label: 'Inline', share: p.alignment.INLINE.share, vs: 'TEs', ...pick(al.get('TE')!) },
  ];
  return (
    <Panel title="Alignment" note={p.pos === 'TE' ? 'TEs are scored on FP allowed to TEs' : 'Weighted by his route share'}>
      <table className="num w-full text-[12px]">
        <thead className="text-[10.5px] uppercase tracking-wider text-ink-3">
          <tr className="text-left">
            <th className="py-1 font-medium">From</th>
            <th className="py-1 text-right font-medium">His routes</th>
            <th className="py-1 pl-3 font-medium">{d.team} allows</th>
            <th className="py-1 pl-2 text-right font-medium">FPG</th>
            <th className="py-1 pl-2 text-right font-medium">League</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const tone = r.fpg > r.league * 1.1 ? 'text-edge-good' : r.fpg < r.league * 0.9 ? 'text-edge-bad' : '';
            return (
              <tr key={r.label} className="border-t border-line/60">
                <td className="py-1.5">{r.label}</td>
                <td className="py-1.5 text-right">{share(r.share)}</td>
                <td className="py-1.5 pl-3 text-ink-2">to {r.vs} <span className="text-ink-3">({rankPhrase(r.rank)})</span></td>
                <td className={`py-1.5 text-right font-semibold ${tone}`}>{n1(r.fpg)}</td>
                <td className="py-1.5 text-right text-ink-3">{n1(r.league)}</td>
              </tr>
            );
          })}
          <tr className="border-t border-line/60 text-ink-3">
            <td className="py-1.5">Backfield</td>
            <td className="py-1.5 text-right">{share(p.alignment.BACK.share)}</td>
            <td className="py-1.5 pl-3" colSpan={3}>neutral (no split allowed)</td>
          </tr>
        </tbody>
      </table>
      {pair && <p className="mt-2 text-[11.5px] text-ink-2">Alignment allowed index (shrunk by games): <span className="num font-semibold text-ink">{n2(pair.align_index)}</span></p>}
    </Panel>
  );
}

function pick(a: { fpg: number; league: number; rank: number }) {
  return { fpg: a.fpg, league: a.league, rank: a.rank };
}

function DetailTable({ p, low }: { p: Player; low: number }) {
  const keys: CoverageKey[] = ['MAN', 'ZONE', 'SINGLE_HIGH', 'TWO_HIGH', 'C2', 'C3', 'C4', 'C6', 'RZ'];
  const cell = (m: { raw: number | null; adj: number; league: number; index?: number | null; diff?: number } | undefined, f: (v: number | null) => string, diffMode = false) =>
    m ? (
      <>
        <td className="px-2 py-1.5 text-right">{f(m.raw)}</td>
        <td className="px-2 py-1.5 text-right font-semibold">{f(m.adj)}</td>
        <td className="px-2 py-1.5 text-right text-ink-3">{f(m.league)}</td>
        <td className="px-2 py-1.5 text-right">{diffMode ? signed(m.diff, 3) : idx(m.index)}</td>
      </>
    ) : (
      <td colSpan={4} className="px-2 py-1.5 text-center text-ink-3">—</td>
    );
  const pct1 = (v: number | null) => pct(v, 1);
  return (
    <Panel title="Detail by coverage" note={`raw · adjusted (shrunk) · league · index vs league; “low n” = under ${low} routes`}>
      <div className="overflow-x-auto">
        <table className="num w-full min-w-[1080px] border-collapse text-[12px]">
          <thead className="text-[10.5px] uppercase tracking-wider text-ink-3">
            <tr>
              <th rowSpan={2} className="sticky left-0 z-10 bg-panel px-2 py-1 text-left font-medium">Coverage</th>
              <th rowSpan={2} className="px-2 py-1 text-right font-medium">Routes</th>
              <th colSpan={4} className="border-l border-line px-2 py-1 font-medium">FP / route</th>
              <th colSpan={4} className="border-l border-line px-2 py-1 font-medium">Yards / route</th>
              <th colSpan={4} className="border-l border-line px-2 py-1 font-medium">Targets / route</th>
              <th rowSpan={2} className="border-l border-line px-2 py-1 text-right font-medium">Sep. routes</th>
              <th colSpan={4} className="px-2 py-1 font-medium">Win rate</th>
              <th colSpan={4} className="border-l border-line px-2 py-1 font-medium">Sep. score (± vs lg)</th>
            </tr>
            <tr className="text-right">
              {Array.from({ length: 5 }).flatMap((_, g) =>
                ['raw', 'adj', 'lg', g === 4 ? '±' : 'idx'].map((h, i) => (
                  <th key={`${g}${h}`} className={`px-2 py-1 font-medium ${i === 0 && g !== 3 ? 'border-l border-line' : ''}`}>
                    {h}
                  </th>
                )),
              )}
            </tr>
          </thead>
          <tbody>
            <tr className="border-t border-line bg-panel-2/40">
              <th scope="row" className="sticky left-0 z-10 bg-panel-2 px-2 py-1.5 text-left font-medium">Overall</th>
              <td className="px-2 py-1.5 text-right">{n0(p.routes)}</td>
              <td className="border-l border-line px-2 py-1.5 text-right">{n2(p.overall.fp_rr)}</td>
              <td className="px-2 py-1.5 text-right font-semibold" title="Shrunk toward the position average">{n2(p.overall.adj_fp_rr)}</td>
              <td className="px-2 py-1.5 text-right text-ink-3" title={`${p.pos} average`}>{n2(p.overall.pos_avg)}</td>
              <td className="px-2 py-1.5 text-right">{idx(p.overall.adj_fp_rr / p.overall.pos_avg)}</td>
              <td className="border-l border-line px-2 py-1.5 text-right">{n2(p.overall.yprr)}</td>
              <td colSpan={3} />
              <td className="border-l border-line px-2 py-1.5 text-right">{n2(p.overall.tprr)}</td>
              <td colSpan={3} />
              <td className="border-l border-line px-2 py-1.5 text-right">{n0(p.overall.sep_routes)}</td>
              <td className="px-2 py-1.5 text-right">{pct(p.overall.win_rate, 1)}</td>
              <td colSpan={3} />
              <td className="border-l border-line px-2 py-1.5 text-right">{n3(p.overall.sep_score)}</td>
              <td colSpan={3} />
            </tr>
            {keys.map((k) => {
              const s = p.splits[k];
              const sr = s.sep_routes ?? s.routes;
              const has = !!s.metrics.FP_RR;
              return (
                <tr key={k} className="border-t border-line/50">
                  <th scope="row" className="sticky left-0 z-10 bg-panel px-2 py-1.5 text-left font-medium">
                    {s.label}
                    {(has ? s.low_sample : s.sep_low_sample) && <LowSample routes={has ? s.routes : sr} />}
                  </th>
                  <td className="px-2 py-1.5 text-right">{has ? n0(s.routes) : '—'}</td>
                  {has ? cell(s.metrics.FP_RR, n2) : <td colSpan={4} className="border-l border-line px-2 py-1.5 text-center text-ink-3">no split in the export</td>}
                  {has ? cell(s.metrics.YPRR, n2) : <td colSpan={4} className="border-l border-line" />}
                  {has ? cell(s.metrics.TPRR, n2) : <td colSpan={4} className="border-l border-line" />}
                  <td className="border-l border-line px-2 py-1.5 text-right">{s.metrics.WIN_RATE ? n0(sr) : '—'}</td>
                  {s.metrics.WIN_RATE ? cell(s.metrics.WIN_RATE, pct1) : <td colSpan={4} className="px-2 py-1.5 text-center text-ink-3">—</td>}
                  {s.metrics.SEP_SCORE ? cell(s.metrics.SEP_SCORE, n3, true) : <td colSpan={4} className="border-l border-line px-2 py-1.5 text-center text-ink-3">—</td>}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-[11px] text-ink-3">
        For reference only (not defined by the source, so not used in any calculation): SEP MS {n2(p.reference.sep_ms)} · ADOR {n2(p.reference.ador)} · +1 Rate {pct(p.reference.plus1, 1)} · +2 Rate {pct(p.reference.plus2, 1)} · +3 Rate {pct(p.reference.plus3, 1)} · Neg Rate {pct(p.reference.neg, 1)}.
        Season line: {n0(p.overall.tgt)} targets ({pct(p.overall.tgt_pct, 1)} share), {n0(p.overall.rec)} rec, {n0(p.overall.yds)} yds, {n0(p.overall.td)} TD, {n0(p.overall.ay)} air yards.
      </p>
    </Panel>
  );
}

export function DefenseContext({ d }: { d: Defense }) {
  const show = ['blitz_pct', 'press_pct_any', 'press_pct_tgt', 'disguise_pct', 'to_one_hi_pct', 'to_two_hi_pct', 'sack_pct', 'base_pct', 'nickel_pct', 'dime_pct'];
  const items = d.context.filter((c) => show.includes(c.key));
  return (
    <Panel title={`${d.team} defense context`} note="No effect on the score">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        {items.map((c) => {
          const diff = c.value - c.league;
          return (
            <div key={c.key} className="rounded border border-line bg-panel-2/50 px-2.5 py-2">
              <p className="text-[10.5px] uppercase tracking-wider text-ink-3">{c.label}</p>
              <p className="num text-[15px] font-semibold">{pct(c.value, 1)}</p>
              <p className="num text-[11px] text-ink-3">
                lg {pct(c.league, 1)} · {signed(diff)} pts
              </p>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

const EDGE_ROWS: { key: string; usage: string }[] = [
  { key: 'MAN', usage: 'MAN' },
  { key: 'ZONE', usage: 'ZONE' },
  { key: 'SINGLE_HIGH', usage: 'SINGLE_HIGH' },
  { key: 'TWO_HIGH', usage: 'TWO_HIGH' },
  { key: 'C2', usage: 'C2' },
  { key: 'C3', usage: 'C3' },
  { key: 'C4', usage: 'C4' },
  { key: 'C6', usage: 'C6' },
];

/** "Is it real?": each coverage split vs its opposite, with how confident we are it isn't luck. */
function RealEdges({ p, d }: { p: Player; d: Defense }) {
  const usage = new Map(d.coverage.map((c) => [c.key, c]));
  return (
    <Panel title="Is it real? His coverage splits" note="Raw numbers this season · confidence that the gap isn't luck">
      <div className="overflow-x-auto">
        <table className="num w-full min-w-[720px] text-[12px]">
          <thead className="text-[10.5px] uppercase tracking-wider text-ink-3">
            <tr className="text-left">
              <th className="py-1 font-medium">Coverage</th>
              <th className="py-1 text-right font-medium">His index</th>
              <th className="py-1 pl-3 font-medium">Compared with</th>
              <th className="py-1 text-right font-medium">Routes</th>
              <th className="py-1 pl-3 font-medium">Confidence</th>
              <th className="py-1 pl-3 font-medium">{d.team} plays it</th>
            </tr>
          </thead>
          <tbody>
            {EDGE_ROWS.map(({ key, usage: u }) => {
              const e = p.edges[key];
              if (!e) return null;
              const c = usage.get(u);
              const cl = confLabel(e.conf);
              const better = (e.z ?? 0) > 0;
              const metric = e.metric === 'YPRR' ? 'yds/route' : 'win rate';
              return (
                <tr key={key} className="border-t border-line/60">
                  <td className="py-1.5 font-medium">
                    {p.splits[key as CoverageKey].label}
                    <span className="block text-[10.5px] font-normal text-ink-3">{metric}</span>
                  </td>
                  <td className={`py-1.5 text-right font-semibold ${e.conf >= 0.9 ? (better ? 'text-edge-good' : 'text-edge-bad') : ''}`}>{idx(e.idx)}</td>
                  <td className="py-1.5 pl-3 text-ink-2">
                    {idx(e.vs_idx)} <span className="text-ink-3">vs {e.vs.toLowerCase()}</span>
                  </td>
                  <td className="py-1.5 text-right text-ink-3">
                    {n0(e.routes)} / {n0(e.vs_routes)}
                  </td>
                  <td className="py-1.5 pl-3">
                    <span className="inline-flex items-center gap-2">
                      <Pill tone={cl.tone}>{cl.label}</Pill>
                      <span className="text-ink-2">{e.z == null ? '—' : `${Math.round(e.conf * 100)}% sure he's ${better ? 'better' : 'worse'} here`}</span>
                    </span>
                  </td>
                  <td className="py-1.5 pl-3 text-ink-2">
                    {c ? (
                      <>
                        {pct(c.pct)} <span className={c.rank != null && c.rank <= 5 ? 'font-semibold text-accent' : 'text-ink-3'}>({c.rank != null ? `#${c.rank}` : '—'})</span>
                      </>
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-[11px] text-ink-3">
        Index = his rate in that coverage ÷ the league rate in it (1.00 = league average). Man vs zone and single- vs two-high compare yards per route; Cover 2/3/4/6 compare win rate with his other zone coverages
        (the exports have no yards for them). Confidence: how sure we can be the gap isn't luck, given how many routes it's based on. Real = 90%+, leaning = 75–90%. #rank = how often {d.team} plays it among 32 defenses.
      </p>
    </Panel>
  );
}
