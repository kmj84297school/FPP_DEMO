"""ability + eligibility + growth(U23)/peak(veteran) 예측 + k-NN 결과를 조인해
docs/data/index.json, docs/data/players/<fbref_id>.json 로 직렬화.

헤드라인 수치는 예측 중심값(mu)이 아니라 80% 구간 상단(ceiling)을 쓴다 —
mu만 보이면 최상위권 선수의 평균회귀가 "하락 선고"처럼 읽히는데, ceiling은
같은 계산값(지어낸 숫자 아님)을 다르게 강조할 뿐이라 정직성 원칙에
어긋나지 않으면서 "잠재력 상한"이라는 서비스 성격에 더 맞는 프레이밍이다.
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


def prediction_block(p):
    return {
        "survival_prob": to_native(p["survival_prob"]),
        "mu": to_native(p["mu"]),
        "ci80": {"lo": to_native(p["lo80"]), "hi": to_native(p["hi80"])},
        "ci50": {"lo": to_native(p["lo50"]), "hi": to_native(p["hi50"])},
        "sigma_model": to_native(p["sigma_model"]),
        "sigma_residual": to_native(p["sigma_residual"]),
    }


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
                "ability": to_native(row["ability"]),
                "score_position": to_native(row["score_position"]),
                "score_style": to_native(row["score_style"]),
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
                player["neighbors"] = growth_knn[fid]["neighbors"]
                player["low_confidence"] = growth_knn[fid]["low_confidence"]
        elif kind == "peak":
            player["prediction"] = prediction_block(peak_pred.loc[fid])
            if fid in peak_knn:
                player["neighbors"] = peak_knn[fid]["neighbors"]
                player["low_confidence"] = peak_knn[fid]["low_confidence"]

        with open(DOCS_DATA / "players" / f"{fid}.json", "w", encoding="utf-8") as f:
            json.dump(player, f, ensure_ascii=False, indent=1, allow_nan=False)

        mu = player["prediction"]["mu"] if player["prediction"] else None
        ceiling = player["prediction"]["ci80"]["hi"] if player["prediction"] else None
        index_entries.append({
            "fbref_id": fid,
            "name": row["Player"],
            "name_ascii": ascii_fold(row["Player"]),
            "squad": row["Squads"],
            "pos_primary": row["pos_primary"],
            "age": to_native(row["age_y"]),
            "ability": to_native(row["ability"]),
            "style": player["style"]["primary"],
            "eligible": kind is not None,
            "kind": kind,
            "mu": mu,
            "ceiling": ceiling,
            "headroom": round(ceiling - row["ability"], 1) if ceiling is not None and pd.notna(row["ability"]) else None,
        })

    with open(DOCS_DATA / "index.json", "w", encoding="utf-8") as f:
        json.dump(index_entries, f, ensure_ascii=False, indent=1, allow_nan=False)

    with open(DOCS_DATA / "meta.json", "w", encoding="utf-8") as f:
        json.dump({**u23_meta, "veteran": veteran_meta}, f, ensure_ascii=False, indent=1)

    n_growth = sum(1 for e in index_entries if e["kind"] == "growth")
    n_peak = sum(1 for e in index_entries if e["kind"] == "peak")
    print(f"저장 완료: {len(index_entries)}명 (growth={n_growth}, peak={n_peak}) -> {DOCS_DATA}")
