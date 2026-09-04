"""A1 보조 실험 2 — 점수는 v1 그대로 두고 '역할 라벨'만 하류에서 쓰는 두 용도 검증.
  (a) 역할 one-hot을 모델 피처로 추가 → OOF 지표
  (b) k-NN 후보 풀을 pos → role로 좁힘 → 이웃 평균 실측치의 예측력(LOO, MAE) 비교
"""
import pathlib, sys, json
import numpy as np, pandas as pd
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "build" / "lib")); sys.path.insert(0, str(ROOT / "build" / "exp"))
import scoring_v2
from cohorts import build_cohorts
from features import MODEL_FEATURES
from knn import DIST_COLS, _zscore
from config import FEATURES_CSV, CACHE
from a1_compare import oof_metrics, CFG

ROLES = list(scoring_v2.ROLE_W)
feats = pd.read_csv(FEATURES_CSV, low_memory=False)
A = scoring_v2.build_scores(feats, pool_by="pos", lens="pos")  # v1 점수 + role
C = build_cohorts(A, feats, extra_cols=("role",), verbose=False)
out = {}
for b in ("u23", "veteran"):
    M = C[b].copy()
    for r in ROLES:
        M[f"role_{r}"] = (M["role"] == r).astype(int)
    out[b] = {"v1": oof_metrics(M, CFG[b], MODEL_FEATURES),
              "v1+role": oof_metrics(M, CFG[b], MODEL_FEATURES + [f"role_{r}" for r in ROLES])}
    for k, m in out[b].items():
        print(f"[{b}][{k}] AUC {m['auc']:.3f} MAE {m['mae']:.2f} R2 {m['r2']:.3f} 75+ {m['mae_top75']}")

    # (b) k-NN LOO — 이웃 평균 fut_ability로 예측
    S = M[M["survived"] == 1].reset_index(drop=True)
    S["pos_primary"] = np.select([S.pos_DF == 1, S.pos_FW == 1, S.pos_MF == 1], ["DF", "FW", "MF"], "")
    Z = _zscore(S, DIST_COLS)
    res = {}
    for mode in ("pos", "role"):
        preds, fallback = [], 0
        for i, q in S.iterrows():
            base = (S["fbref_id"] != q["fbref_id"]) & ((S["age_y"] - q["age_y"]).abs() <= 1)
            cand = base & (S["role"] == q["role"]) if mode == "role" and pd.notna(q["role"]) else base & (S["pos_primary"] == q["pos_primary"])
            if mode == "role" and cand.sum() < 30:
                cand = base & (S["pos_primary"] == q["pos_primary"]); fallback += 1
            d = np.sqrt(((Z[cand] - Z.loc[i]) ** 2).sum(axis=1))
            top = d.nsmallest(10).index
            preds.append(S.loc[top, "fut_ability_v2"].mean())
        preds = np.array(preds)
        y = S["fut_ability_v2"].values
        res[mode] = {"mae": round(float(np.abs(preds - y).mean()), 2),
                     "mae_top75": round(float(np.abs(preds - y)[S["ability"] >= 75].mean()), 2),
                     "corr": round(float(np.corrcoef(preds, y)[0, 1]), 3), "fallback": fallback}
        print(f"[{b}] kNN LOO ({mode}): {res[mode]}")
    out[b]["knn"] = res
json.dump(out, open(CACHE / "a1_role_uses.json", "w"), ensure_ascii=False, indent=1)
