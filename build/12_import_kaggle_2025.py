"""Kaggle 2024-25 시즌 데이터(hubertsidorowicz, FBref 동일 출처)를 기존
fpp_features_clean 스키마로 매핑해 Season_End_Year=2025 행으로 반입하고,
2018~2023 원본과 합쳐 fpp_features_clean_2018_2025.csv 를 생성한다.

- fbref_id: 원본 CSV에 id/URL 컬럼이 없어 (정규화 이름, 생년) 키로 기존
  데이터와 매칭. 키가 모호(동일 이름+생년에 fbref_id 2개 이상)하면 매칭하지
  않고 합성 id를 부여한다 — 동명이인 오결합 방지가 우선 (인계문서 원칙:
  이름 조인 금지의 연장. 생년을 추가해도 모호하면 포기가 정직하다).
- 합성 id: "n25" + md5(이름|생년) 앞 5자리 → 8자. 실제 FBref id와 충돌하지
  않도록 기존 id 집합과 대조.
- 다중 클럽 시즌: 누적 스탯 합산, 비율은 성분에서 재계산(불가하면 출전시간
  가중평균), Squads는 " / " 병기 — 원 전처리 명세와 동일 규칙.
- GK 제외 (기존 파일도 필드플레이어 전용).
- 알려진 결손: 롱패스 시도(pas_Att_Long) 컬럼이 원본에 없음 → shape_long
  판별축 1개가 2025 시즌에서 결측 (스타일 판별은 나머지 축 평균으로 진행).
"""
import hashlib
import pathlib
import sys
import unicodedata

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
from config import DATA, FEATURES_CSV, TARGET_YEAR

KAGGLE_CSV = pathlib.Path(
    "/tmp/claude-0/-home-user-FPP-DEMO/f657c6f8-911b-558a-95c9-123b81ec8bcc/scratchpad/kaggle2526/players_data-2024_2025.csv"
)
OLD_FEATURES = DATA / "fpp_features_clean_2018_2023.csv"

# Kaggle 컬럼 → 우리 스키마. (합산 가능한 누적 스탯)
SUM_MAP = {
    "Min": "std_Min_Playing", "MP": "std_MP_Playing", "Starts": "std_Starts_Playing",
    "Gls": "std_Gls", "Ast": "std_Ast", "G-PK": "std_G_minus_PK",
    "CrdY": "std_CrdY", "CrdR": "std_CrdR",
    "npxG": "std_npxG_Expected", "xAG": "std_xAG_Expected",
    "Sh": "sho_Sh_Standard", "SoT": "sho_SoT_Standard",
    "Cmp": "pas_Cmp_Total", "Att": "pas_Att_Total",
    "PrgDist": "pas_PrgDist_Total", "KP": "pas_KP", "1/3": "pas_Final_Third",
    "PPA": "pas_PPA", "PrgP_stats_passing": "pas_Prog",
    "SCA": "gca_SCA_SCA", "GCA": "gca_GCA_GCA",
    "Tkl": "def_Tkl_Tackles", "Tkl+Int": "def_Tkl_plus_Int",
    "Blocks_stats_defense": "def_Blocks_Blocks", "Clr": "def_Clr", "Err": "def_Err",
    "Touches": "pos_Touches_Touches", "Def Pen": "pos_Def_Pen_Touches",
    "Def 3rd_stats_possession": "pos_Def_3rd_Touches",
    "Mid 3rd_stats_possession": "pos_Mid_3rd_Touches",
    "Att 3rd_stats_possession": "pos_Att_3rd_Touches",
    "Att Pen": "pos_Att_Pen_Touches",
    "Att_stats_possession": "pos_Att_Dribbles", "Succ": "pos_Succ_Dribbles",
    "PrgDist_stats_possession": "pos_PrgDist_Carries",
    "PrgC_stats_possession": "pos_Prog_Carries",
    "Mis": "pos_Mis_Carries", "Dis": "pos_Dis_Carries",
    "PrgR_stats_possession": "pos_Prog_Receiving",
    "Recov": "msc_Recov", "Won": "msc_Won_Aerial", "Lost_stats_misc": "msc_Lost_Aerial",
    "Crs": "msc_Crs", "Fls": "msc_Fls", "2CrdY": "msc_2CrdY",
    # def_Tkl_percent_Vs 재계산용 성분 (드리블러 상대 챌린지 — 승수는 Tkl%*Att로 복원)
    "_chal_won": "_tkl_vs", "Att_stats_defense": "_tkl_vs_att",
}
# 비율 지표: (출력 컬럼, 분자, 분모, 배수)
RATIO_RECOMPUTE = [
    ("pas_Cmp_percent_Total", "pas_Cmp_Total", "pas_Att_Total", 100),
    ("msc_Won_percent_Aerial", "msc_Won_Aerial", "_aer_total", 100),
    ("sho_npxG_per_Sh_Expected", "std_npxG_Expected", "sho_Sh_Standard", 1),
    ("def_Tkl_percent_Vs", "_tkl_vs", "_tkl_vs_att", 100),
]
WEIGHTED_MEAN_MAP = {"Min%": "pt_Min_percent_Playing_Time"}


def ascii_fold(s):
    if not isinstance(s, str):
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


if __name__ == "__main__":
    k = pd.read_csv(KAGGLE_CSV, low_memory=False)
    print("원본:", k.shape)

    k = k[k["Pos"].fillna("") != "GK"].copy()
    print("GK 제외 후:", k.shape)

    # 드리블러 상대 챌린지 승수 복원 (조각 시즌별 Tkl% × 시도 → 합산 후 재비율화)
    k["_chal_won"] = k["Tkl%"] * k["Att_stats_defense"] / 100

    missing = [c for c in SUM_MAP if c not in k.columns] + [c for c in WEIGHTED_MEAN_MAP if c not in k.columns]
    assert not missing, f"매핑 대상 컬럼 부재: {missing}"

    k["_name_key"] = k["Player"].map(ascii_fold)
    k["_born"] = pd.to_numeric(k["Born"], errors="coerce")

    rows = []
    for (name_key, born), g in k.groupby(["_name_key", "_born"], dropna=False):
        minutes = g["Min"].fillna(0)
        rec = {
            "Player": g["Player"].iloc[0],
            "_name_key": name_key,
            "Born": born,
            "Nation": str(g["Nation"].iloc[0]).split()[-1] if pd.notna(g["Nation"].iloc[0]) else None,
            "Pos": g["Pos"].iloc[0],
            "age_y": g["Age"].min(),
            "Squads": " / ".join(dict.fromkeys(g["Squad"].astype(str))),
            "Comps": " / ".join(dict.fromkeys(str(c).split(" ", 1)[-1] for c in g["Comp"])),
            "n_clubs": len(g),
        }
        for src, dst in SUM_MAP.items():
            rec[dst] = g[src].sum(min_count=1)
        rec["_aer_total"] = (g["Won"].fillna(0) + g["Lost"].fillna(0)).sum() or np.nan
        w = minutes.sum()
        for src, dst in WEIGHTED_MEAN_MAP.items():
            rec[dst] = (g[src] * minutes).sum() / w if w > 0 else np.nan
        rows.append(rec)

    new = pd.DataFrame(rows)
    for out_col, num, den, mult in RATIO_RECOMPUTE:
        new[out_col] = new[num] / new[den].replace(0, np.nan) * mult
    new = new.drop(columns=["_tkl_vs", "_tkl_vs_att", "_aer_total"])
    new["pos_primary"] = new["Pos"].str.split(",").str[0]
    new["Season_End_Year"] = TARGET_YEAR
    print("병합(다중클럽 합산) 후:", new.shape)

    # ── fbref_id 매칭: (이름, 생년) → 기존 id, 모호하면 합성 id ──
    old = pd.read_csv(OLD_FEATURES, low_memory=False)
    old["_name_key"] = old["Player"].map(ascii_fold)
    lut = old.groupby(["_name_key", "Born"])["fbref_id"].agg(set)
    known_ids = set(old["fbref_id"])

    def resolve_id(name_key, born, player_name):
        key = (name_key, born)
        if key in lut.index:
            ids = lut.loc[key]
            if len(ids) == 1:
                return next(iter(ids)), "matched"
            return None, "ambiguous"
        return None, "new"

    stats = {"matched": 0, "new": 0, "ambiguous": 0}
    ids = []
    for _, r in new.iterrows():
        fid, status = resolve_id(r["_name_key"], r["Born"], r["Player"])
        stats[status] += 1
        if fid is None:
            h = hashlib.md5(f"{r['_name_key']}|{r['Born']}".encode()).hexdigest()
            fid = "n25" + h[:5]
            while fid in known_ids:
                h = hashlib.md5(h.encode()).hexdigest()
                fid = "n25" + h[:5]
        known_ids.add(fid)
        ids.append(fid)
    new["fbref_id"] = ids
    print("id 매칭:", stats)
    assert new["fbref_id"].is_unique, "fbref_id 중복 발생"

    new = new.drop(columns=["_name_key"])
    combined = pd.concat([old.drop(columns=["_name_key"]), new], ignore_index=True)
    combined.to_csv(FEATURES_CSV, index=False)
    print("저장 완료:", combined.shape, "->", FEATURES_CSV)
    print("2025 시즌 행:", (combined["Season_End_Year"] == TARGET_YEAR).sum())
