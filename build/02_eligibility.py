"""2023시즌 행에 대해 검색 가능 여부(600분+)와 예측모델 적용 대상 여부
(age_y<=23 & 출전시간 기준)를 판정.

600분(검색 가능)·900분(예측 대상) 기준은 둘 다 '풀 시즌(3,420분=38경기)
대비 몇 % 이상 뛴 선수라야 개인 per90 지표가 노이즈 없이 신뢰할 만한가'라는
동일한 성격의 상대적 출전 비율 컷(각각 17.5%, 26.3%)이다. 그런데 이
데이터셋의 2023시즌은 provider 교체 시점에 수집된 부분 시즌 스냅샷이라
최대 출전시간이 1,170분(=13경기)에 불과하다 (data/fpp_ability_v1_2018_2023.csv
실측: 2018~2022는 모두 3,420분이 상한, 2023만 1,170분). 두 기준을 절대값
그대로 적용하면 '13경기 중 51%/77% 출전'을 요구하는 셈이 되어 원래 의도
(풀 시즌 기준 17.5%/26.3%)보다 훨씬 가혹해지고, 상수적으로 검색·예측 대상
선수가 급감한다.
→ 두 기준 모두 동일한 상대 비율을 2023시즌 실제 상한(1,170분)에 다시
   적용해 재계산한다 (600→약 205분, 900→약 308분). 기준을 낮춘 게 아니라
   짧아진 관측 기간에 맞춰 같은 비율로 재환산한 것 — 근거는 docs 사이트에도
   노출.
"""
import json
import pathlib
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
ABILITY_CSV = ROOT / "data" / "fpp_ability_v1_2018_2023.csv"
OUT_CSV = ROOT / "build" / "_cache" / "eligibility_2023.csv"
META_JSON = ROOT / "build" / "_cache" / "eligibility_meta.json"

TARGET_YEAR = 2023
PRED_AGE_MAX = 23
ORIGINAL_SEARCH_MIN = 600
ORIGINAL_PRED_MIN = 900
FULL_SEASON_MINUTES = 3420  # 38경기 * 90분 (2018~2022 실측 상한과 일치)

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
    out.to_csv(OUT_CSV, index=False)

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
    with open(META_JSON, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)

    print("저장 완료:", out.shape, "->", OUT_CSV)
    print("meta:", meta)
    print("searchable:", out["searchable"].sum(), "eligible_for_prediction:", out["eligible_for_prediction"].sum())
