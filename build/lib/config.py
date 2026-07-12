"""빌드 파이프라인 공통 설정 — 대상 시즌과 데이터 파일 경로의 단일 출처.

2024-25 시즌(Kaggle hubertsidorowicz, FBref 동일 출처) 반입 이후 스냅샷
시즌이 2023 → 2025로 이동했다. 2023-24(=2024)는 확보 가능한 공개 소스가
없어 공백이며, 2025-26(=2026) 파일은 고급지표(가담/포제션/수비/GCA 계열)가
통째로 빠져 있어 능력점수 계산이 불가능해 반입하지 않았다.
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CACHE = ROOT / "build" / "_cache"
DOCS_DATA = ROOT / "docs" / "data"

TARGET_YEAR = 2025
SEASON_LABEL = "2024-25"

FEATURES_CSV = DATA / "fpp_features_clean_2018_2025.csv"
ABILITY_CSV = DATA / "fpp_ability_v1_2018_2025.csv"

ELIGIBILITY_CSV = CACHE / "eligibility_current.csv"
ELIGIBILITY_META = CACHE / "eligibility_meta.json"
FEATURES_CURRENT_CSV = CACHE / "features_current_all.csv"
PRED_GROWTH_CSV = CACHE / "predictions_growth.csv"
PRED_PEAK_CSV = CACHE / "predictions_peak.csv"
KNN_GROWTH_JSON = CACHE / "knn_growth.json"
KNN_PEAK_JSON = CACHE / "knn_peak.json"
REPORT_EXTRAS_JSON = CACHE / "report_extras_current.json"
QUALITATIVE_JSON = CACHE / "qualitative_current.json"
VETERAN_META = CACHE / "veteran_meta.json"
