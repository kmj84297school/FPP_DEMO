"""eligible(성장 예측) 선수마다 실제 t+2~t+3 결과가 있는 과거 선수(k=10) 검색."""
import sys, json, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build" / "lib"))

import pandas as pd

from knn import find_neighbors, DIST_COLS
from config import DATA, ELIGIBILITY_CSV, FEATURES_CURRENT_CSV, KNN_GROWTH_JSON

if __name__ == "__main__":
    feat_all = pd.read_csv(FEATURES_CURRENT_CSV, index_col=0)
    elig = pd.read_csv(ELIGIBILITY_CSV)
    eligible_ids = elig.loc[elig["eligible_for_prediction"], "fbref_id"]

    query = feat_all.loc[feat_all.index.intersection(eligible_ids), DIST_COLS + ["pos_primary", "age_y"]].copy()

    pool = pd.read_csv(DATA / "fpp_train_matrix_v2.csv")

    neighbors, low_conf = find_neighbors(pool, query, k=10, age_tol=1)

    labeled_base = pd.read_csv(DATA / "fpp_labeled_base.csv")
    name_lookup = labeled_base.set_index(["fbref_id", "Season_End_Year"])[["Player", "Squads"]]

    out = {}
    for fbref_id, rows in neighbors.items():
        enriched = []
        for r in rows:
            key = (r["fbref_id"], r["season"])
            name, squad = None, None
            if key in name_lookup.index:
                rec = name_lookup.loc[key]
                if isinstance(rec, pd.DataFrame):
                    rec = rec.iloc[0]
                name, squad = rec["Player"], rec["Squads"]
            enriched.append({**r, "player_name": name, "squad": squad})
        out[fbref_id] = {"neighbors": enriched, "low_confidence": bool(low_conf.get(fbref_id, False))}

    with open(KNN_GROWTH_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("저장 완료:", len(out), "명 ->", KNN_GROWTH_JSON)
