import { useEffect, useMemo, useState } from 'react';
import { loadWeek } from './data';
import { n1, signed } from './format';
import type { HashState } from './ReceivingApp';
import { TeamLogo } from './TeamLogo';
import type { SeasonIndex, SlateRow, WeekFile } from './types';
import { Panel, ScoreBadge } from './ui';

const MAX = 4;
/** Normal weeks within this share of each other: close enough that the matchup grade decides. */
const CLOSE = 0.12;

const normalOf = (r: SlateRow) => r.proj / (1 + (r.delta ?? 0));

function statusNote(r: SlateRow): string | null {
  if (!r.status) return null;
  if (r.status.injury) return r.status.injury;
  if (!r.status.active) return r.status.last_week ? `Hasn't played since week ${r.status.last_week}` : 'Inactive';
  return null;
}

function Picker({ rows, onPick, exclude }: { rows: SlateRow[]; onPick: (id: string) => void; exclude: string[] }) {
  const [q, setQ] = useState('');
  const hits = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (s.length < 2) return [];
    return rows.filter((r) => !exclude.includes(r.player) && r.name.toLowerCase().includes(s)).slice(0, 8);
  }, [q, rows, exclude]);
  return (
    <div className="relative w-full max-w-xs">
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Add a player…"
        aria-label="Add a player to compare"
        className="h-9 w-full rounded border border-line-2 bg-panel-2 px-2.5 text-[13px] text-ink placeholder:text-ink-3"
      />
      {hits.length > 0 && (
        <ul className="absolute z-30 mt-1 w-full overflow-hidden rounded-md border border-line-2 bg-panel-2 py-1 shadow-lg">
          {hits.map((r) => (
            <li key={r.player}>
              <button
                type="button"
                onClick={() => (onPick(r.player), setQ(''))}
                className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-[13px] hover:bg-raise"
              >
                <TeamLogo team={r.team} size={18} />
                <span className="font-semibold">{r.name}</span>
                <span className="text-[11px] text-ink-3">
                  {r.role ?? r.pos} · {r.home ? 'vs' : '@'} {r.opponent}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function CompareView({ index, basis, hash, update }: { index: SeasonIndex; basis: string; hash: HashState; update: (p: HashState) => void }) {
  const avail = index.weeks.filter((w) => w.bases.includes(basis));
  const entry = avail.find((w) => w.week === index.current_week) ?? avail[avail.length - 1];
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

  const ids = (hash.cmp ?? '').split(',').filter(Boolean).slice(0, MAX);
  const setIds = (next: string[]) => update({ cmp: next.length ? next.join(',') : undefined });
  const picked = useMemo(() => ids.map((id) => week?.rows.find((r) => r.player === id)).filter((r): r is SlateRow => !!r), [ids, week]);

  if (error) return <p className="text-edge-bad">{error}</p>;
  if (!week) return <p className="text-ink-3">Loading…</p>;

  const ranked = [...picked].sort((a, b) => b.proj - a.proj);
  const best = ranked[0];
  const second = ranked[1];
  let verdict: string | null = null;
  let pick: SlateRow | undefined = best;
  if (best && second) {
    const nb = normalOf(best);
    const ns = normalOf(second);
    const close = Math.abs(nb - ns) / Math.max(nb, ns, 0.1) <= CLOSE;
    const gap = best.proj - second.proj;
    if (gap < 0.3) {
      const [a, b] = best.score >= second.score ? [best, second] : [second, best];
      pick = a;
      verdict = `${a.name}, barely. They project within ${n1(gap)} points of each other, so the better matchup breaks the tie (${a.score} vs ${b.score}).`;
    } else if (close) {
      verdict = `${best.name}. Their normal weeks are close (${n1(nb)} vs ${n1(ns)}), so the matchup decides: ${signed((best.delta ?? 0) * 100, 0, '%')} for ${best.name.split(' ').slice(-1)[0]} vs ${signed((second.delta ?? 0) * 100, 0, '%')} for ${second.name.split(' ').slice(-1)[0]}. ${n1(gap)} more projected points.`;
    } else if (best.score >= second.score) {
      verdict = `${best.name}. Better normal week (${n1(nb)} vs ${n1(ns)}) and the better matchup. ${n1(gap)} more projected points.`;
    } else {
      verdict = `${best.name}. ${second.name} has the better matchup (${second.score} vs ${best.score}), but not enough to make up the gap in their normal weeks (${n1(nb)} vs ${n1(ns)}). ${best.name} still projects ${n1(gap)} more points.`;
    }
  }

  return (
    <div className="space-y-4">
      <p className="max-w-3xl text-[13px] text-ink-2">
        Deciding between players? Add up to {MAX} for week {week.week}. The pick is the higher <b className="text-ink">matchup-adjusted projection</b>: his normal week × this
        week's matchup. When their normal weeks are close, that's the player with the better grade.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {ids.length < MAX && <Picker rows={week.rows} exclude={ids} onPick={(id) => setIds([...ids, id])} />}
        {ids.length > 0 && (
          <button type="button" onClick={() => setIds([])} className="h-9 rounded border border-line-2 bg-panel-2 px-3 text-[12.5px] text-ink-2 hover:text-ink">
            Clear
          </button>
        )}
      </div>

      {verdict && (
        <div className="rounded-md border border-edge-good/40 bg-edge-good/10 px-3 py-2 text-[13.5px] text-ink">
          <span className="font-semibold text-edge-good">Start: </span>
          {verdict}
        </div>
      )}

      {picked.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {picked.map((r) => {
            const note = statusNote(r);
            const isBest = picked.length > 1 && r === pick;
            return (
              <Panel
                key={r.player}
                className={isBest ? 'ring-1 ring-edge-good/60' : ''}
                title={
                  <span className="flex items-center gap-2 normal-case tracking-normal">
                    <TeamLogo team={r.team} size={20} />
                    <span className="text-[13px] font-semibold text-ink">{r.name}</span>
                  </span>
                }
                note={
                  <button type="button" onClick={() => setIds(ids.filter((i) => i !== r.player))} className="text-ink-3 hover:text-ink" aria-label={`Remove ${r.name}`}>
                    ✕
                  </button>
                }
              >
                <p className="text-[12px] text-ink-3">
                  {r.role ?? r.pos} · {r.team} {r.home ? 'vs' : '@'} {r.opponent}
                  {note && <span className="ml-1.5 rounded bg-edge-bad/15 px-1 text-[10.5px] font-semibold text-edge-bad">{note}</span>}
                </p>
                <div className="mt-2 flex items-center gap-3">
                  <ScoreBadge score={r.score} lg small={r.routes < 50} />
                  <div className="num text-[12.5px]">
                    <div className={(r.delta ?? 0) > 0.01 ? 'text-edge-good' : (r.delta ?? 0) < -0.01 ? 'text-edge-bad' : 'text-ink-2'}>{signed((r.delta ?? 0) * 100, 0, '%')} vs his normal week</div>
                    <div className="text-ink-3">Grade</div>
                  </div>
                </div>
                <dl className="num mt-3 grid grid-cols-2 gap-y-1 text-[12.5px]">
                  <dt className="text-ink-3">Normal week</dt>
                  <dd className="text-right">{n1(normalOf(r))}</dd>
                  <dt className="text-ink-3">This week (proj.)</dt>
                  <dd className={`text-right font-semibold ${isBest ? 'text-edge-good' : 'text-ink'}`}>{n1(r.proj)}</dd>
                  <dt className="text-ink-3">Team total</dt>
                  <dd className="text-right">{r.game ? `${n1(r.game.imp)} (${signed(r.game.imp - r.game.avg, 1)})` : '—'}</dd>
                  <dt className="text-ink-3">Routes / game</dt>
                  <dd className="text-right">{n1(r.routes_pg)}</dd>
                </dl>
                <ul className="mt-3 list-disc space-y-1 pl-4 text-[12px] text-ink-2">
                  {r.reasons.map((x) => (
                    <li key={x.text}>{x.text}</li>
                  ))}
                </ul>
                <button type="button" onClick={() => update({ tab: 'player', player: r.player, opp: r.opponent })} className="mt-3 text-[12px] text-accent hover:underline">
                  Full matchup →
                </button>
              </Panel>
            );
          })}
        </div>
      )}
      {picked.length === 0 && <p className="text-[12.5px] text-ink-3">Type a name to add the first player.</p>}
    </div>
  );
}
