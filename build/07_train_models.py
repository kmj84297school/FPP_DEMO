"""U23 성장 / 베테랑 두 코호트의 잔존분류기와 미래능력 회귀기를 학습·검증.

회귀 대상을 '미래 능력(레벨)'이 아니라 **변화량 Δ = 미래능력 - 현재능력**으로
둔다. 레벨을 직접 맞추면 트리 모델이 학습 라벨(최대 ~83, 99%tile ~76) 밖으로
외삽하지 못해, 현재 능력이 그보다 높은 최상위권 선수는 무조건 큰 폭의 하락으로
예측된다(실증 하락폭 -7인데 모델은 -16). Δ를 학습하고 그 선수의 실제 현재
점수에 더하면 이 구조적 상한이 사라진다. OOF 비교에서 MAE·R²도 함께 개선됨을
확인하고 채택했다(레벨 5.98/0.296 → Δ 5.89/0.315, 베테랑 5.33/0.507 → 5.28/0.512).

검증은 전부 GroupKFold(선수 단위) 5겹이며, 지표는 비교 가능하도록 레벨 스케일로
환산해 보고한다. 신뢰구간은 기존 설계 그대로 부트스트랩 sigma_model과 잔차
sigma_residual을 결합한다.
"""
import json
import pathlib
import sys

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score, mean_absolute_error, r2_score
from xgboost import XGBClassifier, XGBRegressor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build" / "lib"))
from ensemble import fit_ensemble
from config import DATA, CACHE

MODELS = ROOT / "models"
Z80, Z50 = 1.2816, 0.6745
B_BOOT = 60

COHORTS = {
    "u23": {
        "matrix": DATA / "fpp_train_matrix_u23.csv",
        "surv": dict(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8),
        "reg": dict(n_estimators=150, max_depth=4, learning_rate=0.08, subsample=0.8, colsample_bytree=0.8),
    },
    "veteran": {
        "matrix": DATA / "fpp_train_matrix_veteran.csv",
        "surv": dict(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8),
        "reg": dict(n_estimators=400, max_depth=4, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8),
    },
}

if __name__ == "__main__":
    metrics = {}
    for name, cfg in COHORTS.items():
        M = pd.read_csv(cfg["matrix"])
        Xcols = [c for c in M.columns if c not in ("fbref_id", "season", "survived", "fut_ability_v2")]
        gkf = GroupKFold(5)

        # ── 잔존 분류 ──
        X, y_surv, g = M[Xcols].astype(float), M["survived"].values, M["fbref_id"].values
        aucs = []
        for tr, te in gkf.split(X, y_surv, g):
            m = XGBClassifier(random_state=2026, tree_method="hist", **cfg["surv"])
            m.fit(X.iloc[tr], y_surv[tr])
            aucs.append(roc_auc_score(y_surv[te], m.predict_proba(X.iloc[te])[:, 1]))
        auc = float(np.mean(aucs))
        print(f"[{name}] 잔존분류 AUC = {auc:.3f} ± {np.std(aucs):.3f}  (n={len(M)}, 잔존율 {y_surv.mean():.3f})")

        # ── 미래능력 회귀 (Δ 학습, 레벨로 환산해 평가) ──
        S = M[M["survived"] == 1].reset_index(drop=True)
        Xs = S[Xcols].astype(float)
        cur = S["ability"].values
        y_level = S["fut_ability_v2"].values
        y_delta = y_level - cur
        gs = S["fbref_id"].values

        oof = np.full(len(S), np.nan)
        for tr, te in gkf.split(Xs, y_delta, gs):
            m = XGBRegressor(random_state=2026, tree_method="hist", **cfg["reg"])
            m.fit(Xs.iloc[tr], y_delta[tr])
            oof[te] = m.predict(Xs.iloc[te]) + cur[te]
        mae, r2 = mean_absolute_error(y_level, oof), r2_score(y_level, oof)
        print(f"[{name}] 미래능력 회귀 MAE = {mae:.2f}, R² = {r2:.3f}  (n={len(S)}, 예측 max {oof.max():.1f})")

        # ── 부트스트랩 신뢰구간: OOF 앙상블로 sigma_model, 잔차로 sigma_residual ──
        fold_preds = []
        for tr, te in gkf.split(Xs, y_delta, gs):
            models = fit_ensemble(Xs.iloc[tr], y_delta[tr], gs[tr], B=B_BOOT, seed=2026)
            preds = np.stack([mm.predict(Xs.iloc[te]) + cur[te] for mm in models], axis=0)
            fold_preds.append((te, preds))
        resid = np.concatenate([y_level[te] - p.mean(axis=0) for te, p in fold_preds])
        sig_r = float(resid.std())
        cov80, cov50 = [], []
        for te, preds in fold_preds:
            mu, sm = preds.mean(axis=0), preds.std(axis=0)
            sig = np.sqrt(sm ** 2 + sig_r ** 2)
            yt = y_level[te]
            cov80.append(((yt >= mu - Z80 * sig) & (yt <= mu + Z80 * sig)).mean())
            cov50.append(((yt >= mu - Z50 * sig) & (yt <= mu + Z50 * sig)).mean())
        c80, c50 = float(np.mean(cov80)), float(np.mean(cov50))
        print(f"[{name}] 잔차 sigma = {sig_r:.2f} | 구간 커버리지 80% 실측 {c80:.1%} / 50% 실측 {c50:.1%}")

        # ── 최종 서빙 모델: 전체 데이터로 재학습 ──
        final_surv = XGBClassifier(random_state=2026, tree_method="hist", **cfg["surv"])
        final_surv.fit(X, y_surv)
        final_surv.save_model(MODELS / f"xgb_survival_{name}.json")
        final_reg = XGBRegressor(random_state=2026, tree_method="hist", **cfg["reg"])
        final_reg.fit(Xs, y_delta)
        final_reg.save_model(MODELS / f"xgb_delta_{name}.json")
        np.save(MODELS / f"resid_sigma_{name}.npy", sig_r)

        metrics[name] = {
            "auc": round(auc, 3), "mae": round(mae, 2), "r2": round(r2, 3),
            "sigma_residual": round(sig_r, 2),
            "ci80_coverage": round(c80, 3), "ci50_coverage": round(c50, 3),
            "n_rows": int(len(M)), "n_labeled": int(len(S)),
            "survival_rate": round(float(y_surv.mean()), 3),
            "label_max": round(float(y_level.max()), 1),
            "label_p99": round(float(np.percentile(y_level, 99)), 1),
            "target": "delta",
        }
        print()

    with open(CACHE / "model_metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=1)
    print("지표 저장:", CACHE / "model_metrics.json")
