"""A1 보조 실험 — v2의 두 변경(역할 풀 / 역할 렌즈)을 분리해 어느 쪽이 지표를 흔드는지,
그리고 역할 판정이 시즌 간 얼마나 안정적인지 측정."""
import pathlib, sys, json
import numpy as np, pandas as pd
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "build" / "lib"))
import scoring_v2
from cohorts import build_cohorts
from features import MODEL_FEATURES
from config import FEATURES_CSV, CACHE
sys.path.insert(0, str(ROOT / "build" / "exp"))
from a1_compare import oof_metrics, CFG

feats = pd.read_csv(FEATURES_CSV, low_memory=False)
A = scoring_v2.build_scores(feats, pool_by="pos", lens="pos")  # = v1 + role
e = A[A["eligible"] & A["role"].notna()].sort_values(["fbref_id", "Season_End_Year"])
e["prev_role"] = e.groupby("fbref_id")["role"].shift(1)
e["prev_year"] = e.groupby("fbref_id")["Season_End_Year"].shift(1)
c = e[e["prev_year"] == e["Season_End_Year"] - 1]
same = (c["role"] == c["prev_role"]).mean()
print(f"연속 시즌 역할 유지율: {same:.3f} (n={len(c)})")
print(pd.crosstab(c["prev_role"], c["role"], normalize="index").round(2).to_string())
same_pos = (c["pos_primary"] == c.groupby("fbref_id")["pos_primary"].shift(1).reindex(c.index)).mean()

out = {"role_stability": round(float(same), 3)}
variants = {"pool=pos,lens=role": dict(pool_by="pos", lens="role"),
            "pool=role,lens=pos": dict(pool_by="role", lens="pos")}
for name, kw in variants.items():
    A = scoring_v2.build_scores(feats, **kw)
    C = build_cohorts(A, feats, verbose=False)
    out[name] = {b: oof_metrics(C[b], CFG[b], MODEL_FEATURES) for b in ("u23", "veteran")}
    for b, m in out[name].items():
        print(f"[{name}][{b}] AUC {m['auc']:.3f} MAE {m['mae']:.2f} R2 {m['r2']:.3f} 기저 {m['mae_baseline']:.2f} 75+ {m['mae_top75']} n75 {m['n_top75']}")
json.dump(out, open(CACHE / "a1_variants.json", "w"), ensure_ascii=False, indent=1)
