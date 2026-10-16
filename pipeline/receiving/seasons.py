"""
Seasons: which data a view is built from, and how seasons are put together.

A view ("basis") is one of:
  <current season>   the current exports only (data/raw/*.csv)                     - the default
  <prior season>     a prior season's exports (data/raw/<season>/*.csv)
  total              every season above, combined

Every view scores the same current-week schedule, so players are always keyed to their CURRENT team:
a prior-season row is matched to this season's player by Name + POS (unique on both sides), takes his
current team, and players who aren't in this season's exports are left out (logged). A player with two
rows in one season (traded) is combined into one first.

Combining (players): counts add up (G, routes, targets, yards, TD, air yards); every rate is re-made as
a route-weighted average using the routes of its own split (e.g. MAN_YPRR by MAN_RTE), which is the same
as recomputing it from the summed counts; each alignment's share of routes is recomputed from routes.
Combining (teams): games and dropbacks add up; coverage shares are weighted by dropbacks; FP per dropback
vs a coverage is weighted by the dropbacks in that coverage; team-defense rates are weighted by dropbacks;
points allowed are summed and per-game / per-target figures recomputed. Columns that are not in every
season's export (e.g. the Blitz group that only some coverage-matrix exports have) are dropped from a
combined view.
"""

from dataclasses import replace

import polars as pl

from .load import Export, FormatError

PLAYER_KEY = ["NAME", "POS"]
COUNT_SUFFIXES = ("_RTE", "_TGT", "_REC", "_YDS", "_TD", "_AY")
ALIGN_GROUPS = ("WIDE", "SLOT", "INLINE", "BACK")
FP_DB_SHARE = {"FP_DB_MAN": "MAN_PCT", "FP_DB_ZONE": "ZONE_PCT", "FP_DB_1HI": "ONE_HI_PCT", "FP_DB_2HI": "TWO_HI_PCT",
               "FP_DB_BLITZ": "BLITZ_PCT", "FP_DB_NOBLITZ": "NO_BLITZ_PCT"}
TEAM_DEFENSE_SUMS = {"PF", "PA", "DIFF", "TO_PLUS_MINUS", "PLAYS", "DR", "EPA", "TO", "SACKS", "PEN", "PEN_YDS", "PEN_EPA"}
ALLOWED_GROUPS = ("OUTER", "SLOT", "LWR", "RWR")


def _wmean(col: str, w: pl.Expr) -> pl.Expr:
    """Weighted mean ignoring nulls; null when no weight."""
    num = (pl.col(col) * w).filter(pl.col(col).is_not_null()).sum()
    den = w.filter(pl.col(col).is_not_null()).sum()
    return pl.when(den > 0).then(num / den).otherwise(None)


def _routes_col(col: str, cols: set[str]) -> str:
    """The routes column behind a player-file rate: the longest <prefix>_RTE that exists."""
    parts = col.split("_")
    for i in range(len(parts) - 1, 0, -1):
        cand = "_".join(parts[:i]) + "_RTE"
        if cand in cols:
            return cand
    return "OVERALL_RTE"


def combine_players(df: pl.DataFrame, key: list[str]) -> pl.DataFrame:
    """Rows sharing `key` (e.g. one player's seasons, or a traded player's teams) into one row."""
    cols = set(df.columns)
    aggs = []
    for c in df.columns:
        if c in key:
            continue
        if c in ("SEASON", "RANK"):
            aggs.append(pl.lit(None, dtype=df.schema[c]).alias(c))
        elif df.schema[c] == pl.Utf8:
            aggs.append(pl.col(c).drop_nulls().last().alias(c))
        elif c == "G" or c.endswith(COUNT_SUFFIXES):
            aggs.append(pl.col(c).sum().alias(c))
        elif c.endswith("_ROUTE_SHARE"):
            continue  # recomputed below
        else:
            aggs.append(_wmean(c, pl.col(_routes_col(c, cols)).fill_null(0)).alias(c))
    out = df.group_by(key, maintain_order=True).agg(aggs)
    shares = [g for g in ALIGN_GROUPS if f"{g}_ROUTE_SHARE" in cols]
    if shares:
        tot = sum(pl.col(f"{g}_RTE").fill_null(0) for g in shares)
        out = out.with_columns([pl.when(tot > 0).then(100 * pl.col(f"{g}_RTE").fill_null(0) / tot).otherwise(None).alias(f"{g}_ROUTE_SHARE")
                                for g in shares])
    # The exports show 0 (not blank) for a split with no routes; keep that.
    num = [c for c in df.columns if c not in key and df.schema[c] != pl.Utf8 and c not in ("SEASON", "RANK")]
    return out.with_columns([pl.col(c).fill_null(0.0) for c in num]).select(df.columns)


def rekey_to_current(prior: pl.DataFrame, current: pl.DataFrame) -> tuple[pl.DataFrame, list[dict]]:
    """Give each prior-season player his current team (Name + POS match); drop players not in the current season."""
    prior = combine_players(prior, PLAYER_KEY + ["TEAM"]) if prior.select(PLAYER_KEY + ["TEAM"]).is_duplicated().any() else prior
    prior = combine_players(prior, PLAYER_KEY) if prior.select(PLAYER_KEY).is_duplicated().any() else prior
    cur = current.select(PLAYER_KEY + [pl.col("TEAM").alias("_CUR")]).filter(pl.len().over(PLAYER_KEY) == 1)
    out = prior.join(cur, on=PLAYER_KEY, how="left")
    dropped = out.filter(pl.col("_CUR").is_null()).select("NAME", "TEAM", "POS").to_dicts()
    out = out.filter(pl.col("_CUR").is_not_null()).with_columns(pl.col("_CUR").alias("TEAM")).drop("_CUR")
    return out, dropped


def _common(frames: list[pl.DataFrame]) -> list[str]:
    cols = [c for c in frames[0].columns if all(c in f.columns for f in frames)]
    return cols


def combine_coverage(frames: list[pl.DataFrame]) -> pl.DataFrame:
    cols = _common(frames)
    df = pl.concat([f.select(cols) for f in frames], how="vertical_relaxed")
    aggs = []
    for c in cols:
        if c == "NAME":
            continue
        if c in ("SEASON", "RANK"):
            aggs.append(pl.lit(None, dtype=df.schema[c]).alias(c))
        elif c in ("G", "DB"):
            aggs.append(pl.col(c).sum().alias(c))
        elif c in FP_DB_SHARE and FP_DB_SHARE[c] in cols:
            aggs.append(_wmean(c, pl.col("DB") * pl.col(FP_DB_SHARE[c]) / 100).alias(c))
        else:
            aggs.append(_wmean(c, pl.col("DB")).alias(c))
    return df.group_by("NAME", maintain_order=True).agg(aggs).select(cols)


def combine_defense(frames: list[pl.DataFrame], dropbacks: list[pl.DataFrame]) -> pl.DataFrame:
    """team-defense seasons; rates weighted by each season's dropbacks (from that season's coverage matrix)."""
    cols = _common(frames)
    parts = [f.select(cols).join(db.select("NAME", pl.col("DB").alias("_W")), on="NAME", how="left") for f, db in zip(frames, dropbacks)]
    df = pl.concat(parts, how="vertical_relaxed")
    aggs = []
    for c in cols:
        if c == "NAME":
            continue
        if c in ("SEASON", "RANK") or df.schema[c] == pl.Utf8:
            aggs.append(pl.lit(None, dtype=df.schema[c]).alias(c))
        elif c == "G" or c in TEAM_DEFENSE_SUMS:
            aggs.append(pl.col(c).sum().alias(c))
        else:
            aggs.append(_wmean(c, pl.col("_W")).alias(c))
    return df.group_by("NAME", maintain_order=True).agg(aggs).select(cols)


def combine_allowed(frames: list[pl.DataFrame]) -> pl.DataFrame:
    cols = _common(frames)
    df = pl.concat([f.select(cols) for f in frames], how="vertical_relaxed")
    aggs = [pl.col("G").sum().alias("G"), pl.lit(None, dtype=df.schema["RANK"]).alias("RANK")]
    for g in ALLOWED_GROUPS:
        for m in ("TGT", "REC", "YDS", "TD", "INT", "FP"):
            aggs.append(pl.col(f"{g}_{m}").sum().alias(f"{g}_{m}"))
        aggs.append(_wmean(f"{g}_RATE", pl.col(f"{g}_TGT")).alias(f"{g}_RATE"))
    if "SLOT_SLOT_PCT" in cols:
        aggs.append(_wmean("SLOT_SLOT_PCT", pl.col("G")).alias("SLOT_SLOT_PCT"))
    out = df.group_by("TEAM", maintain_order=True).agg(aggs)
    fix = []
    for g in ALLOWED_GROUPS:
        fix += [(pl.col(f"{g}_FP") / pl.col("G")).alias(f"{g}_FPG"), (pl.col(f"{g}_YDS") / pl.col("G")).alias(f"{g}_YPG"),
                pl.when(pl.col(f"{g}_TGT") > 0).then(pl.col(f"{g}_FP") / pl.col(f"{g}_TGT")).otherwise(None).alias(f"{g}_FP_T")]
    out = out.with_columns(fix)
    out = out.with_columns([pl.col(f"{g}_FPG").rank("ordinal", descending=True).cast(pl.Float64).alias(f"{g}_FP_RK") for g in ALLOWED_GROUPS])
    return out.select(cols)


def combine_exports(seasons: list[dict[str, Export]]) -> dict[str, Export]:
    """One combined Export per file from several seasons' Exports (players already re-keyed)."""
    out = {}
    for key in seasons[0]:
        es = [s[key] for s in seasons]
        frames = [e.df for e in es]
        if key in ("situation", "separation", "alignment"):
            cols = _common(frames)
            df = combine_players(pl.concat([f.select(cols) for f in frames], how="vertical_relaxed"), PLAYER_KEY + ["TEAM"])
        elif key == "coverage":
            df = combine_coverage(frames)
        elif key == "defense":
            df = combine_defense(frames, [s["coverage"].df for s in seasons])
        elif key == "points_allowed":
            df = combine_allowed(frames)
        else:
            raise FormatError(f"don't know how to combine {key}")
        out[key] = replace(es[0], df=df, league_avg={}, exported_at=max(e.exported_at for e in es),
                           headers={c: es[0].headers.get(c, ("", c)) for c in df.columns})
    return out
