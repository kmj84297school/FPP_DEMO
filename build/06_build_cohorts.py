"""U23 성장 / 베테랑(24세+) 학습 코호트를 함께 생성.

기존에는 코호트 연도가 2018~2020뿐이었다. 원 데이터셋이 2023에서 끝나
t+2·t+3을 관측할 수 있는 시즌이 거기까지였기 때문이다. 2023-24·2024-25를
반입하면서 2021·2022 코호트도 만들 수 있게 되어 학습량이 늘어난다.

로직 본체는 build/lib/cohorts.py (실험 스크립트와 공유).
"""
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
from cohorts import build_cohorts
from config import DATA, ABILITY_CSV, FEATURES_CSV

OUT = {"u23": DATA / "fpp_train_matrix_u23.csv",
       "veteran": DATA / "fpp_train_matrix_veteran.csv"}

if __name__ == "__main__":
    ability_df = pd.read_csv(ABILITY_CSV, low_memory=False)
    features_df = pd.read_csv(FEATURES_CSV, low_memory=False)
    mats = build_cohorts(ability_df, features_df)
    for bucket, path in OUT.items():
        df = mats[bucket]
        df.to_csv(path, index=False)
        surv = df[df["survived"] == 1]
        print(f"[{bucket}] {df.shape} -> {path}")
        print(f"   연도별 {df['season'].value_counts().sort_index().to_dict()}")
        print(f"   잔존율 {df['survived'].mean():.3f} | 라벨 n={len(surv)} "
              f"max {surv['fut_ability_v2'].max():.1f} 99%tile {surv['fut_ability_v2'].quantile(.99):.1f}")
