# PlayerPotentialAI_FBREF_Final_v3 (Playstyle/Radar Final · fixed)
# - 유지: FBref 403 우회(Selenium), 슬러그 자동, 파싱, 점수, 시각화, HTML 리포트
# - 추가/통합(완성):
#   1) 플레이스타일 엔진(fuzzy) → Primary/Top-n/근거/개선 포인트
#   2) 스타일별 레이더 키 자동 선택(없으면 역할 기본키)
#   3) 약점은 역할 가중치 기반 과노출 방지(공격형 역할 수비항목 필터)
#   4) 역할 강제 입력(override) 옵션
# - 종합: 정량/비정량 70/30, Narrative 포함

import re, time, json, math, unicodedata, html as _html
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote, urlencode

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from bs4 import BeautifulSoup

# Selenium
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# HTTP
import requests

BASE = "https://fbref.com"

# ======== 모드 & 바이어스 키 ========
POTENTIAL_MODE = "v3"
STAR_BIAS_KEYS = ["Shots Total", "Successful Take-Ons", "Touches (Att Pen)"]
STABILITY_KEYS = ["Pass Completion %","Progressive Passes","Progressive Carries","Interceptions","Tackles","Blocks"]

# ======== 정량/비정량 통합 가중치 ========
QUANT_WEIGHT = 0.70
QUAL_WEIGHT  = 0.30

# ======== Wikipedia 휴리스틱 ========
QUAL_KEYWORDS = {
    "injury": [
        r"\bacl\b", r"\banterior cruciate ligament\b", r"\bhamstring\b", r"\bmeniscus\b",
        r"\bfracture\b", r"\bmetatarsal\b", r"\bankle\b", r"\bshoulder\b",
        r"\brecurring injury\b", r"\bsetback\b", r"\bsidelined\b", r"\blong[-\s]?term injury\b",
    ],
    "discipline": [
        r"\bcontroversy\b", r"\bdisciplinary\b", r"\bsuspended\b", r"\bsuspension\b",
        r"\bred card\b", r"\bban(ned)?\b", r"\bbreach of discipline\b", r"\bfined\b",
        r"\barrest(ed)?\b", r"\bdrink driving\b", r"\bdoping\b", r"\bmatch[-\s]?fixing\b",
    ],
    "transfer": [
        r"\btransfer request\b", r"\bcontract dispute\b", r"\btraining strike\b",
        r"\bagent saga\b", r"\brelease clause\b", r"\bfree transfer\b", r"\bloan terminated\b",
        r"\bunregistered\b", r"\bregistration issue\b",
    ],
    "character_pos": [
        r"\bcharity\b", r"\bphilanthropy\b", r"\brole model\b", r"\bsportsmanship\b",
        r"\bcommunity work\b", r"\bhumble\b", r"\bwork ethic\b",
    ],
    "character_neg": [
        r"\barrogant\b", r"\battitude problem\b", r"\bindiscipline\b", r"\btraining late\b",
        r"\bdressing room rift\b", r"\bfallout\b",
    ],
}
QUAL_RECENT_WINDOW_YEARS = 3
WIKI_UA_HEADERS = {"User-Agent": "WikiProbe/1.0 (contact: analyst@example.com)"}

# ================= Selenium =================
def start_driver(headless: bool = True, driver_path: str | None = None):
    opts = Options()
    if headless: opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox"); opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu"); opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    )
    service = Service(driver_path) if driver_path else Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(45)
    return driver

def wait_page_ready(driver, timeout=25):
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )

# ================= Viz helpers =================
def _ensure_outdir(base: str) -> Path:
    p = Path(base); p.mkdir(parents=True, exist_ok=True); return p

def _dedup_stats(items, k=10):
    seen, out = set(), []
    for it in (items or []):
        name = str(it.get("statistic", "")).strip()
        if not name or name in seen: continue
        seen.add(name)
        pct = it.get("percentile", None)
        try: pct = float(pct)
        except (TypeError, ValueError): continue
        out.append((name, pct))
        if len(out) >= k: break
    return out

def viz_strengths_weaknesses(scored: dict, outdir: str):
    out = _ensure_outdir(outdir)
    st = _dedup_stats(scored.get("top_strengths", []), k=7)
    if st:
        names = [n for n,_ in st][::-1]; vals  = [v for _,v in st][::-1]
        plt.figure(figsize=(7,4)); plt.barh(range(len(vals)), vals)
        plt.yticks(range(len(vals)), names); plt.xlabel("Percentile")
        plt.title("Top Strengths (role-aware)"); plt.xlim(0,100); plt.tight_layout()
        plt.savefig(out / "strengths.png", dpi=160); plt.close()
    wk = _dedup_stats(scored.get("top_weaknesses", []), k=7)
    if wk:
        names = [n for n,_ in wk][::-1]; vals  = [v for _,v in wk][::-1]
        plt.figure(figsize=(7,4)); plt.barh(range(len(vals)), vals)
        plt.yticks(range(len(vals)), names); plt.xlabel("Percentile")
        plt.title("Weaknesses (role-aware)"); plt.xlim(0,100); plt.tight_layout()
        plt.savefig(out / "weaknesses.png", dpi=160); plt.close()

def viz_group_scores(pot_details: dict, outdir: str):
    out = _ensure_outdir(outdir)
    cats = ["g_prod","g_progress","g_chance","g_stability"]
    labels = ["Productivity","Progression","Chance","Stability"]
    vals = [float(pot_details.get(k,0.0)) for k in cats]
    plt.figure(figsize=(6,4)); plt.bar(range(len(vals)), vals)
    plt.xticks(range(len(vals)), labels, rotation=15)
    plt.ylim(0,100); plt.ylabel("Percentile"); plt.title("Potential Group Scores")
    plt.tight_layout(); plt.savefig(out / "groups.png", dpi=160); plt.close()

def viz_radar(df: pd.DataFrame, keys: list[str], title: str, outfile: str):
    vals, labels = [], []
    for k in keys:
        v = pick_percentile(df, k)
        if v is not None: labels.append(k); vals.append(float(v))
    if len(vals) < 3: return
    angles = np.linspace(0, 2*np.pi, len(vals), endpoint=False)
    vals += vals[:1]; angles = np.concatenate([angles, angles[:1]])
    plt.figure(figsize=(5,5)); ax = plt.subplot(111, polar=True)
    ax.plot(angles, vals); ax.fill(angles, vals, alpha=0.15)
    ax.set_xticks(angles[:-1]); ax.set_xticklabels(labels); ax.set_yticklabels([])
    ax.set_title(title); plt.tight_layout(); plt.savefig(outfile, dpi=160); plt.close()

def viz_make_quick_report(
    meta: dict, scored: dict, pot: float, pot_details: dict, df: pd.DataFrame,
    qual_score: float | None = None, qual_signals: dict | None = None,
    wiki_url: str | None = None, style_block: str = "", outroot: str = "viz_out"
):
    out = _ensure_outdir(outroot)
    viz_strengths_weaknesses(scored, outroot)
    viz_group_scores(pot_details, outroot)
    role = meta.get("role") or "WM"
    radar_keys = RELEVANT_STATS_BY_ROLE.get(role, RELEVANT_STATS_BY_ROLE["WM"])[:6]
    viz_radar(df, radar_keys, f"Role: {role} — Radar", str(out / "radar.png"))

    name = meta.get("player_name") or "(Unknown)"
    minutes = meta.get("minutes_365d"); age = meta.get("age_years")

    diag_html = f"""
<div class="card"><h2>Bias Diagnostics</h2>
  <div>Mode: {pot_details.get('mode','v3')}</div>
  <div>Diversity: {pot_details.get('diversity_0_1', 'n/a')}</div>
  <div>Imbalance penalty: {pot_details.get('imbalance_penalty', 'n/a')}</div>
  <div>Uncertainty penalty: {pot_details.get('uncertainty_penalty', 'n/a')}</div>
  <div>Age gain: {pot_details.get('age_gain', 'n/a')}</div>
</div>
""".strip()

    qual_block = ""
    if qual_score is not None and qual_signals is not None:
        qual_block = f"""
<div class="card"><h2>Wikipedia-derived Qualitative</h2>
  <div>Qual Score: <b>{qual_score}</b></div>
  <div>injury={qual_signals.get('injury_hits',0)}, discipline={qual_signals.get('discipline_hits',0)},
       transfer={qual_signals.get('transfer_hits',0)}, char+= {qual_signals.get('char_pos_hits',0)},
       char-= {qual_signals.get('char_neg_hits',0)}, recent_w={qual_signals.get('recent_w',1.0)}</div>
  <div>Wikipedia: {wiki_url or '(not found)'}</div>
</div>
""".strip()

    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Scout Visual — {name}</title>
<style>
body {{
  font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial,
  "Apple SD Gothic Neo","Noto Sans CJK KR","맑은 고딕", sans-serif; margin:24px;
}}
h1,h2 {{ margin: 8px 0 4px; }}
.card {{ border:1px solid #ddd; border-radius:10px; padding:12px; margin:12px 0; }}
img {{ max-width:480px; height:auto; display:block; margin:8px auto; }}
.meta {{ color:#555; font-size:14px; }}
.grid {{ display:flex; gap:16px; flex-wrap:wrap; align-items:flex-start; }}
.grid > .card {{ flex:1 1 480px; }}
</style></head>
<body>
<h1>Scout Visual — {name}</h1>
<div class="meta">
Player ID: {meta.get('player_id','')} · Role: {role} · Minutes: {minutes} · Age: {age}
<br/>Current: {scored.get('final_score_0_100')} (base {scored.get('base_from_percentiles')}, rel {scored.get('reliability_bonus')}, age {scored.get('age_adjustment')})
<br/>Potential: {pot} — Groups: {pot_details.get('g_prod')}/{pot_details.get('g_progress')}/{pot_details.get('g_chance')}/{pot_details.get('g_stability')}
</div>

<div class="grid">
  <div class="card"><h2>Top Strengths</h2><img src="strengths.png" alt="strengths"/></div>
  <div class="card"><h2>Weaknesses</h2><img src="weaknesses.png" alt="weaknesses"/></div>
  <div class="card"><h2>Potential Groups</h2><img src="groups.png" alt="groups"/></div>
  <div class="card"><h2>Role/Style Radar</h2><img src="radar.png" alt="radar"/></div>
</div>

{style_block}
{qual_block}
{diag_html}

</body></html>"""
    (out / "report.html").write_text(html, encoding="utf-8")
    return {"dir": str(out.resolve()), "files": ["strengths.png","weaknesses.png","groups.png","radar.png","report.html"]}

# ================= HTML utils =================
def strip_html_comments(html: str) -> str:
    return re.sub(r"<!--|-->", "", html)

def parse_minutes_from_html(html: str) -> int | None:
    clean = strip_html_comments(html)
    m = re.search(r'Based\s+on[^0-9]*([\d,]+)\s+minutes', clean, flags=re.I | re.S)
    if not m:
        m = re.search(r'([\d,]+)\s+minutes\s+(played|over\s+the\s+last\s+365\s+days|in\s+the\s+last\s+365\s+days)',
                      clean, flags=re.I | re.S)
    return int(m.group(1).replace(",", "")) if m else None

def extract_dob_from_profile_html(html: str) -> date | None:
    clean = strip_html_comments(html)
    m = re.search(r'data-birth="(\d{4}-\d{2}-\d{2})"', clean)
    if m:
        try: return datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except Exception: pass
    m = re.search(r'itemprop="birthDate"[^>]*datetime="(\d{4}-\d{2}-\d{2})"', clean)
    if m:
        try: return datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except Exception: pass
    m = re.search(r'Born:\s*</span>\s*([A-Za-z]+ \d{1,2}, \d{4})', clean)
    if m:
        try: return datetime.strptime(m.group(1), "%B %d, %Y").date()
        except Exception: pass
    return None

# ================= Slug / URL helpers =================
COHORTS = ["365_m1","365_m2","365_m3","365_m4"]

def build_scout_url_with_cohort(player_id: str, slug: str, cohort: str) -> str:
    s = slug
    if not s.lower().endswith("-scouting-report"):
        s = f"{s}-Scouting-Report"
    return f"{BASE}/en/players/{player_id}/scout/{cohort}/{s}"

def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))

def generate_slug_candidates(name: str) -> list[str]:
    if not name: return []
    name = re.sub(r"\s+", " ", name.strip())
    base = _strip_accents(name)
    base = re.sub(r"[^A-Za-z0-9 \-']", " ", base)
    parts = [p for p in base.split(" ") if p]
    combos = set()
    if len(parts) >= 2:
        combos.add(f"{parts[0]}-{parts[-1]}")
        if len(parts) >= 3:
            combos.add(f"{parts[0]}-{parts[1]}-{parts[-1]}")
            combos.add("-".join(parts[:3]))
        combos.add("-".join(parts))
    else:
        combos.add("-".join(parts))
    combos.update([parts[-1], parts[0]] if parts else [])
    cands = []
    for c in combos:
        c = re.sub(r"'+", "", c); c = re.sub(r"\s+", "-", c).strip("-"); c = re.sub(r"-{2,}", "-", c)
        if c: cands.append(c)
    def _pri(s): return (0 if len(s.split("-"))==2 else 1, len(s))
    return sorted(set(cands), key=_pri)[:20]

def clean_fbref_title_to_name(title: str) -> str:
    if not title: return ""
    title = title.split("|")[0].strip()
    title = re.split(r"\s+Stats\b", title, maxsplit=1)[0].strip()
    return re.sub(r"\s+", " ", title)

def derive_name_from_slug(slug: str) -> str:
    if not slug: return ""
    s = re.sub(r"-Scouting-Report$", "", slug, flags=re.I)
    s = s.replace("-", " ").strip()
    return " ".join(w.capitalize() for w in s.split() if w)

# ================= FBref 검색/Wayback =================
def search_fbref_player_by_name(name: str, timeout=10) -> list[str]:
    if not name: return []
    url = f"https://fbref.com/search/search.fcgi?{urlencode({'search': name})}"
    try:
        r = requests.get(url, headers=WIKI_UA_HEADERS, timeout=timeout)
        if r.status_code != 200: return []
        soup = BeautifulSoup(r.text, "lxml")
        hrefs = [a.get("href","") for a in soup.select("a[href]")]
        hrefs = [h for h in hrefs if re.match(r"^/en/players/[0-9a-f]{8}/", h)]
        slugs = []
        for h in hrefs:
            m = re.search(r"/scout/365_m\d/([^/]+)$", h)
            if m: slugs.append(m.group(1))
        return list(dict.fromkeys(slugs))
    except Exception:
        return []

def wayback_fetch_if_needed(url: str, timeout=10) -> str | None:
    try:
        api = f"https://web.archive.org/cdx/search/cdx?url={quote(url)}&output=json&limit=1&filter=statuscode:200&from=2021"
        j = requests.get(api, timeout=timeout).json()
        if isinstance(j, list) and len(j) >= 2:
            last = j[-1]; ts = last[1]
            snap = f"https://web.archive.org/web/{ts}/{url}"
            r = requests.get(snap, timeout=timeout)
            if r.status_code == 200 and r.text: return r.text
    except Exception:
        pass
    return None

def try_all_scout_urls(driver, player_id: str, slug_candidates: list[str], sleep=1.0):
    for cohort in COHORTS:
        for slug in slug_candidates:
            try:
                url = build_scout_url_with_cohort(player_id, slug, cohort)
                driver.get(url); wait_page_ready(driver); time.sleep(sleep)
                page = driver.page_source
                if ("Scouting Report" in page) and ("Statistic" in page or "Percentile" in page):
                    return page, url
                if driver.current_url != url:
                    page2 = driver.page_source
                    if ("Scouting Report" in page2) and ("Statistic" in page2 or "Percentile" in page2):
                        return page2, driver.current_url
            except Exception:
                continue
    return None, None

# ================= 프로필/슬러그 추출 & 온라인 실행 =================
def extract_player_name_from_profile(html: str) -> str | None:
    clean = strip_html_comments(html)
    m = re.search(r"<h1[^>]*>([^<]+)</h1>", clean)
    if m:
        name = re.sub(r"\s+", " ", m.group(1)).strip()
        name = re.sub(r"\s+Stats\b.*$", "", name).strip()
        return name if name else None
    m2 = re.search(r"<title>([^<]+)</title>", clean, flags=re.I)
    if m2:
        title = clean_fbref_title_to_name(m2.group(1))
        return title or None
    return None

def extract_position_text_from_profile_html(html: str) -> str | None:
    clean = strip_html_comments(html)
    m = re.search(r'(Position[s]?:)\s*</strong>\s*([^<]+)<', clean, flags=re.I)
    if not m:
        m = re.search(r'(Position[s]?:)\s*</span>\s*([^<]+)<', clean, flags=re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(2)).strip()
    m2 = re.search(r'(Position[s]?:\s*)([^<]+)', clean, flags=re.I)
    if m2:
        return re.sub(r"\s+", " ", m2.group(2)).strip()
    return None

def age_on(dob: date | None, ref: date | None = None) -> int | None:
    if not dob: return None
    ref = ref or date.today()
    return ref.year - dob.year - ((ref.month, ref.day) < (dob.month, dob.day))

def map_position_to_role(pos_text: str | None) -> str:
    if not pos_text: return "WM"
    t = pos_text.lower().replace("–","-").replace("/", " ").replace(",", " ")
    def has(pat): return re.search(pat, t) is not None
    ROLE_TOKENS = {
        "GK": [(r"\b(gk|goalkeeper)\b", 6)],
        "FB": [(r"\b(rb|lb|rwb|lwb|fb)\b", 6), (r"wing-?back", 6), (r"\bfull\s*back\b", 6)],
        "CB": [(r"\b(cb)\b", 6), (r"\b(centre|center)\s*back\b", 6), (r"\bdefender\b", 2)],
        "DM": [(r"\b(cdm|dm)\b", 6), (r"defensive\s*mid", 5)],
        "CM": [(r"\b(cm|mf)\b", 5), (r"\bmidfielder\b", 3), (r"central\s*mid", 6), (r"box-?to-?box", 5)],
        "AM": [(r"\b(cam|am)\b", 6), (r"attacking\s*mid", 6), (r"playmaker", 4), (r"no\.?\s*10\b", 5)],
        "WM": [(r"\b(rw|lw|rm|lm)\b", 6), (r"\bwinger\b", 6), (r"\bwide\s*midfielder\b", 5), (r"wide\s*forward", 5)],
        "FW": [(r"\b(st|cf|ss|fw)\b", 6), (r"\bstriker\b", 6), (r"\bforward\b", 4), (r"centre\s*forward", 6), (r"second\s*striker", 5)],
    }
    scores = {k: 0 for k in ROLE_TOKENS}
    for role, pats in ROLE_TOKENS.items():
        for pat, w in pats:
            if has(pat): scores[role] += w
    if "defender" in t and scores["CB"] == 0 and scores["FB"] == 0: scores["CB"] += 2
    max_score = max(scores.values()) if any(scores.values()) else 0
    if max_score == 0: return "WM"
    priority = ["GK", "FB", "CB", "FW", "WM", "AM", "CM", "DM"]
    role_guess = None
    for r in priority:
        if scores[r] == max_score:
            role_guess = r; break
    if role_guess == "CB" and re.search(r"\b(rb|lb|rwb|lwb|fb|wing-?back|full\s*back)\b", t):
        role_guess = "FB"
    return role_guess or "WM"

def try_online_fetch(driver, player_id: str):
    profile_url = f"{BASE}/en/players/{player_id}/"
    driver.get(profile_url); wait_page_ready(driver); time.sleep(0.8)
    profile_html = driver.page_source
    player_name = extract_player_name_from_profile(profile_html) or ""
    if not player_name:
        m2 = re.search(r"<title>([^<]+)</title>", profile_html, flags=re.I)
        if m2: player_name = clean_fbref_title_to_name(m2.group(1)) or ""
    dob = extract_dob_from_profile_html(profile_html)
    pos_text = extract_position_text_from_profile_html(profile_html)
    role = map_position_to_role(pos_text)

    slug_in_profile = None
    m = re.search(rf'/players/{player_id}/scout/365_m\d/([^/"<]+)', profile_html, flags=re.I)
    if m: slug_in_profile = re.split(r'"|<', m.group(1))[0]

    slug_cands = []
    if slug_in_profile: slug_cands.append(slug_in_profile)
    slug_cands += generate_slug_candidates(player_name)
    slug_cands += search_fbref_player_by_name(player_name)
    seen = set(); slug_cands = [s for s in slug_cands if not (s in seen or seen.add(s))]
    if not slug_cands: slug_cands = ["Lionel-Messi","Lionel-Andres-Messi","Messi"]

    html, chosen_url = try_all_scout_urls(driver, player_id, slug_cands, sleep=1.2)
    if not html:
        for cohort in COHORTS:
            for slug in slug_cands[:5]:
                guess = build_scout_url_with_cohort(player_id, slug, cohort)
                wb = wayback_fetch_if_needed(guess)
                if wb and ("Statistic" in wb or "Percentile" in wb):
                    return wb, chosen_url or guess, player_name, dob, pos_text, role
        raise RuntimeError("Slug/검색/아카이브 모두 실패 — 스카우팅 리포트에 접근 불가")
    return html, chosen_url, player_name, dob, pos_text, role

def run_online(player_id: str, headless=True):
    driver = start_driver(headless=headless)
    try:
        html, src_url, player_name, dob, pos_text, role = try_online_fetch(driver, player_id)
        df, meta = parse_scout_from_html(html)
        meta["age_years"] = age_on(dob)
        meta["position_text"] = pos_text
        meta["role"] = role
        meta["player_name"] = player_name
        return df, meta, src_url
    finally:
        driver.quit()

def run_offline(html_path: str):
    with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()
    df, meta = parse_scout_from_html(html)
    meta["age_years"] = None; meta["position_text"] = None
    meta["role"] = "WM"; meta["player_name"] = None
    return df, meta, None

# ================= 파싱 =================
def parse_scout_from_html(html: str):
    def _clean(txt): return re.sub(r"\s+", " ", txt or "").strip()
    soup = BeautifulSoup(strip_html_comments(html), "lxml")
    tables = []
    for tid in ["scout_summary_AM", "scout_full_AM", "scout_summary", "scout_full"]:
        t = soup.find("table", id=tid)
        if t: tables.append(t)
    if not tables:
        for t in soup.find_all("table", class_="stats_table"):
            txt = t.get_text(" ", strip=True)
            if "Statistic" in txt and "Percentile" in txt:
                tables.append(t)
    if not tables:
        raise RuntimeError("스카우팅 표를 찾지 못했습니다.")
    rows = []
    for table in tables:
        current_section = None
        tbody = table.find("tbody") or table
        for tr in tbody.find_all("tr", recursive=False):
            cls = " ".join(tr.get("class", []))
            if "over_header" in cls:
                ths = tr.find_all("th")
                if ths: current_section = _clean(ths[0].get_text())
                continue
            stat_th = tr.find("th", attrs={"data-stat": "statistic"})
            per90_td = tr.find("td", attrs={"data-stat": "per90"})
            pct_td   = tr.find("td", attrs={"data-stat": "percentile"})
            if not stat_th: continue
            statistic = _clean(stat_th.get_text())
            per90_txt = _clean(per90_td.get_text()) if per90_td else ""
            pct_txt   = _clean(pct_td.get_text()) if pct_td else ""
            def to_num(x):
                x = x.replace("%","").replace(",","") if x else ""
                try: return float(x)
                except: return None
            rows.append({
                "section": current_section or "Standard Stats",
                "statistic": statistic,
                "per90": to_num(per90_txt),
                "percentile": to_num(pct_txt),
            })
    df = pd.DataFrame(rows).dropna(subset=["statistic"]).reset_index(drop=True)
    meta = {"minutes_365d": parse_minutes_from_html(html), "tables_found": len(tables)}
    return df, meta

# ================= 스코어 계산 (원본 + 수정) =================
BASE_WEIGHTS_WM = {
    "Non-Penalty Goals": 1.20, "npxG": 1.10, "Shots Total": 0.60,
    "Assists": 1.10, "xAG": 1.00, "npxG + xAG": 1.00, "Shot-Creating Actions": 1.00,
    "Progressive Passes": 0.80, "Progressive Carries": 1.10, "Successful Take-Ons": 1.10,
    "Touches (Att Pen)": 0.70, "Progressive Passes Rec": 0.70, "Passes Attempted": 0.20,
    "Pass Completion %": -0.30, "Tackles": 0.10, "Interceptions": 0.10, "Blocks": 0.05,
    "Clearances": 0.02, "Aerials Won": 0.05,
}
WEIGHTS_BY_ROLE = {
    "FW": {**BASE_WEIGHTS_WM, "Successful Take-Ons": 0.9, "Progressive Carries": 0.9, "Shot-Creating Actions": 0.9,
           "Non-Penalty Goals": 1.6, "npxG": 1.4, "Shots Total": 0.9, "xAG": 0.8, "Aerials Won": 0.15,
           "Tackles": 0.05, "Interceptions": 0.05, "Blocks": 0.02, "Clearances": 0.01},
    "WM": BASE_WEIGHTS_WM,
    "AM": {**BASE_WEIGHTS_WM, "Non-Penalty Goals": 1.0, "npxG": 0.9, "Shots Total": 0.5, "Assists": 1.3,
           "xAG": 1.2, "Shot-Creating Actions": 1.4, "Progressive Passes": 1.1, "Progressive Carries": 1.0,
           "Successful Take-Ons": 1.0},
    "CM": {"Shot-Creating Actions": 1.0, "Assists": 0.9, "xAG": 0.9, "Progressive Passes": 1.4,
           "Passes Attempted": 0.8, "Pass Completion %": 0.5, "Progressive Carries": 0.8, "Tackles": 0.6,
           "Interceptions": 0.6, "Blocks": 0.2, "Clearances": 0.1, "Aerials Won": 0.2, "Non-Penalty Goals": 0.4,
           "npxG": 0.4, "Shots Total": 0.3, "Touches (Att Pen)": 0.4, "Successful Take-Ons": 0.5,
           "Progressive Passes Rec": 0.4, "npxG + xAG": 0.6},
    "DM": {"Progressive Passes": 1.5, "Passes Attempted": 1.0, "Pass Completion %": 0.8, "Tackles": 1.0,
           "Interceptions": 1.0, "Blocks": 0.6, "Clearances": 0.3, "Aerials Won": 0.4, "Shot-Creating Actions": 0.6,
           "Assists": 0.5, "xAG": 0.5, "Non-Penalty Goals": 0.2, "npxG": 0.2, "Shots Total": 0.2,
           "Progressive Carries": 0.6, "Touches (Att Pen)": 0.2, "Successful Take-Ons": 0.4, "npxG + xAG": 0.5,
           "Progressive Passes Rec": 0.2},
    "FB": {"Progressive Carries": 1.2, "Progressive Passes": 1.2, "Passes Attempted": 0.8, "Pass Completion %": 0.5,
           "Shot-Creating Actions": 0.9, "Assists": 0.8, "xAG": 0.7, "Tackles": 0.9, "Interceptions": 0.7,
           "Blocks": 0.5, "Clearances": 0.4, "Aerials Won": 0.3, "Non-Penalty Goals": 0.2, "npxG": 0.2,
           "Shots Total": 0.2, "Touches (Att Pen)": 0.6, "Successful Take-Ons": 0.6, "npxG + xAG": 0.6},
    "CB": {"Tackles": 1.2, "Interceptions": 1.2, "Blocks": 0.9, "Clearances": 1.3, "Aerials Won": 1.1,
           "Passes Attempted": 0.8, "Pass Completion %": 0.6, "Progressive Passes": 0.8, "Progressive Carries": 0.5,
           "Shot-Creating Actions": 0.2, "Assists": 0.2, "xAG": 0.2, "Non-Penalty Goals": 0.2, "npxG": 0.2,
           "Shots Total": 0.2, "Touches (Att Pen)": 0.1, "Successful Take-Ons": 0.2, "npxG + xAG": 0.2,
           "Progressive Passes Rec": 0.1},
    "GK": {"Passes Attempted": 0.5, "Pass Completion %": 0.5, "Aerials Won": 0.2, "Progressive Passes": 0.3,
           "Progressive Carries": 0.2, "Tackles": 0.3, "Interceptions": 0.3, "Blocks": 0.3, "Clearances": 0.4,
           "Shot-Creating Actions": 0.0, "Assists": 0.0, "xAG": 0.0, "Non-Penalty Goals": 0.0, "npxG": 0.0,
           "Shots Total": 0.0, "npxG + xAG": 0.0, "Touches (Att Pen)": 0.0, "Successful Take-Ons": 0.1,
           "Progressive Passes Rec": 0.0}
}

STAT_NORMALIZER = {
    "npxG + xAG": ["npxG + xAG"],
    "Passes Attempted": ["Passes Attempted"],
    "Pass Completion %": ["Pass Completion %"],
    "Touches (Att Pen)": ["Touches (Att Pen)"],
    "Shot-Creating Actions": ["Shot-Creating Actions"],
    "Successful Take-Ons": ["Successful Take-Ons"],
}

def pick_percentile(df: pd.DataFrame, key: str) -> float | None:
    cands = STAT_NORMALIZER.get(key, [key])
    for kk in cands:
        exact = df.loc[df["statistic"].str.casefold() == kk.casefold(), "percentile"]
        if len(exact):
            v = exact.iloc[0]; return float(v) if pd.notna(v) else None
    mask = df["statistic"].str.contains(rf"(?<!\w){re.escape(key)}(?!\w)", case=False, na=False, regex=True)
    if mask.any():
        v = df.loc[mask, "percentile"].iloc[0]
        return float(v) if pd.notna(v) else None
    return None

def base_score(df: pd.DataFrame, weights: dict) -> float:
    acc, total_w = 0.0, 0.0
    for k, w in weights.items():
        p = pick_percentile(df, k)
        if p is None: continue
        acc += w * p; total_w += abs(w)
    if total_w == 0: return 50.0
    return max(0.0, min(100.0, acc / total_w))

def reliability_bonus(minutes: int | None) -> float:
    if minutes is None: return 0.0
    lo, hi = 900, 3000
    x = (max(lo, min(hi, minutes)) - lo) / (hi - lo)
    return 3.0 * x

def age_adjustment(age_years: int | None) -> float:
    if age_years is None: return 0.0
    a = age_years
    if a <= 18: return 8.0
    if 19 <= a <= 27: return 8.0 * (28 - a) / 10.0
    if a == 28: return 0.0
    if 29 <= a <= 34: return -15.0 * (a - 28) / 6.0
    return -25.0

def squash_0_100(x: float) -> float:
    return max(0.0, min(100.0, 100.0 * (math.tanh((x - 50.0) / 25.0) * 0.5 + 0.5)))

# ===== 역할별 레이더 키 =====
RELEVANT_STATS_BY_ROLE = {
    "FW": [
        "Non-Penalty Goals","npxG","Shots Total","Assists","xAG","npxG + xAG",
        "Shot-Creating Actions","Progressive Carries","Successful Take-Ons",
        "Touches (Att Pen)","Progressive Passes Rec","Progressive Passes"
    ],
    "WM": [
        "Successful Take-Ons","Progressive Carries","Shot-Creating Actions",
        "Assists","xAG","npxG + xAG","Shots Total","Touches (Att Pen)",
        "Progressive Passes Rec","Progressive Passes"
    ],
    "AM": [
        "Shot-Creating Actions","Assists","xAG","npxG + xAG",
        "Progressive Passes","Progressive Carries","Successful Take-Ons","Shots Total"
    ],
    "CM": [
        "Progressive Passes","Passes Attempted","Pass Completion %","Shot-Creating Actions",
        "Progressive Carries","Tackles","Interceptions","Blocks","Aerials Won"
    ],
    "DM": [
        "Progressive Passes","Passes Attempted","Pass Completion %",
        "Tackles","Interceptions","Blocks","Clearances","Aerials Won"
    ],
    "FB": [
        "Progressive Carries","Progressive Passes","Shot-Creating Actions",
        "Assists","Passes Attempted","Pass Completion %","Tackles","Interceptions","Blocks"
    ],
    "CB": [
        "Tackles","Interceptions","Blocks","Clearances","Aerials Won",
        "Passes Attempted","Pass Completion %","Progressive Passes"
    ],
    "GK": [
        "Passes Attempted","Pass Completion %","Aerials Won","Tackles","Interceptions","Blocks","Clearances"
    ],
}

# ===== 플레이스타일별 레이더 키 =====
STYLE_RADAR_KEYS = {
    "Inverted Winger": ["Shots Total","npxG","Shot-Creating Actions","Successful Take-Ons","Touches (Att Pen)","Progressive Carries"],
    "Traditional Winger": ["Successful Take-Ons","Progressive Carries","Shot-Creating Actions","Assists","Passes Attempted","Touches (Att Pen)"],
    "Inside Forward": ["Non-Penalty Goals","npxG","Shots Total","Touches (Att Pen)","Successful Take-Ons","Progressive Carries"],
    "Wide Playmaker": ["Shot-Creating Actions","Progressive Passes","xAG","Assists","Passes Attempted","Progressive Carries"],

    "Poacher": ["Non-Penalty Goals","npxG","Shots Total","Touches (Att Pen)","Progressive Passes Rec"],
    "Target Man": ["Aerials Won","Non-Penalty Goals","Shots Total","Touches (Att Pen)","xAG"],
    "Pressing Forward": ["Tackles","Interceptions","Blocks","Shots Total","Successful Take-Ons"],
    "False Nine": ["Shot-Creating Actions","Assists","xAG","Progressive Passes","npxG + xAG"],

    "Classic 10": ["Shot-Creating Actions","Assists","xAG","Progressive Passes","Successful Take-Ons"],
    "Second Striker": ["Non-Penalty Goals","Shots Total","Shot-Creating Actions","Successful Take-Ons","npxG"],

    "Box-to-Box": ["Progressive Carries","Progressive Passes","Tackles","Interceptions","Shot-Creating Actions"],
    "Deep-Lying Playmaker": ["Progressive Passes","Passes Attempted","Pass Completion %","xAG","Shot-Creating Actions"],
    "Ball-Winning Midfielder": ["Tackles","Interceptions","Blocks","Aerials Won","Progressive Carries"],
    "Anchor": ["Interceptions","Tackles","Blocks","Clearances","Pass Completion %"],

    "Overlapping Wingback": ["Progressive Carries","Shot-Creating Actions","Assists","Progressive Passes"],
    "Inverted Fullback": ["Passes Attempted","Pass Completion %","Progressive Passes","Progressive Carries","Shot-Creating Actions"],
    "Defensive Fullback": ["Tackles","Interceptions","Blocks","Clearances","Pass Completion %"],

    "Ball-Playing CB": ["Progressive Passes","Passes Attempted","Pass Completion %","Aerials Won","Interceptions"],
    "Stopper CB": ["Tackles","Blocks","Aerials Won","Clearances","Interceptions"],
    "Sweeper CB": ["Interceptions","Blocks","Clearances","Progressive Passes","Pass Completion %"],
}

# =============== 그룹 스코어 ===============
GROUP_KEYS = {
    "g_prod": ["Non-Penalty Goals","npxG","Shots Total","Assists","xAG","npxG + xAG"],
    "g_progress": ["Progressive Passes","Progressive Carries","Progressive Passes Rec","Passes Attempted"],
    "g_chance": ["Shot-Creating Actions","Assists","xAG","Successful Take-Ons","Touches (Att Pen)"],
    "g_stability": ["Pass Completion %","Tackles","Interceptions","Blocks","Clearances","Aerials Won"],
}

def _avg_percentile(df: pd.DataFrame, keys: list[str]) -> float:
    vals = [pick_percentile(df, k) for k in keys]
    vals = [float(v) for v in vals if v is not None]
    return float(np.mean(vals)) if vals else 50.0

def compute_group_scores(df: pd.DataFrame) -> dict:
    return {k: _avg_percentile(df, v) for k, v in GROUP_KEYS.items()}

# =============== 플레이스타일 엔진 (fuzzy) ===============
def _score_combo(df: pd.DataFrame, items: list[tuple[str, float]]) -> float:
    acc, wsum = 0.0, 0.0
    for k, w in items:
        p = pick_percentile(df, k)
        if p is None: continue
        acc += w * p; wsum += abs(w)
    if wsum == 0: return 0.0
    return acc / wsum

def infer_playstyles(df: pd.DataFrame, role: str) -> dict:
    r = role.upper()
    cand: dict[str, list[tuple[str,float]]] = {}
    if r in ("WM","FW"):
        cand.update({
            "Inverted Winger": [("Shots Total",1.0), ("npxG",1.2), ("Successful Take-Ons",0.8), ("Touches (Att Pen)",0.8), ("Progressive Carries",0.7)],
            "Traditional Winger": [("Successful Take-Ons",1.2), ("Progressive Carries",1.0), ("Shot-Creating Actions",1.0), ("Assists",0.9)],
            "Inside Forward": [("Non-Penalty Goals",1.3), ("npxG",1.2), ("Shots Total",1.0), ("Touches (Att Pen)",0.8)],
            "Wide Playmaker": [("Shot-Creating Actions",1.2), ("Progressive Passes",1.0), ("xAG",1.0), ("Assists",1.0)],
            "Pressing Forward": [("Tackles",1.0), ("Interceptions",0.9), ("Blocks",0.7), ("Successful Take-Ons",0.5)],
            "Poacher": [("Non-Penalty Goals",1.3), ("npxG",1.1), ("Shots Total",1.0), ("Progressive Passes Rec",0.8)],
            "Target Man": [("Aerials Won",1.3), ("Non-Penalty Goals",1.0), ("Shots Total",0.8)],
            "False Nine": [("Shot-Creating Actions",1.2), ("Assists",1.1), ("xAG",1.0), ("Progressive Passes",1.0)],
        })
    elif r == "AM":
        cand.update({
            "Classic 10": [("Shot-Creating Actions",1.3), ("Assists",1.2), ("xAG",1.0), ("Progressive Passes",1.0)],
            "Second Striker": [("Non-Penalty Goals",1.0), ("Shots Total",1.0), ("Shot-Creating Actions",1.0), ("Successful Take-Ons",0.8)],
            "Wide Playmaker": [("Shot-Creating Actions",1.1), ("xAG",1.0), ("Assists",1.0), ("Progressive Carries",0.8)],
        })
    elif r == "CM":
        cand.update({
            "Box-to-Box": [("Progressive Carries",1.0), ("Progressive Passes",1.0), ("Tackles",0.9), ("Interceptions",0.9), ("Shot-Creating Actions",0.7)],
            "Deep-Lying Playmaker": [("Progressive Passes",1.3), ("Passes Attempted",1.0), ("Pass Completion %",1.0), ("xAG",0.7)],
            "Ball-Winning Midfielder": [("Tackles",1.3), ("Interceptions",1.2), ("Blocks",0.8), ("Aerials Won",0.6)],
        })
    elif r == "DM":
        cand.update({
            "Anchor": [("Interceptions",1.2), ("Tackles",1.1), ("Blocks",1.0), ("Clearances",0.9), ("Pass Completion %",0.8)],
            "Deep-Lying Playmaker": [("Progressive Passes",1.3), ("Passes Attempted",1.0), ("Pass Completion %",1.0)],
            "Ball-Winning Midfielder": [("Tackles",1.3), ("Interceptions",1.2), ("Blocks",0.8), ("Aerials Won",0.6)],
        })
    elif r == "FB":
        cand.update({
            "Overlapping Wingback": [("Progressive Carries",1.2), ("Shot-Creating Actions",1.0), ("Assists",1.0), ("Progressive Passes",0.9)],
            "Inverted Fullback": [("Passes Attempted",1.0), ("Pass Completion %",1.0), ("Progressive Passes",1.0), ("Progressive Carries",0.7)],
            "Defensive Fullback": [("Tackles",1.1), ("Interceptions",1.0), ("Blocks",0.8), ("Clearances",0.8)],
        })
    elif r == "CB":
        cand.update({
            "Ball-Playing CB": [("Progressive Passes",1.2), ("Passes Attempted",1.0), ("Pass Completion %",1.0), ("Interceptions",0.6)],
            "Stopper CB": [("Tackles",1.2), ("Blocks",1.0), ("Aerials Won",0.9), ("Clearances",0.9)],
            "Sweeper CB": [("Interceptions",1.2), ("Blocks",1.0), ("Clearances",0.9), ("Pass Completion %",0.7)],
        })
    else:
        cand.update({"Generic": [("Passes Attempted",1.0), ("Pass Completion %",1.0)]})

    scores = {name: _score_combo(df, items) for name, items in cand.items()}
    return scores

def explain_playstyle(df: pd.DataFrame, style: str) -> list[str]:
    keys = STYLE_RADAR_KEYS.get(style, []) or []
    reasons = []
    for k in keys:
        p = pick_percentile(df, k)
        if p is None: continue
        if p >= 80:
            reasons.append(f"{k} 상위 {int(round(p))}퍼센(강점)")
        elif p <= 30:
            reasons.append(f"{k} 하위 {int(round(100-p))}퍼센(보완)")
    return reasons[:6]

def improvement_points(df: pd.DataFrame, style: str, role: str) -> list[str]:
    keys = STYLE_RADAR_KEYS.get(style) or RELEVANT_STATS_BY_ROLE.get(role, [])
    pts = []
    for k in keys:
        p = pick_percentile(df, k)
        if p is not None and p < 40:
            pts.append(f"{k} 개선 필요(현재 {int(p)}퍼센)")
    return pts[:6]
# ====== (REPLACE) 스타일별 코칭 어드바이스: 더 다양하고 디테일하게 ======
def style_coaching_advice(df: pd.DataFrame, style: str, role: str, top_n: int = 6) -> list[str]:
    """
    - 플레이스타일 핵심 스탯의 현재 퍼센타일을 기준으로 '개별 맞춤' 코칭 포인트를 풍부하게 생성
    - 기술/전술/신체/멘탈/비디오 분석 관점까지 포함 (중복 제거, 상한 top_n)
    """
    def pct(key): 
        v = pick_percentile(df, key); 
        return None if v is None else float(v)

    def add_unique(lst, item):
        if item and item not in lst:
            lst.append(item)

    keys = STYLE_RADAR_KEYS.get(style) or RELEVANT_STATS_BY_ROLE.get(role, [])
    pts: list[str] = []

    # ── 1) 핵심 스탯 기반 보정형 조언(자동 생성) ───────────────────────────────
    for k in keys:
        p = pct(k)
        if p is None:
            continue
        # 하위권이면 개선 루틴 제시
        if p < 35:
            add_unique(pts, f"{k} 개선 루틴: 스텝별(기초→속도→압박 하) 반복 / 주 3회(20분)")
        elif p < 50:
            add_unique(pts, f"{k} 안정화: 상황별 반복(반전/오픈바디 추가) / 주 2회(15분)")
        elif p < 70:
            add_unique(pts, f"{k} 상향: 난이도 상승(제한터치·시간압박) / 주 2회(10분)")
        else:
            # 상위면 유지·응용
            add_unique(pts, f"{k} 유지+응용: 역압박 상황 전개/선택지 추가 / 주 1회(클립 5개)")

    # ── 2) 플레이스타일 '유형별' 고정 팁(전술/기술/멘탈) ──────────────────────────
    s = style
    if s in ("Inverted Winger", "Inside Forward"):
        add_unique(pts, "컷인 후 파이널 의사결정 트리(슈팅 vs 패스 vs 리턴) 훈련")
        add_unique(pts, "원터치/투터치 마무리: 니어·파 원포인트 마커 타깃팅")
        add_unique(pts, "하프스페이스 수비유인→월패스→침투 패턴(3인) 주 2세션")
    if s in ("Traditional Winger", "Overlapping Wingback"):
        add_unique(pts, "크로스 3종(드리븐/칠드/컷백) 정확도 KPI 트래킹")
        add_unique(pts, "사선 돌파 이후 '컷백 각도' 스캔 루틴(시선-발목 각)")
        add_unique(pts, "오버/언더래핑 타이밍: 8/10번과 트리거 싱크 맞추기")
    if s in ("Wide Playmaker", "Classic 10", "False Nine", "Deep-Lying Playmaker"):
        add_unique(pts, "리버스/스루 타이밍: 마지막 두 수비자 사이 창 만들기")
        add_unique(pts, "프리셉션(시야/체형) → 터치 방향으로 패스 궤도 열기")
        add_unique(pts, "프레임 압박 시 ‘안전-전진-리스크’ 우선순위 선택지 훈련")
    if s in ("Pressing Forward", "Ball-Winning Midfielder", "Defensive Fullback", "Stopper CB"):
        add_unique(pts, "압박 트리거(백패스/터치 과대/등지는 수비수) 반응 속도")
        add_unique(pts, "전환(Positive/Negative) 3초 룰: 첫 스텝/각도/커버쉐도우")
        add_unique(pts, "대인+공간 혼합: 시야 체크 주기/몸 방향·밸런스 유지")

    # ── 3) 신체/멘탈/비디오 세부 팁(스타일 공통 + 역할 가중) ───────────────────
    r = role.upper()
    if r in ("WM","FW","AM"):
        add_unique(pts, "피니시 효율: xG 대비 득점 효율 주간 리포트 모니터링")
        add_unique(pts, "멘탈: 선택지 과부하 방지(사전 스캔→간결 루틴)")
    if r in ("CM","DM"):
        add_unique(pts, "첫터치·체형 열기 루틴: 4방향 컨트롤·원스텝 패스")
        add_unique(pts, "멘탈: 리스크 관리(누적 턴오버 감축 목표 설정)")
    if r == "FB":
        add_unique(pts, "가속-감속 드릴(사이드라인 5-10-5 리피트)")
        add_unique(pts, "영상: 크로스 이전 마지막 2터치의 각·시선 클립화")
    if r == "CB":
        add_unique(pts, "에어리얼 타점+스텝: 세트피스 수비 재연 10회×3세트")
        add_unique(pts, "라인 컨트롤: 커버-스텝업 콜 단일화(리더십 어사인)")
    if r == "GK":
        add_unique(pts, "스위핑 범위 판단: 뒷공간 수비 1v1 스피드 결정 루틴")
        add_unique(pts, "킥 정확도 KPI: 빌드업 첫 패스 성공률 85%+ 타깃")

    # 상한 자르고 리턴
    return pts[:top_n]


# ====== (NEW) 스타일별 KPI 타깃 생성 (로드맵에 쓰임) ======
def style_kpi_targets(df: pd.DataFrame, style: str, role: str) -> list[str]:
    """
    플레이스타일/역할에 맞는 KPI 목표를 숫자로 제시(대상 스탯의 '구간 상향'을 목표로).
    """
    def tgt_line(stat, from_p=None, to_p=70):
        if from_p is not None:
            return f"{stat}: {int(from_p)}→{to_p} 퍼센 상향"
        return f"{stat}: {to_p} 퍼센 이상"
    out = []
    keys = STYLE_RADAR_KEYS.get(style) or RELEVANT_STATS_BY_ROLE.get(role, [])
    # 중요도상 앞 4~5개만
    for k in keys[:5]:
        p = pick_percentile(df, k)
        if p is None: 
            continue
        # 현재 구간에 따라 목표치 차등
        if p < 40: out.append(tgt_line(k, p, 60))
        elif p < 60: out.append(tgt_line(k, p, 70))
        elif p < 75: out.append(tgt_line(k, p, 80))
        else: out.append(tgt_line(k, p, 85))
    # 스타일 특화 보너스 KPI
    s = style
    if s in ("Traditional Winger","Overlapping Wingback"):
        out.append("Crossing(품질 클립 기준): 경기당 온타깃 2+회")
    if s in ("Inverted Winger","Inside Forward"):
        out.append("컷인 후 슈팅: 경기당 유효슈팅 1.0+회")
    if s in ("Classic 10","Wide Playmaker","False Nine","Deep-Lying Playmaker"):
        out.append("프로그레시브 패스: 80퍼센+ 유지")
        out.append("Shot-Creating Actions: 70퍼센+")
    if s in ("Pressing Forward","Ball-Winning Midfielder","Defensive Fullback","Stopper CB"):
        out.append("턴오버 유도/리커버리: 경기당 2.0+")
    return out[:6]


# ====== (NEW) 스타일별 '잠재력 로드맵' (단계·과업·KPI) ======
def style_growth_roadmap(style: str, role: str, age_years: int | None, df: pd.DataFrame) -> list[str]:
    """
    ① 0~6주(기초/교정) ② 6~12주(난이도 상승/재현성) ③ 12주+(경쟁레벨 전이) 식 단계 로드맵을 생성.
    스타일/역할, 나이, 현재 지표를 고려해 단계별 과업과 KPI를 혼합 제시.
    """
    def phase(title, bullets): 
        nonlocal out; 
        if bullets: out.append(f" · {title}: " + " / ".join(bullets))
    out: list[str] = []

    # 공통 과업(연령/역할 보정)
    common0 = []
    if (age_years is not None) and age_years < 22:
        common0.append("기술 스킬 볼륨 확장(주 3세션)")
    else:
        common0.append("고난도 상황 반복(압박/시간 제약) 주 2세션")
    if role.upper() in ("CM","DM","CB","FB"):
        common0.append("첫터치·체형 열기 루틴(매일 10분)")
    else:
        common0.append("파이널 서드 의사결정 트리 15분")

    # 스타일 핵심 과업
    s = style
    p1, p2, p3 = [], [], []

    if s in ("Inverted Winger","Inside Forward"):
        p1 += ["컷인→원터치/투터치 마무리 50회", "하프스페이스 진입 각 만들기(콘 패턴)"]
        p2 += ["슈팅 의사결정(니어/파/리턴) 시뮬 20세트", "좌우 발 동일 루틴(균형)"]
        p3 += ["상위권 DF 상대 1v1 클립 5개 분석·복기", "xG 대비 득점 효율 5%p↑"]
    if s in ("Traditional Winger","Overlapping Wingback"):
        p1 += ["크로스 3종 30회×3세트(드리븐/칠드/컷백)", "오버랩 타이밍 시그널 합"]
        p2 += ["하프스페이스-와이드 전환 템포 조절", "크로스 사전 스캔(수신자 수·거리)"]
        p3 += ["온타깃 크로스 KPI 달성(경기당 2+)"]
    if s in ("Wide Playmaker","Classic 10","False Nine","Deep-Lying Playmaker"):
        p1 += ["프리셉션 각도 교정(45°/90°)", "리버스/스루 타이밍: 더미 2명"]
        p2 += ["압박 하 전진패스(제한터치) 반복", "세컨드볼 후 즉시 전개 패턴"]
        p3 += ["SCA 70퍼센+ 달성", "프로그레시브 패스 80퍼센+ 유지"]
    if s in ("Pressing Forward","Ball-Winning Midfielder","Defensive Fullback","Stopper CB"):
        p1 += ["트리거 반응 훈련(백패스/등지는 수비수)", "첫 두 스텝 폭발력(5-10-5)"]
        p2 += ["커버쉐도우 각도 유지(2선 차단)", "전환 3초 룰 성공률 모니터링"]
        p3 += ["턴오버 유도/리커버리 2.0+ 유지"]

    # KPI 타깃 보강
    kpis = style_kpi_targets(df, style, role)

    # 단계 조립
    phase("0~6주", common0 + p1[:3])
    phase("6~12주", p2[:3])
    phase("12주+", p3[:3] + kpis[:2])

    # 중복 제거
    seen = set(); final = []
    for x in out:
        if x not in seen:
            seen.add(x); final.append(x)
    return final[:4]


# =============== 강점/약점 (역할 인지) ===============
def role_aware_strengths_weaknesses(df: pd.DataFrame, role: str) -> dict:
    weights = WEIGHTS_BY_ROLE.get(role, BASE_WEIGHTS_WM)
    rows = []
    for stat in set(list(weights.keys()) + df["statistic"].dropna().tolist()):
        p = pick_percentile(df, stat)
        if p is None: continue
        w = weights.get(stat, 0.0)
        rows.append((stat, p, w))
    strengths = sorted(
        [dict(statistic=s, percentile=p) for (s,p,w) in rows if p >= 70 and w > 0.2],
        key=lambda x: x["percentile"], reverse=True
    )[:10]
    weaknesses = sorted(
        [dict(statistic=s, percentile=p) for (s,p,w) in rows if p <= 35 and w > 0.4],
        key=lambda x: x["percentile"]
    )[:10]
    return {"top_strengths": strengths, "top_weaknesses": weaknesses}

# =============== 정량 스코어 (원본 로직 복구) ===============
def strengths_weaknesses_pos(df: pd.DataFrame, role: str, k=5, hi_thresh=80.0, lo_thresh=55.0):
    # 기존 함수도 유지(레이거시 호출 대비); 내부에선 role_aware_* 사용
    r = role_aware_strengths_weaknesses(df, role)
    return r["top_strengths"][:k], r["top_weaknesses"][:k]

def compress_variance(x: float, center: float = 60.0, k: float = 0.85) -> float:
    return center + k * (x - center)

def score_from_df(df: pd.DataFrame, minutes: int | None, age_years: int | None, role: str = "WM"):
    weights = WEIGHTS_BY_ROLE.get(role, BASE_WEIGHTS_WM)
    base = round(base_score(df, weights), 1)
    r_bonus = round(reliability_bonus(minutes), 1)
    a_adj = round(age_adjustment(age_years), 1)   # 표시만
    raw = base + r_bonus                          # 나이 보정 제외(원본 유지)
    final = round(squash_0_100(raw), 1)
    final = round(compress_variance(final, 60.0, 0.85), 1)
    # 역할 인지 강/약점
    rw = role_aware_strengths_weaknesses(df, role)
    top5 = rw["top_strengths"][:5]
    low5 = rw["top_weaknesses"][:5]
    return {
        "base_from_percentiles": base,
        "reliability_bonus": r_bonus,
        "age_adjustment": a_adj,
        "final_score_0_100": final,
        "top_strengths": top5,
        "top_weaknesses": low5,
        "role_used": role
    }

# ========= Potential v3 =========
def P(keys): return keys

PKEYS = {
    "prod":      P(["Non-Penalty Goals","npxG","Assists","xAG","npxG + xAG","Shots Total"]),
    "progress":  P(["Progressive Passes","Progressive Carries","Successful Take-Ons","Progressive Passes Rec","Touches (Att Pen)"]),
    "chance":    P(["Shot-Creating Actions"]),
    "stability": P(["Passes Attempted","Pass Completion %"]),
}

def safe_pick(df, key):
    v = pick_percentile(df, key)
    return float(v) if v is not None else None

def group_stat(df, keys, agg="mean", shrink_to=50.0, shrink_w=0.0):
    vals = []
    for k in keys:
        v = safe_pick(df, k)
        if v is not None:
            v = (1 - shrink_w) * v + shrink_w * shrink_to
            vals.append(v)
    if not vals: return None
    if agg == "mean": return float(np.mean(vals))
    if agg == "max": return float(np.max(vals))
    if agg == "median": return float(np.median(vals))
    return float(np.mean(vals))

def minutes_shrink_weight(minutes):
    if minutes is None: return 0.45
    lo, hi = 900, 2700
    x = 1.0 - (max(lo, min(hi, minutes)) - lo) / (hi - lo)
    return 0.60 * x

def elite_counts(df):
    s = df["percentile"].dropna()
    c95 = int((s >= 95).sum()); c99 = int((s >= 99).sum())
    return c95, c99

def diversity_score(df):
    s = df.dropna(subset=["percentile"]); s = s[s["percentile"] >= 85]
    if s.empty: return 0.0
    def bucket(name):
        n = name.lower()
        if any(w in n for w in ["xag","assist","key","shot-creating"]): return "chance"
        if any(w in n for w in ["npxg","xg","goal"]): return "scoring"
        if any(w in n for w in ["progress","carry","take-on","touches"]): return "progress"
        if any(w in n for w in ["pass"]): return "pass"
        if any(w in n for w in ["tackle","interception","block","clearance","aerial"]): return "def"
        return "other"
    buckets = s["statistic"].map(bucket).value_counts(normalize=True).values
    ent = -np.sum([p * math.log(p + 1e-9) for p in buckets])
    return float(min(1.0, ent / 1.6))

def imbalance_penalty(g_list):
    arr = [x for x in g_list if x is not None]
    if not arr: return 0.0
    gap = max(arr) - min(arr)
    return 0.25 * gap

def age_curve_potential_strict(age):
    if age is None: return 0.50
    a = float(age)
    if a <= 18: return 0.80
    if 19 <= a <= 21: return 0.75
    if 22 <= a <= 24: return 0.70
    if 25 <= a <= 26: return 0.62
    if a == 27: return 0.50
    if a == 28: return 0.40
    if 29 <= a <= 30: return 0.32
    if 31 <= a <= 32: return 0.25
    if a == 33: return 0.18
    if a == 34: return 0.14
    if a == 35: return 0.10
    return 0.08

def uncertainty_penalty_strict(minutes, age):
    if minutes is None: pen = 10.0
    elif minutes < 600: pen = 9.0
    elif minutes < 1200: pen = 7.5
    elif minutes < 1800: pen = 5.0
    elif minutes < 2400: pen = 3.0
    else: pen = 1.0
    if (age is not None) and (age >= 24) and (minutes is not None) and (minutes < 1200):
        pen += 2.0
    return min(12.0, pen)

SCORE_CENTER = 60.0
FINAL_COMPRESS = 0.85
POTENTIAL_COMPRESS = 0.85
def potential_score_v3(df, minutes=None, age_years=None, role: str | None = None):
    """
    v3 잠재력 점수:
    - 그룹지표(생산/전진/찬스/안정) 평균 + 엘리트지표(95/99p) + 다양성(엔트로피)
    - 나이 잠재곡선 + 출전시간 불확실성 페널티 + 불균형 페널티
    - 0~100 스쿼시 & 나이별 상한 캡 & 분산 압축
    """
    # 출전시간이 적을수록 shrink 강하게(50쪽으로 수축)
    shrink_w = minutes_shrink_weight(minutes)

    g_prod = group_stat(df, PKEYS["prod"],     "mean", 50.0, shrink_w) or 50.0
    g_prog = group_stat(df, PKEYS["progress"], "mean", 50.0, shrink_w) or 50.0
    g_ch   = group_stat(df, PKEYS["chance"],   "mean", 50.0, shrink_w) or 50.0
    g_stb  = group_stat(df, PKEYS["stability"],"mean", 50.0, shrink_w) or 50.0

    # 안정성은 과도한 '짧은패스% 뻥튀기' 보정을 위해 15% 역가중(낮을수록 약간 가산)
    pass_comp = safe_pick(df, "Pass Completion %")
    if pass_comp is not None:
        g_stb = 0.85 * g_stb + 0.15 * (100.0 - pass_comp)

    c95, c99 = elite_counts(df)       # 상위 95/99 백분위 항목 개수
    div      = diversity_score(df)    # 0~1
    agep     = age_curve_potential_strict(age_years)  # 0~1

    # 나이에 따른 엘리트/다양성 보너스 감쇠
    if age_years is None:
        age_bonus_decay = 0.85
    else:
        a = float(age_years)
        if a <= 24:   age_bonus_decay = 1.00
        elif a <= 27: age_bonus_decay = 0.90
        elif a <= 30: age_bonus_decay = 0.75
        elif a <= 32: age_bonus_decay = 0.60
        elif a <= 34: age_bonus_decay = 0.50
        else:         age_bonus_decay = 0.45

    # 합성 원시 점수
    base_pot   = (0.35*g_prod + 0.25*g_prog + 0.15*g_ch + 0.10*g_stb)
    ceiling    = (0.60 * c95 + 1.35 * c99) * age_bonus_decay
    div_bonus  = (4.0 * div) * age_bonus_decay
    imb_pen    = 0.20 * (max([g_prod,g_prog,g_ch,g_stb]) - min([g_prod,g_prog,g_ch,g_stb]))
    age_gain   = 12.5 * agep
    unc_raw    = uncertainty_penalty_strict(minutes, age_years)
    unc_pen    = 0.85 * unc_raw

    # 소폭 오프셋(-3)으로 중앙값 보정
    raw = base_pot + ceiling + div_bonus + age_gain - unc_pen - imb_pen - 3.0

    # 나이별 상한(절대치 캡)
    def age_cap(age):
        if age is None: return 98.0
        a = float(age)
        if a <= 22: return 99.0
        if a <= 24: return 96.0
        if a <= 27: return 92.0
        if a == 28: return 90.0
        if a == 29: return 88.0
        if a == 30: return 86.0
        if a == 31: return 84.0
        if a == 32: return 82.0
        if a == 33: return 80.0
        if a == 34: return 78.0
        if a == 35: return 74.0
        return 72.0

    pot = squash_0_100(raw)
    pot = min(pot, age_cap(age_years))
    pot = round(compress_variance(pot, SCORE_CENTER, POTENTIAL_COMPRESS), 1)

    details = {
        "g_prod": round(g_prod,1),
        "g_progress": round(g_prog,1),
        "g_chance": round(g_ch,1),
        "g_stability": round(g_stb,1),
        "elite_p95_count": c95,
        "elite_p99_count": c99,
        "diversity_0_1": round(div,3),
        "imbalance_penalty": round(imb_pen,1),
        "uncertainty_penalty": round(unc_pen,1),
        "age_curve_0_1": round(agep,3),
        "age_gain": round(age_gain,1),
        "raw_before_squash": round(raw,1),
        "age_bonus_decay": round(age_bonus_decay,2),
        "age_cap": age_cap(age_years),
        "mode": "v3",
        "star_bias_penalty": None,
    }
    return round(pot,1), details

def compute_full_scores(df, meta, role):
    minutes = meta.get("minutes_365d")
    age_yrs = meta.get("age_years")
    base_pack = score_from_df(df, minutes=minutes, age_years=age_yrs, role=role)
    pot, pot_details = potential_score_v3(df, minutes=minutes, age_years=age_yrs, role=role)
    return base_pack, pot, pot_details

# ================= Wikipedia 연동(비정량) =================
PREFERRED_LANGS = ["en","ko","pt","es","fr","de","it"]
MIN_WIKI_CHARS = 1200

def _cleanup_text(text: str) -> str:
    if not text: return ""
    text = _html.unescape(text)
    text = re.sub(r"\[\d+\]", "", text)
    text = re.sub(r"\[note\s*\d+\]", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()

def _try_extracts(lang: str, title: str, timeout=10):
    url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {"action":"query","prop":"extracts","explaintext":1,"exsectionformat":"plain","redirects":1,"format":"json","titles":title}
    r = requests.get(url, headers=WIKI_UA_HEADERS, params=params, timeout=timeout)
    if r.status_code == 200:
        data = r.json()
        for p in data.get("query", {}).get("pages", {}).values():
            ext = p.get("extract")
            if ext and ext.strip():
                return f"https://{lang}.wikipedia.org/wiki/{quote(title)}", _cleanup_text(ext), "extracts"
    return None, "", None

def _try_html(lang: str, title: str, timeout=10):
    url = f"https://{lang}.wikipedia.org/wiki/{quote(title)}"
    r = requests.get(url, headers=WIKI_UA_HEADERS, timeout=timeout)
    if r.status_code == 200 and r.text:
        soup = BeautifulSoup(r.text, "lxml")
        root = soup.select_one("div.mw-parser-output") or soup
        # 쓸모없는 블록 제거
        for junk in ["table.infobox","div.reflist","ol.references","table.metadata","div.navbox","table.vertical-navbox","div.hatnote","table.toc"]:
            for t in root.select(junk): 
                try: t.decompose()
                except: pass
        txt = " ".join([p.get_text(" ", strip=True) for p in root.select("p")])
        txt = _cleanup_text(txt)
        if len(txt) > 200:
            return url, txt, "html"
    return None, "", None

def fetch_wikipedia_fulltext(name: str, timeout_each=8):
    if not name: 
        return None, "", None
    # 우선 영어 요약 → 부족하면 현지어 순회
    url, txt, ep = _try_extracts("en", name, timeout=timeout_each)
    if not txt or len(txt) < MIN_WIKI_CHARS:
        for lang in PREFERRED_LANGS:
            url, txt, ep = _try_extracts(lang, name, timeout=timeout_each)
            if txt and len(txt) >= MIN_WIKI_CHARS: 
                break
    if not txt or len(txt) < 600:
        # 마지막으로 HTML 파싱
        for lang in PREFERRED_LANGS:
            url, txt, ep = _try_html(lang, name, timeout=timeout_each)
            if txt and len(txt) >= 600: 
                break
    return url, txt, ep

def analyze_wiki_qual(text: str) -> dict:
    """키워드 매칭으로 신호 횟수 산출."""
    low = (text or "").lower()
    def cnt(pats):
        c = 0
        for pat in pats:
            c += len(re.findall(pat, low, flags=re.I))
        return c
    return {
        "injury_hits": cnt(QUAL_KEYWORDS["injury"]),
        "discipline_hits": cnt(QUAL_KEYWORDS["discipline"]),
        "transfer_hits": cnt(QUAL_KEYWORDS["transfer"]),
        "char_pos_hits": cnt(QUAL_KEYWORDS["character_pos"]),
        "char_neg_hits": cnt(QUAL_KEYWORDS["character_neg"]),
        "recent_w": 1.0,  # 심플: 최근 가중 미적용(원하면 뉴스/연표 파싱 추가)
    }

def qualitative_score(signals: dict, age_years: int | None = None) -> float:
    """
    비정량 v2.1 (연령 보정 없음):
      - 기본 100점에서 시작
      - 긍정(캐릭터+)은 가산, 부정(부상/징계/이적소동/캐릭터-)은 감산
      - 0 ~ 120 사이로 클램프
    가중치(1 히트당):
      + character_pos_hits : +2.5
      - injury_hits        : -2.0
      - discipline_hits    : -3.0
      - transfer_hits      : -1.5
      - char_neg_hits      : -2.0
    """
    if not signals:
        return 100.0

    base = 100.0
    pos = float(signals.get("char_pos_hits", 0))
    inj = float(signals.get("injury_hits", 0))
    dsc = float(signals.get("discipline_hits", 0))
    trf = float(signals.get("transfer_hits", 0))
    neg = float(signals.get("char_neg_hits", 0))

    delta = (
        + 2.5 * pos
        - 2.0 * inj
        - 3.0 * dsc
        - 1.5 * trf
        - 2.0 * neg
    )

    return max(0.0, min(120.0, base + delta))



# =============== 레이더 선택 =============== 
def choose_radar_keys(role: str, primary_style: str | None) -> list[str]:
    if primary_style and primary_style in STYLE_RADAR_KEYS:
        return STYLE_RADAR_KEYS[primary_style]
    return RELEVANT_STATS_BY_ROLE.get(role, RELEVANT_STATS_BY_ROLE["WM"])

# =============== 내러티브 생성 ===============
def ai_assess_current(scored: dict, role: str) -> str:
    parts = []
    parts.append(f"[현재력] 역할={role}, 최종점수={scored.get('final_score_0_100')}")
    if scored.get("top_strengths"):
        xs = ", ".join(f"{d['statistic']}({int(d['percentile'])}p)" for d in scored["top_strengths"][:5])
        parts.append(f"강점: {xs}")
    if scored.get("top_weaknesses"):
        xs = ", ".join(f"{d['statistic']}({int(d['percentile'])}p)" for d in scored["top_weaknesses"][:5])
        parts.append(f"약점(역할기반): {xs}")
    parts.append(f"기초={scored.get('base_from_percentiles')}, 출전보정={scored.get('reliability_bonus')}, 나이표시={scored.get('age_adjustment')}")
    return " / ".join(parts)

def ai_assess_potential_strict(pot: float, pot_details: dict, role: str) -> str:
    parts = []
    parts.append(f"[잠재력 v3] 역할={role}, 잠재점수={pot}")
    parts.append(f"그룹: 생산{int(pot_details.get('g_prod',0))}/전진{int(pot_details.get('g_progress',0))}/찬스{int(pot_details.get('g_chance',0))}/안정{int(pot_details.get('g_stability',0))}")
    parts.append(f"엘리트95+ {pot_details.get('elite_p95_count',0)}, 99+ {pot_details.get('elite_p99_count',0)}, 다양성={pot_details.get('diversity_0_1',0)}")
    parts.append(f"불확실성패널티={pot_details.get('uncertainty_penalty',0)}, 불균형패널티={pot_details.get('imbalance_penalty',0)}, 나이이득={pot_details.get('age_gain',0)}")
    return " / ".join(parts)

# =============== 메인 분석(리포트 생성) ===============
def analyze_player(player_id: str,
                   html_path: str | None = None,
                   role_override: str | None = None,
                   headless: bool = True,
                   outroot: str | None = None) -> dict:
    """
    - 온라인/오프라인 파싱 → 점수 계산(현재/잠재 v3) → 플레이스타일 추론
    - 스타일/역할 레이더 → 강/약점 바차트 → Narrative + 스타일별 코칭/로드맵 → HTML 리포트 저장
    """
    import webbrowser

    # 1) 데이터 로드
    if html_path:
        df, meta, src = run_offline(html_path)
    else:
        df, meta, src = run_online(player_id, headless=headless)

    # 2) 역할 확정(override 우선)
    role = (role_override or meta.get("role") or "WM").upper()

    # 3) 정량(현재) & 잠재(v3)
    base_pack, pot, pot_details = compute_full_scores(df, meta, role)

    # 4) 비정량(Wikipedia) → 신호/점수
    wiki_url, wiki_text, wiki_ep = fetch_wikipedia_fulltext(meta.get("player_name") or "")
    qual_signals = analyze_wiki_qual(wiki_text)
    qual_score = round(qualitative_score(qual_signals, meta.get("age_years")), 1)


    # 5) 종합 스코어(정량:정성 = 70:30)
    quant_current = float(base_pack["final_score_0_100"])
    quant_potential = float(pot)
    final_current = round(QUANT_WEIGHT * quant_current + QUAL_WEIGHT * qual_score, 1)
    final_potential = round(QUANT_WEIGHT * quant_potential + QUAL_WEIGHT * qual_score, 1)

    # 6) 플레이스타일 추론 + 근거/개선 + 코칭/로드맵
    style_scores = infer_playstyles(df, role)
    primary_style = max(style_scores, key=style_scores.get) if style_scores else None
    style_reasons = explain_playstyle(df, primary_style) if primary_style else []
    style_improve = improvement_points(df, primary_style, role) if primary_style else []
    coaching_tips = style_coaching_advice(df, primary_style, role, top_n=6) if primary_style else []
    growth_roadmap = style_growth_roadmap(primary_style, role, meta.get("age_years"), df) if primary_style else []

    # 7) 레이더: 스타일 키 우선(없으면 역할 기본)
    radar_keys = choose_radar_keys(role, primary_style)
    outroot = outroot or f"viz_{player_id}"
    _ = _ensure_outdir(outroot)
    viz_radar(df, radar_keys[:6], f"{primary_style or role} — Radar", str(Path(outroot) / "radar.png"))

    # 8) Playstyle 카드(Top-3/근거/개선 요약)
    style_block = ""
    if primary_style:
        topn = sorted(style_scores.items(), key=lambda x: x[1], reverse=True)[:3]
        topn_txt = ", ".join([f"{n}({round(s,1)})" for n, s in topn])
        reasons_txt = " · ".join(style_reasons) if style_reasons else "데이터 근거 부족"
        improve_txt = " · ".join(style_improve) if style_improve else "핵심 보완 포인트 없음(상대적 우수)"
        style_block = f"""
<div class="card"><h2>Playstyle Engine</h2>
  <div><b>Primary</b>: {primary_style} ({round(style_scores[primary_style],1)})</div>
  <div>Top-3: {topn_txt}</div>
  <div>근거: {reasons_txt}</div>
  <div>개선: {improve_txt}</div>
</div>
""".strip()

    # 9) 역할기반 강/약점 → 그래프 & 그룹점수 바 & HTML 뼈대
    rw = role_aware_strengths_weaknesses(df, role)
    viz_info = viz_make_quick_report(
        meta | {"player_id": player_id, "role": role},
        rw, pot, pot_details, df,
        qual_score=qual_score, qual_signals=qual_signals, wiki_url=wiki_url,
        style_block=style_block, outroot=outroot
    )

    # 10) Narrative(현재/잠재)
    current_txt = ai_assess_current(base_pack, role)
    potential_txt = ai_assess_potential_strict(pot, pot_details, role)

    # 11) report.html 후처리: 코칭/로드맵 섹션 삽입
    html_path_out = Path(viz_info["dir"]) / "report.html"
    if html_path_out.exists():
        html = html_path_out.read_text(encoding="utf-8")

        coaching_html = ""
        if primary_style and coaching_tips:
            coaching_html = "<div class='card'><h2>Coaching — Style-specific</h2><ul>" + \
                "".join([f"<li>{_html.escape(t)}</li>" for t in coaching_tips]) + \
                "</ul></div>"

        roadmap_html = ""
        if primary_style and growth_roadmap:
            roadmap_html = "<div class='card'><h2>Growth Roadmap — Phased</h2><ul>" + \
                "".join([f"<li>{_html.escape(t)}</li>" for t in growth_roadmap]) + \
                "</ul></div>"

        narrative_html = f"""
<div class="card"><h2>Narrative — Current</h2>
  <pre style="white-space:pre-wrap">{current_txt}</pre>
</div>
<div class="card"><h2>Narrative — Potential</h2>
  <pre style="white-space:pre-wrap">{potential_txt}</pre>
</div>
{coaching_html}
{roadmap_html}
"""
        html = html.replace("</body></html>", narrative_html + "\n</body></html>")
        html_path_out.write_text(html, encoding="utf-8")

    # 12) 리포트 열기(가능 환경에서만)
    try:
        webbrowser.open(str(html_path_out))
    except Exception:
        pass

    # 13) 결과 패키징
    return {
        "player_id": player_id,
        "source_url": src,
        "role": role,
        "meta": meta,
        "style": {
            "primary": primary_style,
            "scores": style_scores,
            "reasons": style_reasons,
            "improvements": style_improve,
            "coaching": coaching_tips,
            "roadmap": growth_roadmap,
            "radar_keys": radar_keys,
        },
        "scores": {
            "quant_current": quant_current,
            "quant_potential": quant_potential,
            "qualitative": {
                "score": qual_score,
                "signals": qual_signals,
                "wiki_url": wiki_url,
                "wiki_endpoint": wiki_ep,
                "wiki_chars": len(wiki_text or "")
            },
            "final": {
                "current": final_current,
                "potential": final_potential,
                "weights": {"quant": QUANT_WEIGHT, "qual": QUAL_WEIGHT}
            }
        },
        "quant_detail": {
            "current": base_pack,
            "potential": {"score": pot, "details": pot_details}
        },
        "viz": viz_info,
        "narratives": {"current": current_txt, "potential": potential_txt},
        "report_path": str(html_path_out)
    }

def main():
    """
    - 선수 ID/로컬 HTML 입력 → 분석 실행
    - 결과 파일 저장 및 report.html 오픈
    - 원하면 JSON/TXT 저장
    """
    pid = input("분석할 FBref 선수 ID를 입력하세요 (예: 82ec26c1): ").strip()
    local_path = input("로컬 HTML 경로가 있으면 입력(엔터=실시간 접속): ").strip()
    role_override = input("역할 강제 입력(override, 예: FW/WM/AM/CM/DM/FB/CB/GK, 엔터=자동): ").strip().upper() or None
    if role_override and role_override not in WEIGHTS_BY_ROLE:
        print("[경고] 알 수 없는 역할입니다. 자동 매핑을 사용합니다.")
        role_override = None

    try:
        out = analyze_player(pid, html_path=(local_path or None), role_override=role_override, headless=True)
    except Exception as e:
        print(f"\n[중단] 분석 실패: {e}")
        return

    meta = out.get("meta", {})
    report_path = out.get("report_path")
    print("\n=== 완료 (파일 생성 및 팝업 오픈) ===")
    print(f"FINAL (current): {out['scores']['final']['current']}")
    print(f"Potential (v3) : {out['scores']['final']['potential']}")
    print(f"Primary Role   : {out.get('role')}")
    if out["style"]["primary"]:
        print(f"Primary Style  : {out['style']['primary']}")
    if report_path:
        print(f"Report: {report_path}")

    # 추가 저장
    save = input("\nJSON/TXT로 저장할까요? (y/N): ").strip().lower()
    if save == "y":
        base = Path(f"scout_365d_{pid}")
        # JSON
        with open(base.with_suffix(".json"), "w", encoding="utf-8") as f:
            json.dump({
                "meta": {"player_id": pid, "source_url": out.get("source_url")} | meta,
                "style": out["style"],
                "scores": out["scores"],
                "quant_detail": out["quant_detail"],
                "narratives": out["narratives"]
            }, f, ensure_ascii=False, indent=2)

        # TXT
        with open(base.with_name(base.stem + "_report.txt"), "w", encoding="utf-8") as rf:
            rf.write("=== FBref 365d Scout Score (Integrated) ===\n")
            rf.write(f"Player ID : {pid}\n")
            rf.write(f"Name      : {meta.get('player_name')}\n")
            rf.write(f"Role      : {out.get('role')}\n")
            rf.write(f"Minutes   : {meta.get('minutes_365d')}\n")
            rf.write(f"Age       : {meta.get('age_years')}\n")
            if out["style"]["primary"]:
                rf.write(f"Style     : {out['style']['primary']}\n")
            rf.write("\n[Scores]\n")
            rf.write(f" Current (quant)   : {out['scores']['quant_current']}\n")
            rf.write(f" Potential (quant) : {out['scores']['quant_potential']}\n")
            rf.write(f" Qualitative       : {out['scores']['qualitative']['score']}\n")
            rf.write(f" FINAL current     : {out['scores']['final']['current']}\n")
            rf.write(f" FINAL potential   : {out['scores']['final']['potential']}\n\n")
            rf.write("[Narrative — Current]\n")
            rf.write(out["narratives"]["current"] + "\n\n")
            rf.write("[Narrative — Potential]\n")
            rf.write(out["narratives"]["potential"] + "\n")

        print(f"Saved: {base.with_suffix('.json')} / {base.with_name(base.stem + '_report.txt')}")

if __name__ == "__main__":
    main()
