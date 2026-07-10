"""24세 초과 '베테랑' 코호트 라벨 생성 — U23 코호트(fpp_train_matrix_v2.csv)와
동일한 알고리즘(HANDOVER_DETAIL.md 4장)을 age_y>23 대상으로 재적용.

U23 모델을 나이 기준만 풀어 베테랑에 적용하는 건 학습 범위 밖 외삽이라
부정직하다 — 대신 같은 방법론으로 베테랑 전용 코호트/라벨을 새로 만들고,
07/08 스크립트에서 별도 모델을 처음부터 학습·검증한다.
"""
import pathlib
import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
from features import build_feature_matrix, MODEL_FEATURES

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

COHORT_YEARS = [2018, 2019, 2020]
AGE_MIN = 24  # U23 코호트(<=23)와 겹치지 않도록 24세부터
MIN_MINUTES = 900
FUTURE_OFFSETS = (2, 3)

if __name__ == "__main__":
    ability_df = pd.read_csv(DATA / "fpp_ability_v1_2018_2023.csv", low_memory=False)
    features_df = pd.read_csv(DATA / "fpp_features_clean_2018_2023.csv", low_memory=False)

    by_player = {fid: g.set_index("Season_End_Year") for fid, g in ability_df.groupby("fbref_id")}

    rows = []
    for year in COHORT_YEARS:
        cohort = ability_df[
            (ability_df["Season_End_Year"] == year)
            & (ability_df["age_y"] > AGE_MIN - 1)
            & (ability_df["std_Min_Playing"] >= MIN_MINUTES)
        ]
        feat = build_feature_matrix(features_df, ability_df, year)

        for _, row in cohort.iterrows():
            fid = row["fbref_id"]
            if fid not in feat.index:
                continue
            player_seasons = by_player.get(fid)
            future_abilities = []
            if player_seasons is not None:
                for off in FUTURE_OFFSETS:
                    fy = year + off
                    if fy in player_seasons.index:
                        fr = player_seasons.loc[fy]
                        if isinstance(fr, pd.DataFrame):
                            fr = fr.iloc[0]
                        if fr["std_Min_Playing"] >= MIN_MINUTES:
                            future_abilities.append(fr["ability"])
            survived = int(len(future_abilities) > 0)
            fut_ability = float(np.mean(future_abilities)) if future_abilities else np.nan

            feat_row = feat.loc[fid, MODEL_FEATURES].copy()
            feat_row["fbref_id"] = fid
            feat_row["season"] = year
            feat_row["survived"] = survived
            feat_row["fut_ability_v2"] = fut_ability
            rows.append(feat_row)

    out = pd.DataFrame(rows)
    out.to_csv(DATA / "fpp_train_matrix_veteran.csv", index=False)
    print("저장 완료:", out.shape, "->", DATA / "fpp_train_matrix_veteran.csv")
    print("연도별 n:", out["season"].value_counts().sort_index().to_dict())
    print("잔존율:", out["survived"].mean().round(3))
