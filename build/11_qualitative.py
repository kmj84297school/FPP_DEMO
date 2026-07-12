"""데이터 기반 '정성 시그널' 산출 — 평판·태도·부상 같은 정성 항목 요청에 대해
이 데이터셋으로 정직하게 측정 가능한 세 가지 대리 지표를 계산한다.

1. 경기 내 규율(discipline): 경고/퇴장/파울 per90 — 시즌x포지션 풀 내 분위
   (낮을수록 클린). '태도'의 언론·구단 내부 정보가 아니라 경기 기록상 규율만 측정.
2. 가용성(availability): 시즌별 팀 출전시간 점유율(pt_Min_percent)의 다년 평균 —
   부상 기록 자체는 데이터에 없으므로 '부상 빈도'의 간접 프록시. 로테이션·이적과
   구분 불가함을 명시.
3. 꾸준함(consistency): 시즌 간 능력점수 표준편차 (자격 시즌 2개 이상일 때만).

Wikipedia 기반 평판/성향 분석(legacy)은 인계문서에 기록된 편향 결함(문서 부재 시
기본 100점) + 실시간 크롤링 의존 때문에 의도적으로 재도입하지 않는다.
"""
import json
import pathlib

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "build" / "lib"))
from config import FEATURES_CSV, ABILITY_CSV, ELIGIBILITY_CSV, QUALITATIVE_JSON, TARGET_YEAR

MIN_POOL = 600          # 분위 풀 자격(scoring_v1과 동일)
CONSISTENCY_MIN = {2023: 205}  # 2023은 부분 시즌이라 재환산 기준(205분), 그 외 600분
DEFAULT_CONSISTENCY_MIN = 600

DISC_COLS = ["std_CrdY", "std_CrdR", "msc_2CrdY", "msc_Fls"]

if __name__ == "__main__":
    usecols = ["fbref_id", "Season_End_Year", "pos_primary", "std_Min_Playing",
               "pt_Min_percent_Playing_Time"] + DISC_COLS
    feat = pd.read_csv(FEATURES_CSV, usecols=usecols, low_memory=False)
    ability = pd.read_csv(ABILITY_CSV,
                          usecols=["fbref_id", "Season_End_Year", "std_Min_Playing", "ability"], low_memory=False)

    elig = pd.read_csv(ELIGIBILITY_CSV).set_index("fbref_id")
    searchable_ids = set(elig.index[elig["searchable"]])

    cur = feat[feat["Season_End_Year"] == TARGET_YEAR].set_index("fbref_id", drop=False)
    cur = cur.loc[cur.index.intersection(searchable_ids)].copy()

    n90 = (cur["std_Min_Playing"] / 90).replace(0, np.nan)
    cur["crdy90"] = cur["std_CrdY"] / n90
    cur["fls90"] = cur["msc_Fls"] / n90
    cur["reds_total"] = cur["std_CrdR"].fillna(0) + cur["msc_2CrdY"].fillna(0)

    # 시즌x포지션 풀 내 분위 (scoring_v1과 동일: 600분+ 풀, 20명 미만이면 전체로 완화)
    cur["crdy90_pctl"] = np.nan
    cur["fls90_pctl"] = np.nan
    for pg, idx in cur.groupby("pos_primary").groups.items():
        pool = cur.loc[idx].index[cur.loc[idx, "std_Min_Playing"] >= MIN_POOL]
        if len(pool) < 20:
            pool = idx
        for src, dst in [("crdy90", "crdy90_pctl"), ("fls90", "fls90_pctl")]:
            ref = cur.loc[pool, src].dropna()
            if len(ref) < 10:
                continue
            sv = np.sort(ref.values)
            p = np.searchsorted(sv, cur.loc[idx, src].values, side="right") / len(sv) * 100
            cur.loc[idx, dst] = 100 - p  # 반전: 높을수록 클린

    # 가용성: 전 시즌 팀 출전시간 점유율 평균 (선수별)
    avail = (
        feat.groupby("fbref_id")["pt_Min_percent_Playing_Time"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "minpct_mean", "count": "n_seasons"})
    )

    # 꾸준함: 자격 시즌(부분 시즌은 205분+, 그 외 600분+) ability 표준편차
    ab = ability.copy()
    thr = ab["Season_End_Year"].map(CONSISTENCY_MIN).fillna(DEFAULT_CONSISTENCY_MIN)
    ab = ab[(ab["std_Min_Playing"] >= thr) & ab["ability"].notna()]
    cons = ab.groupby("fbref_id")["ability"].agg(["std", "count"]).rename(
        columns={"std": "ability_std", "count": "n_rated_seasons"})

    def nn(v, r=1):
        return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), r)

    out = {}
    for fid, row in cur.iterrows():
        a = avail.loc[fid] if fid in avail.index else None
        c = cons.loc[fid] if fid in cons.index else None
        n_rated = int(c["count"]) if c is not None and "count" in c else (int(c["n_rated_seasons"]) if c is not None else 0)
        out[fid] = {
            "discipline": {
                "yellows_per90": nn(row["crdy90"], 2),
                "fouls_per90": nn(row["fls90"], 2),
                "reds_total_season": nn(row["reds_total"], 0),
                "clean_pctl_cards": nn(row["crdy90_pctl"]),
                "clean_pctl_fouls": nn(row["fls90_pctl"]),
            },
            "availability": {
                "minpct_mean": nn(a["minpct_mean"]) if a is not None else None,
                "n_seasons": int(a["n_seasons"]) if a is not None else 0,
            },
            "consistency": {
                "ability_std": nn(c["ability_std"]) if c is not None else None,
                "n_rated_seasons": int(c["n_rated_seasons"]) if c is not None else 0,
            },
        }

    with open(QUALITATIVE_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("저장 완료:", len(out), "명 ->", QUALITATIVE_JSON)
