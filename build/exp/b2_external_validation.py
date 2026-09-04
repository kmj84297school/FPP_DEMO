"""B2 — 외부 라벨(시장가치)로 능력점수·예측치의 타당성 교차검증. 데이터가 오면 바로 돌리는 스크립트.

입력 (소유자가 구해올 파일, dev_docs/DATA_REQUESTS.md B2 명세):
  --mv  CSV: 컬럼 tm_id, date(YYYY-MM-DD), market_value_eur  (Transfermarkt 선수별 시장가치 이력)
        선택: fbref_id 컬럼이 있으면 tm_id 대신 그것으로 조인.
조인: data/fbref_tm_mapping_subset.csv (fbref_id ↔ tm_id, worldfootballR 공개 매핑) — 이름 조인 없음.

검증 3종 (전부 시즌 종료 시점 = 6/30 기준 가장 가까운 시장가치 사용):
  V1. 동시점 타당성: 시즌×포지션 내에서 능력점수 vs log(시장가치) Spearman 상관.
      (나이 통제 버전도: 나이 잔차화 후 상관)
  V2. 예측 타당성: 코호트 t의 예측 Δ(폴드 밖) vs t+2~t+3 시장가치 변화율(log 차) 상관.
      — 예측이 "미래의 무언가"를 담고 있는지의 직접 검증.
  V3. 잔존확률 타당성: 잔존확률 vs 실제 t+2 시장가치 존재/하락 AUC.
출력: build/_cache/b2_validation.json + 표준출력 표. 수치를 만들지 않는다 — 조인 실패율도 같이 기록.
"""
import argparse, json, pathlib, sys
import numpy as np, pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "build" / "lib"))
from config import DATA, ABILITY_CSV, CACHE

ap = argparse.ArgumentParser()
ap.add_argument("--mv", required=True, help="시장가치 CSV (tm_id,date,market_value_eur)")
ap.add_argument("--oof", default=str(CACHE / "oof_predictions.csv"), help="선택: 폴드 밖 예측 (fbref_id,season,pred_delta,survival_prob)")
args = ap.parse_args()

mv = pd.read_csv(args.mv)
mv["date"] = pd.to_datetime(mv["date"])
mv = mv.dropna(subset=["market_value_eur"])
mapping = pd.read_csv(DATA / "fbref_tm_mapping_subset.csv", dtype={"tm_id": str})
if "fbref_id" not in mv.columns:
    mv["tm_id"] = mv["tm_id"].astype(str)
    mv = mv.merge(mapping[["fbref_id", "tm_id"]], on="tm_id", how="inner")
ab = pd.read_csv(ABILITY_CSV, low_memory=False)
ab = ab[ab["eligible"] & ab["ability"].notna()]

def mv_at(fid, year):
    """시즌 종료(6/30) 전후 120일 내 가장 가까운 시장가치."""
    s = mv[mv["fbref_id"] == fid]
    if s.empty: return np.nan
    t = pd.Timestamp(year=year, month=6, day=30)
    d = (s["date"] - t).abs()
    i = d.idxmin()
    return s.loc[i, "market_value_eur"] if d.loc[i].days <= 120 else np.nan

ab["mv"] = [mv_at(f, y) for f, y in zip(ab["fbref_id"], ab["Season_End_Year"])]
joined = ab["mv"].notna().mean()
res = {"join_rate": round(float(joined), 3), "n_joined": int(ab["mv"].notna().sum())}
print(f"조인율 {joined:.1%} (n={res['n_joined']})")

# V1
rows = []
for (y, p), g in ab[ab["mv"].notna()].groupby(["Season_End_Year", "pos_primary"]):
    if len(g) < 30: continue
    r = g["ability"].corr(np.log(g["mv"]), method="spearman")
    # 나이 잔차화
    a, l = g["age_y"].values, np.log(g["mv"].values)
    if np.isfinite(a).all():
        lr = l - np.polyval(np.polyfit(a, l, 2), a)
        r_age = pd.Series(g["ability"].values).corr(pd.Series(lr), method="spearman")
    else:
        r_age = np.nan
    rows.append({"season": int(y), "pos": p, "n": len(g), "spearman": round(float(r), 3), "spearman_age_adj": round(float(r_age), 3)})
V1 = pd.DataFrame(rows); print("\n[V1] 능력점수 vs log(시장가치) — 시즌×포지션\n", V1.to_string(index=False))
res["V1"] = rows

# V2 / V3 (폴드 밖 예측 파일이 있을 때만)
oofp = pathlib.Path(args.oof)
if oofp.exists():
    oof = pd.read_csv(oofp)
    oof["mv_t"] = [mv_at(f, y) for f, y in zip(oof["fbref_id"], oof["season"])]
    oof["mv_f"] = [np.nanmean([mv_at(f, y + 2), mv_at(f, y + 3)]) for f, y in zip(oof["fbref_id"], oof["season"])]
    ok = oof[["mv_t", "mv_f"]].notna().all(axis=1) & (oof["mv_t"] > 0) & (oof["mv_f"] > 0)
    d_mv = np.log(oof.loc[ok, "mv_f"]) - np.log(oof.loc[ok, "mv_t"])
    r = pd.Series(oof.loc[ok, "pred_delta"].values).corr(pd.Series(d_mv.values), method="spearman")
    res["V2"] = {"n": int(ok.sum()), "spearman_pred_delta_vs_dlogMV": round(float(r), 3)}
    print(f"\n[V2] 예측 Δ vs Δlog(시장가치) Spearman {r:.3f} (n={ok.sum()})")
    from sklearn.metrics import roc_auc_score
    fut_exists = oof["mv_f"].notna().astype(int)
    if fut_exists.nunique() == 2:
        auc = roc_auc_score(fut_exists, oof["survival_prob"])
        res["V3"] = {"auc_survival_vs_future_mv_exists": round(float(auc), 3)}
        print(f"[V3] 잔존확률 vs 미래 시장가치 존재 AUC {auc:.3f}")
else:
    print("\n(폴드 밖 예측 파일이 없어 V2/V3 생략 — 07_train_models.py에 OOF 저장 옵션을 켜면 생성)")
    res["V2"] = res["V3"] = "not_run"

json.dump(res, open(CACHE / "b2_validation.json", "w"), ensure_ascii=False, indent=1)
print("\n저장:", CACHE / "b2_validation.json")
