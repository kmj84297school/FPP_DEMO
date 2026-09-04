"""A7 — 합성 id 복구(보수적). 2023-24 반입에서 Born을 못 구해 합성 id(n24*)를 받은 선수를
기존 id(실제 fbref_id 또는 2025 합성 id)와 다시 연결한다.

규칙(오결합 0건이 목표):
  1. 정규화 이름이 같거나(토큰 순서 무시 포함 — 한국식 성명 순서 차이 대비) 후보를 모은다.
  2. 국적(Nation)이 같아야 한다.
  3. 후보의 Born이 [2024 − Age − 1, 2024 − Age] 안에 있어야 한다(Age에서 Born을 '만들지'는 않고
     제약으로만 쓴다 — 생일이 8/1 이후면 ±1년 어긋나는 문제를 구간으로 흡수).
  4. 포지션 그룹이 같아야 한다(GK 제외돼 있으므로 FW/MF/DF).
  5. 위를 통과한 후보 id가 **정확히 하나**일 때만 연결. 둘 이상이면 건드리지 않는다.
  6. 연결 시 Born을 후보의 Born으로 채운다. 건마다 근거를 build/_cache/id_recovery_log.csv에 남긴다.
--dry-run이면 파일을 쓰지 않고 로그만 출력한다.
"""
import pathlib, sys, unicodedata
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
from config import FEATURES_CSV, ABILITY_CSV, CACHE

TARGET = 2024


def fold(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s)) if not unicodedata.combining(c)).lower().strip()


def tokens(s):
    return " ".join(sorted(fold(s).replace("-", " ").split()))


def pos_group(p):
    return str(p).split(",")[0]


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    df = pd.read_csv(FEATURES_CSV, low_memory=False)
    is_syn24 = df["fbref_id"].str.match(r"^n24") & (df["Season_End_Year"] == TARGET)
    targets = df[is_syn24 & df["Born"].isna()].copy()
    others = df[~df["fbref_id"].str.match(r"^n24")].copy()   # 실제 id + 2025 합성 id
    others["_k"], others["_t"] = others["Player"].map(fold), others["Player"].map(tokens)
    by_k = others.groupby("_k")["fbref_id"].agg(set)
    by_t = others.groupby("_t")["fbref_id"].agg(set)
    info = others.groupby("fbref_id").agg(Born=("Born", "first"), Nation=("Nation", "first"),
                                          pos=("pos_primary", lambda s: set(pos_group(x) for x in s)),
                                          name=("Player", "first"), seasons=("Season_End_Year", lambda s: sorted(set(s))))
    print(f"대상: Born 없는 2024 합성 id {targets['fbref_id'].nunique()}명")

    log, remap, born_fill = [], {}, {}
    for _, r in targets.iterrows():
        k, t = fold(r["Player"]), tokens(r["Player"])
        cands = set(by_k.get(k, set())) | set(by_t.get(t, set()))
        if not cands:
            log.append({"player": r["Player"], "syn_id": r["fbref_id"], "status": "no_candidate", "evidence": ""}); continue
        age = r["age_y"]
        ok = []
        for cid in cands:
            c = info.loc[cid]
            reasons = []
            if pd.isna(c["Born"]): reasons.append("cand_born_missing")
            elif not (pd.notna(age) and (TARGET - age - 1) <= c["Born"] <= (TARGET - age)): reasons.append(f"born {c['Born']:.0f} vs age {age}")
            if str(c["Nation"]) != str(r["Nation"]): reasons.append(f"nation {c['Nation']}≠{r['Nation']}")
            if pos_group(r["pos_primary"]) not in c["pos"]: reasons.append(f"pos {c['pos']}∌{pos_group(r['pos_primary'])}")
            if not reasons: ok.append(cid)
            else: log.append({"player": r["Player"], "syn_id": r["fbref_id"], "status": "rejected_candidate", "evidence": f"{cid}({c['name']}): " + "; ".join(reasons)})
        if len(ok) == 1:
            cid = ok[0]; c = info.loc[cid]
            remap[r["fbref_id"]] = cid; born_fill[r["fbref_id"]] = c["Born"]
            log.append({"player": r["Player"], "syn_id": r["fbref_id"], "status": "recovered", "evidence": f"→ {cid} ({c['name']}, Born {c['Born']:.0f}, {c['Nation']}, seasons {c['seasons']}); 2024 Age {age}, Nation {r['Nation']}, pos {r['pos_primary']}"})
        elif len(ok) > 1:
            log.append({"player": r["Player"], "syn_id": r["fbref_id"], "status": "ambiguous", "evidence": ", ".join(ok)})
        else:
            log.append({"player": r["Player"], "syn_id": r["fbref_id"], "status": "all_rejected", "evidence": ""})

    L = pd.DataFrame(log)
    print(L["status"].value_counts().to_string())
    rec = L[L.status == "recovered"]
    for _, x in rec.head(40).iterrows():
        print(f"  {x['player']:<28} {x['syn_id']} {x['evidence']}")
    L.to_csv(CACHE / "id_recovery_log.csv", index=False)
    if dry:
        print("(dry-run: 파일 미변경)"); sys.exit(0)

    # 적용: fbref_id 치환 + Born 채움. 같은 시즌에 이미 그 id가 있으면(=중복) 건너뛴다.
    applied = 0
    for syn, cid in remap.items():
        m = (df["fbref_id"] == syn)
        if ((df["fbref_id"] == cid) & (df["Season_End_Year"] == TARGET)).any():
            print("  건너뜀(같은 시즌에 이미 존재):", syn, cid); continue
        df.loc[m, "fbref_id"] = cid; df.loc[m, "Born"] = born_fill[syn]; applied += 1
    assert not df.duplicated(["fbref_id", "Season_End_Year"]).any()
    df.to_csv(FEATURES_CSV, index=False)
    print(f"적용 {applied}건 -> {FEATURES_CSV} (능력점수·코호트 재생성 필요: 01 → 06 → 07 → 02~05)")
