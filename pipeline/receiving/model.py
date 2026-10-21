"""
The matchup model. Every weight and constant is in MODEL below; the README documents each formula.

Steps
  1  Shrink each player split toward the player's own overall rate, scaled by how that coverage plays
     league-wide. Shrink his overall FP/RR toward his position's average.
  2  Express each split as an index vs the league rate in that same coverage (1.00 = league average).
  3  Coverage fit (player side): his expected FP/RR given the defense's coverage mix, vs given the
     league's mix. Axes are listed in AXES, so a new split (e.g. vs blitz) is one more entry.
  4  Defense strength (defense side): FP allowed given its own coverage mix, and FP allowed to his
     alignments (WR) or to TEs, each as an index vs league, shrunk toward 1.00 by games played.
  5  Matchup-adjusted FP/RR and projection. The 0-100 Matchup Score blends man vs zone (35%), coverage
     type (25%), where he lines up (25%) and FP allowed to his position (15%), coverage parts weighted by
     confidence; each part standardized; ranked within position.
"""

from dataclasses import dataclass, field
from math import log

MODEL = {
    # Step 1: shrinkage strength, in routes. adj = (n * value + k * prior) / (n + k)
    "k_routes": {"FP_RR": 60, "YPRR": 60, "TPRR": 60, "WIN_RATE": 40, "SEP_SCORE": 40},
    "k_overall_fp_rr": 80,          # overall FP/RR toward the WR or TE average
    "low_sample_routes": 20,        # a split under this many routes is flagged in the page
    # Step 3
    "zone_detail_weight": 0.15,     # blend of the Cover 2/3/4/6 win-rate layer into coverage fit
    # Step 4: defensive indexes are shrunk toward 1.00: 1 + G / (G + k) * (index - 1)
    "k_def_games": 4,
    # Step 5: matchup FP/RR = adj overall FP/RR * fit^w1 * coverage allowed^w2 * alignment allowed^w3
    "w_fit": 1.0,
    "w_cov_allowed": 0.25,
    "w_align_allowed": 0.5,
    # Matchup Score: four parts, in this order of importance, each standardized within the week's
    # position group and ranked within position (WRs vs WRs, TEs vs TEs).
    #   man_zone       - his yards/route vs man and vs zone, weighted by this defense's man/zone mix
    #   coverage_type  - the same for single-high vs two-high, plus his Cover 2/3/4/6 win rates
    #   alignment      - FP the defense allows where he lines up (outside / slot / inline)
    #   position       - FP the defense allows to his position (WRs or TEs)
    # Both coverage parts are multiplied by how confident we are his gap is real ("Is it real?"), so a
    # gap built on a handful of routes counts for little and a proven one counts in full.
    "score_weights": {"man_zone": 0.35, "coverage_type": 0.25, "alignment": 0.25, "position": 0.15},
    # Within coverage_type: weight of the Cover 2/3/4/6 layer next to single-high vs two-high.
    "zone_type_weight": 0.5,
    # Each part's standardized value is capped at +/- this many SDs, so one outlier (e.g. the league's
    # worst pass defense) can't outweigh the others.
    "score_z_cap": 2.0,
    # Reference set: the week's scheduled pairs at his position whose player has at least this many routes
    "score_ref_min_routes": 50,
    # Reasons: at most this many, and only contributors worth at least this much of the score (z units)
    "max_reasons": 3,
    "reason_min_effect": 0.05,
    # Coverage fit compares his yards per route by coverage. YPRR (not FP/RR) because it also counts the
    # routes where the QB doesn't look his way, and it doesn't swing on touchdowns.
    "fit_metric": "YPRR",
    # "Is it real?" test for coverage splits. Yards on one target vary around their mean with this
    # coefficient of variation (incompletions are 0; catches vary about as much as their mean): about
    # 1.4 for an NFL target. Edges at or above `edge_conf` confidence are called real.
    "ypt_cv": 1.4,
    "edge_conf": 0.90,
    # Slate flag: a real edge (or weakness) in a coverage this week's opponent plays at a top-N rate.
    "edge_usage_rank": 5,
    # Context flags (no score impact): a defense rate this many points above/below league is flagged
    "flag_pts": {"BLITZ_PCT": 5.0, "PRESS_PCT_ANY": 5.0, "DISGUISE_PCT": 5.0},
    "rz_win_index": 1.20,           # red-zone win-rate index at or above this is flagged ...
    "rz_min_routes": 15,            # ... when he has at least this many red-zone routes
}

# Coverage splits used for player rates. (key, label, source file prefix)
RATE_SPLITS = [("MAN", "Man"), ("ZONE", "Zone"), ("SINGLE_HIGH", "Single-High"), ("TWO_HIGH", "Two-High")]
SEP_SPLITS = [("MAN", "Man"), ("ZONE", "Zone"), ("RZ", "Red Zone"), ("C2", "Cover 2"), ("C3", "Cover 3"), ("C4", "Cover 4"), ("C6", "Cover 6")]
RATE_METRICS = ["FP_RR", "YPRR", "TPRR"]       # receiving-situation
SEP_METRICS = ["WIN_RATE", "SEP_SCORE"]        # receiving-separation-by-coverage
ZONE_COVERS = [("C2", "COVER_2_PCT", "Cover 2"), ("C3", "COVER_3_PCT", "Cover 3"), ("C4", "COVER_4_PCT", "Cover 4"), ("C6", "COVER_6_PCT", "Cover 6")]

# Step 3 axes: each pairs player FP/RR splits with the defense's usage of those coverages.
# To add a split later (e.g. vs blitz / no blitz), add an axis with its player columns and defense shares.
AXES = [
    {"key": "man_zone", "label": "Man/Zone", "sides": [("MAN", "MAN_PCT", "man"), ("ZONE", "ZONE_PCT", "zone")]},
    {"key": "shell", "label": "Shell", "sides": [("SINGLE_HIGH", "ONE_HI_PCT", "single-high"), ("TWO_HIGH", "TWO_HI_PCT", "two-high")]},
]
# Step 4: FP allowed per dropback by coverage (coverage-matrix), on the same axes.
ALLOWED_AXES = [
    {"key": "man_zone", "sides": [("MAN_PCT", "FP_DB_MAN"), ("ZONE_PCT", "FP_DB_ZONE")]},
    {"key": "shell", "sides": [("ONE_HI_PCT", "FP_DB_1HI"), ("TWO_HI_PCT", "FP_DB_2HI")]},
]
ALIGNMENTS = [("WIDE", "Wide"), ("SLOT", "Slot"), ("INLINE", "Inline"), ("BACK", "Backfield")]


# ------------------------------------------------------------------------------------------------
# Small maths (unit-tested)
# ------------------------------------------------------------------------------------------------

def shrink(value: float | None, n: float | None, prior: float, k: float) -> float:
    """(n * value + k * prior) / (n + k). A split with no routes is the prior."""
    n = n or 0.0
    if value is None or n <= 0:
        return prior
    return (n * value + k * prior) / (n + k)


def normalize(weights: dict[str, float]) -> dict[str, float]:
    """Scale non-negative weights to sum to 1 (the remainder of the plays is spread pro rata)."""
    tot = sum(max(w or 0.0, 0.0) for w in weights.values())
    if tot <= 0:
        raise ValueError(f"weights sum to zero: {weights}")
    return {k: max(w or 0.0, 0.0) / tot for k, w in weights.items()}


def index(value: float | None, league: float | None) -> float | None:
    """value / league rate for the same coverage. 1.00 = league average."""
    if value is None or not league:
        return None
    return value / league


def shrink_index(idx: float, games: float, k: float) -> float:
    """Pull a defensive index toward 1.00 by games played: 1 + G / (G + k) * (idx - 1)."""
    return 1.0 + (games / (games + k)) * (idx - 1.0)


def weighted_mean(pairs: list[tuple[float | None, float | None]]) -> float | None:
    """Route-weighted mean of (value, routes)."""
    num = sum(v * n for v, n in pairs if v is not None and n)
    den = sum(n for v, n in pairs if v is not None and n)
    return num / den if den else None


def percentile(x: float, ref: list[float]) -> float:
    """Mid-rank percentile of x in ref, 0-100."""
    below = sum(1 for r in ref if r < x)
    equal = sum(1 for r in ref if r == x)
    return 100.0 * (below + 0.5 * equal) / len(ref)


def ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


# ------------------------------------------------------------------------------------------------
# League baselines
# ------------------------------------------------------------------------------------------------

@dataclass
class League:
    rate: dict[str, dict[str, float]]      # split -> metric -> route-weighted league rate (situation; "OVERALL" too)
    sep: dict[str, dict[str, float]]       # split -> metric -> route-weighted league rate (separation; "OVERALL" too)
    pos_fp_rr: dict[str, float]            # WR / TE overall FP/RR, route-weighted
    defense: dict[str, float] = field(default_factory=dict)  # dropback- or game-weighted defense rates
    zone_mix: dict[str, float] = field(default_factory=dict)  # league Cover 2/3/4/6 share of zone


def league_baselines(players: list[dict], defenses: list[dict], allowed: list[dict]) -> League:
    rate = {s: {m: weighted_mean([(p[f"{s}_{m}"], p[f"{s}_RTE"]) for p in players]) for m in RATE_METRICS}
            for s in ["OVERALL"] + [k for k, _ in RATE_SPLITS]}
    sep_splits = ["OVERALL"] + [k for k, _ in SEP_SPLITS]
    sep = {s: {m: weighted_mean([(p[f"{s}_{m}"], p[sep_routes_col(s)]) for p in players]) for m in SEP_METRICS}
           for s in sep_splits}
    pos = {pos: weighted_mean([(p["OVERALL_FP_RR"], p["OVERALL_RTE"]) for p in players if p["POS"] == pos]) for pos in ("WR", "TE")}

    db = lambda col: weighted_mean([(d[col], d["DB"]) for d in defenses])  # noqa: E731
    dcols = ["MAN_PCT", "ZONE_PCT", "ONE_HI_PCT", "TWO_HI_PCT", "COVER_0_PCT", "COVER_1_PCT", "COVER_2_PCT", "COVER_2_MAN_PCT",
             "COVER_3_PCT", "COVER_4_PCT", "COVER_6_PCT", "DISGUISE_PCT", "TO_ONE_HI_PCT", "TO_TWO_HI_PCT", "BASE_PCT", "NICKEL_PCT",
             "DIME_PCT", "PRESS_PCT_ANY", "PRESS_PCT_TGT", "BLITZ_PCT", "SACK_PCT", "SUB_PCT", "EPA_DB", "PASS_SUCC_PCT", "PASS_EXP_PCT"]
    league_def = {c: db(c) for c in dcols}
    # FP allowed per dropback vs a coverage: weighted by dropbacks in that coverage.
    for share, fp in [("MAN_PCT", "FP_DB_MAN"), ("ZONE_PCT", "FP_DB_ZONE"), ("ONE_HI_PCT", "FP_DB_1HI"), ("TWO_HI_PCT", "FP_DB_2HI")]:
        league_def[fp] = weighted_mean([(d[fp], d["DB"] * d[share] / 100) for d in defenses])
    # Fantasy points allowed per game: total points / total games.
    for col in ("WR_FPG", "TE_FPG"):
        league_def[col] = sum(d[col] * d["G"] for d in defenses) / sum(d["G"] for d in defenses)
    for g in ("OUTER", "SLOT", "LWR", "RWR"):
        league_def[f"{g}_FPG"] = sum(a[f"{g}_FP"] for a in allowed) / sum(a["G"] for a in allowed)
    zone = sum(league_def[c] for _, c, _ in ZONE_COVERS)
    zone_mix = {k: league_def[c] / zone for k, c, _ in ZONE_COVERS}
    return League(rate=rate, sep=sep, pos_fp_rr=pos, defense=league_def, zone_mix=zone_mix)


def sep_routes_col(split: str) -> str:
    """Route count behind a separation-file split. Overall/Man/Zone route columns also exist in
    receiving-situation, so the join keeps the separation file's copy as SEP_<split>_RTE."""
    return f"SEP_{split}_RTE" if split in ("OVERALL", "MAN", "ZONE") else f"{split}_RTE"


# ------------------------------------------------------------------------------------------------
# Steps 1-2: player profile
# ------------------------------------------------------------------------------------------------

def player_profile(p: dict, lg: League) -> dict:
    """Raw and adjusted splits, league rates, indexes and low-sample flags for one player."""
    low = MODEL["low_sample_routes"]
    k = MODEL["k_routes"]
    pos_avg = lg.pos_fp_rr[p["POS"]]
    adj_overall = shrink(p["OVERALL_FP_RR"], p["OVERALL_RTE"], pos_avg, MODEL["k_overall_fp_rr"])

    splits = {}
    for s, label in RATE_SPLITS:
        n = p[f"{s}_RTE"]
        ms = {}
        for m in RATE_METRICS:
            lo, ls = lg.rate["OVERALL"][m], lg.rate[s][m]
            own = adj_overall if m == "FP_RR" else p[f"OVERALL_{m}"]
            prior = own * (ls / lo)
            adj = shrink(p[f"{s}_{m}"], n, prior, k[m])
            ms[m] = {"raw": p[f"{s}_{m}"], "adj": adj, "league": ls, "index": index(adj, ls)}
        splits[s] = {"label": label, "routes": n, "low_sample": (n or 0) < low, "metrics": ms}

    for s, label in SEP_SPLITS:
        n = p[sep_routes_col(s)]
        ent = splits.setdefault(s, {"label": label, "routes": n, "low_sample": (n or 0) < low, "metrics": {}})
        ent["sep_routes"] = n
        ent["sep_low_sample"] = (n or 0) < low
        for m in SEP_METRICS:
            col = f"{s}_{m}"
            lo, ls = lg.sep["OVERALL"][m], lg.sep[s][m]
            own = p[f"OVERALL_{m}"]
            if m == "SEP_SCORE":
                # Separation score sits near zero and can be negative, so a ratio is meaningless: the
                # prior is shifted (not scaled) and the "index" is the difference from league.
                prior = own + (ls - lo)
                adj = shrink(p[col], n, prior, k[m])
                ms = {"raw": p[col], "adj": adj, "league": ls, "diff": adj - ls}
            else:
                prior = own * (ls / lo) if lo else own
                adj = shrink(p[col], n, prior, k[m])
                ms = {"raw": p[col], "adj": adj, "league": ls, "index": index(adj, ls)}
            ent["metrics"][m] = ms

    prof_edges = split_edges(p, lg)
    shares = normalize({a: p[f"{a}_ROUTE_SHARE"] for a, _ in ALIGNMENTS}) if any(p[f"{a}_ROUTE_SHARE"] for a, _ in ALIGNMENTS) else {"WIDE": 0.0, "SLOT": 0.0, "INLINE": 0.0, "BACK": 0.0}
    return {"adj_overall": adj_overall, "pos_avg": pos_avg, "splits": splits, "align_shares": shares, "edges": prof_edges}


# ------------------------------------------------------------------------------------------------
# "Is it real?" Significance of a player's coverage splits
# ------------------------------------------------------------------------------------------------

def norm_cdf(z: float) -> float:
    from math import erf, sqrt
    return 0.5 * (1 + erf(z / sqrt(2)))


def confidence(z: float) -> float:
    """Two-sided: 0.90 means a gap this big would show up by chance only 10% of the time."""
    return 2 * norm_cdf(abs(z)) - 1


def yprr_route_var(tprr: float, yprr: float) -> float | None:
    """Variance of yards on a single route: targeted with probability t, then yards with mean
    ypt = yprr / t and SD = cv * ypt. Var = t * ypt^2 * (1 + cv^2) - yprr^2."""
    if not tprr or not yprr or tprr <= 0:
        return None
    ypt = yprr / tprr
    return max(tprr * ypt * ypt * (1 + MODEL["ypt_cv"] ** 2) - yprr * yprr, 1e-9)


def index_gap_z(v1: float, n1: float, l1: float, v2: float, n2: float, l2: float, var1: float, var2: float) -> float | None:
    """z for (v1 / l1) - (v2 / l2): his index in one coverage minus his index in the other, where each
    side's rate has per-route variance var over n routes."""
    if not n1 or not n2 or n1 <= 0 or n2 <= 0:
        return None
    se = ((var1 / n1) / l1 ** 2 + (var2 / n2) / l2 ** 2) ** 0.5
    return (v1 / l1 - v2 / l2) / se if se > 0 else None


def split_edges(p: dict, lg: League) -> dict[str, dict]:
    """For each coverage: is he really better (or worse) in it than in its opposite?

    Man vs zone and single-high vs two-high compare yards per route (raw, not shrunk). Under "no real
    difference", both sides share his overall per-route yards variance, so that is used for both.
    Cover 2 / 3 / 4 / 6 have only win rate: each is compared with his win rate in the rest of his zone
    routes (a two-proportion test on his pooled zone win rate). Indexes are vs league in each coverage,
    so league-wide differences between coverages don't count as his edge."""
    out: dict[str, dict] = {}
    var = yprr_route_var(p["OVERALL_TPRR"], p["OVERALL_YPRR"])
    labels = dict(RATE_SPLITS)
    for a, b in (("MAN", "ZONE"), ("SINGLE_HIGH", "TWO_HIGH")):
        la, lb = lg.rate[a]["YPRR"], lg.rate[b]["YPRR"]
        z = index_gap_z(p[f"{a}_YPRR"], p[f"{a}_RTE"], la, p[f"{b}_YPRR"], p[f"{b}_RTE"], lb, var, var) if var else None
        for side, other, sign in ((a, b, 1), (b, a, -1)):
            zz = None if z is None else sign * z
            out[side] = {"metric": "YPRR", "vs": labels[other], "vs_key": other,
                         "idx": p[f"{side}_YPRR"] / lg.rate[side]["YPRR"], "vs_idx": p[f"{other}_YPRR"] / lg.rate[other]["YPRR"],
                         "routes": p[f"{side}_RTE"], "vs_routes": p[f"{other}_RTE"],
                         "z": zz, "conf": 0.0 if zz is None else confidence(zz)}

    zone_n = sum(p[f"{c}_RTE"] or 0 for c, _, _ in ZONE_COVERS)
    zone_w = sum((p[f"{c}_RTE"] or 0) * (p[f"{c}_WIN_RATE"] or 0) for c, _, _ in ZONE_COVERS) / 100
    pz = zone_w / zone_n if zone_n else 0
    for c, _, label in ZONE_COVERS:
        n1 = p[f"{c}_RTE"] or 0
        n2 = zone_n - n1
        w1 = (p[f"{c}_WIN_RATE"] or 0) / 100
        w2 = (zone_w - n1 * w1) / n2 if n2 > 0 else 0
        l1 = lg.sep[c]["WIN_RATE"] / 100
        # league win rate on the rest of zone: route-weighted over the other covers
        rest = [(lg.sep[o]["WIN_RATE"] / 100, (p[f"{o}_RTE"] or 0)) for o, _, _ in ZONE_COVERS if o != c]
        l2 = sum(v * n for v, n in rest) / sum(n for _, n in rest) if sum(n for _, n in rest) else lg.sep["ZONE"]["WIN_RATE"] / 100
        v = pz * (1 - pz)
        z = index_gap_z(w1, n1, l1, w2, n2, l2, v, v) if 0 < pz < 1 else None
        out[c] = {"metric": "WIN_RATE", "vs": "his other zone coverages", "vs_key": "ZONE",
                  "idx": w1 / l1 if l1 else None, "vs_idx": w2 / l2 if l2 else None, "routes": n1, "vs_routes": n2,
                  "z": z, "conf": 0.0 if z is None else confidence(z)}
    return out


def coverage_edges(prof: dict, d: dict, cov_ranks: dict[str, dict[str, int]], team: str, lg: League) -> list[dict]:
    """Real edges or weaknesses (confidence >= edge_conf) in coverages this defense plays at a top-N rate."""
    L = lg.defense
    out = []
    for key, col, label in USAGE_COLS:
        e = prof["edges"].get(key)
        r = cov_ranks[col][team]
        if not e or e["z"] is None or r > MODEL["edge_usage_rank"] or e["conf"] < MODEL["edge_conf"]:
            continue
        good = e["z"] > 0
        metric = "yards/route" if e["metric"] == "YPRR" else "win rate"
        rank_txt = "most in the NFL" if r == 1 else f"{ordinal(r)} most"
        out.append({
            "cov": key, "label": label, "edge": good, "conf": e["conf"], "rank": r, "pct": d[col], "league": L[col],
            "text": (f"{label}: {e['idx']:.2f}x league {metric} vs {e['vs_idx']:.2f}x vs {e['vs'].lower()} "
                     f"({e['conf'] * 100:.0f}% confident). {team} plays it {rank_txt} ({d[col]:.0f}%, league {L[col]:.0f}%)."),
        })
    out.sort(key=lambda x: (-x["conf"]))
    return out


USAGE_COLS = [("MAN", "MAN_PCT", "Man"), ("ZONE", "ZONE_PCT", "Zone"), ("SINGLE_HIGH", "ONE_HI_PCT", "Single-high"),
              ("TWO_HIGH", "TWO_HI_PCT", "Two-high"), ("C2", "COVER_2_PCT", "Cover 2"), ("C3", "COVER_3_PCT", "Cover 3"),
              ("C4", "COVER_4_PCT", "Cover 4"), ("C6", "COVER_6_PCT", "Cover 6")]


def usage_ranks(defenses: dict[str, dict]) -> dict[str, dict[str, int]]:
    """Rank 1 = plays that coverage on the highest share of dropbacks."""
    out = {}
    for _, col, _ in USAGE_COLS:
        vals = {t: d[col] for t, d in defenses.items()}
        out[col] = {t: _rank_desc(v, list(vals.values())) for t, v in vals.items()}
    return out


# ------------------------------------------------------------------------------------------------
# Step 4: defense profile
# ------------------------------------------------------------------------------------------------

def defense_profile(d: dict, a: dict, lg: League) -> dict:
    """Coverage-weighted FP allowed and alignment / TE FP allowed, as raw and shrunk indexes."""
    kg = MODEL["k_def_games"]
    L = lg.defense
    axes = {}
    for ax in ALLOWED_AXES:
        w = normalize({fp: d[share] for share, fp in ax["sides"]})
        exp = sum(w[fp] * d[fp] for fp in w)
        lw = normalize({fp: L[share] for share, fp in ax["sides"]})
        lexp = sum(lw[fp] * L[fp] for fp in lw)
        axes[ax["key"]] = {"allowed": exp, "league": lexp, "index": exp / lexp}
    cov_raw = sum(x["index"] for x in axes.values()) / len(axes)
    g = d["G"]
    align = {}
    for key, col in [("WIDE", "OUTER_FPG"), ("SLOT", "SLOT_FPG")]:
        raw = a[col] / L[col]
        align[key] = {"fpg": a[col], "league": L[col], "raw": raw, "index": shrink_index(raw, a["G"], kg)}
    te_raw = d["TE_FPG"] / L["TE_FPG"]
    align["TE"] = {"fpg": d["TE_FPG"], "league": L["TE_FPG"], "raw": te_raw, "index": shrink_index(te_raw, g, kg)}
    wr_raw = d["WR_FPG"] / L["WR_FPG"]
    align["WR"] = {"fpg": d["WR_FPG"], "league": L["WR_FPG"], "raw": wr_raw, "index": shrink_index(wr_raw, g, kg)}
    return {
        "cov_axes": axes,
        "cov_raw": cov_raw,
        "cov_index": shrink_index(cov_raw, g, kg),
        "align": align,
        "mix": normalize({"MAN": d["MAN_PCT"], "ZONE": d["ZONE_PCT"]}),
        "shell": normalize({"SINGLE_HIGH": d["ONE_HI_PCT"], "TWO_HIGH": d["TWO_HI_PCT"]}),
        "zone_mix": normalize({k: d[c] for k, c, _ in ZONE_COVERS}),
    }


# ------------------------------------------------------------------------------------------------
# Steps 3 and 5: one player vs one defense
# ------------------------------------------------------------------------------------------------

def axis_expectation(prof: dict, ax: dict, shares: dict[str, float]) -> float:
    w = normalize({s: shares[c] for s, c, _ in ax["sides"]})
    return sum(w[s] * prof["splits"][s]["metrics"][MODEL["fit_metric"]]["adj"] for s in w)


def zone_fit(prof: dict, dprof: dict, lg: League, confidence_weighted: bool = False) -> float:
    """Cover 2/3/4/6 win-rate indexes weighted by the defense's zone mix, vs weighted by the league's.
    confidence_weighted: each index is pulled toward 1.00 by how unsure we are his gap there is real."""
    idx = {k: prof["splits"][k]["metrics"]["WIN_RATE"]["index"] or 1.0 for k, _, _ in ZONE_COVERS}
    if confidence_weighted:
        idx = {k: 1 + prof["edges"][k]["conf"] * (v - 1) for k, v in idx.items()}
    num = sum(dprof["zone_mix"][k] * idx[k] for k in idx)
    den = sum(lg.zone_mix[k] * idx[k] for k in idx)
    return num / den


def matchup(p: dict, prof: dict, d: dict, dprof: dict, lg: League) -> dict:
    L = lg.defense
    axes = {}
    for ax in AXES:
        e_def = axis_expectation(prof, ax, d)
        e_lg = axis_expectation(prof, ax, L)
        # A player with no yards at all has no coverage profile: neutral fit.
        axes[ax["key"]] = {"def": e_def, "league": e_lg, "fit": e_def / e_lg if e_lg > 0 else 1.0}
    base_fit = sum(a["fit"] for a in axes.values()) / len(axes)
    zf = zone_fit(prof, dprof, lg)
    lam = MODEL["zone_detail_weight"]
    fit = (1 - lam) * base_fit + lam * zf
    # The same fit in yards per route gained (or lost) vs a league-average coverage mix. The score uses
    # this, so a receiver who barely produces can't post a big "edge" from tiny numbers.
    e_lg = sum(a["league"] for a in axes.values()) / len(axes)
    cov_yards = (fit - 1) * e_lg

    # Where he lines up: wide routes face the outside corners, slot routes the slot, inline routes are
    # covered like a TE; backfield is neutral. Same for WRs and TEs, weighted by his route shares.
    sh = prof["align_shares"]
    aparts = {"WIDE": dprof["align"]["WIDE"]["index"], "SLOT": dprof["align"]["SLOT"]["index"], "INLINE": dprof["align"]["TE"]["index"], "BACK": 1.0}
    w = {k: sh[k] for k in aparts}
    if sum(w.values()) <= 0:
        w = {"WIDE": 0.0, "SLOT": 0.0, "INLINE": 1.0, "BACK": 0.0} if p["POS"] == "TE" else {"WIDE": 1.0, "SLOT": 0.0, "INLINE": 0.0, "BACK": 0.0}
    w = normalize(w)
    align_idx = sum(w[k] * aparts[k] for k in aparts)
    align_parts = w
    pos_idx = dprof["align"]["TE" if p["POS"] == "TE" else "WR"]["index"]

    # Score parts. Coverage parts are in yards per route gained vs a league-average mix (so tiny producers
    # can't post big edges), times confidence that his gap is real.
    edges = prof["edges"]
    conf_mz = edges["MAN"]["conf"] if edges["MAN"]["z"] is not None else 0.0
    conf_sh = edges["SINGLE_HIGH"]["conf"] if edges["SINGLE_HIGH"]["z"] is not None else 0.0
    zf_conf = zone_fit(prof, dprof, lg, confidence_weighted=True)
    mz, shl = axes["man_zone"], axes["shell"]
    parts = {
        "man_zone": conf_mz * (mz["def"] - mz["league"]),
        "coverage_type": conf_sh * (shl["def"] - shl["league"]) + MODEL["zone_type_weight"] * (zf_conf - 1) * e_lg,
        "alignment": log(align_idx),
        "position": log(pos_idx),
    }

    ratio = (fit ** MODEL["w_fit"]) * (dprof["cov_index"] ** MODEL["w_cov_allowed"]) * (align_idx ** MODEL["w_align_allowed"])
    fp_rr = prof["adj_overall"] * ratio
    # Routes per game: his current-season role (RPG, set for prior / total views), else this data's.
    rpg = p.get("RPG") if p.get("RPG") is not None else (p["OVERALL_RTE"] / p["G"] if p["G"] else 0.0)
    return {
        "axes": axes, "base_fit": base_fit, "zone_fit": zf, "fit": fit, "cov_yards": cov_yards, "e_league": e_lg,
        "cov_index": dprof["cov_index"], "align_index": align_idx, "align_weights": align_parts, "pos_index": pos_idx,
        "parts": parts, "conf_mz": conf_mz, "conf_sh": conf_sh, "zone_fit_conf": zf_conf,
        "ratio": ratio, "fp_rr": fp_rr, "routes_pg": rpg, "proj": rpg * fp_rr,
    }


# ------------------------------------------------------------------------------------------------
# Reasons and flags
# ------------------------------------------------------------------------------------------------

def _rank_desc(value: float, values: list[float]) -> int:
    return 1 + sum(1 for v in values if v > value)


def _rank_phrase(r: int, n: int, most: str = "most", least: str = "fewest") -> str:
    if r == 1:
        return f"{most} in the NFL"
    if r == n:
        return f"{least} in the NFL"
    if r <= n / 2:
        return f"{ordinal(r)} {most}"
    return f"{ordinal(n - r + 1)} {least}"


def score_parts(m: dict) -> dict[str, float]:
    """The parts of the Matchup Score (0 = league-neutral), computed in matchup()."""
    return m["parts"]


@dataclass
class ScoreScale:
    """Mean and spread of each score part over a position's reference set, and the reference composites."""
    mean: dict[str, float]
    sd: dict[str, float]
    ref: list[float]

    def z(self, part: str, value: float) -> float:
        cap = MODEL["score_z_cap"]
        return max(-cap, min(cap, (value - self.mean[part]) / self.sd[part]))

    def composite(self, parts: dict[str, float]) -> float:
        w = MODEL["score_weights"]
        return sum(w[k] * self.z(k, parts[k]) for k in w)

    def per_log(self, part: str) -> float:
        """Score units (z) per unit of this part (yards per route for coverage, log for the others)."""
        return MODEL["score_weights"][part] / self.sd[part]


def score_scale(ref_parts: list[dict[str, float]]) -> ScoreScale:
    keys = list(MODEL["score_weights"])
    mean = {k: sum(p[k] for p in ref_parts) / len(ref_parts) for k in keys}
    sd = {k: (sum((p[k] - mean[k]) ** 2 for p in ref_parts) / len(ref_parts)) ** 0.5 or 1.0 for k in keys}
    sc = ScoreScale(mean=mean, sd=sd, ref=[])
    sc.ref = sorted(sc.composite(p) for p in ref_parts)
    return sc


def reasons(p: dict, prof: dict, m: dict, team: str, d: dict, dprof: dict, lg: League, ranks: dict, scale: ScoreScale) -> list[dict]:
    """Plain-English reasons from the biggest contributors to the score (effect in score z units)."""
    L = lg.defense
    out = []
    sp = prof["splits"]
    fm = MODEL["fit_metric"]

    def axis_reason(ax: dict, part: str, conf: float, share: float = 1.0):
        a = m["axes"][ax["key"]]
        eff = scale.per_log(part) * share * conf * (a["def"] - a["league"])
        lean = max(ax["sides"], key=lambda x: d[x[1]] - L[x[1]])
        other = next(x for x in ax["sides"] if x is not lean)
        s_, col, word = lean
        i_lean = sp[s_]["metrics"][fm]["index"]
        i_other = sp[other[0]]["metrics"][fm]["index"]
        better = "better" if i_lean >= i_other else "worse"
        out.append({"effect": eff, "kind": "coverage" if part == "man_zone" else "shell",
                    "text": (f"{team} plays {word} on {d[col]:.0f}% of dropbacks (league {L[col]:.0f}%); "
                             f"he's {better} vs {word} ({i_lean:.2f}x league yards/route) than vs {other[2]} ({i_other:.2f}x); "
                             f"{conf * 100:.0f}% confident it's real.")})

    axis_reason(AXES[0], "man_zone", m["conf_mz"])
    axis_reason(AXES[1], "coverage_type", m["conf_sh"])

    # Zone types: the cover that moves his (confidence-weighted) zone fit most in the same direction.
    eff = scale.per_log("coverage_type") * MODEL["zone_type_weight"] * (m["zone_fit_conf"] - 1) * m["e_league"]
    zmix = dprof["zone_mix"]
    contrib = {z[0]: (zmix[z[0]] - lg.zone_mix[z[0]]) * prof["edges"][z[0]]["conf"] * ((sp[z[0]]["metrics"]["WIN_RATE"]["index"] or 1.0) - 1)
               for z in ZONE_COVERS}
    zc = max(ZONE_COVERS, key=lambda z: contrib[z[0]] if eff >= 0 else -contrib[z[0]])
    k_, col, label = zc
    wi = sp[k_]["metrics"]["WIN_RATE"]
    more = "more" if d[col] >= L[col] else "less"
    out.append({"effect": eff, "kind": "zone",
                "text": (f"{team} plays {label} {more} than most ({d[col]:.0f}% of dropbacks, league {L[col]:.0f}%); "
                         f"his {label} win rate is {wi['index']:.2f}x league ({prof['edges'][k_]['conf'] * 100:.0f}% confident it's real).")})

    # Where he lines up
    w = m["align_weights"]
    key = max(("WIDE", "SLOT", "INLINE"), key=lambda k: w[k] * abs(log(dprof["align"]["TE" if k == "INLINE" else k]["index"])))
    t = dprof["align"]["TE" if key == "INLINE" else key]
    rk = ranks[{"WIDE": "OUTER_FPG", "SLOT": "SLOT_FPG", "INLINE": "TE_FPG"}[key]][team]
    where = {"WIDE": "outside WRs", "SLOT": "slot receivers", "INLINE": "TEs"}[key]
    frm = {"WIDE": "outside", "SLOT": "from the slot", "INLINE": "inline"}[key]
    out.append({"effect": scale.per_log("alignment") * log(m["align_index"]), "kind": "alignment",
                "text": f"Allows {t['fpg']:.1f} FPG to {where} ({_rank_phrase(rk, 32)}); he runs {w[key] * 100:.0f}% of routes {frm}."})

    # His position
    pk = "TE" if p["POS"] == "TE" else "WR"
    t = dprof["align"][pk]
    rk = ranks[f"{pk}_FPG"][team]
    out.append({"effect": scale.per_log("position") * log(m["pos_index"]), "kind": "position",
                "text": f"Allows {t['fpg']:.1f} FPG to {pk}s (league {t['league']:.1f}; {_rank_phrase(rk, 32)})."})

    cap = MODEL["score_z_cap"]
    wts = MODEL["score_weights"]
    part_of = {"coverage": "man_zone", "shell": "coverage_type", "zone": "coverage_type", "alignment": "alignment", "position": "position"}
    for x in out:
        lim = cap * wts[part_of[x["kind"]]]
        x["effect"] = max(-lim, min(lim, x["effect"]))
    out = [x for x in out if abs(x["effect"]) >= MODEL["reason_min_effect"]]
    out.sort(key=lambda x: -abs(x["effect"]))
    return [{"text": x["text"], "kind": x["kind"], "edge": x["effect"] > 0, "effect": round(x["effect"], 4)} for x in out[: MODEL["max_reasons"]]]


def flags(p: dict, prof: dict, team: str, d: dict, lg: League) -> list[dict]:
    L = lg.defense
    out = []
    names = {"BLITZ_PCT": "blitzes", "PRESS_PCT_ANY": "presses", "DISGUISE_PCT": "disguises its coverage"}
    for col, pts in MODEL["flag_pts"].items():
        diff = d[col] - L[col]
        if abs(diff) >= pts:
            more = "more" if diff > 0 else "less"
            if col == "DISGUISE_PCT" and diff < 0:
                continue  # only a high disguise rate is worth a flag
            out.append({"key": col.lower(), "text": f"{team} {names[col]} {more} than most: {d[col]:.0f}% (league {L[col]:.0f}%)"})
    rz = prof["splits"]["RZ"]
    if (rz["sep_routes"] or 0) >= MODEL["rz_min_routes"] and (rz["metrics"]["WIN_RATE"]["index"] or 0) >= MODEL["rz_win_index"]:
        out.append({"key": "rz", "text": f"Wins in the red zone: {rz['metrics']['WIN_RATE']['raw']:.0f}% win rate on {rz['sep_routes']:.0f} red-zone routes ({rz['metrics']['WIN_RATE']['index']:.2f}x league)"})
    return out


def defense_ranks(defenses: dict[str, dict], dprofs: dict[str, dict], allowed: dict[str, dict]) -> dict[str, dict[str, int]]:
    """Rank 1 = allows the most."""
    teams = list(defenses)
    cov = {t: dprofs[t]["cov_raw"] for t in teams}
    out = {"cov": {t: _rank_desc(cov[t], list(cov.values())) for t in teams}}
    for col, src in [("TE_FPG", defenses), ("WR_FPG", defenses), ("OUTER_FPG", allowed), ("SLOT_FPG", allowed), ("LWR_FPG", allowed), ("RWR_FPG", allowed)]:
        vals = {t: src[t][col] for t in teams}
        out[col] = {t: _rank_desc(vals[t], list(vals.values())) for t in teams}
    for col in ("FP_DB_MAN", "FP_DB_ZONE", "FP_DB_1HI", "FP_DB_2HI"):
        vals = {t: defenses[t][col] for t in teams}
        out[col] = {t: _rank_desc(vals[t], list(vals.values())) for t in teams}
    return out
