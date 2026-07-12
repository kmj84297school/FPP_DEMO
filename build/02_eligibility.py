"""대상 시즌 행에 대해 검색 가능 여부와 예측모델 적용 대상 여부를 판정.

600분(검색 가능)·900분(예측 대상) 기준은 둘 다 '풀 시즌(3,420분=38경기)
대비 몇 % 이상 뛴 선수라야 개인 per90 지표가 노이즈 없이 신뢰할 만한가'라는
동일한 성격의 상대적 출전 비율 컷(각각 17.5%, 26.3%)이다. 대상 시즌이
부분 시즌(최대 출전시간이 풀 시즌의 90% 미만)으로 감지되면 두 기준을 같은
비율로 재환산한다 — 2023 스냅샷 시절 실제로 사용된 로직이며, 풀 시즌이면
원 기준을 그대로 쓴다.
"""
import json
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))

import pandas as pd

from config import ABILITY_CSV, ELIGIBILITY_CSV, ELIGIBILITY_META, TARGET_YEAR

PRED_AGE_MAX = 23
ORIGINAL_SEARCH_MIN = 600
ORIGINAL_PRED_MIN = 900
FULL_SEASON_MINUTES = 3420  # 38경기 * 90분

if __name__ == "__main__":
    df = pd.read_csv(ABILITY_CSV, low_memory=False)
    cur = df[df["Season_End_Year"] == TARGET_YEAR].copy()

    season_max_minutes = float(cur["std_Min_Playing"].max())
    is_partial_season = season_max_minutes < FULL_SEASON_MINUTES * 0.9
    scale = (season_max_minutes / FULL_SEASON_MINUTES) if is_partial_season else 1.0
    search_min = round(ORIGINAL_SEARCH_MIN * scale)
    pred_min = round(ORIGINAL_PRED_MIN * scale)

    cur["searchable"] = cur["std_Min_Playing"] >= search_min

    over_age = cur["age_y"] > PRED_AGE_MAX
    under_min = cur["std_Min_Playing"] < pred_min
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
    out.to_csv(ELIGIBILITY_CSV, index=False)

    meta = {
        "target_year": TARGET_YEAR,
        "search_min_minutes": search_min,
        "original_search_min_minutes": ORIGINAL_SEARCH_MIN,
        "pred_age_max": PRED_AGE_MAX,
        "pred_min_minutes": pred_min,
        "original_pred_min_minutes": ORIGINAL_PRED_MIN,
        "season_max_minutes": season_max_minutes,
        "full_season_minutes": FULL_SEASON_MINUTES,
        "is_partial_season": bool(is_partial_season),
    }
    with open(ELIGIBILITY_META, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)

    print("저장 완료:", out.shape, "->", ELIGIBILITY_CSV)
    print("meta:", meta)
    print("searchable:", out["searchable"].sum(), "eligible_for_prediction:", out["eligible_for_prediction"].sum())
