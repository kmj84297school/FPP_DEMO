"""베테랑(24세+) 전용 잔존분류/미래능력회귀 모델 학습 — U23 모델과 동일한
구조(XGBoost, GroupKFold 5겹 검증)를 fpp_train_matrix_veteran.csv에 재적용.

검증 수치는 U23 모델보다 나빠도 그대로 기록한다 (원 설계 원칙: 성능은
검증 방법과 함께 정직하게 기록).
"""
import pathlib
import sys

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score, mean_absolute_error, r2_score
from xgboost import XGBClassifier, XGBRegressor

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build" / "lib"))
from ensemble import fit_ensemble, predict_ensemble

DATA = ROOT / "data"
MODELS = ROOT / "models"

M = pd.read_csv(DATA / "fpp_train_matrix_veteran.csv")
Xcols = [c for c in M.columns if c not in ("fbref_id", "season", "survived", "fut_ability_v2")]

SURV_PARAMS = dict(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8, tree_method="hist")
ABIL_PARAMS = dict(n_estimators=400, max_depth=4, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8, tree_method="hist")

if __name__ == "__main__":
    X, g = M[Xcols].astype(float), M["fbref_id"].values
    y_surv = M["survived"].values

    gkf = GroupKFold(5)
    aucs = []
    for tr, te in gkf.split(X, y_surv, g):
        m = XGBClassifier(random_state=2026, **SURV_PARAMS)
        m.fit(X.iloc[tr], y_surv[tr])
        p = m.predict_proba(X.iloc[te])[:, 1]
        aucs.append(roc_auc_score(y_surv[te], p))
    print(f"[베테랑 잔존분류] GroupKFold 5겹 AUC = {np.mean(aucs):.3f} ± {np.std(aucs):.3f}")

    S = M[M["survived"] == 1].reset_index(drop=True)
    Xs, ys, gs = S[Xcols].astype(float), S["fut_ability_v2"].values, S["fbref_id"].values
    maes, r2s = [], []
    for tr, te in gkf.split(Xs, ys, gs):
        m = XGBRegressor(random_state=2026, **ABIL_PARAMS)
        m.fit(Xs.iloc[tr], ys[tr])
        p = m.predict(Xs.iloc[te])
        maes.append(mean_absolute_error(ys[te], p))
        r2s.append(r2_score(ys[te], p))
    print(f"[베테랑 미래능력 회귀] GroupKFold 5겹 MAE = {np.mean(maes):.2f} ± {np.std(maes):.2f}, R² = {np.mean(r2s):.3f} ± {np.std(r2s):.3f}")

    # 최종 서빙용: 전체 데이터로 재학습
    final_surv = XGBClassifier(random_state=2026, **SURV_PARAMS)
    final_surv.fit(X, y_surv)
    final_surv.save_model(MODELS / "xgb_survival_veteran.json")

    final_abil = XGBRegressor(random_state=2026, **ABIL_PARAMS)
    final_abil.fit(Xs, ys)
    final_abil.save_model(MODELS / "xgb_ability_veteran.json")

    # 부트스트랩 신뢰구간용 잔차 sigma (out-of-fold, boot_ci.py와 동일 절차)
    fold_preds = []
    for tr, te in gkf.split(Xs, ys, gs):
        models = fit_ensemble(Xs.iloc[tr], ys[tr], gs[tr], B=60, seed=2026)
        _, _ = None, None
        preds = np.stack([m.predict(Xs.iloc[te]) for m in models], axis=0)
        fold_preds.append((te, preds))
    resid = np.concatenate([ys[te] - p.mean(axis=0) for te, p in fold_preds])
    sig_r = resid.std()
    np.save(MODELS / "bootstrap_resid_sigma_veteran.npy", sig_r)
    print(f"[베테랑 부트스트랩] 잔차 sigma = {sig_r:.2f}")

    z80, z50 = 1.2816, 0.6745
    cov80, cov50 = [], []
    for te, preds in fold_preds:
        yt = ys[te]
        mu, sm = preds.mean(axis=0), preds.std(axis=0)
        sig = np.sqrt(sm ** 2 + sig_r ** 2)
        cov80.append(((yt >= mu - z80 * sig) & (yt <= mu + z80 * sig)).mean())
        cov50.append(((yt >= mu - z50 * sig) & (yt <= mu + z50 * sig)).mean())
    print(f"[베테랑 구간 커버리지] 80% 실측 {np.mean(cov80):.1%} | 50% 실측 {np.mean(cov50):.1%}")
