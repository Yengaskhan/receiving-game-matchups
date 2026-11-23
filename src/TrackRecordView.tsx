import { useEffect, useMemo, useState } from 'react';
import { loadBacktests, loadTrackRecord } from './data';
import { n1, share, signed } from './format';
import type { HashState } from './ReceivingApp';
import { TeamLogo } from './TeamLogo';
import type { Backtest, TrackBand, TrackRecord } from './types';
import { DivBar, Panel, ScoreBadge, Select } from './ui';

const MODEL_LABEL: Record<number, string> = {
  1: 'Old model (coverage-led)',
  2: 'Current model',
};

const pctTone = (v: number | null | undefined) => (v == null ? '' : v > 0.02 ? 'text-edge-good' : v < -0.02 ? 'text-edge-bad' : 'text-ink-2');

function BandTable({ bands }: { bands: TrackBand[] }) {
  return (
    <table className="num w-full border-collapse text-[12.5px]">
      <thead>
        <tr className="text-left text-[10.5px] uppercase tracking-wider text-ink-3">
          <th className="py-1 pr-2 font-medium">Matchup score</th>
          <th className="px-2 py-1 text-right font-medium">Players</th>
          <th className="px-2 py-1 text-right font-medium" title="Share who scored more than their normal week">Beat normal</th>
          <th className="px-2 py-1 text-right font-medium" title="Their total points vs their total normal-week points">Points vs normal</th>
          <th className="hidden w-[30%] py-1 pl-2 sm:table-cell" />
        </tr>
      </thead>
      <tbody>
        {bands.map((b) => (
          <tr key={b.key} className="border-t border-line/60">
            <td className="py-1.5 pr-2">{b.label}</td>
            <td className="px-2 py-1.5 text-right">{b.n}</td>
            <td className="px-2 py-1.5 text-right">{share(b.beat)}</td>
            <td className={`px-2 py-1.5 text-right font-semibold ${pctTone(b.vs_normal)}`}>{b.vs_normal == null ? '—' : signed(b.vs_normal * 100, 0, '%')}</td>
            <td className="hidden py-1.5 pl-2 sm:table-cell">
              {b.vs_normal != null && <DivBar value={b.vs_normal} max={0.25} tone={b.vs_normal > 0 ? 'good' : 'bad'} label={`${signed(b.vs_normal * 100, 0, '%')} vs normal`} />}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function BacktestPanel({ bt }: { bt: Backtest }) {
  return (
    <Panel title={`${bt.season} season test`} note={`weeks ${bt.weeks[0]}–${bt.weeks[1]} · ${bt.n.toLocaleString()} player-games`}>
      <p className="mb-3 text-[12.5px] text-ink-2">
        Each week of {bt.season} was scored using only the games before it, then compared with what each WR/TE actually scored. Players are split into five equal groups by
        their score, worst matchups (1) to best (5). “Points vs normal” is the group's total receiving PPR points vs the total of their normal weeks.
      </p>
      <div className="grid gap-4 md:grid-cols-2">
        {bt.models.map((m) => (
          <div key={m.key}>
            <h3 className="text-[12.5px] font-semibold text-ink">{m.key === 'v2' ? 'Current model' : 'Old model'}</h3>
            <p className="mb-1.5 text-[11.5px] text-ink-3">{m.label}</p>
            <table className="num w-full border-collapse text-[12.5px]">
              <thead>
                <tr className="text-left text-[10.5px] uppercase tracking-wider text-ink-3">
                  <th className="py-1 pr-2 font-medium">Group</th>
                  <th className="px-2 py-1 text-right font-medium">Beat normal</th>
                  <th className="px-2 py-1 text-right font-medium">Points vs normal</th>
                  <th className="w-[35%] py-1 pl-2" />
                </tr>
              </thead>
              <tbody>
                {m.quintiles.map((q) => (
                  <tr key={q.quintile} className="border-t border-line/60">
                    <td className="py-1.5 pr-2">{q.quintile === 1 ? '1 · worst' : q.quintile === 5 ? '5 · best' : q.quintile}</td>
                    <td className="px-2 py-1.5 text-right">{share(q.beat)}</td>
                    <td className={`px-2 py-1.5 text-right font-semibold ${pctTone(q.vs_normal)}`}>{signed(q.vs_normal * 100, 0, '%')}</td>
                    <td className="py-1.5 pl-2">
                      <DivBar value={q.vs_normal} max={0.2} tone={q.vs_normal > 0 ? 'good' : 'bad'} label={`${signed(q.vs_normal * 100, 0, '%')} vs normal`} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
      <details className="mt-3 text-[12px] text-ink-2">
        <summary className="cursor-pointer hover:text-ink">Which inputs predicted results</summary>
        <p className="mt-1.5 text-ink-3">Rank correlation with points vs normal (0 = no signal; in weekly fantasy data, 0.05–0.10 is a real but small edge).</p>
        <table className="num mt-1 w-full max-w-xl border-collapse">
          <tbody>
            {[...bt.signals].sort((a, b) => b.rho - a.rho).map((s) => (
              <tr key={s.key} className="border-t border-line/60">
                <td className="py-1 pr-2">{s.label}</td>
                <td className={`py-1 text-right font-semibold ${s.rho > 0.03 ? 'text-edge-good' : s.rho < -0.01 ? 'text-edge-bad' : ''}`}>{s.rho.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </Panel>
  );
}

export function TrackRecordView({ season, hash, update }: { season: number; hash: HashState; update: (p: HashState) => void }) {
  const [tr, setTr] = useState<TrackRecord | null>(null);
  const [bts, setBts] = useState<Backtest[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    loadTrackRecord(season)
      .then((t) => live && setTr(t))
      .catch((e) => live && setError(e instanceof Error ? e.message : String(e)));
    loadBacktests().then((b) => live && setBts(b.sort((x, y) => y.season - x.season)));
    return () => {
      live = false;
    };
  }, [season]);

  const wk = useMemo(() => {
    if (!tr?.weeks.length) return null;
    return tr.weeks.find((w) => String(w.week) === hash.tw) ?? tr.weeks[0];
  }, [tr, hash.tw]);

  if (error) return <p className="text-edge-bad">{error}</p>;
  if (!tr) return <p className="text-ink-3">Loading…</p>;

  const latestVersion = Math.max(...tr.overall.map((o) => o.model_version), 0);
  const rowsTop = wk ? wk.rows.slice(0, 12) : [];
  const rowsBottom = wk ? [...wk.rows].reverse().slice(0, 12) : [];

  return (
    <div className="space-y-4">
      <p className="max-w-4xl text-[13px] text-ink-2">
        How the Matchup Scores did once the games were played. Each scored player ({tr.min_routes}+ routes) is compared with his <b className="text-ink">normal week</b>: his projection
        without the matchup (his usual points per route × routes per game). Actual points are receiving PPR from nflverse. A game only counts if it kicked off after that week's data was
        exported. Weekly fantasy points swing a lot, so judge the groups, not single players: a good matchup should beat its normal week more often, and by more, than a tough one.
      </p>

      {tr.overall.length === 0 ? (
        <Panel title={`${season} results`}>
          <p className="text-[12.5px] text-ink-3">No graded weeks yet. Results appear after the games are played and the next week's data is uploaded.</p>
        </Panel>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {[...tr.overall].reverse().map((o) => (
            <Panel key={o.model_version} title={`${season} · ${MODEL_LABEL[o.model_version] ?? `Model v${o.model_version}`}`} note={`week${o.weeks.length > 1 ? 's' : ''} ${o.weeks.sort((a, b) => a - b).join(', ')} · ${o.n} players`}>
              <BandTable bands={o.bands} />
              {o.model_version < latestVersion && <p className="mt-2 text-[11.5px] text-ink-3">The scores published at the time, before the model was updated.</p>}
            </Panel>
          ))}
        </div>
      )}

      {wk && (
        <Panel
          title={`Week ${wk.week}: how they did`}
          note={
            <Select
              label=""
              value={String(wk.week)}
              onChange={(v) => update({ tw: v })}
              options={tr.weeks.map((w) => [String(w.week), `Week ${w.week} · ${MODEL_LABEL[w.model_version] ?? `v${w.model_version}`}`])}
              className="normal-case"
            />
          }
        >
          <BandTable bands={wk.bands} />
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            {[
              ['Best matchups', rowsTop],
              ['Worst matchups', rowsBottom],
            ].map(([title, rows]) => (
              <div key={title as string} className="overflow-x-auto">
                <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-ink-2">{title as string}</h3>
                <table className="num w-full min-w-[420px] border-collapse text-[12.5px]">
                  <thead>
                    <tr className="text-left text-[10.5px] uppercase tracking-wider text-ink-3">
                      <th className="py-1 pr-2 font-medium">Player</th>
                      <th className="px-2 py-1 text-center font-medium">Score</th>
                      <th className="px-2 py-1 text-right font-medium">Normal</th>
                      <th className="px-2 py-1 text-right font-medium">Actual</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(rows as typeof rowsTop).map((r) => (
                      <tr key={r.player} className="cursor-pointer border-t border-line/60 hover:bg-panel-2/70" onClick={() => update({ tab: 'player', player: r.player, opp: r.opponent })}>
                        <td className="py-1.5 pr-2">
                          <span className="flex items-center gap-2">
                            <TeamLogo team={r.team} size={18} />
                            <span className="whitespace-nowrap font-semibold">{r.name}</span>
                            <span className="text-[11px] text-ink-3">vs {r.opponent}</span>
                          </span>
                        </td>
                        <td className="px-2 py-1.5 text-center">
                          <ScoreBadge score={r.score} />
                        </td>
                        <td className="px-2 py-1.5 text-right text-ink-2">{n1(r.normal)}</td>
                        <td className={`px-2 py-1.5 text-right font-semibold ${r.actual > r.normal ? 'text-edge-good' : 'text-edge-bad'}`}>{n1(r.actual)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        </Panel>
      )}

      {bts.map((bt) => (
        <BacktestPanel key={bt.season} bt={bt} />
      ))}
    </div>
  );
}
