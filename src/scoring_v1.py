# -*- coding: utf-8 -*-
"""FPP 능력점수 v1 — 이중 가중(포지션 렌즈 + 스타일 렌즈)
구조: per90 변환 → 시즌×포지션 내 분위수 → 5그룹 집계 →
      포지션 가중점수 + 스타일 가중점수 → 평균 = 능력점수
"""
import pandas as pd, numpy as np, json

MIN_POOL = 600  # 분위수 풀 자격(분)

# ── 1. 지표 정의 ──────────────────────────────────────
# (컬럼, 방향) direction: +1 높을수록 좋음, -1 낮을수록 좋음
PER90 = {  # 누적 → per90 변환 대상
 "npxG":("std_npxG_Expected",1), "np_G":("std_G_minus_PK",1), "Sh":("sho_Sh_Standard",1),
 "SoT":("sho_SoT_Standard",1), "xAG":("std_xAG_Expected",1), "Ast":("std_Ast",1),
 "PrgPass":("pas_Prog",1), "PrgDistP":("pas_PrgDist_Total",1),
 "PrgCarry":("pos_Prog_Carries",1), "PrgDistC":("pos_PrgDist_Carries",1),
 "TakeOn":("pos_Succ_Dribbles",1), "PrgRec":("pos_Prog_Receiving",1),
 "F3Pass":("pas_Final_Third",1), "AttPenT":("pos_Att_Pen_Touches",1),
 "KP":("pas_KP",1), "PPA":("pas_PPA",1), "SCA":("gca_SCA_SCA",1), "GCA":("gca_GCA_GCA",1),
 "TklInt":("def_Tkl_plus_Int",1), "Blocks":("def_Blocks_Blocks",1),
 "Clr":("def_Clr",1), "Recov":("msc_Recov",1), "AerWon":("msc_Won_Aerial",1),
 "Err":("def_Err",-1), "MisDis":(None,-1),  # 특수: Mis+Dis 합성
}
RATE = {  # 이미 비율/율 지표
 "PassPct":("pas_Cmp_percent_Total",1), "TklPct":("def_Tkl_percent_Vs",1),
 "AerPct":("msc_Won_percent_Aerial",1), "npxG_Sh":("sho_npxG_per_Sh_Expected",1),
}
GROUPS = {
 "prod":      ["npxG","np_G","Sh","SoT","npxG_Sh","xAG","Ast"],
 "progress":  ["PrgPass","PrgDistP","PrgCarry","PrgDistC","TakeOn","PrgRec","F3Pass","AttPenT"],
 "chance":    ["SCA","GCA","KP","PPA"],
 "stability": ["PassPct","Err","MisDis"],
 "defense":   ["TklInt","TklPct","Blocks","Clr","Recov","AerWon","AerPct"],
}
POS_W = {  # 포지션 렌즈 가중치
 "FW": {"prod":.40,"chance":.20,"progress":.20,"stability":.10,"defense":.10},
 "MF": {"prod":.15,"chance":.20,"progress":.30,"stability":.20,"defense":.15},
 "DF": {"prod":.05,"chance":.10,"progress":.20,"stability":.25,"defense":.40},
}
# 스타일 정의: (판별용 shape 피처들) / (스타일 렌즈 가중치)
STYLES = {
 "FW": {
  "박스 포처":      (["shape_attpen","shape_shotrate"],            {"prod":.55,"chance":.15,"progress":.10,"stability":.10,"defense":.10}),
  "타겟맨":        (["shape_aerial","shape_attpen"],              {"prod":.45,"chance":.10,"progress":.10,"stability":.10,"defense":.25}),
  "돌파형 윙어":    (["shape_takeon","shape_carry","shape_cross"], {"prod":.25,"chance":.25,"progress":.35,"stability":.05,"defense":.10}),
  "연결형 공격수":  (["shape_kp","shape_mid3"],                    {"prod":.25,"chance":.35,"progress":.20,"stability":.15,"defense":.05}),
 },
 "MF": {
  "딥 플레이메이커": (["shape_long","shape_def3","shape_kp"],       {"prod":.05,"chance":.25,"progress":.30,"stability":.25,"defense":.15}),
  "볼 운반형":      (["shape_carry","shape_takeon"],               {"prod":.10,"chance":.20,"progress":.45,"stability":.15,"defense":.10}),
  "수비형 파괴자":  (["shape_tklvol","shape_def3","shape_aerial"], {"prod":.05,"chance":.05,"progress":.15,"stability":.25,"defense":.50}),
  "공격형 MF":     (["shape_att3","shape_attpen","shape_shotrate"],{"prod":.30,"chance":.30,"progress":.25,"stability":.10,"defense":.05}),
 },
 "DF": {
  "빌드업 수비수":  (["shape_long","shape_carry","shape_passvol"], {"prod":.05,"chance":.10,"progress":.35,"stability":.30,"defense":.20}),
  "스토퍼":        (["shape_aerial","shape_clrvol","shape_defpen"],{"prod":.03,"chance":.02,"progress":.10,"stability":.25,"defense":.60}),
  "공격형 풀백":    (["shape_att3","shape_cross","shape_takeon"],  {"prod":.10,"chance":.25,"progress":.30,"stability":.15,"defense":.20}),
 },
}

def build_scores(df):
    df = df.copy()
    n90 = (df["std_Min_Playing"]/90).replace(0,np.nan)
    # per90 값 생성
    vals = {}
    for k,(col,d) in PER90.items():
        if k=="MisDis":
            v = (df["pos_Mis_Carries"].fillna(0)+df["pos_Dis_Carries"].fillna(0))/n90
            v[df["pos_Mis_Carries"].isna()&df["pos_Dis_Carries"].isna()] = np.nan
        else:
            v = df[col]/n90
        vals[k] = v
    for k,(col,d) in RATE.items():
        vals[k] = df[col]
    V = pd.DataFrame(vals, index=df.index)

    # shape 피처 (스타일 판별용 — 수준이 아니라 '구성비' 중심)
    T = df["pos_Touches_Touches"].replace(0,np.nan)
    AttP = df["pas_Att_Total"].replace(0,np.nan)
    prgP, prgC = df["pas_PrgDist_Total"], df["pos_PrgDist_Carries"]
    S = pd.DataFrame({
      "shape_attpen": df["pos_Att_Pen_Touches"]/T,
      "shape_att3":   df["pos_Att_3rd_Touches"]/T,
      "shape_mid3":   df["pos_Mid_3rd_Touches"]/T,
      "shape_def3":   df["pos_Def_3rd_Touches"]/T,
      "shape_defpen": df["pos_Def_Pen_Touches"]/T,
      "shape_shotrate": df["sho_Sh_Standard"]/T,
      "shape_takeon": df["pos_Att_Dribbles"]/T,
      "shape_carry":  prgC/(prgC+prgP),
      "shape_cross":  df["msc_Crs"]/AttP,
      "shape_long":   df["pas_Att_Long"]/AttP,
      "shape_kp":     df["pas_KP"]/AttP,
      "shape_aerial": (df["msc_Won_Aerial"]+df["msc_Lost_Aerial"])/n90,
      "shape_tklvol": df["def_Tkl_Tackles"]/n90,
      "shape_clrvol": df["def_Clr"]/n90,
      "shape_passvol": AttP/T,
    }, index=df.index)

    out = df[["fbref_id","Player","Season_End_Year","pos_primary","age_y","std_Min_Playing","Squads","Comps"]].copy()
    out["eligible"] = df["std_Min_Playing"]>=MIN_POOL

    pctl = pd.DataFrame(index=df.index, columns=V.columns, dtype=float)
    Z    = pd.DataFrame(index=df.index, columns=S.columns, dtype=float)
    for (yr,pg), idx in df.groupby(["Season_End_Year","pos_primary"]).groups.items():
        pool = df.loc[idx].index[df.loc[idx,"std_Min_Playing"]>=MIN_POOL]
        if len(pool)<20: pool = idx
        for c in V.columns:
            ref = V.loc[pool,c].dropna()
            if len(ref)<10: continue
            r = V.loc[idx,c].rank(pct=True)*0  # placeholder
            # 풀 기준 분위: searchsorted
            sv = np.sort(ref.values)
            p = np.searchsorted(sv, V.loc[idx,c].values, side="right")/len(sv)*100
            d = dict(PER90, **RATE).get(c,(None,1))[1]
            pctl.loc[idx,c] = p if d==1 else 100-p
        for c in S.columns:
            ref = S.loc[pool,c]
            mu, sd = ref.mean(), ref.std()
            if sd and not np.isnan(sd):
                Z.loc[idx,c] = (S.loc[idx,c]-mu)/sd

    # 그룹 점수(분위 평균) 
    G = pd.DataFrame({g: pctl[ms].mean(axis=1) for g,ms in GROUPS.items()})
    for g in GROUPS: out[f"grp_{g}"] = G[g].round(1)

    # 포지션 렌즈
    pos_score = pd.Series(np.nan, index=df.index)
    for pg,w in POS_W.items():
        m = df["pos_primary"]==pg
        pos_score[m] = sum(G.loc[m,g]*wi for g,wi in w.items())
    out["score_position"] = pos_score.round(1)

    # 스타일 렌즈: shape z 평균 최대 스타일 → 해당 가중치
    style_name = pd.Series(index=df.index, dtype=object)
    style_score = pd.Series(np.nan, index=df.index)
    style_conf  = pd.Series(np.nan, index=df.index)
    for pg, styles in STYLES.items():
        m = df["pos_primary"]==pg
        fit = pd.DataFrame({name: Z.loc[m, feats].mean(axis=1) for name,(feats,_) in styles.items()})
        valid = fit.notna().any(axis=1)
        best = fit[valid].idxmax(axis=1)
        style_name.loc[best.index] = best
        fv = fit[valid]
        if fit.shape[1]>1 and len(fv):
            sf = np.sort(fv.values, axis=1)
            style_conf.loc[fv.index] = sf[:,-1]-sf[:,-2]
        for name,(feats,w) in styles.items():
            mm = m & (style_name==name)
            style_score[mm] = sum(G.loc[mm,g]*wi for g,wi in w.items())
    out["style"] = style_name
    out["style_confidence"] = style_conf.round(2)
    out["score_style"] = style_score.round(1)

    out["ability"] = ((out["score_position"]+out["score_style"])/2).round(1)
    return out

if __name__ == "__main__":
    df = pd.read_csv("fpp_features_clean_2018_2023.csv", low_memory=False)
    res = build_scores(df)
    res.to_csv("fpp_ability_v1_2018_2023.csv", index=False)
    json.dump({"POS_W":POS_W,"STYLES":{p:{s:w for s,(f,w) in d.items()} for p,d in STYLES.items()},
               "GROUPS":GROUPS,"MIN_POOL":MIN_POOL}, open("weights_v1.json","w"), ensure_ascii=False, indent=1)
    print("저장 완료:", res.shape)
