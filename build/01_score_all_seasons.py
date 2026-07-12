"""전체 시즌(2018~현재) 능력점수 산출 — src/scoring_v1.py::build_scores 재사용.
분위수 풀은 시즌x포지션 단위라 반드시 전체 시즌으로 계산해야 함.
"""
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "build" / "lib"))

import pandas as pd
from scoring_v1 import build_scores
from config import FEATURES_CSV, ABILITY_CSV

if __name__ == "__main__":
    df = pd.read_csv(FEATURES_CSV, low_memory=False)
    res = build_scores(df)
    res.to_csv(ABILITY_CSV, index=False)
    print("저장 완료:", res.shape, "->", ABILITY_CSV)
