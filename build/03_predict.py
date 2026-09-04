"""대상 시즌 스냅샷에 두 모델(성장기 U23 / 성숙기 24-38세)을 적용해
잔존확률·2~3년 후 예측 능력·신뢰구간을 산출.

회귀 모델은 Δ(변화량)를 예측하므로, 최종 예측 능력 = 현재 능력 + 예측 Δ.
이렇게 해야 학습 라벨 상한에 갇히지 않는다(07_train_models.py 주석 참조).
신뢰구간의 sigma_model도 Δ 앙상블의 산포에서 그대로 얻는다 — 상수를 더하는
것은 분산을 바꾸지 않으므로 레벨 스케일에서도 동일하다.
"""
import json
import pathlib
import sys

import numpy as np
import pandas as pd
import xgboost as xgb

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build" / "lib"))
sys.path.insert(0, str(ROOT / "src"))

from features import build_feature_matrix, reindex_for_model, MODEL_FEATURES
from ensemble import fit_ensemble, predict_ensemble
from config import (DATA, ABILITY_CSV, FEATURES_CSV, ELIGIBILITY_CSV, ELIGIBILITY_META,
                    FEATURES_CURRENT_CSV, PRED_GROWTH_CSV, PRED_PEAK_CSV,
                    VETERAN_META, TARGET_YEAR)

MODELS = ROOT / "models"
Z80, Z50 = 1.2816, 0.6745
VET_AGE_MIN, VET_AGE_MAX = 24, 38
ORIGINAL_PRED_MIN = 900


def predict_cohort(name, query, cur_ability, out_csv):
    reg = xgb.XGBRegressor(); reg.load_model(MODELS / f"xgb_delta_{name}.json")
    clf = xgb.XGBClassifier(); clf.load_model(MODELS / f"xgb_survival_{name}.json")

    Xr = reindex_for_model(query[MODEL_FEATURES], reg.get_booster())
    Xc = reindex_for_model(query[MODEL_FEATURES], clf.get_booster())
    mu = reg.predict(Xr) + cur_ability          # Δ 예측 → 레벨 환산
    survival_prob = clf.predict_proba(Xc)[:, 1]

    M = pd.read_csv(DATA / f"fpp_train_matrix_{name}.csv")
    S = M[M["survived"] == 1].reset_index(drop=True)
    Xcols = [c for c in S.columns if c not in ("fbref_id", "season", "survived", "fut_ability_v2")]
    y_delta = S["fut_ability_v2"].values - S["ability"].values
    print(f"  [{name}] 부트스트랩 앙상블 학습 (B=60)...")
    boot = fit_ensemble(S[Xcols].astype(float), y_delta, S["fbref_id"].values, B=60, seed=2026)
    _, sigma_model = predict_ensemble(boot, query[Xcols].astype(float))

    sigma_residual = float(np.load(MODELS / f"resid_sigma_{name}.npy"))
    sigma = np.sqrt(sigma_model ** 2 + sigma_residual ** 2)

    out = pd.DataFrame({
        "fbref_id": query.index,
        "mu": np.round(mu, 1),
        "survival_prob": np.round(survival_prob, 4),
        "sigma_model": np.round(sigma_model, 3),
        "sigma_residual": round(sigma_residual, 3),
        "sigma": np.round(sigma, 3),
        "lo80": np.round(mu - Z80 * sigma, 1), "hi80": np.round(mu + Z80 * sigma, 1),
        "lo50": np.round(mu - Z50 * sigma, 1), "hi50": np.round(mu + Z50 * sigma, 1),
    })
    out.to_csv(out_csv, index=False)
    print(f"  [{name}] 저장 완료: {out.shape} -> {out_csv}")


if __name__ == "__main__":
    ability_df = pd.read_csv(ABILITY_CSV, low_memory=False)
    features_df = pd.read_csv(FEATURES_CSV, low_memory=False)

    feat_all = build_feature_matrix(features_df, ability_df, TARGET_YEAR)
    feat_all.to_csv(FEATURES_CURRENT_CSV)
    print("features_current_all:", feat_all.shape)

    cur = ability_df[ability_df["Season_End_Year"] == TARGET_YEAR].set_index("fbref_id")
    cur_ability = cur["ability"]

    # 성장기(U23): 02단계의 eligible 판정 사용
    elig = pd.read_csv(ELIGIBILITY_CSV)
    growth_ids = elig.loc[elig["eligible_for_prediction"], "fbref_id"]
    gq = feat_all.loc[feat_all.index.intersection(growth_ids)]
    gq = gq.loc[cur_ability.reindex(gq.index).notna()]
    print("성장기 대상:", gq.shape)
    predict_cohort("u23", gq, cur_ability.reindex(gq.index).values, PRED_GROWTH_CSV)

    # 성숙기(24~38세): 동일 출전시간 임계 적용
    with open(ELIGIBILITY_META, encoding="utf-8") as f:
        meta = json.load(f)
    pred_min = round(ORIGINAL_PRED_MIN * meta["pred_min_minutes"] / meta["original_pred_min_minutes"])
    peak_ids = cur[(cur["age_y"] >= VET_AGE_MIN) & (cur["age_y"] <= VET_AGE_MAX)
                   & (cur["std_Min_Playing"] >= pred_min) & cur["ability"].notna()].index
    pq = feat_all.loc[feat_all.index.intersection(peak_ids)]
    print("성숙기 대상:", pq.shape, f"(임계 {pred_min}분)")
    predict_cohort("veteran", pq, cur_ability.reindex(pq.index).values, PRED_PEAK_CSV)

    with open(CACHE_META := VETERAN_META, "w", encoding="utf-8") as f:
        json.dump({"age_min": VET_AGE_MIN, "age_max": VET_AGE_MAX, "pred_min_minutes": pred_min}, f,
                  ensure_ascii=False, indent=1)
