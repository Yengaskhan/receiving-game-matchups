import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from receiving import model as M  # noqa: E402


def test_shrink():
    assert M.shrink(0.5, 60, 0.3, 60) == pytest.approx(0.4)
    assert M.shrink(0.5, 0, 0.3, 60) == 0.3          # no routes -> prior
    assert M.shrink(None, 10, 0.3, 60) == 0.3
    assert M.shrink(0.5, 1e9, 0.3, 60) == pytest.approx(0.5)


def test_split_prior_is_the_players_overall_scaled_by_league():
    # Overall 0.40, league man 0.36 vs league overall 0.35 -> prior 0.40 * 0.36 / 0.35
    prior = 0.40 * (0.36 / 0.35)
    assert M.shrink(0.60, 15, prior, 60) == pytest.approx((15 * 0.60 + 60 * prior) / 75)


def test_normalize():
    assert M.normalize({"m": 21.7, "z": 73.8}) == pytest.approx({"m": 21.7 / 95.5, "z": 73.8 / 95.5})
    assert sum(M.normalize({"a": 1, "b": 2, "c": 0}).values()) == pytest.approx(1)
    with pytest.raises(ValueError):
        M.normalize({"a": 0, "b": 0})


def test_index_and_shrink_index():
    assert M.index(0.41, 0.205) == pytest.approx(2.0)
    assert M.index(None, 0.2) is None and M.index(0.2, 0) is None
    assert M.shrink_index(1.5, 4, 4) == pytest.approx(1.25)
    assert M.shrink_index(1.5, 0, 4) == 1.0


def test_percentile():
    ref = [1, 2, 3, 4]
    assert M.percentile(0, ref) == 0 and M.percentile(5, ref) == 100
    assert M.percentile(2.5, ref) == 50
    assert M.percentile(2, ref) == pytest.approx(37.5)


def test_weighted_mean_is_route_weighted():
    assert M.weighted_mean([(1.0, 1), (0.0, 99)]) == pytest.approx(0.01)
    assert M.weighted_mean([(None, 5), (2.0, 0)]) is None


def test_ordinal():
    assert [M.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22)] == ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd"]


# ------------------------------------------------------------------------------------------------
# A league-average defense is a neutral matchup for every player.

def _league():
    rate = {s: {"FP_RR": 0.35, "YPRR": 1.5, "TPRR": 0.2} for s in ["OVERALL", "MAN", "ZONE", "SINGLE_HIGH", "TWO_HIGH"]}
    rate["MAN"]["FP_RR"] = 0.38
    sep = {s: {"WIN_RATE": 10.0, "SEP_SCORE": 0.03} for s in ["OVERALL", "MAN", "ZONE", "RZ", "C2", "C3", "C4", "C6"]}
    d = {"MAN_PCT": 22.0, "ZONE_PCT": 74.0, "ONE_HI_PCT": 50.0, "TWO_HI_PCT": 50.0, "COVER_2_PCT": 12.0, "COVER_3_PCT": 33.0,
         "COVER_4_PCT": 17.0, "COVER_6_PCT": 12.0, "FP_DB_MAN": 0.5, "FP_DB_ZONE": 0.4, "FP_DB_1HI": 0.42, "FP_DB_2HI": 0.46,
         "TE_FPG": 14.0, "WR_FPG": 32.0, "OUTER_FPG": 22.0, "SLOT_FPG": 16.0}
    zone = 12 + 33 + 17 + 12
    return M.League(rate=rate, sep=sep, pos_fp_rr={"WR": 0.36, "TE": 0.3}, defense=d,
                    zone_mix={"C2": 12 / zone, "C3": 33 / zone, "C4": 17 / zone, "C6": 12 / zone})


def _player(pos="WR"):
    p = {"POS": pos, "G": 5, "OVERALL_RTE": 150, "OVERALL_FP_RR": 0.45, "OVERALL_YPRR": 2.0, "OVERALL_TPRR": 0.25,
         "OVERALL_WIN_RATE": 12.0, "OVERALL_SEP_SCORE": 0.05, "SEP_OVERALL_RTE": 148}
    for s, n, fp, y in [("MAN", 30, 0.7, 3.0), ("ZONE", 110, 0.4, 1.7), ("SINGLE_HIGH", 75, 0.5, 2.2), ("TWO_HIGH", 75, 0.4, 1.8)]:
        p.update({f"{s}_RTE": n, f"{s}_FP_RR": fp, f"{s}_YPRR": y, f"{s}_TPRR": 0.25})
    p.update({"SEP_MAN_RTE": 30, "SEP_ZONE_RTE": 110, "RZ_RTE": 10})
    for s in ["MAN", "ZONE", "RZ", "C2", "C3", "C4", "C6"]:
        p.update({f"{s}_WIN_RATE": 15.0 if s == "C3" else 10.0, f"{s}_SEP_SCORE": 0.04})
    p.update({"C2_RTE": 20, "C3_RTE": 50, "C4_RTE": 25, "C6_RTE": 15})
    p.update({"WIDE_ROUTE_SHARE": 60.0, "SLOT_ROUTE_SHARE": 35.0, "INLINE_ROUTE_SHARE": 5.0, "BACK_ROUTE_SHARE": 0.0})
    return p


def test_league_average_defense_is_neutral():
    lg = _league()
    p = _player()
    prof = M.player_profile(p, lg)
    d = dict(lg.defense, G=5)
    a = {"OUTER_FPG": 22.0, "SLOT_FPG": 16.0, "G": 5}
    dp = M.defense_profile(d, a, lg)
    m = M.matchup(p, prof, d, dp, lg)
    assert m["fit"] == pytest.approx(1.0)
    assert m["cov_index"] == pytest.approx(1.0)
    assert m["align_index"] == pytest.approx(1.0)
    assert m["fp_rr"] == pytest.approx(prof["adj_overall"])
    assert m["proj"] == pytest.approx(30 * prof["adj_overall"])


def test_man_heavy_defense_suits_a_man_beater():
    lg = _league()
    p = _player()
    prof = M.player_profile(p, lg)
    d = dict(lg.defense, G=5, MAN_PCT=40.0, ZONE_PCT=56.0)
    dp = M.defense_profile(d, {"OUTER_FPG": 22.0, "SLOT_FPG": 16.0, "G": 5}, lg)
    assert M.matchup(p, prof, d, dp, lg)["fit"] > 1.0


def test_cover3_heavy_defense_raises_zone_fit():
    lg = _league()
    p = _player()
    prof = M.player_profile(p, lg)
    d = dict(lg.defense, G=5, COVER_3_PCT=50.0, COVER_4_PCT=10.0, COVER_6_PCT=2.0)
    dp = M.defense_profile(d, {"OUTER_FPG": 22.0, "SLOT_FPG": 16.0, "G": 5}, lg)
    assert M.zone_fit(prof, dp, lg) > 1.0


def test_te_position_uses_te_fpg_and_defense_index_is_shrunk():
    lg = _league()
    p = _player("TE")
    prof = M.player_profile(p, lg)
    d = dict(lg.defense, G=4, TE_FPG=21.0)
    dp = M.defense_profile(d, {"OUTER_FPG": 22.0, "SLOT_FPG": 16.0, "G": 4}, lg)
    m = M.matchup(p, prof, d, dp, lg)
    assert dp["align"]["TE"]["raw"] == pytest.approx(1.5)
    k = M.MODEL["k_def_games"]
    shrunk = 1 + 4 / (4 + k) * 0.5                  # 4 games: pulled toward 1.00
    assert m["pos_index"] == pytest.approx(shrunk)
    # alignment: only his inline routes (5% here) face the TE number
    assert m["align_index"] == pytest.approx(1 + 0.05 * (shrunk - 1))


def test_sep_score_index_is_a_difference():
    lg = _league()
    prof = M.player_profile(_player(), lg)
    ms = prof["splits"]["MAN"]["metrics"]["SEP_SCORE"]
    assert "index" not in ms and ms["diff"] == pytest.approx(ms["adj"] - ms["league"])


def test_low_sample_flag():
    lg = _league()
    p = _player()
    p["MAN_RTE"] = 12
    prof = M.player_profile(p, lg)
    assert prof["splits"]["MAN"]["low_sample"] and not prof["splits"]["ZONE"]["low_sample"]


# ------------------------------------------------------------------------------------------------
# The committed outputs

DATA = Path(__file__).resolve().parents[2] / "data"


@pytest.mark.skipif(not (DATA / "2026" / "index.json").exists(), reason="no outputs yet")
def test_committed_week_scores():
    idx = json.loads((DATA / "2026" / "index.json").read_text())
    w = json.loads((DATA / "2026" / "2026" / f"week-{idx['current_week']:02d}.json").read_text())
    rows = [r for r in w["rows"] if r["routes"] >= 50]
    assert rows and all(r["score"] is not None and 0 <= r["score"] <= 100 for r in rows)
    assert 45 <= sum(r["score"] for r in rows) / len(rows) <= 55


def test_score_is_a_fixed_scale_of_the_multiplier():
    assert M.score_from_ratio(1.0) == 50
    assert M.score_from_ratio(1.05) == 66
    assert M.score_from_ratio(1.10) == 79
    assert M.score_from_ratio(0.98) == 43          # a small effect stays near 50 (not ranked to the bottom)
    assert 0 <= M.score_from_ratio(0.2) < 2 and 98 < M.score_from_ratio(5.0) <= 100


def test_score_parts_add_up_to_the_multiplier():
    import math
    m = {"fit": 1.04, "align_index": 1.2, "cov_index": 0.9}
    parts = M.score_parts(m)
    ratio = (1.04 ** M.MODEL["w_fit"]) * (1.2 ** M.MODEL["w_align_allowed"]) * (0.9 ** M.MODEL["w_cov_allowed"])
    assert sum(parts.values()) == pytest.approx(math.log(ratio))


def test_coverage_fit_counts_by_confidence():
    lg = _league()
    p = _player()
    prof = M.player_profile(p, lg)
    d = dict(lg.defense, G=5, MAN_PCT=40.0, ZONE_PCT=56.0)
    dp = M.defense_profile(d, {"OUTER_FPG": 22.0, "SLOT_FPG": 16.0, "G": 5}, lg)
    a = M.matchup(p, prof, d, dp, lg)["axes"]["man_zone"]
    assert a["fit"] == pytest.approx(1 + a["conf"] * (a["fit_raw"] - 1))
    prof["edges"]["MAN"]["conf"] = 0.0          # not sure at all -> no effect
    assert M.matchup(p, prof, d, dp, lg)["axes"]["man_zone"]["fit"] == pytest.approx(1.0)


@pytest.mark.skipif(not (DATA / "2026" / "index.json").exists(), reason="no outputs yet")
def test_scores_are_centred_within_each_position():
    idx = json.loads((DATA / "2026" / "index.json").read_text())
    w = json.loads((DATA / "2026" / "2026" / f"week-{idx['current_week']:02d}.json").read_text())
    for pos in ("WR", "TE"):
        rows = [r for r in w["rows"] if r["routes"] >= 50 and r["pos"] == pos]
        assert 45 <= sum(r["score"] for r in rows) / len(rows) <= 55


def test_confidence():
    assert M.confidence(0) == pytest.approx(0)
    assert M.confidence(1.645) == pytest.approx(0.90, abs=0.001)
    assert M.confidence(-1.96) == pytest.approx(0.95, abs=0.001)


def test_yprr_route_variance():
    # 20% targeted, 2.0 YPRR -> 10 yards per target, SD 14: Var = 0.2 * 100 * (1 + 1.96) - 4
    assert M.yprr_route_var(0.2, 2.0) == pytest.approx(0.2 * 100 * (1 + M.MODEL["ypt_cv"] ** 2) - 4)
    assert M.yprr_route_var(0, 1.0) is None


def test_split_edge_needs_volume():
    lg = _league()
    big = _player()
    small = _player()
    for k in ("MAN_RTE", "ZONE_RTE"):
        small[k] = big[k] / 10
    e_big = M.split_edges(big, lg)["MAN"]
    e_small = M.split_edges(small, lg)["MAN"]
    # Same rates, 10x the routes -> much more confident; MAN and ZONE are mirror images.
    assert e_big["conf"] > e_small["conf"]
    assert e_big["z"] > 0 and M.split_edges(big, lg)["ZONE"]["z"] == pytest.approx(-e_big["z"])


def test_coverage_edge_only_when_real_and_heavily_used():
    lg = _league()
    p = _player()
    prof = M.player_profile(p, lg)
    prof["edges"]["MAN"].update(z=2.5, conf=M.confidence(2.5))
    d = dict(lg.defense)
    ranks = {col: {"X": 1} for _, col, _ in M.USAGE_COLS}
    assert [e["cov"] for e in M.coverage_edges(prof, d, ranks, "X", lg) if e["cov"] == "MAN"] == ["MAN"]
    ranks["MAN_PCT"]["X"] = 6                       # not a top-5 man defense -> no flag
    assert not [e for e in M.coverage_edges(prof, d, ranks, "X", lg) if e["cov"] == "MAN"]
