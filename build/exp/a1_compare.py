"""A1 실험 — 능력점수 v1(포지션 3종) vs v2(역할 7종) 정면 비교.

채택 기준(NEXT_PHASE_PROMPT 규칙): 폴드 밖 지표가 나빠지면 채택하지 않는다.
비교 항목
  1. 역할 판정 건전성: 시즌별 역할 비율, 알려진 선수 표본 확인
  2. 포지션 간 분산 불일치: 능력점수 sd (v1: pos 단위, v2: role 단위)
  3. 하류 모델 OOF 지표: 동일 코호트 규칙·동일 GroupKFold로
     잔존 AUC / Δ회귀 MAE·R² / 기저모델(미래=현재) MAE / 75+ 밴드 MAE
     변형: v1 / v2(51피처) / v2+role one-hot(58피처)
결과는 build/_cache/a1_compare.json 과 표준출력.
"""
import json
import pathlib
import sys

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score, mean_absolute_error, r2_score
from xgboost import XGBClassifier, XGBRegressor

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "build" / "lib"))
import scoring_v1, scoring_v2
from cohorts import build_cohorts
from features import MODEL_FEATURES
from config import FEATURES_CSV, CACHE

CFG = {
    "u23": dict(surv=dict(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8),
                reg=dict(n_estimators=150, max_depth=4, learning_rate=0.08, subsample=0.8, colsample_bytree=0.8)),
    "veteran": dict(surv=dict(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8),
                    reg=dict(n_estimators=400, max_depth=4, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8)),
}
KNOWN = {  # fbref_id: (이름, 기대 역할) — 2023 시즌 기준 눈으로 확인
    "Trent Alexander-Arnold": "FB", "Virgil van Dijk": "CB", "Rodri": "DM", "Kevin De Bruyne": "AM",
    "Erling Haaland": "ST", "Vinicius Júnior": "W", "Bukayo Saka": "W", "Harry Kane": "ST",
    "Joshua Kimmich": "CM", "Casemiro": "DM", "Rúben Dias": "CB", "Achraf Hakimi": "FB",
    "Bruno Fernandes": "AM", "Martin Ødegaard": "AM", "Robert Lewandowski": "ST", "Kylian Mbappé": "W",
}
ROLES = list(scoring_v2.ROLE_W)


def oof_metrics(M, cfg, feat_cols):
    X, y_surv, g = M[feat_cols].astype(float), M["survived"].values, M["fbref_id"].values
    gkf = GroupKFold(5)
    aucs = []
    for tr, te in gkf.split(X, y_surv, g):
        m = XGBClassifier(random_state=2026, tree_method="hist", **cfg["surv"])
        m.fit(X.iloc[tr], y_surv[tr])
        aucs.append(roc_auc_score(y_surv[te], m.predict_proba(X.iloc[te])[:, 1]))
    S = M[M["survived"] == 1].reset_index(drop=True)
    Xs, cur, y = S[feat_cols].astype(float), S["ability"].values, S["fut_ability_v2"].values
    gs = S["fbref_id"].values
    oof = np.full(len(S), np.nan)
    for tr, te in gkf.split(Xs, y - cur, gs):
        m = XGBRegressor(random_state=2026, tree_method="hist", **cfg["reg"])
        m.fit(Xs.iloc[tr], (y - cur)[tr])
        oof[te] = m.predict(Xs.iloc[te]) + cur[te]
    top = cur >= 75
    return {
        "auc": round(float(np.mean(aucs)), 3), "auc_sd": round(float(np.std(aucs)), 3),
        "mae": round(mean_absolute_error(y, oof), 2), "r2": round(r2_score(y, oof), 3),
        "mae_baseline": round(mean_absolute_error(y, cur), 2),
        "mae_top75": round(mean_absolute_error(y[top], oof[top]), 2) if top.sum() else None,
        "n_top75": int(top.sum()), "n": int(len(M)), "n_labeled": int(len(S)),
        "label_p99": round(float(np.percentile(y, 99)), 1), "label_max": round(float(y.max()), 1),
    }


if __name__ == "__main__":
    feats = pd.read_csv(FEATURES_CSV, low_memory=False)
    print("scoring v1 ..."); A1 = scoring_v1.build_scores(feats)
    print("scoring v2 ..."); A2 = scoring_v2.build_scores(feats)
    out = {}

    # 1) 역할 비율 / 알려진 선수
    elig = A2[A2["eligible"]]
    prop = pd.crosstab(elig["Season_End_Year"], elig["role"], normalize="index").round(3)
    print("\n[역할 비율(시즌별, 600분+)]\n", prop.to_string())
    out["role_share_by_season"] = prop.to_dict(orient="index")
    latest = A2[(A2["Season_End_Year"] == 2023) & A2["eligible"]]
    checks = []
    for name, exp in KNOWN.items():
        r = latest[latest["Player"] == name]
        got = r["role"].iloc[0] if len(r) else None
        axis = float(r["role_axis"].iloc[0]) if len(r) else None
        checks.append({"player": name, "expected": exp, "got": got, "axis": axis, "ok": got == exp})
    print("\n[알려진 선수 역할 판정 — 2023]")
    for c in checks:
        print(f"  {'OK ' if c['ok'] else 'NG '} {c['player']:<24} 기대 {c['expected']:<3} 판정 {c['got']}  축 {c['axis']}")
    out["known_checks"] = checks
    out["known_ok_rate"] = round(sum(c["ok"] for c in checks) / len(checks), 3)

    # 2) 분산 불일치
    v1sd = A1[A1["eligible"]].groupby("pos_primary")["ability"].agg(["mean", "std", "count"]).round(2)
    v2sd_pos = A2[A2["eligible"]].groupby("pos_primary")["ability"].agg(["mean", "std", "count"]).round(2)
    v2sd = A2[A2["eligible"]].groupby("role")["ability"].agg(["mean", "std", "count"]).round(2)
    print("\n[능력점수 분산 — v1 pos]\n", v1sd.to_string())
    print("[능력점수 분산 — v2 pos]\n", v2sd_pos.to_string())
    print("[능력점수 분산 — v2 role]\n", v2sd.to_string())
    out["sd_v1_pos"] = v1sd.to_dict(orient="index")
    out["sd_v2_pos"] = v2sd_pos.to_dict(orient="index")
    out["sd_v2_role"] = v2sd.to_dict(orient="index")
    out["sd_spread"] = {"v1_pos": round(float(v1sd["std"].max() - v1sd["std"].min()), 2),
                        "v2_pos": round(float(v2sd_pos["std"].max() - v2sd_pos["std"].min()), 2),
                        "v2_role": round(float(v2sd["std"].max() - v2sd["std"].min()), 2)}
    # 같은 선수-시즌의 점수 상관 (얼마나 바뀌었나)
    j = A1[["fbref_id", "Season_End_Year", "ability"]].merge(
        A2[["fbref_id", "Season_End_Year", "ability", "role"]], on=["fbref_id", "Season_End_Year"], suffixes=("_v1", "_v2"))
    j = j.dropna()
    d = j["ability_v2"] - j["ability_v1"]
    print(f"\n[v1→v2 점수 변화] corr {j['ability_v1'].corr(j['ability_v2']):.3f}, 평균차 {d.mean():+.2f}, |차| 평균 {d.abs().mean():.2f}, 최대 {d.abs().max():.1f}")
    print(j.groupby("role").apply(lambda x: (x["ability_v2"] - x["ability_v1"]).mean()).round(2).to_string())
    out["v1_v2_corr"] = round(float(j["ability_v1"].corr(j["ability_v2"])), 3)

    # 3) 하류 모델 OOF
    print("\n코호트(v1) ..."); C1 = build_cohorts(A1, feats, verbose=False)
    print("코호트(v2) ..."); C2 = build_cohorts(A2, feats, extra_cols=("role",), verbose=False)
    res = {}
    for b in ("u23", "veteran"):
        M2 = C2[b].copy()
        for r in ROLES:
            M2[f"role_{r}"] = (M2["role"] == r).astype(int)
        res[b] = {
            "v1": oof_metrics(C1[b], CFG[b], MODEL_FEATURES),
            "v2": oof_metrics(M2, CFG[b], MODEL_FEATURES),
            "v2+role": oof_metrics(M2, CFG[b], MODEL_FEATURES + [f"role_{r}" for r in ROLES]),
        }
        print(f"\n[{b}] OOF (GroupKFold 5겹)")
        print(f"  {'변형':<8}{'AUC':>8}{'MAE':>8}{'R2':>8}{'기저MAE':>9}{'75+MAE':>9}{'n75':>6}{'n':>7}{'라벨p99':>9}")
        for k, m in res[b].items():
            print(f"  {k:<8}{m['auc']:>8.3f}{m['mae']:>8.2f}{m['r2']:>8.3f}{m['mae_baseline']:>9.2f}{str(m['mae_top75']):>9}{m['n_top75']:>6}{m['n']:>7}{m['label_p99']:>9}")
    out["oof"] = res

    with open(CACHE / "a1_compare.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, allow_nan=False)
    print("\n저장:", CACHE / "a1_compare.json")
