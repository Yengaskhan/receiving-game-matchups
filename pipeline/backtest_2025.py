"""
Walk-forward backtest of the matchup signals on the 2025 season (research tool; not part of the weekly run).

    python pipeline/backtest_2025.py        # writes data/backtest/2025.json (about a minute)

For each week w = 5..18, every signal is built only from 2025 games before week w (nflverse play-by-play
and participation, which carries man/zone and Cover 0-6 for each play) and compared with what each WR/TE
actually scored in week w. Players need 80+ routes before the week and 8+ routes in it (1,645 games).

  routes      on-field pass plays x his 2025 route rate (Data Suite routes / on-field pass plays)
  alignment   his 2025 Data Suite route shares (wide / slot / inline / backfield); points allowed to an
              alignment = targets' points weighted by the targeted player's share there
  outcome     receiving PPR points (catch 1, yard 0.1, TD 6) vs his normal week: his FP per route before
              the week (shrunk toward his position's average, 80 routes) x his routes per game

The weights in pipeline/receiving/model.py (MODEL) come from this file's results.
"""
import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
R = str(ROOT / "data" / "raw" / "2025") + "/"


def ds(name, ncols, cols):
    t = open(R + name).read().splitlines()
    df = pd.read_csv(io.StringIO('\n'.join(t[1:-1])))
    df = df[df.Season.astype(str) == '2025']
    out = df.iloc[:, :ncols].copy(); out.columns = cols
    out['pid'] = df['player_id'].astype(str)
    return out.set_index('pid')
sit = ds('receiving-situation.csv', 10, ['S', 'R', 'Name', 'Team', 'POS', 'G', 'RTE', 'TPRR', 'YPRR', 'FPRR'])
al = pd.read_csv(io.StringIO('\n'.join(open(R + 'receiving-alignment.csv').read().splitlines()[1:-1])))
al = al[al.Season.astype(str) == '2025'].set_index(al.columns[-1])
# alignment route shares (RTE % columns): wide, slot, inline, back
rc = [c for c in al.columns if c.startswith('RTE %')]
sh = al[rc[-4:]].astype(float).div(100); sh.columns = ['WIDE', 'SLOT', 'INLINE', 'BACK']
sh.index = sh.index.astype(str)
sh = sh.div(sh.sum(1).replace(0, np.nan), axis=0).fillna(0)

import nflreadpy as nfl  # noqa: E402

pbp = nfl.load_pbp([2025]).filter(
    (pl.col('season_type') == 'REG') & (pl.col('pass_attempt') == 1) & (pl.col('two_point_attempt') != 1)).to_pandas()
part = nfl.load_participation([2025]).to_pandas()
pbp = pbp[['game_id', 'play_id', 'week', 'posteam', 'defteam', 'sack', 'receiver_player_id', 'receiving_yards', 'complete_pass', 'pass_touchdown', 'interception']]
part = part.rename(columns={'nflverse_game_id': 'game_id'})[['game_id', 'play_id', 'offense_players', 'defense_man_zone_type', 'defense_coverage_type']]
pbp['play_id'] = pbp.play_id.astype(float); part['play_id'] = part.play_id.astype(float)
P = pbp.merge(part, on=['game_id', 'play_id'], how='left')
P['receiving_yards'] = P.receiving_yards.fillna(0)
P['fp'] = np.where(P.receiver_player_id.notna(), P.complete_pass.fillna(0) * 1 + 0.1 * P.receiving_yards + 6 * P.pass_touchdown.fillna(0), 0)
P['mz'] = P.defense_man_zone_type.map({'MAN_COVERAGE': 'MAN', 'ZONE_COVERAGE': 'ZONE'})
CT = {'COVER_0': 'C0', 'COVER_1': 'C1', 'COVER_2': 'C2', '2_MAN': 'C2M', 'COVER_3': 'C3', 'COVER_4': 'C4', 'COVER_6': 'C6'}
P['ct'] = P.defense_coverage_type.map(CT)
P['shell'] = P.ct.map({'C0': 'ONE', 'C1': 'ONE', 'C3': 'ONE', 'C2': 'TWO', 'C2M': 'TWO', 'C4': 'TWO', 'C6': 'TWO'})
# receiver position + alignment share for targeted plays
pos = sit['POS']
P['rpos'] = P.receiver_player_id.map(pos)
for k in ['WIDE', 'SLOT', 'INLINE']:
    P['sh_' + k] = P.receiver_player_id.map(sh[k]).fillna(0)

# player-play exposure (routes): on-field pass plays (non-sack) x season route rate
NP = P[P.sack != 1].copy()
of = NP[['game_id', 'play_id', 'week', 'posteam', 'defteam', 'mz', 'shell', 'ct', 'receiver_player_id', 'receiving_yards', 'fp', 'offense_players']].dropna(subset=['offense_players'])
of['pid'] = of.offense_players.str.split(';'); of = of.explode('pid')
of = of[of.pid.isin(sit.index)]
onf = of.groupby('pid').size()
rr = (sit.RTE.astype(float) / onf).clip(upper=1).dropna()
of['rte'] = of.pid.map(rr)
of['tgt'] = (of.receiver_player_id == of.pid).astype(float)
of['yds'] = np.where(of.tgt > 0, of.receiving_yards, 0.0)
of['pfp'] = np.where(of.tgt > 0, of.fp, 0.0)
of = of.drop(columns=['offense_players', 'receiver_player_id', 'receiving_yards', 'fp'])

sch = nfl.load_schedules([2025]).to_pandas(); sch = sch[sch.game_type == 'REG']
imp = []
for _, g in sch.iterrows():
    h = (g.total_line + g.spread_line) / 2
    imp += [dict(week=g.week, team=g.home_team, opp=g.away_team, imp=h), dict(week=g.week, team=g.away_team, opp=g.home_team, imp=g.total_line - h)]
imp = pd.DataFrame(imp).sort_values('week')
imp['imp_avg'] = imp.groupby('team').imp.transform(lambda x: x.expanding().mean().shift(1))

K = 60
GRP = {}
for pid_ in sit.index:
    if sit.loc[pid_, 'POS'] == 'TE': GRP[pid_] = 'TE'
    elif pid_ in sh.index and sh.loc[pid_, 'SLOT'] > 0.5: GRP[pid_] = 'WR_SLOT'
    else: GRP[pid_] = 'WR_WIDE'
rows = []
for w in range(5, 19):
    pr = of[of.week < w]; wk = of[of.week == w]
    D = P[P.week < w]
    # ---------------- league baselines
    lg_ov = pr.yds.sum() / pr.rte.sum()
    def split_rates(col, keys):
        g = pr.dropna(subset=[col]).groupby(['pid', col])[['rte', 'yds', 'tgt', 'pfp']].sum().unstack(col)
        lgs = pr.dropna(subset=[col]).groupby(col)[['rte', 'yds']].sum()
        lg_ratio = (lgs.yds / lgs.rte) / lg_ov
        return g, lg_ratio
    pl_ov = pr.groupby('pid')[['rte', 'yds', 'tgt', 'pfp']].sum()
    games = pr.groupby('pid').game_id.nunique()
    # defense usage (share of dropbacks, weeks < w)
    du = {}
    for col in ['mz', 'shell', 'ct']:
        c = D.dropna(subset=[col]).groupby(['defteam', col]).size().unstack(col).fillna(0)
        du[col] = c.div(c.sum(1), axis=0)
        du[col + '_lg'] = c.sum() / c.sum().sum()
    # defense allowed
    dg = D.groupby('defteam').game_id.nunique()
    db = D.groupby('defteam').size()
    al_ = {}
    for p_ in ['WR', 'TE']:
        x = D[D.rpos == p_]
        al_[p_ + '_fpg'] = x.groupby('defteam').fp.sum() / dg
        al_[p_ + '_fpt'] = x.groupby('defteam').fp.sum() / x.groupby('defteam').size()
        al_[p_ + '_tpg'] = x.groupby('defteam').size() / dg
    wrte = D[D.rpos.isin(['WR', 'TE'])]
    al_['ppd'] = wrte.groupby('defteam').fp.sum() / db
    for k in ['WIDE', 'SLOT', 'INLINE']:
        x = D[D.rpos.isin(['WR', 'TE'])]
        al_[k + '_fpg'] = (x.fp * x['sh_' + k]).groupby(x.defteam).sum() / dg
        al_[k + '_fpt'] = (x.fp * x['sh_' + k]).groupby(x.defteam).sum() / x['sh_' + k].groupby(x.defteam).sum()
    al_['db_pg'] = db / dg
    alw = pd.DataFrame(al_)
    alw_lg = alw.mean()
    # recent (last 4 weeks) versions
    D4 = D[D.week >= w - 4]; dg4 = D4.groupby('defteam').game_id.nunique()
    x4 = D4[D4.rpos.isin(['WR', 'TE'])]
    rec_ppd = x4.groupby('defteam').fp.sum() / D4.groupby('defteam').size()
    split = {c: split_rates(c, None) for c in ['mz', 'shell', 'ct']}
    GR = {}
    pg = pr.assign(grp=pr.pid.map(GRP).fillna('WR_WIDE'))
    for c in ['mz', 'ct']:
        q = pg.dropna(subset=[c]).groupby(['grp', c])[['rte', 'pfp']].sum()
        rate = (q.pfp / q.rte).unstack(c)
        lgr = pg.dropna(subset=[c]).groupby(c)[['rte', 'pfp']].sum(); lgr = lgr.pfp / lgr.rte
        ovr = pg.groupby('grp')[['rte', 'pfp']].sum(); ovr = ovr.pfp / ovr.rte
        lgo = pg.pfp.sum() / pg.rte.sum()
        GR[c] = (rate.div(ovr, axis=0)).div(lgr / lgo, axis=1)
    LR = {}
    for c in ['mz', 'shell', 'ct']:
        q = pr.dropna(subset=[c]).groupby(c)[['rte', 'yds', 'tgt']].sum()
        LR[c] = {m: (q[m] / q.rte) / (pr[m].sum() / pr.rte.sum()) for m in ['yds', 'tgt']}
    # ---------------- outcomes for week w
    out = wk.groupby(['pid', 'posteam', 'defteam'])[['rte', 'yds', 'tgt', 'pfp']].sum().reset_index()
    for _, o in out.iterrows():
        pid = o.pid
        if pid not in pl_ov.index or pl_ov.loc[pid, 'rte'] < 80 or o.rte < 8: continue
        ov = pl_ov.loc[pid]; d = o.defteam
        if d not in alw.index: continue
        r = dict(week=w, pid=pid, name=sit.loc[pid, 'Name'], pos=sit.loc[pid, 'POS'], team=o.posteam, opp=d,
                 rte=o.rte, yds=o.yds, tgt=o.tgt, fp=o.pfp, p_rte=ov.rte, p_yprr=ov.yds / ov.rte, p_tprr=ov.tgt / ov.rte,
                 p_fprr=ov.pfp / ov.rte, p_rpg=ov.rte / games[pid], p_fpg=ov.pfp / games[pid])
        for col in ['mz', 'shell', 'ct']:
            g = split[col][0]
            keys = list(du[col].columns)
            wd = du[col].loc[d] if d in du[col].index else du[col + '_lg']
            wl = du[col + '_lg']
            for met in ['yds', 'tgt']:
                ov_rate = ov[met] / ov.rte
                for KK in [60, 200, 600]:
                    adj = {}
                    for s_k in keys:
                        n = g[('rte', s_k)].get(pid, 0) if ('rte', s_k) in g.columns else 0
                        y = g[(met, s_k)].get(pid, 0) if (met, s_k) in g.columns else 0
                        n = 0 if pd.isna(n) else n; y = 0 if pd.isna(y) else y
                        adj[s_k] = (y + KK * ov_rate * LR[col][met].get(s_k, 1)) / (n + KK)
                    e_d = sum(wd[s_k] * adj[s_k] for s_k in keys); e_l = sum(wl[s_k] * adj[s_k] for s_k in keys)
                    r[f'fit_{col}_{met}_{KK}'] = e_d / e_l if e_l > 0 else 1
            r['fit_' + col] = r[f'fit_{col}_yds_60']
        grp = GRP.get(pid, 'WR_WIDE')
        for col in ['mz', 'ct']:
            idx = GR[col].loc[grp] if grp in GR[col].index else None
            wd = du[col].loc[d] if d in du[col].index else du[col + '_lg']; wl = du[col + '_lg']
            if idx is None: r['gfit_' + col] = 1.0; continue
            idx = idx.reindex(wd.index).fillna(1.0)
            r['gfit_' + col] = float((wd * idx).sum() / (wl * idx).sum())
        a = alw.loc[d]
        p_ = r['pos']
        r['d_pos_fpg'] = a[p_ + '_fpg'] / alw_lg[p_ + '_fpg']
        r['d_pos_fpt'] = a[p_ + '_fpt'] / alw_lg[p_ + '_fpt']
        r['d_pos_tpg'] = a[p_ + '_tpg'] / alw_lg[p_ + '_tpg']
        r['d_ppd'] = a['ppd'] / alw_lg['ppd']
        r['d_ppd_recent'] = rec_ppd.get(d, np.nan) / alw_lg['ppd']
        r['d_db_pg'] = a['db_pg'] / alw_lg['db_pg']
        s_ = sh.loc[pid] if pid in sh.index else pd.Series({'WIDE': 1 if p_ == 'WR' else 0, 'SLOT': 0, 'INLINE': 1 if p_ == 'TE' else 0, 'BACK': 0})
        for m in ['fpg', 'fpt']:
            num = sum(s_[k] * a[k + '_' + m] / alw_lg[k + '_' + m] for k in ['WIDE', 'SLOT', 'INLINE']) + s_['BACK']
            r['d_align_' + m] = num / max(s_.sum(), 1e-9)
        r['games_def'] = dg[d]
        rows.append(r)
    print(w, len(rows), file=sys.stderr)
df = pd.DataFrame(rows)
df = df.merge(imp[['week', 'team', 'imp', 'imp_avg']], on=['week', 'team'], how='left')
df['vegas_rel'] = df.imp / df.imp_avg

# ------------------------------------------------------------------------------------------------
# Results
# ------------------------------------------------------------------------------------------------
lgf = df.groupby('pos').apply(lambda d: (d.p_fprr * d.p_rte).sum() / d.p_rte.sum())
df['normal_rr'] = (df.p_fprr * df.p_rte + 80 * df.pos.map(lgf)) / (df.p_rte + 80)
df['normal'] = df.normal_rr * df.p_rpg
df['tot'] = np.log((df.fp + 1) / (df.normal + 1))


def rho(a, b):
    return round(float(pd.Series(a).corr(pd.Series(b), method='spearman')), 3)


def shr(col, k):
    return np.log(1 + df.games_def / (df.games_def + k) * (df[col] - 1))


fit = np.log(0.85 * (df.fit_mz + df.fit_shell) / 2 + 0.15 * df.fit_ct)
models = {
    "v1": {"label": "Old model (coverage fit x alignment allowed^0.5 x FP/dropback^0.25)",
           "x": fit + 0.5 * shr('d_align_fpg', 10) + 0.25 * shr('d_ppd', 10)},
    "v2": {"label": "New model (alignment allowed^0.45 x Vegas^0.31 x coverage fit^0.25)",
           "x": 0.45 * shr('d_align_fpg', 3) + 0.31 * np.log(df.vegas_rel) + 0.25 * fit},
}
signals = [("fit_mz", "His man vs zone fit"), ("fit_shell", "His single- vs two-high fit"), ("fit_ct", "His Cover 0-6 fit"),
           ("gfit_ct", "Cover 0-6 fit by player type (slot WR / wide WR / TE)"),
           ("d_align_fpg", "Points per game allowed to his alignment"), ("d_align_fpt", "Points per target allowed to his alignment"),
           ("d_pos_fpg", "Points per game allowed to his position"), ("d_ppd", "Points per dropback allowed to WR/TE"),
           ("d_ppd_recent", "Points per dropback allowed, last 4 weeks"), ("vegas_rel", "Vegas team total vs its average")]
rng = np.random.default_rng(0)
clusters = (df.week.astype(str) + df.team).values
uc = np.unique(clusters)


def boot_ci(x):
    idx = {c: np.where(clusters == c)[0] for c in uc}
    vals = []
    for _ in range(300):
        take = np.concatenate([idx[c] for c in rng.choice(uc, len(uc))])
        vals.append(pd.Series(np.asarray(x)[take]).corr(pd.Series(df.tot.values[take]), method='spearman'))
    return [round(float(np.percentile(vals, 5)), 3), round(float(np.percentile(vals, 95)), 3)]


out = {"season": 2025, "weeks": [int(df.week.min()), int(df.week.max())], "n": int(len(df)),
       "outcome": "receiving PPR points vs his normal week (FP per route before the week x routes per game)",
       "signals": [{"key": k, "label": lab, "rho": rho(df[k], df.tot)} for k, lab in signals],
       "models": []}
for key, m in models.items():
    q = pd.qcut(m["x"], 5, labels=False)
    quint = []
    for i in range(5):
        d = df[q == i]
        quint.append({"quintile": i + 1, "n": int(len(d)), "beat": round(float((d.fp > d.normal).mean()), 4),
                      "vs_normal": round(float(d.fp.sum() / d.normal.sum() - 1), 4)})
    out["models"].append({"key": key, "label": m["label"], "rho": rho(m["x"], df.tot), "rho_90ci": boot_ci(m["x"]), "quintiles": quint})
dest = ROOT / "data" / "backtest" / "2025.json"
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out, indent=1))
