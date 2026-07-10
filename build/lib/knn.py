"""유사 선수 k-NN — 실제 t+2~t+3 결과가 있는 라벨 코호트(fpp_train_matrix_v2.csv)를
이웃 풀로 사용해 2023 스냅샷 선수와 비슷한 과거 선수 k=10명을 찾는다.
"""
import numpy as np
import pandas as pd

DIST_COLS = [
    "grp_prod", "grp_progress", "grp_chance", "grp_stability", "grp_defense",
    "npxG90", "xAG90", "SCA90", "PrgPass90", "PrgCarry90", "TakeOn90",
    "TklInt90", "AttPenT90", "KP90", "PassPct", "AerPct", "MinPct",
]


def _zscore(df, cols):
    mu = df[cols].mean()
    sd = df[cols].std().replace(0, np.nan)
    return ((df[cols] - mu) / sd).fillna(0.0)


def pos_from_onehot(df):
    pos = pd.Series("", index=df.index)
    pos[df["pos_DF"] == 1] = "DF"
    pos[df["pos_FW"] == 1] = "FW"
    pos[df["pos_MF"] == 1] = "MF"
    return pos


def find_neighbors(pool, query, k=10, age_tol=1):
    """
    pool: fpp_train_matrix_v2.csv 로드본 (fbref_id, season, age_y, survived,
          fut_ability_v2, pos_DF/FW/MF, DIST_COLS 포함), 기본 인덱스.
    query: 2023 eligible 선수 feature matrix, index=fbref_id, pos_primary/age_y/
           DIST_COLS 포함.
    반환: (neighbors: {fbref_id: [dict,...]}, low_confidence: {fbref_id: bool})
    """
    pool = pool.copy()
    pool["pos_primary"] = pos_from_onehot(pool)
    pool_z = _zscore(pool, DIST_COLS)
    query_z = _zscore(query, DIST_COLS)

    neighbors, mean_dists = {}, {}
    for qid, qrow in query.iterrows():
        qz = query_z.loc[qid]
        cand_mask = (
            (pool["pos_primary"] == qrow["pos_primary"])
            & ((pool["age_y"] - qrow["age_y"]).abs() <= age_tol)
            & (pool["fbref_id"] != qid)
        )
        cand = pool[cand_mask]
        if cand.empty:
            neighbors[qid] = []
            mean_dists[qid] = np.nan
            continue
        cz = pool_z.loc[cand.index]
        dist = np.sqrt(((cz - qz) ** 2).sum(axis=1))
        top = dist.nsmallest(k)
        rows = []
        for idx, d in top.items():
            row = cand.loc[idx]
            rows.append({
                "fbref_id": row["fbref_id"],
                "season": int(row["season"]),
                "distance": round(float(d), 3),
                "survived": int(row["survived"]),
                "fut_ability_v2": None if pd.isna(row["fut_ability_v2"]) else round(float(row["fut_ability_v2"]), 1),
            })
        neighbors[qid] = rows
        mean_dists[qid] = top.mean()

    dist_series = pd.Series(mean_dists)
    threshold = dist_series.quantile(0.90)
    low_conf = (dist_series > threshold).fillna(False).to_dict()
    return neighbors, low_conf
