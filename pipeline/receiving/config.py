"""
Settings for the Receiving Game Matchup pipeline: input files, column naming rules and the columns
each export must have. Model weights and constants are added here with the model.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
TEAM_MAP = ROOT / "data" / "team_map.csv"
OUTPUT_DIR = ROOT / "data"
SEASON = 2026
SCHEMA_VERSION = 1

# ------------------------------------------------------------------------------------------------
# Column naming
#
# Each export has two header rows: a group ("Man", "Cover 3", "SLOT") and a sub-header ("FP/RR").
# A column's name is built from both, e.g. Man + FP/RR -> MAN_FP_RR. Groups listed in DETAIL_GROUPS
# are identity columns and get no prefix (Season, Name, Team...). Any group not in GROUP_PREFIX gets
# a prefix made from its own name, so a new group in an export still loads with a readable name.
# ------------------------------------------------------------------------------------------------

DETAIL_GROUPS = {"", "Player Details", "Team Details", "Team"}

GROUP_PREFIX = {
    "Overall": "OVERALL",
    "Man": "MAN",
    "Zone": "ZONE",
    "Single-High": "SINGLE_HIGH",
    "Two-High": "TWO_HIGH",
    "Red Zone": "RZ",
    "Cover 2": "C2",
    "Cover 3": "C3",
    "Cover 4": "C4",
    "Cover 6": "C6",
    "Wide": "WIDE",
    "Slot": "SLOT",
    "Inline": "INLINE",
    "Backfield": "BACK",
    "OUTER": "OUTER",
    "SLOT": "SLOT",
    "OUTSIDE LWR": "LWR",
    "OUTSIDE RWR": "RWR",
}

# Text swaps applied (in order) before a header is turned into an identifier.
TOKEN_SWAPS = [
    ("1-HIGH", "ONE_HIGH"),
    ("2-HIGH", "TWO_HIGH"),
    ("1-HI", "ONE_HI"),
    ("2-HI", "TWO_HI"),
    ("+/-", " PLUS_MINUS"),
    ("+", "PLUS"),
    ("%", " PCT"),
]

# ------------------------------------------------------------------------------------------------
# Files
#
# naming:
#   "grouped" - every non-detail column is GROUP_SUB (player files, points allowed: groups are splits)
#   "flat"    - sub-header only (team files: groups are just sections). Repeated sub-headers must be
#               resolved by `follows` or the load fails.
# sub_alias:  sub-header -> replacement, applied inside a group before prefixing.
# follows:    a repeated sub-header is named by the column right before it: {sub: {previous sub: name}}.
# league_avg: how to find the League Avg row: ("NAME", "League Avg") or ("TEAM", "") for a blank team.
# required:   columns the pipeline uses; a missing one stops the run with the file and column named.
# ------------------------------------------------------------------------------------------------

_SPLIT4 = ["RTE", "TPRR", "YPRR", "FP_RR"]

FILES = {
    "situation": {
        "file": "receiving-situation.csv",
        "naming": "grouped",
        "league_avg": ("NAME", "League Avg"),
        "required": ["SEASON", "NAME", "TEAM", "POS", "G"]
        + [f"{g}_{m}" for g in ("OVERALL", "MAN", "ZONE", "SINGLE_HIGH", "TWO_HIGH") for m in _SPLIT4],
    },
    "separation": {
        "file": "receiving-separation-by-coverage.csv",
        "naming": "grouped",
        "league_avg": ("NAME", "League Avg"),
        "required": ["SEASON", "NAME", "TEAM", "POS", "G"]
        + [f"OVERALL_{m}" for m in ("RTE", "SEP_SCORE", "YPRR", "TPRR", "WIN_RATE", "SEP_MS", "ADOR", "TGT_PCT",
                                     "PLUS1_RATE", "PLUS2_RATE", "PLUS3_RATE", "NEG_RATE", "TGT", "REC", "YDS", "TD", "AY")]
        + [f"{g}_{m}" for g in ("MAN", "ZONE", "RZ") for m in ("RTE", "SEP_SCORE", "YPRR", "TPRR", "WIN_RATE")]
        + [f"{g}_{m}" for g in ("C2", "C3", "C4", "C6") for m in ("RTE", "SEP_SCORE", "WIN_RATE")],
    },
    "alignment": {
        "file": "receiving-alignment.csv",
        "naming": "grouped",
        "league_avg": ("NAME", "League Avg"),
        # "WIDE RTE %" inside the Wide group is the share of his routes from that alignment.
        "sub_alias": {"WIDE RTE %": "ROUTE SHARE", "SLOT RTE %": "ROUTE SHARE", "INLINE RTE %": "ROUTE SHARE", "BACK RTE %": "ROUTE SHARE"},
        "required": ["SEASON", "NAME", "TEAM", "POS", "G"]
        + [f"OVERALL_{m}" for m in ("RTE", "TGT", "TPRR", "RTE_PCT", "YPRR")]
        + [f"{g}_{m}" for g in ("WIDE", "SLOT", "INLINE", "BACK") for m in ("RTE", "ROUTE_SHARE", "TM_RTE_PCT", "TGT", "TPRR", "RTE_PCT", "YPRR")],
    },
    "coverage": {
        "file": "coverage-matrix.csv",
        "naming": "flat",
        "league_avg": ("NAME", "League Avg"),
        "sub_alias": {"1-HI/MOF C %": "ONE_HI %", "2-HI/MOF O %": "TWO_HI %"},
        # The four FP/DB columns are PPR points allowed to WR/TE per dropback vs the coverage before them.
        "follows": {"FP/DB": {"MAN %": "FP_DB_MAN", "ZONE %": "FP_DB_ZONE", "1-HI/MOF C %": "FP_DB_1HI", "2-HI/MOF O %": "FP_DB_2HI"}},
        "required": ["SEASON", "NAME", "G", "DB", "MAN_PCT", "ZONE_PCT", "ONE_HI_PCT", "TWO_HI_PCT",
                     "FP_DB_MAN", "FP_DB_ZONE", "FP_DB_1HI", "FP_DB_2HI", "DISGUISE_PCT", "TO_ONE_HI_PCT", "TO_TWO_HI_PCT",
                     "COVER_0_PCT", "COVER_1_PCT", "COVER_2_PCT", "COVER_2_MAN_PCT", "COVER_3_PCT", "COVER_4_PCT", "COVER_6_PCT",
                     "BASE_PCT", "NICKEL_PCT", "DIME_PCT", "PRESS_PCT_ANY", "PRESS_PCT_TGT"],
    },
    "defense": {
        "file": "team-defense.csv",
        "naming": "flat",
        "league_avg": ("NAME", "League Avg"),
        "required": ["SEASON", "NAME", "G", "BLITZ_PCT", "SACK_PCT", "PRESS_PCT", "BASE_PCT", "SUB_PCT",
                     "WR_FPG", "TE_FPG", "EPA_DB", "PASS_SUCC_PCT", "PASS_EXP_PCT",
                     "MAN_PCT", "ZONE_PCT", "ONE_HIGH_PCT", "PASS_PCT", "PROE", "PACE"],
    },
    "points_allowed": {
        "file": "receiving-points-allowed.csv",
        "naming": "grouped",
        "league_avg": ("TEAM", ""),
        "required": ["TEAM", "G"]
        + [f"{g}_{m}" for g in ("OUTER", "SLOT", "LWR", "RWR") for m in ("TGT", "REC", "YDS", "TD", "INT", "RATE", "YPG", "FP", "FPG", "FP_RK", "FP_T")]
        + ["SLOT_SLOT_PCT"],
    },
}

# Columns kept as text; everything else must be numeric (blank = missing).
TEXT_COLUMNS = {"NAME", "TEAM", "POS", "W_L_T"}

# Player files are joined onto receiving-situation (the base) on Name + Team, then Name + POS.
PLAYER_FILES = ("situation", "separation", "alignment")
POSITIONS = ("WR", "TE")

# team-defense repeats coverage-matrix shares; they must agree within this many percentage points.
COVERAGE_AGREE_TOL = 0.5
