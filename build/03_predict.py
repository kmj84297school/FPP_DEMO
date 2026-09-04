"""대상 시즌 스냅샷에 두 모델(성장기 U23 / 성숙기 24-38세)을 적용해
잔존확률·2~3년 후 예측 능력·신뢰구간을 산출.

회귀 모델은 Δ(변화량)를 예측하므로, 최종 예측 능력 = 현재 능력 + 예측 Δ.
이렇게 해야 학습 라벨 상한에 갇히지 않는다(07_train_models.py 주석 참조).
신뢰구간의 sigma_model도 Δ 앙상블의 산포에서 그대로 얻는다 — 상수를 더하는
것은 분산을 바꾸지 않으므로 레벨 스케일에서도 동일하다.

설명(A5): XGBoost의 pred_contribs(=TreeExplainer의 SHAP 값과 동치, 합이 예측과 정확히
일치)로 선수별 피처 기여도를 산출해 상위 5개 + 나머지 합 + 기준값(base)을 저장한다.
Δ 회귀는 능력점수 단위, 잔존 분류는 로그오즈 단위다.
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

from features import build_feature_matrix, reindex_for_model, MODEL_FEATURES, feature_set
from ensemble import fit_ensemble, predict_ensemble
from cohorts import LABEL_COLS
from config import (DATA, ABILITY_CSV, FEATURES_CSV, ELIGIBILITY_CSV, ELIGIBILITY_META,
                    FEATURES_CURRENT_CSV, PRED_GROWTH_CSV, PRED_PEAK_CSV,
                    VETERAN_META, TARGET_YEAR, SHAP_GROWTH_JSON, SHAP_PEAK_JSON)

MODELS = ROOT / "models"
with open(ROOT / "build" / "hparams.json", encoding="utf-8") as f:
    HP = json.load(f)
Z80, Z50 = 1.2816, 0.6745
VET_AGE_MIN, VET_AGE_MAX = 24, 38
ORIGINAL_PRED_MIN = 900


TOP_K_CONTRIB = 5


def contributions(boosters, X, top_k=TOP_K_CONTRIB):
    """행별 SHAP 기여도 → [{"base", "top": [{"feature","value","contrib"}...], "rest", "total"}]
    boosters가 여러 개면(앙상블) 기여도를 평균한다 — 평균의 SHAP = SHAP의 평균(가법성)."""
    D = xgb.DMatrix(X)
    C = np.mean([b.predict(D, pred_contribs=True) for b in boosters], axis=0)
    names = list(X.columns)
    out = []
    for i in range(len(X)):
        row, base = C[i, :-1], float(C[i, -1])
        order = np.argsort(-np.abs(row))[:top_k]
        top = []
        for j in order:
            v = X.iloc[i, j]
            top.append({"feature": names[j], "value": None if pd.isna(v) else round(float(v), 3),
                        "contrib": round(float(row[j]), 3)})
        rest = float(row.sum() - row[order].sum())
        out.append({"base": round(base, 3), "top": top, "rest": round(rest, 3),
                    "total": round(float(row.sum() + base), 3)})
    return out


def predict_cohort(name, query, cur_ability, out_csv, shap_json):
    surv_p = {k: v for k, v in HP[name]["surv"].items() if k != "features"}
    reg_p = {k: v for k, v in HP[name]["reg"].items() if k != "features"}
    cols_r = feature_set(HP[name]["reg"]["features"])
    clf = xgb.XGBClassifier(); clf.load_model(MODELS / f"xgb_survival_{name}.json")
    Xc = reindex_for_model(query, clf.get_booster())
    survival_prob = clf.predict_proba(Xc)[:, 1]

    # 점추정 mu = 부트스트랩 앙상블 평균 + 현재 능력 (07과 동일 설정·시드로 전체 데이터 재학습)
    M = pd.read_csv(DATA / f"fpp_train_matrix_{name}.csv")
    S = M[M["survived"] == 1].reset_index(drop=True)
    y_delta = S["fut_ability_v2"].values - S["ability"].values
    print(f"  [{name}] 부트스트랩 앙상블 학습 (B=60, 피처 {len(cols_r)})...")
    boot = fit_ensemble(S[cols_r].astype(float), y_delta, S["fbref_id"].values, B=60, seed=2026, params=reg_p)
    Xr = query[cols_r].astype(float)
    delta_mean, sigma_model = predict_ensemble(boot, Xr)
    mu = delta_mean + cur_ability

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

    # ── 설명(A5): Δ 회귀·잔존 분류 각각의 기여도 ──
    delta_c = contributions([m.get_booster() for m in boot], Xr)
    surv_c = contributions([clf.get_booster()], Xc)
    expl = {fid: {"delta": d, "survival": s} for fid, d, s in zip(query.index, delta_c, surv_c)}
    with open(shap_json, "w", encoding="utf-8") as f:
        json.dump(expl, f, ensure_ascii=False, indent=1)
    print(f"  [{name}] 기여도 저장: {len(expl)}명 -> {shap_json}")


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
    predict_cohort("u23", gq, cur_ability.reindex(gq.index).values, PRED_GROWTH_CSV, SHAP_GROWTH_JSON)

    # 성숙기(24~38세): 동일 출전시간 임계 적용
    with open(ELIGIBILITY_META, encoding="utf-8") as f:
        meta = json.load(f)
    pred_min = round(ORIGINAL_PRED_MIN * meta["pred_min_minutes"] / meta["original_pred_min_minutes"])
    peak_ids = cur[(cur["age_y"] >= VET_AGE_MIN) & (cur["age_y"] <= VET_AGE_MAX)
                   & (cur["std_Min_Playing"] >= pred_min) & cur["ability"].notna()].index
    pq = feat_all.loc[feat_all.index.intersection(peak_ids)]
    print("성숙기 대상:", pq.shape, f"(임계 {pred_min}분)")
    predict_cohort("veteran", pq, cur_ability.reindex(pq.index).values, PRED_PEAK_CSV, SHAP_PEAK_JSON)

    with open(CACHE_META := VETERAN_META, "w", encoding="utf-8") as f:
        json.dump({"age_min": VET_AGE_MIN, "age_max": VET_AGE_MAX, "pred_min_minutes": pred_min}, f,
                  ensure_ascii=False, indent=1)
