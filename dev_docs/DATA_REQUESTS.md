# DATA_REQUESTS — 코드로는 못 풀고 데이터가 있어야 풀리는 문제 (B 항목) 명세

> 각 항목: 왜 필요한가 → 정확히 어떤 파일(컬럼·키·기간)이 필요한가 → 어디서 구할 수 있는가(이 환경에서
> 조사한 범위) → 데이터가 오면 무엇을 바로 돌릴 수 있는가. 조인 키는 항상 **fbref_id 또는 (이름, 생년)**
> 이상이며 이름 단독 조인은 하지 않는다(동명이인 33명+ 확인, 3단계에서 6쌍 추가 확인).

이 환경의 접속 제약: Kaggle·FBref·Transfermarkt·GitHub API는 차단, `raw.githubusercontent.com`·PyPI는 됨.
그래서 아래 "조사"는 GitHub raw로 실제로 내려받아 확인한 것과, 알고 있는 공개 소스의 명세로 나뉜다.

## 이번에 실제로 확보한 것 (요청 아님, 보고)

- **FBref ↔ Transfermarkt 선수 매핑** (`data/fbref_tm_mapping_subset.csv`, 5,240행)
  출처: worldfootballR_data `raw-data/fbref-tm-player-mapping/output/fbref_to_tm_mapping.csv` (공개, 15,440행).
  우리 데이터의 실제 fbref_id 5,256개 중 **5,240개(99.7%)**, 2025 스냅샷 실 id 1,518명은 **전원** TM id를 얻었다.
  → B2(시장가치)의 조인 키가 이미 준비됐다. 합성 id(n24*/n25*)는 매핑에 없다(B1과 연동).
- worldfootballR_data의 `fb_big5_advanced_season_stats/*.rds`는 **2023(13경기 부분 시즌)에서 멈춰 있고 저장소가
  아카이브(유지 종료)** 상태다 — 2024·2025 시즌은 이 경로로 못 채운다(확인함).

## B1. 실제 fbref_id — 합성 id 1,633명(2024 1,078 / 2025 981, 겹침 포함)의 근본 해결

- **왜**: 사진 없음, 2023 이전 이력과 단절(Δ 피처 결측), 유사 선수·외부 라벨 조인 불가.
  3단계 A7의 데이터 내 복구는 **1건**에 그쳤다(나머지는 데이터 어디에도 같은 이름이 없는 진짜 신규 선수).
- **필요한 파일**: 2023-24·2024-25 시즌 빅5 선수 표준 스탯 테이블에 **FBref 선수 URL(또는 8자 hex id)**,
  `Born`, `Nation`, `Squad`가 함께 있는 CSV. 최소 컬럼: `player_url|fbref_id, Player, Born, Nation, Squad, Comp, Season_End_Year`.
- **조인**: (fbref_id) 직접. 합성 id 행은 (정규화 이름, Born, Nation) 3중 일치 + 후보 유일할 때만 치환하고 건마다 로그.
- **어디서**: ① worldfootballR을 소유자 PC에서 직접 실행(`fb_big5_advanced_season_stats(season_end_year=2024:2025, stat_type="standard", team_or_player="player")` — 결과에 `Url` 컬럼 포함; FBref 속도 제한이 있어 한 번에 한 시즌씩) ② Kaggle에서 "fbref" 검색 시 `player_url`/`id` 컬럼이 있는 데이터셋(2024-25 hubertsidorowicz 판은 URL이 없어 이번에 합성 id가 생겼다) ③ FBref 페이지의 "Share & Export → CSV"는 URL을 안 준다 — HTML 표에서 링크 추출이 필요.
- **오면 돌릴 것**: `build/14_recover_ids.py`를 3중 키 모드로 확장(30분 작업), 이후 01→06→07→02~05 전체 재빌드.

## B2. 외부 검증 라벨 — "능력점수로 능력점수를 예측한다"는 순환성 비판에 대한 답 (가장 중요)

- **왜**: 라벨(미래 능력점수)과 피처(현재 능력점수)가 같은 산식이다. 점수가 "실제 무언가"와 상관이 있어야 한다.
- **필요한 파일 (1순위: Transfermarkt 시장가치 이력)**
  `tm_id, date(YYYY-MM-DD), market_value_eur` — 선수별 시점별 시장가치. 기간 2017-06 ~ 2026-06.
  대상: `data/fbref_tm_mapping_subset.csv`의 tm_id 5,235개(전부가 아니어도 됨 — 조인율을 같이 보고한다).
  **2순위**: 이적료(`tm_id, date, fee_eur, from_club, to_club`), 국가대표 출전 수(`tm_id, season, caps`),
  개인 수상(발롱도르/리그 올해의 팀 등, `fbref_id|tm_id, season, award`).
- **어디서**: ① worldfootballR `tm_player_market_values(country_name, start_year)` 소유자 PC 실행 (리그·시즌별, 선수 URL 포함 → tm_id 추출) ② Kaggle "transfermarkt" 데이터셋(dcaribou/transfermarkt-datasets: `player_valuations.csv`에 `player_id, date, market_value_in_eur` — 이 명세와 정확히 맞고 tm_id가 같은 체계다) ③ football-data 류 CSV.
- **오면 돌릴 것**: `build/exp/b2_external_validation.py --mv <파일>` — 이미 작성돼 있다.
  V1 시즌×포지션 내 능력점수 vs log(시장가치) Spearman(나이 통제 포함), V2 폴드 밖 예측 Δ vs 2~3년 후 시장가치 변화율,
  V3 잔존확률 vs 미래 시장가치 존재 AUC. 조인율·표본수를 함께 기록하고, 낮게 나와도 그대로 보고한다.

## B3. 부상 기록 — "가용성"을 로테이션과 부상으로 분리

- **왜**: 현재 정성 시그널의 가용성은 출전시간 점유율(MinPct) 대리변수라 "안 뛴 이유"를 모른다.
- **필요한 파일**: `tm_id|fbref_id, injury, from_date, to_date, games_missed` (선수별 부상 에피소드). 기간 2017~2026.
- **어디서**: ① worldfootballR `tm_player_injury_history(player_url)` — 선수 URL 단위라 5천 명은 시간이 걸린다(우선순위: 2025 스냅샷 1,692명) ② Kaggle transfermarkt 계열 데이터셋 일부에 injuries 테이블이 있음(버전 확인 필요).
- **오면 돌릴 것**: `build/11_qualitative.py`의 availability에 `days_injured_season`, `n_injuries_3y`를 추가하고, A4 잔존 피처에 부상일수를 넣어 GroupKFold로 AUC 전후 비교(채택 규칙 동일).

## B4. 빅5 밖 리그 — "이탈"을 "하락"과 "수평 이동"으로 분리

- **왜**: 잔존 라벨은 "빅5 900분+ 시즌이 있는가"뿐이라, 챔피언십·에레디비시·포르투갈 1부로 가서 잘 뛰는 선수가 "이탈"로 묶인다.
  A4 피처(리그1 one-hot이 U23 잔존에 7위)가 이 문제의 존재를 데이터로 보여줬다.
- **필요한 파일**: 잉글랜드 2부·네덜란드·포르투갈·튀르키예·벨기에·MLS·사우디 1부의 선수-시즌 표준 스탯(`fbref_id|player_url, Season_End_Year, Squad, Comp, Min_Playing, Born, Nation`). 고급지표는 없어도 된다(라벨 분리용).
- **어디서**: worldfootballR `fb_league_stats`/`fb_player_season_stats`(FBref는 위 리그 대부분에 표준 스탯 제공), Kaggle "fbref championship/eredivisie" 데이터셋.
- **오면 돌릴 것**: `build/lib/cohorts.py`의 survived를 3값(빅5 잔존 / 타 리그 활동 / 소멸)으로 확장 → 다중 분류 또는 "빅5 이탈 중 수평 이동 비율" 보고. 라벨 정의 변경이므로 §4 핵심 설계 5번에 해당 — 착수 전 소유자 승인.

## B5. 2025-26 고급지표

- **왜**: 반입된 2025-26 파일은 102컬럼(표준 스탯만)이라 패스·포제션·수비·GCA 블록이 없어 능력점수 계산 불가.
- **필요한 파일**: 2025-26 빅5 선수별 `passing, possession, defense, gca, misc, shooting` 8종 테이블(2023-24 반입 때와 같은 팀/카테고리 폴더 구조면 `build/13_import_2024.py`를 그대로 재사용).
- **어디서**: FBref는 시즌 진행 중에도 고급지표를 제공한다 — 소유자 PC의 worldfootballR(`stat_type = "passing"` 등) 또는 시즌 종료 후 Kaggle에 올라오는 판. 주의: 시즌 중 파일은 부분 시즌이라 `02_eligibility.py`의 비례 임계가 자동 적용된다.
- **오면 돌릴 것**: `build/13_import_2024.py`의 TARGET_YEAR=2026 복제본 → config.TARGET_YEAR=2026 → 전체 재빌드. 코호트 2023이 t+3=2026을 얻어 학습 라벨이 늘어난다.

## B6. GK 모델

- **현황**: `data/fpp_features_GK_2018_2023.csv` 1,166행(2018~2023)은 있고, 2024·2025 반입 시 GK는 버렸다(카테고리 파일에 GK 전용 지표가 없어서).
- **필요한 파일**: 2024·2025 시즌 `keepers`·`keepersadv` 테이블(`PSxG, PSxG+/-, /90, Save%, Cmp% (long), AvgDist (sweeper)` 등) + 2018~2023과 같은 컬럼 체계.
- **설계 상 주의**: 필드플레이어 산식(5그룹·11스타일)을 그대로 쓸 수 없다. GK는 PSxG−GA(슛스토핑), 스위핑, 배급 3축 정도의 별도 점수와 별도 코호트(GK는 24세 이후에도 성장·롱런)가 필요하다 — §D대로 착수 전 소유자와 상의.

## C1. 상업적 사용 (확인만)

FBref(Stats Perform/Opta 유래) 데이터의 상업 서비스 직접 사용은 불가. 코드로 풀리는 문제가 아니며, BYOD(고객 데이터 반입형) 또는 정식 라이선스 확보가 전제다(인계문서 §7, Stats Perform 문의 이력 2025.10). 3단계에서 바뀐 것 없음.
