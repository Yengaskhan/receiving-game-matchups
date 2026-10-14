"""Team mapping: FantasyPoints codes (player files) and full names (team files) to nflverse codes."""

import csv
from dataclasses import dataclass
from pathlib import Path

from .config import TEAM_MAP


class TeamMapError(Exception):
    pass


@dataclass
class TeamMap:
    by_fp: dict[str, str]    # FantasyPoints code -> nflverse code
    by_name: dict[str, str]  # full name -> nflverse code
    names: dict[str, str]    # nflverse code -> full name

    def fp(self, code: str, where: str) -> str:
        try:
            return self.by_fp[code]
        except KeyError:
            raise TeamMapError(f"{where}: team code {code!r} is not in data/team_map.csv (fp_code).") from None

    def full(self, name: str, where: str) -> str:
        try:
            return self.by_name[name]
        except KeyError:
            raise TeamMapError(f"{where}: team name {name!r} is not in data/team_map.csv (full_name).") from None


def load_team_map(path: Path = TEAM_MAP) -> TeamMap:
    with path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    if len(rows) != 32:
        raise TeamMapError(f"{path.name}: expected 32 teams, found {len(rows)}.")
    for col in ("fp_code", "full_name", "nflverse_code"):
        vals = [r[col].strip() for r in rows]
        if len(set(vals)) != 32 or not all(vals):
            raise TeamMapError(f"{path.name}: column {col} must have 32 distinct, non-blank values.")
    return TeamMap(
        by_fp={r["fp_code"].strip(): r["nflverse_code"].strip() for r in rows},
        by_name={r["full_name"].strip(): r["nflverse_code"].strip() for r in rows},
        names={r["nflverse_code"].strip(): r["full_name"].strip() for r in rows},
    )
