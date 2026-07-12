"""베테랑(24세+) 대상 시즌 선수마다 실제 결과가 있는 과거 베테랑 선수(k=10) 검색."""
import sys, json, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build" / "lib"))

import pandas as pd

from knn import find_neighbors, DIST_COLS
from config import DATA, ABILITY_CSV, FEATURES_CURRENT_CSV, PRED_PEAK_CSV, KNN_PEAK_JSON

if __name__ == "__main__":
    preds = pd.read_csv(PRED_PEAK_CSV)
    eligible_ids = preds["fbref_id"]

    feat_all = pd.read_csv(FEATURES_CURRENT_CSV, index_col=0)
    query = feat_all.loc[feat_all.index.intersection(eligible_ids), DIST_COLS + ["pos_primary", "age_y"]].copy()

    pool = pd.read_csv(DATA / "fpp_train_matrix_veteran.csv")

    neighbors, low_conf = find_neighbors(pool, query, k=10, age_tol=2)

    labeled = pd.read_csv(ABILITY_CSV, low_memory=False)
    name_lookup = labeled.set_index(["fbref_id", "Season_End_Year"])[["Player", "Squads"]]

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

    with open(KNN_PEAK_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("저장 완료:", len(out), "명 ->", KNN_PEAK_JSON)
