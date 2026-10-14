"""
One loader for every FantasyPoints Data Suite export.

The export format:
  row 1      group header ("Player Details", "Man", "Cover 3", "SLOT"); blank over some identity columns
  row 2      the real column header; names repeat across groups (RTE, FP/RR...)
  League Avg one row, the export's own simple per-player mean (kept for reference only)
  data rows  one per player or team
  footer     "Exported from Data Suite 2.0 by ... on 2026-10-14 22:06 UTC"

Column names are built from both header rows (see config.py), so the load does not depend on column
order. Every problem raises FormatError naming the file and what changed.
"""

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl

from .config import DETAIL_GROUPS, FILES, GROUP_PREFIX, RAW_DIR, TEXT_COLUMNS, TOKEN_SWAPS

FOOTER_RE = re.compile(r"^Exported from Data Suite.* on (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) UTC\s*$")


class FormatError(Exception):
    """An export does not look the way the pipeline expects."""


@dataclass
class Export:
    key: str
    file: str
    df: pl.DataFrame
    league_avg: dict
    exported_at: str  # "2026-10-14 22:06" (UTC)
    # column name -> (group header, sub-header) as they appear in the file
    headers: dict[str, tuple[str, str]] = field(default_factory=dict)


def ident(text: str) -> str:
    """A header as an identifier: 'FP/RR' -> 'FP_RR', 'PRESS % (ANY)' -> 'PRESS_PCT_ANY', '+1 Rate' -> 'PLUS1_RATE'."""
    s = text.strip().upper()
    for a, b in TOKEN_SWAPS:
        s = s.replace(a, b)
    s = re.sub(r"[^A-Z0-9]+", "_", s).strip("_")
    if not s:
        raise ValueError(f"empty header {text!r}")
    return f"X{s}" if s[0].isdigit() else s


def group_prefix(group: str) -> str:
    return GROUP_PREFIX.get(group.strip(), ident(group))


def build_names(groups: list[str], subs: list[str], spec: dict, file: str) -> list[str]:
    """Unique column names from the two header rows, per the file's naming rule."""
    if len(groups) != len(subs):
        raise FormatError(f"{file}: the two header rows have different lengths ({len(groups)} vs {len(subs)}).")
    alias = spec.get("sub_alias", {})
    follows = spec.get("follows", {})
    names = []
    for i, (g, s) in enumerate(zip(groups, subs)):
        g, s = g.strip(), s.strip()
        if not s:
            raise FormatError(f"{file}: column {i + 1} (group {g!r}) has a blank header.")
        if s in follows:
            prev = subs[i - 1].strip() if i else ""
            if prev not in follows[s]:
                raise FormatError(f"{file}: column {i + 1} {s!r} should follow one of {sorted(follows[s])}, but follows {prev!r}.")
            names.append(follows[s][prev])
            continue
        base = ident(alias.get(s, s))
        if spec["naming"] == "grouped" and g not in DETAIL_GROUPS:
            names.append(f"{group_prefix(g)}_{base}")
        else:
            names.append(base)
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise FormatError(f"{file}: these column names repeat after combining the two header rows: {dupes}. "
                          "The export's layout changed; update FILES in pipeline/receiving/config.py.")
    return names


def _number(v: str):
    v = v.strip()
    if v == "":
        return None
    return float(v.replace(",", ""))


def read_export(key: str, raw_dir: Path = RAW_DIR) -> Export:
    spec = FILES[key]
    path = raw_dir / spec["file"]
    if not path.exists():
        raise FormatError(f"Missing input file {path}. Export it from Data Suite with exactly this name.")
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = [r for r in csv.reader(fh)]
    rows = [r for r in rows if any(c.strip() for c in r)]
    if len(rows) < 4:
        raise FormatError(f"{spec['file']}: only {len(rows)} non-empty rows; expected two header rows, data and a footer.")

    # Footer: the last row. Parse its timestamp, then drop it.
    m = FOOTER_RE.match(rows[-1][0])
    if not m:
        raise FormatError(f"{spec['file']}: the last row should be the 'Exported from Data Suite ... UTC' footer, got {rows[-1][0][:80]!r}.")
    exported_at = m.group(1)
    groups, subs, body = rows[0], rows[1], rows[2:-1]

    names = build_names(groups, subs, spec, spec["file"])
    missing = [c for c in spec["required"] if c not in names]
    if missing:
        raise FormatError(f"{spec['file']}: missing expected columns {missing}. "
                          f"Columns found: {names}. The export's layout changed; update FILES in pipeline/receiving/config.py.")

    records = []
    for n, r in enumerate(body, start=3):
        if len(r) != len(names):
            raise FormatError(f"{spec['file']} line {n}: {len(r)} cells, expected {len(names)}.")
        rec = {}
        for col, v in zip(names, r):
            if col in TEXT_COLUMNS:
                rec[col] = v.strip()
            else:
                try:
                    rec[col] = _number(v)
                except ValueError:
                    raise FormatError(f"{spec['file']} line {n}: column {col} should be a number, got {v!r}.") from None
        records.append(rec)

    schema = {c: (pl.Utf8 if c in TEXT_COLUMNS else pl.Float64) for c in names}
    df = pl.DataFrame(records, schema=schema, orient="row")

    lcol, lval = spec["league_avg"]
    is_avg = pl.col(lcol).fill_null("") == lval
    avg = df.filter(is_avg)
    if avg.height != 1:
        raise FormatError(f"{spec['file']}: expected exactly one League Avg row ({lcol} = {lval!r}), found {avg.height}.")
    df = df.filter(~is_avg)

    return Export(key=key, file=spec["file"], df=df, league_avg=avg.row(0, named=True), exported_at=exported_at,
                  headers={c: (g.strip(), s.strip()) for c, g, s in zip(names, groups, subs)})


def load_all(raw_dir: Path = RAW_DIR) -> dict[str, Export]:
    return {k: read_export(k, raw_dir) for k in FILES}
