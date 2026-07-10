"""ability + eligibility + growth(U23)/peak(veteran) 예측 + k-NN 결과를 조인해
docs/data/index.json, docs/data/players/<fbref_id>.json 로 직렬화.

헤드라인 수치는 예측 중심값(mu)이 아니라 80% 구간 상단(ceiling)을 쓴다 —
mu만 보이면 최상위권 선수의 평균회귀가 "하락 선고"처럼 읽히는데, ceiling은
같은 계산값(지어낸 숫자 아님)을 다르게 강조할 뿐이라 정직성 원칙에
어긋나지 않으면서 "잠재력 상한"이라는 서비스 성격에 더 맞는 프레이밍이다.

점수 재조정: "능력(ability)"류 복합점수(ability/score_position/score_style/
mu/ci/실제 미래능력)는 전 시즌·전 코호트를 통틀어 가장 높았던 값을 100으로
재조정해 표시한다 (선형 스케일, 상대 순위·비율은 그대로 유지). 단, 그룹
세부점수(생산/전진/찬스/안정/수비)는 이미 시즌×포지션 풀 내 순수 백분위라
자체로 0~100이 자연스러운 상한이므로 재조정 대상에서 제외 — 같이 스케일링하면
100을 넘어버린다. 모델 학습·검증(MAE/AUC/R²/신뢰구간 실측)은 원 스케일 그대로
수행되고 이 재조정은 표시 직전 단계에서만 적용되는 선형 변환이다.
"""
import json
import pathlib
import unicodedata

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = ROOT / "build" / "_cache"
DOCS_DATA = ROOT / "docs" / "data"
TARGET_YEAR = 2023


def ascii_fold(s):
    if not isinstance(s, str):
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def to_native(v):
    if pd.isna(v):
        return None
    if hasattr(v, "item"):
        return v.item()
    return v


if __name__ == "__main__":
    (DOCS_DATA / "players").mkdir(parents=True, exist_ok=True)

    ability_df = pd.read_csv(DATA / "fpp_ability_v1_2018_2023.csv", low_memory=False)
    cur = ability_df[ability_df["Season_End_Year"] == TARGET_YEAR].copy()

    elig = pd.read_csv(CACHE / "eligibility_2023.csv").set_index("fbref_id")
    cur = cur[cur["fbref_id"].isin(elig.index[elig["searchable"]])].copy()

    nation = (
        pd.read_csv(DATA / "fpp_features_clean_2018_2023.csv", usecols=["fbref_id", "Season_End_Year", "Nation"], low_memory=False)
        .query("Season_End_Year == @TARGET_YEAR")
        .set_index("fbref_id")["Nation"]
    )

    growth_pred = pd.read_csv(CACHE / "predictions_2023.csv").set_index("fbref_id")
    with open(CACHE / "knn_2023.json", encoding="utf-8") as f:
        growth_knn = json.load(f)

    peak_pred = pd.read_csv(CACHE / "predictions_veteran_2023.csv").set_index("fbref_id")
    with open(CACHE / "knn_veteran_2023.json", encoding="utf-8") as f:
        peak_knn = json.load(f)

    with open(CACHE / "eligibility_meta.json", encoding="utf-8") as f:
        u23_meta = json.load(f)
    with open(CACHE / "veteran_meta.json", encoding="utf-8") as f:
        veteran_meta = json.load(f)

    u23_train = pd.read_csv(DATA / "fpp_train_matrix_v2.csv")
    veteran_train = pd.read_csv(DATA / "fpp_train_matrix_veteran.csv")

    # ── 재조정 기준(SCALE) 산출: 전 시즌 능력 복합점수 + 예측치 + 실제 라벨 결과 통틀어 최댓값 ──
    composite_max = max(
        ability_df[["ability", "score_position", "score_style"]].max().max(),
        growth_pred[["mu", "hi80"]].max().max(),
        peak_pred[["mu", "hi80"]].max().max(),
        u23_train[["ability", "fut_ability_v2"]].max().max(),
        veteran_train[["ability", "fut_ability_v2"]].max().max(),
    )
    SCALE = 100.0 / composite_max
    print(f"재조정 기준: 전체 최고 복합점수 {composite_max:.2f} -> 100 (SCALE={SCALE:.4f})")

    def scale(v):
        v = to_native(v) if not isinstance(v, (int, float)) else v
        return None if v is None or pd.isna(v) else round(v * SCALE, 1)

    def prediction_block(p):
        return {
            "survival_prob": to_native(p["survival_prob"]),
            "mu": scale(p["mu"]),
            "ci80": {"lo": scale(p["lo80"]), "hi": scale(p["hi80"])},
            "ci50": {"lo": scale(p["lo50"]), "hi": scale(p["hi50"])},
            "sigma_model": scale(p["sigma_model"]),
            "sigma_residual": scale(p["sigma_residual"]),
        }

    def scaled_neighbors(entries):
        out = []
        for n in entries:
            n = dict(n)
            n["fut_ability_v2"] = scale(n["fut_ability_v2"]) if n.get("fut_ability_v2") is not None else None
            out.append(n)
        return out

    index_entries = []
    for _, row in cur.iterrows():
        fid = row["fbref_id"]

        kind = None
        reason = None
        if pd.isna(row["ability"]):
            reason = "insufficient_data"
        elif fid in growth_pred.index:
            kind = "growth"
        elif fid in peak_pred.index:
            kind = "peak"
        else:
            if row["age_y"] <= u23_meta["pred_age_max"]:
                reason = "under_minutes"
            elif row["age_y"] <= veteran_meta["age_max"]:
                reason = "under_minutes"
            else:
                reason = "too_old_for_model"

        player = {
            "meta": {
                "fbref_id": fid,
                "player_name": row["Player"],
                "nation": to_native(nation.get(fid)),
                "age_years": to_native(row["age_y"]),
                "squad": row["Squads"],
                "comps": row["Comps"],
                "pos_primary": row["pos_primary"],
                "minutes_2023": to_native(row["std_Min_Playing"]),
            },
            "current": {
                "ability": scale(row["ability"]),
                "score_position": scale(row["score_position"]),
                "score_style": scale(row["score_style"]),
                "groups": {
                    "prod": to_native(row["grp_prod"]),
                    "progress": to_native(row["grp_progress"]),
                    "chance": to_native(row["grp_chance"]),
                    "stability": to_native(row["grp_stability"]),
                    "defense": to_native(row["grp_defense"]),
                },
            },
            "style": {
                "primary": row["style"] if isinstance(row["style"], str) else None,
                "confidence": to_native(row["style_confidence"]),
            },
            "eligibility": {
                "eligible_for_prediction": kind is not None,
                "kind": kind,
                "reason": reason,
            },
            "prediction": None,
            "neighbors": [],
            "low_confidence": False,
        }

        if kind == "growth":
            player["prediction"] = prediction_block(growth_pred.loc[fid])
            if fid in growth_knn:
                player["neighbors"] = scaled_neighbors(growth_knn[fid]["neighbors"])
                player["low_confidence"] = growth_knn[fid]["low_confidence"]
        elif kind == "peak":
            player["prediction"] = prediction_block(peak_pred.loc[fid])
            if fid in peak_knn:
                player["neighbors"] = scaled_neighbors(peak_knn[fid]["neighbors"])
                player["low_confidence"] = peak_knn[fid]["low_confidence"]

        with open(DOCS_DATA / "players" / f"{fid}.json", "w", encoding="utf-8") as f:
            json.dump(player, f, ensure_ascii=False, indent=1, allow_nan=False)

        mu = player["prediction"]["mu"] if player["prediction"] else None
        ceiling = player["prediction"]["ci80"]["hi"] if player["prediction"] else None
        ability_scaled = player["current"]["ability"]
        index_entries.append({
            "fbref_id": fid,
            "name": row["Player"],
            "name_ascii": ascii_fold(row["Player"]),
            "squad": row["Squads"],
            "pos_primary": row["pos_primary"],
            "age": to_native(row["age_y"]),
            "ability": ability_scaled,
            "style": player["style"]["primary"],
            "eligible": kind is not None,
            "kind": kind,
            "mu": mu,
            "ceiling": ceiling,
            "headroom": round(ceiling - ability_scaled, 1) if ceiling is not None and ability_scaled is not None else None,
        })

    with open(DOCS_DATA / "index.json", "w", encoding="utf-8") as f:
        json.dump(index_entries, f, ensure_ascii=False, indent=1, allow_nan=False)

    meta_out = {
        **u23_meta,
        "veteran": {**veteran_meta, "mae": round(veteran_meta["mae"] * SCALE, 2)},
        "u23_mae": round(6.19 * SCALE, 2),
        "u23_r2": 0.231,
        "scale_factor": round(SCALE, 4),
        "scale_basis": "전 시즌·전 코호트 통틀어 최고 복합점수(원점수 {:.1f})를 100으로 재조정".format(composite_max),
    }
    with open(DOCS_DATA / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta_out, f, ensure_ascii=False, indent=1)

    n_growth = sum(1 for e in index_entries if e["kind"] == "growth")
    n_peak = sum(1 for e in index_entries if e["kind"] == "peak")
    print(f"저장 완료: {len(index_entries)}명 (growth={n_growth}, peak={n_peak}) -> {DOCS_DATA}")
