"""리포트 확장 항목(강점/약점, Top3 스타일, 코칭 제안, 성장 로드맵) 계산.

scoring_v1.py의 build_scores()는 그룹 집계 점수만 반환하고 개별 지표
퍼센타일·스타일 피팅 점수 전체를 버리기 때문에, 같은 PER90/RATE/STYLES
상수를 재사용해 '표시용' 개별 지표 퍼센타일과 스타일 피팅 점수를 별도로
계산한다. scoring_v1.py 자체는 손대지 않는다(원본 능력점수 계산과 분리).

이 파일이 만드는 것은 전부 '규칙 기반 제안/설명'이지 검증된 예측이 아니다.
"""
import numpy as np
import pandas as pd

import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from scoring_v1 import PER90, RATE, GROUPS, POS_W, STYLES, MIN_POOL

METRIC_LABELS = {
    "npxG": "비페널티 xG", "np_G": "무페널티 득점", "Sh": "슈팅 시도", "SoT": "유효슈팅",
    "xAG": "도움 기대값(xAG)", "Ast": "어시스트",
    "PrgPass": "전진 패스", "PrgDistP": "전진 패스 거리", "PrgCarry": "전진 운반",
    "PrgDistC": "전진 운반 거리", "TakeOn": "성공 드리블", "PrgRec": "전진 패스 수신",
    "F3Pass": "최종 3분의1 패스", "AttPenT": "박스 터치", "KP": "키패스", "PPA": "박스 진입 패스",
    "SCA": "슈팅 창출(SCA)", "GCA": "골 창출(GCA)",
    "TklInt": "태클+인터셉트", "Blocks": "블록", "Clr": "클리어링", "Recov": "볼 리커버리",
    "AerWon": "공중볼 승리", "Err": "실책", "MisDis": "볼 손실(미스+파울)",
    "PassPct": "패스 성공률", "TklPct": "태클 성공률", "AerPct": "공중볼 승률", "npxG_Sh": "슈팅당 기대득점",
}

# 그룹별 위치가중치(POS_W) 0.15 미만인 그룹은 그 포지션의 '본업'이 아니라고 보고
# 약점 목록에서 제외 — legacy의 "포지션을 고려한 약점 선별"과 동일한 취지.
WEAKNESS_MIN_WEIGHT = 0.15

METRIC_GROUP = {m: g for g, ms in GROUPS.items() for m in ms}

# 포지션별 핵심지표 6개 (레이더용) — 스타일보다 넓은 포지션 단위 대표 지표.
POSITION_RADAR_KEYS = {
    "FW": ["npxG", "SCA", "TakeOn", "PrgCarry", "AttPenT", "KP"],
    "MF": ["PrgPass", "KP", "TklInt", "PrgCarry", "SCA", "PassPct"],
    "DF": ["TklInt", "Clr", "AerPct", "PrgPass", "PassPct", "Blocks"],
}

# 스타일별 코칭 핵심 지표(3~4개) — scoring_v1 STYLES의 판별 shape 피처와 같은 축의
# 실지표(원시 percentile) 버전으로 선정.
COACHING_KEYS = {
    "박스 포처": ["npxG", "SoT", "AttPenT"],
    "타겟맨": ["AerWon", "np_G", "AttPenT"],
    "돌파형 윙어": ["TakeOn", "PrgCarry", "KP"],
    "연결형 공격수": ["KP", "SCA", "PrgRec"],
    "딥 플레이메이커": ["PrgPass", "KP", "PPA"],
    "볼 운반형": ["PrgCarry", "TakeOn", "PrgDistC"],
    "수비형 파괴자": ["TklInt", "Blocks", "Recov"],
    "공격형 MF": ["SCA", "KP", "npxG"],
    "빌드업 수비수": ["PrgPass", "PrgCarry", "PassPct"],
    "스토퍼": ["TklInt", "Clr", "AerWon"],
    "공격형 풀백": ["PrgCarry", "TakeOn", "KP"],
}


def compute_pctl_and_style_fit(df):
    """df: 단일 시즌(예: 2023) 필드플레이어 전체 행. scoring_v1.build_scores와
    동일한 시즌×포지션 풀·searchsorted 백분위 로직으로 개별 지표 퍼센타일(pctl)과
    스타일별 피팅 점수 전체(fit_all, 후보 스타일 모두)를 반환한다."""
    df = df.copy()
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
        "shape_attpen": df["pos_Att_Pen_Touches"] / T, "shape_att3": df["pos_Att_3rd_Touches"] / T,
        "shape_mid3": df["pos_Mid_3rd_Touches"] / T, "shape_def3": df["pos_Def_3rd_Touches"] / T,
        "shape_defpen": df["pos_Def_Pen_Touches"] / T, "shape_shotrate": df["sho_Sh_Standard"] / T,
        "shape_takeon": df["pos_Att_Dribbles"] / T, "shape_carry": prgC / (prgC + prgP),
        "shape_cross": df["msc_Crs"] / AttP, "shape_long": df["pas_Att_Long"] / AttP,
        "shape_kp": df["pas_KP"] / AttP, "shape_aerial": (df["msc_Won_Aerial"] + df["msc_Lost_Aerial"]) / n90,
        "shape_tklvol": df["def_Tkl_Tackles"] / n90, "shape_clrvol": df["def_Clr"] / n90,
        "shape_passvol": AttP / T,
    }, index=df.index)

    pctl = pd.DataFrame(index=df.index, columns=V.columns, dtype=float)
    Z = pd.DataFrame(index=df.index, columns=S.columns, dtype=float)
    for (yr, pg), idx in df.groupby(["Season_End_Year", "pos_primary"]).groups.items():
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
        for c in S.columns:
            ref = S.loc[pool, c]
            mu, sd = ref.mean(), ref.std()
            if sd and not np.isnan(sd):
                Z.loc[idx, c] = (S.loc[idx, c] - mu) / sd

    fit_all = {}
    for pg, styles in STYLES.items():
        m = df["pos_primary"] == pg
        fit = pd.DataFrame({name: Z.loc[m, feats].mean(axis=1) for name, (feats, _) in styles.items()})
        fit_all[pg] = fit

    return pctl.round(1), fit_all, Z


def top_strengths(pctl_row, n=7):
    s = pctl_row.dropna().sort_values(ascending=False)
    return [{"key": k, "label": METRIC_LABELS.get(k, k), "percentile": round(float(v), 1)} for k, v in s.head(n).items()]


def top_weaknesses(pctl_row, pos, n=5):
    w = POS_W.get(pos, {})
    relevant = [m for m, g in METRIC_GROUP.items() if w.get(g, 0) >= WEAKNESS_MIN_WEIGHT and m in pctl_row.index]
    s = pctl_row[relevant].dropna().sort_values(ascending=True)
    return [{"key": k, "label": METRIC_LABELS.get(k, k), "percentile": round(float(v), 1)} for k, v in s.head(n).items()]


def position_radar(pctl_row, pos):
    keys = POSITION_RADAR_KEYS.get(pos, [])
    out = []
    for k in keys:
        v = pctl_row.get(k)
        if v is None or pd.isna(v):
            continue
        out.append({"key": k, "label": METRIC_LABELS.get(k, k), "percentile": round(float(v), 1)})
    return out


def top3_styles(fit_all, pos, row_idx):
    fit = fit_all.get(pos)
    if fit is None or row_idx not in fit.index:
        return []
    row = fit.loc[row_idx].dropna().sort_values(ascending=False)
    return [{"style": name, "fit_z": round(float(v), 2)} for name, v in row.head(3).items()]


def style_evidence(Z_row, style, pos):
    feats = STYLES.get(pos, {}).get(style, (None, None))[0]
    if not feats:
        return {"top": [], "bottom": []}
    z = Z_row[feats].dropna().sort_values(ascending=False)
    if z.empty:
        return {"top": [], "bottom": []}
    label_map = {
        "shape_attpen": "박스 터치 비중", "shape_att3": "공격 3분의1 활동 비중", "shape_mid3": "중원 활동 비중",
        "shape_def3": "수비 3분의1 활동 비중", "shape_defpen": "자책 박스 활동 비중", "shape_shotrate": "슈팅 비중",
        "shape_takeon": "드리블 시도 비중", "shape_carry": "운반 비중", "shape_cross": "크로스 비중",
        "shape_long": "롱패스 비중", "shape_kp": "키패스 비중", "shape_aerial": "공중볼 경합량",
        "shape_tklvol": "태클량", "shape_clrvol": "클리어링량", "shape_passvol": "패스 관여도",
    }
    top = [{"label": label_map.get(k, k), "z": round(float(v), 2)} for k, v in z.head(2).items()]
    # 판별 축이 2개 이하면 top/bottom이 겹치므로 '약한 축'은 생략
    bottom = []
    if len(z) > 2:
        bottom = [{"label": label_map.get(k, k), "z": round(float(v), 2)} for k, v in z.tail(1).items()]
    return {"top": top, "bottom": bottom}


def _tier_tip(label, p):
    if p < 35:
        return f"{label} 개선 필요 — 기초 반복 훈련 권장 (현재 하위 {p:.0f}퍼센타일)"
    if p < 50:
        return f"{label} 안정화 단계 — 상황별 반복 훈련 (현재 {p:.0f}퍼센타일)"
    if p < 70:
        return f"{label} 강화 여지 — 난이도를 높인 반복 훈련 (현재 {p:.0f}퍼센타일)"
    return f"{label} 이미 강점 — 유지 및 응용 훈련 (상위 {100 - p:.0f}퍼센타일)"


def coaching_advice(pctl_row, style):
    keys = COACHING_KEYS.get(style, [])
    tips = []
    for k in keys:
        p = pctl_row.get(k)
        if p is None or pd.isna(p):
            continue
        tips.append(_tier_tip(METRIC_LABELS.get(k, k), float(p)))
    return tips


def growth_roadmap(pctl_row, style):
    keys = COACHING_KEYS.get(style, [])
    scored = [(k, pctl_row.get(k)) for k in keys if pctl_row.get(k) is not None and not pd.isna(pctl_row.get(k))]
    scored.sort(key=lambda x: x[1])  # 약점 먼저
    if not scored:
        return []

    def kpi_line(k, p):
        label = METRIC_LABELS.get(k, k)
        if p < 40:
            target = 60
        elif p < 60:
            target = 70
        elif p < 75:
            target = 80
        elif p < 90:
            target = 90
        else:
            return f"{label}: 이미 상위 {100 - p:.0f}퍼센타일 — 유지"
        return f"{label}: {p:.0f} → {target} 퍼센타일"

    phases = []
    if len(scored) >= 1:
        k, p = scored[0]
        phases.append({"phase": "0~6주", "focus": f"{METRIC_LABELS.get(k, k)} 기초 교정", "kpi": kpi_line(k, p)})
    if len(scored) >= 2:
        k, p = scored[1]
        phases.append({"phase": "6~12주", "focus": f"{METRIC_LABELS.get(k, k)} 실전 적용 반복", "kpi": kpi_line(k, p)})
    k, p = scored[-1]
    phases.append({"phase": "12주+", "focus": "강점 유지 및 상위 리그 수준 경쟁력 전이", "kpi": kpi_line(k, p)})
    return phases


def narrative_current(name, pos, ability, groups, style_primary, strengths, weaknesses):
    top_s = ", ".join(s["label"] for s in strengths[:3]) if strengths else "뚜렷한 항목 없음"
    top_w = ", ".join(w["label"] for w in weaknesses[:2]) if weaknesses else "뚜렷한 약점 없음"
    grp_sorted = sorted(groups.items(), key=lambda kv: -(kv[1] or 0))
    grp_label = {"prod": "생산", "progress": "전진", "chance": "찬스", "stability": "안정", "defense": "수비"}
    best_val = grp_sorted[0][1] if grp_sorted else None
    style_txt = f" 플레이스타일은 '{style_primary}'로 분류된다." if style_primary else ""
    if best_val is not None and best_val >= 60:
        best_group = grp_label.get(grp_sorted[0][0], grp_sorted[0][0])
        group_txt = f"가장 두드러지는 항목은 {best_group} 그룹이며, "
    else:
        group_txt = "그룹별 점수는 특별히 두드러지는 항목 없이 대체로 평이하며, "
    return (
        f"{name}({pos})의 현재 능력 점수는 {ability:.1f}점이다.{style_txt} "
        f"{group_txt}세부 강점은 {top_s} 순으로 나타난다. "
        f"상대적으로 보완이 필요한 부분은 {top_w}이다."
    )


def narrative_potential(name, kind, mu, ceiling, survival_prob, headroom):
    kind_txt = "2~3년 후 성장" if kind == "growth" else "2~3년 후 전성기 유지"
    surv_txt = "빅5 잔존확률" if kind == "growth" else "빅5 현역 유지확률"
    trend = "추가 성장" if headroom is not None and headroom > 5 else "현 수준 유지" if headroom is not None and headroom > -3 else "다소의 하락"
    return (
        f"{name}의 {kind_txt} 예측 중심값은 {mu:.1f}점, 80% 구간 상단(잠재력 상한)은 {ceiling:.1f}점이다. "
        f"{surv_txt}은 {survival_prob * 100:.1f}%로 추정된다. 종합하면 현재 대비 {trend} 경향으로 예측된다 "
        f"(단, 이 모델의 R²는 {'0.231' if kind == 'growth' else '0.502'}로 예측에는 상당한 불확실성이 남아있다)."
    )
