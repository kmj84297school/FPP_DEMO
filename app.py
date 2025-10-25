# app.py
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from functools import lru_cache
import time
from pathlib import Path

# 너의 기존 분석 함수 그대로 재사용
from PlayerPotentialAI_FBREF_Version import analyze_player  # 변경 금지!  :contentReference[oaicite:2]{index=2}

app = FastAPI(title="Scout Visual — Player Potential AI (FastAPI)")

# 정적/템플릿 연결
app.mount("/static", StaticFiles(directory="static"), name="static")
# 생성물(viz_out)도 정적으로 서비스 (레이더/막대/리포트 html 접근)
app.mount("/viz", StaticFiles(directory="viz_out"), name="viz")
templates = Jinja2Templates(directory="templates")

# ===== 캐시(온라인 증명용): 동일 선수 재요청 시 속도 차이 시각화 =====
@lru_cache(maxsize=128)
def cached_player_result(player_id: str):
    # 최초 계산(캐시 생성)
    start = time.time()
    result = analyze_player(player_id)   # 내부에서 리포트/이미지 생성 및 경로 반환  :contentReference[oaicite:3]{index=3}
    elapsed = round(time.time() - start, 2)
    # 화면에서 배지로 보여줄 메타 정보 추가
    result["_elapsed"] = elapsed
    result["_cached"] = False
    return result

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/analyze", response_class=HTMLResponse)
async def analyze(request: Request, player_id: str = Form(...)):
    t0 = time.time()
    # 1) 캐시에 있으면 즉시 반환 (lru_cache)
    try:
        result = cached_player_result(player_id)
        # lru_cache는 객체를 그대로 주므로, 표시용 플래그만 바꿔주자
        result = dict(result)
        result["_cached"] = True
        result["_elapsed"] = round(time.time() - t0, 2)
    except Exception:
        # 2) 캐시에 없거나 예외 발생 시 실시간 분석
        result = analyze_player(player_id)
        result["_cached"] = False
        result["_elapsed"] = round(time.time() - t0, 2)

    # 리포트 파일이 있으면 /viz 경로로 접근 가능하게 변환
    report_link = None
    rp = result.get("report_path")
    if rp:
        # viz_out/ 이하 상대경로로 바꿔서 /viz/<상대경로> 링크 제공
        p = Path(rp)
        # viz_out/xxx/report.html → /viz/xxx/report.html
        if "viz_out" in rp.replace("\\", "/"):
            rel = "/".join(p.parts[p.parts.index("viz_out")+1:])
            report_link = f"/viz/{rel}"
        else:
            # 혹시 다른 경로라면 파일명만 표시
            report_link = f"/viz/{p.name}" if p.exists() else None

    # 템플릿으로 전달할 출력 정리
    payload = {
        "player_id": result.get("player_id"),
        "role": result.get("role"),
        "meta": result.get("meta", {}),
        "style": result.get("style", {}),
        "scores": result.get("scores", {}),
        "quant_detail": result.get("quant_detail", {}),
        "viz": result.get("viz", {}),
        "report_link": report_link,
        "_cached": result.get("_cached", False),
        "_elapsed": result.get("_elapsed", 0.0),
    }
    return templates.TemplateResponse("dashboard.html", {"request": request, "result": payload})
