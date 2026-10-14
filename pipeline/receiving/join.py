"""
Joins the three player files onto receiving-situation (the base).

Tier 1: Name + Team. Tier 2, for rows tier 1 left over: Name + POS. A key only matches when it is
unique on both sides, so two players with the same name are never guessed between. Everything left
unmatched is reported. Columns a later file shares with what is already joined (e.g. OVERALL_RTE) keep
the earlier value; the other file's copy is kept with a prefix (SEP_, ALIGN_) so the two can be compared.
"""

from dataclasses import dataclass, field

import polars as pl

KEY_COLS = ["NAME", "TEAM", "POS"]
DROP = {"SEASON", "RANK", "G"}
PREFIX = {"separation": "SEP_", "alignment": "ALIGN_"}


@dataclass
class JoinReport:
    file: str
    base_rows: int
    other_rows: int
    by_team: int = 0
    by_pos: int = 0
    unmatched_base: list[dict] = field(default_factory=list)
    unmatched_other: list[dict] = field(default_factory=list)


def _unique_keys(df: pl.DataFrame, keys: list[str]) -> pl.DataFrame:
    return df.filter(pl.len().over(keys) == 1)


def join_player_files(base: pl.DataFrame, others: dict[str, pl.DataFrame]) -> tuple[pl.DataFrame, list[JoinReport]]:
    out = base.with_row_index("_row")
    reports = []
    for key, df in others.items():
        p = PREFIX[key]
        rename = {c: (f"{p}{c}" if c in out.columns else c) for c in df.columns if c not in KEY_COLS and c not in DROP}
        other = df.select(KEY_COLS + list(rename)).rename(rename).with_row_index("_orow")
        rep = JoinReport(file=key, base_rows=base.height, other_rows=df.height)

        # Tier 1: Name + Team
        t1 = _unique_keys(out.select("_row", "NAME", "TEAM"), ["NAME", "TEAM"]).join(
            _unique_keys(other.select("_orow", "NAME", "TEAM"), ["NAME", "TEAM"]), on=["NAME", "TEAM"])
        # Tier 2: Name + POS among rows tier 1 didn't match
        rest_b = out.select("_row", "NAME", "POS").filter(~pl.col("_row").is_in(t1["_row"].implode()))
        rest_o = other.select("_orow", "NAME", "POS").filter(~pl.col("_orow").is_in(t1["_orow"].implode()))
        t2 = _unique_keys(rest_b, ["NAME", "POS"]).join(_unique_keys(rest_o, ["NAME", "POS"]), on=["NAME", "POS"])
        rep.by_team, rep.by_pos = t1.height, t2.height

        pairs = pl.concat([t1.select("_row", "_orow"), t2.select("_row", "_orow")])
        matched_o = pairs["_orow"].implode()
        rep.unmatched_base = out.filter(~pl.col("_row").is_in(pairs["_row"].implode())).select(KEY_COLS).to_dicts()
        rep.unmatched_other = other.filter(~pl.col("_orow").is_in(matched_o)).select(KEY_COLS).to_dicts()

        out = out.join(pairs, on="_row", how="left").join(other.drop(KEY_COLS), on="_orow", how="left").drop("_orow")
        reports.append(rep)
    return out.drop("_row"), reports
