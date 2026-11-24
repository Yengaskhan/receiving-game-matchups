"""
Current roles from recent games, so an injury or a depth-chart change shows up the next week.

From nflverse (weekly player stats, snap counts, injury report), for each team's last RECENT_GAMES
games before this week:
  recent targets / game   his targets in those team games / the number of team games (a missed game = 0)
  recent snap share       his offensive snap share in those team games (a missed game = 0)
  active                  he played in at least one of the team's last ACTIVE_GAMES games
  injury                  this week's injury-report status (Out / Doubtful / Questionable), if any

Roles (WR1, WR2, TE1 ...) rank recent targets per game within team and position; players who aren't
active rank last. Routes per game for the projection scale his season rate by his recent snap share vs
his snap share in the games he played this season (clamped), so a promoted player's projection rises.
Anything nflverse doesn't have falls back to the season numbers.
"""

import polars as pl

RECENT_GAMES = 3
ACTIVE_GAMES = 2
RPG_SCALE_LIMITS = (0.6, 1.4)


def recent_usage(season: int, week: int) -> dict[str, dict]:
    """player_id (gsis) -> {"tpg", "snap_recent", "snap_season", "active", "last_week", "injury"}."""
    import nflreadpy as nfl

    ps = nfl.load_player_stats([season])
    if "season_type" in ps.columns:
        ps = ps.filter(pl.col("season_type") == "REG")
    ps = ps.filter(pl.col("week") < week).select("player_id", "team", "week", pl.col("targets").fill_null(0))
    sc = nfl.load_snap_counts([season]).filter((pl.col("game_type") == "REG") & (pl.col("week") < week))
    ids = nfl.load_players().select("gsis_id", "pfr_id").drop_nulls()
    pfr = dict(zip(ids["pfr_id"].to_list(), ids["gsis_id"].to_list()))
    sc = sc.with_columns(pl.col("pfr_player_id").replace_strict(pfr, default=None).alias("player_id")).drop_nulls("player_id")

    # Each team's last RECENT_GAMES weeks with a game.
    team_weeks = sc.select("team", "week").unique()
    recent = {t: sorted(g["week"].to_list())[-RECENT_GAMES:] for (t,), g in team_weeks.group_by(["team"])}

    out: dict[str, dict] = {}
    snaps = sc.select("player_id", "team", "week", "offense_pct", "offense_snaps")
    for (pid,), g in snaps.group_by(["player_id"]):
        team = g.sort("week")["team"][-1]
        wks = recent.get(team, [])
        if not wks:
            continue
        played = g.filter(pl.col("offense_snaps") > 0)
        rec = g.filter(pl.col("week").is_in(wks) & (pl.col("team") == team))
        snap_recent = rec["offense_pct"].sum() / len(wks)
        snap_season = played["offense_pct"].mean() if played.height else None
        out[pid] = {"team": team, "snap_recent": snap_recent, "snap_season": snap_season,
                    "active": played.filter(pl.col("week").is_in(wks[-ACTIVE_GAMES:])).height > 0,
                    "last_week": played["week"].max() if played.height else None, "tpg": 0.0, "injury": None}
    tg = ps.join(pl.DataFrame({"team": list(recent), "weeks": list(recent.values())}), on="team").filter(pl.col("week").is_in(pl.col("weeks")))
    for r in tg.group_by("player_id").agg(pl.col("targets").sum(), pl.col("team").first()).iter_rows(named=True):
        if r["player_id"] in out:
            out[r["player_id"]]["tpg"] = r["targets"] / len(recent[r["team"]])

    try:
        inj = nfl.load_injuries([season]).filter((pl.col("week") == week) & pl.col("report_status").is_not_null())
        for r in inj.select("gsis_id", "report_status", "report_primary_injury").iter_rows(named=True):
            if r["gsis_id"] in out and r["report_status"] in ("Out", "Doubtful", "Questionable"):
                out[r["gsis_id"]]["injury"] = r["report_status"] + (f" ({r['report_primary_injury']})" if r["report_primary_injury"] else "")
    except Exception as e:  # the injury report is optional context
        print(f"Injury report unavailable: {e}")
    return out


def season_tgt(r: dict) -> float:
    if r.get("OVERALL_TGT") is not None:
        return r["OVERALL_TGT"]
    return (r.get("OVERALL_TPRR") or 0) * (r.get("OVERALL_RTE") or 0)


def apply_usage(players: list[dict], usage: dict[str, dict]) -> tuple[dict[tuple, str], dict[tuple, float], dict[tuple, dict]]:
    """players: current-season receiving-situation rows (NAME, TEAM, POS, G, OVERALL_RTE, OVERALL_TPRR, PLAYER_ID).
    Returns roles, routes per game and status, keyed (NAME, TEAM, POS)."""
    key = lambda r: (r["NAME"], r["TEAM"], r["POS"])  # noqa: E731
    rpg, status, groups = {}, {}, {}
    lo, hi = RPG_SCALE_LIMITS
    for r in players:
        season_rpg = r["OVERALL_RTE"] / r["G"] if r["G"] else 0.0
        u = usage.get(r.get("PLAYER_ID") or "")
        scale = 1.0
        if u and u["active"] and u["snap_season"]:
            scale = min(max(u["snap_recent"] / u["snap_season"], lo), hi)
        rpg[key(r)] = season_rpg * scale
        status[key(r)] = {"active": u["active"] if u else True, "last_week": u["last_week"] if u else None,
                          "injury": u["injury"] if u else None, "snap_recent": round(u["snap_recent"], 3) if u else None,
                          "tpg_recent": round(u["tpg"], 2) if u else None}
        team = r["TEAM"].split(",")[-1].strip()
        groups.setdefault((team, r["POS"]), []).append((r, u))
    roles = {}
    for (_t, pos), rs in groups.items():
        rs.sort(key=lambda x: (not (x[1]["active"] if x[1] else True),
                               -(x[1]["tpg"] if x[1] else 0.0),
                               -(season_tgt(x[0]) / x[0]["G"] if x[0]["G"] else 0)))
        for i, (r, _u) in enumerate(rs, start=1):
            roles[key(r)] = f"{pos}{i}"
    return roles, rpg, status
