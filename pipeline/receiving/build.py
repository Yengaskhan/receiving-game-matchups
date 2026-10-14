"""
Assembles the site's JSON files from the loaded exports and the model.

  data/<season>/meta.json          data as of, league baselines, model settings, join log, notes
  data/<season>/players.json       every WR/TE: raw and adjusted splits, indexes, alignment, reference metrics
  data/<season>/defenses.json      every defense: coverage mix, FP allowed by coverage and alignment, context
  data/<season>/pairs/<TEAM>.json  every WR/TE vs that defense (for the Player vs Defense view)
  data/<season>/week-XX.json       the week's scheduled matchups (Slate Rankings, Defense Profiles)
  data/<season>/index.json         the weeks on disk
"""

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from . import model as M
from .config import COVERAGE_AGREE_TOL, FILES, POSITIONS, SCHEMA_VERSION
from .join import JoinReport
from .load import Export, FormatError
from .teams import TeamMap


def r4(v):
    if v is None:
        return None
    if isinstance(v, float):
        return round(v, 4)
    return v


def rnd(obj):
    if isinstance(obj, dict):
        return {k: rnd(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [rnd(v) for v in obj]
    return r4(obj)


def slug(name: str, team: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return f"{re.sub(r'[^a-z0-9]+', '-', s).strip('-')}-{team.lower()}"


# ------------------------------------------------------------------------------------------------
# Checks
# ------------------------------------------------------------------------------------------------

def check_inputs(ex: dict[str, Export], joined: pl.DataFrame, reports: list[JoinReport]) -> list[str]:
    """Stops the run (FormatError) on anything the model can't trust; returns the passed checks."""
    done = []
    for k in ("situation", "separation", "alignment"):
        bad = set(ex[k].df["POS"]) - set(POSITIONS)
        if bad:
            raise FormatError(f"{ex[k].file}: unexpected positions {sorted(bad)}; the model only handles WR and TE.")
    d = joined.filter(pl.len().over(["NAME", "TEAM"]) > 1)
    if d.height:
        raise FormatError(f"receiving-situation.csv: duplicate Name + Team rows {d.select('NAME', 'TEAM').to_dicts()}.")
    done.append(f"{joined.height} WR/TE rows, one per player and team")
    for r in reports:
        done.append(f"{FILES[r.file]['file']}: {r.by_team} matched on Name + Team, {r.by_pos} on Name + POS, "
                    f"{len(r.unmatched_base)} unmatched")

    cz = joined.select((pl.col("C2_RTE") + pl.col("C3_RTE") + pl.col("C4_RTE") + pl.col("C6_RTE") - pl.col("SEP_ZONE_RTE")).abs().max()).item()
    if cz and cz > 0:
        raise FormatError(f"receiving-separation-by-coverage.csv: Cover 2/3/4/6 routes no longer add up to Zone routes (off by up to {cz:.0f}).")
    done.append("Cover 2 + 3 + 4 + 6 routes equal Zone routes for every player")

    cov = ex["coverage"].df.select("NAME", "MAN_PCT", "ZONE_PCT", "ONE_HI_PCT")
    td = ex["defense"].df.select("NAME", pl.col("MAN_PCT").alias("m2"), pl.col("ZONE_PCT").alias("z2"), pl.col("ONE_HIGH_PCT").alias("h2"))
    c = cov.join(td, on="NAME", how="inner")
    if c.height != 32:
        raise FormatError(f"coverage-matrix.csv and team-defense.csv share only {c.height} of 32 team names.")
    worst = c.select(pl.max_horizontal((pl.col("MAN_PCT") - pl.col("m2")).abs(), (pl.col("ZONE_PCT") - pl.col("z2")).abs(),
                                       (pl.col("ONE_HI_PCT") - pl.col("h2")).abs()).max()).item()
    if worst > COVERAGE_AGREE_TOL:
        raise FormatError(f"team-defense.csv MAN/ZONE/1-HIGH % differ from coverage-matrix.csv by up to {worst:.2f} points "
                          f"(tolerance {COVERAGE_AGREE_TOL}). Are both exports from the same date?")
    done.append(f"team-defense MAN / ZONE / 1-HIGH % agree with the coverage matrix (max difference {worst:.2f} pts)")
    zs = ex["coverage"].df.select((pl.col("COVER_2_PCT") + pl.col("COVER_3_PCT") + pl.col("COVER_4_PCT") + pl.col("COVER_6_PCT") - pl.col("ZONE_PCT")).abs().max()).item()
    if zs > 1.0:
        raise FormatError(f"coverage-matrix.csv: Cover 2/3/4/6 % no longer add up to ZONE % (off by up to {zs:.1f} points).")
    done.append(f"Cover 2 + 3 + 4 + 6 % equal ZONE % within {zs:.1f} pts for every defense")
    return done


# ------------------------------------------------------------------------------------------------

def build(ex: dict[str, Export], joined: pl.DataFrame, reports: list[JoinReport], tm: TeamMap,
          season: int, week: int, games: list[dict]) -> dict:
    checks = check_inputs(ex, joined, reports)

    players = [dict(p, TEAM_NFL=tm.fp(p["TEAM"], "receiving-situation.csv")) for p in joined.to_dicts()]
    for p in players:
        p["id"] = slug(p["NAME"], p["TEAM_NFL"])
    ids = [p["id"] for p in players]
    if len(set(ids)) != len(ids):
        raise FormatError("two players share a name and team; can't give them distinct ids.")

    defenses = {}
    for d in ex["coverage"].df.to_dicts():
        defenses[tm.full(d["NAME"], "coverage-matrix.csv")] = d
    for d in ex["defense"].df.to_dicts():
        t = tm.full(d["NAME"], "team-defense.csv")
        defenses[t].update({k: v for k, v in d.items() if k not in defenses[t]})  # coverage matrix wins on shared columns
    allowed = {tm.fp(a["TEAM"], "receiving-points-allowed.csv"): a for a in ex["points_allowed"].df.to_dicts()}
    if set(allowed) != set(defenses) or len(defenses) != 32:
        raise FormatError("receiving-points-allowed.csv and coverage-matrix.csv don't cover the same 32 teams.")

    lg = M.league_baselines(players, list(defenses.values()), list(allowed.values()))
    profs = {p["id"]: M.player_profile(p, lg) for p in players}
    dprofs = {t: M.defense_profile(defenses[t], allowed[t], lg) for t in defenses}
    ranks = M.defense_ranks(defenses, dprofs, allowed)

    # Every player vs every defense (not his own team).
    pairs: dict[str, dict[str, dict]] = {t: {} for t in defenses}
    for p in players:
        for t in defenses:
            if t == p["TEAM_NFL"]:
                continue
            pairs[t][p["id"]] = M.matchup(p, profs[p["id"]], defenses[t], dprofs[t], lg)

    # The week's schedule: each team's opponent, or bye.
    opp = {}
    for g in games:
        opp[g["away"]] = (g["home"], False, g["game_id"])
        opp[g["home"]] = (g["away"], True, g["game_id"])
    byes = sorted(set(defenses) - set(opp))

    # Matchup Score: blend of standardized coverage fit and FP allowed to his position, as a percentile
    # among this week's scheduled pairs at his position (players with enough routes).
    minr = M.MODEL["score_ref_min_routes"]
    pos_of = {p["id"]: p["POS"] for p in players}
    scales = {}
    for pos in POSITIONS:
        ref_parts = [M.score_parts(pairs[opp[p["TEAM_NFL"]][0]][p["id"]]) for p in players
                     if p["POS"] == pos and p["TEAM_NFL"] in opp and p["OVERALL_RTE"] >= minr]
        if len(ref_parts) < 15:
            raise FormatError(f"only {len(ref_parts)} scheduled {pos}s with {minr}+ routes in week {week}; check the schedule.")
        scales[pos] = M.score_scale(ref_parts)
    for t, rows in pairs.items():
        for pid, m in rows.items():
            sc = scales[pos_of[pid]]
            m["parts"] = M.score_parts(m)
            m["composite"] = sc.composite(m["parts"])
            m["score"] = round(M.percentile(m["composite"], sc.ref))

    by_id = {p["id"]: p for p in players}

    def pair_out(pid: str, t: str) -> dict:
        m = pairs[t][pid]
        p = by_id[pid]
        return {
            "player": pid, "defense": t, "score": m["score"], "composite": m["composite"], "parts": m["parts"],
            "proj": m["proj"], "fp_rr": m["fp_rr"], "ratio": m["ratio"],
            "fit": m["fit"], "base_fit": m["base_fit"], "zone_fit": m["zone_fit"],
            "axes": {k: {"fit": a["fit"], "def": a["def"], "league": a["league"]} for k, a in m["axes"].items()},
            "cov_index": m["cov_index"], "align_index": m["align_index"], "align_weights": m["align_weights"],
            "reasons": M.reasons(p, profs[pid], m, t, defenses[t], dprofs[t], lg, ranks, scales[p["POS"]]),
            "flags": M.flags(p, profs[pid], t, defenses[t], lg),
        }

    pair_files = {t: {"schema": SCHEMA_VERSION, "season": season, "week": week, "defense": t,
                      "rows": [pair_out(pid, t) for pid in sorted(pairs[t], key=lambda i: -pairs[t][i]["score"])]} for t in defenses}

    # Players
    L = lg.defense
    players_out = []
    for p in sorted(players, key=lambda x: -x["OVERALL_RTE"]):
        pr = profs[p["id"]]
        o = opp.get(p["TEAM_NFL"])
        players_out.append({
            "id": p["id"], "name": p["NAME"], "team": p["TEAM_NFL"], "fp_team": p["TEAM"], "pos": p["POS"], "g": p["G"],
            "routes": p["OVERALL_RTE"], "routes_pg": p["OVERALL_RTE"] / p["G"] if p["G"] else 0,
            "opponent": o[0] if o else None, "home": o[1] if o else None,
            "overall": {"fp_rr": p["OVERALL_FP_RR"], "adj_fp_rr": pr["adj_overall"], "pos_avg": pr["pos_avg"], "yprr": p["OVERALL_YPRR"],
                        "tprr": p["OVERALL_TPRR"], "win_rate": p["OVERALL_WIN_RATE"], "sep_score": p["OVERALL_SEP_SCORE"],
                        "sep_routes": p["SEP_OVERALL_RTE"], "tgt": p["OVERALL_TGT"], "rec": p["OVERALL_REC"], "yds": p["OVERALL_YDS"],
                        "td": p["OVERALL_TD"], "ay": p["OVERALL_AY"], "tgt_pct": p["OVERALL_TGT_PCT"]},
            "splits": pr["splits"],
            "alignment": {a: {"label": lab, "share": pr["align_shares"][a], "routes": p[f"{a}_RTE"], "tgt": p[f"{a}_TGT"],
                              "tprr": p[f"{a}_TPRR"], "yprr": p[f"{a}_YPRR"]} for a, lab in M.ALIGNMENTS},
            # Undefined by the source: shown for reference, never used in a calculation.
            "reference": {"sep_ms": p["OVERALL_SEP_MS"], "ador": p["OVERALL_ADOR"], "plus1": p["OVERALL_PLUS1_RATE"],
                          "plus2": p["OVERALL_PLUS2_RATE"], "plus3": p["OVERALL_PLUS3_RATE"], "neg": p["OVERALL_NEG_RATE"]},
        })

    # Defenses
    shares = [("MAN", "Man", "MAN_PCT"), ("ZONE", "Zone", "ZONE_PCT"), ("SINGLE_HIGH", "Single-High", "ONE_HI_PCT"), ("TWO_HIGH", "Two-High", "TWO_HI_PCT"),
              ("C0", "Cover 0", "COVER_0_PCT"), ("C1", "Cover 1", "COVER_1_PCT"), ("C2M", "Cover 2 Man", "COVER_2_MAN_PCT"),
              ("C2", "Cover 2", "COVER_2_PCT"), ("C3", "Cover 3", "COVER_3_PCT"), ("C4", "Cover 4", "COVER_4_PCT"), ("C6", "Cover 6", "COVER_6_PCT")]
    ctx = [("BLITZ_PCT", "Blitz"), ("PRESS_PCT_ANY", "Press (any)"), ("PRESS_PCT_TGT", "Press (target)"), ("DISGUISE_PCT", "Disguise"),
           ("TO_ONE_HI_PCT", "Rotates to 1-high"), ("TO_TWO_HI_PCT", "Rotates to 2-high"), ("SACK_PCT", "Sack"),
           ("BASE_PCT", "Base"), ("NICKEL_PCT", "Nickel"), ("DIME_PCT", "Dime"), ("PASS_SUCC_PCT", "Pass success allowed"),
           ("PASS_EXP_PCT", "Explosive pass allowed"), ("EPA_DB", "EPA per dropback allowed")]
    defenses_out = []
    for t in sorted(defenses):
        d, a, dp = defenses[t], allowed[t], dprofs[t]
        o = opp.get(t)
        defenses_out.append({
            "team": t, "name": tm.names[t], "g": d["G"], "db": d["DB"],
            "opponent": o[0] if o else None, "home": o[1] if o else None,
            "coverage": [{"key": k, "label": lab, "pct": d[c], "league": L[c]} for k, lab, c in shares],
            "fp_db": [{"key": k, "label": lab, "value": d[c], "league": L[c], "rank": ranks[c][t]}
                      for k, lab, c in [("MAN", "Man", "FP_DB_MAN"), ("ZONE", "Zone", "FP_DB_ZONE"), ("SINGLE_HIGH", "Single-High", "FP_DB_1HI"), ("TWO_HIGH", "Two-High", "FP_DB_2HI")]],
            "alignment": [{"key": k, "label": lab, "fpg": src[c], "league": L[c], "rank": ranks[c][t]}
                          for k, lab, c, src in [("OUTER", "Outside WRs", "OUTER_FPG", a), ("LWR", "Outside left", "LWR_FPG", a), ("RWR", "Outside right", "RWR_FPG", a),
                                                 ("SLOT", "Slot WRs", "SLOT_FPG", a), ("WR", "All WRs", "WR_FPG", d), ("TE", "TEs", "TE_FPG", d)]],
            "context": [{"key": c.lower(), "label": lab, "value": d[c], "league": L[c]} for c, lab in ctx],
            # team-defense Tendencies: unclear whether they describe this defense's opponents, so display only.
            "display_only": {"pass_pct": d["PASS_PCT"], "proe": d["PROE"], "pace": d["PACE"]},
            "index": {"cov_raw": dp["cov_raw"], "cov": dp["cov_index"], "cov_axes": dp["cov_axes"], "cov_rank": ranks["cov"][t],
                      "wide": dp["align"]["WIDE"], "slot": dp["align"]["SLOT"], "te": dp["align"]["TE"]},
        })

    # The week's slate
    rows = []
    for p in players:
        o = opp.get(p["TEAM_NFL"])
        if not o:
            continue
        po = pair_out(p["id"], o[0])
        rows.append({"player": p["id"], "name": p["NAME"], "team": p["TEAM_NFL"], "pos": p["POS"], "opponent": o[0], "home": o[1],
                     "game_id": o[2], "routes": p["OVERALL_RTE"], "routes_pg": p["OVERALL_RTE"] / p["G"] if p["G"] else 0,
                     "score": po["score"], "proj": po["proj"], "fp_rr": po["fp_rr"], "adj_fp_rr": profs[p["id"]]["adj_overall"],
                     "fit": po["fit"], "cov_index": po["cov_index"], "align_index": po["align_index"], "parts": po["parts"],
                     "reasons": po["reasons"], "flags": po["flags"]})
    rows.sort(key=lambda r: (-r["score"], -r["proj"]))

    # Validation of the model output (stops the run)
    for pos in POSITIONS:
        scored = [r for r in rows if r["routes"] >= minr and r["pos"] == pos]
        if any(r["score"] is None for r in scored):
            raise FormatError(f"a {pos} with {minr}+ routes has no Matchup Score.")
        mean = sum(r["score"] for r in scored) / len(scored)
        if not 40 <= mean <= 60:
            raise FormatError(f"{pos} Matchup Scores are off-centre: mean {mean:.1f} for {minr}+ route players (expected near 50).")
        checks.append(f"{pos} Matchup Score mean {mean:.1f} across {len(scored)} scheduled {pos}s with {minr}+ routes; none blank")

    as_of = max(e.exported_at for e in ex.values())
    meta = {
        "schema": SCHEMA_VERSION, "season": season, "week": week,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_as_of": as_of, "exports": {e.file: e.exported_at for e in ex.values()},
        "model": M.MODEL,
        "league": {
            "rate": lg.rate, "sep": lg.sep, "pos_fp_rr": lg.pos_fp_rr, "defense": lg.defense, "zone_mix": lg.zone_mix,
            "export_league_avg": {e.file: {k: v for k, v in e.league_avg.items() if v not in (None, "")} for e in ex.values()},
        },
        "joins": [{"file": FILES[r.file]["file"], "by_team": r.by_team, "by_pos": r.by_pos, "unmatched_base": r.unmatched_base,
                   "unmatched_other": r.unmatched_other} for r in reports],
        "checks": checks,
    }
    week_out = {
        "schema": SCHEMA_VERSION, "season": season, "week": week, "data_as_of": as_of, "generated_at": meta["generated_at"],
        "games": games, "byes": byes, "ref_size": {pos: len(sc.ref) for pos, sc in scales.items()},
        "score_scale": {pos: {"mean": sc.mean, "sd": sc.sd} for pos, sc in scales.items()}, "rows": rows,
    }
    return {"meta": meta, "players": players_out, "defenses": defenses_out, "pairs": pair_files, "week": week_out,
            "_debug": {"rows": rows}}


def write(out: dict, root: Path, season: int, week: int) -> list[Path]:
    d = root / str(season)
    (d / "pairs").mkdir(parents=True, exist_ok=True)
    written = []

    def dump(path: Path, obj):
        path.write_text(json.dumps(rnd(obj), separators=(",", ":")) + "\n")
        written.append(path)

    dump(d / "meta.json", out["meta"])
    dump(d / "players.json", {"schema": SCHEMA_VERSION, "season": season, "week": week, "players": out["players"]})
    dump(d / "defenses.json", {"schema": SCHEMA_VERSION, "season": season, "week": week, "defenses": out["defenses"]})
    for t, obj in out["pairs"].items():
        dump(d / "pairs" / f"{t}.json", obj)
    for stale in (d / "pairs").glob("*.json"):
        if stale.stem not in out["pairs"]:
            stale.unlink()
    dump(d / f"week-{week:02d}.json", out["week"])

    weeks = []
    for f in sorted(d.glob("week-*.json")):
        r = json.loads(f.read_text())
        weeks.append({"week": r["week"], "games": len(r["games"]), "path": f"data/{season}/{f.name}", "data_as_of": r["data_as_of"],
                      "first_gameday": min((g["gameday"] for g in r["games"]), default=None),
                      "last_gameday": max((g["gameday"] for g in r["games"]), default=None)})
    idx = {"schema": SCHEMA_VERSION, "season": season, "current_week": week, "data_as_of": out["meta"]["data_as_of"], "weeks": weeks}
    (d / "index.json").write_text(json.dumps(idx, indent=1) + "\n")
    written.append(d / "index.json")
    return written
