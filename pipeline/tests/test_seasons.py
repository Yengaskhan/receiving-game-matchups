import sys
from pathlib import Path

import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from receiving.seasons import combine_allowed, combine_coverage, combine_players, rekey_to_current  # noqa: E402


def test_combine_players_sums_counts_and_route_weights_rates():
    df = pl.DataFrame({
        "NAME": ["A", "A"], "TEAM": ["DET", "DET"], "POS": ["WR", "WR"], "SEASON": [2025.0, 2026.0], "G": [17.0, 5.0],
        "OVERALL_RTE": [400.0, 100.0], "OVERALL_YPRR": [2.0, 3.0], "MAN_RTE": [100.0, 0.0], "MAN_YPRR": [2.5, 0.0],
        "WIDE_RTE": [300.0, 50.0], "SLOT_RTE": [100.0, 50.0], "WIDE_ROUTE_SHARE": [75.0, 50.0], "SLOT_ROUTE_SHARE": [25.0, 50.0],
    })
    r = combine_players(df, ["NAME", "TEAM", "POS"]).row(0, named=True)
    assert r["G"] == 22 and r["OVERALL_RTE"] == 500
    assert r["OVERALL_YPRR"] == pytest.approx((400 * 2 + 100 * 3) / 500)   # same as summed yards / summed routes
    assert r["MAN_YPRR"] == pytest.approx(2.5)                              # weighted by MAN routes, so 0-route season adds nothing
    assert r["WIDE_ROUTE_SHARE"] == pytest.approx(350 / 500 * 100)          # recomputed from routes
    assert r["SEASON"] is None


def test_rekey_gives_current_team_and_drops_missing_players():
    prior = pl.DataFrame({"NAME": ["A", "B", "C"], "TEAM": ["MIA", "KC", "NYJ"], "POS": ["WR", "TE", "WR"], "G": [17.0, 17.0, 3.0],
                          "OVERALL_RTE": [500.0, 300.0, 50.0]})
    cur = pl.DataFrame({"NAME": ["A", "B"], "TEAM": ["DET", "KC"], "POS": ["WR", "TE"], "G": [5.0, 5.0], "OVERALL_RTE": [150.0, 90.0]})
    out, dropped = rekey_to_current(prior, cur)
    assert dict(zip(out["NAME"], out["TEAM"])) == {"A": "DET", "B": "KC"}
    assert [d["NAME"] for d in dropped] == ["C"]


def test_rekey_combines_a_traded_player_first():
    prior = pl.DataFrame({"NAME": ["A", "A"], "TEAM": ["MIA", "NYJ"], "POS": ["WR", "WR"], "G": [8.0, 9.0],
                          "OVERALL_RTE": [200.0, 250.0], "OVERALL_YPRR": [1.0, 2.0]})
    cur = pl.DataFrame({"NAME": ["A"], "TEAM": ["DET"], "POS": ["WR"], "G": [5.0], "OVERALL_RTE": [150.0], "OVERALL_YPRR": [1.5]})
    out, _ = rekey_to_current(prior, cur)
    r = out.row(0, named=True)
    assert out.height == 1 and r["TEAM"] == "DET" and r["G"] == 17 and r["OVERALL_YPRR"] == pytest.approx((200 + 500) / 450)


def test_combine_coverage_weights_shares_by_dropbacks():
    a = pl.DataFrame({"NAME": ["X"], "G": [17.0], "DB": [600.0], "MAN_PCT": [20.0], "FP_DB_MAN": [0.5], "BLITZ_PCT": [30.0]})
    b = pl.DataFrame({"NAME": ["X"], "G": [5.0], "DB": [200.0], "MAN_PCT": [40.0], "FP_DB_MAN": [0.9]})
    r = combine_coverage([a, b]).row(0, named=True)
    assert r["DB"] == 800 and r["MAN_PCT"] == pytest.approx((600 * 20 + 200 * 40) / 800)
    # FP per man dropback: weighted by man dropbacks (120 and 80)
    assert r["FP_DB_MAN"] == pytest.approx((120 * 0.5 + 80 * 0.9) / 200)
    assert "BLITZ_PCT" not in r  # only in one season


def test_combine_allowed_recomputes_per_game():
    cols = {"RANK": [1.0], "TEAM": ["X"], "G": [17.0]}
    for g in ("OUTER", "SLOT", "LWR", "RWR"):
        cols.update({f"{g}_{m}": [v] for m, v in [("TGT", 100.0), ("REC", 60.0), ("YDS", 800.0), ("TD", 5.0), ("INT", 2.0), ("RATE", 90.0),
                                                   ("YPG", 47.0), ("FP", 170.0), ("FPG", 10.0), ("FP_RK", 1.0), ("FP_T", 1.7)]})
    a = pl.DataFrame(cols)
    b = a.with_columns(pl.lit(5.0).alias("G"), pl.lit(60.0).alias("SLOT_FP"))
    r = combine_allowed([a, b]).row(0, named=True)
    assert r["G"] == 22 and r["SLOT_FP"] == 230 and r["SLOT_FPG"] == pytest.approx(230 / 22)
