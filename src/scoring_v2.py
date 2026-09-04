# -*- coding: utf-8 -*-
"""FPP 능력점수 v2 — v1 + 세부 역할(role) 단위 백분위 풀·렌즈 가중치

v1의 문제: pos_primary가 FW/MF/DF 세 종류뿐이라 풀백과 센터백이 같은 "DF" 풀에서
백분위를 받고, 수비형 MF와 공격형 MF가 같은 "MF" 풀에 있다. 인계문서 §D의 "수비수 팀
강도 편향", "포지션 간 분산 불일치", 그리고 스타일 렌즈가 필요했던 이유("공격형 풀백
저평가")의 상당 부분이 여기서 나온다.

v2의 변경 (그 외는 v1과 동일):
  1. 역할 추론: shape(구성비) z-스코어로 각 선수를 7개 역할 중 하나로 분류
       DF → CB / FB,  MF → DM / CM / AM,  FW → ST / W
     판별 축은 §4-3 원칙대로 '구성비' 피처만 쓰고, 점수에 들어가는 per90 지표는
     쓰지 않는다(순환성 방지). z는 시즌×pos_primary 풀 기준(v1과 동일).
  2. 지표 백분위 풀: 시즌×pos_primary → **시즌×role**
  3. 포지션 렌즈 가중치: POS_W(3종) → ROLE_W(7종). POS_W를 역할 성격에 맞게 보간한 값이며,
     설계값이므로 폴드 밖 지표로 검증 후 채택(build/exp/a1_compare.py).
  4. 스타일 렌즈(STYLES)는 v1 그대로 pos_primary 단위 — A1 효과를 분리 측정하기 위해.

원본 v1은 보존한다(인계문서 규칙). 상수는 v1에서 import.

── 실험 결과 (2026-09, build/exp/a1_compare.py · a1_variants.py · a1_role_uses.py) ──
  · 역할 판정 자체는 건전: 알려진 선수 16명 중 13명 기대 역할 일치(불일치도 Saka→AM,
    Kimmich→DM처럼 해석 가능), 시즌별 역할 비율 안정. 단 연속 시즌 역할 유지율 79%
    (CB 94% / FB 89% / ST 87% / DM 82% / AM 69% / W 58% / CM 36%) — MF 내부 경계와
    W↔AM 경계는 해마다 흔들린다.
  · 시즌×role 백분위 풀은 점수 자체를 더 시끄럽게 만든다: 기저모델(미래=현재) MAE가
    U23 6.65→8.03, 베테랑 6.04→7.26으로 커지고(=시즌 간 재현성 하락), 하류 Δ회귀 OOF
    MAE도 6.00→7.10 / 5.31→6.39로 악화. 역할 렌즈(ROLE_W)만 써도 6.00→6.18 / 5.31→5.58.
  · 역할 one-hot 피처(v1 점수 위): AUC·MAE 변화 ±0.01 이내(중립). k-NN 후보 풀을
    role로 좁히기: LOO MAE 6.17→6.22 / 5.73→5.78(중립~미세 악화).
  · 포지션 간 분산 불일치도 해소되지 않음(v2 role sd 8.4~15.2, v1 pos sd 7.5~13.6).
  → 채택 규칙("폴드 밖 지표가 나빠지면 채택하지 않는다")에 따라 **점수 v2는 채택하지 않음**.
    현재 파이프라인은 build_scores(pool_by="pos", lens="pos") — v1과 점수가 동일하며
    role/role_axis 열만 추가되어 화면 표시(참고 라벨)에 쓰인다.
"""
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from scoring_v1 import PER90, RATE, GROUPS, STYLES, MIN_POOL, POS_W  # noqa: F401

# ── 역할 판별 축 (shape z 평균의 차) ─────────────────────────────
# 각 항목: (양의 축 피처들, 음의 축 피처들, 임계 목록, 역할 라벨 목록)
# 임계가 n개면 역할은 n+1개: axis < thr[0] → roles[0], ... , axis >= thr[-1] → roles[-1]
ROLE_RULES = {
    "DF": (["shape_cross", "shape_att3", "shape_takeon"],
           ["shape_aerial", "shape_clrvol", "shape_defpen"],
           [0.0], ["CB", "FB"]),
    "MF": (["shape_att3", "shape_attpen", "shape_shotrate", "shape_kp"],
           ["shape_tklvol", "shape_def3", "shape_defpen"],
           [-0.4, 0.4], ["DM", "CM", "AM"]),
    "FW": (["shape_attpen", "shape_shotrate", "shape_aerial"],
           ["shape_takeon", "shape_carry", "shape_cross"],
           [0.0], ["W", "ST"]),
}
ROLE_TO_POS = {"CB": "DF", "FB": "DF", "DM": "MF", "CM": "MF", "AM": "MF", "W": "FW", "ST": "FW"}
ROLE_LABEL_KO = {"CB": "센터백", "FB": "풀백", "DM": "수비형 MF", "CM": "중앙 MF",
                 "AM": "공격형 MF", "W": "윙어", "ST": "스트라이커"}

ROLE_W = {  # 역할 렌즈 가중치 — POS_W를 역할 성격에 맞게 보간. 각 행 합 = 1.00
    "ST": {"prod": .45, "chance": .15, "progress": .15, "stability": .10, "defense": .15},
    "W":  {"prod": .30, "chance": .25, "progress": .30, "stability": .05, "defense": .10},
    "AM": {"prod": .25, "chance": .30, "progress": .25, "stability": .10, "defense": .10},
    "CM": {"prod": .10, "chance": .20, "progress": .30, "stability": .25, "defense": .15},
    "DM": {"prod": .05, "chance": .10, "progress": .25, "stability": .25, "defense": .35},
    "FB": {"prod": .05, "chance": .20, "progress": .30, "stability": .20, "defense": .25},
    "CB": {"prod": .03, "chance": .05, "progress": .15, "stability": .27, "defense": .50},
}
for _r, _w in ROLE_W.items():
    assert abs(sum(_w.values()) - 1.0) < 1e-9, _r


def _per90_and_shape(df):
    n90 = (df["std_Min_Playing"] / 90).replace(0, np.nan)
    vals = {}
    for k, (col, d) in PER90.items():
        if k == "MisDis":
            v = (df["pos_Mis_Carries"].fillna(0) + df["pos_Dis_Carries"].fillna(0)) / n90
            v[df["pos_Mis_Carries"].isna() & df["pos_Dis_Carries"].isna()] = np.nan
        else:
            v = df[col] / n90
        vals[k] = v
    for k, (col, d) in RATE.items():
        vals[k] = df[col]
    V = pd.DataFrame(vals, index=df.index)

    T = df["pos_Touches_Touches"].replace(0, np.nan)
    AttP = df["pas_Att_Total"].replace(0, np.nan)
    prgP, prgC = df["pas_PrgDist_Total"], df["pos_PrgDist_Carries"]
    S = pd.DataFrame({
        "shape_attpen": df["pos_Att_Pen_Touches"] / T,
        "shape_att3": df["pos_Att_3rd_Touches"] / T,
        "shape_mid3": df["pos_Mid_3rd_Touches"] / T,
        "shape_def3": df["pos_Def_3rd_Touches"] / T,
        "shape_defpen": df["pos_Def_Pen_Touches"] / T,
        "shape_shotrate": df["sho_Sh_Standard"] / T,
        "shape_takeon": df["pos_Att_Dribbles"] / T,
        "shape_carry": prgC / (prgC + prgP),
        "shape_cross": df["msc_Crs"] / AttP,
        "shape_long": df["pas_Att_Long"] / AttP,
        "shape_kp": df["pas_KP"] / AttP,
        "shape_aerial": (df["msc_Won_Aerial"] + df["msc_Lost_Aerial"]) / n90,
        "shape_tklvol": df["def_Tkl_Tackles"] / n90,
        "shape_clrvol": df["def_Clr"] / n90,
        "shape_passvol": AttP / T,
    }, index=df.index)
    return V, S


def _zscore_within(df, S, keys):
    """S의 각 열을 df.groupby(keys) 풀(600분+) 기준으로 z-표준화."""
    Z = pd.DataFrame(index=df.index, columns=S.columns, dtype=float)
    for _, idx in df.groupby(keys).groups.items():
        pool = df.loc[idx].index[df.loc[idx, "std_Min_Playing"] >= MIN_POOL]
        if len(pool) < 20:
            pool = idx
        for c in S.columns:
            ref = S.loc[pool, c]
            mu, sd = ref.mean(), ref.std()
            if sd and not np.isnan(sd):
                Z.loc[idx, c] = (S.loc[idx, c] - mu) / sd
    return Z


def infer_roles(df, Z):
    """시즌×pos_primary 풀 z-스코어(Z)로 역할 추론. 반환: (role Series, role_axis Series)"""
    role = pd.Series(index=df.index, dtype=object)
    axis = pd.Series(np.nan, index=df.index)
    for pg, (pos_f, neg_f, thr, labels) in ROLE_RULES.items():
        m = df["pos_primary"] == pg
        a = Z.loc[m, pos_f].mean(axis=1) - Z.loc[m, neg_f].mean(axis=1)
        axis.loc[m] = a
        cut = np.digitize(a.values, thr)  # 0..len(thr)
        lab = pd.Series([labels[i] if not np.isnan(v) else None for i, v in zip(cut, a.values)], index=a.index)
        role.loc[m] = lab
    return role, axis


def build_scores(df, pool_by="role", lens="role"):
    """pool_by: 지표 백분위 풀 단위("role" | "pos"), lens: 포지션 렌즈 가중치("role" → ROLE_W | "pos" → POS_W).
    두 인자 모두 "pos"이면 v1과 동일한 점수에 role 컬럼만 추가된다(실험 분리용)."""
    df = df.copy()
    V, S = _per90_and_shape(df)

    # 1) 역할 추론 — v1과 동일한 시즌×pos 풀 z
    Z_pos = _zscore_within(df, S, ["Season_End_Year", "pos_primary"])
    role, role_axis = infer_roles(df, Z_pos)
    df["role"] = role

    out = df[["fbref_id", "Player", "Season_End_Year", "pos_primary", "age_y",
              "std_Min_Playing", "Squads", "Comps"]].copy()
    out["role"] = role
    out["role_axis"] = role_axis.round(2)
    out["eligible"] = df["std_Min_Playing"] >= MIN_POOL

    # 2) 지표 백분위 — 시즌×role 풀 (role 없는 행은 pos 풀로 폴백)
    pool_key = df["role"].where(df["role"].notna(), df["pos_primary"]) if pool_by == "role" else df["pos_primary"]
    pctl = pd.DataFrame(index=df.index, columns=V.columns, dtype=float)
    for (yr, rk), idx in df.groupby([df["Season_End_Year"], pool_key]).groups.items():
        pool = df.loc[idx].index[df.loc[idx, "std_Min_Playing"] >= MIN_POOL]
        if len(pool) < 20:
            pool = idx
        for c in V.columns:
            ref = V.loc[pool, c].dropna()
            if len(ref) < 10:
                continue
            sv = np.sort(ref.values)
            p = np.searchsorted(sv, V.loc[idx, c].values, side="right") / len(sv) * 100
            d = dict(PER90, **RATE).get(c, (None, 1))[1]
            pctl.loc[idx, c] = p if d == 1 else 100 - p

    G = pd.DataFrame({g: pctl[ms].mean(axis=1) for g, ms in GROUPS.items()})
    for g in GROUPS:
        out[f"grp_{g}"] = G[g].round(1)

    # 3) 역할 렌즈 (v1의 포지션 렌즈를 대체; 컬럼명은 하위호환 위해 score_position 유지)
    role_score = pd.Series(np.nan, index=df.index)
    for r, w in (ROLE_W.items() if lens == "role" else ()):
        m = df["role"] == r
        role_score[m] = sum(G.loc[m, g] * wi for g, wi in w.items())
    # 역할 미판정(shape 결측) 행은 v1 POS_W로 폴백
    for pg, w in POS_W.items():
        m = (df["pos_primary"] == pg) & role_score.isna()
        role_score[m] = sum(G.loc[m, g] * wi for g, wi in w.items())
    out["score_position"] = role_score.round(1)

    # 4) 스타일 렌즈 — v1과 동일 (pos_primary 단위, Z_pos 사용)
    style_name = pd.Series(index=df.index, dtype=object)
    style_score = pd.Series(np.nan, index=df.index)
    style_conf = pd.Series(np.nan, index=df.index)
    for pg, styles in STYLES.items():
        m = df["pos_primary"] == pg
        fit = pd.DataFrame({name: Z_pos.loc[m, feats].mean(axis=1) for name, (feats, _) in styles.items()})
        valid = fit.notna().any(axis=1)
        best = fit[valid].idxmax(axis=1)
        style_name.loc[best.index] = best
        fv = fit[valid]
        if fit.shape[1] > 1 and len(fv):
            sf = np.sort(fv.values, axis=1)
            style_conf.loc[fv.index] = sf[:, -1] - sf[:, -2]
        for name, (feats, w) in styles.items():
            mm = m & (style_name == name)
            style_score[mm] = sum(G.loc[mm, g] * wi for g, wi in w.items())
    out["style"] = style_name
    out["style_confidence"] = style_conf.round(2)
    out["score_style"] = style_score.round(1)

    out["ability"] = ((out["score_position"] + out["score_style"]) / 2).round(1)
    return out
