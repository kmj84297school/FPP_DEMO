"""전체 시즌(2018~2023) 능력점수 산출 — src/scoring_v1.py::build_scores 재사용.
분위수 풀은 시즌x포지션 단위라 반드시 전체 시즌으로 계산해야 함.
"""
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
from scoring_v1 import build_scores

FEATURES_CSV = ROOT / "data" / "fpp_features_clean_2018_2023.csv"
OUT_CSV = ROOT / "data" / "fpp_ability_v1_2018_2023.csv"

if __name__ == "__main__":
    df = pd.read_csv(FEATURES_CSV, low_memory=False)
    res = build_scores(df)
    res.to_csv(OUT_CSV, index=False)
    print("저장 완료:", res.shape, "->", OUT_CSV)
