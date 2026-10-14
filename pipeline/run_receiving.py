"""
Receiving Game Matchup Report pipeline.

    python pipeline/run_receiving.py --inspect    # load and check the six exports, print what was parsed

Reads the six FantasyPoints Data Suite exports in data/raw/, maps teams, joins the player files and
(next stage) runs the matchup model and writes the site's JSON files.
"""

import argparse
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))

from receiving.config import COVERAGE_AGREE_TOL, FILES, PLAYER_FILES, POSITIONS, SEASON  # noqa: E402
from receiving.join import join_player_files  # noqa: E402
from receiving.load import FormatError, load_all  # noqa: E402
from receiving.teams import TeamMapError, load_team_map  # noqa: E402


def wrap(names: list[str], width: int = 110, indent: str = "    ") -> str:
    lines, cur = [], indent
    for n in names:
        if len(cur) + len(n) + 2 > width:
            lines.append(cur.rstrip())
            cur = indent
        cur += n + ", "
    lines.append(cur.rstrip(", "))
    return "\n".join(lines)


def inspect() -> int:
    ex = load_all()
    tm = load_team_map()

    print("== Files ==")
    for k, e in ex.items():
        print(f"\n{e.file}  ({e.df.height} rows + League Avg; exported {e.exported_at} UTC; {len(e.df.columns)} columns)")
        print(wrap(e.df.columns))

    print("\n== Team mapping ==")
    for k in ("situation", "separation", "alignment", "points_allowed"):
        codes = sorted(set(ex[k].df["TEAM"].to_list()))
        mapped = {c: tm.fp(c, ex[k].file) for c in codes}
        print(f"{ex[k].file}: {len(codes)} team codes, all mapped" + (f"; renamed {', '.join(f'{a}->{b}' for a, b in mapped.items() if a != b)}" if any(a != b for a, b in mapped.items()) else ""))
    for k in ("coverage", "defense"):
        names = sorted(set(ex[k].df["NAME"].to_list()))
        for n in names:
            tm.full(n, ex[k].file)
        print(f"{ex[k].file}: {len(names)} team names, all mapped")
    for k in ("coverage", "defense", "points_allowed"):
        if ex[k].df.height != 32:
            raise TeamMapError(f"{ex[k].file}: {ex[k].df.height} team rows, expected 32.")

    import nflreadpy as nfl
    sched = nfl.load_schedules([SEASON]).filter(pl.col("game_type") == "REG")
    sched_teams = set(sched["home_team"].to_list()) | set(sched["away_team"].to_list())
    print(f"nflverse {SEASON} schedule: {len(sched_teams)} teams; "
          + ("all in team_map" if sched_teams == set(tm.names) else f"NOT in team_map: {sorted(sched_teams - set(tm.names))}"))
    week = nfl.get_current_week()
    wk = sched.filter(pl.col("week") == week)
    playing = set(wk["home_team"].to_list()) | set(wk["away_team"].to_list())
    print(f"Week {week}: {wk.height} games, {len(playing)} teams; on bye: {', '.join(sorted(set(tm.names) - playing)) or 'none'}")

    print("\n== Player rows ==")
    for k in PLAYER_FILES:
        df = ex[k].df
        pos = df["POS"].value_counts().sort("POS")
        print(f"{ex[k].file}: {df.height} rows; " + ", ".join(f"{p} {n}" for p, n in pos.iter_rows())
              + (f"  (unexpected positions: {sorted(set(df['POS']) - set(POSITIONS))})" if set(df["POS"]) - set(POSITIONS) else ""))
        d = df.filter(pl.len().over(["NAME", "TEAM"]) > 1)
        if d.height:
            print(f"  duplicate Name+Team keys: {d.select('NAME', 'TEAM', 'POS').to_dicts()}")

    print("\n== Joins onto receiving-situation ==")
    joined, reports = join_player_files(ex["situation"].df, {k: ex[k].df for k in PLAYER_FILES[1:]})
    for r in reports:
        print(f"{FILES[r.file]['file']}: {r.by_team} by Name+Team, {r.by_pos} by Name+POS, "
              f"{len(r.unmatched_base)} situation rows unmatched, {len(r.unmatched_other)} {r.file} rows unmatched")
        for u in r.unmatched_base:
            print(f"    situation only: {u}")
        for u in r.unmatched_other:
            print(f"    {r.file} only: {u}")

    print("\n== Consistency checks ==")
    j = joined
    for a, b in [("OVERALL_RTE", "SEP_OVERALL_RTE"), ("OVERALL_RTE", "ALIGN_OVERALL_RTE"), ("MAN_RTE", "SEP_MAN_RTE"), ("ZONE_RTE", "SEP_ZONE_RTE")]:
        diff = j.filter((pl.col(a) - pl.col(b)).abs() > 0)
        print(f"{a} vs {b}: {j.height - diff.height - j[b].null_count()} equal, {diff.height} differ"
              + (f" (max diff {(diff[a] - diff[b]).abs().max():.0f}; e.g. {diff.select('NAME', a, b).head(3).to_dicts()})" if diff.height else ""))
    cz = j.with_columns((pl.col("C2_RTE") + pl.col("C3_RTE") + pl.col("C4_RTE") + pl.col("C6_RTE")).alias("_cz"))
    bad = cz.filter((pl.col("_cz") - pl.col("SEP_ZONE_RTE")).abs() > 0)
    print(f"Cover 2+3+4+6 routes = Zone routes: {cz.height - bad.height}/{cz.height} rows"
          + (f"; mismatches e.g. {bad.select('NAME', '_cz', 'SEP_ZONE_RTE').head(3).to_dicts()}" if bad.height else ""))
    al = j.with_columns(sum(pl.col(f"{g}_ROUTE_SHARE").fill_null(0) for g in ("WIDE", "SLOT", "INLINE", "BACK")).alias("_s"))
    print(f"Wide+Slot+Inline+Backfield route shares: min {al['_s'].min():.1f}, max {al['_s'].max():.1f}")
    print(f"Man+Zone routes / overall routes (situation): median {(j['MAN_RTE'] + j['ZONE_RTE']).sum() / j['OVERALL_RTE'].sum():.3f}; "
          f"Single-High+Two-High: {(j['SINGLE_HIGH_RTE'] + j['TWO_HIGH_RTE']).sum() / j['OVERALL_RTE'].sum():.3f}")

    cov = ex["coverage"].df.with_columns(pl.col("NAME").alias("team"))
    dfn = ex["defense"].df.select(pl.col("NAME").alias("team"), "MAN_PCT", "ZONE_PCT", "ONE_HIGH_PCT")
    c = cov.join(dfn, on="team", suffix="_TD")
    worst = max((c[a] - c[f"{b}_TD" if b == a else b]).abs().max() for a, b in [("MAN_PCT", "MAN_PCT"), ("ZONE_PCT", "ZONE_PCT"), ("ONE_HI_PCT", "ONE_HIGH_PCT")])
    print(f"team-defense MAN/ZONE/1-HIGH vs coverage-matrix: max difference {worst:.2f} pts (tolerance {COVERAGE_AGREE_TOL})")
    zs = c.with_columns((pl.col("COVER_2_PCT") + pl.col("COVER_3_PCT") + pl.col("COVER_4_PCT") + pl.col("COVER_6_PCT") - pl.col("ZONE_PCT")).alias("_z"),
                        (pl.col("COVER_0_PCT") + pl.col("COVER_1_PCT") + pl.col("COVER_2_MAN_PCT") - pl.col("MAN_PCT")).alias("_m"),
                        (pl.col("MAN_PCT") + pl.col("ZONE_PCT")).alias("_mz"))
    print(f"Cover 2+3+4+6 - ZONE %: {zs['_z'].min():+.1f} to {zs['_z'].max():+.1f};  Cover 0+1+2M - MAN %: {zs['_m'].min():+.1f} to {zs['_m'].max():+.1f};  MAN+ZONE: {zs['_mz'].min():.1f} to {zs['_mz'].max():.1f}")

    exp = sorted({e.exported_at for e in ex.values()})
    print(f"\nData as of: {exp[-1]} UTC (exports span {exp[0]} to {exp[-1]})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inspect", action="store_true", help="load and check the exports, print what was parsed, write nothing")
    args = ap.parse_args()
    try:
        if args.inspect:
            return inspect()
        print("Only --inspect is implemented so far.")
        return 2
    except (FormatError, TeamMapError) as e:
        print(f"STOPPED: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
