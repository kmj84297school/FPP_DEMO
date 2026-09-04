"""학습 코호트(U23 성장 / 베테랑) 생성 로직 — build/06_build_cohorts.py와
실험 스크립트(build/exp/*)가 같은 코드를 쓰도록 분리.

- 코호트 연도: t+2와 t+3이 둘 다 관측 가능한 해(2018~2022).
- 라벨(fut_ability_v2) = t+2·t+3 중 자격(900분+) 시즌의 능력점수 평균.
- survived = 자격 미래 시즌이 하나라도 있으면 1.
"""
import numpy as np
import pandas as pd

from features import build_feature_matrix, MODEL_FEATURES, SURVIVAL_EXTRA

COHORT_YEARS = [2018, 2019, 2020, 2021, 2022]
# 학습 행렬에서 피처가 아닌 열 — 07_train_models.py / 03_predict.py가 Xcols 선정 시 제외해야 한다.
LABEL_COLS = ("fbref_id", "season", "survived", "fut_ability_v2", "fut_ability_max", "fut_n")
FUTURE_OFFSETS = (2, 3)
MIN_MINUTES = 900
U23_AGE_MAX = 23
VET_AGE_MIN, VET_AGE_MAX = 24, 38


def build_cohorts(ability_df, features_df, extra_cols=(), verbose=True):
    """반환: {"u23": DataFrame, "veteran": DataFrame}. 컬럼 = MODEL_FEATURES + extra_cols
    + fbref_id/season/survived/fut_ability_v2."""
    by_player = {fid: g.set_index("Season_End_Year") for fid, g in ability_df.groupby("fbref_id")}
    rows = {"u23": [], "veteran": []}
    for year in COHORT_YEARS:
        cohort = ability_df[
            (ability_df["Season_End_Year"] == year)
            & (ability_df["std_Min_Playing"] >= MIN_MINUTES)
            & ability_df["ability"].notna()
        ]
        feat = build_feature_matrix(features_df, ability_df, year, extra_cols=extra_cols)
        keep = list(MODEL_FEATURES) + list(SURVIVAL_EXTRA) + [c for c in extra_cols if c not in SURVIVAL_EXTRA]

        for _, row in cohort.iterrows():
            age = row["age_y"]
            if pd.isna(age):
                continue
            if age <= U23_AGE_MAX:
                bucket = "u23"
            elif VET_AGE_MIN <= age <= VET_AGE_MAX:
                bucket = "veteran"
            else:
                continue
            fid = row["fbref_id"]
            if fid not in feat.index:
                continue

            seasons = by_player.get(fid)
            future = []
            if seasons is not None:
                for off in FUTURE_OFFSETS:
                    fy = year + off
                    if fy in seasons.index:
                        fr = seasons.loc[fy]
                        if isinstance(fr, pd.DataFrame):
                            fr = fr.iloc[0]
                        if fr["std_Min_Playing"] >= MIN_MINUTES and pd.notna(fr["ability"]):
                            future.append(fr["ability"])

            rec = feat.loc[fid, keep].copy()
            rec["fbref_id"] = fid
            rec["season"] = year
            rec["survived"] = int(len(future) > 0)
            rec["fut_ability_v2"] = float(np.mean(future)) if future else np.nan   # 평균 라벨(현행)
            rec["fut_ability_max"] = float(np.max(future)) if future else np.nan   # 최댓값 라벨(A2 비교용)
            rec["fut_n"] = len(future)
            rows[bucket].append(rec)
        if verbose:
            print(f"  {year} 처리 완료 (누적 u23={len(rows['u23'])}, veteran={len(rows['veteran'])})")
    return {b: pd.DataFrame(r) for b, r in rows.items()}
