"""2023-24 시즌(Season_End_Year=2024)을 팀별·카테고리별 FBref CSV 묶음에서 반입.

이 소스는 2025 반입분(Kaggle 단일 CSV)과 형태가 다르다. 리그/팀 폴더마다
players·passing·possession·defensive_actions·g_e_s_creation·miscellaneous_stats·
shooting·playing_time CSV가 따로 있어, 팀 단위로 Player 키 병합 후 전체를 이어붙인다.

- Born 컬럼이 팀별 파일에는 없어, 같은 시즌 표준 스탯 테이블(top5-players.csv)에서
  이름으로 가져온다. 여기서도 못 찾으면 Born=NaN으로 두고 id를 새로 부여한다
  (Age에서 역산하면 생일이 8/1 이후인 선수가 ±1년 어긋나 오결합 위험이 있어 하지 않음).
- fbref_id는 기존 통합 데이터(2018~2023 + 2025)의 (정규화 이름, 생년) 표와 대조.
  2025에서 합성 id(n25xxxxx)를 받은 선수도 같은 키로 연결되므로, 2024·2025 두 시즌을
  가진 선수는 성장궤적(Δ) 피처를 실제로 갖게 된다.
- 'Squad Total'/'Opponent Total' 집계행 제거, GK 제외(기존 파일과 동일 기준).
- (2026-09 수정) ① Wolverhampton은 같은 내용의 폴더가 둘이라 별칭 통합 후 **합산**돼
  출전시간이 2배로 잡혔다 → 같은 팀은 한 폴더만 읽는다. ② 선수 집계 키가 정규화
  이름뿐이라 동명이인(Danilo 포레스트/유벤투스, Rodri 시티/베티스)이 한 명으로 합쳐졌다
  → 키를 (이름, 생년), 생년이 없으면 (이름, 시즌 나이)로 바꾼다. Born 조회도
  (이름, 나이)로 해서 동명이인에게 같은 생년이 붙지 않게 한다.
- 다중 클럽 시즌은 누적 합산 + 비율 재계산 (원 전처리 명세와 동일 규칙).
- 재실행 가능: 기존 2024 행을 지우고 다시 붙인다.
"""
import glob
import hashlib
import os
import pathlib
import sys
import unicodedata

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
from config import FEATURES_CSV

SRC = pathlib.Path(
    "/tmp/claude-0/-home-user-FPP-DEMO/f657c6f8-911b-558a-95c9-123b81ec8bcc/scratchpad"
)
SEASON_DIR = SRC / "new2" / "2023-2024"
BORN_CSV = SRC / "new3" / "top5-players.csv"
TARGET_YEAR = 2024

LEAGUES = {
    "EPL": "Premier League", "La Liga": "La Liga", "Serie A": "Serie A",
    "Bundesliga": "Bundesliga", "Ligue 1": "Ligue 1",
}
# 같은 구단이 서로 다른 폴더명으로 중복 존재 → 정규화 후 합산되게 한다
SQUAD_ALIASES = {"Wolverhampton Wanderers": "Wolverhampton"}
DROP_ROWS = {"squad total", "opponent total"}

CATEGORY_FILES = {
    "players": "players.csv", "shooting": "shooting.csv", "passing": "passing.csv",
    "possession": "possession.csv", "defense": "defensive_actions.csv",
    "gca": "g_e_s_creation.csv", "misc": "miscellaneous_stats.csv",
    "playing_time": "playing_time.csv",
}
# 병합 시 카테고리 간 중복되는 메타 컬럼은 첫 파일 것만 유지
META_COLS = {"Nation", "Pos", "Age", "90s", "Matches"}

SUM_MAP = {
    "Playing Time Min": "std_Min_Playing", "Playing Time MP": "std_MP_Playing",
    "Playing Time Starts": "std_Starts_Playing",
    "Performance Gls": "std_Gls", "Performance Ast": "std_Ast",
    "Performance G-PK": "std_G_minus_PK",
    "Performance CrdY": "std_CrdY", "Performance CrdR": "std_CrdR",
    "Expected npxG": "std_npxG_Expected", "Expected xAG": "std_xAG_Expected",
    "Standard Sh": "sho_Sh_Standard", "Standard SoT": "sho_SoT_Standard",
    "Total Cmp": "pas_Cmp_Total", "Total Att": "pas_Att_Total",
    "Total PrgDist": "pas_PrgDist_Total", "Long Att": "pas_Att_Long",
    "KP": "pas_KP", "1/3": "pas_Final_Third", "PPA": "pas_PPA", "PrgP": "pas_Prog",
    "SCA SCA": "gca_SCA_SCA", "GCA GCA": "gca_GCA_GCA",
    "Tackles Tkl": "def_Tkl_Tackles", "Tkl+Int": "def_Tkl_plus_Int",
    "Blocks Blocks": "def_Blocks_Blocks", "Clr": "def_Clr", "Err": "def_Err",
    "Touches Touches": "pos_Touches_Touches", "Touches Def Pen": "pos_Def_Pen_Touches",
    "Touches Def 3rd": "pos_Def_3rd_Touches", "Touches Mid 3rd": "pos_Mid_3rd_Touches",
    "Touches Att 3rd": "pos_Att_3rd_Touches", "Touches Att Pen": "pos_Att_Pen_Touches",
    "Take-Ons Att": "pos_Att_Dribbles", "Take-Ons Succ": "pos_Succ_Dribbles",
    "Carries PrgDist": "pos_PrgDist_Carries", "Carries PrgC": "pos_Prog_Carries",
    "Carries Mis": "pos_Mis_Carries", "Carries Dis": "pos_Dis_Carries",
    "Receiving PrgR": "pos_Prog_Receiving",
    "Performance Recov": "msc_Recov", "Aerial Duels Won": "msc_Won_Aerial",
    "Aerial Duels Lost": "msc_Lost_Aerial", "Performance Crs": "msc_Crs",
    "Performance Fls": "msc_Fls", "Performance 2CrdY": "msc_2CrdY",
    "Challenges Tkl": "_chal_won", "Challenges Att": "_chal_att",
}
RATIO_RECOMPUTE = [
    ("pas_Cmp_percent_Total", "pas_Cmp_Total", "pas_Att_Total", 100),
    ("msc_Won_percent_Aerial", "msc_Won_Aerial", "_aer_total", 100),
    ("sho_npxG_per_Sh_Expected", "std_npxG_Expected", "sho_Sh_Standard", 1),
    ("def_Tkl_percent_Vs", "_chal_won", "_chal_att", 100),
]
WEIGHTED_MEAN_MAP = {"Playing Time Min%": "pt_Min_percent_Playing_Time"}


def fold(s):
    if not isinstance(s, str):
        return ""
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower().strip()


def numify(df, skip):
    for c in df.columns:
        if c in skip:
            continue
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "", regex=False), errors="coerce")
    return df


def load_team(d):
    merged = None
    for _, fname in CATEGORY_FILES.items():
        path = os.path.join(d, fname)
        if not os.path.exists(path):
            continue
        df = pd.read_csv(path, low_memory=False)
        if "Player" not in df.columns:
            continue
        df = df[~df["Player"].map(fold).isin(DROP_ROWS)]
        df = df.loc[:, ~df.columns.duplicated()]
        if merged is None:
            merged = df
        else:
            drop = [c for c in df.columns if c in merged.columns and c != "Player"]
            merged = merged.merge(df.drop(columns=drop), on="Player", how="outer")
    return merged


if __name__ == "__main__":
    frames = []
    for league_dir, comp in LEAGUES.items():
        seen = set()
        for d in sorted(glob.glob(str(SEASON_DIR / league_dir / "*/"))):
            squad = os.path.basename(d.rstrip("/"))
            if SQUAD_ALIASES.get(squad, squad) in seen:
                print(f"  중복 폴더 건너뜀: {league_dir}/{squad}")
                continue
            seen.add(SQUAD_ALIASES.get(squad, squad))
            t = load_team(d)
            if t is None or t.empty:
                continue
            t["Squad"] = SQUAD_ALIASES.get(squad, squad)
            t["Comp"] = comp
            frames.append(t)
    raw = pd.concat(frames, ignore_index=True)
    print("팀별 병합 결과:", raw.shape)

    raw = raw[~raw["Pos"].astype(str).str.contains("GK", na=False)].copy()
    print("GK 제외 후:", raw.shape)

    keep_text = {"Player", "Nation", "Pos", "Squad", "Comp"}
    raw = numify(raw, keep_text)
    raw["_k"] = raw["Player"].map(fold)

    born_src = pd.read_csv(BORN_CSV, low_memory=False)
    born_src["_k"] = born_src["Player"].map(fold)
    born_src["Age"] = pd.to_numeric(born_src["Age"], errors="coerce")
    # (이름, 시즌 나이)로 조회 — 동명이인은 나이가 다르면 갈라진다. 같은 (이름, 나이)에
    # 생년이 둘 이상이면 모호하므로 붙이지 않는다.
    by_name_age = born_src.groupby(["_k", "Age"])["Born"].agg(lambda x: set(x.dropna()))
    by_name = born_src.groupby("_k")["Born"].agg(lambda x: set(x.dropna()))
    def lookup_born(k, age):
        c = by_name_age.get((k, age)) if pd.notna(age) else None
        if c is None or len(c) == 0:
            c = by_name.get(k)
        return next(iter(c)) if c and len(c) == 1 else np.nan
    raw["Born"] = [lookup_born(k, a) for k, a in zip(raw["_k"], raw["Age"])]
    print("Born 확보:", raw["Born"].notna().sum(), "/", len(raw))
    # 선수 집계 키: (이름, 생년) — 생년이 없으면 (이름, 시즌 나이)
    raw["_g"] = [f"{k}|b{int(b)}" if pd.notna(b) else f"{k}|a{a}" for k, b, a in zip(raw["_k"], raw["Born"], raw["Age"])]
    multi = raw.groupby("_k")["_g"].nunique()
    for k in multi[multi > 1].index:
        sub = raw[raw["_k"] == k]
        print(f"  동명이인 분리: {sub['Player'].iloc[0]} -> " + " | ".join(f"{s}({n}, Age {a})" for s, n, a in zip(sub["Squad"], sub["Nation"], sub["Age"])))

    rows = []
    for gk, g in raw.groupby("_g", dropna=False):
        k = g["_k"].iloc[0]
        minutes = g["Playing Time Min"].fillna(0)
        rec = {
            "Player": g["Player"].iloc[0], "_k": k,
            "Born": g["Born"].dropna().iloc[0] if g["Born"].notna().any() else np.nan,
            "Nation": str(g["Nation"].iloc[0]).split()[-1] if pd.notna(g["Nation"].iloc[0]) else None,
            "Pos": g["Pos"].iloc[0],
            "age_y": g["Age"].min(),
            "Squads": " / ".join(dict.fromkeys(g["Squad"].astype(str))),
            "Comps": " / ".join(dict.fromkeys(g["Comp"].astype(str))),
            "n_clubs": g["Squad"].nunique(),
        }
        for src, dst in SUM_MAP.items():
            rec[dst] = g[src].sum(min_count=1) if src in g.columns else np.nan
        aer = (g.get("Aerial Duels Won", pd.Series(dtype=float)).fillna(0)
               + g.get("Aerial Duels Lost", pd.Series(dtype=float)).fillna(0)).sum()
        rec["_aer_total"] = aer or np.nan
        w = minutes.sum()
        for src, dst in WEIGHTED_MEAN_MAP.items():
            rec[dst] = (g[src] * minutes).sum() / w if (w > 0 and src in g.columns) else np.nan
        rows.append(rec)

    new = pd.DataFrame(rows)
    for out_col, num, den, mult in RATIO_RECOMPUTE:
        new[out_col] = new[num] / new[den].replace(0, np.nan) * mult
    new = new.drop(columns=["_chal_won", "_chal_att", "_aer_total"])
    new["pos_primary"] = new["Pos"].astype(str).str.split(",").str[0]
    new["Season_End_Year"] = TARGET_YEAR
    print("선수 단위 집계 후:", new.shape)

    old = pd.read_csv(FEATURES_CSV, low_memory=False)
    old = old[old["Season_End_Year"] != TARGET_YEAR].copy()  # 재실행 대비
    old["_k"] = old["Player"].map(fold)
    lut = old.groupby(["_k", "Born"])["fbref_id"].agg(set)
    known_ids = set(old["fbref_id"])
    # Born을 못 구한 선수용 대체 경로: 이름이 데이터 전체에서 유일할 때만 이름으로 연결.
    # 동명이인이 하나라도 있으면 연결하지 않는다(오결합 방지 원칙 유지).
    name_lut = old.groupby("_k")["fbref_id"].agg(set)
    unique_name_lut = {k: next(iter(v)) for k, v in name_lut.items() if len(v) == 1}

    stats = {"matched": 0, "new": 0, "ambiguous": 0,
             "no_born_recovered": 0, "no_born_unresolved": 0}
    ids = []
    for _, r in new.iterrows():
        fid = None
        if pd.notna(r["Born"]):
            key = (r["_k"], r["Born"])
            if key in lut.index:
                cand = lut.loc[key]
                if len(cand) == 1:
                    fid, status = next(iter(cand)), "matched"
                else:
                    status = "ambiguous"
            else:
                status = "new"
        elif r["_k"] in unique_name_lut:
            fid, status = unique_name_lut[r["_k"]], "no_born_recovered"
        else:
            status = "no_born_unresolved"
        stats[status] += 1
        if fid is None:
            h = hashlib.md5(f"{r['_k']}|{r['Born']}".encode()).hexdigest()
            fid = "n24" + h[:5]
            while fid in known_ids:
                h = hashlib.md5(h.encode()).hexdigest()
                fid = "n24" + h[:5]
        known_ids.add(fid)
        ids.append(fid)
    new["fbref_id"] = ids
    print("id 매칭:", stats)
    assert new["fbref_id"].is_unique, "fbref_id 중복"

    combined = pd.concat([old.drop(columns=["_k"]), new.drop(columns=["_k"])], ignore_index=True)
    combined.to_csv(FEATURES_CSV, index=False)
    print("저장 완료:", combined.shape, "->", FEATURES_CSV)
    print("시즌별 행 수:", combined["Season_End_Year"].value_counts().sort_index().to_dict())
