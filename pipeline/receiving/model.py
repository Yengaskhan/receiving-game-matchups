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
  5  Matchup-adjusted FP/RR, projection, 0-100 Matchup Score, reasons and context flags.
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
    "w_cov_allowed": 0.5,
    "w_align_allowed": 0.5,
    # Matchup Score reference set: the week's scheduled pairs whose player has at least this many routes
    "score_ref_min_routes": 50,
    # Reasons: at most this many, and only contributors that move the matchup by at least this (log scale)
    "max_reasons": 3,
    "reason_min_effect": 0.01,
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

    shares = normalize({a: p[f"{a}_ROUTE_SHARE"] for a, _ in ALIGNMENTS}) if any(p[f"{a}_ROUTE_SHARE"] for a, _ in ALIGNMENTS) else {"WIDE": 0.0, "SLOT": 0.0, "INLINE": 0.0, "BACK": 0.0}
    return {"adj_overall": adj_overall, "pos_avg": pos_avg, "splits": splits, "align_shares": shares}


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
    return sum(w[s] * prof["splits"][s]["metrics"]["FP_RR"]["adj"] for s in w)


def zone_fit(prof: dict, dprof: dict, lg: League) -> float:
    """Cover 2/3/4/6 win-rate indexes weighted by the defense's zone mix, vs weighted by the league's."""
    idx = {k: prof["splits"][k]["metrics"]["WIN_RATE"]["index"] or 1.0 for k, _, _ in ZONE_COVERS}
    num = sum(dprof["zone_mix"][k] * idx[k] for k in idx)
    den = sum(lg.zone_mix[k] * idx[k] for k in idx)
    return num / den


def matchup(p: dict, prof: dict, d: dict, dprof: dict, lg: League) -> dict:
    L = lg.defense
    axes = {}
    for ax in AXES:
        e_def = axis_expectation(prof, ax, d)
        e_lg = axis_expectation(prof, ax, L)
        axes[ax["key"]] = {"def": e_def, "league": e_lg, "fit": e_def / e_lg}
    base_fit = sum(a["fit"] for a in axes.values()) / len(axes)
    zf = zone_fit(prof, dprof, lg)
    lam = MODEL["zone_detail_weight"]
    fit = (1 - lam) * base_fit + lam * zf

    if p["POS"] == "TE":
        align_idx = dprof["align"]["TE"]["index"]
        align_parts = {"TE": 1.0}
    else:
        # Wide routes face the outer corners, slot routes the slot; inline routes are TE-like; backfield is neutral.
        sh = prof["align_shares"]
        parts = {"WIDE": dprof["align"]["WIDE"]["index"], "SLOT": dprof["align"]["SLOT"]["index"], "INLINE": dprof["align"]["TE"]["index"], "BACK": 1.0}
        w = {k: sh[k] for k in parts}
        if sum(w.values()) <= 0:
            w = {"WIDE": 1.0, "SLOT": 0.0, "INLINE": 0.0, "BACK": 0.0}
        w = normalize(w)
        align_idx = sum(w[k] * parts[k] for k in parts)
        align_parts = w

    ratio = (fit ** MODEL["w_fit"]) * (dprof["cov_index"] ** MODEL["w_cov_allowed"]) * (align_idx ** MODEL["w_align_allowed"])
    fp_rr = prof["adj_overall"] * ratio
    rpg = p["OVERALL_RTE"] / p["G"] if p["G"] else 0.0
    return {
        "axes": axes, "base_fit": base_fit, "zone_fit": zf, "fit": fit,
        "cov_index": dprof["cov_index"], "align_index": align_idx, "align_weights": align_parts,
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


def reasons(p: dict, prof: dict, m: dict, team: str, d: dict, dprof: dict, lg: League, ranks: dict) -> list[dict]:
    """Plain-English reasons from the biggest contributors (effect = log of that factor)."""
    L = lg.defense
    lam = MODEL["zone_detail_weight"]
    nax = len(AXES)
    out = []
    sp = prof["splits"]
    ov = prof["adj_overall"]

    for ax in AXES:
        a = m["axes"][ax["key"]]
        eff = MODEL["w_fit"] * log(1 + (1 - lam) * (a["fit"] - 1) / nax)
        # Talk about the side the defense leans toward relative to league.
        lean = max(ax["sides"], key=lambda s: d[s[1]] - L[s[1]])
        s, col, word = lean
        fr = sp[s]["metrics"]["FP_RR"]
        txt = (f"{team} plays {word} on {d[col]:.0f}% of dropbacks (league {L[col]:.0f}%); "
               f"his {word} FP/RR is {fr['adj']:.2f} vs his overall {ov:.2f}.")
        out.append({"effect": eff, "text": txt, "kind": "coverage"})

    # Zone detail: the cover the defense uses most above league.
    zc = max(ZONE_COVERS, key=lambda z: d[z[1]] - L[z[1]])
    k_, col, label = zc
    wi = sp[k_]["metrics"]["WIN_RATE"]
    eff = MODEL["w_fit"] * log(1 + lam * (m["zone_fit"] - 1))
    out.append({"effect": eff, "kind": "zone",
                "text": f"{team} plays {label} on {d[col]:.0f}% of dropbacks (league {L[col]:.0f}%); his {label} win rate is {wi['index']:.2f}x league."})

    # Coverage-weighted FP allowed
    r = ranks["cov"][team]
    eff = MODEL["w_cov_allowed"] * log(dprof["cov_index"])
    mz = dprof["cov_axes"]["man_zone"]
    out.append({"effect": eff, "kind": "allowed",
                "text": f"Allows {mz['allowed']:.2f} PPR points per dropback to WR/TE given how it covers (league {mz['league']:.2f}; {_rank_phrase(r, 32)})."})

    # Alignment / TE
    if p["POS"] == "TE":
        t = dprof["align"]["TE"]
        r = ranks["TE_FPG"][team]
        out.append({"effect": MODEL["w_align_allowed"] * log(m["align_index"]), "kind": "alignment",
                    "text": f"Allows {t['fpg']:.1f} FPG to TEs (league {t['league']:.1f}; {_rank_phrase(r, 32)})."})
    else:
        w = m["align_weights"]
        key = max(("WIDE", "SLOT"), key=lambda k: w[k] * abs(log(dprof["align"][k]["index"])))
        t = dprof["align"][key]
        r = ranks["OUTER_FPG" if key == "WIDE" else "SLOT_FPG"][team]
        where = "outside WRs" if key == "WIDE" else "slot WRs"
        frm = "outside" if key == "WIDE" else "from the slot"
        out.append({"effect": MODEL["w_align_allowed"] * log(m["align_index"]), "kind": "alignment",
                    "text": f"Allows {t['fpg']:.1f} FPG to {where} ({_rank_phrase(r, 32)}); he runs {w[key] * 100:.0f}% of routes {frm}."})

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
