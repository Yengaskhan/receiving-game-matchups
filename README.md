# ClevAnalytics Receiving Game Matchup Report

The pass-game companion to the [Run Game Matchup Report](https://github.com/Yengaskhan/run-game-matchups). Pick a WR or TE and an opposing defense to see:
- how he produces against each coverage and alignment
- how often that defense plays each coverage, and what it allows
- a matchup-adjusted projection and a 0–100 **Matchup Score**

There's also a weekly **Slate Rankings** view of every WR/TE and a **Defense Profiles** view.

It has two parts, built the same way as the RB report:
- **Pipeline** (`pipeline/`, Python + polars). It reads the six FantasyPoints Data Suite exports in `data/raw/`, checks them, runs the matchup model, and writes precomputed JSON to `data/<season>/`. The schedule comes from nflverse via nflreadpy.
- **Page** (`index.html`, `src/`; React + TypeScript + Vite + Tailwind, with the same design tokens and components as the RB report). It only reads those JSON files, which are bundled at build time and loaded on demand. There are no runtime network calls.

## Weekly update

1. In FantasyPoints Data Suite, export these six tables (season to date, WR + TE) and save them with exactly these names:

   | File | Data Suite table |
   |---|---|
   | `receiving-situation.csv` | Receiving: Situation (Overall / Man / Zone / Single-High / Two-High) |
   | `receiving-separation-by-coverage.csv` | Receiving: Separation by Coverage |
   | `receiving-alignment.csv` | Receiving: Alignment |
   | `coverage-matrix.csv` | Team: Coverage Matrix |
   | `team-defense.csv` | Team: Defense |
   | `receiving-points-allowed.csv` | Team: Receiving Points Allowed |

2. On GitHub, open `data/raw/`, click **Add file → Upload files**, drop in all six (they replace the old ones), and commit to `main`.

That's it. The **Rebuild on upload** action (`.github/workflows/rebuild-on-upload.yml`) then:
- runs the pipeline for the current NFL week (nflverse's current week)
- runs `npm run build`, the same check Netlify runs
- commits the new `data/<season>/` files

Netlify redeploys within a couple of minutes. Earlier weeks' slate files stay on disk, so the Week selector keeps them.

- **If a run fails** (an export changed format, a team doesn't map, a check fails), GitHub emails you. The failed step's log says which file and which column. Nothing is committed and the live site keeps the last good data.
- **Build a specific week:** GitHub → **Actions** → **Rebuild on upload** → **Run workflow**, then enter the week.

### By hand

```bash
python3 -m venv .venv && .venv/bin/pip install -r pipeline/requirements.txt   # once
.venv/bin/python pipeline/run_receiving.py --inspect    # parse + check the exports, print columns, joins, team mapping
.venv/bin/python pipeline/run_receiving.py              # build this week (prints top/bottom 10 matchups and the score distribution)
.venv/bin/python pipeline/run_receiving.py --week 7     # a specific week
.venv/bin/python -m pytest pipeline/tests               # pipeline tests
npm install && npm run dev                              # local site
npm run build                                           # typecheck + data checks + bundle (what Netlify runs)
```

## Seasons: 2026, 2025, or both

A **Data** switch at the top of the page picks which numbers the report uses. Default: the current season.
- **2026** (default): the six exports in `data/raw/`.
- **2025**: the six 2025 exports in `data/raw/2025/` (same file names).
- **2025–2026**: both seasons combined.

Every view scores *this week's* matchups:
- **Players are on their current teams.** A 2025 row is matched to the 2026 player by Name + POS. A player with two 2025 rows (traded) is combined first. Players not in the 2026 exports are left out of the 2025 and combined views; the pipeline prints how many. Rookies have no 2025 data, so they only show in 2026 and combined.
- **Projections use 2026 routes per game** in every view, so they reflect his current role. Efficiency comes from the chosen view.
- **Combining (players):** routes, targets, yards, TDs, air yards and games add up. Every rate is the route-weighted average using that split's own routes, which is the same as recomputing it from the summed counts. Alignment shares are recomputed from routes.
- **Combining (defenses):** games and dropbacks add up. Coverage shares and team-defense rates are weighted by dropbacks. FP per dropback vs a coverage is weighted by the dropbacks in that coverage. Points allowed are summed, and per-game and per-target numbers recomputed.
- **Columns that only one season has** are left out of the combined view. Example: the 2025 coverage matrix's Blitz group.
- **Scores are ranked within each view**, so 50 is neutral in every view.

To add another prior season (e.g. 2024), put its six exports in `data/raw/2024/`, add `2024` to `PRIOR_SEASONS` in `pipeline/receiving/config.py`, and push. "Total" then covers every listed season. The output goes to `data/<season>/<view>/`; `data/<season>/index.json` lists the views and weeks.

## Deploy (one time)

1. In Netlify: **Add new site → Import an existing project → GitHub**, then pick **Yengaskhan/receiving-game-matchups**.
2. Leave the settings alone. `netlify.toml` already sets the build command `npm run build`, publish directory `dist`, and Node 22.
3. Click **Deploy** and rename the site if you like (e.g. `clevanalytics-receiving`). Optionally add a domain such as `receiving.yourdomain.com`.

**Embed on WordPress / Elementor:** add an **HTML** widget (Elementor) or a **Custom HTML** block (WordPress) with:

```html
<iframe
  src="https://receiving.yourdomain.com/"
  title="ClevAnalytics Receiving Game Matchups"
  style="width:100%; height:1400px; border:0;"
  loading="lazy"
></iframe>
```

- **Full screen:** when embedded, the page shows an "Open full screen ↗" link.
- **Links:** the selected tab, player, opponent, week and filters live in the URL hash (`#tab=player&player=puka-nacua-la&opp=ARI`), so links go straight to a view.
- **CSV downloads** work inside the frame. Don't add a `sandbox` attribute.
- **Restricting embedding:** to allow it only on your site, change `frame-ancestors *` in `netlify.toml` to your domain.

## How the exports are read

The loader is `pipeline/receiving/load.py`; settings are in `pipeline/receiving/config.py`.

- **Two header rows.** Row 1 is a group ("Man", "Cover 3", "SLOT") and row 2 the column. Names are built from both, e.g. `MAN_FP_RR`, `C3_WIN_RATE`, `SLOT_FPG`, `OVERALL_PLUS1_RATE`.
  - Because names are built from the headers, columns can be reordered without breaking anything.
  - Identity groups (Player Details, Team Details, Team) get no prefix.
  - A new group still loads, with a prefix made from its own name.
- **Team files** use the column name alone. The coverage matrix's four `FP/DB` columns are named after the coverage column just before each one: `FP_DB_MAN`, `FP_DB_ZONE`, `FP_DB_1HI`, `FP_DB_2HI`.
- **League Avg row** (the row with a blank Team in receiving-points-allowed) is kept for reference only. The model uses its own route-weighted league rates.
- **Footer** ("Exported from Data Suite … on 2026-10-14 22:06 UTC") is dropped. Its timestamp becomes the page's "Data as of". If the exports differ, the latest one is used.
- **Percentages** stay in percent units (26.6 = 26.6%).
- **Each file's expected columns are listed in `config.py`.** The run stops, naming the file and column, if one is missing, a value isn't numeric, the footer or League Avg row is missing, or two columns end up with the same name.
- **Player join:** receiving-situation is the base. The other two files join on Name + Team, then Name + POS for anything left, and only when a key is unique on both sides. Unmatched rows are printed and listed in `meta.json`.
  - Overall/Man/Zone route counts in the separation file are often a few routes lower than in the situation file. So each file's metrics are shrunk with that file's own route counts (the separation file's copies are kept as `SEP_*_RTE`).
- **Teams:** `data/team_map.csv` maps all 32 teams in three forms:
  - FantasyPoints code (ARZ, BLT, CLV, HST, LA, …)
  - full name, as in the team files
  - nflverse code (ARI, BAL, CLE, HOU, LA, …)

  The site uses nflverse codes so it shares the RB report's logos. Any code or name that doesn't map stops the run.
- **Checks that stop the run:**
  - only WR/TE rows
  - no duplicate Name + Team
  - Cover 2/3/4/6 routes add up to Zone routes for every player
  - team-defense MAN/ZONE/1-HIGH % agree with the coverage matrix within 0.5 points
  - Cover 2/3/4/6 % add up to ZONE % within 1 point
  - at least 15 scheduled WRs and 15 scheduled TEs with 50+ routes
  - no blank score for a 50+ route player
  - mean Matchup Score between 40 and 60, for WRs and TEs separately

## The matchup model

Everything is in `pipeline/receiving/model.py`, with every constant in the `MODEL` dict at the top. Defaults are shown below.

### League baselines

- **Player rates** are route-weighted over player rows: `league_split_m = Σ(routes_split × m_split) / Σ routes_split`. Situation-file metrics use situation routes; separation-file metrics use separation routes.
- **Position averages:** WR and TE overall FP/RR, route-weighted the same way.
- **Defense rates** are weighted by dropbacks (DB). FP per dropback vs a coverage is weighted by the dropbacks in that coverage (`DB × share`).
- **FPG allowed** = total points / total games.

### Step 1: Shrink splits toward the player

```
adj_overall_FP_RR = (RTE × FP_RR + 80 × position_avg) / (RTE + 80)

prior_split_m = player_overall_m × (league_split_m / league_overall_m)
adj_split_m   = (split_RTE × split_m + k × prior_split_m) / (split_RTE + k)
```

- `k` = 60 routes for FP/RR, YPRR and TPRR, and 40 for WIN RATE and SEP SCORE.
- For FP/RR, `player_overall` is his adjusted overall FP/RR. Other metrics use his raw overall.
- **SEP SCORE** sits near zero and can be negative, so its prior is shifted rather than scaled: `prior = overall + (league_split − league_overall)`. Its "index" is a difference from league.
- **Low sample:** any split under 20 routes is flagged "low n".

### Step 2: Indexes, never raw rates across coverages

`index_split_m = adj_split_m / league_split_m` (1.00 = league average in that coverage). The chart and detail table compare indexes only.

### Step 3: Coverage fit (player side)

Coverage fit uses **yards per route** (`MODEL["fit_metric"]`). FP/RR swings on touchdowns, and target rate alone ignores what a target is worth; yards per route also counts the routes where the QB never looks his way.

For each axis, the defense's shares are normalised to sum to 1. That spreads the ~4% of unusual plays pro rata.

```
E_axis(mix)   = Σ_side share_side(mix) × adj_YPRR_side
fit_axis      = E_axis(defense mix) / E_axis(league mix)
base_fit      = mean(fit_man_zone, fit_shell)
zone_fit      = Σ_c defense_zone_share_c × win_index_c / Σ_c league_zone_share_c × win_index_c    (c = Cover 2/3/4/6)
coverage_fit  = (1 − 0.15) × base_fit + 0.15 × zone_fit
```

- **Man/Zone axis** uses MAN % and ZONE %.
- **Shell axis** uses 1-HI % and 2-HI %.
- **Zone detail** compares each defense's Cover 2/3/4/6 shares within its zone with the league's.

**One change from the original spec:** the spec divided by the player's adjusted overall FP/RR; this divides by his expected FP/RR against the *league's* mix.
- **Why:** a league-average defense then scores exactly 1.00 for every player.
- **What it avoids:** a player whose man and zone FP/RR both beat his overall (because his other plays drag it down) would otherwise get a "good fit" against every defense, and the score would measure the player rather than the matchup.

**Adding an axis:** append an entry to `AXES` with its player split columns and defense share columns, and the fit becomes the mean over all axes. A future "vs blitz / no blitz" split would go here. Cover 0, 1 and 2 Man have no player split; the Man split covers them.

### Step 4: Defense strength (defense side)

```
allowed_axis   = Σ_side share_side(defense) × FP_DB_side           (FP_DB_MAN/ZONE, FP_DB_1HI/2HI)
cov_allowed    = mean_axis( allowed_axis / league allowed_axis )

WR: align_allowed = wide × OUTER_FPG idx + slot × SLOT_FPG idx + inline × TE_FPG idx + backfield × 1.00
TE: align_allowed = TE_FPG / league TE_FPG

every defensive index is shrunk:  1 + G / (G + 4) × (index − 1)
```

- The WR weights are his Wide/Slot/Inline/Backfield route shares, normalised.
- `OUTER` covers both outside sides.
- Each alignment index is that FPG / league FPG.

### Step 5: Projection and score

```
coverage fit (per axis) = 1 + confidence × (E_axis(defense mix) / E_axis(league mix) − 1)     confidence = "Is it real?" for that gap
multiplier              = coverage_fit^1.0 × alignment_allowed^0.5 × FP_per_dropback_allowed^0.25
                          (alignment_allowed: outside / slot / inline FPG allowed, weighted by his route shares;
                           defensive indexes shrunk toward 1.00 by games: 1 + G/(G + 10) × (index − 1))
expected change         = multiplier − 1                                   e.g. +5% = 5% more production than his normal week
projection (PPR)        = (2026 routes / G) × adj_overall_FP_RR × multiplier     ← "matchup-adjusted projection"
Matchup Score           = 50 + 50 × tanh(ln(multiplier) / 0.145)          fixed scale: 0% → 50, +5% → 66, +10% → 79, +20% → 93, −5% → 34
```

- **One number, two uses:** the score and the projection come from the same multiplier, so they always agree. The page shows the % next to every score, and each reason shows about how much it moves him.
- **Fixed scale, not a ranking:** a small effect stays near 50. A player who is a bit worse against the coverage he'll see more of (e.g. −1%) gets about 47, not a bottom-of-the-slate score.
- **Measured against his own normal week:** his season numbers came against roughly league-average coverage, so "normal" = a league-average defense. The score does not rate how good the player is.
- **Coverage effects are counted at their real size.** In most weeks a defense's coverage mix moves a player a few percent; extreme defenses (e.g. 46% man) move proven players 5–10%.
- **Points allowed are trusted gradually** (10 games to count half), because they depend heavily on which offenses a defense has faced.
- **Not in the score:** FP allowed to the whole position group (overlaps the alignment numbers, which are more specific).

### "Is it real?" Coverage-edge confidence

For each player, each coverage is tested against its opposite:
- man vs zone, and single-high vs two-high, on **yards per route**
- Cover 2, 3, 4 and 6, each vs his other zone routes, on **win rate** (the only stat the exports give for them)

Indexes are vs the league in each coverage, so league-wide differences between coverages don't count as his edge. The test uses raw (unshrunk) numbers.

```
per-route yards variance  Var = t × ypt² × (1 + cv²) − YPRR²      t = his TPRR, ypt = YPRR / t, cv = 1.4
                          (a target's yards: incompletions are 0 and catches vary about as much as their mean)
z          = (YPRR_a / L_a − YPRR_b / L_b) / sqrt(Var / n_a / L_a² + Var / n_b / L_b²)
win rate   same, with Var = p(1 − p), p = his win rate over all zone routes
confidence = 2Φ(|z|) − 1          (two-sided; 90% = a gap this big shows up by chance 10% of the time)
```

- **Labels:** "Real" at 90%+, "Leaning" at 75–90%, otherwise "Could be noise".
- **Why cv = 1.4:** it comes from how a target's yards vary, not from fitting this data. With it, man-vs-zone and single-vs-two-high gaps across 100+ route players have a z spread of about 1.0. That means most gaps in five weeks of data are consistent with luck, which is why the test matters.
- **Coverage edge flag:** a real (90%+) edge or weakness in a coverage this week's opponent plays at a top-5 rate (`edge_conf`, `edge_usage_rank`). It shows in Slate Rankings (with a "Coverage edges only" filter) and Player vs Defense. It has no direct effect on the score; the score already counts the same splits through coverage fit, with shrinkage.

### Reasons and context flags

- **Reasons:** up to 3 per matchup, from the parts that move the score most (in score units, capped like the score), and only those worth at least 0.05. Candidates:
  - each fit axis, phrased around the side the defense leans to vs league, e.g. "NE plays man on 35% of dropbacks (league 22%); he's better vs man (2.22x league FP/RR) than vs zone (1.23x)."
  - the zone-detail layer, naming the Cover 2/3/4/6 that moves his zone fit most
  - FP per dropback allowed to WRs and TEs
  - alignment or TE FP allowed, e.g. "Allows 30.5 FPG to outside WRs (3rd most); he runs 79% of routes outside."
- **Context flags** (no effect on the score) appear for:
  - blitz %, press % (any) or disguise % at least 5 points from league (disguise is flagged only when high)
  - a red-zone win-rate index of 1.20+ on 15+ red-zone routes
- **Not used in any calculation:** SEP MS, ADOR, +1/+2/+3 Rate and Neg Rate, which the source doesn't define. They're shown in the player detail table for reference.
- **Display only:** team-defense PASS %, PROE and PACE, because it's unclear whether they describe the defense's opponents.

## Roles (WR1, WR2, TE1 ...)

Each team's WRs and TEs are ranked by **targets per game this season** (the current season, in every view). Players with fewer than 2 games rank after the regulars, so one big game can't make a WR1. A player traded mid-season is ranked on his current team. The slate's **Role** filter uses this (WR1, WR2, WR3, WR1 + WR2, WR1–WR3, WR4 and below, TE1, TE2 and below), and the role shows under each name.

## Output files (`data/<season>/`)

| File | Contents |
|---|---|
| `index.json` | Weeks on disk, current week, data as of |
| `meta.json` | Export timestamps, league baselines (ours and the exports' League Avg), model settings, join log, passed checks |
| `players.json` | Every WR/TE: raw and adjusted splits, league rates, indexes, low-sample flags, alignment, reference metrics |
| `defenses.json` | Every defense: coverage mix vs league, FP allowed by coverage and alignment with ranks, context, shrunk indexes |
| `pairs/<TEAM>.json` | Every WR/TE vs that defense: score, projection, fit, factors, reasons, flags |
| `week-XX.json` | The week's scheduled matchups (Slate Rankings, Defense Profiles) |

## Tests

- `pipeline/tests/` (pytest), which the action runs first:
  - double-header parsing, footer removal and duplicate-name handling
  - format-change errors
  - team map covers all 32
  - shrinkage, weight normalisation, indexes, percentiles
  - a league-average defense is exactly neutral
  - committed scores are centred
- `tests/data.test.ts` (vitest, part of `npm run build`) checks every committed output file before a deploy:
  - every week file is listed in the index
  - player ids are unique
  - 32 defenses, with full pair files
  - scores in 0–100, slate scores centred
