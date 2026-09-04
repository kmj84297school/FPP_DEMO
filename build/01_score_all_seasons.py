"""전체 시즌(2018~현재) 능력점수 산출.
분위수 풀은 시즌x포지션 단위라 반드시 전체 시즌으로 계산해야 함.

점수는 v1 산식 그대로(scoring_v2.build_scores(pool_by="pos", lens="pos")는 v1과 동일한
점수를 내고 role/role_axis 열만 덧붙인다 — 역할 단위 채점은 A1 실험에서 기각됨,
src/scoring_v2.py 문서 참조).
"""
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "build" / "lib"))

import pandas as pd
from scoring_v2 import build_scores
from config import FEATURES_CSV, ABILITY_CSV

if __name__ == "__main__":
    df = pd.read_csv(FEATURES_CSV, low_memory=False)
    res = build_scores(df, pool_by="pos", lens="pos")
    res.to_csv(ABILITY_CSV, index=False)
    print("저장 완료:", res.shape, "->", ABILITY_CSV)
