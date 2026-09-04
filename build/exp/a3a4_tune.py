"""A4(잔존 피처 보강) + A3(소규모 하이퍼파라미터 탐색) — 한 스크립트에서 순서대로.

A4: MODEL_FEATURES(51) vs +SURVIVAL_EXTRA(13)를 잔존 분류·Δ 회귀 각각 GroupKFold 5겹으로 비교.
    채택 규칙: AUC +0.005 이상이면 분류에 채택, MAE가 나빠지지 않으면 회귀에도 채택.
A3: 채택된 피처셋 위에서 작은 격자(54조합) 탐색. 선택은 GroupKFold(기본 분할)의 OOF로 하고,
    선택 낙관(54개 중 최선을 고른 편향)을 드러내기 위해 **다른 분할**(shuffle, seed=7)에서
    현행 설정과 선택 설정을 다시 평가해 나란히 기록한다.
결과: build/_cache/a3a4.json, 채택 설정은 build/hparams.json (07_train_models.py가 읽음).
"""
import itertools, json, pathlib, sys, time
import numpy as np, pandas as pd
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score, mean_absolute_error, r2_score
from xgboost import XGBClassifier, XGBRegressor

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "build" / "lib"))
from features import MODEL_FEATURES, SURVIVAL_EXTRA
from cohorts import LABEL_COLS
from config import DATA, CACHE

CUR = {
    "u23": {"surv": dict(n_estimators=300, max_depth=4, learning_rate=0.05, min_child_weight=1),
            "reg": dict(n_estimators=150, max_depth=4, learning_rate=0.08, min_child_weight=1)},
    "veteran": {"surv": dict(n_estimators=300, max_depth=4, learning_rate=0.05, min_child_weight=1),
                "reg": dict(n_estimators=400, max_depth=4, learning_rate=0.05, min_child_weight=1)},
}
FIXED = dict(subsample=0.8, colsample_bytree=0.8, tree_method="hist", random_state=2026, n_jobs=8)
GRID = dict(max_depth=[3, 4, 6], learning_rate=[0.03, 0.05, 0.1], n_estimators=[150, 300, 600], min_child_weight=[1, 5])


def cv_surv(M, cols, params, gkf):
    X, y, g = M[cols].astype(float), M["survived"].values, M["fbref_id"].values
    aucs = []
    for tr, te in gkf.split(X, y, g):
        m = XGBClassifier(**FIXED, **params); m.fit(X.iloc[tr], y[tr])
        aucs.append(roc_auc_score(y[te], m.predict_proba(X.iloc[te])[:, 1]))
    return float(np.mean(aucs)), float(np.std(aucs))


def cv_reg(S, cols, params, gkf):
    X, cur, y, g = S[cols].astype(float), S["ability"].values, S["fut_ability_v2"].values, S["fbref_id"].values
    oof = np.full(len(S), np.nan)
    for tr, te in gkf.split(X, y, g):
        m = XGBRegressor(**FIXED, **params); m.fit(X.iloc[tr], (y - cur)[tr])
        oof[te] = m.predict(X.iloc[te]) + cur[te]
    top = cur >= 75
    return mean_absolute_error(y, oof), r2_score(y, oof), mean_absolute_error(y[top], oof[top])


if __name__ == "__main__":
    out, hp = {}, {}
    gkf = GroupKFold(5)
    gkf2 = GroupKFold(5, shuffle=True, random_state=7)
    base, ext = list(MODEL_FEATURES), list(MODEL_FEATURES) + list(SURVIVAL_EXTRA)
    for b in ("u23", "veteran"):
        M = pd.read_csv(DATA / f"fpp_train_matrix_{b}.csv")
        S = M[M["survived"] == 1].reset_index(drop=True)
        r = {"a4": {}, "a3": {}}
        # ── A4 ──
        for name, cols in (("base51", base), ("+extra13", ext)):
            auc, sd = cv_surv(M, cols, CUR[b]["surv"], gkf)
            mae, r2, mae_top = cv_reg(S, cols, CUR[b]["reg"], gkf)
            r["a4"][name] = {"auc": round(auc, 3), "auc_sd": round(sd, 3), "mae": round(mae, 2), "r2": round(r2, 3), "mae_top75": round(mae_top, 2)}
            print(f"[{b}][A4 {name:<9}] AUC {auc:.3f}±{sd:.3f} | MAE {mae:.2f} R2 {r2:.3f} 75+ {mae_top:.2f}")
        # extra 피처 중요도(gain) — 전체 데이터 분류기
        m = XGBClassifier(**FIXED, **CUR[b]["surv"]); m.fit(M[ext].astype(float), M["survived"].values)
        gain = pd.Series(m.get_booster().get_score(importance_type="gain")).sort_values(ascending=False)
        r["a4"]["extra_gain_rank"] = {f: int(list(gain.index).index(f)) + 1 for f in SURVIVAL_EXTRA if f in gain.index}
        r["a4"]["top10_gain"] = {k: round(float(v), 1) for k, v in gain.head(10).items()}
        use_ext_surv = r["a4"]["+extra13"]["auc"] >= r["a4"]["base51"]["auc"] + 0.005
        use_ext_reg = r["a4"]["+extra13"]["mae"] <= r["a4"]["base51"]["mae"]
        r["a4"]["adopt"] = {"survival": use_ext_surv, "regression": use_ext_reg}
        print(f"[{b}] A4 채택: 분류 {use_ext_surv}, 회귀 {use_ext_reg}")
        cols_s = ext if use_ext_surv else base
        cols_r = ext if use_ext_reg else base
        # ── A3 ──
        t0 = time.time(); rows = []
        for vals in itertools.product(*GRID.values()):
            p = dict(zip(GRID.keys(), vals))
            auc, _ = cv_surv(M, cols_s, p, gkf)
            mae, r2, mae_top = cv_reg(S, cols_r, p, gkf)
            rows.append({**p, "auc": auc, "mae": mae, "r2": r2, "mae_top75": mae_top})
        G = pd.DataFrame(rows)
        best_s = G.sort_values("auc", ascending=False).iloc[0]
        best_r = G.sort_values("mae").iloc[0]
        keys = list(GRID.keys())
        ps = {k: (int(best_s[k]) if k != "learning_rate" else float(best_s[k])) for k in keys}
        pr = {k: (int(best_r[k]) if k != "learning_rate" else float(best_r[k])) for k in keys}
        # 확인 분할(shuffle)에서 현행 vs 선택
        conf = {}
        for tag, p_s, p_r in (("current", CUR[b]["surv"], CUR[b]["reg"]), ("selected", ps, pr)):
            auc, sd = cv_surv(M, cols_s, p_s, gkf2); mae, r2, mt = cv_reg(S, cols_r, p_r, gkf2)
            conf[tag] = {"auc": round(auc, 3), "mae": round(mae, 2), "r2": round(r2, 3), "mae_top75": round(mt, 2)}
        r["a3"] = {
            "grid_size": len(G), "seconds": round(time.time() - t0),
            "current": {"surv": CUR[b]["surv"], "reg": CUR[b]["reg"],
                        "auc": round(float(G[(G.max_depth == 4) & (G.learning_rate == CUR[b]['surv']['learning_rate']) & (G.n_estimators == 300) & (G.min_child_weight == 1)]["auc"].iloc[0]), 3) if len(G) else None},
            "selected": {"surv": ps, "reg": pr, "auc": round(float(best_s["auc"]), 3), "mae": round(float(best_r["mae"]), 2), "r2": round(float(best_r["r2"]), 3), "mae_top75": round(float(best_r["mae_top75"]), 2)},
            "confirm_split": conf,
            "auc_range": [round(float(G.auc.min()), 3), round(float(G.auc.max()), 3)],
            "mae_range": [round(float(G.mae.min()), 2), round(float(G.mae.max()), 2)],
        }
        print(f"[{b}] A3 격자 {len(G)}개 {r['a3']['seconds']}s | AUC 범위 {r['a3']['auc_range']} MAE 범위 {r['a3']['mae_range']}")
        print(f"[{b}]   선택 surv {ps} -> AUC {best_s['auc']:.3f} | reg {pr} -> MAE {best_r['mae']:.2f} R2 {best_r['r2']:.3f}")
        print(f"[{b}]   확인 분할: 현행 {conf['current']} | 선택 {conf['selected']}")
        # 채택: 확인 분할에서도 나빠지지 않을 때만
        adopt_s = conf["selected"]["auc"] >= conf["current"]["auc"]
        adopt_r = conf["selected"]["mae"] <= conf["current"]["mae"]
        r["a3"]["adopt"] = {"survival": adopt_s, "regression": adopt_r}
        hp[b] = {"surv": {**(ps if adopt_s else CUR[b]["surv"]), "features": "ext" if use_ext_surv else "base"},
                 "reg": {**(pr if adopt_r else CUR[b]["reg"]), "features": "ext" if use_ext_reg else "base"}}
        out[b] = r
    json.dump(out, open(CACHE / "a3a4.json", "w"), ensure_ascii=False, indent=1)
    json.dump(hp, open(ROOT / "build" / "hparams.json", "w"), ensure_ascii=False, indent=1)
    print("\n채택 설정 ->", ROOT / "build" / "hparams.json"); print(json.dumps(hp, ensure_ascii=False, indent=1))
