"""ability + eligibility + growth(U23)/peak(veteran) 예측 + k-NN 결과를 조인해
docs/data/index.json, docs/data/players/<fbref_id>.json 로 직렬화.

헤드라인 수치는 예측 중심값(mu)이 아니라 80% 구간 상단(ceiling)을 쓴다 —
mu만 보이면 최상위권 선수의 평균회귀가 "하락 선고"처럼 읽히는데, ceiling은
같은 계산값(지어낸 숫자 아님)을 다르게 강조할 뿐이다.

용어 주의: 이 모델이 예측하는 것은 '커리어 전성기'가 아니라 **정확히 t+2~t+3
시점의 능력**이다. 17세 선수라면 19~20세 시점이며 전성기와는 무관하다.
그래서 UI 문구도 "잠재력"이 아니라 기간을 명시하는 쪽으로 통일한다.
또한 능력 점수는 절대 기량이 아니라 시즌x포지션 풀 내 상대 순위이므로,
점수 유지 = 정체가 아니라 '같은 수준의 상대적 지위 유지'를 뜻한다.

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
import sys
import unicodedata

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build" / "lib"))
from report_extras import narrative_current, narrative_potential
from feature_labels import feature_label, FLAG_FEATURES, COMPOSITE_VALUE_FEATURES
from config import (DATA, DOCS_DATA, FEATURES_CSV, ABILITY_CSV, ELIGIBILITY_CSV,
                    ELIGIBILITY_META, PRED_GROWTH_CSV, PRED_PEAK_CSV,
                    KNN_GROWTH_JSON, KNN_PEAK_JSON, REPORT_EXTRAS_JSON, SHAP_GROWTH_JSON, SHAP_PEAK_JSON,
                    QUALITATIVE_JSON, VETERAN_META, CACHE, TARGET_YEAR, SEASON_LABEL)


def ascii_fold(s):
    if not isinstance(s, str):
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


ROLE_LABEL_KO = {"CB": "센터백", "FB": "풀백", "DM": "수비형 MF", "CM": "중앙 MF",
                 "AM": "공격형 MF", "W": "윙어", "ST": "스트라이커"}


def role_block(row):
    """세부 역할(추정) — 구성비 z-축으로 판정한 참고 라벨. 점수 계산에는 쓰이지 않는다
    (A1 실험: 역할 단위 채점은 OOF 지표 악화로 기각). |축|이 작으면 경계 사례라고 표시."""
    r = row.get("role")
    if not isinstance(r, str):
        return None
    axis = to_native(row.get("role_axis"))
    return {"code": r, "label": ROLE_LABEL_KO.get(r, r), "axis": axis,
            "borderline": bool(axis is not None and abs(axis) < 0.3)}


def to_native(v):
    if pd.isna(v):
        return None
    if hasattr(v, "item"):
        return v.item()
    return v


if __name__ == "__main__":
    (DOCS_DATA / "players").mkdir(parents=True, exist_ok=True)

    ability_df = pd.read_csv(ABILITY_CSV, low_memory=False)
    cur = ability_df[ability_df["Season_End_Year"] == TARGET_YEAR].copy()

    elig = pd.read_csv(ELIGIBILITY_CSV).set_index("fbref_id")
    cur = cur[cur["fbref_id"].isin(elig.index[elig["searchable"]])].copy()

    nation = (
        pd.read_csv(FEATURES_CSV, usecols=["fbref_id", "Season_End_Year", "Nation"], low_memory=False)
        .query("Season_End_Year == @TARGET_YEAR")
        .set_index("fbref_id")["Nation"]
    )

    growth_pred = pd.read_csv(PRED_GROWTH_CSV).set_index("fbref_id")
    with open(KNN_GROWTH_JSON, encoding="utf-8") as f:
        growth_knn = json.load(f)

    peak_pred = pd.read_csv(PRED_PEAK_CSV).set_index("fbref_id")
    with open(KNN_PEAK_JSON, encoding="utf-8") as f:
        peak_knn = json.load(f)
    with open(SHAP_GROWTH_JSON, encoding="utf-8") as f:
        growth_shap = json.load(f)
    with open(SHAP_PEAK_JSON, encoding="utf-8") as f:
        peak_shap = json.load(f)

    with open(ELIGIBILITY_META, encoding="utf-8") as f:
        u23_meta = json.load(f)
    with open(VETERAN_META, encoding="utf-8") as f:
        veteran_meta = json.load(f)

    u23_train = pd.read_csv(DATA / "fpp_train_matrix_u23.csv")
    veteran_train = pd.read_csv(DATA / "fpp_train_matrix_veteran.csv")

    with open(REPORT_EXTRAS_JSON, encoding="utf-8") as f:
        report_extras = json.load(f)

    with open(QUALITATIVE_JSON, encoding="utf-8") as f:
        qualitative = json.load(f)

    with open(CACHE / "model_metrics.json", encoding="utf-8") as f:
        model_metrics = json.load(f)

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

    # ── 모델 검증범위 임계 ──
    # 트리 모델은 학습 라벨 범위 밖으로 외삽하지 못한다. 현재 능력이 학습 라벨의
    # 99%tile을 넘는 선수는 모델이 구조적으로 '현상 유지'조차 예측할 수 없으므로
    # (예측 상한 자체가 그 아래), 점추정을 신뢰 구간이 아닌 '범위 밖'으로 표시한다.
    OOR_THRESHOLD = {
        "growth": float(u23_train.loc[u23_train["survived"] == 1, "fut_ability_v2"].quantile(0.99)),
        "peak": float(veteran_train.loc[veteran_train["survived"] == 1, "fut_ability_v2"].quantile(0.99)),
    }
    print("검증범위 임계(원점수):", {k: round(v, 1) for k, v in OOR_THRESHOLD.items()})

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

    def explanation_block(e):
        """A5: SHAP 기여도를 표시 스케일로. Δ 기여는 능력점수 단위(×SCALE), 잔존 기여는 로그오즈."""
        def item(t, scale_contrib):
            v = t["value"]
            if t["feature"] in FLAG_FEATURES:
                value_text = "예" if v == 1 else "아니오"
            elif v is None:
                value_text = "결측"
            else:
                vv = v * SCALE if t["feature"] in COMPOSITE_VALUE_FEATURES else v
                value_text = f"{vv:.1f}"
            c = t["contrib"] * SCALE if scale_contrib else t["contrib"]
            return {"feature": t["feature"], "label": feature_label(t["feature"]),
                    "value_text": value_text, "contrib": round(c, 2)}
        d, sv = e["delta"], e["survival"]
        import math
        return {
            "delta": {"base": round(d["base"] * SCALE, 2), "rest": round(d["rest"] * SCALE, 2),
                      "total": round(d["total"] * SCALE, 2), "top": [item(t, True) for t in d["top"]]},
            "survival": {"base_logit": round(sv["base"], 3), "rest": round(sv["rest"], 3),
                         "base_prob": round(1 / (1 + math.exp(-sv["base"])), 3),
                         "prob": round(1 / (1 + math.exp(-sv["total"])), 3),
                         "top": [item(t, False) for t in sv["top"]]},
            "method": "XGBoost pred_contribs (TreeExplainer SHAP과 동치); 기여도 합 + 기준값 = 예측값",
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
                "role": role_block(row),
                "minutes_season": to_native(row["std_Min_Playing"]),
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
            "explanation": None,
            "neighbors": [],
            "low_confidence": False,
            "report": report_extras.get(fid, {"strengths": [], "weaknesses": [], "top3_styles": [], "style_evidence": {"top": [], "bottom": []}, "coaching": [], "roadmap": []}),
            "qualitative": qualitative.get(fid),
            "narrative": {"current": None, "potential": None},
        }
        if player["qualitative"] and player["qualitative"]["consistency"]["ability_std"] is not None:
            # ability_std는 능력 복합점수 스케일 — 표시 스케일로 함께 재조정
            player["qualitative"]["consistency"]["ability_std"] = round(
                player["qualitative"]["consistency"]["ability_std"] * SCALE, 1)

        if kind == "growth":
            player["prediction"] = prediction_block(growth_pred.loc[fid])
            if fid in growth_shap:
                player["explanation"] = explanation_block(growth_shap[fid])
            if fid in growth_knn:
                player["neighbors"] = scaled_neighbors(growth_knn[fid]["neighbors"])
                player["low_confidence"] = growth_knn[fid]["low_confidence"]
        elif kind == "peak":
            player["prediction"] = prediction_block(peak_pred.loc[fid])
            if fid in peak_shap:
                player["explanation"] = explanation_block(peak_shap[fid])
            if fid in peak_knn:
                player["neighbors"] = scaled_neighbors(peak_knn[fid]["neighbors"])
                player["low_confidence"] = peak_knn[fid]["low_confidence"]

        raw_ability = row["ability"]
        out_of_range = bool(
            kind is not None and pd.notna(raw_ability) and raw_ability > OOR_THRESHOLD[kind]
        )
        player["eligibility"]["out_of_validated_range"] = out_of_range

        if player["current"]["ability"] is not None:
            player["narrative"]["current"] = narrative_current(
                row["Player"], row["pos_primary"], player["current"]["ability"],
                player["current"]["groups"], player["style"]["primary"],
                player["report"]["strengths"], player["report"]["weaknesses"],
            )
        if player["prediction"] is not None:
            ceiling = player["prediction"]["ci80"]["hi"]
            headroom = round(ceiling - player["current"]["ability"], 1) if player["current"]["ability"] is not None else None
            player["narrative"]["potential"] = narrative_potential(
                row["Player"], kind, player["prediction"]["mu"], ceiling,
                player["prediction"]["survival_prob"], headroom, out_of_range,
                model_metrics["u23" if kind == "growth" else "veteran"]["r2"],
                explanation=player["explanation"], current=player["current"]["ability"],
            )

        with open(DOCS_DATA / "players" / f"{fid}.json", "w", encoding="utf-8") as f:
            json.dump(player, f, ensure_ascii=False, indent=1, allow_nan=False)

        mu = player["prediction"]["mu"] if player["prediction"] else None
        ceiling = player["prediction"]["ci80"]["hi"] if player["prediction"] else None
        ability_scaled = player["current"]["ability"]
        index_entries.append({
            "fbref_id": fid,
            "name": row["Player"],
            "squad": row["Squads"],
            "league": str(row["Comps"]).split(" / ")[0] if isinstance(row["Comps"], str) else None,
            "pos_primary": row["pos_primary"],
            "role": row["role"] if isinstance(row.get("role"), str) else None,
            "age": to_native(row["age_y"]),
            "ability": ability_scaled,
            "style": player["style"]["primary"],
            "kind": kind,
            "out_of_range": out_of_range,
            "mu": mu,
            "ceiling": ceiling,
        })

    # index.json은 첫 로드 크기를 위해 열 기반(columnar)·무들여쓰기로 저장한다.
    # (행 기반 indent=1: 569KB → 열 기반 compact: ~180KB. name_ascii·headroom·eligible은 클라이언트가 계산)
    INDEX_COLS = ["fbref_id", "name", "squad", "league", "pos_primary", "role", "age", "ability",
                  "style", "kind", "out_of_range", "mu", "ceiling"]
    with open(DOCS_DATA / "index.json", "w", encoding="utf-8") as f:
        json.dump({"cols": INDEX_COLS, "rows": [[e[c] for c in INDEX_COLS] for e in index_entries]},
                  f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    print("index.json:", (DOCS_DATA / "index.json").stat().st_size // 1024, "KB")

    meta_out = {
        **u23_meta,
        "season_label": SEASON_LABEL,
        "veteran": {**veteran_meta,
                    **{k: model_metrics["veteran"][k] for k in ("auc", "r2", "ci80_coverage", "ci50_coverage")},
                    "mae": round(model_metrics["veteran"]["mae"] * SCALE, 2)},
        "u23": {**{k: model_metrics["u23"][k] for k in ("auc", "r2", "ci80_coverage", "ci50_coverage")},
                "mae": round(model_metrics["u23"]["mae"] * SCALE, 2)},
        "u23_mae": round(model_metrics["u23"]["mae"] * SCALE, 2),
        "u23_r2": model_metrics["u23"]["r2"],
        "scale_factor": round(SCALE, 4),
        "top_band": {k: {**model_metrics[k]["top_band"],
                         "threshold_display": round(model_metrics[k]["top_band"]["threshold_raw"] * SCALE, 1),
                         "mae": round(model_metrics[k]["top_band"]["mae"] * SCALE, 2),
                         "bias": round(model_metrics[k]["top_band"]["bias"] * SCALE, 2)}
                     for k in ("u23", "veteran") if "top_band" in model_metrics[k]},
        "n_players": len(index_entries),
        "filters": {"leagues": sorted({e["league"] for e in index_entries if e["league"]}),
                    "styles": sorted({e["style"] for e in index_entries if e["style"]}),
                    "roles": ["CB", "FB", "DM", "CM", "AM", "W", "ST"]},
        "role_labels": ROLE_LABEL_KO,
        "oor_threshold_display": {k: round(v * SCALE, 1) for k, v in OOR_THRESHOLD.items()},
        "scale_basis": "전 시즌·전 코호트 통틀어 최고 복합점수(원점수 {:.1f})를 100으로 재조정".format(composite_max),
    }
    with open(DOCS_DATA / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta_out, f, ensure_ascii=False, indent=1)

    n_growth = sum(1 for e in index_entries if e["kind"] == "growth")
    n_peak = sum(1 for e in index_entries if e["kind"] == "peak")
    print(f"저장 완료: {len(index_entries)}명 (growth={n_growth}, peak={n_peak}) -> {DOCS_DATA}")
