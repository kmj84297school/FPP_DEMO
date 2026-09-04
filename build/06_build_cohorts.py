"""U23 성장 / 베테랑(24세+) 학습 코호트를 함께 생성.

기존에는 코호트 연도가 2018~2020뿐이었다. 원 데이터셋이 2023에서 끝나
t+2·t+3을 관측할 수 있는 시즌이 거기까지였기 때문이다. 2023-24·2024-25를
반입하면서 2021·2022 코호트도 만들 수 있게 되어 학습량이 늘어난다.

- 코호트 연도: t+2와 t+3이 **둘 다** 관측 가능한 해만 사용(2018~2022).
  2023은 t+3(2026)이 없어 잔존 판정이 짧은 창으로 왜곡되므로 제외한다.
- 라벨(fut_ability_v2) = t+2·t+3 중 자격(900분+) 시즌의 능력점수 평균.
  한 시즌만 자격이면 그 시즌 값. (원 설계와 동일)
- survived = 자격 미래 시즌이 하나라도 있으면 1.
- 피처는 build/lib/features.py로 코호트 연도마다 생성 후 이어붙인다.
"""
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
from features import build_feature_matrix, MODEL_FEATURES
from config import DATA, ABILITY_CSV, FEATURES_CSV

COHORT_YEARS = [2018, 2019, 2020, 2021, 2022]
FUTURE_OFFSETS = (2, 3)
MIN_MINUTES = 900
U23_AGE_MAX = 23
VET_AGE_MIN, VET_AGE_MAX = 24, 38

OUT = {"u23": DATA / "fpp_train_matrix_u23.csv",
       "veteran": DATA / "fpp_train_matrix_veteran.csv"}

if __name__ == "__main__":
    ability_df = pd.read_csv(ABILITY_CSV, low_memory=False)
    features_df = pd.read_csv(FEATURES_CSV, low_memory=False)
    by_player = {fid: g.set_index("Season_End_Year") for fid, g in ability_df.groupby("fbref_id")}

    rows = {"u23": [], "veteran": []}
    for year in COHORT_YEARS:
        cohort = ability_df[
            (ability_df["Season_End_Year"] == year)
            & (ability_df["std_Min_Playing"] >= MIN_MINUTES)
            & ability_df["ability"].notna()
        ]
        feat = build_feature_matrix(features_df, ability_df, year)

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

            rec = feat.loc[fid, MODEL_FEATURES].copy()
            rec["fbref_id"] = fid
            rec["season"] = year
            rec["survived"] = int(len(future) > 0)
            rec["fut_ability_v2"] = float(np.mean(future)) if future else np.nan
            rows[bucket].append(rec)
        print(f"  {year} 처리 완료 (누적 u23={len(rows['u23'])}, veteran={len(rows['veteran'])})")

    for bucket, path in OUT.items():
        df = pd.DataFrame(rows[bucket])
        df.to_csv(path, index=False)
        surv = df[df["survived"] == 1]
        print(f"[{bucket}] {df.shape} -> {path}")
        print(f"   연도별 {df['season'].value_counts().sort_index().to_dict()}")
        print(f"   잔존율 {df['survived'].mean():.3f} | 라벨 n={len(surv)} "
              f"max {surv['fut_ability_v2'].max():.1f} 99%tile {surv['fut_ability_v2'].quantile(.99):.1f}")
