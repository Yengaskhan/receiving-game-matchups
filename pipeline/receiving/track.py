"""
Track record: how the published Matchup Scores did once the games were played.

For every published week file (data/<season>/<season>/week-XX.json) before the current week, each
scored player (50+ routes) is compared with his actual receiving PPR points that week (nflverse weekly
player stats: receptions + 0.1 x yards + 6 x TDs, the same scoring as Data Suite FP/RR).

  normal week   his projection without the matchup: proj / (1 + delta), i.e. his adjusted FP per route
                x his routes per game
  beat          actual points > normal week
  vs normal     sum of actual points / sum of normal-week points - 1, per score band

Only players who were on the field (nflverse snap counts, offensive snaps > 0) in a game that started
after the week file's data was exported count, so a score is never graded on a game it already saw.
Written to data/<season>/track-record.json.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl

# The site's score bands: good or great matchup (58+), neutral (43-57), tough or very tough (42 or less).
BANDS = [("good", "Good matchups (58+)", 58, 100), ("neutral", "Neutral (43-57)", 43, 57), ("tough", "Tough matchups (42 or less)", 0, 42)]
MIN_ROUTES = 50


def kickoff_utc(gameday: str, gametime: str | None) -> datetime:
    # nflverse times are US Eastern; +5h (EST) is close enough to order kickoffs against an export time.
    t = datetime.strptime(f"{gameday} {gametime or '13:00'}", "%Y-%m-%d %H:%M")
    return (t + timedelta(hours=5)).replace(tzinfo=timezone.utc)


def load_actuals(season: int) -> tuple[dict[tuple[str, int], float], set[tuple[str, int]]]:
    """(player_id, week) -> receiving PPR points, and the (player_id, week) pairs with offensive snaps."""
    import nflreadpy as nfl

    ps = nfl.load_player_stats([season])
    if "season_type" in ps.columns:
        ps = ps.filter(pl.col("season_type") == "REG")
    ps = ps.with_columns((pl.col("receptions").fill_null(0) + 0.1 * pl.col("receiving_yards").fill_null(0)
                          + 6 * pl.col("receiving_tds").fill_null(0)).alias("fp"))
    fp = {(r["player_id"], r["week"]): r["fp"] for r in ps.select("player_id", "week", "fp").iter_rows(named=True)}
    ids = nfl.load_players().select("gsis_id", "pfr_id").drop_nulls()
    pfr = {r["pfr_id"]: r["gsis_id"] for r in ids.iter_rows(named=True)}
    sc = nfl.load_snap_counts([season]).filter(pl.col("offense_snaps") > 0)
    played = {(pfr[r["pfr_player_id"]], r["week"]) for r in sc.select("pfr_player_id", "week").iter_rows(named=True) if r["pfr_player_id"] in pfr}
    return fp, played


def band_stats(rows: list[dict]) -> list[dict]:
    out = []
    for key, label, lo, hi in BANDS:
        rs = [r for r in rows if lo <= r["score"] <= hi]
        normal = sum(r["normal"] for r in rs)
        out.append({"key": key, "label": label, "n": len(rs),
                    "beat": round(sum(r["actual"] > r["normal"] for r in rs) / len(rs), 4) if rs else None,
                    "vs_normal": round(sum(r["actual"] for r in rs) / normal - 1, 4) if normal > 0 else None})
    return out


def build_track_record(root: Path, season: int, current_week: int, slug_to_id: dict[str, str]) -> dict:
    wdir = root / str(season) / str(season)
    fp, played = load_actuals(season)
    weeks, all_rows = [], {}
    for f in sorted(wdir.glob("week-*.json")):
        wk = json.loads(f.read_text())
        week = wk["week"]
        if week >= current_week:
            continue
        as_of = datetime.strptime(wk["data_as_of"][:16], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        upcoming = {g["game_id"] for g in wk["games"] if kickoff_utc(g["gameday"], g.get("gametime")) > as_of}
        version = wk.get("model_version", 1)
        rows = []
        for r in wk["rows"]:
            if r["routes"] < MIN_ROUTES or r["game_id"] not in upcoming or r.get("delta") is None:
                continue
            pid = r.get("player_id") or slug_to_id.get(r["player"])
            if not pid or (pid, week) not in played:
                continue
            normal = r["proj"] / (1 + r["delta"])
            rows.append({"player": r["player"], "name": r["name"], "team": r["team"], "pos": r["pos"], "opponent": r["opponent"],
                         "score": r["score"], "normal": round(normal, 2), "proj": round(r["proj"], 2), "actual": round(fp.get((pid, week), 0.0), 2)})
        if not rows:
            continue
        rows.sort(key=lambda r: -r["score"])
        weeks.append({"week": week, "model_version": version, "data_as_of": wk["data_as_of"], "generated_at": wk.get("generated_at"),
                      "graded_games": len(upcoming), "n": len(rows), "bands": band_stats(rows), "rows": rows})
        all_rows.setdefault(version, []).extend(rows)
    overall = [{"model_version": v, "weeks": [w["week"] for w in weeks if w["model_version"] == v], "n": len(rs), "bands": band_stats(rs)}
               for v, rs in sorted(all_rows.items())]
    return {"season": season, "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "min_routes": MIN_ROUTES, "bands": [{"key": k, "label": lab} for k, lab, _, _ in BANDS],
            "overall": overall, "weeks": sorted(weeks, key=lambda w: -w["week"])}


def write_track_record(root: Path, season: int, current_week: int, slug_to_id: dict[str, str]) -> Path:
    tr = build_track_record(root, season, current_week, slug_to_id)
    p = root / str(season) / "track-record.json"
    # Unchanged results keep the old file (and its timestamp), so a re-run doesn't create a commit.
    if p.exists():
        old = json.loads(p.read_text())
        if {k: v for k, v in old.items() if k != "generated_at"} == {k: v for k, v in tr.items() if k != "generated_at"}:
            return p
    p.write_text(json.dumps(tr, separators=(",", ":")) + "\n")
    return p
