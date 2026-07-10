# FPP 상세 기술 인계 문서 (HANDOVER_DETAIL)

> CLAUDE.md의 부속 문서. 코드·수식·설계의 전체 디테일을 담는다.
> 모든 표·목록은 실제 산출물 파일에서 자동 추출한 값이다 (수기 전사 아님).

## 1. 능력점수 산식 전체 명세 (scoring_v1.py)

### 1-1. 파이프라인
```
per90 변환 (누적스탯 ÷ 출전90분수)
→ 분위수: 시즌×포지션(FW/MF/DF) 풀 내, 600분+ 선수 기준 searchsorted 백분위
  (풀 20명 미만이면 전체로 완화, 음의 지표는 100-p로 반전)
→ 5그룹 점수 = 그룹 내 지표 분위 평균
→ 포지션 렌즈 점수 = Σ(그룹×포지션 가중치)
→ 스타일 렌즈: shape 피처 z점수 → argmax 스타일 배정 → 스타일 가중치로 점수
→ 최종 능력 = (포지션 점수 + 스타일 점수) / 2
```

### 1-2. 지표 그룹 구성 (방향: MisDis·Err만 음수, 나머지 양수)
```json
{
 "prod": [
  "npxG",
  "np_G",
  "Sh",
  "SoT",
  "npxG_Sh",
  "xAG",
  "Ast"
 ],
 "progress": [
  "PrgPass",
  "PrgDistP",
  "PrgCarry",
  "PrgDistC",
  "TakeOn",
  "PrgRec",
  "F3Pass",
  "AttPenT"
 ],
 "chance": [
  "SCA",
  "GCA",
  "KP",
  "PPA"
 ],
 "stability": [
  "PassPct",
  "Err",
  "MisDis"
 ],
 "defense": [
  "TklInt",
  "TklPct",
  "Blocks",
  "Clr",
  "Recov",
  "AerWon",
  "AerPct"
 ]
}
```
컬럼 매핑은 scoring_v1.py의 PER90/RATE 딕셔너리가 원본. 주요 매핑:
npxG→std_npxG_Expected, SCA→gca_SCA_SCA, PrgCarry→pos_Prog_Carries,
TklInt→def_Tkl_plus_Int, AerWon→msc_Won_Aerial, PassPct→pas_Cmp_percent_Total,
MisDis→(pos_Mis_Carries+pos_Dis_Carries) 합성.

### 1-3. 포지션 렌즈 가중치
```json
{
 "FW": {
  "prod": 0.4,
  "chance": 0.2,
  "progress": 0.2,
  "stability": 0.1,
  "defense": 0.1
 },
 "MF": {
  "prod": 0.15,
  "chance": 0.2,
  "progress": 0.3,
  "stability": 0.2,
  "defense": 0.15
 },
 "DF": {
  "prod": 0.05,
  "chance": 0.1,
  "progress": 0.2,
  "stability": 0.25,
  "defense": 0.4
 }
}
```

### 1-4. 스타일 렌즈 (11개 스타일)
판별은 shape 피처(z점수 평균 argmax), 점수는 그룹 가중치. 가중치표:
```json
{
 "FW": {
  "박스 포처": {
   "prod": 0.55,
   "chance": 0.15,
   "progress": 0.1,
   "stability": 0.1,
   "defense": 0.1
  },
  "타겟맨": {
   "prod": 0.45,
   "chance": 0.1,
   "progress": 0.1,
   "stability": 0.1,
   "defense": 0.25
  },
  "돌파형 윙어": {
   "prod": 0.25,
   "chance": 0.25,
   "progress": 0.35,
   "stability": 0.05,
   "defense": 0.1
  },
  "연결형 공격수": {
   "prod": 0.25,
   "chance": 0.35,
   "progress": 0.2,
   "stability": 0.15,
   "defense": 0.05
  }
 },
 "MF": {
  "딥 플레이메이커": {
   "prod": 0.05,
   "chance": 0.25,
   "progress": 0.3,
   "stability": 0.25,
   "defense": 0.15
  },
  "볼 운반형": {
   "prod": 0.1,
   "chance": 0.2,
   "progress": 0.45,
   "stability": 0.15,
   "defense": 0.1
  },
  "수비형 파괴자": {
   "prod": 0.05,
   "chance": 0.05,
   "progress": 0.15,
   "stability": 0.25,
   "defense": 0.5
  },
  "공격형 MF": {
   "prod": 0.3,
   "chance": 0.3,
   "progress": 0.25,
   "stability": 0.1,
   "defense": 0.05
  }
 },
 "DF": {
  "빌드업 수비수": {
   "prod": 0.05,
   "chance": 0.1,
   "progress": 0.35,
   "stability": 0.3,
   "defense": 0.2
  },
  "스토퍼": {
   "prod": 0.03,
   "chance": 0.02,
   "progress": 0.1,
   "stability": 0.25,
   "defense": 0.6
  },
  "공격형 풀백": {
   "prod": 0.1,
   "chance": 0.25,
   "progress": 0.3,
   "stability": 0.15,
   "defense": 0.2
  }
 }
}
```
스타일별 판별 shape 피처 (scoring_v1.py STYLES 원본):
- FW 박스포처: attpen+shotrate / 타겟맨: aerial+attpen / 돌파형윙어: takeon+carry+cross / 연결형: kp+mid3
- MF 딥플레이메이커: long+def3+kp / 볼운반형: carry+takeon / 수비형파괴자: tklvol+def3+aerial / 공격형MF: att3+attpen+shotrate
- DF 빌드업: long+carry+passvol / 스토퍼: aerial+clrvol+defpen / 공격형풀백: att3+cross+takeon

### 1-5. shape 피처 공식 (T=총터치, AttP=패스시도, n90=출전90분수)
```
attpen=박스터치/T, att3=공격3분의1터치/T, mid3, def3, defpen (동일 패턴)
shotrate=슈팅/T, takeon=드리블시도/T, carry=운반전진거리/(운반+패스 전진거리)
cross=크로스/AttP, long=롱패스시도/AttP, kp=키패스/AttP
aerial=(공중볼승+패)/n90, tklvol=태클/n90, clrvol=클리어/n90, passvol=AttP/T
```
설계 의도: 스타일 판별에 '수준'이 아닌 '구성비'를 써서 점수 가중과의 순환성 차단.

## 2. 전처리 규칙 (fpp_features_clean_2018_2023.csv)

- 8개 카테고리(std/sho/pas/pos/gca/def/msc/pt 접두어)를 fbref_id+Season_End_Year로 병합
- 다중 팀 시즌(4.1%): 누적 합산, 비율·per90은 출전시간 가중평균. Squads 병기, n_clubs 기록
- 검증: Depaoli 2021 (3팀 191+1120+77=1388분) 정확 일치 확인
- 카테고리 간 중복 19개 컬럼 제거, snake_case 정규화
- pos_primary(첫 포지션), pos_multi 파생. GK 1,166행 분리
- 무결성 감사 결과: 키 중복 0, 나이-시즌 불일치 0, 신원분리 실질 0
  (Guilherme 1991년생 2명은 동일 시즌 타리그 동시 출전으로 동명이인 판정)
  동명이인 33명 존재 → **이름 조인 절대 금지, fbref_id만 사용**

## 3. 2023 시즌 사망 컬럼 (20개 — 제공사 StatsBomb→Opta 교체 영향)
```
pas_A_minus_xA
pos_Dis_Carries
pos_Targ_Receiving
pos_Rec_percent_Receiving
pos_nPl_Dribbles
pos_Megs_Dribbles
pos_Carries_Carries
def_Mid_3rd_Pressures
def_Succ_Pressures
def_percent_Pressures
def_Press_Pressures
def_Att_3rd_Pressures
def_Def_3rd_Pressures
def_ShSv_Blocks
pos_Mis_Carries
pos_TotDist_Carries
pos_PrgDist_Carries
pos_Prog_Carries
pos_Final_Third_Carries
pos_CPA_Carries
```
→ 2023을 피처 시즌으로 쓸 때 이 컬럼들은 결측. 라벨 시즌으로만 쓰면 영향 최소.

## 4. 라벨 생성 알고리즘 (v2)

```
코호트: Season_End_Year ∈ [2018,2020], age_y ≤ 23, std_Min_Playing ≥ 900, 필드플레이어
후보: 같은 fbref_id의 미래 시즌 중 (미래시즌-현재시즌) ∈ {2,3} 이고 900분+
survived = 후보 존재 여부 (1,323행 중 75.1%)
fut_ability_v2 = 후보 시즌들의 ability 평균 (40.5%는 2개 시즌 평균)
```
검열 없음: 2020 코호트의 t+3=2023까지 전부 관측 가능 창.

## 5. 학습 행렬 컬럼 전체 (51개)

```
age_y
std_Min_Playing
grp_prod
grp_progress
grp_chance
grp_stability
grp_defense
score_position
score_style
ability
style_confidence
npxG90
xAG90
SCA90
PrgPass90
PrgCarry90
TakeOn90
TklInt90
AttPenT90
KP90
PassPct
AerPct
MinPct
has_prev
d_ability
d_grp_prod
d_grp_progress
d_grp_chance
d_grp_stability
d_grp_defense
d_npxG90
d_xAG90
d_SCA90
d_PrgCarry90
d_PrgPass90
d_MinPct
d_std_Min_Playing
pos_DF
pos_FW
pos_MF
sty_공격형 MF
sty_공격형 풀백
sty_돌파형 윙어
sty_딥 플레이메이커
sty_박스 포처
sty_볼 운반형
sty_빌드업 수비수
sty_수비형 파괴자
sty_스토퍼
sty_연결형 공격수
sty_타겟맨
```
Δ피처: 전 시즌(600분+) 대비 변화량, 보유율 39.5% (2018 코호트는 2017 부재로 결측
— XGBoost 네이티브 결측 처리에 위임, has_prev 플래그 동반)

## 6. 모델 하이퍼파라미터 (v2 확정)

- 분류: XGBClassifier(n_estimators=300, max_depth=4, lr=0.05, subsample=0.8, colsample=0.8)
- 회귀: XGBRegressor(n_estimators=400, max_depth=4, lr=0.05, subsample=0.8, colsample=0.8)
- 부트스트랩용 경량: n_estimators=150~200, lr=0.07~0.08, tree_method=hist
- 튜닝 미수행 — 하이퍼파라미터 탐색은 백로그 (현 수치는 보수적 기본값)

## 7. 부트스트랩 알고리즘 (boot_ci.py)

```
B=60~150, 훈련 선수 목록에서 선수 단위 복원추출 → 해당 선수의 전 행 포함
각 부트스트랩 표본으로 회귀기 학습 → 대상 선수 예측 → 분포
sigma_model = 예측 분포 표준편차
sigma_residual = 폴드 밖 잔차 표준편차 = 7.49 (bootstrap_resid_sigma.npy)
구간 = mu ± z·sqrt(sigma_model² + 7.49²), z80=1.2816, z50=0.6745
```
검증 실측: 순수 구간 커버리지 29.3%(실패) → 결합 보정 82.0%/52.1%(성공).
서빙에서 앙상블 재학습이 무거우면: 전체 데이터로 B=60 앙상블 1회 구축 후
모델 60개 저장(개당 ~300KB) 또는 sigma_model 근사 상수화 검토.

## 8. 얼굴 타당성 검증 기록 (2022 시즌)

- FW TOP: Mbappé(84.6) → Nkunku → Vinicius → Benzema → Salah → Messi → Neymar
- MF TOP: De Bruyne(78.2) → Musiala(18세) → Barella / DF TOP: Schlotterbeck 등
- 스타일 배정 전수 일치: Haaland·Lewa·Benzema=박스포처, KDB=공격형MF,
  Kimmich=딥플레이메이커, Kanté=수비형파괴자, VVD=스토퍼, TAA·Cancelo=공격형풀백
- 진단된 편향 3종: ①박스포처 저평가(그룹 내 균등가중이 npxG 압도성 희석,
  Lewa 70.6) ②수비수 팀강도 편향(VVD 65.2 — 강팀 수비수는 수비기회 자체가 적음)
  ③포지션 간 분산 불일치(FW sd 13.8 vs DF 7.5 — 교차 비교 시 재표준화 필요)

## 9. 1학년 레거시 (legacy/ 폴더) 핵심 지식

- 최종본: PlayerPotentialAI_FBREF_Final_v3 계열 (ML 미사용 규칙 기반)
- 산식: 최종점수 = 정량 70% + 정성 30% (Current:Potential 70:30 아님 — 혼동 주의)
- Potential v3 그룹: prod/progress/chance/stability (현 v2 GROUPS의 원형)
- Strict 감점: 600분<9점, 1200분<7.5, 1800분<5, 2400분<3, 24세+저출전 +2, 상한 12
- 알려진 결함(2학년 한계분석 소재): 위키 부재 시 정성점수 기본 100(+30 기저 인플레),
  age_adjustment 계산되나 미반영(표시용), 정성 상한 120
- 실행 수정: 최신 starlette은 TemplateResponse(request, "템플릿", ctx) 순서
  (구식 호출은 신규 환경에서 즉사 — 이미 패치본 존재: legacy 폴더)

## 10. 환경 함정 목록

- pip: 시스템 따라 --break-system-packages 필요
- pyreadr: RDS 읽기용 (원본 아카이브 재다운로드 시에만 필요)
- worldfootballR 원본: raw.githubusercontent.com/JaseZiv/worldfootballR_data/master/
  data/fb_big5_advanced_season_stats/big5_player_{카테고리}.rds
- matplotlib 서버 사용 시 Agg 백엔드 강제
- Render 기존 서비스: FPP_PROTOTYPE / srv-d3u9hqhr0fns73apb93g / Docker 환경

## 11. 프로젝트 타임라인 (생기부 시점 관리용)

- 2025 (1학년): 아이디어 → FBref 크롤링 프로토타입 → Final_v3 → FastAPI 데모
  → Render 배포 시도 → Stats Perform 라이선스 문의 (10~11월)
- 2026-07 (2학년): GPT 인계 검증 → 완성/계획 분리 확정 → 데이터 재구축(worldfootballR)
  → 전처리·무결성 감사 → 이중 렌즈 능력점수 → 라벨 설계 → XGBoost v1 → v2(Δ피처)
  → 클러스터 부트스트랩 신뢰구간 검증 → 본 인계
- 다음 마일스톤: k-NN 유사선수 → 웹 서빙 → 최신 시즌 보충 → 진로활동 보고서

## 12. 보고서·문서 작성 규약 (소유자 확립 원칙)

- 성능 주장에는 검증 방법 병기 (in-sample/out-of-fold 구분)
- "세계 최초" 류 표현 금지 — 올바른 프레임: "산업 검증된 방법론(SciSports,
  PECOTA 계보)을 학생 수준에서 전 과정 재구현하고 한계까지 정량 측정"
- 완성 vs 계획 분리, 겸손한 수치(+5.0%)를 숨기지 않고 난이도 실측으로 해석
- 상업화 서사는 탐구 깊이에 종속 (입시 관점 주 서사는 탐구)
