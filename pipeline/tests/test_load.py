import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from receiving import config  # noqa: E402
from receiving.load import FormatError, build_names, ident, read_export  # noqa: E402
from receiving.teams import load_team_map  # noqa: E402

FOOTER = "Exported from Data Suite 2.0 by someone (user 1) on 2026-10-14 22:06 UTC"


def write(tmp: Path, name: str, lines: list[str]) -> Path:
    (tmp / name).write_text("\n".join(lines) + "\n")
    return tmp


def test_ident():
    assert ident("FP/RR") == "FP_RR"
    assert ident("PRESS % (ANY)") == "PRESS_PCT_ANY"
    assert ident("+1 Rate") == "PLUS1_RATE"
    assert ident("TO +/-") == "TO_PLUS_MINUS"
    assert ident("1-HIGH %") == "ONE_HIGH_PCT"
    assert ident("TO 2-HI %") == "TO_TWO_HI_PCT"


def test_grouped_names_are_unique_and_order_free():
    spec = {"naming": "grouped"}
    g = ["", "Player Details", "Man", "Man", "Cover 3", "Zone"]
    s = ["Season", "Name", "RTE", "FP/RR", "WIN RATE", "RTE"]
    assert build_names(g, s, spec, "f") == ["SEASON", "NAME", "MAN_RTE", "MAN_FP_RR", "C3_WIN_RATE", "ZONE_RTE"]
    # Reordered columns give the same names, reordered.
    order = [5, 2, 0, 4, 1, 3]
    assert build_names([g[i] for i in order], [s[i] for i in order], spec, "f") == ["ZONE_RTE", "MAN_RTE", "SEASON", "C3_WIN_RATE", "NAME", "MAN_FP_RR"]


def test_unknown_group_gets_its_own_prefix():
    assert build_names(["Vs Blitz"], ["FP/RR"], {"naming": "grouped"}, "f") == ["VS_BLITZ_FP_RR"]


def test_flat_duplicates_fail_without_a_rule():
    with pytest.raises(FormatError, match="repeat"):
        build_names(["A", "B"], ["FP/DB", "FP/DB"], {"naming": "flat"}, "f")


def test_follows_names_repeated_columns_by_their_rate():
    spec = config.FILES["coverage"]
    names = build_names(["x"] * 4, ["ZONE %", "FP/DB", "MAN %", "FP/DB"], spec, "f")
    assert names == ["ZONE_PCT", "FP_DB_ZONE", "MAN_PCT", "FP_DB_MAN"]
    with pytest.raises(FormatError, match="should follow"):
        build_names(["x"] * 2, ["DB", "FP/DB"], spec, "f")


def test_double_header_league_avg_and_footer(tmp_path, monkeypatch):
    monkeypatch.setitem(config.FILES, "t", {"file": "t.csv", "naming": "grouped", "league_avg": ("NAME", "League Avg"),
                                            "required": ["NAME", "TEAM", "MAN_RTE", "ZONE_RTE"]})
    write(tmp_path, "t.csv", [
        ",Player Details,Player Details,Man,Zone",
        "Season,Name,Team,RTE,RTE",
        "2026,League Avg,,15.5,48.2",
        "2026,A One,DET,20,60",
        "2026,B Two,KC,,30",
        f"{FOOTER},,,,",
    ])
    e = read_export("t", tmp_path)
    assert e.df.height == 2
    assert e.exported_at == "2026-10-14 22:06"
    assert e.league_avg["MAN_RTE"] == 15.5
    assert e.df["MAN_RTE"].to_list() == [20.0, None]
    assert "League Avg" not in e.df["NAME"].to_list()


def test_blank_team_league_avg(tmp_path, monkeypatch):
    monkeypatch.setitem(config.FILES, "t", {"file": "t.csv", "naming": "grouped", "league_avg": ("TEAM", ""), "required": ["TEAM", "SLOT_FPG"]})
    write(tmp_path, "t.csv", ["Team,Team,SLOT", "Rank,Team,FPG", ",,15.9", "1,KC,13.8", f"{FOOTER},,"])
    e = read_export("t", tmp_path)
    assert e.df["TEAM"].to_list() == ["KC"]
    assert e.league_avg["SLOT_FPG"] == 15.9


@pytest.mark.parametrize("lines,msg", [
    (["Team,Team", "Team,FPG", ",1", "KC,2"], "footer"),
    (["Team,SLOT", "Team,YDS", ",1", "KC,2", f"{FOOTER},"], "missing expected columns"),
    (["Team,SLOT", "Team,FPG", ",1", "KC,abc", f"{FOOTER},"], "should be a number"),
    (["Team,SLOT", "Team,FPG", "KC,2", f"{FOOTER},"], "League Avg"),
])
def test_format_changes_fail_clearly(tmp_path, monkeypatch, lines, msg):
    monkeypatch.setitem(config.FILES, "t", {"file": "t.csv", "naming": "grouped", "league_avg": ("TEAM", ""), "required": ["TEAM", "SLOT_FPG"]})
    write(tmp_path, "t.csv", lines)
    with pytest.raises(FormatError, match=msg):
        read_export("t", tmp_path)


def test_team_map_covers_all_32():
    tm = load_team_map()
    assert len(tm.by_fp) == len(tm.by_name) == len(tm.names) == 32
    assert tm.by_fp["LA"] == "LA" and tm.by_fp["LAC"] == "LAC"
    assert tm.by_fp["ARZ"] == "ARI" and tm.by_fp["HST"] == "HOU"
    assert tm.by_name["Los Angeles Rams"] == "LA"
    # traded mid-season: current team is the last one listed
    assert tm.fp("ARZ, HST", "test") == "HOU"


def test_committed_exports_load():
    from receiving.load import load_all
    ex = load_all()
    # Player counts change every week; the three player files must agree, and there are always 32 teams.
    counts = {ex[k].df.height for k in config.PLAYER_FILES}
    assert len(counts) == 1 and counts.pop() > 100
    assert all(e.df.height == 32 for k, e in ex.items() if k not in config.PLAYER_FILES)


def test_team_roles_by_targets_per_game():
    import polars as pl
    from receiving.build import team_roles
    sep = pl.DataFrame({
        "NAME": ["A", "B", "C", "D", "T"], "TEAM": ["GB", "GB", "GB", "ARZ, HST", "GB"], "POS": ["WR", "WR", "WR", "WR", "TE"],
        "G": [6.0, 6.0, 1.0, 5.0, 6.0], "OVERALL_TGT": [30.0, 48.0, 12.0, 40.0, 20.0],
    })
    r = team_roles(sep)
    assert r[("B", "GB", "WR")] == "WR1" and r[("A", "GB", "WR")] == "WR2"
    assert r[("C", "GB", "WR")] == "WR3"            # 12 targets in 1 game ranks after the regulars
    assert r[("D", "ARZ, HST", "WR")] == "WR1"      # traded: ranked on his current team (HST)
    assert r[("T", "GB", "TE")] == "TE1"
