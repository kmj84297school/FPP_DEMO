"""2023 스냅샷 행에 대해 fpp_train_matrix_v2.csv와 동일한 51피처를 재구성.

원본 train_matrix_v2.csv 생성 스크립트는 handover에 포함되어 있지 않아,
CLAUDE.md/HANDOVER_DETAIL.md에 문서화된 컬럼 정의와 실제 학습된 모델의
booster.feature_names(51개, 순서 고정)를 근거로 역산해 재구현한다.
"""
import numpy as np
import pandas as pd

MODEL_FEATURES = [
    "age_y", "std_Min_Playing", "grp_prod", "grp_progress", "grp_chance",
    "grp_stability", "grp_defense", "score_position", "score_style", "ability",
    "style_confidence", "npxG90", "xAG90", "SCA90", "PrgPass90", "PrgCarry90",
    "TakeOn90", "TklInt90", "AttPenT90", "KP90", "PassPct", "AerPct", "MinPct",
    "has_prev", "d_ability", "d_grp_prod", "d_grp_progress", "d_grp_chance",
    "d_grp_stability", "d_grp_defense", "d_npxG90", "d_xAG90", "d_SCA90",
    "d_PrgCarry90", "d_PrgPass90", "d_MinPct", "d_std_Min_Playing",
    "pos_DF", "pos_FW", "pos_MF",
    "sty_공격형 MF", "sty_공격형 풀백", "sty_돌파형 윙어", "sty_딥 플레이메이커",
    "sty_박스 포처", "sty_볼 운반형", "sty_빌드업 수비수", "sty_수비형 파괴자",
    "sty_스토퍼", "sty_연결형 공격수", "sty_타겟맨",
]

STYLE_NAMES = [c[4:] for c in MODEL_FEATURES if c.startswith("sty_")]

# 컬럼명: (원본 누적/비율 컬럼, per90 변환 필요 여부) — src/scoring_v1.py의 PER90/RATE와 동일 매핑
RAW90_SOURCE = {
    "npxG90": ("std_npxG_Expected", True),
    "xAG90": ("std_xAG_Expected", True),
    "SCA90": ("gca_SCA_SCA", True),
    "PrgPass90": ("pas_Prog", True),
    "PrgCarry90": ("pos_Prog_Carries", True),
    "TakeOn90": ("pos_Succ_Dribbles", True),
    "TklInt90": ("def_Tkl_plus_Int", True),
    "AttPenT90": ("pos_Att_Pen_Touches", True),
    "KP90": ("pas_KP", True),
    "PassPct": ("pas_Cmp_percent_Total", False),
    "AerPct": ("msc_Won_percent_Aerial", False),
    "MinPct": ("pt_Min_percent_Playing_Time", False),
}

PREV_SEASON_MIN = 600  # 전 시즌 자격(분) — 원 라벨 설계와 동일


def compute_raw90(features_df):
    df = features_df[["fbref_id", "Season_End_Year", "std_Min_Playing"] + [s for s, _ in RAW90_SOURCE.values()]].copy()
    n90 = (df["std_Min_Playing"] / 90).replace(0, np.nan)
    out = df[["fbref_id", "Season_End_Year"]].copy()
    for out_col, (src_col, needs_div) in RAW90_SOURCE.items():
        out[out_col] = df[src_col] / n90 if needs_div else df[src_col]
    return out


def build_feature_matrix(features_df, ability_df, target_year):
    """target_year 시즌 행에 대해 모델 입력 51피처 매트릭스 생성.

    features_df: data/fpp_features_clean_2018_2023.csv 전체 (raw per90 계산용)
    ability_df:  scoring_v1.build_scores() 출력, 전체 시즌
    반환: index=fbref_id, columns=MODEL_FEATURES + 참고용 메타 컬럼
    """
    raw = compute_raw90(features_df)
    base = ability_df.merge(raw, on=["fbref_id", "Season_End_Year"], how="left")

    cur = base[base["Season_End_Year"] == target_year].set_index("fbref_id").copy()
    prev = base[base["Season_End_Year"] == target_year - 1]
    prev = prev[prev["std_Min_Playing"] >= PREV_SEASON_MIN].set_index("fbref_id")

    cur["has_prev"] = cur.index.isin(prev.index).astype(int)

    delta_pairs = {
        "d_ability": "ability", "d_grp_prod": "grp_prod", "d_grp_progress": "grp_progress",
        "d_grp_chance": "grp_chance", "d_grp_stability": "grp_stability", "d_grp_defense": "grp_defense",
        "d_npxG90": "npxG90", "d_xAG90": "xAG90", "d_SCA90": "SCA90",
        "d_PrgCarry90": "PrgCarry90", "d_PrgPass90": "PrgPass90",
        "d_MinPct": "MinPct", "d_std_Min_Playing": "std_Min_Playing",
    }
    for dcol, base_col in delta_pairs.items():
        prev_vals = prev[base_col].reindex(cur.index)
        diff = cur[base_col] - prev_vals
        cur[dcol] = np.where(cur["has_prev"] == 1, diff, np.nan)

    for p in ("DF", "FW", "MF"):
        cur[f"pos_{p}"] = (cur["pos_primary"] == p).astype(int)
    for s in STYLE_NAMES:
        cur[f"sty_{s}"] = (cur["style"] == s).astype(int)

    meta_cols = ["Player", "pos_primary", "style", "Squads", "Comps"]
    return cur[MODEL_FEATURES + meta_cols].copy()


def reindex_for_model(feat_df, booster):
    """모델 학습 시 저장된 feature_names 순서로 정확히 재정렬 (컬럼 불일치 방지)."""
    names = booster.feature_names
    return feat_df.reindex(columns=names)
