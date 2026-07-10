"""2023시즌 검색 가능 선수 전체에 대해 강점/약점, Top3 스타일, 코칭 제안,
성장 로드맵을 계산해 캐시에 저장.
"""
import sys, json, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build" / "lib"))

import pandas as pd

from report_extras import (
    compute_pctl_and_style_fit, top_strengths, top_weaknesses, position_radar,
    top3_styles, style_evidence, coaching_advice, growth_roadmap,
)

DATA = ROOT / "data"
CACHE = ROOT / "build" / "_cache"
TARGET_YEAR = 2023

if __name__ == "__main__":
    features_df = pd.read_csv(DATA / "fpp_features_clean_2018_2023.csv", low_memory=False)
    cur = features_df[features_df["Season_End_Year"] == TARGET_YEAR].copy().set_index("fbref_id", drop=False)

    elig = pd.read_csv(CACHE / "eligibility_2023.csv").set_index("fbref_id")
    searchable_ids = elig.index[elig["searchable"]]
    cur = cur.loc[cur.index.intersection(searchable_ids)]

    pctl, fit_all, Z = compute_pctl_and_style_fit(cur)

    ability_df = pd.read_csv(DATA / "fpp_ability_v1_2018_2023.csv", low_memory=False)
    style_lookup = ability_df[ability_df["Season_End_Year"] == TARGET_YEAR].set_index("fbref_id")["style"]

    out = {}
    for fid in cur.index:
        pos = cur.loc[fid, "pos_primary"]
        prow = pctl.loc[fid]
        primary_style = style_lookup.get(fid)
        t3 = top3_styles(fit_all, pos, fid)
        evidence = style_evidence(Z.loc[fid], primary_style, pos) if isinstance(primary_style, str) else {"top": [], "bottom": []}
        out[fid] = {
            "strengths": top_strengths(prow),
            "weaknesses": top_weaknesses(prow, pos),
            "position_radar": position_radar(prow, pos),
            "top3_styles": t3,
            "style_evidence": evidence,
            "coaching": coaching_advice(prow, primary_style) if isinstance(primary_style, str) else [],
            "roadmap": growth_roadmap(prow, primary_style) if isinstance(primary_style, str) else [],
        }

    with open(CACHE / "report_extras_2023.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("저장 완료:", len(out), "명 ->", CACHE / "report_extras_2023.json")
