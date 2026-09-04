"""U23 성장 / 베테랑 두 코호트의 잔존분류기와 미래능력 회귀기를 학습·검증.

회귀 대상을 '미래 능력(레벨)'이 아니라 **변화량 Δ = 미래능력 - 현재능력**으로
둔다. 레벨을 직접 맞추면 트리 모델이 학습 라벨(최대 ~83, 99%tile ~76) 밖으로
외삽하지 못해, 현재 능력이 그보다 높은 최상위권 선수는 무조건 큰 폭의 하락으로
예측된다(실증 하락폭 -7인데 모델은 -16). Δ를 학습하고 그 선수의 실제 현재
점수에 더하면 이 구조적 상한이 사라진다.

3단계(2026-09) 변경:
- 하이퍼파라미터·피처셋은 build/hparams.json에서 읽는다(build/exp/a3a4_tune.py가
  GroupKFold 탐색 + 별도 분할 확인 후 기록). A4 보강 피처(팀 강도 대리변수·리그·선발
  비율·2년 출전 추세)가 잔존 AUC를 U23 0.69→0.74, 베테랑 0.73→0.76으로 올렸다.
- 점추정(mu)은 단일 모델이 아니라 **부트스트랩 앙상블 평균**을 쓴다(A2 실험에서
  같은 설정의 단일 모델보다 OOF MAE가 0.1~0.2 낮았다). 여기서는 단일/앙상블 OOF를
  둘 다 기록한다. 신뢰구간은 기존 설계 그대로 sigma_model ⊕ sigma_residual.
- 현재능력 75+ 밴드의 OOF 표본수·MAE·편향·커버리지를 기록해 사이트가 "검증범위 밖"
  경고에 실측값을 쓰게 한다.

검증은 전부 GroupKFold(선수 단위) 5겹.
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
from features import feature_set
from config import DATA, CACHE

MODELS = ROOT / "models"
Z80, Z50 = 1.2816, 0.6745
B_BOOT = 60
TOP = 75  # 상위 밴드 기준(원점수)

with open(ROOT / "build" / "hparams.json", encoding="utf-8") as f:
    HP = json.load(f)


def split_params(d):
    return {k: v for k, v in d.items() if k != "features"}, d["features"]


if __name__ == "__main__":
    metrics = {}
    for name in ("u23", "veteran"):
        M = pd.read_csv(DATA / f"fpp_train_matrix_{name}.csv")
        surv_p, surv_f = split_params(HP[name]["surv"])
        reg_p, reg_f = split_params(HP[name]["reg"])
        cols_s, cols_r = feature_set(surv_f), feature_set(reg_f)
        gkf = GroupKFold(5)

        # ── 잔존 분류 ──
        X, y_surv, g = M[cols_s].astype(float), M["survived"].values, M["fbref_id"].values
        aucs = []
        for tr, te in gkf.split(X, y_surv, g):
            m = XGBClassifier(random_state=2026, tree_method="hist", subsample=0.8, colsample_bytree=0.8, **surv_p)
            m.fit(X.iloc[tr], y_surv[tr])
            aucs.append(roc_auc_score(y_surv[te], m.predict_proba(X.iloc[te])[:, 1]))
        auc = float(np.mean(aucs))
        print(f"[{name}] 잔존분류 AUC = {auc:.3f} ± {np.std(aucs):.3f}  (n={len(M)}, 잔존율 {y_surv.mean():.3f}, 피처 {len(cols_s)})")

        # ── 미래능력 회귀 (Δ 학습, 레벨로 환산해 평가) ──
        S = M[M["survived"] == 1].reset_index(drop=True)
        Xs = S[cols_r].astype(float)
        cur = S["ability"].values
        y_level = S["fut_ability_v2"].values
        y_delta = y_level - cur
        gs = S["fbref_id"].values

        oof_single = np.full(len(S), np.nan)
        fold_preds = []
        for tr, te in gkf.split(Xs, y_delta, gs):
            m = XGBRegressor(random_state=2026, tree_method="hist", subsample=0.8, colsample_bytree=0.8, **reg_p)
            m.fit(Xs.iloc[tr], y_delta[tr])
            oof_single[te] = m.predict(Xs.iloc[te]) + cur[te]
            models = fit_ensemble(Xs.iloc[tr], y_delta[tr], gs[tr], B=B_BOOT, seed=2026, params=reg_p)
            preds = np.stack([mm.predict(Xs.iloc[te]) + cur[te] for mm in models], axis=0)
            fold_preds.append((te, preds))
        oof = np.full(len(S), np.nan); sm = np.full(len(S), np.nan)
        for te, p in fold_preds:
            oof[te], sm[te] = p.mean(axis=0), p.std(axis=0)
        mae_s, r2_s = mean_absolute_error(y_level, oof_single), r2_score(y_level, oof_single)
        mae, r2 = mean_absolute_error(y_level, oof), r2_score(y_level, oof)
        print(f"[{name}] 미래능력 회귀 단일 MAE {mae_s:.2f}/R² {r2_s:.3f} → 앙상블 평균 MAE = {mae:.2f}, R² = {r2:.3f}  (n={len(S)}, 예측 max {oof.max():.1f})")

        # ── 신뢰구간: 앙상블 σ_model ⊕ OOF 잔차 σ_residual ──
        resid = y_level - oof
        sig_r = float(resid.std())
        sig = np.sqrt(sm ** 2 + sig_r ** 2)
        in80 = (y_level >= oof - Z80 * sig) & (y_level <= oof + Z80 * sig)
        in50 = (y_level >= oof - Z50 * sig) & (y_level <= oof + Z50 * sig)
        c80, c50 = float(in80.mean()), float(in50.mean())
        top = cur >= TOP
        top_stats = {
            "n": int(top.sum()),
            "mae": round(float(np.abs(resid[top]).mean()), 2),
            "bias": round(float((oof[top] - y_level[top]).mean()), 2),
            "ci80_coverage": round(float(in80[top].mean()), 3),
        }
        print(f"[{name}] 잔차 sigma = {sig_r:.2f} | 커버리지 80% {c80:.1%} / 50% {c50:.1%} | 75+ 밴드 {top_stats}")

        # ── 최종 서빙 모델: 전체 데이터로 재학습 ──
        final_surv = XGBClassifier(random_state=2026, tree_method="hist", subsample=0.8, colsample_bytree=0.8, **surv_p)
        final_surv.fit(X, y_surv)
        final_surv.save_model(MODELS / f"xgb_survival_{name}.json")
        final_reg = XGBRegressor(random_state=2026, tree_method="hist", subsample=0.8, colsample_bytree=0.8, **reg_p)
        final_reg.fit(Xs, y_delta)
        final_reg.save_model(MODELS / f"xgb_delta_{name}.json")  # 참고용 단일 모델(서빙 mu는 03의 앙상블 평균)
        np.save(MODELS / f"resid_sigma_{name}.npy", sig_r)

        metrics[name] = {
            "auc": round(auc, 3), "auc_sd": round(float(np.std(aucs)), 3),
            "mae": round(mae, 2), "r2": round(r2, 3),
            "mae_single": round(mae_s, 2), "r2_single": round(r2_s, 3),
            "sigma_residual": round(sig_r, 2),
            "ci80_coverage": round(c80, 3), "ci50_coverage": round(c50, 3),
            "n_rows": int(len(M)), "n_labeled": int(len(S)),
            "survival_rate": round(float(y_surv.mean()), 3),
            "label_max": round(float(y_level.max()), 1),
            "label_p99": round(float(np.percentile(y_level, 99)), 1),
            "top_band": {"threshold_raw": TOP, **top_stats},
            "target": "delta", "point_estimate": "bootstrap_ensemble_mean",
            "hparams": HP[name], "n_features": {"survival": len(cols_s), "regression": len(cols_r)},
        }
        print()

    with open(CACHE / "model_metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=1)
    print("지표 저장:", CACHE / "model_metrics.json")
