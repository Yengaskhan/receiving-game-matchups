import type { Defense, Meta, PairFile, Player, SeasonIndex, WeekFile } from './types';

/*
 * Everything is precomputed by pipeline/run_receiving.py and committed under data/. Files are bundled
 * at build time: the small season index eagerly, everything else as its own chunk loaded on demand.
 * Nothing is fetched from anywhere else at runtime.
 */

const indexes = import.meta.glob('/data/*/index.json', { eager: true, import: 'default' }) as Record<string, SeasonIndex>;
const metas = import.meta.glob('/data/*/meta.json', { import: 'default' }) as Record<string, () => Promise<Meta>>;
const players = import.meta.glob('/data/*/players.json', { import: 'default' }) as Record<string, () => Promise<{ players: Player[] }>>;
const defenses = import.meta.glob('/data/*/defenses.json', { import: 'default' }) as Record<string, () => Promise<{ defenses: Defense[] }>>;
const pairs = import.meta.glob('/data/*/pairs/*.json', { import: 'default' }) as Record<string, () => Promise<PairFile>>;
const weeks = import.meta.glob('/data/*/week-*.json', { import: 'default' }) as Record<string, () => Promise<WeekFile>>;

function need<T>(table: Record<string, () => Promise<T>>, path: string): Promise<T> {
  const load = table[path];
  if (!load) return Promise.reject(new Error(`No data file ${path}. Re-run the pipeline (see README).`));
  return load();
}

/** The newest season with data. */
export function latestIndex(): SeasonIndex | null {
  return Object.values(indexes).sort((a, b) => b.season - a.season)[0] ?? null;
}

export interface Core { meta: Meta; players: Player[]; defenses: Defense[] }

export async function loadCore(season: number): Promise<Core> {
  const [meta, p, d] = await Promise.all([
    need(metas, `/data/${season}/meta.json`),
    need(players, `/data/${season}/players.json`),
    need(defenses, `/data/${season}/defenses.json`),
  ]);
  return { meta, players: p.players, defenses: d.defenses };
}

export const loadPairs = (season: number, team: string) => need(pairs, `/data/${season}/pairs/${team}.json`);
export const loadWeek = (path: string) => need(weeks, `/${path}`);
