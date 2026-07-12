"""대상 시즌 스냅샷 중 U23 성장 예측 대상(eligible) 선수에 대해:
- 잔존확률 (models/xgb_survival_v2.json)
- 예측 미래능력 mu (models/xgb_ability_v2.json)
- 신뢰구간 (부트스트랩 앙상블 sigma_model + 저장된 sigma_residual 결합)
을 계산한다. 특징행렬(features_current_all.csv)은 후속 단계에서도 재사용된다.
"""
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build" / "lib"))
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd
import xgboost as xgb

from features import build_feature_matrix, reindex_for_model, MODEL_FEATURES
from ensemble import fit_ensemble, predict_ensemble
from config import (DATA, ABILITY_CSV, FEATURES_CSV, ELIGIBILITY_CSV,
                    FEATURES_CURRENT_CSV, PRED_GROWTH_CSV, TARGET_YEAR)

MODELS = ROOT / "models"
Z80, Z50 = 1.2816, 0.6745

if __name__ == "__main__":
    ability_df = pd.read_csv(ABILITY_CSV, low_memory=False)
    features_df = pd.read_csv(FEATURES_CSV, low_memory=False)
    elig = pd.read_csv(ELIGIBILITY_CSV)

    feat_all = build_feature_matrix(features_df, ability_df, TARGET_YEAR)
    feat_all.to_csv(FEATURES_CURRENT_CSV)
    print("features_current_all:", feat_all.shape)

    eligible_ids = elig.loc[elig["eligible_for_prediction"], "fbref_id"]
    query = feat_all.loc[feat_all.index.intersection(eligible_ids)].copy()
    print("eligible query rows:", query.shape)

    ability_model = xgb.XGBRegressor()
    ability_model.load_model(MODELS / "xgb_ability_v2.json")
    survival_model = xgb.XGBClassifier()
    survival_model.load_model(MODELS / "xgb_survival_v2.json")

    Xq_ability = reindex_for_model(query[MODEL_FEATURES], ability_model.get_booster())
    Xq_survival = reindex_for_model(query[MODEL_FEATURES], survival_model.get_booster())
    mu = ability_model.predict(Xq_ability)
    survival_prob = survival_model.predict_proba(Xq_survival)[:, 1]

    train_matrix = pd.read_csv(DATA / "fpp_train_matrix_v2.csv")
    survived = train_matrix[train_matrix["survived"] == 1].reset_index(drop=True)
    Xcols = [c for c in survived.columns if c not in ("fbref_id", "season", "survived", "fut_ability_v2")]
    Xtr = survived[Xcols].astype(float)
    ytr = survived["fut_ability_v2"].values
    groups = survived["fbref_id"].values

    print("부트스트랩 앙상블 학습 (B=60)...")
    models = fit_ensemble(Xtr, ytr, groups, B=60, seed=2026)

    Xq_ensemble = query[Xcols].astype(float)
    _, sigma_model = predict_ensemble(models, Xq_ensemble)

    sigma_residual = float(np.load(MODELS / "bootstrap_resid_sigma.npy"))
    sigma = np.sqrt(sigma_model ** 2 + sigma_residual ** 2)

    out = pd.DataFrame({
        "fbref_id": query.index,
        "mu": np.round(mu, 1),
        "survival_prob": np.round(survival_prob, 4),
        "sigma_model": np.round(sigma_model, 3),
        "sigma_residual": round(sigma_residual, 3),
        "sigma": np.round(sigma, 3),
        "lo80": np.round(mu - Z80 * sigma, 1),
        "hi80": np.round(mu + Z80 * sigma, 1),
        "lo50": np.round(mu - Z50 * sigma, 1),
        "hi50": np.round(mu + Z50 * sigma, 1),
    })
    out.to_csv(PRED_GROWTH_CSV, index=False)
    print("저장 완료:", out.shape, "->", PRED_GROWTH_CSV)
