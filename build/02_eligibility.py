"""2023시즌 행에 대해 검색 가능 여부(600분+)와 예측모델 적용 대상 여부
(age_y<=23 & std_Min_Playing>=900, 라벨 코호트 기준과 동일)를 판정.
"""
import pathlib
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
ABILITY_CSV = ROOT / "data" / "fpp_ability_v1_2018_2023.csv"
OUT_CSV = ROOT / "build" / "_cache" / "eligibility_2023.csv"

TARGET_YEAR = 2023
SEARCH_MIN = 600
PRED_AGE_MAX = 23
PRED_MIN = 900

if __name__ == "__main__":
    df = pd.read_csv(ABILITY_CSV, low_memory=False)
    cur = df[df["Season_End_Year"] == TARGET_YEAR].copy()

    cur["searchable"] = cur["std_Min_Playing"] >= SEARCH_MIN

    over_age = cur["age_y"] > PRED_AGE_MAX
    under_min = cur["std_Min_Playing"] < PRED_MIN
    cur["eligible_for_prediction"] = cur["searchable"] & ~over_age & ~under_min

    reasons = []
    for oa, um in zip(over_age, under_min):
        rs = []
        if oa:
            rs.append("over_age")
        if um:
            rs.append("under_minutes")
        reasons.append(";".join(rs) if rs else "")
    cur["reason"] = reasons

    out = cur[["fbref_id", "searchable", "eligible_for_prediction", "reason"]]
    out.to_csv(OUT_CSV, index=False)
    print("저장 완료:", out.shape, "->", OUT_CSV)
    print("searchable:", out["searchable"].sum(), "eligible_for_prediction:", out["eligible_for_prediction"].sum())
