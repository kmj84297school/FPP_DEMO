# app.py (FINAL)
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from functools import lru_cache
import time
from pathlib import Path
import traceback
from player_lookup import get_player_id, init_driver
import re # 필요 시


# 기존 분석 함수 (변경 금지)
from PlayerPotentialAI_FBREF_Version import analyze_player

app = FastAPI(title="Scout Visual — Player Potential AI (FastAPI)")

# 정적/템플릿
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/viz", StaticFiles(directory="viz_out"), name="viz")
templates = Jinja2Templates(directory="templates")
templates.env.globals.update(min=min, max=max)

# ---------- 유틸 ----------
def _pick(d, *paths, default=None):
    """중첩 dict에서 첫 번째로 존재하는 값을 골라줌. ('a.b.c' 형식)"""
    for path in paths:
        cur = d
        ok = True
        for key in path.split("."):
            if isinstance(cur, dict) and (key in cur):
                cur = cur[key]
            else:
                ok = False
                break
        if ok and cur is not None:
            return cur
    return default

def _ival(x):
    try:
        return int(round(float(x)))
    except Exception:
        return 0

def _safe_report_link(report_path: str | None) -> str | None:
    """로컬 경로를 /viz/ 상대 경로로 변환 (report.html 접근 가능)"""
    if not report_path:
        return None
    try:
        p = Path(report_path)
        parts_lower = [s.lower() for s in p.parts]
        if "viz_out" in parts_lower:
            idx = parts_lower.index("viz_out")
            rel_parts = p.parts[idx + 1:]
            rel = "/".join(rel_parts)
            return f"/viz/{rel}"
        # report.html 바로 가기 보정
        if p.name.lower() == "report.html":
            return f"/viz/{p.parent.name}/report.html"
    except Exception:
        pass
    return None

def _extract_viz_paths(viz_obj: dict) -> dict:
    """
    viz 구조가 다양해도 .png/.jpg 경로를 최대한 추출해 dict로 반환.
    허용 패턴:
      - viz['paths'][k] = "xxx.png"
      - viz['charts'][k] = "xxx.png"
      - viz[k] = "xxx.png"
      - viz[...] 중첩 dict 내부의 "xxx.png"
    """
    paths = {}
    if not isinstance(viz_obj, dict):
        return paths

    def _maybe_add(k, v):
        if isinstance(v, str) and (v.lower().endswith(".png") or v.lower().endswith(".jpg")):
            paths[k] = v

    # 1) 자주 쓰는 컨테이너 키 우선
    for key in ("paths", "charts", "figures", "images"):
        if key in viz_obj and isinstance(viz_obj[key], dict):
            for k, v in viz_obj[key].items():
                _maybe_add(k, v)

    # 2) 최상위 평탄화
    for k, v in viz_obj.items():
        _maybe_add(k, v)

    # 3) 얕은 중첩 탐색(1단계)
    for k, v in viz_obj.items():
        if isinstance(v, dict):
            for k2, v2 in v.items():
                _maybe_add(k2, v2)

    return paths

# ---------- 캐시 ----------
@lru_cache(maxsize=128)
def cached_player_result(player_id: str):
    start = time.time()
    result = analyze_player(player_id)  # 내부에서 리포트/이미지 생성
    elapsed = round(time.time() - start, 2)
    result["_elapsed"] = elapsed
    result["_cached"] = False
    return result

# ---------- 라우트 ----------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})

@app.post("/analyze", response_class=HTMLResponse)
async def analyze(request: Request, player_id_or_name: str = Form(...)):
    t0 = time.time()
    player_id = player_id_or_name.strip()

    # ✅ 이제 정상적으로 player_id 변수 사용 가능
    if not re.fullmatch(r"[0-9a-f]{8}", player_id, re.IGNORECASE):
        driver = init_driver()
        resolved_id = get_player_id(player_id, driver)
        driver.quit()
        if not resolved_id:
            return templates.TemplateResponse(request, "dashboard.html", {
                "result": {},
                "error": f"선수 '{player_id}'을(를) 찾을 수 없습니다.",
                "trace": ""
            })
        player_id = resolved_id

    # 1) 캐시 우선
    try:
        result = cached_player_result(player_id)
        result = dict(result)
        result["_cached"] = True
        result["_elapsed"] = round(time.time() - t0, 2)
    except Exception:
        # 2) 캐시 실패 → 실시간
        try:
            result = analyze_player(player_id)
            result["_cached"] = False
            result["_elapsed"] = round(time.time() - t0, 2)
        except Exception as e2:
            payload = {
                "player_id": player_id,
                "role": None, "meta": {}, "style": {},
                "scores": {}, "quant_detail": {}, "viz": {},
                "report_link": None, "_cached": False,
                "_elapsed": round(time.time() - t0, 2),
            }
            return templates.TemplateResponse(
                request, "dashboard.html",
                {"result": payload,
                 "error": str(e2), "trace": traceback.format_exc()},
                status_code=200
            )

    # 3) report_link 계산
    report_link = _safe_report_link(result.get("report_path"))

    # 4) Scores/Groups 정규화
    overall = _pick(result,
                    "scores.overall",
                    "scores.final.current",
                    "scores.quant_current",
                    "overall",
                    default=None)

    potential_total = _pick(result,
                            "scores.potential_total",
                            "scores.final.potential",
                            "scores.quant_potential",
                            "final_potential",
                            default=None)

    scores = dict(result.get("scores") or {})
    if overall is not None:
        scores["overall"] = overall
    if potential_total is not None:
        scores["potential_total"] = potential_total

    # 5) PRD/PRG/CHA/STA 정규화 (quant_detail → scores.groups → fallback 순)
    qd_src = dict(result.get("quant_detail") or {})
    groups_from_scores = (scores.get("groups") or {})
    fallback_groups = dict(result.get("groups") or {})

    # 먼저 quant_detail의 potential.details(g_*) 형태 지원
    pot = ((qd_src.get("potential") or {}).get("details") or {})
    g_prd = pot.get("g_prod")
    g_prg = pot.get("g_progress")
    g_cha = pot.get("g_chance")
    g_sta = pot.get("g_stability")

    qd_flat = {
        "PRD": _ival(_pick({"a": qd_src, "b": groups_from_scores, "c": fallback_groups},
                           "a.PRD", "b.PRD", "c.PRD",
                           default=g_prd)),
        "PRG": _ival(_pick({"a": qd_src, "b": groups_from_scores, "c": fallback_groups},
                           "a.PRG", "b.PRG", "c.PRG",
                           default=g_prg)),
        "CHA": _ival(_pick({"a": qd_src, "b": groups_from_scores, "c": fallback_groups},
                           "a.CHA", "b.CHA", "c.CHA",
                           default=g_cha)),
        "STA": _ival(_pick({"a": qd_src, "b": groups_from_scores, "c": fallback_groups},
                           "a.STA", "b.STA", "c.STA",
                           default=g_sta)),
    }

    # 6) viz 경로 자동 추출
    viz_raw = result.get("viz", {}) or {}
    viz_paths = _extract_viz_paths(viz_raw)

    # --- 디버그 로그 (콘솔) ---
    print("DEBUG: result.viz =", viz_raw)
    print("DEBUG: extracted viz paths =", viz_paths)

    viz_safe = {"paths": viz_paths}

    # 7) 템플릿 페이로드
    payload = {
        "player_id": result.get("player_id"),
        "role": result.get("role"),
        "meta": result.get("meta", {}),
        "style": result.get("style", {}),
        "scores": scores,
        "quant_detail": qd_flat,
        "viz": viz_safe,
        "report_link": report_link,
        "_cached": result.get("_cached", False),
        "_elapsed": result.get("_elapsed", 0.0),
    }

    return templates.TemplateResponse(request, "dashboard.html",
                                      {"result": payload})
