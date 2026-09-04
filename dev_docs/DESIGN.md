# FPP 디자인 시스템 "Orbit" (2026-09)

## 의도
"전문가용 표"에서 **대중이 즐기며 쓰는 스카우팅 앱**으로. 참고: EA FC26 매니저 모드(검은 유리·네온 그린·OVR/POT 카드),
Football Manager(스카우트 리포트 스탬프), Sofascore/FotMob(원형 평점·카드형 목록), Transfermarkt(▲/▼ 변동), FBref(퍼센타일 막대).
우리만의 것은 **궤도(Orbit)** 모티프 — 현재와 2~3년 후를 한 궤도 위의 두 점으로 그린다. 로고·카드 게이지·상세 헤더·배경이 같은 언어를 쓴다.

## 로고 — 별·궤도
- 중심의 4각 별 = 잠재력. 기울어진 타원 궤도 2개 = F와 P의 획을 암시(하나는 닫힌 궤도=현재, 하나는 열린 궤도=미래).
  궤도 위 두 점: 초록(현재) · 보라(2~3년 후). 선은 그린→바이올렛 그라데이션.
- 파일: `docs/assets/logo.svg`(단독), 인라인 `<symbol id="fpp-logo">`(motion.js가 body 첫머리에 삽입), 파비콘은 data URI(각 html `<link rel="icon">`).
- 동작: 랜딩 첫 방문(세션당 1회) 인트로 — 궤도 회전 + 별 스케일업 → 0.5초 페이드아웃. 헤더 로고는 호버 시 느리게 회전. 페이지 전환 오버레이에서도 회전.
- 구현 주의: `<use>` 그림자 트리에는 조상 선택자가 닿지 않는다. 심볼 내부 클래스(`.fpp-orbit/.fpp-og/.fpp-star/.fpp-sat`)는 단독 선택자로 스타일하고,
  회전·팝 애니메이션은 호스트가 정하는 CSS 변수(`--og-a`, `--og-b`, `--star-anim`)로 넘긴다.

## 토큰 (`docs/assets/style.css :root`)
| 역할 | 값 |
|---|---|
| 배경 | `#070911` + 좌상 보라(`rgba(91,33,182,.45)`)·우하 청록(`rgba(15,118,110,.35)`) 라디얼 + 궤도 라인 SVG(opacity .11) + 빛 점 10개 |
| 유리 패널 | `rgba(17,21,30,.72)` + `backdrop-filter: blur(14px)` + 1px `rgba(255,255,255,.08)` 테두리 + 상단 하이라이트 |
| 액센트 | 네온 그린 `#19ffa7`(현재·긍정), 골드 `#ffd700`(예측·2~3년 후), 바이올렛 `#a78bfa`(궤도·보조) |
| 등급 색 | elite/great/good/ok/mid/bad 6단계 — 이전과 동일, 항상 등급 텍스트를 병기 |
| 모션 | `--ease-out: cubic-bezier(.22,1,.36,1)`, 220/420/900ms. `prefers-reduced-motion`이면 전부 0ms·정적, 인트로 표시 안 함 |

## 컴포넌트
- **선수 카드**(`playerCardHtml`, common.js): 상단 좌 `현재`(초록) / 우 `2~3년 후 상한`(금색, 툴팁 "80% 신뢰구간 상단 — 최댓값이 아니라 상위 10% 시나리오"),
  등급 텍스트, 아바타, 국가 코드 칩(이미지 없음), 포지션·역할·나이·클럽, 궤도 게이지, 모델 태그. 호버 3D 틸트 + 광택(마우스 위치 추적), 진입 스태거.
  카드 상단 띠 색: 성장기=그린, 성숙기=골드, 예측 없음=바이올렛.
- **궤도 게이지**(`orbitGaugeHtml`): 0~100 궤도 위 현재(초록 점)→상한(금색 별) 호.
- **링 게이지**(`ringHtml`): 상세 헤더의 두 원형 게이지, 카운트업 + 원호 채우기.
- **스탬프**(`.stamp`): 성장기/성숙기 모델, 검증 범위 밖, 비교 신뢰도 낮음 — FM식 리포트 스탬프(살짝 기울임).
- **섹션 탭**(`.section-tabs`): 상세 페이지 sticky 탭, IntersectionObserver 스크롤 스파이, 해시 permalink.
- **모션 유틸**(`docs/assets/motion.js`): `observe`(리빌, threshold 0 + rootMargin -8% — 키 큰 패널도 일부만 보이면 리빌), `countUp`, `tilt`, `rings`, `spy`,
  페이지 전환 오버레이(내부 .html 링크 클릭 → 230ms), 배경 레이어, 인트로. 모바일에서는 배경 애니메이션·틸트 끔.

## 정직성 규칙 (디자인이 숫자를 과장하지 않도록)
- 카드의 두 숫자는 "현재" / "2~3년 후 상한"으로만 부른다. OVR/POT·"잠재력 최대치" 표현 금지. 상한 툴팁에 80% 구간 상단임을 명시.
- 검증 범위 밖·비교 신뢰도 낮음은 숨기지 않고 스탬프로 헤더에 노출. 경고문 수치는 meta.json 실측값.
- 색만으로 정보를 전달하지 않는다(등급 텍스트, ▲/▼, aria-label).

## 측정 (2026-09-04, Chromium)
- 첫 로드(index.html + css + common/motion/app.js + index.json + meta.json): **266 KB** (목표 350 KB 이하). Chart.js(200 KB)는 상세·비교에서만.
  index.json은 nation 열 추가로 190 → 201 KB.
- 375px: index/player/compare `scrollWidth` 375(가로 스크롤 0). 콘솔 스크립트 오류 0(FBref 헤드샷 핫링크 차단 로그만).
- reduced-motion 에뮬레이션: `html.no-motion` 부여, 레이아웃 동일, 인트로 없음.
- 스크린샷: `dev_docs/phase3_shots/redesign/` (intro, index 카드/표, player, compare, card_hover, reduced motion).
