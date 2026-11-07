"""
One-time build of data/nflverse/coverage_types_<season>.csv: each WR/TE's routes, targets and receiving
yards against every coverage type (Cover 0, 1, 2, 2 Man, 3, 4, 6) for a finished season, from nflverse.

    python pipeline/build_coverage_types.py --season 2025

Why a separate script: nflverse publishes play-level coverage types (participation data) only after a
season ends, so this is built once per finished season and committed. The weekly pipeline just reads
the small CSV, with no play-by-play download.

Method
  plays     regular-season pass attempts (no sacks, no two-point tries) with a coverage type
  routes    nflverse lists who was on the field, not who ran a route, so a player's on-field plays are
            scaled by his route rate: his Data Suite routes for the season / his on-field pass plays
            (capped at 1). This removes the plays where a TE stayed in to block.
  targets   plays where he was the targeted receiver; yards = receiving yards on those plays
Only players in that season's Data Suite receiving-situation export (WR/TE, by player_id) are kept.
"""

import argparse
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))

from receiving.config import RAW_DIR, ROOT  # noqa: E402
from receiving.load import read_export  # noqa: E402

TYPES = {"COVER_0": "C0", "COVER_1": "C1", "COVER_2": "C2", "2_MAN": "C2M", "COVER_3": "C3", "COVER_4": "C4", "COVER_6": "C6"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=int, required=True)
    args = ap.parse_args()
    import nflreadpy as nfl

    ds = read_export("situation", RAW_DIR / str(args.season)).df
    if "PLAYER_ID" not in ds.columns:
        raise SystemExit(f"data/raw/{args.season}/receiving-situation.csv has no player_id column.")
    ds = ds.filter(pl.col("PLAYER_ID").is_not_null()).select(
        pl.col("PLAYER_ID").alias("player_id"), pl.col("OVERALL_RTE").alias("ds_routes"))

    pbp = nfl.load_pbp([args.season]).filter(
        (pl.col("season_type") == "REG") & (pl.col("pass_attempt") == 1) & (pl.col("sack") != 1)
        & (pl.col("two_point_attempt") != 1)
    ).select(pl.col("game_id"), pl.col("play_id").cast(pl.Float64), "receiver_player_id",
             pl.col("receiving_yards").fill_null(0.0))
    part = nfl.load_participation([args.season]).select(
        pl.col("nflverse_game_id").alias("game_id"), pl.col("play_id").cast(pl.Float64), "offense_players", "defense_coverage_type")
    plays = pbp.join(part, on=["game_id", "play_id"], how="inner")
    on_field = plays.with_columns(pl.col("offense_players").str.split(";").alias("player_id")).explode("player_id")
    on_field = on_field.filter(pl.col("player_id").str.len_chars() > 0)

    # Route rate from all pass plays (labelled or not), then counts on plays with a coverage type.
    rate = (on_field.group_by("player_id").agg(pl.len().alias("on_field"))
            .join(ds, on="player_id", how="inner")
            .with_columns(pl.min_horizontal(pl.col("ds_routes") / pl.col("on_field"), pl.lit(1.0)).alias("route_rate")))
    typed = on_field.filter(pl.col("defense_coverage_type").is_in(list(TYPES))).with_columns(
        pl.col("defense_coverage_type").replace_strict(TYPES).alias("cov"),
        (pl.col("receiver_player_id") == pl.col("player_id")).fill_null(False).alias("is_tgt"))
    out = (typed.join(rate.select("player_id", "route_rate"), on="player_id", how="inner")
           .group_by("player_id", "cov").agg(
               (pl.len() * pl.col("route_rate").first()).alias("rte"),
               pl.col("is_tgt").sum().alias("tgt"),
               pl.when(pl.col("is_tgt")).then(pl.col("receiving_yards")).otherwise(0.0).sum().alias("yds"))
           .with_columns(pl.col("rte").round(1))
           .sort("player_id", "cov"))
    dest = ROOT / "data" / "nflverse" / f"coverage_types_{args.season}.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.write_csv(dest)
    print(f"{out['player_id'].n_unique()} players, {out.height} rows -> {dest.relative_to(ROOT)}; "
          f"{plays.height} pass plays, {typed.select('game_id', 'play_id').unique().height} with a coverage type")
    return 0


if __name__ == "__main__":
    sys.exit(main())
