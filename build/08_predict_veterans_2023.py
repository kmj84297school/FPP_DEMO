"""2023 스냅샷의 24세+ '베테랑' 선수에 대해 전성기 유지 예측
(현역 유지 확률 + 2~3년 후 예측 능력 + 신뢰구간)을 산출.
"""
import json
import pathlib
import sys

import numpy as np
import pandas as pd
import xgboost as xgb

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build" / "lib"))
from features import build_feature_matrix, reindex_for_model, MODEL_FEATURES
from ensemble import fit_ensemble, predict_ensemble

DATA = ROOT / "data"
MODELS = ROOT / "models"
CACHE = ROOT / "build" / "_cache"
TARGET_YEAR = 2023
AGE_MIN = 24
AGE_MAX = 38  # 학습 코호트에서 39세+ 표본이 극히 적어(n<=2) 제외
ORIGINAL_PRED_MIN = 900
Z80, Z50 = 1.2816, 0.6745

if __name__ == "__main__":
    ability_df = pd.read_csv(DATA / "fpp_ability_v1_2018_2023.csv", low_memory=False)
    features_df = pd.read_csv(DATA / "fpp_features_clean_2018_2023.csv", low_memory=False)

    with open(CACHE / "eligibility_meta.json", encoding="utf-8") as f:
        u23_meta = json.load(f)
    scale = u23_meta["pred_min_minutes"] / u23_meta["original_pred_min_minutes"]
    pred_min = round(ORIGINAL_PRED_MIN * scale)

    cur = ability_df[ability_df["Season_End_Year"] == TARGET_YEAR]
    elig_ids = cur[
        (cur["age_y"] >= AGE_MIN) & (cur["age_y"] <= AGE_MAX) & (cur["std_Min_Playing"] >= pred_min)
    ]["fbref_id"]

    feat_all = build_feature_matrix(features_df, ability_df, TARGET_YEAR)
    query = feat_all.loc[feat_all.index.intersection(elig_ids)].copy()
    print("베테랑 예측 대상:", query.shape, "(임계 출전시간:", pred_min, "분)")

    ability_model = xgb.XGBRegressor()
    ability_model.load_model(MODELS / "xgb_ability_veteran.json")
    survival_model = xgb.XGBClassifier()
    survival_model.load_model(MODELS / "xgb_survival_veteran.json")

    Xq_ability = reindex_for_model(query[MODEL_FEATURES], ability_model.get_booster())
    Xq_survival = reindex_for_model(query[MODEL_FEATURES], survival_model.get_booster())
    mu = ability_model.predict(Xq_ability)
    survival_prob = survival_model.predict_proba(Xq_survival)[:, 1]

    train_matrix = pd.read_csv(DATA / "fpp_train_matrix_veteran.csv")
    survived = train_matrix[train_matrix["survived"] == 1].reset_index(drop=True)
    Xcols = [c for c in survived.columns if c not in ("fbref_id", "season", "survived", "fut_ability_v2")]
    Xtr = survived[Xcols].astype(float)
    ytr = survived["fut_ability_v2"].values
    groups = survived["fbref_id"].values

    print("베테랑 부트스트랩 앙상블 학습 (B=60)...")
    models = fit_ensemble(Xtr, ytr, groups, B=60, seed=2026)
    Xq_ensemble = query[Xcols].astype(float)
    _, sigma_model = predict_ensemble(models, Xq_ensemble)

    sigma_residual = float(np.load(MODELS / "bootstrap_resid_sigma_veteran.npy"))
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
    out.to_csv(CACHE / "predictions_veteran_2023.csv", index=False)
    print("저장 완료:", out.shape, "->", CACHE / "predictions_veteran_2023.csv")

    meta = {
        "age_min": AGE_MIN, "age_max": AGE_MAX, "pred_min_minutes": pred_min,
        "auc": 0.726, "mae": 5.33, "r2": 0.502, "ci80_coverage": 0.826, "ci50_coverage": 0.520,
    }
    with open(CACHE / "veteran_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
