"""ability + eligibility + predictions + k-NN 결과를 조인해
docs/data/index.json, docs/data/players/<fbref_id>.json 로 직렬화.
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

    predictions = pd.read_csv(CACHE / "predictions_2023.csv").set_index("fbref_id")
    with open(CACHE / "knn_2023.json", encoding="utf-8") as f:
        knn_raw = json.load(f)

    index_entries = []
    for _, row in cur.iterrows():
        fid = row["fbref_id"]
        elig_row = elig.loc[fid]
        eligible = bool(elig_row["eligible_for_prediction"])
        reason = elig_row["reason"] if isinstance(elig_row["reason"], str) else ""

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
                "eligible_for_prediction": eligible,
                "reason": reason or None,
            },
            "prediction": None,
            "neighbors": [],
            "low_confidence": False,
        }

        if eligible and fid in predictions.index:
            p = predictions.loc[fid]
            player["prediction"] = {
                "survival_prob": to_native(p["survival_prob"]),
                "mu": to_native(p["mu"]),
                "ci80": {"lo": to_native(p["lo80"]), "hi": to_native(p["hi80"])},
                "ci50": {"lo": to_native(p["lo50"]), "hi": to_native(p["hi50"])},
                "sigma_model": to_native(p["sigma_model"]),
                "sigma_residual": to_native(p["sigma_residual"]),
            }
        if eligible and fid in knn_raw:
            player["neighbors"] = knn_raw[fid]["neighbors"]
            player["low_confidence"] = knn_raw[fid]["low_confidence"]

        with open(DOCS_DATA / "players" / f"{fid}.json", "w", encoding="utf-8") as f:
            json.dump(player, f, ensure_ascii=False, indent=1)

        mu = player["prediction"]["mu"] if player["prediction"] else None
        index_entries.append({
            "fbref_id": fid,
            "name": row["Player"],
            "name_ascii": ascii_fold(row["Player"]),
            "squad": row["Squads"],
            "pos_primary": row["pos_primary"],
            "age": to_native(row["age_y"]),
            "ability": to_native(row["ability"]),
            "style": player["style"]["primary"],
            "eligible": eligible,
            "mu": mu,
            "delta": round(mu - row["ability"], 1) if mu is not None else None,
        })

    with open(DOCS_DATA / "index.json", "w", encoding="utf-8") as f:
        json.dump(index_entries, f, ensure_ascii=False, indent=1)

    with open(CACHE / "eligibility_meta.json", encoding="utf-8") as f:
        meta = json.load(f)
    with open(DOCS_DATA / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)

    print(f"저장 완료: {len(index_entries)}명 -> {DOCS_DATA}")
