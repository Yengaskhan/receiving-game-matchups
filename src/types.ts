/** Shapes of the files in data/<season>/, written by pipeline/run_receiving.py. */

export type Pos = 'WR' | 'TE';
export type CoverageKey = 'MAN' | 'ZONE' | 'SINGLE_HIGH' | 'TWO_HIGH' | 'C2' | 'C3' | 'C4' | 'C6' | 'RZ';

export interface RateMetric {
  raw: number | null;
  adj: number;
  league: number;
  index?: number | null;
  /** SEP SCORE only: adjusted minus league (it sits near zero, so a ratio is meaningless). */
  diff?: number;
}

export interface SplitBlock {
  label: string;
  routes: number;
  low_sample: boolean;
  sep_routes?: number;
  sep_low_sample?: boolean;
  metrics: Partial<Record<'FP_RR' | 'YPRR' | 'TPRR' | 'WIN_RATE' | 'SEP_SCORE', RateMetric>>;
}

export interface Player {
  id: string;
  name: string;
  team: string;
  fp_team: string;
  pos: Pos;
  /** WR1, WR2, ... / TE1, TE2, ... within his team, by targets per game this season. */
  role?: string | null;
  g: number;
  routes: number;
  routes_pg: number;
  opponent: string | null;
  home: boolean | null;
  overall: {
    fp_rr: number; adj_fp_rr: number; pos_avg: number; yprr: number; tprr: number; win_rate: number; sep_score: number;
    sep_routes: number; tgt: number; rec: number; yds: number; td: number; ay: number; tgt_pct: number;
  };
  splits: Record<CoverageKey, SplitBlock>;
  alignment: Record<'WIDE' | 'SLOT' | 'INLINE' | 'BACK', { label: string; share: number; routes: number; tgt: number; tprr: number; yprr: number }>;
  edges: Record<string, SplitEdge>;
  reference: { sep_ms: number | null; ador: number | null; plus1: number | null; plus2: number | null; plus3: number | null; neg: number | null };
}

export interface Reason { text: string; kind: 'coverage' | 'shell' | 'zone' | 'allowed' | 'alignment' | 'position'; edge: boolean; effect: number }
export interface Flag { key: string; text: string }

/** A real (confidence >= 90%) edge or weakness in a coverage this opponent plays at a top-5 rate. */
export interface CoverageEdge { cov: CoverageKey; label: string; edge: boolean; conf: number; rank: number; pct: number; league: number; text: string }

/** "Is it real?" for one coverage split: his index there vs in its opposite, and how confident. */
export interface SplitEdge {
  metric: 'YPRR' | 'WIN_RATE';
  vs: string;
  vs_key: string;
  idx: number | null;
  vs_idx: number | null;
  routes: number;
  vs_routes: number;
  z: number | null;
  conf: number;
}

export interface Pair {
  player: string;
  defense: string;
  score: number;
  proj: number;
  fp_rr: number;
  ratio: number;
  fit: number;
  base_fit: number;
  /** Coverage fit in yards per route gained vs a league-average coverage mix (the score's coverage part). */
  cov_yards?: number;
  zone_fit: number;
  axes: Record<string, { fit: number; def: number; league: number }>;
  cov_index: number;
  /** Score parts on a log scale (0 = neutral): coverage fit, FP allowed where he lines up, FP per dropback allowed. */
  parts: Record<string, number>;
  align_index: number;
  align_weights: Record<string, number>;
  pos_index?: number;
  reasons: Reason[];
  flags: Flag[];
  coverage_edges: CoverageEdge[];
}

export interface PairFile { schema: number; season: number; week: number; defense: string; rows: Pair[] }

export interface Defense {
  team: string;
  name: string;
  g: number;
  db: number;
  opponent: string | null;
  home: boolean | null;
  coverage: { key: string; label: string; pct: number; league: number; rank: number | null }[];
  fp_db: { key: string; label: string; value: number; league: number; rank: number }[];
  alignment: { key: string; label: string; fpg: number; league: number; rank: number }[];
  context: { key: string; label: string; value: number; league: number }[];
  display_only: { pass_pct: number; proe: number; pace: number };
  index: {
    cov_raw: number; cov: number; cov_rank: number;
    cov_axes: Record<string, { allowed: number; league: number; index: number }>;
    wide: { fpg: number; league: number; raw: number; index: number };
    slot: { fpg: number; league: number; raw: number; index: number };
    te: { fpg: number; league: number; raw: number; index: number };
  };
}

export interface SlateRow {
  player: string;
  name: string;
  team: string;
  pos: Pos;
  /** WR1, WR2, ... / TE1, TE2, ... within his team, by targets per game this season. */
  role?: string | null;
  opponent: string;
  home: boolean;
  game_id: string;
  routes: number;
  routes_pg: number;
  score: number;
  proj: number;
  fp_rr: number;
  adj_fp_rr: number;
  fit: number;
  cov_index: number;
  /** Score parts on a log scale (0 = neutral): coverage fit, FP allowed where he lines up, FP per dropback allowed. */
  parts: Record<string, number>;
  pos_index?: number;
  align_index: number;
  reasons: Reason[];
  flags: Flag[];
  coverage_edges: CoverageEdge[];
}

export interface WeekFile {
  schema: number;
  season: number;
  week: number;
  data_as_of: string;
  generated_at: string;
  games: { game_id: string; away: string; home: string; gameday: string; gametime: string | null }[];
  byes: string[];
  ref_size: Record<Pos, number>;
  rows: SlateRow[];
}

export interface Meta {
  schema: number;
  season: number;
  week: number;
  generated_at: string;
  data_as_of: string;
  exports: Record<string, string>;
  model: Record<string, unknown> & { low_sample_routes: number; score_ref_min_routes: number };
  league: { defense: Record<string, number>; pos_fp_rr: Record<Pos, number> };
  joins: { file: string; by_team: number; by_pos: number; unmatched_base: unknown[]; unmatched_other: unknown[] }[];
  checks: string[];
}

export interface SeasonIndex {
  schema: number;
  season: number;
  current_week: number;
  data_as_of: string;
  default_basis: string;
  /** The views: the current season, prior seasons, and all seasons combined. */
  bases: { key: string; label: string; note: string }[];
  weeks: { week: number; games: number; file: string; data_as_of: string; first_gameday: string | null; last_gameday: string | null; bases: string[] }[];
}
