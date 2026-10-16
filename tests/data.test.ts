import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { formatAsOf, ordinal, rankPhrase } from '../src/format';
import type { Defense, Meta, PairFile, Player, SeasonIndex, WeekFile } from '../src/types';

/*
 * Checks every committed output in data/<season>/<view>/. `npm run build` runs this, so a bad pipeline
 * output fails the deploy instead of reaching the site.
 */

const ROOT = join(__dirname, '..');
const DATA = join(ROOT, 'data');
const seasons = existsSync(DATA) ? readdirSync(DATA).filter((d) => /^\d{4}$/.test(d)) : [];
const read = <T>(...p: string[]) => JSON.parse(readFileSync(join(DATA, ...p), 'utf8')) as T;

describe.each(seasons)('season %s', (season) => {
  const index = read<SeasonIndex>(season, 'index.json');

  it('index: views exist, default is the current season, weeks match the files', () => {
    expect(index.bases.length).toBeGreaterThan(0);
    expect(index.default_basis).toBe(season);
    for (const b of index.bases) expect(existsSync(join(DATA, season, b.key, 'meta.json'))).toBe(true);
    for (const w of index.weeks) for (const b of w.bases) expect(existsSync(join(DATA, season, b, w.file))).toBe(true);
    const onDisk = readdirSync(join(DATA, season, season)).filter((f) => /^week-\d+\.json$/.test(f));
    expect(index.weeks.map((w) => w.file).sort()).toEqual(onDisk.sort());
    expect(index.weeks.some((w) => w.week === index.current_week)).toBe(true);
  });

  describe.each(index.bases.map((b) => [b.key] as const))('view %s', (basis) => {
    const meta = read<Meta>(season, basis, 'meta.json');
    const players = read<{ players: Player[] }>(season, basis, 'players.json').players;
    const defenses = read<{ defenses: Defense[] }>(season, basis, 'defenses.json').defenses;

    it('has a data-as-of stamp', () => {
      expect(meta.data_as_of).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
    });

    it('players: unique ids, WR/TE only, sane values', () => {
      expect(new Set(players.map((p) => p.id)).size).toBe(players.length);
      for (const p of players) {
        expect(['WR', 'TE']).toContain(p.pos);
        expect(p.overall.adj_fp_rr).toBeGreaterThan(0);
        const shares = Object.values(p.alignment).reduce((s, a) => s + a.share, 0);
        expect(shares === 0 || Math.abs(shares - 1) < 1e-3).toBe(true);
      }
    });

    it('32 defenses, each with a pair file covering every other team’s players', () => {
      expect(defenses.length).toBe(32);
      for (const d of defenses) {
        const f = read<PairFile>(season, basis, 'pairs', `${d.team}.json`);
        expect(f.rows.length).toBe(players.filter((p) => p.team !== d.team).length);
        for (const r of f.rows) {
          expect(r.score).toBeGreaterThanOrEqual(0);
          expect(r.score).toBeLessThanOrEqual(100);
          expect(r.proj).toBeGreaterThanOrEqual(0);
        }
      }
    });

    it.each(index.weeks.filter((w) => w.bases.includes(basis)).map((w) => [w.week, w] as const))('week %i slate', (_w, entry) => {
      const w = read<WeekFile>(season, basis, entry.file);
      const teams = new Set(w.games.flatMap((g) => [g.away, g.home]));
      expect(teams.size + w.byes.length).toBe(32);
      for (const r of w.rows) {
        expect(teams.has(r.team) && teams.has(r.opponent)).toBe(true);
        expect(r.reasons.length).toBeLessThanOrEqual(3);
      }
      for (const pos of ['WR', 'TE']) {
        const scored = w.rows.filter((r) => r.routes >= 50 && r.pos === pos);
        expect(scored.every((r) => r.score != null)).toBe(true);
        const mean = scored.reduce((s, r) => s + r.score, 0) / scored.length;
        expect(mean).toBeGreaterThan(40);
        expect(mean).toBeLessThan(60);
      }
    });
  });
});

describe('format', () => {
  it('ordinals and rank phrases', () => {
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22].map(ordinal)).toEqual(['1st', '2nd', '3rd', '4th', '11th', '12th', '13th', '21st', '22nd']);
    expect(rankPhrase(2)).toBe('2nd most');
    expect(rankPhrase(32)).toBe('1st fewest');
  });
  it('data-as-of stamp', () => {
    expect(formatAsOf('2026-10-14 22:08')).toBe('Oct 14, 2026, 10:08 PM UTC');
  });
});
