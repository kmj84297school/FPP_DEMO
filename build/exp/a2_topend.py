"""A2 실험 — 상위권 외삽의 나머지 반: (1) 라벨 = 평균 vs 최댓값, (2) 정규 CI vs 분위수 회귀.

동일 코호트·동일 GroupKFold(선수 단위) 5겹. 회귀 타깃은 전부 Δ(라벨 − 현재).
채택 기준(프롬프트): 폴드 밖 커버리지(특히 현재능력 75+ 밴드)와 75+ 밴드 MAE.
결과: build/_cache/a2_topend.json
"""
import json, pathlib, sys
import numpy as np, pandas as pd
from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_absolute_error, r2_score
from xgboost import XGBRegressor

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "build" / "lib"))
from ensemble import fit_ensemble
from cohorts import LABEL_COLS
from config import DATA, CACHE

Z80, Z50 = 1.2816, 0.6745
B_BOOT = 30
TOP = 75
REG = {"u23": dict(n_estimators=150, max_depth=4, learning_rate=0.08, subsample=0.8, colsample_bytree=0.8),
       "veteran": dict(n_estimators=400, max_depth=4, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8)}
QS = [0.1, 0.25, 0.5, 0.75, 0.9]


def band_stats(y, mu, lo80, hi80, lo50, hi50, cur, tag):
    top = cur >= TOP
    def cov(m, lo, hi):
        return float(((y[m] >= lo[m]) & (y[m] <= hi[m])).mean()) if m.sum() else None
    return {
        f"{tag}_mae": round(mean_absolute_error(y, mu), 2), f"{tag}_r2": round(r2_score(y, mu), 3),
        f"{tag}_cov80": round(cov(np.ones_like(top), lo80, hi80), 3), f"{tag}_cov50": round(cov(np.ones_like(top), lo50, hi50), 3),
        f"{tag}_width80": round(float((hi80 - lo80).mean()), 1),
        f"{tag}_top_mae": round(mean_absolute_error(y[top], mu[top]), 2) if top.sum() else None,
        f"{tag}_top_bias": round(float((mu[top] - y[top]).mean()), 2) if top.sum() else None,
        f"{tag}_top_cov80": cov(top, lo80, hi80), f"{tag}_top_cov50": cov(top, lo50, hi50),
        f"{tag}_top_width80": round(float((hi80 - lo80)[top].mean()), 1) if top.sum() else None,
        f"{tag}_top_asym": round(float(((hi80 - mu) - (mu - lo80))[top].mean()), 2) if top.sum() else None,
        "n_top": int(top.sum()),
    }


def normal_ci_variant(S, Xcols, cfg, y, cur, gs, gkf):
    """현행 방식: 점추정 Δ 모델 + 부트스트랩 σ_model ⊕ 잔차 σ_resid, 정규 z 구간."""
    n = len(S); mu = np.full(n, np.nan); sm = np.full(n, np.nan)
    for tr, te in gkf.split(S, y, gs):
        models = fit_ensemble(S.iloc[tr][Xcols].astype(float), (y - cur)[tr], gs[tr], B=B_BOOT, seed=2026, params=cfg)
        P = np.stack([m.predict(S.iloc[te][Xcols].astype(float)) for m in models]) + cur[te]
        mu[te], sm[te] = P.mean(0), P.std(0)
    sig_r = float((y - mu).std())
    sig = np.sqrt(sm ** 2 + sig_r ** 2)
    return mu, mu - Z80 * sig, mu + Z80 * sig, mu - Z50 * sig, mu + Z50 * sig


def quantile_variant(S, Xcols, cfg, y, cur, gs, gkf):
    n = len(S); Q = np.full((n, len(QS)), np.nan)
    for tr, te in gkf.split(S, y, gs):
        m = XGBRegressor(random_state=2026, tree_method="hist", objective="reg:quantileerror",
                         quantile_alpha=np.array(QS), **cfg)
        m.fit(S.iloc[tr][Xcols].astype(float), (y - cur)[tr])
        Q[te] = m.predict(S.iloc[te][Xcols].astype(float)) + cur[te][:, None]
    Q = np.sort(Q, axis=1)  # 분위수 교차 방지(단조 정렬)
    return Q[:, 2], Q[:, 0], Q[:, 4], Q[:, 1], Q[:, 3]


if __name__ == "__main__":
    out = {}
    for b in ("u23", "veteran"):
        M = pd.read_csv(DATA / f"fpp_train_matrix_{b}.csv")
        Xcols = [c for c in M.columns if c not in LABEL_COLS]
        S = M[M["survived"] == 1].reset_index(drop=True)
        cur, gs = S["ability"].values, S["fbref_id"].values
        gkf = GroupKFold(5)
        labels = {"mean": S["fut_ability_v2"].values, "max": S["fut_ability_max"].values}
        print(f"\n[{b}] n={len(S)} | 라벨 평균 mean {labels['mean'].mean():.1f} p99 {np.percentile(labels['mean'],99):.1f} "
              f"| 최댓값 mean {labels['max'].mean():.1f} p99 {np.percentile(labels['max'],99):.1f} | 두 시즌 보유 {(S['fut_n']==2).mean():.0%}")
        res = {}
        for lab, y in labels.items():
            for method, fn in (("normal", normal_ci_variant), ("quantile", quantile_variant)):
                mu, lo80, hi80, lo50, hi50 = fn(S, Xcols, REG[b], y, cur, gs, gkf)
                st = band_stats(y, mu, lo80, hi80, lo50, hi50, cur, "v")
                # 교차 비교: 라벨 정의가 달라도 같은 관측(평균 라벨)에 대해 얼마나 맞는가
                st["mae_vs_mean_label"] = round(mean_absolute_error(labels["mean"], mu), 2)
                st["pred_max"] = round(float(mu.max()), 1)
                res[f"{lab}+{method}"] = st
                print(f"  {lab:>4}+{method:<8} MAE {st['v_mae']:.2f} R2 {st['v_r2']:.3f} cov80 {st['v_cov80']:.3f} cov50 {st['v_cov50']:.3f} w80 {st['v_width80']:>5} "
                      f"| 75+ (n={st['n_top']}) MAE {st['v_top_mae']} bias {st['v_top_bias']} cov80 {st['v_top_cov80']:.3f} w80 {st['v_top_width80']} asym {st['v_top_asym']}")
        out[b] = res
    json.dump(out, open(CACHE / "a2_topend.json", "w"), ensure_ascii=False, indent=1)
    print("\n저장:", CACHE / "a2_topend.json")
